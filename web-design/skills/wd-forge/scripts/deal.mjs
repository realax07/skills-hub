#!/usr/bin/env node
// Раздача трёх диаметрально разных направлений дизайна из каталогов (assets/catalog/) — детерминированно.
// Оси: UX-архетип и раскладка, палитра (светлая/тёмная, температура, тон акцента), типографика, форма, плотность, движение.
// Из тысяч сочетаний, допустимых для режима поверхности, выбирается тройка с максимальным минимальным расстоянием
// между направлениями — чтобы не получилось три оттенка одного. Для каждого пишет tokens.css, base.css и PLAN.md.
//
//   node scripts/deal.mjs --out design-forge --mode persuade --product "Обжарочная Зерно"
//   node scripts/deal.mjs --out design-forge --mode operate --product "CRM для клиник" --scheme light
//   node scripts/deal.mjs --out design-forge --reroll c            переиграть одно направление, остальные оставить
//   node scripts/deal.mjs --validate                               проверить контраст палитр каталога
//
// Флаги: --mode persuade|operate|read|experience (обязательно, кроме --validate/--reroll)
//        --product "<название>" (зерно раздачи и заголовки)  --seed <строка> (другая раздача при том же брифе)
//        --scheme light|dark (все направления в одной схеме; по умолчанию — смешанно)
//        --brand "#hex" (бренд-цвет: акцент во всех трёх направлениях)  --screens "index.html:главная,app.html:дашборд"
//        --force (перезаписать существующие tokens.css и PLAN.md)  --json
// Код выхода: 0 — готово; 1 — проверка каталога нашла проблемы; 2 — ошибка аргументов.
import { readFileSync, existsSync, writeFileSync, mkdirSync, copyFileSync } from "node:fs";
import { join, resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { parseArgs } from "./lib/runtime.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const CAT = join(HERE, "..", "assets", "catalog");
const args = parseArgs(process.argv.slice(2), {
  out: { default: "design-forge" }, mode: {}, product: { default: "" }, seed: {}, scheme: {}, brand: {}, screens: {},
  reroll: {}, validate: { type: "bool" }, force: { type: "bool" }, json: { type: "bool" }, help: { alias: "h", type: "bool" },
});
if (args.help) {
  console.log(readFileSync(fileURLToPath(import.meta.url), "utf8").split("\n").filter((l) => l.startsWith("//")).map((l) => l.slice(3)).join("\n"));
  process.exit(0);
}
const die = (m) => { console.error("error: " + m); process.exit(2); };
const load = (f) => JSON.parse(readFileSync(join(CAT, f), "utf8"));
const ARCH = load("archetypes.json"), PAL = load("palettes.json").palettes, TYPE = load("type.json").pairs, SYS = load("system.json");

// ---------- цвет ----------
const rgb = (h) => { h = h.replace("#", ""); if (h.length === 3) h = [...h].map((x) => x + x).join(""); return [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16)); };
const lum = (h) => { const [r, g, b] = rgb(h).map((v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; }); return 0.2126 * r + 0.7152 * g + 0.0722 * b; };
export const contrast = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05); };
const hsl = (h) => {
  const [r, g, b] = rgb(h).map((v) => v / 255), mx = Math.max(r, g, b), mn = Math.min(r, g, b), d = mx - mn;
  let hue = 0;
  if (d) hue = mx === r ? ((g - b) / d) % 6 : mx === g ? (b - r) / d + 2 : (r - g) / d + 4;
  const l = (mx + mn) / 2;
  return { h: (hue * 60 + 360) % 360, s: d ? d / (1 - Math.abs(2 * l - 1)) : 0, l };
};
const chroma = (h) => hsl(h).s > 0.25 && hsl(h).l > 0.12 && hsl(h).l < 0.9;
const hueGap = (a, b) => { const d = Math.abs(hsl(a).h - hsl(b).h) % 360; return Math.min(d, 360 - d); };

if (args.validate) {
  let bad = 0;
  const need = (name, a, b, min, what) => { const c = contrast(a, b); if (c < min) { bad++; console.log(`✗ ${name}: ${what} ${c.toFixed(2)} < ${min} (${a} на ${b})`); } };
  for (const p of PAL) {
    const c = p.c;
    for (const k of ["bg", "surface", "text", "muted", "border", "accent", "onAccent", "accent2"]) if (!/^#[0-9a-f]{6}$/i.test(c[k] || "")) { bad++; console.log(`✗ ${p.id}: ${k} не #rrggbb`); }
    need(p.id, c.text, c.bg, 7, "текст/фон"); need(p.id, c.text, c.surface, 7, "текст/поверхность");
    need(p.id, c.muted, c.bg, 4.5, "приглушённый/фон"); need(p.id, c.muted, c.surface, 4.5, "приглушённый/поверхность");
    need(p.id, c.onAccent, c.accent, 4.5, "текст на акценте"); need(p.id, c.accent, c.bg, 3, "акцент/фон (элементы UI)");
  }
  console.log(bad ? `Проблем: ${bad}` : `Палитр: ${PAL.length}, проблем нет`);
  process.exit(bad ? 1 : 0);
}

// ---------- раздача ----------
const OUT = resolve(args.out);
const prev = existsSync(join(OUT, "directions.json")) ? JSON.parse(readFileSync(join(OUT, "directions.json"), "utf8")) : null;
if (args.reroll && !prev) die(`--reroll: нет ${join(OUT, "directions.json")} — сначала раздай без него`);
const mode = args.mode || (prev && prev.mode);
if (!mode || !ARCH[mode]) die(`--mode: одно из ${Object.keys(ARCH).filter((k) => !k.startsWith("_")).join(", ")}`);
const product = args.product || (prev && prev.product) || "Продукт";
const brand = args.brand || (prev && prev.brand) || null;
if (brand && !/^#[0-9a-f]{6}$/i.test(brand)) die("--brand: цвет #rrggbb");
const scheme = args.scheme || (prev && prev.scheme) || null;
const M = SYS.modes[mode];

// детерминированный ГПСЧ от брифа
const seedStr = `${args.seed || (prev && prev.seed) || ""}|${product}|${mode}`;
let h = 2166136261; for (const ch of seedStr) { h ^= ch.charCodeAt(0); h = Math.imul(h, 16777619); }
let st = h >>> 0;
const rnd = () => { st |= 0; st = (st + 0x6d2b79f5) | 0; let t = Math.imul(st ^ (st >>> 15), 1 | st); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
const pick = (a) => a[Math.floor(rnd() * a.length)];

const pals = PAL.filter((p) => (!scheme || p.scheme === scheme) && M.scheme.includes(p.scheme));
if (!pals.length) die(`нет палитр для схемы ${scheme}`);
const types = TYPE.filter((t) => !(M.typeAvoid || []).includes(t.class)); // смелость шрифта — по режиму
const candidate = () => {
  const arch = pick(ARCH[mode]);
  const dens = arch.density.filter((d) => M.density.includes(d));
  return { arch, pal: pick(pals), type: pick(types), shape: pick(Object.keys(SYS.shapes)), density: pick(dens.length ? dens : M.density), motion: pick(M.motion) };
};
const accentOf = (d) => brand || d.pal.c.accent;
const ORD = { shape: ["sharp", "soft", "round"], density: ["compact", "regular", "airy"], motion: ["still", "subtle", "orchestrated", "expressive"] };
const step = (k, a, b) => Math.abs(ORD[k].indexOf(a) - ORD[k].indexOf(b)) / (ORD[k].length - 1);
function dist(a, b) {
  let d = a.arch.id !== b.arch.id ? 3 : 0;
  d += a.pal.scheme !== b.pal.scheme ? 2 : 0;
  d += a.pal.temp !== b.pal.temp ? 1 : 0;
  d += a.pal.energy !== b.pal.energy ? 0.75 : 0;
  if (!brand) {
    const ca = chroma(accentOf(a)), cb = chroma(accentOf(b));
    d += ca && cb ? 2.5 * (hueGap(accentOf(a), accentOf(b)) / 180) : ca !== cb ? 1.5 : 0;
  }
  d += a.type.class !== b.type.class ? 2 : 0;
  d += a.type.bodyClass !== b.type.bodyClass ? 0.75 : 0;
  d += a.type.display === b.type.display ? -4 : 0;
  d += 1.5 * step("shape", a.shape, b.shape) + 1 * step("density", a.density, b.density) + 0.75 * step("motion", a.motion, b.motion);
  return d;
}
const ok3 = (t) => new Set(t.map((x) => x.arch.id)).size === t.length && new Set(t.map((x) => x.pal.id)).size === t.length && new Set(t.map((x) => x.type.display)).size === t.length;
const score = (t) => { let mn = Infinity, sum = 0; for (let i = 0; i < t.length; i++) for (let j = i + 1; j < t.length; j++) { const d = dist(t[i], t[j]); mn = Math.min(mn, d); sum += d; } return mn * 100 + sum; };

const LETTERS = ["a", "b", "c"];
const fromPrev = (x) => ({ arch: ARCH[mode].find((a) => a.id === x.archetype), pal: PAL.find((p) => p.id === x.palette), type: TYPE.find((t) => t.id === x.type), shape: x.shape, density: x.density, motion: x.motion });
let best = null, bestScore = -Infinity;
if (args.reroll) {
  const keep = LETTERS.filter((l) => l !== args.reroll);
  if (!LETTERS.includes(args.reroll)) die("--reroll: a, b или c");
  const kept = keep.map((l) => fromPrev(prev.directions.find((d) => d.letter === l)));
  const old = fromPrev(prev.directions.find((d) => d.letter === args.reroll));
  for (let i = 0; i < 5000; i++) {
    const c = candidate();
    if (c.arch.id === old.arch.id && c.pal.id === old.pal.id) continue;
    const t = [...kept]; t.splice(LETTERS.indexOf(args.reroll), 0, c);
    if (!ok3(t)) continue;
    const s = score(t); if (s > bestScore) { bestScore = s; best = t; }
  }
} else {
  for (let i = 0; i < 8000; i++) {
    const t = [candidate(), candidate(), candidate()];
    if (!ok3(t)) continue;
    const s = score(t); if (s > bestScore) { bestScore = s; best = t; }
  }
}
if (!best) die("не удалось подобрать тройку — ослабь ограничения (--scheme)");

// ---------- токены ----------
const fallback = (cls) => (/serif/.test(cls) ? 'Georgia, "Times New Roman", serif' : cls === "mono" ? "ui-monospace, Menlo, monospace" : 'system-ui, "Segoe UI", sans-serif');
const px = (v) => `${Math.round(v)}px`;
function tokensCss(letter, d) {
  const c = { ...d.pal.c };
  if (brand) { c.accent = brand; c.onAccent = contrast("#ffffff", brand) >= contrast("#111111", brand) ? "#ffffff" : "#111111"; }
  const sh = SYS.shapes[d.shape], de = SYS.density[d.density], mo = SYS.motion[d.motion];
  const base = parseFloat(de.base), r = de.ratio;
  const sizes = { xs: base / r / r, sm: base / r, md: base, lg: base * r, xl: base * r ** 2, "2xl": base * r ** 3, "3xl": base * r ** 4, "4xl": base * r ** (mode === "operate" ? 4.4 : 5.6) };
  const fam = [...new Set(d.type.weights.split("|"))].map((f) => "family=" + f).join("&");
  const ui = d.type.ui || d.type.body;
  return `/* Направление ${letter.toUpperCase()} — ${d.arch.name} · ${d.pal.name} · ${d.type.display} / ${d.type.body}
   Сгенерировано deal.mjs. Меняй осознанно и отражай в PLAN.md: lint.mjs сверяет страницы с этими токенами. */
@import url("https://fonts.googleapis.com/css2?${fam}&display=swap");
:root {
  --scheme: ${d.pal.scheme};
  --color-bg: ${c.bg};
  --color-surface: ${c.surface};
  --color-text: ${c.text};
  --color-muted: ${c.muted};
  --color-border: ${c.border};
  --color-accent: ${c.accent};
  --color-on-accent: ${c.onAccent};
  --color-accent-2: ${c.accent2};
  --font-display: "${d.type.display}", ${fallback(d.type.class)};
  --font-body: "${d.type.body}", ${fallback(d.type.bodyClass)};
  --font-ui: "${ui}", ${fallback(d.type.bodyClass)};
${Object.entries(sizes).map(([k, v]) => `  --text-${k}: ${px(k === "xs" ? Math.max(12, v) : k === "sm" ? Math.max(13, v) : v)};`).join("\n")}
  --leading-body: ${/serif/.test(d.type.bodyClass) ? 1.65 : d.density === "compact" ? 1.45 : 1.55};
  --measure: ${de.maxText};
${de.space.map((v, i) => `  --space-${i + 1}: ${v};`).join("\n")}
  --radius-sm: ${sh.radius[0]};
  --radius-md: ${sh.radius[1]};
  --radius-lg: ${sh.radius[2]};
  --shadow-1: ${sh.shadow[0]};
  --shadow-2: ${sh.shadow[1]};
  --dur: ${mo.dur};
  --ease: ${mo.ease};
}
`;
}
const screensOf = (d) => (args.screens ? args.screens.split(",").map((s) => s.split(":").map((x) => x.trim())) : d.arch.screens);
function planMd(letter, d) {
  const sh = SYS.shapes[d.shape], de = SYS.density[d.density], mo = SYS.motion[d.motion];
  const T = "‹заполни›";
  return `# Направление ${letter.toUpperCase()} — ${d.arch.name}

Продукт: ${product} · режим: ${M.name}. Сгенерировано deal.mjs — заполни все пропуски **до вёрстки** (lint.mjs не пропустит незаполненный план).

## Оси направления

| Ось | Значение |
|---|---|
| UX-архетип | **${d.arch.name}** — ${d.arch.idea}. Навигация: ${d.arch.nav} |
| Палитра | ${d.pal.name} (${d.pal.scheme === "dark" ? "тёмная" : "светлая"}, ${d.pal.temp}, ${d.pal.energy}); акцент ${brand || d.pal.c.accent}${brand ? " — бренд" : ""} |
| Типографика | ${d.type.display} / ${d.type.body} — ${d.type.mood} |
| Форма | ${sh.name}: радиусы ${sh.radius.join(" / ")} |
| Плотность | ${de.name}: база ${de.base}, шаг шкалы ${de.ratio}, колонка текста ${de.maxText} |
| Движение | ${mo.name} — ${mo.idea} |
| Смелость режима | ${M.ambition} |

Токены — \`tokens.css\` (цвета, шрифты, шкала, отступы, радиусы, тени, движение), гигиена — \`base.css\`. В вёрстке — только переменные.

## Идея

${T} (1–2 предложения: чем это направление отвечает на бриф и чем оно не похоже на два других)

## Для кого и сценарий

${T} (кто приходит, что хочет сделать, путь по экранам)

## Каркас экранов

${screensOf(d).map(([f, what]) => `### ${f} — ${what}

Опора архетипа: ${d.arch.structure.join(" → ")}.

\`\`\`
${T} ASCII-каркас: зоны и их порядок, что крупно, что мелко
\`\`\``).join("\n\n")}

## Принципы

1. ${T}
2. ${T}
3. ${T}

## Что тут дефолтное — и что изменено

${T} (пройди по черновику: какие решения взялись «сами собой» — центр, карточки, eyebrow, градиент, стандартный герой — и на что заменены)

## Плюсы

- ${T}

## Минусы

- ${T}
`;
}

const directions = best.map((d, i) => ({
  letter: LETTERS[i], archetype: d.arch.id, archetypeName: d.arch.name, palette: d.pal.id, paletteName: d.pal.name, scheme: d.pal.scheme,
  accent: brand || d.pal.c.accent, type: d.type.id, display: d.type.display, body: d.type.body, shape: d.shape, density: d.density, motion: d.motion,
  screens: screensOf(d).map(([file, what]) => ({ file, what })),
}));
mkdirSync(OUT, { recursive: true });
const written = [];
for (const [i, d] of best.entries()) {
  const L = LETTERS[i];
  if (args.reroll && L !== args.reroll) continue;
  const dir = join(OUT, L);
  mkdirSync(dir, { recursive: true });
  for (const [f, text] of [["tokens.css", tokensCss(L, d)], ["PLAN.md", planMd(L, d)]]) {
    const p = join(dir, f);
    if (existsSync(p) && !args.force && !args.reroll) { console.log(`  = ${L}/${f} уже есть — не трогаю (--force перезапишет)`); continue; }
    writeFileSync(p, text); written.push(`${L}/${f}`);
  }
  copyFileSync(join(HERE, "..", "assets", "base.css"), join(dir, "base.css"));
}
const pairs = [];
for (let i = 0; i < 3; i++) for (let j = i + 1; j < 3; j++) pairs.push({ pair: LETTERS[i] + LETTERS[j], distance: +dist(best[i], best[j]).toFixed(2) });
const doc = { product, mode, scheme, brand, seed: args.seed || (prev && prev.seed) || null, createdAt: new Date().toISOString(), directions, distances: pairs };
writeFileSync(join(OUT, "directions.json"), JSON.stringify(doc, null, 2));

if (args.json) { console.log(JSON.stringify(doc, null, 2)); process.exit(0); }
console.log(`Направления для «${product}» (${M.name}) → ${OUT}`);
for (const d of directions) console.log(`  ${d.letter.toUpperCase()}: ${d.archetypeName} · ${d.paletteName} (${d.scheme}, акцент ${d.accent}) · ${d.display} / ${d.body} · форма ${d.shape}, плотность ${d.density}, движение ${d.motion}\n     экраны: ${d.screens.map((s) => `${s.file} (${s.what})`).join(", ")}`);
console.log(`  Расстояния (больше — различнее): ${pairs.map((p) => `${p.pair} ${p.distance}`).join(", ")}`);
console.log(`Записано: ${written.join(", ") || "—"}. Дальше: заполни <буква>/PLAN.md, затем свёрстай экраны в <буква>/.`);
