// Каталог мокапов: index.html для человека и README.md для AI-агента.
import { writeFileSync } from "node:fs";
import { join } from "node:path";

const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);

export function buildCatalog(out, doc, tokens) {
  const items = doc.items || [];
  const groups = new Map();
  for (const it of items) {
    const key = it.kind === "page" ? "Страницы" : it.kind === "modal" ? `Модалки` : `Компоненты · ${it.group}`;
    (groups.get(key) || groups.set(key, []).get(key)).push(it);
  }
  const order = [...groups.keys()].sort((a, b) => rank(a) - rank(b) || a.localeCompare(b));
  function rank(k) { return k === "Страницы" ? 0 : k === "Модалки" ? 2 : 1; }

  const colors = [...(tokens.color || []), ...(tokens.background || [])]
    .reduce((acc, c) => (acc.find((x) => x.value === c.value) ? acc : [...acc, c]), []).slice(0, 40);
  const fonts = (tokens.fontFamily || []).slice(0, 6);
  const sizes = (tokens.fontSize || []).slice(0, 12).sort((a, b) => parseFloat(b.value) - parseFloat(a.value));
  const vars = Object.entries(tokens.cssVariables || {});

  const card = (it) => `
      <article class="card" id="${esc(it.id)}">
        <a class="thumb" href="${esc(it.file)}" target="_blank">${it.screenshot ? `<img loading="lazy" src="${esc(it.screenshot)}" alt="">` : `<span>нет скриншота</span>`}</a>
        <div class="meta">
          <a href="${esc(it.file)}" target="_blank"><b>${esc(it.title)}</b></a>
          <code>${esc(it.file)}</code>
          <small>${esc(it.viewport)}${it.size ? ` · ${it.size.width}×${it.size.height}` : ""}${it.selector ? ` · <code>${esc(it.selector)}</code>` : ""}</small>
          ${it.notes ? `<small>${esc(it.notes)}</small>` : ""}
        </div>
      </article>`;

  const html = `<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Мокапы · ${esc(doc.source)}</title>
<style>
  :root { --bg:#f6f6f4; --fg:#1b1b1a; --muted:#6b6b66; --line:#e2e2dc; --card:#fff; --accent:#3b5bdb; }
  @media (prefers-color-scheme: dark) { :root { --bg:#151514; --fg:#ededea; --muted:#9a9a93; --line:#2c2c2a; --card:#1d1d1c; --accent:#8ea2ff; } }
  * { box-sizing:border-box } body { margin:0; font:14px/1.5 system-ui,-apple-system,sans-serif; background:var(--bg); color:var(--fg) }
  header { padding:24px 24px 8px } h1 { margin:0 0 4px; font-size:20px } header p { margin:0; color:var(--muted) }
  nav { position:sticky; top:0; background:var(--bg); padding:8px 24px; border-bottom:1px solid var(--line); display:flex; gap:12px; flex-wrap:wrap; z-index:1 }
  nav a { color:var(--accent); text-decoration:none } section { padding:16px 24px } h2 { font-size:16px; margin:8px 0 12px }
  .grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(260px,1fr)); gap:16px }
  .card { background:var(--card); border:1px solid var(--line); border-radius:10px; overflow:hidden; display:flex; flex-direction:column }
  .thumb { display:flex; align-items:flex-start; justify-content:center; height:180px; overflow:hidden; padding:8px; background:repeating-conic-gradient(var(--line) 0 25%, transparent 0 50%) 0 0/16px 16px }
  .thumb img { max-width:100%; height:auto; object-fit:contain; object-position:top } .thumb span { margin:auto; color:var(--muted) }
  .meta { padding:10px 12px; display:flex; flex-direction:column; gap:2px; min-width:0 } .meta a { color:inherit; text-decoration:none }
  code { font:12px ui-monospace,monospace; color:var(--muted); overflow-wrap:anywhere } small { color:var(--muted) }
  .swatches { display:flex; flex-wrap:wrap; gap:8px } .sw { width:110px; font-size:11px } .sw i { display:block; height:40px; border-radius:6px; border:1px solid var(--line) }
  .type div { margin:4px 0 } table { border-collapse:collapse; font-size:12px } td { border-top:1px solid var(--line); padding:4px 12px 4px 0; vertical-align:top }
</style>
</head>
<body>
<header>
  <h1>Мокапы сайта</h1>
  <p>${esc(doc.source)} · ${items.length} снимков · ${esc(doc.createdAt)}</p>
</header>
<nav>${order.map((g) => `<a href="#g-${esc(g)}">${esc(g)} (${groups.get(g).length})</a>`).join("")}<a href="#tokens">Токены</a></nav>
${order.map((g) => `<section id="g-${esc(g)}"><h2>${esc(g)}</h2><div class="grid">${groups.get(g).map(card).join("")}</div></section>`).join("\n")}
<section id="tokens">
  <h2>Токены</h2>
  <h3>Цвета (по частоте)</h3>
  <div class="swatches">${colors.map((c) => `<div class="sw"><i style="background:${esc(c.value)}"></i><code>${esc(c.value)}</code> ×${c.count}</div>`).join("")}</div>
  <h3>Шрифты</h3>
  <div class="type">${fonts.map((f) => `<div style="font-family:${esc(f.value)}">Съешь же ещё этих мягких булок — <code>${esc(f.value)}</code> ×${f.count}</div>`).join("")}</div>
  <h3>Размеры текста</h3>
  <div class="type">${sizes.map((s) => `<div style="font-size:${esc(s.value)};line-height:1.2">${esc(s.value)} <small>×${s.count}</small></div>`).join("")}</div>
  ${vars.length ? `<h3>CSS-переменные</h3><table>${vars.slice(0, 300).map(([k, v]) => `<tr><td><code>${esc(k)}</code></td><td><code>${esc(v)}</code></td></tr>`).join("")}</table>` : ""}
</section>
</body>
</html>`;
  writeFileSync(join(out, "index.html"), html);

  const byKind = (k) => items.filter((i) => i.kind === k);
  const list = (arr) => arr.map((i) => `- \`${i.file}\` — ${i.title}${i.viewport !== Object.keys(doc.viewports || { d: 1 })[0] ? ` (${i.viewport})` : ""}${i.selector ? ` · \`${i.selector}\`` : ""}${i.notes ? ` — ${i.notes}` : ""}`).join("\n");
  const readme = `# Мокапы сайта

Источник: ${doc.source} · собрано: ${doc.createdAt} · генератор: site-mockups

Статические HTML-снимки реального сайта — для использования как контекст AI-агентами
при доработке, редизайне и создании новых страниц в том же стиле.

## Как пользоваться

- **Страницы** (\`pages/\`) — полная компоновка: порядок секций, сетка, отступы.
- **Компоненты** (\`components/<группа>/\`) — отдельные элементы. Каждый файл содержит сам элемент
  целиком и «скелет» его предков (без соседей), чтобы CSS-селекторы сайта работали как на странице.
  Корень компонента помечен атрибутом \`data-mockup-root\`.
- **Модалки и состояния** (\`modals/\`) — окна и элементы, которые появляются только после действия;
  нужные действия записаны в \`manifest.json\` → \`steps\`.
- **Стили** — \`assets/css/\` (реально применённые правила, включая CSS-in-JS), \`tokens.json\` / \`tokens.css\`
  (CSS-переменные и частотность цветов, шрифтов, размеров, радиусов, теней, отступов).
- **Скриншоты** — \`screenshots/\` повторяет структуру HTML-файлов.
- **Каталог для человека** — \`index.html\`. **Полный список для машины** — \`manifest.json\`.

Новые элементы делай на тех же классах и токенах. HTML здесь — результат рендера, а не исходник:
имена компонентов во фреймворке смотри в исходниках проекта.

## Страницы

${list(byKind("page")) || "—"}

## Компоненты

${list(byKind("component")) || "—"}

## Модалки и состояния

${list(byKind("modal")) || "—"}

## Пересъёмка

\`\`\`bash
node <skill>/scripts/capture.mjs plan.json            # всё
node <skill>/scripts/capture.mjs plan.json --only id  # отдельные элементы
\`\`\`
`;
  writeFileSync(join(out, "README.md"), readme);
}
