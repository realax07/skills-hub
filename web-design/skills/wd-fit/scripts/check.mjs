#!/usr/bin/env node
// Проверка соответствия: новая или изменённая вёрстка против дизайн-контекста (design-context/ из wd-scan).
// Открывает страницу в Chromium, извлекает основы и детали тем же кодом, что снимал контекст, и сравнивает:
// цвета и шрифты вне палитры, размеры шрифта, радиусы и тени не из шкалы, новые варианты кнопок/полей/ссылок/бейджей/карточек
// вместо канона. С --changed ещё смотрит изменённые строки кода: литералы цветов вместо CSS-переменных.
//
//   node scripts/check.mjs --context design-context --url http://localhost:5173/pricing
//   node scripts/check.mjs --context design-context --url http://localhost:5173/ --selector "#pricing"   только новый блок
//   node scripts/check.mjs --context design-context --serve dist --path /pricing.html                   папка сборки (путь — как файл: /about.html)
//   node scripts/check.mjs --context design-context --url … --steps '[{"click":"text=Тарифы"},{"waitFor":"[role=dialog]"}]'
//   node scripts/check.mjs --context design-context --changed                                           только код (git diff)
//
// Флаги: --viewport desktop|mobile (из плана контекста; по умолчанию первый)  --storage-state auth.json
//        --changed [--base HEAD]  --shot <файл.png> (скриншот; клади во временную папку, не в проект)  --json  --strict (предупреждения = ошибки)
//        --theme all|none|<имя> — темы из контекста (foundations.md, «Темы»): по умолчанию all — страница проверяется ещё раз
//        в каждой теме, цвета сравниваются с палитрой этой темы
// Код выхода: 0 — нарушений нет; 1 — есть нарушения (или предупреждения при --strict); 2 — ошибка запуска.
// Как читать отчёт и что исправлять — references/rules.md, «Проверка».
import { readFileSync, existsSync } from "node:fs";
import { join, resolve, dirname, relative } from "node:path";
import { fileURLToPath } from "node:url";
import { execFileSync } from "node:child_process";
import { loadPlaywright, parseArgs, readJson } from "./lib/runtime.mjs";
import { serveDir } from "./lib/serve.mjs";
import { runSteps, themeBefore, themeAfter } from "./lib/steps.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const args = parseArgs(process.argv.slice(2), {
  context: { default: "design-context" }, url: {}, serve: {}, path: { default: "/" }, selector: {}, steps: {},
  viewport: {}, theme: { default: "all" }, "storage-state": {}, changed: { type: "bool" }, base: { default: "HEAD" }, shot: {},
  json: { type: "bool" }, strict: { type: "bool" }, help: { alias: "h", type: "bool" },
});
if (args.help) {
  console.log(readFileSync(fileURLToPath(import.meta.url), "utf8").split("\n").filter((l) => l.startsWith("//")).map((l) => l.slice(3)).join("\n"));
  process.exit(0);
}
const die = (m) => { console.error("error: " + m); process.exit(2); };
if (!args.url && !args.serve && !args.changed) die("нужен --url, --serve или --changed (см. --help)");

// ---------- контекст ----------
const CTX = resolve(args.context);
const REF = join(CTX, "reference");
for (const f of ["kit.json", "manifest.json"]) if (!existsSync(join(REF, f))) die(`нет ${join(REF, f)} — это не дизайн-контекст или он не снят (скилл wd-scan)`);
const K = readJson(join(REF, "kit.json"));
const doc = readJson(join(REF, "manifest.json"));
const planFile = resolve(CTX, doc.plan || "plan.json");
const plan = existsSync(planFile) ? readJson(planFile) : {};
const labels = plan.parts || {};
const stance = plan.stance || null;
const tokens = existsSync(join(REF, "tokens.json")) ? readJson(join(REF, "tokens.json")).cssVariables || {} : {};
const GROUPS = { buttons: "кнопка", inputs: "поле", links: "ссылка", badges: "бейдж", cards: "карточка" };

// ---------- цвета ----------
function rgba(c) {
  if (!c) return null;
  c = String(c).trim().toLowerCase();
  let m = c.match(/^#([0-9a-f]{3,8})$/);
  if (m) {
    let h = m[1];
    if (h.length <= 4) h = [...h].map((x) => x + x).join("");
    const n = (i) => parseInt(h.slice(i, i + 2), 16);
    return [n(0), n(2), n(4), h.length === 8 ? +(n(6) / 255).toFixed(2) : 1];
  }
  m = c.match(/^rgba?\(\s*([\d.]+)[ ,]+([\d.]+)[ ,]+([\d.]+)(?:\s*[,/]\s*([\d.]+%?))?\s*\)$/);
  if (m) { const a = m[4] === undefined ? 1 : m[4].endsWith("%") ? parseFloat(m[4]) / 100 : +m[4]; return [+m[1], +m[2], +m[3], +a.toFixed(2)]; }
  return null;
}
const hex = (c) => { const v = rgba(c); if (!v) return c; const h = v.slice(0, 3).map((x) => Math.round(x).toString(16).padStart(2, "0")).join(""); return v[3] < 1 ? `rgba(${v.slice(0, 3).join(", ")}, ${v[3]})` : "#" + h; };
const dist = (a, b) => { const x = rgba(a), y = rgba(b); if (!x || !y) return 999; return Math.hypot(x[0] - y[0], x[1] - y[1], x[2] - y[2]) + Math.abs(x[3] - y[3]) * 255; };
const palette = [];
for (const [role, list] of Object.entries(K.colors || {})) for (const c of list) palette.push({ ...c, role });
const varsFor = (c) => { const vs = new Set(); for (const p of palette) if (dist(p.color, c) < 1) (p.vars || []).forEach((v) => vs.add(v)); for (const [k, v] of Object.entries(tokens)) if (dist(v, c) < 1) vs.add(k.split(" @ ")[0]); return [...vs]; };
const nearest = (c, role) => {
  const pool = palette.filter((p) => !role || p.role === role);
  return (pool.length ? pool : palette).map((p) => ({ ...p, d: dist(p.color, c) })).sort((a, b) => a.d - b.d)[0];
};
const fmtColor = (c) => { const vs = varsFor(c); return `\`${hex(c)}\`${vs.length ? ` (var(${vs[0]}))` : ""}`; };

// ---------- отчёт ----------
const R = { violations: [], warnings: [], ok: [] };
const V = (what, fix) => R.violations.push({ what, fix });
const W = (what, fix) => R.warnings.push({ what, fix });

function compareFoundations(E) {
  const roles = { text: "текст", background: "фон", border: "граница", icon: "иконка" };
  for (const [role, title] of Object.entries(roles)) {
    for (const c of E.foundations.colors[role] || []) {
      const nb = nearest(c.color, role);
      if (!nb) continue;
      if (nb.d < 1) { R.ok.push(`цвет ${title} ${hex(c.color)}`); continue; }
      // значение CSS-переменной сайта (например фон страницы на <body>) — законный цвет, даже если элементы его не рисуют
      const tv = Object.entries(tokens).find(([k, v]) => !k.includes(" @ ") && dist(v, c.color) < 1);
      if (tv) { R.ok.push(`цвет ${title} ${hex(c.color)} = var(${tv[0]})`); continue; }
      const any = nearest(c.color);
      if (any && any.d < 1) { R.ok.push(`цвет ${title} ${hex(c.color)} (есть на сайте в роли «${roles[any.role]}»)`); continue; }
      const ref = any && any.d < nb.d ? any : nb;
      (ref.d <= 8 ? W : V)(`цвет (${title}) ${hex(c.color)} не из палитры сайта — ${c.n} эл.`, `возьми ${fmtColor(ref.color)}${ref.d <= 8 ? " — почти тот же" : " — ближайший"}`);
    }
  }
  const fams = new Set((K.fonts || []).map((f) => f.family));
  for (const f of E.foundations.fonts || []) if (!fams.has(f.family)) V(`шрифт ${f.family} не используется на сайте — ${f.n} эл.`, `шрифты сайта: ${[...fams].slice(0, 3).join(", ")}; поля и кнопки без \`font: inherit\` получают браузерный шрифт`);
  const typeKeys = new Set((K.type || []).map((t) => `${t.family}|${t.size}|${t.weight}`));
  for (const t of E.foundations.type || []) {
    if (typeKeys.has(`${t.family}|${t.size}|${t.weight}`) || !fams.has(t.family)) continue;
    const sizes = [...new Set((K.type || []).filter((x) => x.family === t.family).map((x) => parseFloat(x.size)))].sort((a, b) => a - b);
    const near = [...sizes].sort((a, b) => Math.abs(a - parseFloat(t.size)) - Math.abs(b - parseFloat(t.size))).slice(0, 2).sort((a, b) => a - b);
    W(`сочетание шрифта ${t.family} ${t.size} / ${t.weight} не встречается на сайте — ${t.n} эл.${t.ex && t.ex[0] ? ` (например \`${t.ex[0].tag}\` «${t.ex[0].text.slice(0, 30)}»)` : ""}`, `размеры этого шрифта на сайте: ${sizes.map((s) => s + "px").join(", ")}; ближайшие — ${near.map((s) => s + "px").join(", ")}`);
  }
  const scale = (list, kind, fixHint) => {
    const known = (K[kind] || []).map((x) => x.v);
    for (const x of E.foundations[kind] || []) {
      if (known.includes(x.v)) continue;
      if (kind === "spacing") continue; // отступы шумные: проверяются через детали
      const num = parseFloat(x.v);
      const near = known.filter((k) => !isNaN(parseFloat(k))).sort((a, b) => Math.abs(parseFloat(a) - num) - Math.abs(parseFloat(b) - num)).slice(0, 2);
      W(`${list} ${x.v} не из шкалы сайта — ${x.n} эл.`, `${fixHint}: ${near.join(", ") || known.slice(0, 4).join(", ")}`);
    }
  };
  scale("радиус", "radius", "радиусы сайта, ближайшие");
  const shadows = new Set((K.shadow || []).map((x) => x.v));
  for (const x of E.foundations.shadow || []) if (!shadows.has(x.v)) W(`тень \`${x.v.slice(0, 60)}\` не встречается на сайте — ${x.n} эл.`, shadows.size ? `тени сайта: ${[...shadows].slice(0, 3).map((s) => "`" + s.slice(0, 60) + "`").join(", ")}` : "на сайте теней нет — убери");
}

// Тема: цвета страницы против палитры этой темы. Главный дефект — цвет основной темы, который в теме не изменился:
// это литерал (или переменная, которую тема не переопределяет) — в одной из тем блок выбьется.
function compareThemeColors(E, name) {
  const T = (K.themes || {})[name] || {};
  const pal = [];
  for (const [role, list] of Object.entries(T.colors || {})) for (const c of list) pal.push({ ...c, role });
  const tvars = Object.entries(T.vars || {});
  const roles = { text: "текст", background: "фон", border: "граница", icon: "иконка" };
  const tag = `[тема ${name}]`;
  for (const [role, title] of Object.entries(roles)) {
    for (const c of E.foundations.colors[role] || []) {
      const hit = pal.map((p) => ({ ...p, d: dist(p.color, c.color) })).sort((a, b) => a.d - b.d)[0];
      if (hit && hit.d < 1) { R.ok.push(`${tag} цвет ${title} ${hex(c.color)}`); continue; }
      const own = tvars.find(([, v]) => dist(v.value, c.color) < 1);
      if (own) { R.ok.push(`${tag} цвет ${title} ${hex(c.color)} = var(${own[0]})`); continue; }
      const stuck = tvars.find(([, v]) => dist(v.light, c.color) < 1);
      if (stuck) { V(`${tag} цвет (${title}) ${hex(c.color)} остался как в основной теме — ${c.n} эл.`, `это значение ${stuck[0]}: в коде литерал вместо var(${stuck[0]}) — тогда в теме ${name} станет \`${stuck[1].value}\``); continue; }
      if (!hit) { W(`${tag} у темы нет палитры в контексте`, "пересними контекст wd-scan с themes в плане"); return; }
      const v = tvars.find(([, x]) => dist(x.value, hit.color) < 1);
      (hit.d <= 8 ? W : V)(`${tag} цвет (${title}) ${hex(c.color)} не из палитры темы — ${c.n} эл.`, `в теме ${name} ${hit.d <= 8 ? "почти тот же" : "ближайший"} \`${hex(hit.color)}\`${v ? ` = var(${v[0]})` : ""}; цвета, разные в темах, — только через переменные`);
    }
  }
}

// подпись детали: фон · текст · граница · радиус · размер · вес · отступы · тень · декор
const FIELDS = ["фон", "цвет текста", "граница", "радиус", "размер шрифта", "вес", "отступы", "тень", "подчёркивание"];
const diffSig = (a, b) => { const x = a.split(" · "), y = b.split(" · "); return FIELDS.map((f, i) => (x[i] !== y[i] ? `${f} ${x[i] || "—"} вместо ${y[i] || "—"}` : null)).filter(Boolean); };
const sigDist = (a, b) => diffSig(a, b).length;
const statusOf = (id) => (labels[id] || {}).status || "unreviewed";
const nameOf = (p) => (labels[p.id] || {}).name || (p.text ? `«${p.text}»` : p.id);

function compareParts(E) {
  for (const [g, list] of Object.entries(E.parts || {})) {
    const known = (K.parts || {})[g] || [];
    for (const p of list) {
      const same = known.find((x) => x.id === p.id);
      const where = p.text ? ` «${p.text}»` : "";
      if (same) {
        const st = statusOf(same.id);
        if (st === "noise") (stance === "preserve" ? W : V)(`${GROUPS[g]}${where} повторяет вариант, помеченный как шум (\`${same.id}\`)`, canonHint(g, p));
        else R.ok.push(`${GROUPS[g]}${where} = ${nameOf(same)} (${st === "canon" ? "канон" : st === "variant" ? "вариант" : "не разобрано"})`);
        continue;
      }
      V(`${GROUPS[g]}${where} — новый вариант, такого на сайте нет (${p.n} эл.)`, canonHint(g, p));
    }
  }
}
function canonHint(g, p) {
  const known = (K.parts || {})[g] || [];
  let pool = known.filter((x) => statusOf(x.id) === "canon");
  if (!pool.length || stance === "preserve") pool = known.filter((x) => statusOf(x.id) !== "noise");
  if (!pool.length) return `в контексте нет вариантов этой группы — проверь, нужна ли тут ${GROUPS[g]}, или сделай по основам (foundations.md) и скажи в отчёте`;
  const best = pool.map((x) => ({ x, d: sigDist(p.sig, x.sig) })).sort((a, b) => a.d - b.d || b.x.n - a.x.n)[0].x;
  const diff = diffSig(p.sig, best.sig);
  return `ближайший ${statusOf(best.id) === "canon" ? "канон" : "вариант"}: ${nameOf(best)} \`${best.id}\` (parts/${g}.md) — отличие: ${diff.slice(0, 4).join("; ") || "только размеры"}`;
}

// ---------- изменённый код ----------
function checkChanged() {
  let root;
  try { root = execFileSync("git", ["rev-parse", "--show-toplevel"], { encoding: "utf8" }).trim(); } catch { W("--changed: не git-репозиторий", "проверь код вручную или запусти из репозитория"); return; }
  const ctxRel = relative(root, CTX).split("\\").join("/");
  const STY = /\.(css|scss|sass|less|styl|pcss|js|jsx|ts|tsx|mjs|vue|svelte|astro|html|htm|php|twig|liquid|hbs|erb)$/i;
  const added = [];
  let diff = "";
  try { diff = execFileSync("git", ["diff", "--unified=0", "--no-color", args.base, "--"], { cwd: root, encoding: "utf8", maxBuffer: 64 << 20 }); } catch (e) { W(`--changed: git diff ${args.base} не удался`, String(e.message).split("\n")[0]); }
  let file = null, line = 0;
  for (const l of diff.split("\n")) {
    if (l.startsWith("+++ ")) { file = l.slice(4).replace(/^b\//, ""); continue; }
    const h = l.match(/^@@ -\d+(?:,\d+)? \+(\d+)/);
    if (h) { line = +h[1]; continue; }
    if (file && l.startsWith("+") && !l.startsWith("+++")) { added.push({ file, line, text: l.slice(1) }); line++; }
  }
  try {
    const untracked = execFileSync("git", ["ls-files", "--others", "--exclude-standard"], { cwd: root, encoding: "utf8" }).split("\n").filter(Boolean);
    for (const f of untracked) { if (!STY.test(f)) continue; try { readFileSync(join(root, f), "utf8").split("\n").forEach((t, i) => added.push({ file: f, line: i + 1, text: t })); } catch {} }
  } catch {}
  const vals = Object.entries(tokens).map(([k, v]) => [k.split(" @ ")[0], v]);
  let n = 0;
  for (const a of added) {
    if (!STY.test(a.file) || (ctxRel && a.file.startsWith(ctxRel + "/")) || /\/(node_modules|dist|build)\//.test("/" + a.file)) continue;
    if (/^\s*--[\w-]+\s*:/.test(a.text)) continue; // объявление переменной — не литерал
    if (/shadow/i.test(a.text)) continue; // цвет тени — часть тени, тени проверяются на странице
    for (const m of a.text.matchAll(/#[0-9a-fA-F]{3,8}\b|rgba?\([^)]*\)/g)) {
      if (/^#\d+$/.test(m[0]) && m[0].length < 4) continue;
      const c = m[0];
      if (!rgba(c)) continue;
      n++;
      const at = `${a.file}:${a.line}`;
      const v = vals.find(([, val]) => dist(val, c) < 1);
      if (v) { V(`литерал ${c} в ${at}`, `замени на var(${v[0]})`); continue; }
      const nb = nearest(c);
      if (!nb || nb.d >= 1) V(`цвет ${c} в ${at} не из палитры сайта`, nb ? `ближайший ${fmtColor(nb.color)}` : "палитра пуста");
      else if (varsFor(c).length) V(`литерал ${c} в ${at}`, `замени на var(${varsFor(c)[0]})`);
    }
  }
  R.ok.push(`код: просмотрено добавленных строк ${added.length}, цветов-литералов ${n}`);
}

// ---------- браузер ----------
async function checkPage(browser, server, theme) {
  const vps = doc.viewports || plan.viewports || { desktop: { width: 1440, height: 900 } };
  const vpName = args.viewport || doc.primaryViewport || Object.keys(vps)[0];
  const vp = vps[vpName];
  if (!vp) die(`нет вьюпорта ${vpName}; есть: ${Object.keys(vps).join(", ")}`);
  const url = server ? server.url + args.path : args.url;
  const how = theme ? ((K.themes || {})[theme] || {}).how || (plan.themes || {})[theme] || {} : null;
  const context = await browser.newContext({ viewport: { width: vp.width, height: vp.height }, deviceScaleFactor: vp.deviceScaleFactor || 1, isMobile: !!vp.isMobile, hasTouch: !!vp.isMobile,
    storageState: args["storage-state"] ? resolve(args["storage-state"]) : undefined, locale: plan.locale, colorScheme: (how && how.colorScheme) || vp.colorScheme || plan.colorScheme });
  try {
    const page = await context.newPage();
    const jsErrors = [], consoleErrors = [];
    page.on("pageerror", (e) => jsErrors.push(String(e.message).split("\n")[0]));
    page.on("console", (m) => {
      if (m.type() !== "error") return;
      const at = (m.location() || {}).url || "";
      if (/favicon\.ico/.test(at)) return; // браузер просит favicon сам — не ошибка страницы
      consoleErrors.push(/^Failed to load resource/.test(m.text()) ? `не загрузился ресурс ${at || "(адрес неизвестен)"}` : m.text().split("\n")[0]);
    });
    if (how) await themeBefore(page, how);
    await page.goto(url, { waitUntil: "load", timeout: 45000 });
    await page.waitForLoadState("networkidle", { timeout: 8000 }).catch(() => {});
    await page.evaluate(() => document.fonts && document.fonts.ready);
    if (how) await themeAfter(page, how, url, 8000);
    if (args.steps) { let st; try { st = JSON.parse(args.steps); } catch { die("--steps: нужен JSON-массив шагов"); } await runSteps(page, st, url, 8000); }
    await page.waitForTimeout(300);
    const E = await page.evaluate(`(${readFileSync(join(HERE, "lib/page-extract.js"), "utf8")})(${JSON.stringify({ root: args.selector, iconMax: 64 })})`);
    if (E.error) die(E.error + (args.selector ? " — проверь --selector (CSS)" : ""));
    if (args.shot) {
      const target = args.selector ? page.locator(args.selector).first() : page;
      const shot = theme ? resolve(args.shot).replace(/(\.\w+)?$/, (m) => `-${theme}${m || ".png"}`) : resolve(args.shot);
      await target.screenshot({ path: shot, ...(args.selector ? {} : { fullPage: true }) });
    }
    if (theme) { compareThemeColors(E, theme); (R.themes ||= []).push(theme); return; }
    R.page = { url, viewport: vpName, selector: args.selector || null, elements: E.elements };
    compareFoundations(E);
    compareParts(E);
    // ошибки JS на странице: часто скрипт проекта ищет элемент, которого на новой странице нет
    for (const e of [...new Set(consoleErrors)].slice(0, 5)) W(`консоль: ${e.slice(0, 160)}`, "ресурс или скрипт с ошибкой — проверь путь; если это не из твоей правки, упомяни в отчёте");
    for (const e of [...new Set(jsErrors)].slice(0, 5)) V(`ошибка JS на странице: ${e.slice(0, 160)}`, "скрипт проекта упал — проверь, что новая разметка не сломала его (нет ожидаемого элемента, другой id); интерактив может не работать");
  } finally {
    await context.close();
  }
}

async function main() {
  if (args.url || args.serve) {
    const all = Object.keys(K.themes || {});
    const themes = args.theme === "none" ? [] : args.theme === "all" ? all : args.theme.split(",");
    for (const t of themes) if (!all.includes(t)) die(`темы ${t} нет в контексте; есть: ${all.join(", ") || "нет тем"}`);
    const { chromium } = await loadPlaywright();
    const server = args.serve ? await serveDir(resolve(args.serve)) : null;
    const browser = await chromium.launch();
    try {
      await checkPage(browser, server, null);
      for (const t of themes) await checkPage(browser, server, t);
    } finally {
      await browser.close();
      if (server) server.close();
    }
  }
  if (args.changed) checkChanged();
  const fail = R.violations.length || (args.strict && R.warnings.length);
  if (args.json) { console.log(JSON.stringify({ stance, ...R, pass: !fail }, null, 2)); process.exit(fail ? 1 : 0); }
  const st = stance === "preserve" ? "повторять как есть" : stance === "normalize" ? "приводить к канону" : "не задана (сравнение со всем, что есть на сайте)";
  console.log(`Проверка по ${relative(process.cwd(), CTX) || "."} · позиция: ${st}`);
  if (R.page) console.log(`Страница: ${R.page.url} [${R.page.viewport}]${R.page.selector ? ` внутри ${R.page.selector}` : ""} — элементов ${R.page.elements}`);
  if (R.themes) console.log(`Темы: основная + ${R.themes.join(", ")} (цвета каждой темы — против её палитры)`);
  if (R.page && R.page.elements === 0) console.log("! видимых элементов нет — проверь --selector и что страница открылась");
  console.log("");
  for (const v of R.violations) console.log(`✗ ${v.what}\n    → ${v.fix}`);
  for (const w of R.warnings) console.log(`! ${w.what}\n    → ${w.fix}`);
  console.log(`\n✓ совпало с контекстом: ${R.ok.length}${R.ok.length ? " — " + R.ok.slice(0, 8).join("; ") + (R.ok.length > 8 ? "; …" : "") : ""}`);
  console.log(`Итог: нарушений ${R.violations.length}, предупреждений ${R.warnings.length} — ${fail ? "НЕ ПРОЙДЕНО" : "пройдено"}`);
  process.exit(fail ? 1 : 0);
}
main().catch((e) => { console.error("error: " + e.message); process.exit(2); });
