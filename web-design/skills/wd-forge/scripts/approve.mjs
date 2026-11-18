#!/usr/bin/env node
// Утверждение направления: превращает выбранный мокап в дизайн-контекст (design-context/) через скилл wd-scan,
// чтобы дальше страницы и фичи делал wd-fit. Пишет план съёмки и APPROVED.md; с --run сразу снимает и размечает канон.
//
//   node scripts/approve.mjs --dir design-forge --pick b                     план + команды для wd-scan
//   node scripts/approve.mjs --dir design-forge --pick b --run               снять сразу (нужен wd-scan рядом)
//   node scripts/approve.mjs --dir design-forge --pick b --out web/design-context --context ../AGENTS.md
//
// Флаги: --out (куда класть контекст, по умолчанию design-context рядом с <dir>)  --context <файл инструкций, от папки контекста>
//        --run  --wd-scan <папка скилла wd-scan> (если не рядом)  --force (утвердить, хотя lint.mjs нашёл ошибки)
// Код выхода: 0 — готово; 1 — у направления ошибки проверки (без --force) или съёмка упала; 2 — ошибка запуска.
import { readFileSync, existsSync, writeFileSync, mkdirSync } from "node:fs";
import { join, resolve, dirname, relative } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";
import { parseArgs } from "./lib/runtime.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const args = parseArgs(process.argv.slice(2), {
  dir: { default: "design-forge" }, pick: {}, out: {}, context: {}, run: { type: "bool" }, "wd-scan": {}, force: { type: "bool" }, help: { alias: "h", type: "bool" },
});
if (args.help || !args.pick) {
  console.log(readFileSync(fileURLToPath(import.meta.url), "utf8").split("\n").filter((l) => l.startsWith("//")).map((l) => l.slice(3)).join("\n"));
  process.exit(args.help ? 0 : 2);
}
const die = (m, code = 2) => { console.error("error: " + m); process.exit(code); };
const DIR = resolve(args.dir);
if (!existsSync(join(DIR, "directions.json"))) die(`нет ${join(DIR, "directions.json")}`);
const D = JSON.parse(readFileSync(join(DIR, "directions.json"), "utf8"));
const d = D.directions.find((x) => x.letter === args.pick);
if (!d) die(`--pick: одно из ${D.directions.map((x) => x.letter).join(", ")}`);
for (const s of d.screens) if (!existsSync(join(DIR, d.letter, s.file))) die(`нет экрана ${d.letter}/${s.file} — направление не свёрстано`);
const lint = existsSync(join(DIR, "lint-report.json")) ? JSON.parse(readFileSync(join(DIR, "lint-report.json"), "utf8")) : null;
const v = lint && lint.variants[d.letter];
if (!v) console.log("! lint.mjs по этому направлению не запускался — качество не подтверждено");
else if (v.errors && !args.force) die(`у направления ${d.letter.toUpperCase()} ошибок проверки: ${v.errors} — исправь (lint.mjs) или утверди с --force`, 1);

const OUT = resolve(args.out || join(dirname(DIR), "design-context"));
mkdirSync(OUT, { recursive: true });
const rel = (p) => relative(OUT, p).split("\\").join("/") || ".";
const plan = {
  serve: rel(join(DIR, d.letter)),
  stance: "normalize",
  ...(args.context ? { context: args.context } : {}),
  viewports: { desktop: { width: 1440, height: 900 }, mobile: { width: 390, height: 844, isMobile: true, deviceScaleFactor: 2 } },
  pages: d.screens.map((s, i) => ({ id: i === 0 ? "home" : s.file.replace(/\.html?$/, ""), path: s.file === "index.html" ? "/" : "/" + s.file, title: s.what })),
  components: [],
  // вторая тема направления — тем же атрибутом, что в tokens.css; wd-scan снимет её палитру, wd-fit будет проверять обе
  ...((d.themes || []).length > 1 ? { themes: Object.fromEntries(d.themes.slice(1).map((t) => [t, { htmlAttr: { "data-theme": t } }])) } : {}),
};
// общие блоки — если они есть на главном экране (у рабочих интерфейсов шапки может не быть, зато есть сайдбар)
const home = readFileSync(join(DIR, d.letter, d.screens[0].file), "utf8");
for (const [tag, id, title] of [["header", "header", "Шапка"], ["nav", "nav", "Навигация"], ["aside", "sidebar", "Боковая панель"], ["footer", "footer", "Футер"]])
  if (new RegExp(`<${tag}[\\s>]`, "i").test(home)) plan.components.push({ id, group: "layout", page: "home", selector: tag, title });
const planFile = join(OUT, "plan.json");
if (existsSync(planFile) && !args.force) die(`${planFile} уже есть — это контекст другого дизайна? Выбери --out или --force`);
writeFileSync(planFile, JSON.stringify(plan, null, 2) + "\n");
writeFileSync(join(DIR, "APPROVED.md"), `# Утверждено: направление ${d.letter.toUpperCase()} — ${d.archetypeName}\n\nДата: ${new Date().toISOString().slice(0, 10)}\nПалитра: ${d.paletteName}, шрифты: ${d.display} / ${d.body}, форма ${d.shape}, плотность ${d.density}, движение ${d.motion}.\nДизайн-контекст: ${relative(DIR, OUT) || OUT} (план: ${relative(DIR, planFile)}).\n`);
console.log(`Утверждено ${d.letter.toUpperCase()} — ${d.archetypeName}. План съёмки: ${planFile}`);

// wd-scan: рядом в наборе (web-design/skills/wd-scan) или в той же папке скиллов агента
const scanCand = [args["wd-scan"], join(HERE, "..", "..", "wd-scan"), process.env.WD_SCAN_DIR].filter(Boolean).map((p) => resolve(p));
const scan = scanCand.find((p) => existsSync(join(p, "scripts", "capture.mjs")));
const capture = scan ? join(scan, "scripts", "capture.mjs") : "<wd-scan>/scripts/capture.mjs";
const parts = scan ? join(scan, "scripts", "parts.mjs") : "<wd-scan>/scripts/parts.mjs";
if (!args.run) {
  console.log(`Дальше (скилл wd-scan${scan ? "" : " — найди его папку"}):\n  node ${capture} ${planFile}\n  node ${parts} ${OUT} --group <группа> --rest canon      # для каждой группы: новый дизайн — всё канон\nили запусти approve.mjs с --run.`);
  process.exit(0);
}
if (!scan) die("--run: не нашёл wd-scan рядом — укажи --wd-scan <папка скилла> или выполни команды вручную");
const run = (argv) => { const r = spawnSync(process.execPath, argv, { stdio: "inherit" }); if (r.status) die(`упало: node ${argv.join(" ")}`, 1); };
run([capture, planFile]);
const kit = JSON.parse(readFileSync(join(OUT, "reference", "kit.json"), "utf8"));
const groups = Object.entries(kit.parts || {}).filter(([, l]) => l.length);
// имена из UI-кита (data-part) — подписи канона; остальное в группе — тоже канон (новый дизайн)
const named = groups.flatMap(([, l]) => l.filter((p) => p.name).map((p) => `${p.id}=canon:${p.name}`));
if (named.length) run([parts, OUT, "--set", ...named, "--no-rebuild"]);
for (const [g] of groups) run([parts, OUT, "--group", g, "--rest", "canon", "--no-rebuild"]);
run([capture, planFile, "--rebuild"]);
const many = groups.filter(([, l]) => l.length > 6).map(([g, l]) => `${g} ${l.length}`);
console.log(`\nДизайн-контекст: ${join(OUT, "GUIDE.md")} — все детали размечены как канон.${many.length ? `\n! Много вариантов в группах (${many.join(", ")}): мокап непоследователен — проверь parts.mjs --group и пометь лишнее как noise.` : ""}\nДальше страницы и фичи — скиллом wd-fit по этому контексту.`);
