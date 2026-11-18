// Верхний слой результата — то, что читает агент:
//   GUIDE.md            вход: какие вопросы решает, задача → файл, позиция проекта (stance), указатель
//   foundations.md      цвета (роль, значение, переменная, частота), типографика, отступы, радиусы, тени, движение, шум
//   parts/<группа>.md   детали: кластеры кнопок, полей, ссылок, бейджей, карточек (канон/вариант/шум) +
//                       компоненты и модалки, выбранные в плане (схема разметки)
//   compositions/*.md   сжатые схемы страниц по разделам
//   assets/             шрифты, иконки (svg), логотипы, tokens.css
// Эталон (reference/) собирает build.mjs; отсюда пишется только reference/parts.html — галерея для разбора.
import { readFileSync, writeFileSync, existsSync, readdirSync, copyFileSync, unlinkSync, statSync } from "node:fs";
import { join, posix, extname, relative } from "node:path";
import { ensureDir } from "./runtime.mjs";
import { matchParts } from "./source-scan.mjs";

import { MARK, isGenerated } from "./build.mjs";
export { MARK };
const GROUPS = {
  buttons: "Кнопки", inputs: "Поля ввода", links: "Ссылки", badges: "Бейджи и метки", cards: "Карточки",
};
const STATUS = { canon: "канон", variant: "вариант", noise: "шум", unreviewed: "не разобрано" };
const ORDER = { canon: 0, variant: 1, unreviewed: 2, noise: 3 };
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
const fence = (lang, s) => "```" + lang + "\n" + s + "\n```";

// ---------- слияние извлечений со всех страниц ----------
export function mergeExtracts(list) {
  const sumBy = (target, items, key, extra) => { for (const x of items || []) { const k = x[key]; const t = target.get(k); if (t) { t.n += x.n; if (extra) extra(t, x); } else target.set(k, { ...x }); } };
  const M = { colors: { text: new Map(), background: new Map(), border: new Map(), icon: new Map() }, type: new Map(), spacing: new Map(), radius: new Map(), shadow: new Map(),
    fonts: new Map(), fontFaces: new Set(), transitions: new Map(), animations: new Map(), keyframes: new Set(), js: {}, icons: new Map(), logos: [], parts: {}, pages: [], cssVars: 0 };
  for (const e of list) {
    M.pages.push({ id: e.id, url: e.url });
    const f = e.foundations;
    for (const role of Object.keys(M.colors)) sumBy(M.colors[role], f.colors[role], "color", (t, x) => { t.vars = [...new Set([...(t.vars || []), ...(x.vars || [])])].slice(0, 4); });
    sumBy(M.type, f.type, "key", (t, x) => { if ((t.ex || []).length < 2) t.ex = [...(t.ex || []), ...(x.ex || [])].slice(0, 2); });
    sumBy(M.spacing, f.spacing, "v"); sumBy(M.radius, f.radius, "v"); sumBy(M.shadow, f.shadow, "v"); sumBy(M.fonts, f.fonts, "family");
    (f.fontFaces || []).forEach((x) => M.fontFaces.add(x));
    M.cssVars = Math.max(M.cssVars, f.cssVars || 0);
    sumBy(M.transitions, e.motion.transitions, "v"); sumBy(M.animations, e.motion.animations, "v");
    (e.motion.keyframes || []).forEach((k) => M.keyframes.add(k));
    for (const [k, v] of Object.entries(e.motion.js || {})) M.js[k] = Math.max(M.js[k] || 0, +v);
    sumBy(M.icons, e.icons, "id");
    for (const l of e.logos || []) if (!M.logos.some((x) => x.id === l.id || (l.blob && x.blob === l.blob) || (l.svg && x.svg === l.svg))) M.logos.push(l);
    for (const [g, items] of Object.entries(e.parts || {})) {
      M.parts[g] ||= new Map();
      for (const p of items) {
        const t = M.parts[g].get(p.id);
        if (t) { t.n += p.n; if (!t.pages.includes(e.url)) t.pages.push(e.url); if (!t.crop && p.crop) t.crop = p.crop; }
        else M.parts[g].set(p.id, { ...p, pages: [e.url] });
      }
    }
  }
  const sorted = (m, n) => [...m.values()].sort((a, b) => b.n - a.n).slice(0, n);
  return {
    pages: M.pages,
    colors: Object.fromEntries(Object.entries(M.colors).map(([k, m]) => [k, sorted(m, 60)])),
    type: sorted(M.type, 60), spacing: sorted(M.spacing, 30), radius: sorted(M.radius, 20), shadow: sorted(M.shadow, 16),
    fonts: sorted(M.fonts, 12), fontFaces: [...M.fontFaces].sort(), cssVars: M.cssVars,
    motion: { transitions: sorted(M.transitions, 24), animations: sorted(M.animations, 24), keyframes: [...M.keyframes].sort(), js: M.js },
    icons: sorted(M.icons, 120), logos: M.logos,
    parts: Object.fromEntries(Object.entries(M.parts).map(([g, m]) => [g, sorted(m, 200)])),
  };
}

// «сколько вариантов покрывают 80% употреблений» — мера разброса
const cover = (list) => {
  const tot = list.reduce((a, x) => a + x.n, 0);
  let acc = 0, k = 0;
  for (const x of list) { acc += x.n; k++; if (acc >= tot * 0.8) break; }
  return { variants: list.length, for80: tot ? k : 0 };
};
const shortKeyframe = (k) => k.replace(/^[_A-Za-z0-9]{5,8}_(?=[a-z])/, ""); // хэш-префикс CSS-модулей
function motionSummary(m) {
  const dur = new Map(), ease = new Map();
  for (const t of m.transitions) {
    const [, d, e] = t.v.split(" | ");
    for (const x of (d || "").split(", ")) if (x !== "0s") dur.set(x, (dur.get(x) || 0) + t.n);
    for (const x of (e || "").split(/,\s*(?![^(]*\))/)) ease.set(x, (ease.get(x) || 0) + t.n);
  }
  const top = (mm) => [...mm.entries()].sort((a, b) => b[1] - a[1]).slice(0, 6);
  return { durations: top(dur), easings: top(ease) };
}

// ---------- файлы ----------
function writeIf(OUT, rel, text, generated) {
  const full = join(OUT, rel);
  if (existsSync(full) && rel.endsWith(".md") && !isGenerated(readFileSync(full, "utf8"))) return false; // написан руками
  ensureDir(join(full, ".."));
  writeFileSync(full, text);
  generated.add(rel);
  return true;
}

function foundationsMd(K, noise, warnings) {
  const L = [MARK, "# Основы дизайна", "", `Собрано с ${K.pages.length} страниц. Частота — сколько видимых элементов используют значение.`,
    "Переменная — CSS-переменная сайта с тем же значением: в новом коде используй её, а не литерал.", ""];
  const roles = { text: "Текст", background: "Фоны", border: "Границы", icon: "Иконки (fill)" };
  L.push("## Цвета", "");
  for (const [role, title] of Object.entries(roles)) {
    const list = K.colors[role] || [];
    if (!list.length) continue;
    L.push(`### ${title}`, "", "| Цвет | Переменная | Частота |", "|---|---|---|");
    for (const c of list.slice(0, 16)) L.push(`| \`${c.color}\` | ${(c.vars || []).map((v) => "`" + v + "`").join(" ") || "—"} | ${c.n} |`);
    if (list.length > 16) L.push(`| …ещё ${list.length - 16} редких | | ${list.slice(16).reduce((a, x) => a + x.n, 0)} |`);
    L.push("");
  }
  L.push("## Типографика", "", "| Шрифт | Размер / интерлиньяж | Вес | Трекинг | Регистр | Частота | Пример |", "|---|---|---|---|---|---|---|");
  for (const t of K.type.slice(0, 24)) {
    const ex = (t.ex || [])[0];
    L.push(`| ${t.family}${t.style === "italic" ? " italic" : ""} | ${t.size} / ${t.lineHeight} | ${t.weight} | ${t.letterSpacing} | ${t.transform === "none" ? "—" : t.transform} | ${t.n} | ${ex ? `\`${ex.tag}\` ${ex.text.replace(/\|/g, "/").slice(0, 40)}` : ""} |`);
  }
  if (K.type.length > 24) L.push(`| …ещё ${K.type.length - 24} сочетаний | | | | | ${K.type.slice(24).reduce((a, x) => a + x.n, 0)} | |`);
  L.push("", `Семейства: ${K.fonts.map((f) => `${f.family} (${f.n})`).join(", ") || "—"}.`,
    `Загруженные начертания: ${K.fontFaces.join(", ") || "—"}. Файлы — \`assets/fonts/\`.`, "");
  L.push("## Отступы, радиусы, тени", "",
    `- **Отступы:** ${K.spacing.map((x) => `${x.v} (${x.n})`).join(", ") || "—"}`,
    `- **Радиусы:** ${K.radius.map((x) => `${x.v === "9999px" || parseFloat(x.v) > 500 ? "pill" : x.v} (${x.n})`).join(", ") || "—"}`,
    `- **Тени:**${K.shadow.length ? "" : " —"}`, ...K.shadow.slice(0, 10).map((x) => `  - \`${x.v}\` (${x.n})`), "");
  const ms = motionSummary(K.motion);
  L.push("## Движение", "",
    `- **Длительности переходов:** ${ms.durations.map(([d, n]) => `${d} (${n})`).join(", ") || "—"}`,
    `- **Кривые:** ${ms.easings.map(([e, n]) => `\`${e}\` (${n})`).join(", ") || "—"}`,
    `- **@keyframes (${K.motion.keyframes.length}):** ${K.motion.keyframes.slice(0, 40).map(shortKeyframe).join(", ") || "—"}`,
    `- **Анимации в работе:** ${K.motion.animations.slice(0, 8).map((a) => `${shortKeyframe(a.v.split(" | ")[0])} ${a.v.split(" | ").slice(1).join(" ")} (${a.n})`).join("; ") || "—"}`,
    `- **JS:** ${Object.entries(K.motion.js).filter(([, v]) => v).map(([k, v]) => `${k}${v > 1 ? " ×" + v : ""}`).join(", ") || "нет признаков GSAP / Framer Motion / Lottie / canvas / WebGL"}`, "",
    "<details><summary>Переходы целиком (свойство | длительность | кривая)</summary>", "", ...K.motion.transitions.map((t) => `- \`${t.v}\` (${t.n})`), "", "</details>", "");
  const notes = (warnings || []).filter((w) => /meta name="viewport"/.test(w));
  if (notes.length) L.push("## Особенности вёрстки", "", `- Нет \`<meta name="viewport">\` (${notes.length} стр.): на телефоне страницы рисуются как десктоп шириной ~980px, мобильные правила @media не срабатывают. Мобильные снимки в \`reference/\` это показывают. В новых страницах — решение по позиции проекта.`, "");
  L.push("## Разброс", "", "Сколько вариантов найдено и сколько из них дают 80% употреблений. Большой разрыв — признак шума или легаси.", "",
    "| Что | Вариантов | Дают 80% |", "|---|---|---|", ...Object.entries(noise).map(([k, v]) => `| ${k} | ${v.variants} | ${v.for80} |`), "");
  return L.join("\n");
}

function partsMd(group, list, labels, stance, srcRefs, link, siteFonts) {
  const title = GROUPS[group] || group;
  const items = list.map((p) => ({ ...p, label: labels[p.id] || {} })).map((p) => ({ ...p, status: p.label.status || "unreviewed" }))
    .sort((a, b) => ORDER[a.status] - ORDER[b.status] || b.n - a.n);
  const c = cover(list);
  const L = [MARK, `# ${title}`, "", `Найдено вариантов: ${c.variants}, из них ${c.for80} дают 80% употреблений.`,
    stance === "preserve" ? "Позиция проекта — **повторять как есть**: новый элемент делай как ближайший существующий вариант." :
      stance === "normalize" ? "Позиция проекта — **приводить к канону**: в новом коде только варианты со статусом «канон»." :
        "Позиция проекта не задана (`stance` в плане) — по умолчанию бери самые частые варианты.", "",
    "Статус задаётся в плане (`parts` → id → `status`, `name`); вырезки всех вариантов — `reference/parts.html`.", ""];
  // подробно — разобранные и частые (до 20); шум и хвост — одной строкой ниже
  const shown = items.filter((p) => p.status !== "noise").slice(0, 20);
  for (const p of shown) {
    const name = p.label.name || (p.text ? `«${p.text}»` : p.id);
    L.push(`## ${name} · ${STATUS[p.status]} · ${p.n}× на ${p.pages.length} стр.`, "");
    if (p.label.note) L.push(p.label.note, "");
    const s = p.style || {};
    L.push(`- id: \`${p.id}\` · размер ${p.w}×${p.h}${p.crop ? ` · вырезка: [${posix.basename(p.crop)}](../reference/${p.crop})` : ""}`,
      `- стиль: фон \`${s.background}\`, текст \`${s.color}\`, граница \`${s.border}\`, радиус \`${s.radius}\`, шрифт \`${s.font}\`, отступы \`${s.padding}\`${s.shadow ? `, тень \`${s.shadow}\`` : ""}${s.transition ? `, переход \`${s.transition}\`` : ""}`,
      `- где: ${p.pages.slice(0, 3).join(", ")}${p.pages.length > 3 ? ` и ещё ${p.pages.length - 3}` : ""}`);
    const fam = ((s.font || "").match(/\/\S+\s+(.+)$/) || [])[1];
    if (fam && siteFonts && siteFonts.length && !siteFonts.some((f) => fam.includes(f))) L.push(`- ⚠ шрифт \`${fam}\` не из основных на сайте (${siteFonts.join(", ")}) — часто браузерный по умолчанию у полей и кнопок без \`font: inherit\``);
    for (const r of (srcRefs || {})[p.id] || []) L.push(`- исходник: [${link(r.file)}:${r.line}](${link(r.file, "parts")}) — ${r.how}${r.cls ? ` (${r.cls})` : ""}`);
    L.push("", fence("html", p.html), "");
  }
  const rest = items.filter((p) => !shown.includes(p));
  if (rest.length) {
    L.push("## Остальное", "", "Редкие варианты и помеченные как шум — только для справки, в новом коде не повторяй.", "");
    for (const p of rest.slice(0, 60)) L.push(`- \`${p.id}\` ${STATUS[p.status]} · ${p.n}× · ${p.text ? `«${p.text}» · ` : ""}\`${p.sig}\``);
    L.push("");
  }
  return L.join("\n");
}

function componentsMd(items, outlines, kind) {
  const title = kind === "modal" ? "Модалки, меню, поповеры" : "Компоненты";
  const L = [MARK, `# ${title}`, "", "Выбраны при съёмке (план): то, что агент-съёмщик счёл значимыми блоками интерфейса. Схема — сжатая разметка; полный HTML и скриншот — в `reference/`.", ""];
  const byBase = new Map();
  for (const it of items) if (!byBase.has(it.baseId) || it.viewport === it.primary) byBase.set(it.baseId, it);
  const groups = new Map();
  for (const it of byBase.values()) { const g = it.group || "misc"; if (!groups.has(g)) groups.set(g, []); groups.get(g).push(it); }
  for (const [g, list] of [...groups].sort()) {
    L.push(`## ${g}`, "");
    for (const it of list) {
      L.push(`### ${it.title} \`${it.baseId}\``, "",
        `- снят на: \`${it.pagePath}\`, селектор \`${it.selector}\`${it.size ? `, ${it.size.width}×${it.size.height}` : ""}`,
        `- эталон: [html](../reference/${it.file})${it.screenshot ? ` · [скриншот](../reference/${it.screenshot})` : ""}`);
      if (it.steps) L.push(`- как открыть: ${it.steps.map((s) => "`" + JSON.stringify(s) + "`").join(" → ")}`);
      if (it.notes) L.push(`- ${it.notes}`);
      L.push("");
      const o = outlines[it.id];
      if (o) L.push(fence("html", o), "");
    }
  }
  return L.join("\n");
}

const compName = (section) => (section ? section.replace(/\//g, "--") : "home");

function compositionMd(section, pages, states, outlines) {
  const main = pages[0];
  const L = [MARK, `# ${main ? main.title : section} — \`${main ? main.pagePath : "/" + section}\``, ""];
  if (main) L.push(`Источник: ${main.sourceUrl}. Эталон: [html](../reference/${main.file})${main.screenshot ? ` · [скриншот](../reference/${main.screenshot})` : ""}.`, "");
  L.push("Схема — сжатая разметка страницы: svg без путей, длинный текст обрезан, повторы свёрнуты, общие компоненты — ссылками на `parts/`.", "");
  if (states.length) {
    L.push("## Состояния", "");
    for (const s of states) L.push(`- **${s.title}** \`${s.baseId}\`: ${(s.steps || []).map((x) => "`" + JSON.stringify(x) + "`").join(" → ")} — [html](../reference/${s.file})${s.screenshot ? ` · [скриншот](../reference/${s.screenshot})` : ""}`);
    L.push("");
  }
  if (main && outlines[main.id]) L.push("## Схема страницы", "", fence("html", outlines[main.id]), "");
  return L.join("\n");
}

// ---------- source.md: где дизайн задан в коде ----------
function sourceMd(S, K, srcRefs, link, siteVars) {
  const L = [MARK, "# Дизайн в исходниках", "",
    `Просканировано: ${S.roots.map((r) => "`" + link(r) + "`").join(", ")} — ${S.files} файлов${S.truncated ? " (лимит, часть пропущена)" : ""}.`,
    "Браузер (`foundations.md`, `parts/`) показывает, **что видит пользователь**; этот файл — **где это задано в коде** и что переиспользовать.",
    "В новом коде бери существующие переменные, темы, варианты и компоненты отсюда, а не литералы из вычисленных стилей.", ""];
  const cat = { framework: "Фреймворк", styling: "Стили", ui: "UI-библиотеки", variants: "Варианты классов", motion: "Анимации", icons: "Иконки", fonts: "Шрифты" };
  L.push("## Стек", "");
  const st = Object.entries(cat).filter(([k]) => S.stack[k]);
  // много пакетов одного scope (@radix-ui/react-*) — одной строкой
  const pk = (o) => {
    const by = new Map();
    for (const [n, v] of Object.entries(o)) { const sc = n.startsWith("@") ? n.split("/")[0] : n; if (!by.has(sc)) by.set(sc, []); by.get(sc).push([n, v]); }
    return [...by].flatMap(([sc, l]) => (l.length > 3 ? [`\`${sc}/*\` (${l.length}: ${l.map(([n]) => n.split("/")[1]).slice(0, 12).join(", ")}${l.length > 12 ? "…" : ""})`] : l.map(([n, v]) => `\`${n}\`${v ? " " + v : ""}`)));
  };
  if (st.length) for (const [k, t] of st) L.push(`- **${t}:** ${pk(S.stack[k]).join(", ")}`);
  else L.push(S.packages && S.packages.length ? `- В ${S.packages.map((p) => "`" + link(p) + "`").join(", ")} нет дизайн-библиотек: вёрстка на чистых HTML/CSS/JS.` : "- package.json не найден (ни в `src`, ни выше до корня репозитория).");
  if (S.configs.length) L.push("", "Конфиги: " + S.configs.map((c) => `[\`${link(c.file)}\`](${link(c.file, "")})`).join(", "));
  L.push("");

  // токены
  const byFile = new Map();
  for (const v of S.cssVars) { if (!byFile.has(v.file)) byFile.set(v.file, []); byFile.get(v.file).push(v); }
  L.push("## Токены: CSS-переменные", "");
  if (!S.cssVars.length) L.push(siteVars && siteVars.size ? `В просканированных исходниках CSS-переменных нет, а на сайте их ${siteVars.size} (\`assets/tokens.css\`): стили лежат вне \`src\` — добавь их папку в \`src\` плана (для статики без сборки — папку со стилями сайта) и пересобери.` : "В исходниках CSS-переменных нет.", "");
  else {
    const used = siteVars || new Set();
    L.push(`Определений: ${S.cssVars.length} в ${byFile.size} файлах. «На сайте» — переменная есть среди вычисленных на снятых страницах.`, "");
    let shown = 0;
    for (const [f, list] of [...byFile].sort((a, b) => b[1].length - a[1].length).slice(0, 12)) {
      L.push(`### [\`${link(f)}\`](${link(f, "")}) — ${list.length}`, "", "| Переменная | Значение | Контекст | На сайте | Строка |", "|---|---|---|---|---|");
      for (const v of list.slice(0, 50)) L.push(`| \`${v.name}\` | \`${v.value.replace(/\|/g, "\\|")}\` | ${v.scope ? "`" + v.scope.replace(/\|/g, "\\|") + "`" : ""} | ${used.has(v.name) ? "да" : ""} | ${v.line} |`);
      if (list.length > 50) L.push(`| …ещё ${list.length - 50} | | | | |`);
      L.push("");
      if ((shown += list.length) > 400) break;
    }
  }
  if (S.preVars.length) {
    L.push("## Токены: переменные препроцессора (SCSS / LESS)", "");
    for (const v of S.preVars.slice(0, 80)) L.push(`- \`${v.name}: ${v.value}\` — ${link(v.file)}:${v.line}`);
    if (S.preVars.length > 80) L.push(`- …ещё ${S.preVars.length - 80}`);
    L.push("");
  }
  if (S.themes.length) {
    L.push("## Темы и конфиги дизайна", "");
    for (const t of S.themes.slice(0, 6)) L.push(`### ${t.kind} — [${link(t.file)}:${t.line}](${link(t.file, "")})`, "", fence(/\.json$/.test(t.file) ? "json" : /\.css$/.test(t.file) ? "css" : "js", t.excerpt), "");
    if (S.themes.length > 6) L.push(`Ещё: ${S.themes.slice(6, 30).map((t) => `${link(t.file)}:${t.line}`).join(", ")}`, "");
  }
  if (S.variants.length) {
    L.push("## Варианты компонентов в коде", "", "Определения вариантов (cva, tailwind-variants, styled, рецепты). Новый вариант кнопки — сюда, а не новым набором классов.", "");
    for (const v of S.variants.slice(0, 80)) L.push(`- ${v.kind} \`${v.name || "—"}\` — [${link(v.file)}:${v.line}](${link(v.file, "")})`);
    if (S.variants.length > 80) L.push(`- …ещё ${S.variants.length - 80}`);
    L.push("");
  }
  const comps = S.components;
  if (comps.length) {
    L.push("## Компоненты", "", "Экспортируемые компоненты по папкам. Папки вида `ui/`, `components/ui`, `design-system` — обычно библиотека примитивов: переиспользуй.", "");
    const byDir = new Map();
    for (const c of comps) { const d = posix.dirname(link(c.file)); if (!byDir.has(d)) byDir.set(d, []); byDir.get(d).push(c); }
    const isUi = (d) => /(^|\/)(ui|primitives|design-system|ds|kit|base|atoms|elements|shared\/ui)(\/|$)/i.test(d);
    for (const [d, list] of [...byDir].sort((a, b) => (isUi(b[0]) - isUi(a[0])) || a[0].localeCompare(b[0])).slice(0, 40))
      L.push(`- \`${d}/\`${isUi(d) ? " **(примитивы)**" : ""}: ${list.slice(0, 30).map((c) => c.name).join(", ")}${list.length > 30 ? ` …+${list.length - 30}` : ""}`);
    if (byDir.size > 40) L.push(`- …ещё ${byDir.size - 40} папок`);
    L.push("");
  }
  L.push("## Движение в коде", "");
  if (S.keyframes.length) L.push(`- **@keyframes / keyframes:** ${S.keyframes.slice(0, 40).map((k) => `\`${k.name}\` (${link(k.file)}:${k.line})`).join(", ")}`);
  for (const [lib, fl] of Object.entries(S.motion)) L.push(`- **${lib}:** ${fl.length}${fl.length >= 20 ? "+" : ""} файлов — ${fl.slice(0, 6).map((f) => "`" + link(f) + "`").join(", ")}`);
  if (!S.keyframes.length && !Object.keys(S.motion).length) L.push("- Анимаций в коде не найдено.");
  L.push("");
  L.push("## Иконки и шрифты в коде", "");
  for (const [lib, v] of Object.entries(S.icons)) L.push(`- **${lib}** (${v.files} файлов): ${v.names.slice(0, 40).join(", ") || "—"}`);
  for (const f of S.fonts.slice(0, 20)) L.push(`- шрифт ${f.kind}: ${f.what || "—"} — ${link(f.file)}:${f.line}`);
  if (!Object.keys(S.icons).length && !S.fonts.length) L.push("- Иконочных библиотек и подключения шрифтов в коде не найдено (иконки и шрифты с сайта — в `assets/`).");
  L.push("");
  if (S.duplicates && S.duplicates.length) L.push("## Копии файлов", "", "Одинаковые по содержимому — учтены один раз (обычно исходник и его копия в сборке):", "", ...S.duplicates.slice(0, 20).map(([a, b]) => `- \`${link(a)}\` = \`${link(b)}\``), "");
  const total = Object.values(K.parts).reduce((a, l) => a + l.length, 0);
  L.push("## Детали сайта → исходники", "", `Привязано ${Object.keys(srcRefs).length} из ${total} найденных вариантов (по CSS-модулям, классам из CSS проекта и строкам классов в коде).`,
    "Ссылки — в `parts/*.md`, строка «исходник». Нет ссылки — разметка собирается динамически или классы сгенерированы; ищи по тексту или стилю.", "");
  return L.join("\n");
}

function guideMd(doc, K, noise, files, plan) {
  const stance = plan.stance;
  const st = stance === "preserve" ? "**Повторять как есть.** Решение владельца: новый элемент делай как ближайший существующий вариант, даже если он неидеален. Не «улучшай» дизайн попутно."
    : stance === "normalize" ? "**Приводить к канону.** Новое делай только из вариантов со статусом «канон» в `parts/`; остальное — легаси или шум, его не размножай."
      : "Не задана. Спроси владельца проекта: повторять как есть или приводить к канону (поле `stance` в плане). Пока — бери самые частые варианты.";
  const L = [MARK, "# Дизайн-контекст проекта — гайд для агента", "",
    `Источник: ${doc.source} · собрано ${String(doc.createdAt).slice(0, 10)} · ${K.pages.length} страниц и состояний.`,
    "Это не копия сайта, а материал для сборки: основы, детали с вариантами, схемы разделов и ассеты, извлечённые из того, что реально отрисовывает браузер.", "",
    "## Позиция проекта", "", st, "",
    "## Какие вопросы решает", "",
    "- Какие цвета, шрифты, размеры, отступы, радиусы, тени и анимации здесь приняты — и как они называются в CSS?",
    "- Как выглядит и свёрстана кнопка, поле, ссылка, бейдж, карточка; какие варианты считаются нормой?",
    "- Как устроен конкретный раздел или страница: какие блоки, в каком порядке, из каких деталей?",
    "- Как выглядят модалки, меню, состояния; как их открыть?",
    "- Где взять шрифты, иконки, логотипы, CSS-переменные файлами?", "",
    "## Задача → что открыть", "",
    "Грузи только нужное: каждый файл самодостаточен.", "",
    "| Задача | Файл |", "|---|---|",
    "| Цвета, типографика, отступы, движение | [`foundations.md`](foundations.md) |",
    "| Нужна кнопка, поле, ссылка, бейдж, карточка | `parts/<группа>.md` — сначала «канон» |",
    "| Нужен готовый блок: шапка, футер, форма, секция | [`parts/components.md`](parts/components.md) |",
    "| Модалка, меню, поповер | [`parts/overlays.md`](parts/overlays.md) |",
    "| Доработка раздела `/x/y` | `compositions/x--y.md` (схема страницы) + детали из `parts/` |",
    "| Новая страница или раздел | схема похожего раздела + `foundations.md` + канон из `parts/` |",
    "| Шрифты, иконки, логотипы, CSS-переменные | `assets/` |",
    ...(files.source ? ["| Где это в коде: токены, темы, варианты, компоненты; что переиспользовать | [`source.md`](source.md) |"] : []),
    "| Проверить вёрстку против того, что было | `reference/` (полные HTML и скриншоты) + `verify.mjs` |", "",
    "## Указатель", "",
    "### Детали", "",
    ...files.parts.map((f) => `- [\`${f.file}\`](${f.file}) — ${f.title}${f.stats ? ` (${f.stats})` : ""}`), "",
    "### Разделы", "",
    ...files.compositions.map((f) => `- [\`${f.file}\`](${f.file}) — \`${f.path}\` ${f.title}${f.states ? ` · состояний: ${f.states}` : ""}`), "",
    "### Ассеты", "",
    `- \`assets/fonts/\` — ${files.fonts} файлов; \`assets/icons/\` — ${files.icons} svg; \`assets/logos/\` — ${files.logos}; \`assets/tokens.css\` — ${K.cssVars} CSS-переменных.`, "",
    "## Как устроено", "",
    "- Значения взяты из вычисленных стилей видимых элементов: это то, что видит пользователь.",
    files.source ? "- Исходники просканированы (`source.md`): где заданы токены и варианты, какой файл рисует деталь (строка «исходник» в `parts/`). В новом коде — существующие переменные и компоненты, не литералы." : "- Исходники не сканировались (нет `src` в плане): связи «деталь → файл» нет.",
    "- Детали сгруппированы по визуальной подписи (фон, цвет, граница, радиус, шрифт, отступы). Статусы «канон / вариант / шум» ставит человек или агент при разборе — в плане (`parts`).",
    "- Фото и видео контента не скачиваются: в эталоне это заглушки тех же пропорций.",
    "- `reference/` — эталон для сверки, читать его целиком не нужно. Файлы сгенерированы, руками не правь — пересними.", "",
    "## Обновление", "",
    `План: \`${doc.plan}\` (путь от этой папки).`, "", "```bash",
    `node <скилл wd-scan>/scripts/capture.mjs ${doc.plan}             # переснять`,
    `node <скилл wd-scan>/scripts/capture.mjs ${doc.plan} --only <id> # отдельные элементы`,
    `node <скилл wd-scan>/scripts/capture.mjs ${doc.plan} --rebuild   # только пересобрать слой после правки статусов`,
    "node <скилл wd-scan>/scripts/verify.mjs .                        # сверка эталона", "```", ""];
  return L.join("\n");
}

function galleryHtml(K, labels) {
  const card = (p) => {
    const l = labels[p.id] || {};
    return `<div class="p ${l.status || "unreviewed"}">${p.crop ? `<img src="${esc(p.crop)}">` : "<i>нет вырезки</i>"}<div class="m"><b>${esc(l.name || p.text || p.id)}</b> <code>${p.id}</code><br>${STATUS[l.status || "unreviewed"]} · ${p.n}× на ${p.pages.length} стр. · ${p.w}×${p.h}</div><code class="s">${esc(p.sig)}</code></div>`;
  };
  return `<!doctype html><meta charset="utf-8"><title>Разбор деталей</title><style>
body{font:13px/1.4 system-ui;margin:24px;color:#111}h2{margin:32px 0 8px;border-top:1px solid #ddd;padding-top:16px}.row{display:flex;flex-wrap:wrap;gap:10px}
.p{border:1px solid #e5e5e5;border-radius:8px;padding:8px;width:300px}.p img{max-width:284px;max-height:160px;display:block;background:repeating-conic-gradient(#eee 0 25%,#fff 0 50%) 0 0/12px 12px}
.p code{font:10px monospace;color:#666}.s{display:block;margin-top:4px;word-break:break-all}.canon{border-color:#16a34a;border-width:2px}.noise{opacity:.45}.variant{border-color:#0ea5e9}
.ic{display:grid;place-items:center;width:44px;height:44px;border:1px solid #eee;border-radius:6px}.ic svg{max-width:28px;max-height:28px}
</style><h1>Разбор деталей</h1><p>Статусы и имена задаются в плане: <code>"parts": { "&lt;id&gt;": { "status": "canon|variant|noise", "name": "…" } }</code>, затем <code>capture.mjs plan.json --rebuild</code>.</p>
${Object.entries(K.parts).map(([g, l]) => `<h2>${GROUPS[g] || g}: ${l.length}</h2><div class="row">${l.slice(0, 80).map(card).join("")}</div>`).join("")}
<h2>Иконки: ${K.icons.length}</h2><div class="row">${K.icons.slice(0, 120).map((i) => `<div class="ic" title="${i.n}× ${esc(i.label)}">${i.svg}</div>`).join("")}</div>`;
}

// ---------- главная функция ----------
export function buildContext({ OUT, REF, CACHE, doc, plan, log, tokensCss, source }) {
  const generated = new Set();
  const extracts = existsSync(join(CACHE, "extract")) ? readdirSync(join(CACHE, "extract")).filter((f) => f.endsWith(".json")).map((f) => JSON.parse(readFileSync(join(CACHE, "extract", f), "utf8"))) : [];
  const outlines = {};
  if (existsSync(join(CACHE, "outline"))) for (const f of readdirSync(join(CACHE, "outline"))) outlines[f.replace(/\.txt$/, "")] = readFileSync(join(CACHE, "outline", f), "utf8");
  const K = mergeExtracts(extracts);
  const labels = plan.parts || {};
  const noise = { "цвета текста": cover(K.colors.text || []), "фоны": cover(K.colors.background || []), "типографика": cover(K.type), ...Object.fromEntries(Object.entries(K.parts).map(([g, l]) => [GROUPS[g] || g, cover(l)])) };
  // предупреждения съёмки: текущего прогона и прошлого полного (при --rebuild/--only текущий лог неполный)
  let prevWarn = [];
  try { prevWarn = JSON.parse(readFileSync(join(REF, "capture-log.json"), "utf8")).warnings || []; } catch {}
  writeIf(OUT, "foundations.md", foundationsMd(K, noise, [...new Set([...(log ? log.warnings : []), ...prevWarn])]), generated);
  writeFileSync(join(REF, "kit.json"), JSON.stringify(K, null, 1));

  const files = { parts: [], compositions: [], fonts: 0, icons: 0, logos: 0, source: !!source };
  // ссылки на исходники: текст — от корня проекта, href — от файла слоя (sub — его подпапка)
  const link = (f, sub) => { const r = relative(sub === undefined ? join(OUT, "..") : join(OUT, sub), f).split("\\").join("/"); return r; };
  const srcRefs = source ? matchParts(K.parts, source) : {};
  for (const [g, list] of Object.entries(K.parts)) {
    if (!list.length) continue;
    const rel = `parts/${g}.md`;
    writeIf(OUT, rel, partsMd(g, list, labels, plan.stance, srcRefs, link, K.fonts.slice(0, 2).map((f) => f.family.replace(/["']/g, "").split(",")[0].trim())), generated);
    const c = cover(list);
    const canon = list.filter((p) => (labels[p.id] || {}).status === "canon").length;
    files.parts.push({ file: rel, title: GROUPS[g] || g, stats: `вариантов: ${c.variants}, дают 80%: ${c.for80}${canon ? `, канон: ${canon}` : ""}` });
  }
  const primary = doc.primaryViewport;
  const withPrimary = (it) => ({ ...it, primary });
  const comps = doc.items.filter((i) => i.kind === "component").map(withPrimary);
  const modals = doc.items.filter((i) => i.kind === "modal").map(withPrimary);
  if (comps.length) { writeIf(OUT, "parts/components.md", componentsMd(comps, outlines, "component"), generated); files.parts.push({ file: "parts/components.md", title: "Компоненты из плана", stats: `${new Set(comps.map((c) => c.baseId)).size}` }); }
  if (modals.length) { writeIf(OUT, "parts/overlays.md", componentsMd(modals, outlines, "modal"), generated); files.parts.push({ file: "parts/overlays.md", title: "Модалки и меню из плана", stats: `${new Set(modals.map((c) => c.baseId)).size}` }); }

  const sections = new Map();
  for (const it of doc.items) {
    if (it.kind !== "page" && it.kind !== "state") continue;
    if (it.viewport !== primary) continue;
    if (!sections.has(it.section)) sections.set(it.section, { pages: [], states: [] });
    sections.get(it.section)[it.kind === "page" ? "pages" : "states"].push(it);
  }
  for (const [section, s] of [...sections].sort((a, b) => a[0].localeCompare(b[0]))) {
    const rel = `compositions/${compName(section)}.md`;
    writeIf(OUT, rel, compositionMd(section, s.pages, s.states, outlines), generated);
    const main = s.pages[0];
    files.compositions.push({ file: rel, path: main ? main.pagePath : "/" + section, title: main ? main.title : "", states: s.states.length });
  }

  // ассеты
  const blobs = join(CACHE, "blobs");
  if (existsSync(blobs)) for (const f of readdirSync(blobs)) if (/\.(woff2?|ttf|otf)$/.test(f)) { ensureDir(join(OUT, "assets/fonts")); copyFileSync(join(blobs, f), join(OUT, "assets/fonts", f)); generated.add("assets/fonts/" + f); files.fonts++; }
  for (const ic of K.icons) {
    const name = `assets/icons/${(ic.label || "icon").toLowerCase().replace(/[^a-z0-9а-яё]+/gi, "-").replace(/^-|-$/g, "").slice(0, 30) || "icon"}-${ic.id}.svg`;
    writeIf(OUT, name, ic.svg, generated); files.icons++;
  }
  K.logos.forEach((l, i) => {
    if (l.svg) { writeIf(OUT, `assets/logos/logo-${i + 1}.svg`, l.svg, generated); files.logos++; }
    else if (l.blob && existsSync(join(blobs, l.blob))) { ensureDir(join(OUT, "assets/logos")); copyFileSync(join(blobs, l.blob), join(OUT, "assets/logos", l.blob)); generated.add("assets/logos/" + l.blob); files.logos++; }
  });
  if (tokensCss) writeIf(OUT, "assets/tokens.css", tokensCss, generated);
  if (source) {
    const tf = join(REF, "tokens.json");
    const siteVars = new Set(existsSync(tf) ? Object.keys(JSON.parse(readFileSync(tf, "utf8")).cssVariables || {}).map((k) => k.split(" @ ")[0]) : []);
    writeIf(OUT, "source.md", sourceMd(source, K, srcRefs, link, siteVars), generated);
    files.linked = Object.keys(srcRefs).length;
    writeFileSync(join(REF, "parts-source.json"), JSON.stringify(Object.fromEntries(Object.entries(srcRefs).map(([id, rs]) => [id, rs.map((r) => ({ ...r, file: link(r.file) }))])), null, 1));
  }

  writeFileSync(join(REF, "parts.html"), galleryHtml({ ...K, parts: Object.fromEntries(Object.entries(K.parts).map(([g, l]) => [g, l.map((p) => ({ ...p, crop: p.crop && posix.relative(".", p.crop) }))])) }, labels));
  writeIf(OUT, "GUIDE.md", guideMd(doc, K, noise, files, plan), generated);

  // уборка: файлы слоя прошлой сборки, которых больше нет
  for (const f of doc.contextGenerated || []) {
    if (generated.has(f)) continue;
    const full = join(OUT, f);
    if (!existsSync(full)) continue;
    if (f.endsWith(".md") && !isGenerated(readFileSync(full, "utf8"))) continue;
    unlinkSync(full);
  }
  doc.contextGenerated = [...generated].sort();
  doc.stats = { pages: K.pages.length, noise, parts: Object.fromEntries(Object.entries(K.parts).map(([g, l]) => [g, l.length])), icons: K.icons.length, fonts: files.fonts };
  return { K, files, noise };
}
