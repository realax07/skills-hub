#!/usr/bin/env node
// Разведка сайта перед снимками: страницы, кандидаты в компоненты/модалки, подсказки из исходников.
//
//   node scripts/discover.mjs --url http://localhost:3000 --src ./src --out discovery.json
//   node scripts/discover.mjs --serve ./dist --out discovery.json      (только папка сборки)
//   node scripts/discover.mjs --src ./src --no-browser                 (только исходники)
//
// Флаги: --max-pages 40  --depth 3  --per-section 6  --storage-state auth.json  --include-query
// Результат (JSON): { baseUrl, pages:[{url,path,title,candidates}], sections:[{section,visited,skipped}], source:{routes, modals, components},
//                    design:{stack, configs, cssVars, themes, variants, …} — сводка дизайна в коде (подробно — source.md после capture) }
// Это сырьё для plan.json — агент выбирает из него, что снимать (см. references/plan-format.md).
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative, extname, dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { loadPlaywright, parseArgs, writeFile } from "./lib/runtime.mjs";
import { serveDir } from "./lib/serve.mjs";
import { scanDesignSource } from "./lib/source-scan.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const args = parseArgs(process.argv.slice(2), {
  url: {}, serve: {}, src: {}, out: { default: "discovery.json" },
  "max-pages": { type: "int", default: 40 }, "per-section": { type: "int", default: 6 }, depth: { type: "int", default: 3 },
  "storage-state": {}, "include-query": { type: "bool" }, "no-browser": { type: "bool" },
  help: { alias: "h", type: "bool" },
});
if (args.help || (!args.url && !args.serve && !args.src)) {
  console.log(readFileSync(fileURLToPath(import.meta.url), "utf8").split("\n").filter((l) => l.startsWith("//")).map((l) => l.slice(3)).join("\n"));
  process.exit(args.help ? 0 : 2);
}

// ---------- исходники ----------
const SRC_EXT = new Set([".html", ".htm", ".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx", ".vue", ".svelte", ".astro", ".php", ".twig", ".liquid", ".hbs", ".njk", ".erb", ".blade.php"]);
const SKIP = new Set(["node_modules", ".git", ".next", ".nuxt", ".svelte-kit", ".cache", "coverage", ".turbo", "vendor"]);
const PATTERNS = {
  modals: [
    /<(?:\w+\.)?(Modal|Dialog|Drawer|Sheet|Popover|Popup|Lightbox|Offcanvas|AlertDialog|Toast|Snackbar)\b/g,
    /role=["'](dialog|alertdialog)["']/g,
    /aria-modal=["']?true/g,
    /data-bs-toggle=["']modal["']|data-toggle=["']modal["']/g,
    /\.showModal\(|\$\([^)]*\)\.modal\(/g,
    /\b(open|show|toggle)[A-Z]\w*(Modal|Dialog|Drawer|Popup)\b/g,
    /class(?:Name)?=["'][^"']*\b(modal|dialog|drawer|popup|offcanvas|lightbox)\b/g,
  ],
  routes: [
    /<Route[^>]*\bpath=["']([^"']+)["']/g,
    /\bpath:\s*["'](\/[^"']*)["']/g,
    /router\.(?:get|route)\(\s*["'](\/[^"']*)["']/g,
    /href=["'](\/[a-z0-9\-/]*)["']/gi,
  ],
  components: [
    /export\s+(?:default\s+)?(?:function|const|class)\s+([A-Z]\w+)/g,
    /customElements\.define\(\s*["']([\w-]+)["']/g,
  ],
};

function walk(dir, files = [], limit = 6000) {
  for (const name of readdirSync(dir)) {
    if (files.length >= limit) break;
    if (SKIP.has(name) || name.startsWith(".")) continue;
    const p = join(dir, name);
    const st = statSync(p);
    if (st.isDirectory()) walk(p, files, limit);
    else if (SRC_EXT.has(extname(name)) && st.size < 3_000_000) files.push(p);
  }
  return files;
}

function scanSource(root) {
  const res = { root, files: 0, routes: {}, modals: [], components: {}, fileRoutes: [] };
  const files = walk(root);
  res.files = files.length;
  for (const f of files) {
    const rel = relative(root, f);
    // файловый роутинг: pages/ или app/ (Next, Nuxt, SvelteKit, Astro)
    const m = rel.match(/(?:^|\/)(pages|app|routes)\/(.+?)\.(jsx?|tsx?|vue|svelte|astro|html)$/);
    if (m && !/(^|\/)_|layout|loading|error|api\//.test(m[2])) res.fileRoutes.push("/" + m[2].replace(/(^|\/)(index|page|\+page)$/, "").replace(/\[([^\]]+)\]/g, ":$1"));
    let text;
    try { text = readFileSync(f, "utf8"); } catch { continue; }
    const lines = text.split("\n");
    const lineOf = (idx) => text.slice(0, idx).split("\n").length;
    for (const re of PATTERNS.modals) {
      for (const mm of text.matchAll(re)) {
        const ln = lineOf(mm.index);
        if (res.modals.length < 400) res.modals.push({ file: rel, line: ln, match: mm[0].slice(0, 80), context: (lines[ln - 1] || "").trim().slice(0, 160) });
      }
    }
    for (const re of PATTERNS.routes) for (const mm of text.matchAll(re)) res.routes[mm[1]] = (res.routes[mm[1]] || 0) + 1;
    for (const re of PATTERNS.components) for (const mm of text.matchAll(re)) (res.components[mm[1]] ||= []).push(rel);
  }
  res.routes = Object.entries(res.routes).sort((a, b) => b[1] - a[1]).slice(0, 200).map(([path, count]) => ({ path, count }));
  res.components = Object.entries(res.components).slice(0, 400).map(([name, files]) => ({ name, files: [...new Set(files)].slice(0, 3) }));
  res.fileRoutes = [...new Set(res.fileRoutes)];
  return res;
}

// ---------- браузер ----------
async function crawl(baseUrl) {
  const { chromium } = await loadPlaywright();
  const discoverSrc = readFileSync(join(HERE, "lib/page-discover.js"), "utf8");
  const browser = await chromium.launch();
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, storageState: args["storage-state"] });
  const page = await context.newPage();
  const origin = new URL(baseUrl).origin;
  const norm = (u) => {
    const x = new URL(u);
    x.hash = "";
    if (!args["include-query"]) x.search = "";
    return x.href.replace(/\/$/, "") || x.href;
  };
  const queue = [[norm(baseUrl), 0]];
  // sitemap.xml как дополнительный источник
  try {
    const r = await context.request.get(origin + "/sitemap.xml", { timeout: 5000 });
    if (r.ok()) for (const m of (await r.text()).matchAll(/<loc>\s*([^<\s]+)\s*<\/loc>/g)) if (m[1].startsWith(origin)) queue.push([norm(m[1]), 1]);
  } catch {}
  const seen = new Set();
  const pages = [];
  // Лимит на раздел: однотипные страницы (/docs/*, /blog/*) не съедают весь бюджет обхода,
  // и он доходит до других веток. Пропущенные учитываются в sections — агент видит объём раздела.
  const sections = new Map();
  // страницы верхнего уровня (/pricing, /blog) — разные разделы, лимит к ним не применяется
  const sectionOf = (u) => {
    const p = new URL(u).pathname.replace(/\/$/, "");
    return p.split("/").length <= 2 ? p || "/" : p.replace(/\/[^/]*$/, "");
  };
  while (queue.length && pages.length < args["max-pages"]) {
    const [url, d] = queue.shift();
    if (seen.has(url)) continue;
    seen.add(url);
    if (/\.(pdf|zip|png|jpe?g|gif|svg|webp|mp4|xml|json|txt)$/i.test(url)) continue;
    const sec = sectionOf(url);
    if (!sections.has(sec)) sections.set(sec, { section: sec, visited: 0, skipped: [] });
    const st = sections.get(sec);
    if (st.visited >= args["per-section"]) { st.skipped.push(new URL(url).pathname); continue; }
    st.visited++;
    try {
      const resp = await page.goto(url, { waitUntil: "load", timeout: 20000 });
      await page.waitForLoadState("networkidle", { timeout: 5000 }).catch(() => {});
      const info = await page.evaluate(`(${discoverSrc})()`);
      pages.push({ url, path: new URL(url).pathname, status: resp ? resp.status() : null, title: info.title, candidates: info.candidates });
      console.log(`  page ${pages.length}: ${new URL(url).pathname} (${info.candidates.length} кандидатов)`);
      if (d < args.depth) for (const l of info.links) if (l.startsWith(origin)) queue.push([norm(l), d + 1]);
    } catch (e) {
      pages.push({ url, path: new URL(url).pathname, error: String(e.message).split("\n")[0] });
    }
  }
  await browser.close();
  const summary = [...sections.values()].filter((x) => x.visited)
    .map((x) => ({ section: x.section, visited: x.visited, skipped: x.skipped.length, skippedSample: x.skipped.slice(0, 5) }))
    .sort((a, b) => a.section.localeCompare(b.section));
  for (const x of summary) if (x.skipped) console.log(`  раздел ${x.section}: снято ${x.visited}, пропущено однотипных ${x.skipped}`);
  return { pages, sections: summary };
}

async function main() {
  const result = { createdAt: new Date().toISOString() };
  let server;
  if (args.serve) {
    server = await serveDir(args.serve);
    result.baseUrl = server.url;
    result.servedDir = args.serve;
    console.log(`→ раздаю ${args.serve} на ${server.url}`);
  } else if (args.url) result.baseUrl = args.url;

  if (args.src) {
    console.log(`→ сканирую исходники ${args.src}`);
    result.source = scanSource(args.src);
    console.log(`  файлов: ${result.source.files}, модалок-подсказок: ${result.source.modals.length}, маршрутов: ${result.source.routes.length + result.source.fileRoutes.length}`);
    // дизайн в коде — коротко, чтобы решить, добавлять ли "src" в план (полный разбор сделает capture → source.md)
    const d = scanDesignSource([args.src]);
    result.design = { stack: d.stack, configs: d.configs.map((c) => relative(args.src, c.file)), cssVars: d.cssVars.length, preVars: d.preVars.length,
      themes: d.themes.length, variants: d.variants.length, keyframes: d.keyframes.length, components: d.components.length };
    const libs = Object.values(d.stack).flatMap((o) => Object.keys(o));
    console.log(`  дизайн в коде: ${libs.join(", ") || "библиотек не найдено"}; CSS-переменных ${d.cssVars.length}, тем/конфигов ${d.themes.length}, вариантов ${d.variants.length}`);
    console.log(`  → добавь в план "src" (путь от папки плана), чтобы capture собрал source.md и связал детали с файлами`);
    if (!d.cssVars.length && !d.preVars.length && !d.themes.length && !Object.keys(d.stack.styling || {}).length)
      console.log(`  ! в ${args.src} нет стилей (CSS, тем, Tailwind): если они в другой папке (для статики — папка со стилями сайта), добавь её в "src" массивом`);
  }
  if (result.baseUrl && !args["no-browser"]) {
    console.log(`→ обхожу ${result.baseUrl}`);
    Object.assign(result, await crawl(result.baseUrl));
  }
  // папка сборки: страницы, на которые нет ссылок, обход не найдёт — перечисляем *.html
  if (args.serve) {
    const found = new Set((result.pages || []).map((p) => p.path.replace(/\/$/, "").replace(/\.html$/, "").replace(/\/index$/, "") || "/"));
    const htmls = walk(resolve(args.serve)).filter((f) => /\.html?$/.test(f)).map((f) => "/" + relative(resolve(args.serve), f).split("\\").join("/"));
    result.unlinkedPages = htmls.filter((h) => !found.has(h.replace(/\.html?$/, "").replace(/\/index$/, "") || "/"));
    if (result.unlinkedPages.length) console.log(`  страниц без ссылок на них: ${result.unlinkedPages.length} — ${result.unlinkedPages.slice(0, 5).join(", ")} (discovery.json → unlinkedPages)`);
  }
  if (server) server.close();
  writeFile(args.out, JSON.stringify(result, null, 2));
  console.log(`Готово: ${args.out}`);
}

main().catch((e) => { console.error("error: " + e.message); process.exit(1); });
