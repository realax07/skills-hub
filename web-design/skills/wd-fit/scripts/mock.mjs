#!/usr/bin/env node
// Мокапы доработки на утверждение: три варианта нового блока прямо в странице сайта (копия из эталона design-context),
// проверка каждого check.mjs, мера различия вариантов и страница сравнения. Реализация в коде — после выбора человека.
//
//   node scripts/mock.mjs new --context design-context --out design-mocks/pricing --page home
//   node scripts/mock.mjs new … --page home --where "#cards" --position after       куда вставить блок
//   node scripts/mock.mjs build --out design-mocks/pricing                            собрать, проверить, сравнить
//   node scripts/mock.mjs build --out design-mocks/pricing --no-check                 только собрать и снять скриншоты
//
// new:   пишет <out>/mock.json, PLAN.md (заполнить до вёрстки), a|b|c.fragment.html (заготовки) и печатает
//        блоки страницы — кандидаты для --where. --page — id страницы из плана wd-scan или URL-путь (/pricing).
//        --position: after | before | append | prepend (по умолчанию: перед футером, иначе в конец main/body).
//        --force — заново записать mock.json (другое место вставки); PLAN.md и фрагменты не перезаписываются.
// build: собирает <out>/a.html, b.html, c.html (страница эталона + фрагмент в <div data-wd-mock="…">),
//        запускает check.mjs по каждому (все темы контекста), меряет различие, пишет <out>/index.html и mock-report.json.
// Код выхода: 0 — всё пройдено; 1 — есть нарушения check, похожие варианты или незаполненный план; 2 — ошибка запуска.
// Как придумать три разных варианта — references/mock-patterns.md; процесс — SKILL.md, шаг «Варианты на утверждение».
import { readFileSync, existsSync, writeFileSync, mkdirSync, copyFileSync } from "node:fs";
import { join, resolve, dirname, relative, sep } from "node:path";
import { fileURLToPath } from "node:url";
import { execFileSync } from "node:child_process";
import { loadPlaywright, parseArgs, readJson } from "./lib/runtime.mjs";
import { serveDir } from "./lib/serve.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const SKILL = resolve(HERE, "..");
const args = parseArgs(process.argv.slice(2), {
  context: { default: "design-context" }, out: {}, page: {}, where: {}, position: {}, "no-check": { type: "bool" },
  force: { type: "bool" }, help: { alias: "h", type: "bool" },
});
const cmd = args._[0];
if (args.help || !["new", "build"].includes(cmd)) {
  console.log(readFileSync(fileURLToPath(import.meta.url), "utf8").split("\n").filter((l) => l.startsWith("//")).map((l) => l.slice(3)).join("\n"));
  process.exit(args.help ? 0 : 2);
}
const die = (m) => { console.error("error: " + m); process.exit(2); };
if (!args.out) die("нужен --out <папка мокапов>, например design-mocks/<задача>");
const OUT = resolve(args.out);
const LETTERS = ["a", "b", "c"];
const posix = (p) => p.split(sep).join("/");
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);

// общий предок двух папок — корень локального сервера (страница эталона и мокапы должны быть видны с одного адреса)
function commonRoot(a, b) {
  const x = a.split(sep), y = b.split(sep);
  let i = 0;
  while (i < x.length && i < y.length && x[i] === y[i]) i++;
  return x.slice(0, i).join(sep) || sep;
}

// ---------- new ----------
async function cmdNew() {
  const CTX = resolve(args.context);
  const REF = join(CTX, "reference");
  if (!existsSync(join(REF, "manifest.json"))) die(`нет ${join(REF, "manifest.json")} — нет дизайн-контекста (скилл wd-scan)`);
  if (existsSync(join(OUT, "mock.json")) && !args.force) die(`${join(args.out, "mock.json")} уже есть — продолжай с build; другое место вставки — добавь --force (PLAN.md и фрагменты останутся); начать заново — удали папку`);
  if (!args.page) die("нужен --page: id страницы из плана wd-scan (home, about…) или URL-путь (/pricing)");
  const doc = readJson(join(REF, "manifest.json"));
  const pages = doc.items.filter((i) => i.kind === "page" && i.viewport === doc.primaryViewport && !i.variant);
  const norm = (p) => (p || "/").replace(/\/+$/, "") || "/";
  const item = pages.find((p) => p.baseId === args.page || p.id === args.page) || pages.find((p) => norm(p.pagePath) === norm(args.page));
  if (!item) die(`страницы «${args.page}» нет в эталоне; есть: ${pages.map((p) => `${p.baseId} (${p.pagePath})`).join(", ")}`);
  const refFile = join(REF, item.file);
  const hasRef = existsSync(refFile);
  mkdirSync(OUT, { recursive: true });

  // блоки страницы — кандидаты для --where
  let blocks = [];
  if (hasRef) {
    const { chromium } = await loadPlaywright();
    const server = await serveDir(dirname(refFile));
    const browser = await chromium.launch();
    try {
      const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
      await page.goto(`${server.url}/${item.file.split("/").pop()}`, { waitUntil: "load" });
      blocks = await page.evaluate(() => {
        const root = document.querySelector("main") || document.body;
        const kids = [...(root === document.body ? document.body.children : [...document.body.children].flatMap((e) => (e === root ? [...root.children] : [e])))];
        const sel = (el) => {
          if (el.id) return "#" + CSS.escape(el.id);
          const tag = el.tagName.toLowerCase();
          const cls = [...el.classList].filter((c) => !/^(js-|is-|has-)/.test(c))[0];
          const same = [...el.parentElement.children].filter((x) => x.tagName === el.tagName);
          const base = cls ? `${tag}.${CSS.escape(cls)}` : tag;
          const sib = [...el.parentElement.querySelectorAll(":scope > " + base)];
          return (el.parentElement === document.body ? "body > " : el.parentElement.tagName === "MAIN" ? "main > " : "") + (sib.length > 1 ? `${base}:nth-of-type(${same.indexOf(el) + 1})` : base);
        };
        return kids.filter((e) => !/^(SCRIPT|STYLE|LINK|META|TEMPLATE)$/.test(e.tagName) && e.getBoundingClientRect().height > 0).map((e) => {
          const h = e.querySelector("h1,h2,h3");
          return { selector: sel(e), tag: e.tagName.toLowerCase(), height: Math.round(e.getBoundingClientRect().height), what: (h ? h.textContent : e.textContent).trim().replace(/\s+/g, " ").slice(0, 60) };
        });
      });
    } finally { await browser.close(); server.close(); }
  }
  const footer = blocks.find((b) => b.tag === "footer");
  const where = args.where || (footer ? footer.selector : null);
  const position = args.position || (args.where ? "after" : footer ? "before" : "append");
  const M = { context: posix(relative(OUT, CTX)) || ".", page: item.baseId, path: item.pagePath, ref: hasRef ? posix(relative(OUT, refFile)) : null,
    where, position, createdAt: new Date().toISOString() };
  writeFileSync(join(OUT, "mock.json"), JSON.stringify(M, null, 2));
  // PLAN.md и фрагменты кладутся, только если их нет: --force меняет место вставки, а не работу агента
  if (!existsSync(join(OUT, "PLAN.md"))) copyFileSync(join(SKILL, "assets/mock-plan.template.md"), join(OUT, "PLAN.md"));
  for (const l of LETTERS) {
    const f = join(OUT, `${l}.fragment.html`);
    if (!existsSync(f)) writeFileSync(f, readFileSync(join(SKILL, "assets/mock-fragment.template.html"), "utf8").replaceAll("{{L}}", l).replaceAll("{{LU}}", l.toUpperCase()));
  }
  console.log(`Мокапы: ${args.out} · страница ${item.baseId} (${item.pagePath})`);
  if (!hasRef) console.log(`! в эталоне нет ${posix(relative(process.cwd(), refFile))} (reference/ не сохранён или не снят): блок будет на пустой странице только с tokens.css — классы сайта не применятся. Лучше переснять wd-scan.`);
  if (blocks.length) {
    console.log("\nБлоки страницы (сверху вниз) — для --where:");
    for (const b of blocks) console.log(`  ${b.selector.padEnd(34)} ${String(b.height).padStart(5)}px  ${b.what}`);
  }
  console.log(`\nВставка: ${where ? `${position} ${where}` : `${position} в main/body`}${args.where ? "" : " (по умолчанию; поменять — new --force --where … --position …)"}`);
  console.log(`\nДальше:\n  1. PLAN.md — задача и три разных подхода (references/mock-patterns.md), до вёрстки\n  2. a|b|c.fragment.html — разметка и стили блока, только классы и переменные сайта\n  3. node <skill>/scripts/mock.mjs build --out ${args.out}`);
}

// ---------- build ----------
function planIssues(md) {
  const I = [];
  const left = (md.match(/‹заполни›/g) || []).length;
  if (left) I.push(`в PLAN.md не заполнено ${left} мест «‹заполни›»`);
  const appr = LETTERS.map((l) => { const m = md.match(new RegExp(`^## ${l.toUpperCase()}\\b[\\s\\S]*?\\*\\*Подход[^*]*\\*\\*\\s*(.+)`, "mi")); return m ? m[1].trim().toLowerCase() : ""; });
  if (!left && appr.some((a) => a.length < 12)) I.push("PLAN.md: у каждого варианта нужен «Подход (UX)» — паттерн и сценарий одной-двумя фразами");
  if (!left && new Set(appr).size < appr.length) I.push("PLAN.md: подходы вариантов совпадают — варианты должны различаться сценарием (references/mock-patterns.md)");
  return I;
}

const STATS = (sel) => {
  const W = document.querySelector(sel);
  if (!W) return null;
  const wr = W.getBoundingClientRect();
  const lum = (c) => { const m = c.match(/[\d.]+/g); if (!m) return 1; const [r, g, b] = m.slice(0, 3).map((v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; }); return 0.2126 * r + 0.7152 * g + 0.0722 * b; };
  const chroma = (c) => { const m = c.match(/[\d.]+/g); if (!m) return 0; const v = m.slice(0, 3).map(Number); return (Math.max(...v) - Math.min(...v)) / 255; };
  const alpha = (c) => { const m = c.match(/[\d.]+/g); return m && m.length > 3 ? +m[3] : 1; };
  let cols = 1, dark = 0, accent = 0;
  const area = Math.max(1, wr.width * wr.height);
  for (const el of W.querySelectorAll("*")) {
    const r = el.getBoundingClientRect();
    if (!r.width || !r.height) continue;
    const kids = [...el.children].filter((k) => { const b = k.getBoundingClientRect(); return b.width > 40 && b.height > 20; });
    if (kids.length >= 2) {
      const xs = new Set(kids.map((k) => Math.round(k.getBoundingClientRect().left / 8)));
      const tops = new Set(kids.map((k) => Math.round(k.getBoundingClientRect().top / 8)));
      if (tops.size < kids.length) cols = Math.max(cols, xs.size);
    }
    const s = getComputedStyle(el), bg = s.backgroundColor;
    if (alpha(bg) < 0.5 || bg === "transparent") continue;
    const a = Math.min(r.width * r.height, area);
    if (lum(bg) < 0.12) dark += a; else if (chroma(bg) > 0.3) accent += a;
  }
  const ownBg = getComputedStyle(W.firstElementChild || W).backgroundColor;
  if (alpha(ownBg) >= 0.5 && lum(ownBg) < 0.12) dark = Math.max(dark, area);
  return {
    height: Math.round(wr.height), top: Math.round(wr.top + scrollY), cols,
    table: !!W.querySelector("table,[role=table],[role=grid]"),
    controls: W.querySelectorAll("[role=tablist],[role=switch],input[type=radio],input[type=checkbox],select,details,[aria-pressed]").length,
    actions: W.querySelectorAll("a[href],button").length,
    dark: +Math.min(1, dark / area).toFixed(2), accent: +Math.min(1, accent / area).toFixed(2),
    hscroll: document.documentElement.scrollWidth > innerWidth + 1,
  };
};

async function cmdBuild() {
  if (!existsSync(join(OUT, "mock.json"))) die(`нет ${join(args.out, "mock.json")} — сначала mock.mjs new`);
  const M = readJson(join(OUT, "mock.json"));
  const CTX = resolve(OUT, M.context);
  const refFile = M.ref ? resolve(OUT, M.ref) : null;
  const ROOT = commonRoot(OUT, CTX);
  const report = { builtAt: new Date().toISOString(), plan: [], variants: {}, divergence: [] };
  report.plan = existsSync(join(OUT, "PLAN.md")) ? planIssues(readFileSync(join(OUT, "PLAN.md"), "utf8")) : ["нет PLAN.md"];

  const { chromium } = await loadPlaywright();
  const server = await serveDir(ROOT);
  const browser = await chromium.launch();
  const urlOf = (f) => `${server.url}/${posix(relative(ROOT, f))}`;
  mkdirSync(join(OUT, "_compare"), { recursive: true });
  try {
    for (const l of LETTERS) {
      const V = (report.variants[l] = { errors: [], check: null, stats: null, mobile: null });
      const fragFile = join(OUT, `${l}.fragment.html`);
      const frag = existsSync(fragFile) ? readFileSync(fragFile, "utf8") : "";
      const body = frag.replace(/<!--[\s\S]*?-->/g, "").replace(/<style[\s\S]*?<\/style>/gi, "").replace(/<(section|div)[^>]*>\s*<\/\1>/gi, "").trim();
      if (!body) { V.errors.push(`${l}.fragment.html пуст — сверстай вариант`); continue; }
      // страница эталона + фрагмент
      const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
      let html;
      if (refFile && existsSync(refFile)) {
        await page.goto(urlOf(refFile), { waitUntil: "load" });
        const res = await page.evaluate(({ frag, where, position, l }) => {
          const target = where ? document.querySelector(where) : document.querySelector("main") || document.body;
          if (!target) return { error: `нет элемента ${where} на странице — поправь where в mock.json или new --force --where` };
          const w = document.createElement("div");
          w.setAttribute("data-wd-mock", l);
          w.innerHTML = frag;
          const pos = where ? position : position === "prepend" ? "prepend" : "append";
          ({ after: () => target.after(w), before: () => target.before(w), append: () => target.append(w), prepend: () => target.prepend(w) })[pos]();
          return { html: "<!doctype html>\n" + document.documentElement.outerHTML };
        }, { frag, where: M.where, position: M.position, l });
        if (res.error) { V.errors.push(res.error); await page.close(); continue; }
        const base = posix(relative(OUT, dirname(refFile))) + "/";
        html = res.html.replace(/<head([^>]*)>/i, `<head$1>\n<base href="${base}">`);
      } else {
        const tok = posix(relative(OUT, join(CTX, "assets/tokens.css")));
        html = `<!doctype html>\n<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Вариант ${l.toUpperCase()}</title><link rel="stylesheet" href="${tok}"></head>\n<body><div data-wd-mock="${l}">${frag}</div></body></html>`;
      }
      await page.close();
      writeFileSync(join(OUT, `${l}.html`), html);
      // замеры и скриншоты: десктоп и мобильный
      for (const [vp, cfg] of [["desktop", { viewport: { width: 1440, height: 900 } }], ["mobile", { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, deviceScaleFactor: 2 }]]) {
        const ctx = await browser.newContext(cfg);
        const p = await ctx.newPage();
        const jsErr = [];
        p.on("pageerror", (e) => jsErr.push(String(e.message).split("\n")[0]));
        await p.goto(urlOf(join(OUT, `${l}.html`)), { waitUntil: "load" });
        await p.waitForLoadState("networkidle", { timeout: 5000 }).catch(() => {});
        await p.evaluate(() => document.fonts && document.fonts.ready);
        const st = await p.evaluate(`(${STATS})(${JSON.stringify(`[data-wd-mock="${l}"]`)})`);
        if (vp === "desktop") V.stats = st; else V.mobile = st;
        if (st && st.hscroll) V.errors.push(`горизонтальный скролл на ${cfg.viewport.width}px — блок шире экрана (min-width: 0, перенос, медиа-запрос)`);
        for (const e of jsErr) V.errors.push(`ошибка JS (${vp}): ${e.slice(0, 120)}`);
        if (st) {
          const pad = vp === "desktop" ? 160 : 120, maxH = vp === "desktop" ? 2400 : 3600;
          const y = Math.max(0, st.top - pad);
          const h = Math.min(maxH, st.height + pad * 2);
          const full = await p.evaluate(() => document.documentElement.scrollHeight);
          await p.screenshot({ path: join(OUT, "_compare", `${l}-${vp}.jpg`), type: "jpeg", quality: 80, fullPage: true, clip: { x: 0, y, width: cfg.viewport.width, height: Math.max(1, Math.min(h, full - y)) } });
        }
        await ctx.close();
      }
      // проверка соответствия контексту — тот же check.mjs, что и для кода; все темы, если тему можно включить на статике
      if (!args["no-check"]) {
        const kit = existsSync(join(CTX, "reference/kit.json")) ? readJson(join(CTX, "reference/kit.json")) : {};
        const themes = Object.entries(kit.themes || {}).filter(([, t]) => t.how && (t.how.htmlClass || t.how.htmlAttr || t.how.colorScheme)).map(([n]) => n);
        const a = [join(HERE, "check.mjs"), "--context", CTX, "--serve", ROOT, "--path", "/" + posix(relative(ROOT, join(OUT, `${l}.html`))), "--selector", `[data-wd-mock="${l}"]`, "--json", "--theme", themes.length ? themes.join(",") : "none"];
        let outJson;
        try { outJson = execFileSync(process.execPath, a, { encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] }); }
        catch (e) { outJson = e.stdout || ""; if (e.status === 2) V.errors.push(`check.mjs не запустился: ${String(e.stderr || e.message).split("\n")[0]}`); }
        try { const r = JSON.parse(outJson); V.check = { violations: r.violations, warnings: r.warnings, ok: r.ok.length, themes }; } catch {}
      }
    }
  } finally { await browser.close(); server.close(); }

  // ---------- различие ----------
  // Сценарий (структура) должен различаться у каждой пары; палитра — хотя бы у одного варианта (references/mock-patterns.md).
  const L = LETTERS.filter((l) => report.variants[l].stats);
  const S = (l) => report.variants[l].stats;
  const sameStruct = (a, b) => a.cols === b.cols && a.table === b.table && (a.controls > 0) === (b.controls > 0);
  const samePal = (a, b) => Math.abs(a.dark - b.dark) < 0.15 && Math.abs(a.accent - b.accent) < 0.1;
  for (let i = 0; i < L.length; i++) for (let j = i + 1; j < L.length; j++) {
    const a = S(L[i]), b = S(L[j]), same = [];
    if (sameStruct(a, b)) same.push(`одна структура (колонок ${a.cols}${a.table ? ", таблица" : ""}${a.controls ? ", переключатели" : ""})`);
    if (samePal(a, b)) same.push(`одно использование палитры (тёмного ${Math.round(a.dark * 100)}%, акцента ${Math.round(a.accent * 100)}%)`);
    if (Math.abs(a.height - b.height) / Math.max(a.height, b.height) < 0.15 && Math.abs(a.actions - b.actions) <= 1) same.push(`похожий объём (высота ${a.height}/${b.height}px, действий ${a.actions}/${b.actions})`);
    const struct = sameStruct(a, b);
    report.divergence.push({ pair: L[i] + L[j], level: struct && same.length >= 2 ? "error" : struct ? "warn" : "ok", same });
  }
  if (L.length === 3 && samePal(S(L[0]), S(L[1])) && samePal(S(L[1]), S(L[2])) && samePal(S(L[0]), S(L[2])))
    report.divergence.push({ pair: L.join(""), level: "warn", same: ["палитра у всех вариантов используется одинаково — пусть хотя бы один будет на другой подложке или с другим акцентом (из палитры сайта)"] });
  writeFileSync(join(OUT, "mock-report.json"), JSON.stringify(report, null, 2));
  writeFileSync(join(OUT, "index.html"), comparePage(M, report));

  // ---------- отчёт ----------
  let errs = report.plan.length + report.divergence.filter((d) => d.level === "error").length;
  for (const p of report.plan) console.log(`✗ ${p}`);
  for (const l of LETTERS) {
    const V = report.variants[l];
    const c = V.check;
    errs += V.errors.length + (c ? c.violations.length : 0);
    console.log(`\n${l.toUpperCase()}: ${V.errors.length || (c && c.violations.length) ? "НЕ ПРОЙДЕНО" : "пройдено"}${c ? ` — нарушений ${c.violations.length}, предупреждений ${c.warnings.length}${c.themes.length ? ` (темы: основная + ${c.themes.join(", ")})` : ""}` : args["no-check"] ? " (без check)" : ""}`);
    for (const e of V.errors) console.log(`  ✗ ${e}`);
    if (c) { for (const v of c.violations) console.log(`  ✗ ${v.what}\n      → ${v.fix}`); for (const w of c.warnings) console.log(`  ! ${w.what}\n      → ${w.fix}`); }
  }
  if (report.divergence.length) {
    console.log("\nРазличие вариантов:");
    for (const d of report.divergence) console.log(`  ${d.level === "error" ? "✗" : d.level === "warn" ? "!" : "✓"} ${d.pair.toUpperCase()}: ${d.level === "ok" ? "различаются" + (d.same.length ? ` (общее: ${d.same.join("; ")})` : "") : "похожи — " + d.same.join("; ")}`);
  }
  console.log(`\nСравнение: ${posix(relative(process.cwd(), join(OUT, "index.html")))} · Итог: ошибок ${errs} — ${errs ? "НЕ ПРОЙДЕНО" : "пройдено"}`);
  process.exit(errs ? 1 : 0);
}

function comparePage(M, report) {
  const md = existsSync(join(OUT, "PLAN.md")) ? readFileSync(join(OUT, "PLAN.md"), "utf8") : "";
  const sec = (title) => { const m = md.match(new RegExp(`^## ${title}(?=\\s)[^\\n]*\\n([\\s\\S]*?)(?=^## |(?![\\s\\S]))`, "m")); return m ? m[1].trim() : ""; };
  const inline = (t) => esc(t).replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/`([^`]+)`/g, "<code>$1</code>");
  const list = (t) => { const items = t.split("\n").filter((x) => x.trim().startsWith("- ")); return items.length ? `<ul>${items.map((x) => `<li>${inline(x.trim().slice(2))}</li>`).join("")}</ul>` : `<p>${inline(t)}</p>`; };
  const cols = LETTERS.map((l) => {
    const V = report.variants[l], c = V.check;
    const bad = V.errors.length || (c && c.violations.length);
    const status = !V.stats ? `✗ ${esc(V.errors[0] || "не собран")}` : `${bad ? "✗" : "✓"} нарушений ${(c ? c.violations.length : 0) + V.errors.length}, предупреждений ${c ? c.warnings.length : 0}`;
    const issues = [...V.errors.map((e) => "✗ " + e), ...(c ? c.violations.map((v) => "✗ " + v.what) : []), ...(c ? c.warnings.map((w) => "! " + w.what) : [])].slice(0, 6);
    return `<section class="col"><h2>${l.toUpperCase()}</h2><p class="status ${bad ? "bad" : "ok"}">${status}</p>
      ${list(sec(l.toUpperCase()))}
      ${issues.length ? `<details><summary>Проверка</summary><ul class="iss">${issues.map((x) => `<li>${esc(x)}</li>`).join("")}</ul></details>` : ""}
      ${V.stats ? `<div class="pair"><a href="${l}.html"><img loading="lazy" src="_compare/${l}-desktop.jpg" alt="Вариант ${l.toUpperCase()}, десктоп"></a><a href="${l}.html"><img loading="lazy" class="m" src="_compare/${l}-mobile.jpg" alt="Вариант ${l.toUpperCase()}, мобильный"></a></div>` : ""}</section>`;
  }).join("");
  const div = report.divergence.map((d) => `${d.pair.toUpperCase()} — ${d.level === "ok" ? "различаются" : esc(d.same.join("; "))}`).join(" · ");
  return `<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Варианты доработки</title>
<style>
:root{color-scheme:light;--b:#e4e4e7;--t:#18181b;--m:#5b5b63}*{box-sizing:border-box}body{margin:0;font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif;color:var(--t);background:#fafafa}
header{padding:24px 32px;border-bottom:1px solid var(--b);background:#fff}h1{margin:0 0 6px;font-size:22px}header p{margin:0;color:var(--m)}
.grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:24px;padding:24px 32px}.col{background:#fff;border:1px solid var(--b);border-radius:10px;padding:20px;min-width:0}
h2{margin:0 0 6px;font-size:18px}.status{margin:0 0 10px;font-size:13px}.status.bad{color:#b42318}.status.ok{color:#067647}ul{padding-left:18px;margin:8px 0}li{margin:4px 0}
.iss{font-size:13px;color:var(--m)}.pair{display:grid;grid-template-columns:1fr 92px;gap:8px;align-items:start;margin-top:14px}.pair img{width:100%;border:1px solid var(--b);border-radius:6px;display:block}
.div{margin:0;padding:12px 32px 0;color:var(--m)}footer{padding:16px 32px 40px;color:var(--m)}code{background:#f1f1f3;padding:1px 5px;border-radius:4px}
@media (max-width:1100px){.grid{grid-template-columns:1fr}}
</style></head><body><header><h1>Варианты доработки — страница ${esc(M.path)}</h1><p>${inline(sec("Задача")) || "Задача не описана в PLAN.md"}</p></header>
${report.plan.length ? `<p class="div">✗ ${esc(report.plan.join("; "))}</p>` : ""}${div ? `<p class="div">Различие: ${div}</p>` : ""}<main class="grid">${cols}</main>
<footer>${sec("Рекомендация") ? `<p><b>Рекомендация:</b> ${inline(sec("Рекомендация"))}</p>` : ""}Выбери вариант (или скажи, что взять из других) — затем он реализуется в коде проекта и проверяется <code>check.mjs</code>. Скриншот открывает мокап в странице целиком.</footer></body></html>`;
}

(cmd === "new" ? cmdNew() : cmdBuild()).catch((e) => { console.error("error: " + e.message); process.exit(2); });
