// Гайд для агента (GUIDE.md в корне мокапов) и указатель на него в файле инструкций проекта.
//
// GUIDE.md отвечает на «у меня задача X — какие файлы открыть»: какие вопросы решают мокапы,
// маршрутизация задач, указатель компонентов и модалок по всему сайту, правила загрузки контекста.
// Указатель — короткий блок между метками в AGENTS.md / CLAUDE.md / другом файле, который агент
// читает всегда: без него агент про мокапы не узнает. Текст вне меток не трогаем.
import { readFileSync, writeFileSync, existsSync } from "node:fs";
import { dirname, relative, sep } from "node:path";
import { posix } from "node:path";
import { ensureDir } from "./runtime.mjs";

export const BLOCK_START = "<!-- site-mockups:start -->";
export const BLOCK_END = "<!-- site-mockups:end -->";

const GROUP_TITLES = {
  layout: "каркас (шапка, футер, сайдбары)", sections: "крупные блоки страниц", forms: "формы", controls: "контролы (кнопки, поля)",
  content: "контент (карточки, таблицы, списки)", navigation: "навигация (табы, крошки, пагинация)", modals: "модалки", menus: "меню и выпадающие",
};

// Одна строка на элемент: версия основного вьюпорта, остальные вьюпорты перечислены.
function uniqueItems(items, doc) {
  const by = new Map();
  for (const it of items) {
    const key = `${it.baseId}#${it.variant || 0}`;
    if (!by.has(key)) by.set(key, { main: null, vps: new Set() });
    const e = by.get(key);
    e.vps.add(it.viewport);
    if (!e.main || it.viewport === doc.primaryViewport) e.main = it;
  }
  return [...by.values()];
}

const sectionName = (s) => (s.folder ? `\`${s.path}\`` : "главная");
const onSection = (s) => (s.folder ? `\`${s.path}\`` : "главной");

export function guideMd(ordered, doc, tokens, MARK) {
  const all = ordered.flatMap((s) => [...s.page, ...s.states, ...s.modals, ...s.components].map((it) => ({ it, s })));
  const vpList = Object.keys(doc.viewports || {});
  const other = vpList.filter((v) => v !== doc.primaryViewport);
  const vars = Object.keys((tokens && tokens.cssVariables) || {}).length;
  const pages = ordered.filter((s) => s.page.length);
  const line = (e, s, extra = "") =>
    `- [\`${e.main.file}\`](${e.main.file}) — ${e.main.title}${e.main.viewport !== doc.primaryViewport ? ` (${e.main.viewport})` : ""}${extra}${e.vps.size > 1 ? ` · также ${[...e.vps].filter((v) => v !== e.main.viewport).join(", ")}` : ""}${e.main.notes ? ` — ${e.main.notes}` : ""}`;

  const L = [MARK, "# Мокапы сайта — гайд для агента", "",
    `Статические HTML-снимки сайта (источник: ${doc.source}, ${String(doc.createdAt).slice(0, 10)}): страницы, компоненты, модалки и состояния`,
    "с той же разметкой и классами, что на сайте, реально применёнными стилями и дизайн-ассетами. Скриптов нет, открываются без сети.",
    "Это эталон **текущего дизайна**. Поведение и данные смотри в коде — мокап показывает только, как это выглядит и свёрстано.", "",
    "## Какие вопросы решают", "",
    "- Как выглядит и как свёрстана страница или раздел (структура, теги, классы)?",
    "- Как устроен компонент: шапка, футер, кнопка, карточка, форма — разметка и стили?",
    "- Как выглядит модалка, выпадающее меню, состояние страницы (открытое меню, ошибки формы)?",
    other.length ? `- Как это выглядит на ${other.join(", ")}?` : null,
    "- Какие цвета, шрифты, размеры, радиусы, тени использует сайт (дизайн-токены)?",
    "- Какие логотипы, иконки, шрифты брать файлами?",
    "- Совпадает ли новая вёрстка с текущим дизайном (сравнение с мокапом и скриншотом оригинала)?", "",
    "## Задача → что открыть", "",
    "Не грузи всё дерево. Каждый раздел самодостаточен вместе с папками выше: его README перечисляет, что где.", "",
    "| Задача | Что открыть |",
    "|---|---|",
    "| Доработка страницы или раздела `/x/y` | `x/y/README.md` → `x/y/index.html`; стили — `_css/styles.css` в `x/y/` и в каждой папке выше до корня (пути в README раздела) |",
    "| Новая страница в существующем разделе | README и `index.html` соседней страницы того же раздела — это шаблон; плюс общие компоненты с главной |",
    "| Новый раздел, похожего нет | [README.md](README.md) (карта) → главная `index.html` + `tokens.css` + `_components/` корня |",
    "| Компонент (шапка, футер, кнопка, карточка) | указатель «Компоненты» ниже; общие для сайта — в `_components/` корня |",
    "| Модалка, меню, поповер | указатель «Модалки, меню и состояния» ниже — отдельно в `_modals/`; поверх страницы — в `_states/` того же раздела |",
    other.length ? `| Мобильная или другая версия | тот же файл с суффиксом \`--<вьюпорт>\`: ${other.map((v) => `\`index--${v}.html\``).join(", ")} |` : null,
    "| Цвета, шрифты, отступы, радиусы | [`tokens.css`](tokens.css) (CSS-переменные), [`tokens.json`](tokens.json) (частотность значений) |",
    "| Логотипы, иконки, шрифты | `_media/` раздела или корня; что откуда — в README раздела |",
    "| Как это выглядит в пикселях | `.png` рядом с каждым HTML — скриншот оригинала |",
    "| Проверить свою вёрстку против дизайна | открой мокап и свою версию на том же вьюпорте, сравни со скриншотом оригинала |",
    "| Найти элемент по селектору или id | [`manifest.json`](manifest.json): `items[].selector`, `items[].file`, `sections[]` |",
    "", "## Указатель", "",
    "### Страницы", "",
    ...pages.map((s) => `- ${sectionName(s)} → [\`${s.folder ? s.folder + "/" : ""}README.md\`](${s.folder ? s.folder + "/" : ""}README.md) — ${s.title || ""}`),
    ""].filter((x) => x !== null);

  const comps = all.filter(({ it }) => !["page", "state", "modal"].includes(it.kind));
  if (comps.length) {
    L.push("### Компоненты", "");
    const groups = new Map();
    for (const c of comps) {
      const g = c.it.file.match(/_components\/([^/]+)\//)?.[1] || "other";
      if (!groups.has(g)) groups.set(g, []);
      groups.get(g).push(c);
    }
    for (const [g, list] of [...groups].sort()) {
      L.push(`**${g}**${GROUP_TITLES[g] ? ` — ${GROUP_TITLES[g]}` : ""}`, "");
      for (const s of ordered) {
        const mine = list.filter((c) => c.s === s).map((c) => c.it);
        for (const e of uniqueItems(mine, doc)) L.push(line(e, s, ` · снят на ${onSection(s)}`));
      }
      L.push("");
    }
  }
  const overlays = all.filter(({ it }) => it.kind === "modal" || it.kind === "state");
  if (overlays.length) {
    L.push("### Модалки, меню и состояния", "");
    for (const s of ordered) {
      for (const e of uniqueItems(s.modals, doc)) L.push(line(e, s, ` · на ${onSection(s)}`));
      for (const e of uniqueItems(s.states, doc)) L.push(line(e, s, ` · состояние: ${sectionName(s)}`));
    }
    L.push("");
  }

  L.push("## Как устроено", "",
    "- Папки повторяют URL: корень — главная, `docs/colors/` — `/docs/colors`. В папке раздела: `index.html` (и `index--<вьюпорт>.html`),",
    "  `_states/`, `_modals/`, `_components/<группа>/`, `_css/styles.css`, `_media/`, `README.md`.",
    "- Стили и ассеты лежат в ближайшем общем разделе страниц, которые их используют: раздел + папки выше = всё нужное, лишнего нет.",
    "- Контент (фото, видео статей) заменён заглушками тех же пропорций: `data-mockup-placeholder`, исходник — `data-mockup-src`.",
    "  Ссылки между снятыми страницами работают, исходный путь — `data-mockup-href`. Исходное позиционирование оверлея — `data-mockup-position`.",
    `- Дизайн-токены: ${vars} CSS-переменных в \`tokens.css\`.`,
    "- Файлы сгенерированы: не правь их руками — при пересъёмке перезапишутся. Устарели — переснимай.", "",
    "## Обновление", "",
    `Мокапы делает скилл \`site-mockups\`; план съёмки — \`${doc.plan || "plan.json"}\` (путь от этой папки).`, "",
    "```bash",
    `node <скилл site-mockups>/scripts/capture.mjs ${doc.plan || "plan.json"}             # переснять всё`,
    `node <скилл site-mockups>/scripts/capture.mjs ${doc.plan || "plan.json"} --only <id> # отдельные элементы`,
    "node <скилл site-mockups>/scripts/verify.mjs .                       # проверка",
    "```", "");
  return L.join("\n");
}

// Блок для файла инструкций проекта: когда открывать гайд и где он лежит.
export function contextBlock(guideRel, doc) {
  const dir = posix.dirname(guideRel);
  return [BLOCK_START,
    "## Мокапы дизайна сайта",
    "",
    `В \`${dir}/\` — статические HTML-снимки сайта (источник: ${doc.source}): страницы по разделам, компоненты, модалки, состояния, дизайн-токены.`,
    "Это эталон текущего дизайна и вёрстки. Открой гайд, когда:",
    "",
    "- верстаешь или меняешь страницу, раздел, компонент — нужно, как это выглядит и свёрстано сейчас;",
    "- нужен вид модалки, меню, состояния или мобильной версии;",
    "- нужны цвета, шрифты, отступы, логотипы, иконки сайта;",
    "- проверяешь свою вёрстку против текущего дизайна.",
    "",
    `Гайд: [\`${guideRel}\`](${guideRel}) — какие файлы брать под задачу. Грузи только папку нужного раздела и папки выше, не всё дерево.`,
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
      log.warnings.push(`${file}: одна метка блока site-mockups без пары — файл не тронут, поправь вручную`);
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

// Убирает блок site-mockups из файлов (остальной текст не трогает).
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
