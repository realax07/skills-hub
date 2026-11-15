#!/usr/bin/env node
// Снимает статические HTML-мокапы по плану: страницы целиком, отдельные компоненты, модалки и состояния.
//
//   node scripts/capture.mjs <out>/plan.json
//   node scripts/capture.mjs plan.json --only home,login-modal --no-screenshots
//
// Формат плана — references/plan-format.md. Относительные пути в плане (out, serve, storageState)
// считаются от папки plan.json. Результат:
//   pages/<id>.html  components/<group>/<id>.html  modals/<id>.html
//   assets/css/*.css  assets/media/*  screenshots/**.png
//   tokens.json  tokens.css  manifest.json  index.html (каталог)  README.md  capture-log.json
// Код выхода 1, если хоть один снимок не удался (остальные всё равно сохраняются).
import { readFileSync, existsSync, rmSync } from "node:fs";
import { join, dirname, resolve, relative, extname, posix } from "node:path";
import { fileURLToPath } from "node:url";
import { loadPlaywright, parseArgs, writeFile, readJson, hash, ensureDir } from "./lib/runtime.mjs";
import { serveDir } from "./lib/serve.mjs";
import { runSteps } from "./lib/steps.mjs";
import { buildCatalog } from "./lib/catalog.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const SERIALIZE = readFileSync(join(HERE, "lib/page-serialize.js"), "utf8");
const TOKENS = readFileSync(join(HERE, "lib/page-tokens.js"), "utf8");
const SERVICE_STYLE_ID = "__mockup_service__";

const args = parseArgs(process.argv.slice(2), {
  only: {}, "no-screenshots": { type: "bool" }, clean: { type: "bool" }, help: { alias: "h", type: "bool" },
});
if (args.help || !args._[0]) {
  console.log(readFileSync(fileURLToPath(import.meta.url), "utf8").split("\n").filter((l) => l.startsWith("//")).map((l) => l.slice(3)).join("\n"));
  process.exit(args.help ? 0 : 2);
}

const planPath = resolve(args._[0]);
const planDir = dirname(planPath);
const plan = readJson(planPath);
const OUT = resolve(planDir, plan.out || ".");
const only = args.only ? new Set(args.only.split(",")) : null;
const D = {
  waitUntil: "load", settle: 600, disableAnimations: true, lazyScroll: true, hide: [], steps: [], timeout: 8000,
  screenshots: !args["no-screenshots"], ...(plan.defaults || {}),
};
const viewports = plan.viewports || { desktop: { width: 1440, height: 900 } };
const vpNames = Object.keys(viewports);

const log = { startedAt: new Date().toISOString(), errors: [], warnings: [] };
const manifest = [];
const tokenRuns = [];

// ---------- ассеты ----------
const assetMap = new Map(); // abs url -> path from OUT (posix)
const cssMap = new Map(); // content hash -> path
let context;

const EXT_BY_TYPE = { "image/svg+xml": ".svg", "image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp", "image/gif": ".gif", "image/avif": ".avif", "font/woff2": ".woff2", "font/woff": ".woff", "font/ttf": ".ttf", "font/otf": ".otf", "video/mp4": ".mp4", "image/x-icon": ".ico" };

async function download(url) {
  if (assetMap.has(url)) return assetMap.get(url);
  let rel = null;
  try {
    const r = await context.request.get(url, { timeout: 20000 });
    if (!r.ok()) throw new Error("HTTP " + r.status());
    const body = await r.body();
    let ext = extname(new URL(url).pathname).toLowerCase();
    if (!ext || ext.length > 6) ext = EXT_BY_TYPE[(r.headers()["content-type"] || "").split(";")[0]] || ".bin";
    if (ext === ".css") {
      rel = await saveCss(body.toString("utf8"), url, "", null);
    } else {
      rel = `assets/media/${hash(url)}${ext}`;
      writeFile(join(OUT, rel), body);
    }
  } catch (e) {
    log.warnings.push(`ассет не скачан: ${url} (${e.message})`);
    rel = null;
  }
  assetMap.set(url, rel);
  return rel;
}

// Заменить токены/URL в CSS на локальные пути (относительно assets/css/)
async function rewriteCss(text, base, tokenAssets) {
  if (!tokenAssets) {
    // CSS, скачанный раннером: url() ещё не токенизированы
    text = text.replace(/url\(\s*(['"]?)([^'")]+)\1\s*\)/g, (m, q, u) => {
      if (/^(data:|#|%23)/.test(u.trim())) return m;
      try { return `url("__RAW__${new URL(u.trim(), base).href}__RAW__")`; } catch { return m; }
    });
    text = text.replace(/@import\s+(?:url\()?\s*['"]([^'"]+)['"]\s*\)?([^;]*);/g, (m, u, media) => {
      try { return `@import url("__RAW__${new URL(u, base).href}__RAW__")${media};`; } catch { return m; }
    });
  }
  const resolveOne = async (abs) => {
    const p = await download(abs);
    return p ? posix.relative("assets/css", p) : abs;
  };
  const parts = [];
  let last = 0;
  const re = /__MOCKUP_ASSET_(\d+)__|__RAW__(.+?)__RAW__/g;
  for (const m of text.matchAll(re)) {
    parts.push(text.slice(last, m.index));
    const abs = m[1] !== undefined ? tokenAssets[+m[1]] : m[2];
    parts.push(await resolveOne(abs));
    last = m.index + m[0].length;
  }
  parts.push(text.slice(last));
  return parts.join("");
}

async function saveCss(text, base, media, tokenAssets) {
  const css = await rewriteCss(text, base, tokenAssets);
  const finalCss = media ? `@media ${media} {\n${css}\n}` : css;
  const h = hash(finalCss, 12);
  if (!cssMap.has(h)) {
    const rel = `assets/css/${h}.css`;
    writeFile(join(OUT, rel), finalCss);
    cssMap.set(h, rel);
  }
  return cssMap.get(h);
}

// ---------- снимок ----------
async function snapshot(page, opts, fileRel) {
  const res = await page.evaluate(`(${SERIALIZE})(${JSON.stringify({ ...opts, skipStyleIds: [SERVICE_STYLE_ID] })})`);
  if (!res.ok) throw new Error(res.error);
  const fileDir = posix.dirname(fileRel);
  // CSS
  const cssFiles = [];
  for (const s of res.sheets) {
    let rel;
    if (s.text === null && s.href) {
      try {
        const r = await context.request.get(s.href, { timeout: 20000 });
        rel = r.ok() ? await saveCss(await r.text(), s.href, s.media, null) : null;
      } catch { rel = null; }
      if (!rel) log.warnings.push(`CSS не получен: ${s.href}`);
    } else if (s.text) rel = await saveCss(s.text, s.href || page.url(), s.media, res.assets);
    if (rel && !cssFiles.includes(rel)) cssFiles.push(rel);
  }
  // HTML-ассеты
  let html = res.html;
  const idx = [...new Set([...html.matchAll(/__MOCKUP_ASSET_(\d+)__/g)].map((m) => +m[1]))];
  const local = {};
  for (const i of idx) {
    const p = await download(res.assets[i]);
    local[i] = p ? posix.relative(fileDir, p) : res.assets[i];
  }
  html = html.replace(/__MOCKUP_ASSET_(\d+)__/g, (m, i) => local[i]);
  const links = cssFiles.map((c) => `<link rel="stylesheet" href="${posix.relative(fileDir, c)}">`).join("\n");
  const meta = `<meta charset="utf-8">\n<meta name="mockup-source" content="${page.url().replace(/"/g, "&quot;")}">\n`;
  html = html.replace(/<head([^>]*)>/i, `<head$1>\n${meta}`).replace(/<\/head>/i, `${links}\n</head>`);
  html = html.replace(/<meta charset="[^"]*">\s*(?=[\s\S]*<meta charset)/i, "");
  writeFile(join(OUT, fileRel), html);
  return { rect: res.rect, title: res.title, bytes: html.length };
}

async function preparePage(page, url) {
  await page.goto(url, { waitUntil: D.waitUntil, timeout: 30000 });
  await page.waitForLoadState("networkidle", { timeout: 8000 }).catch(() => {});
  if (D.disableAnimations) {
    await page.addStyleTag({ content: "*,*::before,*::after{animation-duration:0s!important;animation-delay:0s!important;transition:none!important;caret-color:transparent!important;scroll-behavior:auto!important}" })
      .then((h) => h.evaluate((el, id) => (el.id = id), SERVICE_STYLE_ID));
  }
  if (D.lazyScroll) {
    await page.evaluate(async () => {
      const step = window.innerHeight * 0.8;
      for (let y = 0; y < document.body.scrollHeight && y < 40000; y += step) {
        window.scrollTo(0, y);
        await new Promise((r) => setTimeout(r, 120));
      }
      window.scrollTo(0, 0);
    });
    await page.waitForLoadState("networkidle", { timeout: 5000 }).catch(() => {});
  }
  await page.evaluate(() => document.fonts && document.fonts.ready);
  await runSteps(page, D.steps, url, D.timeout);
  if (D.hide.length) await page.evaluate((sels) => sels.forEach((s) => document.querySelectorAll(s).forEach((e) => e.remove())), D.hide);
  await page.waitForTimeout(D.settle);
}

function pageUrl(ref) {
  const p = (plan.pages || []).find((x) => x.id === ref);
  const path = p ? p.path : ref || "/";
  return new URL(path, plan.baseUrl).href;
}

const suffix = (vp) => (vp === vpNames[0] ? "" : `--${vp}`);

async function captureItem(page, item, vp, kind) {
  const base = kind === "page" ? `pages/${item.id}` : kind === "modal" ? `modals/${item.id}` : `components/${item.group || "misc"}/${item.id}`;
  const variants = item.all ? Math.min(await page.locator(item.selector).count(), item.limit || 12) : 1;
  if (item.all && !variants) throw new Error(`не найдено ни одного элемента: ${item.selector}`);
  for (let v = 0; v < variants; v++) {
    const id = item.all ? `${item.id}--${v + 1}` : item.id;
    const fileRel = `${item.all ? base + "--" + (v + 1) : base}${suffix(vp)}.html`;
    const opts = kind === "page" ? {} : { selector: item.selector, index: item.all ? v : item.index || 0, fitSize: item.fitSize ?? item.fitWidth };
    const info = await snapshot(page, opts, fileRel);
    let shot = null;
    if (D.screenshots) {
      shot = fileRel.replace(/\.html$/, ".png").replace(/^/, "screenshots/");
      ensureDir(dirname(join(OUT, shot)));
      try {
        if (kind === "page") await page.screenshot({ path: join(OUT, shot), fullPage: true });
        else await page.locator(item.selector).nth(opts.index).screenshot({ path: join(OUT, shot), timeout: 5000 });
      } catch (e) {
        log.warnings.push(`${id}: скриншот не снят (${String(e.message).split("\n")[0]})`);
        shot = null;
      }
    }
    manifest.push({
      id: id + suffix(vp), baseId: item.id, kind, group: kind === "page" ? "pages" : kind === "modal" ? item.group || "modals" : item.group || "misc",
      title: item.title || (kind === "page" ? info.title : item.id), viewport: vp, file: fileRel, screenshot: shot,
      sourceUrl: page.url(), selector: item.selector, steps: item.steps, notes: item.notes,
      size: info.rect ? { width: Math.round(info.rect.width), height: Math.round(info.rect.height) } : null, bytes: info.bytes,
    });
    console.log(`  + ${fileRel}`);
  }
}

async function main() {
  const { chromium } = await loadPlaywright();
  let server;
  if (plan.serve) {
    server = await serveDir(resolve(planDir, plan.serve));
    plan.baseUrl = server.url;
    console.log(`→ раздаю ${plan.serve} на ${server.url}`);
  }
  if (!plan.baseUrl) throw new Error("в плане нужен baseUrl или serve");
  if (args.clean) for (const d of ["pages", "components", "modals", "assets", "screenshots"]) rmSync(join(OUT, d), { recursive: true, force: true });
  ensureDir(OUT);

  const browser = await chromium.launch();
  const items = [
    ...(plan.pages || []).map((x) => ({ ...x, kind: "page", pageRef: x.id })),
    ...(plan.components || []).map((x) => ({ ...x, kind: "component", pageRef: x.page })),
    ...(plan.modals || []).map((x) => ({ ...x, kind: "modal", pageRef: x.page })),
  ].filter((x) => !only || only.has(x.id));
  for (const x of items) if (!x.id || (x.kind !== "page" && !x.selector)) throw new Error(`элементу плана нужны id и selector: ${JSON.stringify(x)}`);

  for (const vp of vpNames) {
    const cfg = viewports[vp];
    context = await browser.newContext({
      viewport: { width: cfg.width, height: cfg.height }, deviceScaleFactor: cfg.deviceScaleFactor || 1,
      isMobile: !!cfg.isMobile, hasTouch: !!cfg.isMobile, userAgent: cfg.userAgent,
      storageState: plan.storageState ? resolve(planDir, plan.storageState) : undefined,
      locale: plan.locale, colorScheme: cfg.colorScheme || plan.colorScheme,
    });
    console.log(`> viewport ${vp} ${cfg.width}x${cfg.height}`);
    const mine = items.filter((x) => !x.viewports || x.viewports.includes(vp));
    // Без шагов — снимаем пачкой с одной загрузки страницы; с шагами — каждую в свежей вкладке.
    const groups = new Map();
    for (const x of mine) {
      const key = x.steps && x.steps.length ? `__solo__${x.kind}:${x.id}` : x.pageRef || "/";
      (groups.get(key) || groups.set(key, []).get(key)).push(x);
    }
    for (const [key, list] of groups) {
      const page = await context.newPage();
      const url = pageUrl(list[0].pageRef);
      try {
        await preparePage(page, url);
        if (vp === vpNames[0] && !key.startsWith("__solo__") && list.some((x) => x.kind === "page")) {
          try { tokenRuns.push(await page.evaluate(`(${TOKENS})()`)); } catch {}
        }
        for (const x of list) {
          try {
            if (x.steps) await runSteps(page, x.steps, url, D.timeout);
            if (x.steps) await page.waitForTimeout(x.settle ?? 300);
            await captureItem(page, x, vp, x.kind);
          } catch (e) {
            log.errors.push({ id: x.id, viewport: vp, error: String(e.message).split("\n")[0] });
            console.log(`  ✗ ${x.id} [${vp}]: ${String(e.message).split("\n")[0]}`);
          }
        }
      } catch (e) {
        for (const x of list) log.errors.push({ id: x.id, viewport: vp, error: `страница ${url}: ${String(e.message).split("\n")[0]}` });
        console.log(`  ✗ ${url}: ${String(e.message).split("\n")[0]}`);
      }
      await page.close();
    }
    await context.close();
  }
  await browser.close();
  if (server) server.close();

  // ---------- токены ----------
  const vars = {};
  const stats = {};
  for (const t of tokenRuns) {
    Object.assign(vars, t.vars);
    for (const [cat, vals] of Object.entries(t.stats)) {
      stats[cat] ||= {};
      for (const [v, n] of Object.entries(vals)) stats[cat][v] = (stats[cat][v] || 0) + n;
    }
  }
  // Токены собираются со страниц плана. При частичной пересъёмке (--only) или если страниц
  // в прогоне не было, оставляем прежние tokens.json/tokens.css — иначе затрём их пустыми.
  let tokens = { source: plan.baseUrl, cssVariables: vars };
  for (const [cat, vals] of Object.entries(stats)) {
    tokens[cat] = Object.entries(vals).sort((a, b) => b[1] - a[1]).slice(0, cat === "fontFamily" ? 10 : 30).map(([value, count]) => ({ value, count }));
  }
  const tokensFile = join(OUT, "tokens.json");
  if ((only || !tokenRuns.length) && existsSync(tokensFile)) {
    tokens = readJson(tokensFile);
    if (!tokenRuns.length && !only) log.warnings.push("токены не собраны: в плане нет страниц без steps");
  } else {
    if (!tokenRuns.length) log.warnings.push("токены не собраны: в плане нет страниц без steps");
    writeFile(tokensFile, JSON.stringify(tokens, null, 2));
    const rootVars = Object.entries(vars).filter(([k]) => !k.includes(" @ "));
    writeFile(join(OUT, "tokens.css"), `/* CSS-переменные сайта (собраны site-mockups) */\n:root {\n${rootVars.map(([k, v]) => `  ${k}: ${v};`).join("\n")}\n}\n`);
  }

  // ---------- манифест, каталог ----------
  const prev = existsSync(join(OUT, "manifest.json")) && only ? readJson(join(OUT, "manifest.json")).items || [] : [];
  const ids = new Set(manifest.map((m) => m.id));
  const all = [...prev.filter((m) => !ids.has(m.id)), ...manifest];
  const doc = { generator: "site-mockups", source: plan.baseUrl, createdAt: new Date().toISOString(), viewports, items: all };
  writeFile(join(OUT, "manifest.json"), JSON.stringify(doc, null, 2));
  buildCatalog(OUT, doc, tokens);
  log.finishedAt = new Date().toISOString();
  writeFile(join(OUT, "capture-log.json"), JSON.stringify(log, null, 2));

  const shown = relative(process.cwd(), OUT);
  console.log(`\nГотово: ${manifest.length} снимков → ${shown && !shown.startsWith("..") ? shown : OUT}/index.html`);
  if (log.warnings.length) console.log(`Предупреждений: ${log.warnings.length} (capture-log.json)`);
  if (log.errors.length) {
    console.log(`Ошибок: ${log.errors.length}:`);
    for (const e of log.errors) console.log(`  ✗ ${e.id} [${e.viewport}]: ${e.error}`);
    process.exit(1);
  }
}

main().catch((e) => { console.error("error: " + e.message); process.exit(1); });
