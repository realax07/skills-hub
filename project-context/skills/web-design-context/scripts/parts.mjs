#!/usr/bin/env node
// Разбор деталей текстом — без картинок и без ручной правки JSON (подходит моделям без зрения).
//
//   node scripts/parts.mjs <out>                                 сводка: сколько вариантов в группах и сколько разобрано
//   node scripts/parts.mjs <out> --group buttons                 варианты группы: id, статус, частота, текст, стиль, исходник
//   node scripts/parts.mjs <out> --set 1k3x9a=canon:"Кнопка основная" 0zq2mf=variant:"Кнопка вторичная" 2c8u1w=noise
//   node scripts/parts.mjs <out> --group buttons --rest noise    все неразобранные в группе → шум
//   node scripts/parts.mjs <out> --set 2c8u1w=variant:"Иконочная"   поменять статус уже размеченной — тем же --set
//
// <out> — папка дизайн-контекста (где лежит reference/manifest.json). Статусы: canon | variant | noise | unreviewed
// (unreviewed — снять пометку). Имя после двоеточия — то, что увидит агент-потребитель; для шума не нужно.
// После --set/--rest план сохраняется и слой пересобирается (capture.mjs --rebuild); --no-rebuild — только план.
// Группы: buttons, inputs, links, badges, cards.
import { readFileSync, existsSync, writeFileSync } from "node:fs";
import { join, resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";
import { parseArgs, readJson } from "./lib/runtime.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const args = parseArgs(process.argv.slice(2), {
  group: {}, set: { type: "bool" }, rest: {}, "no-rebuild": { type: "bool" }, limit: { type: "int", default: 60 }, help: { alias: "h", type: "bool" },
});
if (args.help || !args._[0]) {
  console.log(readFileSync(fileURLToPath(import.meta.url), "utf8").split("\n").filter((l) => l.startsWith("//")).map((l) => l.slice(3)).join("\n"));
  process.exit(args.help ? 0 : 2);
}
const OUT = resolve(args._[0]);
const REF = join(OUT, "reference");
if (!existsSync(join(REF, "manifest.json")) || !existsSync(join(REF, "kit.json"))) {
  console.error(`error: в ${OUT} нет reference/manifest.json или reference/kit.json — сначала capture.mjs`);
  process.exit(2);
}
const doc = readJson(join(REF, "manifest.json"));
const K = readJson(join(REF, "kit.json"));
const planPath = resolve(OUT, doc.plan || "plan.json");
const plan = readJson(planPath);
const labels = (plan.parts ||= {});
const srcRefs = existsSync(join(REF, "parts-source.json")) ? readJson(join(REF, "parts-source.json")) : {};
const STATUSES = new Set(["canon", "variant", "noise", "unreviewed"]);
const all = new Map();
for (const [g, list] of Object.entries(K.parts || {})) for (const p of list) all.set(p.id, { ...p, group: g });

let changed = 0;
if (args.set) {
  for (const a of args._.slice(1)) {
    const m = a.match(/^([\w-]+)=(\w+)(?::(.*))?$/);
    if (!m) { console.error(`error: не понял «${a}» — нужно id=status или id=status:Имя`); process.exit(2); }
    const [, id, status, name] = m;
    if (!STATUSES.has(status)) { console.error(`error: статус «${status}» — допустимы canon, variant, noise, unreviewed`); process.exit(2); }
    if (!all.has(id)) console.warn(`  ! id ${id} не найден среди деталей последней съёмки — записываю всё равно`);
    if (status === "unreviewed") delete labels[id];
    else labels[id] = { ...(labels[id] || {}), status, ...(name ? { name: name.trim() } : {}) };
    changed++;
  }
}
if (args.rest) {
  if (!args.group) { console.error("error: --rest нужен вместе с --group"); process.exit(2); }
  if (!STATUSES.has(args.rest) || args.rest === "unreviewed") { console.error("error: --rest canon|variant|noise"); process.exit(2); }
  for (const p of K.parts[args.group] || []) if (!labels[p.id]) { labels[p.id] = { status: args.rest }; changed++; }
}
if (changed) {
  writeFileSync(planPath, JSON.stringify(plan, null, 2) + "\n");
  console.log(`план: ${planPath} — пометок изменено: ${changed}`);
  if (!args["no-rebuild"]) {
    const r = spawnSync(process.execPath, [join(HERE, "capture.mjs"), planPath, "--rebuild"], { encoding: "utf8" });
    if (r.status) { process.stdout.write(r.stdout || ""); process.stderr.write(r.stderr || ""); process.exit(r.status); }
    console.log("слой пересобран (capture.mjs --rebuild)");
  }
  if (!args.group) process.exit(0);
}

const st = (id) => (labels[id] || {}).status || "unreviewed";
if (!args.group) {
  console.log(`Детали (${OUT}):`);
  for (const [g, list] of Object.entries(K.parts || {})) {
    if (!list.length) continue;
    const c = { canon: 0, variant: 0, noise: 0, unreviewed: 0 };
    for (const p of list) c[st(p.id)]++;
    console.log(`  ${g.padEnd(8)} вариантов ${String(list.length).padStart(3)} · канон ${c.canon} · вариант ${c.variant} · шум ${c.noise} · не разобрано ${c.unreviewed}`);
  }
  console.log("Подробно: --group <группа>. Пометить: --set id=canon:\"Имя\" …");
  process.exit(0);
}
const list = K.parts[args.group];
if (!list) { console.error(`error: группы ${args.group} нет; есть: ${Object.keys(K.parts).join(", ")}`); process.exit(2); }
const tot = list.reduce((a, p) => a + p.n, 0);
console.log(`${args.group}: ${list.length} вариантов, ${tot} употреблений. Сортировка — по частоте.`);
console.log("Ориентир канона: частый, на многих страницах, понятная роль. Шум: редкий, почти копия другого, не та категория.\n");
for (const p of list.slice(0, args.limit)) {
  const s = p.style || {};
  const l = labels[p.id] || {};
  console.log(`${p.id}  [${st(p.id)}${l.name ? `: ${l.name}` : ""}]  ${p.n}× (${Math.round((p.n / tot) * 100)}%) на ${p.pages.length} стр.  ${p.w}×${p.h}${p.text ? `  «${p.text}»` : ""}`);
  console.log(`    фон ${s.background} · текст ${s.color} · граница ${s.border} · радиус ${s.radius} · шрифт ${s.font} · отступы ${s.padding}`);
  const cls = ((p.html || "").match(/^<[^>]*?\sclass="([^"]*)"/) || [])[1];
  if (cls) console.log(`    class="${cls.length > 140 ? cls.slice(0, 140) + "…" : cls}"`);
  for (const r of srcRefs[p.id] || []) console.log(`    исходник: ${r.file}:${r.line} (${r.how})`);
}
if (list.length > args.limit) console.log(`\n…ещё ${list.length - args.limit} (редкие): --limit ${list.length}`);
