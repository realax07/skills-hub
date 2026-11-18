#!/usr/bin/env node
// Указатель на дизайн-контекст в файле инструкций проекта (AGENTS.md, CLAUDE.md…): какие вопросы решает
// и путь до GUIDE.md. Блок между метками wd-scan:start/end, остальной текст файла не трогается.
// Обычно это делает capture.mjs сам по полю "context" плана; скрипт — чтобы вписать/убрать без пересъёмки.
//
//   node scripts/link-context.mjs --suggest [--root .]                какие файлы инструкций есть в репо (--json)
//   node scripts/link-context.mjs <папка контекста> --into AGENTS.md    вписать/обновить (несколько — через запятую)
//   node scripts/link-context.mjs <папка контекста> --into AGENTS.md --remove   убрать блок
import { readFileSync, existsSync } from "node:fs";
import { join, resolve, relative } from "node:path";
import { fileURLToPath } from "node:url";
import { parseArgs, readJson } from "./lib/runtime.mjs";
import { linkContext, unlinkContext, suggestContext } from "./lib/guide.mjs";

const args = parseArgs(process.argv.slice(2), {
  into: {}, suggest: { type: "bool" }, root: { default: "." }, remove: { type: "bool" }, json: { type: "bool" }, help: { alias: "h", type: "bool" },
});
if (args.help || (!args.suggest && (!args._[0] || !args.into))) {
  console.log(readFileSync(fileURLToPath(import.meta.url), "utf8").split("\n").filter((l) => l.startsWith("//")).map((l) => l.slice(3)).join("\n"));
  process.exit(args.help ? 0 : 2);
}

if (args.suggest) {
  const r = suggestContext(resolve(args.root));
  if (args.json) console.log(JSON.stringify(r, null, 2));
  else {
    if (!r.found.length) console.log("Файлов инструкций агентов нет. Предложи создать AGENTS.md (его читает большинство агентов).");
    for (const f of r.found) console.log(`  ${f.file} — ${f.who}${f.importsAgents ? " (импортирует @AGENTS.md)" : ""}${f.hasBlock ? " [блок дизайн-контекста уже есть]" : ""}`);
    console.log(`Рекомендация: ${r.recommended.join(", ")}${r.create ? " (создать)" : ""}`);
  }
  process.exit(0);
}

const OUT = resolve(args._[0]);
const files = args.into.split(",").map((f) => resolve(f.trim()));
const log = { warnings: [] };
let res;
if (args.remove) res = unlinkContext(files);
else {
  if (!existsSync(join(OUT, "GUIDE.md")) || !existsSync(join(OUT, "reference", "manifest.json"))) {
    console.error(`error: в ${OUT} нет GUIDE.md / reference/manifest.json — сначала capture.mjs`);
    process.exit(1);
  }
  res = linkContext(files, join(OUT, "GUIDE.md"), readJson(join(OUT, "reference", "manifest.json")), log);
}
for (const r of res) console.log(`  ${relative(process.cwd(), r.file) || r.file} — ${r.action}`);
for (const w of log.warnings) console.log(`  ! ${w}`);
process.exit(log.warnings.length ? 1 : 0);
