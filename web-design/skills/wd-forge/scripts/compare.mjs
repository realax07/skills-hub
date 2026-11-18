#!/usr/bin/env node
// Страница сравнения трёх направлений для утверждения: скриншоты экранов (десктоп и мобильный), оси и токены,
// идея, плюсы и минусы из PLAN.md, итог lint.mjs. Открывается без сервера: <dir>/index.html.
//
//   node scripts/compare.mjs --dir design-forge
//   node scripts/compare.mjs --dir design-forge --no-shots      без пересъёмки скриншотов
//
// Сначала lint.mjs (его итог попадает на страницу). Скриншоты — <dir>/_compare/*.jpg.
// Код выхода: 0 — готово, 2 — ошибка запуска.
import { readFileSync, existsSync, writeFileSync, mkdirSync } from "node:fs";
import { join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { loadPlaywright, parseArgs } from "./lib/runtime.mjs";
import { serveDir } from "./lib/serve.mjs";

const args = parseArgs(process.argv.slice(2), { dir: { default: "design-forge" }, "no-shots": { type: "bool" }, help: { alias: "h", type: "bool" } });
if (args.help) {
  console.log(readFileSync(fileURLToPath(import.meta.url), "utf8").split("\n").filter((l) => l.startsWith("//")).map((l) => l.slice(3)).join("\n"));
  process.exit(0);
}
const DIR = resolve(args.dir);
if (!existsSync(join(DIR, "directions.json"))) { console.error(`error: нет ${join(DIR, "directions.json")} — сначала deal.mjs`); process.exit(2); }
const D = JSON.parse(readFileSync(join(DIR, "directions.json"), "utf8"));
const lint = existsSync(join(DIR, "lint-report.json")) ? JSON.parse(readFileSync(join(DIR, "lint-report.json"), "utf8")) : null;
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
const section = (md, title) => { const m = md.match(new RegExp(`^## ${title}[^\\n]*\\n([\\s\\S]*?)(?=^## |$(?![\\s\\S]))`, "m")); return m ? m[1].trim() : ""; };
const mdToHtml = (t) => esc(t).replace(/^- (.*)$/gm, "<li>$1</li>").replace(/(<li>[\s\S]*<\/li>)/, "<ul>$1</ul>").replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/\n{2,}/g, "<br><br>");

async function shots() {
  const { chromium } = await loadPlaywright();
  const server = await serveDir(DIR);
  const browser = await chromium.launch();
  mkdirSync(join(DIR, "_compare"), { recursive: true });
  try {
    for (const d of D.directions) for (const s of d.screens) {
      if (!existsSync(join(DIR, d.letter, s.file))) continue;
      for (const [vp, cfg] of [["desktop", { viewport: { width: 1440, height: 900 } }], ["mobile", { viewport: { width: 390, height: 844 }, isMobile: true, deviceScaleFactor: 2 }]]) {
        const ctx = await browser.newContext(cfg);
        const page = await ctx.newPage();
        await page.goto(`${server.url}/${d.letter}/${s.file}`, { waitUntil: "load", timeout: 45000 });
        await page.waitForLoadState("networkidle", { timeout: 6000 }).catch(() => {});
        await page.evaluate(() => document.fonts && document.fonts.ready);
        await page.waitForTimeout(400);
        const h = await page.evaluate(() => document.documentElement.scrollHeight);
        await page.screenshot({ path: join(DIR, "_compare", `${d.letter}-${s.file.replace(/\.html?$/, "")}-${vp}.jpg`), type: "jpeg", quality: 78, fullPage: h <= (vp === "desktop" ? 3600 : 5200), clip: h > (vp === "desktop" ? 3600 : 5200) ? { x: 0, y: 0, width: cfg.viewport.width, height: vp === "desktop" ? 3600 : 5200 } : undefined });
        await ctx.close();
      }
    }
  } finally { await browser.close(); server.close(); }
}

function page() {
  const cols = D.directions.map((d) => {
    const plan = existsSync(join(DIR, d.letter, "PLAN.md")) ? readFileSync(join(DIR, d.letter, "PLAN.md"), "utf8") : "";
    const tokens = existsSync(join(DIR, d.letter, "tokens.css")) ? [...readFileSync(join(DIR, d.letter, "tokens.css"), "utf8").matchAll(/--color-([\w-]+):\s*(#[0-9a-f]{6})/gi)] : [];
    const v = lint && lint.variants[d.letter];
    const status = !v ? "проверка не запускалась" : v.errors ? `✗ ошибок ${v.errors}, предупреждений ${v.warnings}` : `✓ ошибок нет, предупреждений ${v.warnings}`;
    const screens = d.screens.map((s) => {
      const base = s.file.replace(/\.html?$/, "");
      return `<figure><figcaption><a href="${d.letter}/${esc(s.file)}">${esc(s.file)}</a> — ${esc(s.what)}</figcaption>
        <div class="pair"><a href="${d.letter}/${esc(s.file)}"><img loading="lazy" src="_compare/${d.letter}-${base}-desktop.jpg" alt="${esc(s.what)}, десктоп"></a>
        <a href="${d.letter}/${esc(s.file)}"><img loading="lazy" class="m" src="_compare/${d.letter}-${base}-mobile.jpg" alt="${esc(s.what)}, мобильный"></a></div></figure>`;
    }).join("");
    return `<section class="col"><h2>${d.letter.toUpperCase()} · ${esc(d.archetypeName)}</h2>
      <p class="status ${v && v.errors ? "bad" : "ok"}">${status}</p>
      <div class="sw">${tokens.map(([, k, c]) => `<span title="${esc(k)} ${c}" style="background:${c}"></span>`).join("")}</div>
      <table><tr><th>Палитра</th><td>${esc(d.paletteName)} (${d.scheme === "dark" ? "тёмная" : "светлая"})</td></tr><tr><th>Шрифты</th><td>${esc(d.display)} / ${esc(d.body)}</td></tr>
      <tr><th>Форма</th><td>${esc(d.shape)}</td></tr><tr><th>Плотность</th><td>${esc(d.density)}</td></tr><tr><th>Движение</th><td>${esc(d.motion)}</td></tr></table>
      <h3>Идея</h3><div>${mdToHtml(section(plan, "Идея"))}</div>
      <h3>Плюсы</h3><div>${mdToHtml(section(plan, "Плюсы"))}</div><h3>Минусы</h3><div>${mdToHtml(section(plan, "Минусы"))}</div>
      ${screens}</section>`;
  }).join("");
  const div = lint && lint.divergence.length ? `<p class="div">Различие: ${lint.divergence.map((x) => `${x.pair.toUpperCase()} — ${x.level === "ok" ? "различаются" : esc(x.same.join("; "))}`).join(" · ")}</p>` : "";
  return `<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Направления — ${esc(D.product)}</title>
<style>
:root{color-scheme:light;--b:#e4e4e7;--t:#18181b;--m:#5b5b63}*{box-sizing:border-box}body{margin:0;font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif;color:var(--t);background:#fafafa}
header{padding:24px 32px;border-bottom:1px solid var(--b);background:#fff}h1{margin:0 0 4px;font-size:22px}header p{margin:0;color:var(--m)}
.grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:24px;padding:24px 32px}.col{background:#fff;border:1px solid var(--b);border-radius:10px;padding:20px;min-width:0}
h2{margin:0 0 6px;font-size:18px}h3{margin:16px 0 4px;font-size:14px}.status{margin:0 0 10px;font-size:13px}.status.bad{color:#b42318}.status.ok{color:#067647}
.sw{display:flex;gap:4px;margin:8px 0}.sw span{width:28px;height:28px;border-radius:6px;border:1px solid var(--b)}table{border-collapse:collapse;font-size:13px;width:100%}th{text-align:left;color:var(--m);font-weight:500;padding:2px 8px 2px 0;width:90px}td{padding:2px 0}
figure{margin:18px 0 0}figcaption{font-size:13px;color:var(--m);margin-bottom:6px}.pair{display:grid;grid-template-columns:1fr 92px;gap:8px;align-items:start}.pair img{width:100%;border:1px solid var(--b);border-radius:6px;display:block}
.div{margin:0;padding:0 32px;color:var(--m)}footer{padding:16px 32px 40px;color:var(--m)}code{background:#f1f1f3;padding:1px 5px;border-radius:4px}
@media (max-width:1100px){.grid{grid-template-columns:1fr}}
</style></head><body><header><h1>${esc(D.product)}: три направления</h1><p>Режим: ${esc(D.mode)}${D.brand ? ` · бренд-цвет ${esc(D.brand)}` : ""}. Клик по скриншоту открывает мокап.</p></header>
${div}<main class="grid">${cols}</main>
<footer>Выбери одно направление (или скажи, что взять из других). Утвердить: <code>node &lt;wd-forge&gt;/scripts/approve.mjs --dir ${esc(args.dir)} --pick &lt;a|b|c&gt;</code></footer></body></html>`;
}

async function main() {
  if (!args["no-shots"]) await shots();
  writeFileSync(join(DIR, "index.html"), page());
  console.log(`Сравнение: ${join(args.dir, "index.html")}${lint ? "" : " (lint.mjs ещё не запускался — итога проверки на странице нет)"}`);
}
main().catch((e) => { console.error("error: " + e.message); process.exit(2); });
