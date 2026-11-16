#!/usr/bin/env node
// Снимает статические HTML-мокапы по плану и раскладывает их деревом разделов сайта.
//
//   node scripts/capture.mjs <out>/plan.json
//   node scripts/capture.mjs plan.json --only home,login --no-screenshots
//   node scripts/capture.mjs plan.json --clean        (удалить прошлый результат и кэш, снять заново)
//   node scripts/capture.mjs plan.json --keep-video   (скачивать файлы видео; по умолчанию у <video> только poster)
//
// Формат плана — references/plan-format.md. Относительные пути в плане (out, serve, storageState)
// считаются от папки plan.json. Результат — дерево, повторяющее URL сайта (корень = главная):
//   index.html [index--mobile.html] index.png      страница раздела
//   _states/  _modals/  _components/<группа>/       состояния, модалки, компоненты этой страницы
//   _css/  _media/                                  общее для раздела и подразделов
//   <подраздел>/...                                 то же самое глубже
//   README.md в каждом разделе, tokens.json/css, manifest.json, _catalog.html, capture-log.json
// Код выхода 1, если хоть один снимок не удался (остальные всё равно сохраняются).
import { readFileSync, existsSync, rmSync, unlinkSync } from "node:fs";
import { join, dirname, resolve, relative, extname, posix } from "node:path";
import { fileURLToPath } from "node:url";
import { loadPlaywright, parseArgs, writeFile, readJson, hash, ensureDir } from "./lib/runtime.mjs";
import { serveDir } from "./lib/serve.mjs";
import { runSteps } from "./lib/steps.mjs";
import { build, MARK } from "./lib/build.mjs";
import { linkContext } from "./lib/guide.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const SERIALIZE = readFileSync(join(HERE, "lib/page-serialize.js"), "utf8");
const TOKENS = readFileSync(join(HERE, "lib/page-tokens.js"), "utf8");
const SERVICE_STYLE_ID = "__mockup_service__";

const args = parseArgs(process.argv.slice(2), {
  only: {}, "no-screenshots": { type: "bool" }, clean: { type: "bool" }, "keep-video": { type: "bool" },
  help: { alias: "h", type: "bool" },
});
if (args.help || !args._[0]) {
  console.log(readFileSync(fileURLToPath(import.meta.url), "utf8").split("\n").filter((l) => l.startsWith("//")).map((l) => l.slice(3)).join("\n"));
  process.exit(args.help ? 0 : 2);
}

const planPath = resolve(args._[0]);
const planDir = dirname(planPath);
const plan = readJson(planPath);
const OUT = resolve(planDir, plan.out || ".");
const CACHE = join(OUT, ".mockup-cache");
const only = args.only ? new Set(args.only.split(",")) : null;
const D = {
  waitUntil: "load", navTimeout: 45000, settle: 600, disableAnimations: true, lazyScroll: true, hide: [], steps: [], timeout: 8000,
  screenshots: !args["no-screenshots"], ...(plan.defaults || {}),
};
const viewports = plan.viewports || { desktop: { width: 1440, height: 900 } };
const vpNames = Object.keys(viewports);

const log = { startedAt: new Date().toISOString(), errors: [], warnings: [] };
const manifest = [];
const tokenRuns = [];

// ---------- разделы: URL-путь → папка ----------
const slug = (s) => decodeURIComponent(s).toLowerCase().replace(/[^a-z0-9._-]+/g, "-").replace(/^[-.]+|-+$/g, "") || "x";
function sectionOf(path) {
  const u = new URL(path || "/", "http://x");
  const segs = u.pathname.split("/").filter(Boolean).map(slug).map((s) => (s.startsWith("_") ? "x" + s : s));
  if (u.search) segs.push((segs.pop() || "index") + "--" + slug(u.search.slice(1)));
  return segs.join("/");
}
function pagePathOf(ref) {
  const p = (plan.pages || []).find((x) => x.id === ref);
  return p ? p.path || "/" : ref || "/";
}
const sub = (folder, rest) => (folder ? `${folder}/${rest}` : rest);

// ---------- кэш: CSS и ассеты по одному экземпляру ----------
const assetMap = new Map(); // abs url -> ключ блоба (или null)
const blobFile = (k) => join(CACHE, "blobs", k);
let context;
const EXT_BY_TYPE = { "image/svg+xml": ".svg", "image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp", "image/gif": ".gif", "image/avif": ".avif", "font/woff2": ".woff2", "font/woff": ".woff", "font/ttf": ".ttf", "font/otf": ".otf", "video/mp4": ".mp4", "image/x-icon": ".ico" };
// Читаемое имя: исходное имя файла + короткий хэш (logo-3fa2c1d0.svg).
const nameFor = (src, salt, ext) => {
  let b = "";
  try { b = posix.basename(new URL(src).pathname).replace(/\.[^.]+$/, ""); } catch { b = String(src); }
  b = b.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 40) || "asset";
  return `${b}-${hash(salt, 8)}${ext}`;
};

async function download(url) {
  if (assetMap.has(url)) return assetMap.get(url);
  let key = null;
  try {
    const r = await context.request.get(url, { timeout: 20000 });
    if (!r.ok()) throw new Error("HTTP " + r.status());
    const body = await r.body();
    const type = (r.headers()["content-type"] || "").split(";")[0].trim();
    // Многие сайты на несуществующий файл отвечают 200 и HTML-страницей (SPA-фолбэк) — это не ассет.
    if (type === "text/html" || /^\s*<(!doctype|html)/i.test(body.subarray(0, 64).toString("utf8"))) throw new Error("вместо файла пришла HTML-страница");
    let ext = extname(new URL(url).pathname).toLowerCase();
    if (!ext || ext.length > 6) ext = EXT_BY_TYPE[type] || ".bin";
    if (ext === ".css") key = await saveCss(body.toString("utf8"), url, "", null);
    else {
      key = nameFor(url, body, ext); // хэш от содержимого: тот же файл — то же имя при любом адресе
      if (!existsSync(blobFile(key))) writeFile(blobFile(key), body);
    }
  } catch (e) {
    log.warnings.push(`ассет не скачан: ${url} (${e.message})`);
    key = null;
  }
  assetMap.set(url, key);
  return key;
}

// url() в CSS → метки блобов (пути расставит сборка)
// Ссылки из CSS — метки от URL (__MOCKUP_URL_<хэш>__): текст CSS выходит одинаковым на всех страницах,
// даже если одна страница файл использует, а другая нет. Путь или url("") подставит сборка по urls.json.
const urlsFile = () => join(CACHE, "urls.json");
const cssUrls = existsSync(urlsFile()) ? readJson(urlsFile()) : {}; // хэш -> { url, key }
const urlToken = (url, key) => {
  const h = hash(url, 12);
  const prev = cssUrls[h];
  cssUrls[h] = { url, key: key || (prev && prev.key) || null };
  return `__MOCKUP_URL_${h}__`;
};

async function rewriteCss(text, base, tokenAssets, unused) {
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
  const parts = [];
  let last = 0;
  for (const m of text.matchAll(/__MOCKUP_ASSET_(\d+)__|__RAW__(.+?)__RAW__/g)) {
    parts.push(text.slice(last, m.index));
    const url = m[1] !== undefined ? tokenAssets[+m[1]] : m[2];
    if (m[1] !== undefined && unused && unused.has(+m[1])) parts.push(urlToken(url, null));
    else {
      const k = await download(url);
      // @import ссылается на CSS-блоб — его связи сборка читает напрямую
      parts.push(k && k.endsWith(".css") ? `__MOCKUP_BLOB_${k}__` : urlToken(url, k));
    }
    last = m.index + m[0].length;
  }
  parts.push(text.slice(last));
  return parts.join("");
}

async function saveCss(text, base, media, tokenAssets, unused) {
  const css = await rewriteCss(text, base, tokenAssets, unused);
  const finalCss = media ? `@media ${media} {\n${css}\n}` : css;
  const key = nameFor(base && /^https?:/.test(base) && /\.css(\?|$)/.test(base) ? base : "inline", finalCss, ".css");
  if (!existsSync(blobFile(key))) writeFile(blobFile(key), finalCss);
  return key;
}

// ---------- снимок ----------
async function snapshot(page, opts, fileRel) {
  // Видео на паузу: кадр в мокапе и скриншот оригинала должны совпасть.
  await page.evaluate(() => document.querySelectorAll("video").forEach((v) => { try { v.pause(); } catch {} }));
  const res = await page.evaluate(`(${SERIALIZE})(${JSON.stringify({ ...opts, videoFrames: !args["keep-video"], media: plan.media, skipStyleIds: [SERVICE_STYLE_ID] })})`);
  if (!res.ok) throw new Error(res.error);
  const cssKeys = [];
  for (const s of res.sheets) {
    let k = null;
    if (s.text === null && s.href) {
      try {
        const r = await context.request.get(s.href, { timeout: 20000 });
        k = r.ok() ? await saveCss(await r.text(), s.href, s.media, null) : null;
      } catch { k = null; }
      if (!k) log.warnings.push(`CSS не получен: ${s.href}`);
    } else if (s.text) k = await saveCss(s.text, s.href || "inline", s.media, res.assets, new Set(res.unusedCss || []));
    if (k && !cssKeys.includes(k)) cssKeys.push(k);
  }
  let html = res.html;
  const idx = [...new Set([...html.matchAll(/__MOCKUP_(?:CSS)?ASSET_(\d+)__/g)].map((m) => +m[1]))];
  const keys = {};
  for (const i of idx) keys[i] = await download(res.assets[i]);
  // Не скачалось — пустое значение (URL есть в capture-log.json): внешняя ссылка сломала бы офлайн-мокап.
  html = html.replace(/__MOCKUP_ASSET_(\d+)__/g, (m, i) => (keys[i] ? `__MOCKUP_BLOB_${keys[i]}__` : ""))
    .replace(/__MOCKUP_CSSASSET_(\d+)__/g, (m, i) => (keys[i] ? `__MOCKUP_BLOBCSS_${keys[i]}__` : ""));
  // Кадры фоновых видео: скриншот области документа (clip + fullPage не скроллит страницу).
  const frameKeys = {};
  for (const [i, f] of (res.frames || []).entries()) {
    try {
      const clip = { x: Math.max(0, Math.floor(f.x)), y: Math.max(0, Math.floor(f.y)), width: Math.max(1, Math.round(f.width)), height: Math.max(1, Math.round(f.height)) };
      const png = await page.screenshot({ fullPage: true, clip });
      const k = `video-frame-${hash(png, 10)}.png`;
      if (!existsSync(blobFile(k))) writeFile(blobFile(k), png);
      frameKeys[i] = k;
    } catch (e) {
      log.warnings.push(`кадр видео не снят (${fileRel}): ${String(e.message).split("\n")[0]}`);
    }
  }
  html = html.replace(/__MOCKUP_FRAME_(\d+)__/g, (m, i) => (frameKeys[i] ? `__MOCKUP_BLOB_${frameKeys[i]}__` : ""));
  const links = cssKeys.map((k) => `<link rel="stylesheet" href="__MOCKUP_BLOB_${k}__">`).join("\n");
  const meta = `<meta charset="utf-8">\n<meta name="mockup-source" content="${page.url().replace(/"/g, "&quot;")}">\n`;
  html = html.replace(/<head([^>]*)>/i, `<head$1>\n${meta}`).replace(/<\/head>/i, `${links}\n</head>`);
  html = html.replace(/<meta charset="[^"]*">\s*(?=[\s\S]*<meta charset)/i, "");
  // Сайт раздавался из папки на временном порту — адрес бессмыслен, оставляем пути от корня сайта.
  if (plan.serve) html = html.split(new URL(plan.baseUrl).origin).join("");
  writeFile(join(CACHE, "raw", fileRel), html);
  return { rect: res.rect, title: res.title, placeholders: res.placeholders };
}

async function preparePage(page, url) {
  // Медленные сайты иногда не укладываются в таймаут — одна повторная попытка.
  for (let attempt = 1; ; attempt++) {
    try { await page.goto(url, { waitUntil: D.waitUntil, timeout: D.navTimeout }); break; }
    catch (e) {
      if (attempt >= 2 || !/Timeout/i.test(String(e.message))) throw e;
      log.warnings.push(`повторная загрузка после таймаута: ${url}`);
    }
  }
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

const suffix = (vp) => (vp === vpNames[0] ? "" : `--${vp}`);

// Куда кладётся элемент внутри папки своего раздела
function fileFor(item, vp, variant) {
  const folder = sectionOf(item.pagePath);
  const v = variant ? `--${variant}` : "";
  const name =
    item.kind === "page" ? `index${suffix(vp)}` :
    item.kind === "state" ? `_states/${item.id}${suffix(vp)}` :
    item.kind === "modal" ? `_modals/${item.id}${v}${suffix(vp)}` :
    `_components/${item.group || "misc"}/${item.id}${v}${suffix(vp)}`;
  return { folder, file: sub(folder, `${name}.html`) };
}

async function captureItem(page, item, vp) {
  const isPageLike = item.kind === "page" || item.kind === "state";
  const variants = item.all ? Math.min(await page.locator(item.selector).count(), item.limit || 12) : 1;
  if (item.all && !variants) throw new Error(`не найдено ни одного элемента: ${item.selector}`);
  for (let v = 0; v < variants; v++) {
    const id = item.all ? `${item.id}--${v + 1}` : item.id;
    const { folder, file } = fileFor(item, vp, item.all ? v + 1 : 0);
    const opts = isPageLike ? {} : { selector: item.selector, index: item.all ? v : item.index || 0, fitSize: item.fitSize ?? item.fitWidth };
    const info = await snapshot(page, opts, file);
    let shot = null;
    if (D.screenshots) {
      shot = file.replace(/\.html$/, ".png");
      ensureDir(dirname(join(OUT, shot)));
      try {
        if (isPageLike) await page.screenshot({ path: join(OUT, shot), fullPage: true });
        else {
          const loc = page.locator(item.selector).nth(opts.index);
          // Элемент выше окна Playwright снимает прокруткой, и fixed/sticky-слои страницы (шапка,
          // липкие заголовки) налезают на него. Такой элемент снимаем куском полной страницы —
          // в режиме fullPage fixed-слои рисуются один раз на своём месте, а не над элементом.
          const box = await loc.evaluate((el) => {
            const r = el.getBoundingClientRect();
            return { x: r.left + scrollX, y: r.top + scrollY, width: r.width, height: r.height, tall: r.height > innerHeight };
          }, null, { timeout: 5000 });
          if (box.tall) await page.screenshot({ path: join(OUT, shot), fullPage: true,
            clip: { x: Math.max(0, box.x), y: Math.max(0, box.y), width: box.width, height: box.height } });
          else await loc.screenshot({ path: join(OUT, shot), timeout: 5000 });
        }
      } catch (e) {
        log.warnings.push(`${id}: скриншот не снят (${String(e.message).split("\n")[0]})`);
        shot = null;
      }
    }
    manifest.push({
      id: id + suffix(vp), baseId: item.id, kind: item.kind, variant: item.all ? v + 1 : undefined,
      group: item.kind === "component" ? item.group || "misc" : item.kind === "modal" ? item.group || "modals" : item.kind === "state" ? "states" : "pages",
      title: item.title || (item.kind === "page" ? info.title : item.id), viewport: vp, section: folder, pagePath: item.pagePath,
      file, screenshot: shot, sourceUrl: plan.serve ? new URL(page.url()).pathname : page.url(), selector: item.selector, steps: item.steps, notes: item.notes,
      size: info.rect ? { width: Math.round(info.rect.width), height: Math.round(info.rect.height) } : null,
      placeholders: info.placeholders && (info.placeholders.image || info.placeholders.video) ? info.placeholders : undefined,
    });
    console.log(`  + ${file}`);
  }
}

// Удалить всё, что генерировала прошлая сборка (по манифесту), и кэш. Чужие файлы не трогаем.
function cleanPrevious() {
  const mf = join(OUT, "manifest.json");
  if (existsSync(mf)) {
    for (const f of readJson(mf).generated || []) {
      const p = join(OUT, f);
      if (!existsSync(p)) continue;
      if (f.endsWith("README.md") && !readFileSync(p, "utf8").startsWith(MARK)) continue;
      unlinkSync(p);
    }
    unlinkSync(mf);
  }
  rmSync(CACHE, { recursive: true, force: true });
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
  if (args.clean) cleanPrevious();
  ensureDir(OUT);

  const browser = await chromium.launch();
  const items = [
    // страница со steps — это состояние страницы: кладётся в _states/ раздела
    ...(plan.pages || []).map((x) => ({ ...x, kind: x.steps && x.steps.length ? "state" : "page", pageRef: x.id, pagePath: x.path || "/" })),
    ...(plan.components || []).map((x) => ({ ...x, kind: "component", pageRef: x.page, pagePath: pagePathOf(x.page) })),
    ...(plan.modals || []).map((x) => ({ ...x, kind: "modal", pageRef: x.page, pagePath: pagePathOf(x.page) })),
  ].filter((x) => !only || only.has(x.id));
  for (const x of items) if (!x.id || (x.kind === "component" || x.kind === "modal") && !x.selector) throw new Error(`элементу плана нужны id и selector: ${JSON.stringify(x)}`);
  const seenPage = new Map();
  for (const x of items.filter((i) => i.kind === "page")) {
    const f = sectionOf(x.pagePath);
    if (seenPage.has(f)) throw new Error(`страницы «${seenPage.get(f)}» и «${x.id}» попадают в одну папку раздела «${f || "/"}» — для второй задай другой path или сделай её состоянием (steps)`);
    seenPage.set(f, x.id);
  }

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
      const key = x.steps && x.steps.length ? `__solo__${x.kind}:${x.id}` : x.pagePath;
      (groups.get(key) || groups.set(key, []).get(key)).push(x);
    }
    for (const [key, list] of groups) {
      const page = await context.newPage();
      const url = new URL(list[0].pagePath, plan.baseUrl).href;
      try {
        await preparePage(page, url);
        if (vp === vpNames[0] && !key.startsWith("__solo__") && list.some((x) => x.kind === "page")) {
          try { tokenRuns.push(await page.evaluate(`(${TOKENS})()`)); } catch {}
        }
        for (const x of list) {
          try {
            if (x.steps) await runSteps(page, x.steps, url, D.timeout);
            if (x.steps) await page.waitForTimeout(x.settle ?? 300);
            await captureItem(page, x, vp);
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
  // При частичной пересъёмке (--only) или если страниц в прогоне не было — прежние токены.
  let tokens = { source: plan.serve ? `папка ${plan.serve}` : plan.baseUrl, cssVariables: vars };
  for (const [cat, vals] of Object.entries(stats)) {
    tokens[cat] = Object.entries(vals).sort((a, b) => b[1] - a[1]).slice(0, cat === "fontFamily" ? 10 : 30).map(([value, count]) => ({ value, count }));
  }
  const tokensFile = join(OUT, "tokens.json");
  if ((only || !tokenRuns.length) && existsSync(tokensFile)) tokens = readJson(tokensFile);
  else {
    if (!tokenRuns.length) log.warnings.push("токены не собраны: в плане нет страниц без steps");
    writeFile(tokensFile, JSON.stringify(tokens, null, 2));
    const rootVars = Object.entries(vars).filter(([k]) => !k.includes(" @ "));
    writeFile(join(OUT, "tokens.css"), `/* CSS-переменные сайта (собраны site-mockups) */\n:root {\n${rootVars.map(([k, v]) => `  ${k}: ${v};`).join("\n")}\n}\n`);
  }

  // ---------- сборка дерева ----------
  const mf = join(OUT, "manifest.json");
  const prevDoc = existsSync(mf) ? readJson(mf) : {};
  const ids = new Set(manifest.map((m) => m.id));
  const prevItems = only ? (prevDoc.items || []).filter((m) => !ids.has(m.id) && !only.has(m.baseId)) : [];
  const doc = {
    generator: "site-mockups", layout: "sections", source: plan.serve ? `сборка ${plan.serve}` : plan.baseUrl, createdAt: new Date().toISOString(),
    plan: relative(OUT, resolve(planPath)).split("\\").join("/") || "plan.json", viewports, primaryViewport: vpNames[0], cssBundle: plan.cssBundle !== false, items: [...prevItems, ...manifest], generated: prevDoc.generated || [],
  };
  writeFile(urlsFile(), JSON.stringify(cssUrls));
  build(OUT, doc, tokens, log);
  // Указатель на гайд в файле инструкций проекта (AGENTS.md, CLAUDE.md…) — куда, решает пользователь (plan.context).
  const ctx = [].concat(plan.context || []).map((f) => resolve(planDir, f));
  if (ctx.length) {
    doc.context = [];
    for (const r of linkContext(ctx, join(OUT, "GUIDE.md"), doc, log)) {
      doc.context.push(relative(OUT, r.file).split("\\").join("/"));
      console.log(`  контекст: ${relative(process.cwd(), r.file) || r.file} — ${r.action}`);
    }
  }
  writeFile(mf, JSON.stringify(doc, null, 2));
  log.finishedAt = new Date().toISOString();
  // При частичной пересъёмке дописываем лог: предупреждения полного прогона не должны пропасть.
  const logFile = join(OUT, "capture-log.json");
  if (only && existsSync(logFile)) {
    const prevLog = readJson(logFile);
    log.errors = [...(prevLog.errors || []).filter((e) => !only.has(e.id)), ...log.errors];
    log.warnings = [...new Set([...(prevLog.warnings || []), ...log.warnings])];
    log.startedAt = prevLog.startedAt || log.startedAt;
  }
  writeFile(logFile, JSON.stringify(log, null, 2));

  const shown = relative(process.cwd(), OUT);
  console.log(`\nГотово: ${manifest.length} снимков, ${doc.sections.length} разделов → ${shown && !shown.startsWith("..") ? shown : OUT}/README.md (каталог: _catalog.html)`);
  if (log.warnings.length) console.log(`Предупреждений: ${log.warnings.length} (capture-log.json)`);
  if (log.errors.length) {
    console.log(`Ошибок: ${log.errors.length}:`);
    for (const e of log.errors) console.log(`  ✗ ${e.id} [${e.viewport}]: ${e.error}`);
    process.exit(1);
  }
}

main().catch((e) => { console.error("error: " + e.message); process.exit(1); });
