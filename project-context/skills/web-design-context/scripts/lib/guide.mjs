// Указатель на дизайн-контекст в файле инструкций проекта (AGENTS.md, CLAUDE.md…): короткий блок
// между метками — какие вопросы решает и путь до GUIDE.md. Текст вне меток не трогаем.
import { readFileSync, writeFileSync, existsSync } from "node:fs";
import { dirname, relative, sep } from "node:path";
import { posix } from "node:path";
import { ensureDir } from "./runtime.mjs";

export const BLOCK_START = "<!-- web-design-context:start -->";
export const BLOCK_END = "<!-- web-design-context:end -->";

// Блок для файла инструкций проекта: когда открывать гайд и где он лежит.
export function contextBlock(guideRel, doc) {
  const dir = posix.dirname(guideRel);
  return [BLOCK_START,
    "## Дизайн-контекст",
    "",
    `В \`${dir}/\` — дизайн проекта, извлечённый из отрисованного сайта${/^сборка /.test(doc.source || "") ? " (локальная сборка)" : doc.source ? ` (${doc.source})` : ""}${doc.hasSource ? " и исходников" : ""}: основы (цвета с CSS-переменными, типографика, отступы, движение),`,
    "детали с вариантами (кнопки, поля, карточки, компоненты, модалки), схемы разделов, шрифты и иконки. Открой гайд, когда:",
    "",
    "- верстаешь или меняешь страницу, раздел, компонент — чтобы новое выглядело как существующее;",
    "- нужны цвета, шрифты, отступы, анимации, иконки, логотипы проекта;",
    "- нужен вид или разметка модалки, меню, состояния;",
    "- проверяешь свою вёрстку против текущего дизайна.",
    "",
    `Гайд: [\`${guideRel}\`](${guideRel}) — какой файл открыть под задачу и позиция проекта (повторять как есть или приводить к канону). Грузи только нужные файлы.`,
    BLOCK_END].join("\n");
}

// Вписывает/обновляет блок в файлах контекста. Возвращает список { file, action }.
export function linkContext(files, guideAbs, doc, log) {
  const out = [];
  for (const file of files) {
    const guideRel = relative(dirname(file), guideAbs).split(sep).join("/");
    const block = contextBlock(guideRel, doc);
    let text = existsSync(file) ? readFileSync(file, "utf8") : "";
    const a = text.indexOf(BLOCK_START), b = text.indexOf(BLOCK_END);
    let action;
    if (a !== -1 && b > a) {
      const next = text.slice(0, a) + block + text.slice(b + BLOCK_END.length);
      action = next === text ? "без изменений" : "обновлён";
      text = next;
    } else if (a !== -1 || b !== -1) {
      log.warnings.push(`${file}: одна метка блока web-design-context без пары — файл не тронут, поправь вручную`);
      out.push({ file, action: "пропущен" });
      continue;
    } else {
      action = text ? "добавлен" : "создан";
      text = text ? text.replace(/\s*$/, "\n\n") + block + "\n" : block + "\n";
    }
    ensureDir(dirname(file));
    writeFileSync(file, text);
    out.push({ file, action });
  }
  return out;
}

// Убирает блок web-design-context из файлов (остальной текст не трогает).
export function unlinkContext(files) {
  const out = [];
  for (const file of files) {
    if (!existsSync(file)) { out.push({ file, action: "нет файла" }); continue; }
    const text = readFileSync(file, "utf8");
    const a = text.indexOf(BLOCK_START), b = text.indexOf(BLOCK_END);
    if (a === -1 || b < a) { out.push({ file, action: "блока нет" }); continue; }
    writeFileSync(file, (text.slice(0, a).replace(/\n+$/, "\n") + text.slice(b + BLOCK_END.length).replace(/^\n+/, "\n")).replace(/^\n+/, ""));
    out.push({ file, action: "убран" });
  }
  return out;
}

// Файлы инструкций, которые читают код-агенты. Первый существующий из «общих» — рекомендация.
export const CONTEXT_FILES = [
  ["AGENTS.md", "общий стандарт: Codex, OpenCode, Qwen Code, Hermes, Cursor, Copilot и др."],
  ["CLAUDE.md", "Claude Code"],
  [".claude/CLAUDE.md", "Claude Code"],
  ["GEMINI.md", "Gemini CLI"],
  ["QWEN.md", "Qwen Code"],
  [".github/copilot-instructions.md", "GitHub Copilot"],
  ["CONVENTIONS.md", "Aider и др."],
];
export function suggestContext(root) {
  const found = CONTEXT_FILES.filter(([f]) => existsSync(`${root}/${f}`)).map(([file, who]) => {
    const text = readFileSync(`${root}/${file}`, "utf8");
    return { file, who, importsAgents: /^@AGENTS\.md\s*$/m.test(text), hasBlock: text.includes(BLOCK_START) };
  });
  const names = found.map((f) => f.file);
  // CLAUDE.md, который импортирует AGENTS.md (@AGENTS.md), прочитает блок из AGENTS.md сам
  const recommended = names.includes("AGENTS.md") ? ["AGENTS.md"]
    : names.length ? [names[0]] : ["AGENTS.md"];
  return { found, recommended, create: !names.length };
}
