#!/usr/bin/env node
// Рабочая выжимка дизайн-контекста под задачу — одним текстом вместо чтения десятка файлов.
// Позиция проекта, токены (цвета с переменными, шрифты, шкалы), канон деталей с разметкой и исходником,
// какая схема раздела ближе к месту изменения, компоненты и модалки из плана, где это в коде, свежесть контекста.
//
//   node scripts/brief.mjs --context design-context
//   node scripts/brief.mjs --context design-context --path /pricing --groups buttons,cards
//   node scripts/brief.mjs --context design-context --path /blog/new-post --max 2 --json
//
// Флаги: --path — URL-путь, который меняешь или создаёшь (подберёт схему раздела);
//        --groups — какие детали показать (buttons, inputs, links, badges, cards; по умолчанию все);
//        --max N — сколько вариантов на группу (по умолчанию 3); --json — машинный вывод.
// Код выхода 2 — контекст не найден.
import { readFileSync, existsSync, readdirSync } from "node:fs";
import { join, resolve, relative } from "node:path";
import { fileURLToPath } from "node:url";
import { execFileSync } from "node:child_process";
import { parseArgs, readJson } from "./lib/runtime.mjs";

const args = parseArgs(process.argv.slice(2), {
  context: { default: "design-context" }, path: {}, groups: {}, max: { type: "int", default: 3 }, json: { type: "bool" }, help: { alias: "h", type: "bool" },
});
if (args.help) {
  console.log(readFileSync(fileURLToPath(import.meta.url), "utf8").split("\n").filter((l) => l.startsWith("//")).map((l) => l.slice(3)).join("\n"));
  process.exit(0);
}
const CTX = resolve(args.context);
const REF = join(CTX, "reference");
if (!existsSync(join(REF, "kit.json")) || !existsSync(join(CTX, "GUIDE.md"))) {
  console.error(`error: в ${CTX} нет дизайн-контекста (GUIDE.md, reference/kit.json). Его собирает скилл web-design-context.`);
  process.exit(2);
}
const K = readJson(join(REF, "kit.json"));
const doc = readJson(join(REF, "manifest.json"));
const planFile = resolve(CTX, doc.plan || "plan.json");
const plan = existsSync(planFile) ? readJson(planFile) : {};
const labels = plan.parts || {};
const srcRefs = existsSync(join(REF, "parts-source.json")) ? readJson(join(REF, "parts-source.json")) : {};
const source = existsSync(join(REF, ".cache/source.json")) ? readJson(join(REF, ".cache/source.json")) : null;
const rel = (p) => relative(process.cwd(), join(CTX, p)).split("\\").join("/") || p;
const GROUPS = { buttons: "Кнопки", inputs: "Поля", links: "Ссылки", badges: "Бейджи", cards: "Карточки" };
const statusOf = (id) => (labels[id] || {}).status || "unreviewed";
const ST = { canon: "канон", variant: "вариант", unreviewed: "не разобрано", noise: "шум" };

const out = { context: rel("."), stance: plan.stance || null, createdAt: doc.createdAt, source: doc.source };

// ---------- свежесть: коммиты в исходниках после съёмки ----------
try {
  const srcs = [].concat(plan.src || []).map((s) => resolve(CTX, s)).filter(existsSync);
  if (srcs.length && doc.createdAt) {
    const log = execFileSync("git", ["log", `--since=${doc.createdAt}`, "--oneline", "--", ...srcs], { encoding: "utf8", cwd: srcs[0] }).trim();
    out.commitsSinceCapture = log ? log.split("\n").length : 0;
    out.recentCommits = log ? log.split("\n").slice(0, 3) : [];
  }
} catch {}

// ---------- основы ----------
const colorRows = (role, n) => (K.colors[role] || []).slice(0, n).map((c) => ({ color: c.color, vars: c.vars || [], n: c.n }));
out.colors = { text: colorRows("text", 8), background: colorRows("background", 8), border: colorRows("border", 5) };
out.fonts = (K.fonts || []).slice(0, 3).map((f) => f.family);
out.type = (K.type || []).slice(0, 10).map((t) => ({ font: `${t.family} ${t.size}/${t.lineHeight} ${t.weight}`, n: t.n, ex: t.ex && t.ex[0] ? `${t.ex[0].tag} «${t.ex[0].text.slice(0, 24)}»` : "" }));
out.radius = (K.radius || []).slice(0, 6).map((x) => x.v);
out.shadow = (K.shadow || []).slice(0, 3).map((x) => x.v);
out.spacing = (K.spacing || []).slice(0, 10).map((x) => x.v);
const tf = join(REF, "tokens.json");
out.cssVariables = existsSync(tf) ? Object.keys(readJson(tf).cssVariables || {}).length : 0;

// ---------- детали ----------
const wanted = args.groups ? args.groups.split(",").map((s) => s.trim()) : Object.keys(GROUPS);
out.parts = {};
for (const g of wanted) {
  const list = (K.parts || {})[g] || [];
  if (!list.length) continue;
  const order = { canon: 0, variant: 1, unreviewed: 2, noise: 3 };
  const pick = list.filter((p) => statusOf(p.id) !== "noise").sort((a, b) => order[statusOf(a.id)] - order[statusOf(b.id)] || b.n - a.n).slice(0, args.max);
  out.parts[g] = { total: list.length, canon: list.filter((p) => statusOf(p.id) === "canon").length, items: pick.map((p) => ({
    id: p.id, status: statusOf(p.id), name: (labels[p.id] || {}).name || null, text: p.text, n: p.n, pages: p.pages.length,
    style: p.style, html: p.html, source: (srcRefs[p.id] || []).map((r) => `${r.file}:${r.line} (${r.how})`),
  })) };
}

// ---------- схема раздела ----------
const comps = existsSync(join(CTX, "compositions")) ? readdirSync(join(CTX, "compositions")).filter((f) => f.endsWith(".md")) : [];
if (args.path) {
  const segs = new URL(args.path, "http://x").pathname.split("/").filter(Boolean).map((s) => s.toLowerCase().replace(/\.html?$/, ""));
  let found = null;
  for (let i = segs.length; i >= 0 && !found; i--) { const name = (i ? segs.slice(0, i).join("--") : "home") + ".md"; if (comps.includes(name)) found = name; }
  out.composition = found ? { file: rel("compositions/" + found), exact: found === (segs.length ? segs.join("--") : "home") + ".md" } : null;
}
out.compositions = comps.map((f) => rel("compositions/" + f));
const headings = (f) => (existsSync(join(CTX, f)) ? [...readFileSync(join(CTX, f), "utf8").matchAll(/^### (.+)$/gm)].map((m) => m[1]) : []);
out.components = headings("parts/components.md");
out.overlays = headings("parts/overlays.md");

// ---------- код ----------
if (source) {
  out.code = {
    stack: Object.values(source.stack || {}).flatMap((o) => Object.keys(o)).slice(0, 14),
    tokensIn: [...new Set((source.cssVars || []).map((v) => v.file))].slice(0, 4),
    themes: (source.themes || []).slice(0, 4).map((t) => `${t.kind} — ${t.file}:${t.line}`),
    variants: (source.variants || []).slice(0, 10).map((v) => `${v.kind} ${v.name || ""} — ${v.file}:${v.line}`),
    uiDirs: [...new Set((source.components || []).map((c) => c.file.replace(/\/[^/]+$/, "")).filter((d) => /(^|\/)(ui|primitives|design-system|ds|kit|base|atoms|elements)(\/|$)/i.test(d)))].slice(0, 5),
  };
}

if (args.json) { console.log(JSON.stringify(out, null, 2)); process.exit(0); }

// ---------- текст ----------
const L = [];
const stance = out.stance === "preserve" ? "**повторять как есть** — новое делай как ближайший существующий вариант, ничего не «улучшай»"
  : out.stance === "normalize" ? "**приводить к канону** — только варианты со статусом «канон»; шум и легаси не повторяй"
    : "**не задана** — спроси владельца; пока бери самые частые варианты и скажи об этом в отчёте";
L.push(`# Выжимка дизайн-контекста — ${out.context}`, "", `Источник: ${out.source} · снят ${String(out.createdAt).slice(0, 10)}`);
if (out.commitsSinceCapture) L.push(`⚠ После даты съёмки исходники (\`src\` плана) меняли ${out.commitsSinceCapture} коммит(ов): ${out.recentCommits.map((c) => "«" + c + "»").join(", ")}${out.commitsSinceCapture > 3 ? " …" : ""}.`,
  "  Если среди них есть новые компоненты или стили — сверяй `source.md` с кодом; check.mjs сравнивает со снятым состоянием. Служебные коммиты (init, форматирование) можно не учитывать.");
L.push("", `Позиция проекта: ${stance}.`, "");
L.push("## Токены", "");
const cl = (rows) => rows.map((c) => `\`${c.color}\`${c.vars.length ? ` var(${c.vars[0]})` : ""}`).join(", ") || "—";
L.push(`- Текст: ${cl(out.colors.text)}`, `- Фоны: ${cl(out.colors.background)}`, `- Границы: ${cl(out.colors.border)}`,
  `- Шрифты: ${out.fonts.join(", ") || "—"}`, `- Радиусы: ${out.radius.join(", ") || "—"} · Тени: ${out.shadow.map((s) => "`" + s + "`").join(", ") || "нет"}`,
  `- Отступы (частые): ${out.spacing.join(", ") || "—"}`, `- CSS-переменных на сайте: ${out.cssVariables} (\`${rel("assets/tokens.css")}\`) — в новом коде переменные, не литералы`, "");
L.push("Типографика (частые сочетания):", "", ...out.type.map((t) => `- ${t.font}${t.ex ? ` — ${t.ex}` : ""}`), "");
L.push("## Детали", "");
for (const [g, d] of Object.entries(out.parts)) {
  L.push(`### ${GROUPS[g] || g} — вариантов ${d.total}, канон ${d.canon}${d.canon ? "" : " (разбора нет: показаны частые)"} · полный список: \`${rel(`parts/${g}.md`)}\``, "");
  for (const p of d.items) {
    const s = p.style || {};
    L.push(`**${p.name || (p.text ? `«${p.text}»` : p.id)}** · ${ST[p.status]} · \`${p.id}\` · ${p.n}× на ${p.pages} стр.`,
      `- стиль: фон \`${s.background}\`, текст \`${s.color}\`, граница \`${s.border}\`, радиус \`${s.radius}\`, шрифт \`${s.font}\`, отступы \`${s.padding}\``);
    for (const r of p.source) L.push(`- исходник: ${r}`);
    L.push("```html", p.html, "```", "");
  }
}
L.push("## Где менять и на что смотреть", "");
if (args.path) L.push(out.composition ? `- Схема раздела для \`${args.path}\`: \`${out.composition.file}\`${out.composition.exact ? "" : " (ближайший раздел — точной схемы нет)"}` : `- Для \`${args.path}\` схемы нет — возьми похожий раздел: ${out.compositions.slice(0, 6).map((f) => "`" + f + "`").join(", ")}`);
else L.push(`- Схемы разделов: ${out.compositions.map((f) => "`" + f + "`").join(", ") || "—"} (передай --path, чтобы выбрать)`);
if (out.components.length) L.push(`- Компоненты (\`${rel("parts/components.md")}\`): ${out.components.join("; ")}`);
if (out.overlays.length) L.push(`- Модалки и меню (\`${rel("parts/overlays.md")}\`): ${out.overlays.join("; ")}`);
if (out.code) {
  L.push(`- Стек: ${out.code.stack.join(", ") || "без дизайн-библиотек"}`);
  if (out.code.tokensIn.length) L.push(`- Токены в коде: ${out.code.tokensIn.join(", ")}`);
  if (out.code.themes.length) L.push(`- Темы/конфиги: ${out.code.themes.join("; ")}`);
  if (out.code.uiDirs.length) L.push(`- Примитивы UI: ${out.code.uiDirs.join(", ")} — переиспользуй, не копируй классы со страницы`);
  if (out.code.variants.length) L.push(`- Варианты в коде: ${out.code.variants.join("; ")}`);
  L.push(`- Подробно: \`${rel("source.md")}\``);
} else L.push("- Исходники в контексте не сканировались (нет `source.md`): ищи компоненты в коде по классам из разметки выше.");
L.push("", "Проверка после изменений: `node <skill>/scripts/check.mjs --context " + out.context + " --url <адрес> [--selector <новый блок>] --changed`");
console.log(L.join("\n"));
