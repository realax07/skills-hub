#!/usr/bin/env node
// Проверка мокапов направлений в браузере: пол качества, «тела» шаблонного ИИ-дизайна, верность токенам направления
// и мера различия между направлениями (не три оттенка одного).
//
//   node scripts/lint.mjs --dir design-forge                 все направления и экраны
//   node scripts/lint.mjs --dir design-forge --only b        одно направление
//   node scripts/lint.mjs --dir design-forge --json
//
// Экраны и шрифты берутся из directions.json (его пишет deal.mjs). Вьюпорты: 1440×900, 768×1024, 390×844 (мобильный);
// у направления с двумя темами каждый экран ещё раз на 1440 во второй теме (<html data-theme="…">).
// kit.html (UI-кит) — обязательные детали data-part из assets/catalog/system.json → kit.
// Пишет <dir>/lint-report.json. Код выхода: 0 — ошибок нет (предупреждения допустимы), 1 — есть ошибки, 2 — ошибка запуска.
// Что значит каждое правило и как исправить — references/rules.md, «Проверка».
import { readFileSync, existsSync, writeFileSync } from "node:fs";
import { join, resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { loadPlaywright, parseArgs } from "./lib/runtime.mjs";
import { serveDir } from "./lib/serve.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const args = parseArgs(process.argv.slice(2), { dir: { default: "design-forge" }, only: {}, json: { type: "bool" }, help: { alias: "h", type: "bool" } });
if (args.help) {
  console.log(readFileSync(fileURLToPath(import.meta.url), "utf8").split("\n").filter((l) => l.startsWith("//")).map((l) => l.slice(3)).join("\n"));
  process.exit(0);
}
const die = (m) => { console.error("error: " + m); process.exit(2); };
const DIR = resolve(args.dir);
if (!existsSync(join(DIR, "directions.json"))) die(`нет ${join(DIR, "directions.json")} — сначала deal.mjs`);
const D = JSON.parse(readFileSync(join(DIR, "directions.json"), "utf8"));
const only = args.only ? new Set(args.only.split(",")) : null;
const VPS = { desktop: { width: 1440, height: 900 }, tablet: { width: 768, height: 1024 }, mobile: { width: 390, height: 844, isMobile: true, deviceScaleFactor: 2 } };
const LINT = readFileSync(join(HERE, "lib/page-lint.js"), "utf8");
const SYS = JSON.parse(readFileSync(join(HERE, "..", "assets", "catalog", "system.json"), "utf8"));
const KIT_NEED = [...(SYS.kit ? SYS.kit.required : []), ...(SYS.kit && D.mode === "operate" ? SYS.kit.operate : [])];
const EXTRACT = readFileSync(join(HERE, "lib/page-extract.js"), "utf8");

const hex = (c) => { const m = String(c).match(/^#([0-9a-f]{6})$/i); return m ? "#" + m[1].toLowerCase() : null; };
const rgbOf = (c) => { if (c.startsWith("#")) { const h = c.slice(1); return [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16)); } const m = c.match(/[\d.]+/g); return m ? m.slice(0, 3).map(Number) : null; };
const dist = (a, b) => { const x = rgbOf(a), y = rgbOf(b); return x && y ? Math.hypot(x[0] - y[0], x[1] - y[1], x[2] - y[2]) : 999; };
const hue = (c) => { const [r, g, b] = rgbOf(c).map((v) => v / 255), mx = Math.max(r, g, b), mn = Math.min(r, g, b), d = mx - mn; if (d < 0.15) return null; const h = mx === r ? ((g - b) / d) % 6 : mx === g ? (b - r) / d + 2 : (r - g) / d + 4; return (h * 60 + 360) % 360; };

function tokenColors(letter) {
  const f = join(DIR, letter, "tokens.css");
  if (!existsSync(f)) return [];
  return [...readFileSync(f, "utf8").matchAll(/--color-[\w-]+:\s*(#[0-9a-f]{6})/gi)].map((m) => m[1].toLowerCase());
}

async function main() {
  const { chromium } = await loadPlaywright();
  const server = await serveDir(DIR);
  const browser = await chromium.launch();
  const report = { checkedAt: new Date().toISOString(), variants: {}, divergence: [] };
  try {
    for (const d of D.directions) {
      if (only && !only.has(d.letter)) continue;
      const V = (report.variants[d.letter] = { name: d.archetypeName, errors: 0, warnings: 0, screens: {}, plan: [], stats: null });
      const plan = join(DIR, d.letter, "PLAN.md");
      if (!existsSync(plan)) V.plan.push("нет PLAN.md");
      else {
        const md = readFileSync(plan, "utf8");
        const left = (md.match(/‹заполни›/g) || []).length;
        if (left) V.plan.push(`в PLAN.md не заполнено ${left} мест «‹заполни›»`);
        // минимальная содержательность: самопроверка и каркасы не должны быть отпиской
        const sec = (t) => { const m = md.match(new RegExp(`^## ${t}[^\\n]*\\n([\\s\\S]*?)(?=^## |(?![\\s\\S]))`, "m")); return m ? m[1].trim() : ""; };
        if (!left && sec("Что тут дефолтное").replace(/\s+/g, " ").length < 80) V.plan.push("PLAN.md: раздел «Что тут дефолтное — и что изменено» слишком короткий — перечисли, что взялось по умолчанию и на что заменено");
        const frames = [...md.matchAll(/```\n([\s\S]*?)```/g)].map((m) => m[1].trim().split("\n").length);
        // раздел кита — подзаголовок «### kit.html» внутри «Каркас экранов» (deal.mjs) или «## kit.html», если его подняли
        const kitSec = (() => { const m = md.match(/^(#{2,3}) kit\.html[^\n]*\n([\s\S]*?)(?=^#{2,3} |(?![\s\S]))/m); return m ? m[2].replace(/Заготовка уже лежит[^\n]*\n?/, "").trim() : ""; })();
        if (!left && kitSec.replace(/\s+/g, " ").length < 120) V.plan.push("PLAN.md: раздел «kit.html — UI-кит» слишком короткий — опиши, что в заготовке кита изменено под направление (кнопки, поля, метки, таблица)");
        if (!left && frames.some((n) => n < 4)) V.plan.push("PLAN.md: ASCII-каркас экрана короче 4 строк — опиши зоны экрана сверху вниз");
      }
      V.errors += V.plan.length;
      const tokens = tokenColors(d.letter);
      // кит — первым: его детали — эталон для экранов (off-kit)
      const kitSigs = {};
      for (const s of [...d.screens].sort((x, y) => (y.kit ? 1 : 0) - (x.kit ? 1 : 0))) {
        const file = join(DIR, d.letter, s.file);
        const S = (V.screens[s.file] = { issues: [] });
        if (!existsSync(file)) { S.issues.push({ level: "error", rule: "missing", what: `нет экрана ${d.letter}/${s.file} (${s.what})` }); V.errors++; continue; }
        const html = readFileSync(file, "utf8");
        for (const css of ["tokens.css", "base.css"]) if (!new RegExp(`href=["'][^"']*${css.replace(".", "\\.")}`).test(html)) S.issues.push({ level: "error", rule: "no-" + css.replace(".css", ""), what: `экран не подключает ${css}` });
        // проходы: три ширины в основной теме + десктоп во второй теме
        const passes = Object.entries(VPS).map(([n, vp]) => [n, vp, null]);
        for (const t of (d.themes || []).slice(1)) passes.push([`desktop ${t}`, VPS.desktop, t]);
        for (const [vpName, vp, theme] of passes) {
          const ctx = await browser.newContext({ viewport: { width: vp.width, height: vp.height }, isMobile: !!vp.isMobile, hasTouch: !!vp.isMobile, deviceScaleFactor: vp.deviceScaleFactor || 1 });
          const page = await ctx.newPage();
          const jsErr = [];
          page.on("pageerror", (e) => jsErr.push(String(e.message).split("\n")[0]));
          await page.goto(`${server.url}/${d.letter}/${s.file}`, { waitUntil: "load", timeout: 45000 });
          await page.waitForLoadState("networkidle", { timeout: 6000 }).catch(() => {});
          await page.evaluate(() => document.fonts && document.fonts.ready);
          if (theme) { await page.evaluate((t) => document.documentElement.setAttribute("data-theme", t), theme); await page.waitForTimeout(100); }
          if (s.kit && !theme && vpName === "desktop") {
            const have = await page.evaluate(() => [...document.querySelectorAll("[data-part]")].filter((e) => { const r = e.getBoundingClientRect(); return r.width && r.height; }).map((e) => e.getAttribute("data-part")));
            const miss = KIT_NEED.filter((n) => !have.includes(n));
            if (miss.length) S.issues.push({ level: "error", rule: "kit-missing", what: "в UI-ките нет обязательных деталей (data-part) — без них у дизайн-контекста не будет канона", n: miss.length, ex: miss, viewport: vpName });
          }
          const r = await page.evaluate(`(${LINT})(${JSON.stringify({ mobile: !!vp.isMobile, fonts: [...new Set([d.display, d.body])] })})`);
          for (const i of r.issues) S.issues.push({ ...i, viewport: vpName });
          for (const e of jsErr) S.issues.push({ level: "error", rule: "js-error", what: `ошибка JS: ${e.slice(0, 140)}`, viewport: vpName });
          if (vpName === "desktop") {
            if (s.file === d.screens[0].file) V.stats = r.stats;
            // цвета страницы против токенов направления
            const E = await page.evaluate(`(${EXTRACT})({})`);
            // детали экранов — из кита: иначе в каноне окажется по два варианта каждой кнопки
            const G = { buttons: "кнопка", inputs: "поле", badges: "метка" };
            if (s.kit) for (const g of Object.keys(G)) kitSigs[g] = new Set((E.parts[g] || []).map((p) => p.sig));
            else if (Object.keys(kitSigs).length) {
              const off = [];
              for (const [g, w] of Object.entries(G)) for (const p of E.parts[g] || []) if (!kitSigs[g].has(p.sig)) off.push(`${w} «${p.text || p.id}»`);
              if (off.length) S.issues.push({ level: "error", rule: "off-kit", what: "детали не из UI-кита — сделай их классами kit.html (или добавь вариант в кит с data-part)", n: off.length, ex: off.slice(0, 5), viewport: vpName });
            }
            const off = [];
            for (const role of ["text", "background", "border"]) for (const c of E.foundations.colors[role] || []) {
              const h = hex(c.color);
              if (!h || !tokens.length) continue; // полупрозрачные и производные (color-mix) не считаем
              if (!tokens.some((t) => dist(t, h) < 3)) off.push(`${role} ${h} (${c.n} эл.)`);
            }
            if (off.length) S.issues.push({ level: "warn", rule: "off-tokens", what: "цвета вне токенов направления — добавь в tokens.css осознанно или замени на var(--color-…)", n: off.length, ex: off.slice(0, 4), viewport: vpName });
          }
          await ctx.close();
        }
        // одинаковые нарушения на разных вьюпортах — одной строкой
        const merged = new Map();
        for (const i of S.issues) { const k = i.rule + "|" + i.what; if (merged.has(k)) merged.get(k).viewports.push(i.viewport); else merged.set(k, { ...i, viewports: i.viewport ? [i.viewport] : [] }); }
        S.issues = [...merged.values()];
        V.errors += S.issues.filter((i) => i.level === "error").length;
        V.warnings += S.issues.filter((i) => i.level === "warn").length;
      }
    }
    // ---- мера различия
    const L = Object.keys(report.variants).filter((l) => report.variants[l].stats);
    for (let i = 0; i < L.length; i++) for (let j = i + 1; j < L.length; j++) {
      const a = report.variants[L[i]], b = report.variants[L[j]], da = D.directions.find((x) => x.letter === L[i]), db = D.directions.find((x) => x.letter === L[j]);
      const same = [], pair = L[i] + L[j];
      if (a.stats.headFont === b.stats.headFont) same.push(`один шрифт заголовков (${a.stats.headFont})`);
      const darkA = a.stats.bgLum < 0.3, darkB = b.stats.bgLum < 0.3;
      const ha = hue(da.accent), hb = hue(db.accent);
      const close = ha !== null && hb !== null ? Math.min(Math.abs(ha - hb), 360 - Math.abs(ha - hb)) < 35 : ha === hb;
      if (darkA === darkB && close && !D.brand) same.push("одна схема и близкий акцент");
      if (a.stats.layout === b.stats.layout && Math.abs(a.stats.sections - b.stats.sections) <= 1 && a.stats.radius === b.stats.radius) same.push(`одинаковая раскладка (${a.stats.layout}, секций ${a.stats.sections}) и радиус ${a.stats.radius}`);
      const level = same.length >= 2 ? "error" : same.length ? "warn" : "ok";
      report.divergence.push({ pair, level, same });
    }
  } finally {
    await browser.close();
    server.close();
  }
  writeFileSync(join(DIR, "lint-report.json"), JSON.stringify(report, null, 2));
  const errs = Object.values(report.variants).reduce((a, v) => a + v.errors, 0) + report.divergence.filter((x) => x.level === "error").length;
  if (args.json) { console.log(JSON.stringify(report, null, 2)); process.exit(errs ? 1 : 0); }
  for (const [l, v] of Object.entries(report.variants)) {
    console.log(`\n${l.toUpperCase()} — ${v.name}: ошибок ${v.errors}, предупреждений ${v.warnings}`);
    for (const p of v.plan) console.log(`  ✗ ${p}`);
    for (const [f, s] of Object.entries(v.screens)) for (const i of s.issues)
      console.log(`  ${i.level === "error" ? "✗" : "!"} ${f}${i.viewports && i.viewports.length ? ` [${i.viewports.join(",")}]` : ""}: ${i.what}${i.n > 1 ? ` — ${i.n}` : ""}${i.ex && i.ex.length ? `\n      ${i.ex.join("; ")}` : ""}`);
  }
  if (report.divergence.length) {
    console.log("\nРазличие направлений:");
    for (const x of report.divergence) console.log(`  ${x.level === "error" ? "✗" : x.level === "warn" ? "!" : "✓"} ${x.pair}: ${x.same.length ? "похожи — " + x.same.join("; ") : "различаются"}`);
  }
  console.log(`\nИтог: ошибок ${errs} — ${errs ? "НЕ ПРОЙДЕНО" : "пройдено"} → ${join(args.dir, "lint-report.json")}`);
  process.exit(errs ? 1 : 0);
}
main().catch((e) => { console.error("error: " + e.message); process.exit(2); });
