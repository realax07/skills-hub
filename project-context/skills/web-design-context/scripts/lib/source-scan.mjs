// Дизайн из исходников: где в коде заданы токены, темы, варианты компонентов, анимации, иконки и шрифты,
// и какой файл рисует найденную на сайте деталь. Дополняет то, что извлекает браузер: браузер говорит «что видно»,
// код — «где это задано и что переиспользовать». Только чтение файлов, без сборки и без зависимостей.
//
//   scanDesignSource(["/abs/src"]) → { roots, files, stack, configs, cssVars, preVars, themes, variants, keyframes,
//                                      motion, icons, fonts, components, _index }   (_index — для matchParts, в JSON не пишется)
//   matchParts(K.parts, scan)      → { <id детали>: [{ file, line, how, cls }] }
import { readFileSync, readdirSync, statSync, existsSync } from "node:fs";
import { join, relative, extname, basename, dirname, resolve } from "node:path";
import { createHash } from "node:crypto";

const SKIP = new Set(["node_modules", ".git", ".next", ".nuxt", ".svelte-kit", ".output", ".cache", "coverage", ".turbo", "vendor", "dist", "build", "out", "public", "design-context", "storybook-static"]);
const CODE = new Set([".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx", ".mts", ".cts", ".vue", ".svelte", ".astro"]);
const STYLE = new Set([".css", ".scss", ".sass", ".less", ".styl", ".pcss", ".postcss"]);
const MARKUP = new Set([".html", ".htm", ".php", ".twig", ".liquid", ".hbs", ".handlebars", ".njk", ".erb", ".cshtml", ".razor", ".jinja", ".j2", ".ejs", ".pug", ".mdx"]);
const CONFIG_RE = /^(tailwind|postcss|panda|uno|windi|vite|next|nuxt|astro|svelte|stitches|theme|tokens|style-dictionary)\.config\.(js|cjs|mjs|ts|json)$|^components\.json$|^(design-)?tokens(\.[\w-]+)?\.json$|^[\w-]+\.tokens\.json$|^theme\.(js|ts|json)$/;

// Библиотеки, которые определяют дизайн: имя пакета → категория
const STACK = [
  ["framework", /^(react|next|vue|nuxt|svelte|@sveltejs\/kit|astro|@angular\/core|solid-js|preact|jquery|alpinejs|htmx\.org|@builder\.io\/qwik|lit|@remix-run\/react|gatsby)$/],
  ["styling", /^(tailwindcss|@tailwindcss\/[\w-]+|styled-components|@emotion\/(react|styled|css)|sass|less|stylus|@vanilla-extract\/css|@stitches\/react|@pandacss\/dev|unocss|bootstrap|bulma|foundation-sites|@linaria\/core|styled-jsx|daisyui)$/],
  ["ui", /^(@mui\/material|@material-ui\/core|antd|@chakra-ui\/react|@radix-ui\/[\w-]+|@headlessui\/(react|vue)|@mantine\/core|vuetify|element-plus|element-ui|primevue|primereact|@ark-ui\/[\w-]+|react-bootstrap|bootstrap-vue|quasar|naive-ui|@nextui-org\/react|@heroui\/react|@fluentui\/react[\w-]*|@carbon\/react|@blueprintjs\/core|semantic-ui-react|@shopify\/polaris|react-aria-components|@ariakit\/react|bits-ui|reka-ui|radix-vue|@kobalte\/core|@skeletonlabs\/skeleton|flowbite[\w-]*)$/],
  ["variants", /^(class-variance-authority|tailwind-variants|clsx|classnames|tailwind-merge|cva)$/],
  ["motion", /^(framer-motion|motion|gsap|@gsap\/[\w-]+|lottie-web|lottie-react|@lottiefiles\/[\w-]+|react-spring|@react-spring\/[\w-]+|animejs|three|@react-three\/fiber|swiper|aos|locomotive-scroll|lenis|@studio-freight\/lenis|@formkit\/auto-animate|@vueuse\/motion|popmotion|velocity-animate|rive-react|@rive-app\/[\w-]+)$/],
  ["icons", /^(lucide|lucide-react|lucide-vue-next|lucide-svelte|@heroicons\/[\w-]+|react-icons|@fortawesome\/[\w-]+|@tabler\/icons[\w-]*|@phosphor-icons\/[\w-]+|phosphor-react|@iconify\/[\w-]+|@mdi\/[\w-]+|bootstrap-icons|@radix-ui\/react-icons|feather-icons|react-feather|remixicon|@remixicon\/[\w-]+|ionicons|@primer\/octicons-react|@mui\/icons-material|@ant-design\/icons)$/],
  ["fonts", /^(@fontsource\/[\w-]+|@fontsource-variable\/[\w-]+|geist|typeface-[\w-]+)$/],
];

function walk(dir, out, limit) {
  let names;
  try { names = readdirSync(dir); } catch { return; }
  for (const name of names) {
    if (out.length >= limit) return;
    if (SKIP.has(name) || name.startsWith(".")) continue;
    const p = join(dir, name);
    let st;
    try { st = statSync(p); } catch { continue; }
    if (st.isDirectory()) walk(p, out, limit);
    else {
      const ext = extname(name).toLowerCase();
      if (/\.min\.\w+$/.test(name) || st.size > 1_500_000) continue;
      if (CODE.has(ext) || STYLE.has(ext) || MARKUP.has(ext) || CONFIG_RE.test(name)) out.push(p);
    }
  }
}

const lineAt = (text) => {
  const starts = [0];
  for (let i = 0; i < text.length; i++) if (text.charCodeAt(i) === 10) starts.push(i + 1);
  return (idx) => { let lo = 0, hi = starts.length - 1; while (lo < hi) { const m = (lo + hi + 1) >> 1; if (starts[m] <= idx) lo = m; else hi = m - 1; } return lo + 1; };
};
const excerpt = (text, line, n) => text.split("\n").slice(line - 1, line - 1 + n).join("\n");
// блок от строки с совпадением до парной закрывающей скобки, не длиннее n строк
function blockFrom(text, idx, n) {
  const open = text.indexOf("{", idx);
  if (open < 0) return text.slice(idx, idx + 400);
  let depth = 0, i = open;
  for (; i < text.length; i++) { const c = text[i]; if (c === "{") depth++; else if (c === "}" && --depth === 0) break; }
  const s = text.slice(text.lastIndexOf("\n", idx) + 1, i + 1).split("\n");
  return s.length > n ? [...s.slice(0, n), `… (ещё ${s.length - n} строк)`].join("\n") : s.join("\n");
}

const CLASS_TOKEN = /^[A-Za-z0-9_!\-:[\]/.%#@()&>=,*~+'"]+$/;
function classLiterals(text, push) {
  const re = /(["'`])((?:(?!\1)[^\n\\]){5,600})\1/g;
  for (const m of text.matchAll(re)) {
    const raw = m[2].replace(/\$\{[^}]*\}/g, " ");
    const toks = raw.trim().split(/\s+/);
    if (toks.length < 2 || toks.length > 80) continue;
    if (!toks.every((t) => CLASS_TOKEN.test(t))) continue;
    if (!toks.some((t) => /[-:]/.test(t))) continue;
    if (/^(https?:|\/|\.\/|@\w)/.test(toks[0])) continue;
    push(m.index, toks, false);
  }
  // class="…" / className="…" внутри HTML-строк и шаблонов (innerHTML, PHP, шаблонизаторы) — даже из одного класса
  for (const m of text.matchAll(/\bclass(?:Name)?\s*=\s*\\?["'`]([^"'`\n\\]{1,400})/g)) {
    const toks = m[1].replace(/\$\{[^}]*\}|\{\{[^}]*\}\}|<\?[\s\S]*?\?>/g, " ").trim().split(/\s+/).filter((t) => CLASS_TOKEN.test(t));
    if (toks.length) push(m.index, toks, true);
  }
}

function findPackages(roots) {
  // package.json в корнях и до 4 уровней вверх (монорепо: зависимости приложения и корня)
  const seen = new Set(), pkgs = [];
  for (const r of roots) {
    let d = r;
    for (let i = 0; i < 5; i++) {
      const f = join(d, "package.json");
      if (!seen.has(f) && existsSync(f)) {
        seen.add(f);
        try { pkgs.push({ file: f, json: JSON.parse(readFileSync(f, "utf8")) }); } catch {}
      }
      if (existsSync(join(d, ".git"))) break;
      const up = dirname(d);
      if (up === d) break;
      d = up;
    }
  }
  return pkgs;
}

export function scanDesignSource(rootsIn, opts = {}) {
  const roots = rootsIn.map((r) => resolve(r)).filter((r) => existsSync(r));
  const limit = opts.limit || 8000;
  const files = [];
  for (const r of roots) walk(r, files, limit);
  const pkgs = findPackages(roots);
  // конфиги дизайна часто лежат в корне приложения (рядом с package.json), а не в src
  for (const p of pkgs) {
    const d = dirname(p.file);
    try { for (const n of readdirSync(d)) if (CONFIG_RE.test(n) && !files.includes(join(d, n))) files.push(join(d, n)); } catch {}
  }

  const S = { roots, files: files.length, truncated: files.length >= limit, stack: {}, configs: [], cssVars: [], preVars: [], themes: [], variants: [], keyframes: [], motion: {}, icons: {}, fonts: [], components: [] };
  const idx = { selectors: new Map(), literals: [], tokenLits: new Map() };

  // стек по package.json
  for (const p of pkgs) {
    const deps = { ...(p.json.dependencies || {}), ...(p.json.devDependencies || {}), ...(p.json.peerDependencies || {}) };
    for (const [name, ver] of Object.entries(deps)) for (const [cat, re] of STACK) if (re.test(name)) (S.stack[cat] ||= {})[name] = String(ver);
  }
  S.packages = pkgs.map((p) => p.file);

  const seenContent = new Map(); // одинаковые файлы (src/app.js и его копия в assets/) — один раз
  S.duplicates = [];
  for (const f of files) {
    let text;
    try { text = readFileSync(f, "utf8"); } catch { continue; }
    const h = createHash("sha1").update(text).digest("hex");
    if (seenContent.has(h)) { S.duplicates.push([f, seenContent.get(h)]); continue; }
    seenContent.set(h, f);
    const ext = extname(f).toLowerCase(), name = basename(f);
    const at = lineAt(text);
    const isStyle = STYLE.has(ext) || ((ext === ".vue" || ext === ".svelte" || ext === ".astro" || MARKUP.has(ext)) && /<style/i.test(text));
    const isCode = CODE.has(ext);

    if (CONFIG_RE.test(name)) {
      S.configs.push({ file: f, kind: name.replace(/\.(js|cjs|mjs|ts|json)$/, "") });
      const ti = text.search(/\btheme\s*:|"theme"\s*:|\bextend\s*:|"colors"\s*:|\btokens\s*:/);
      if (ti >= 0) S.themes.push({ file: f, line: at(ti), kind: "конфиг " + name, excerpt: blockFrom(text, ti, 80) });
      else if (/\.json$/.test(name) && !/^components\.json$/.test(name)) S.themes.push({ file: f, line: 1, kind: "токены " + name, excerpt: excerpt(text, 1, 60) });
    }

    if (isStyle) {
      // CSS-переменные: определение, значение, селектор (контекст темы: :root, .dark, [data-theme=…])
      for (const m of text.matchAll(/(--[A-Za-z0-9_-]+)\s*:\s*([^;{}]+?)\s*(?:;|(?=}))/g)) {
        const ob = text.lastIndexOf("{", m.index);
        const prev = ob > 0 ? Math.max(text.lastIndexOf("}", ob), text.lastIndexOf(";", ob), text.lastIndexOf("{", ob - 1)) : -1;
        const sel = ob >= 0 ? text.slice(prev + 1, ob).trim().replace(/\s+/g, " ").slice(-80) : "";
        S.cssVars.push({ name: m[1], value: m[2].trim().slice(0, 120), scope: sel, file: f, line: at(m.index) });
      }
      for (const m of text.matchAll(/^[ \t]*([$@])([A-Za-z_][\w-]*)\s*:\s*([^;\n]+);/gm)) {
        if (m[1] === "@" && /^(media|import|include|use|forward|supports|font-face|keyframes|layer|tailwind|apply|theme|plugin|source|custom-variant|utility|variant|config)$/.test(m[2])) continue;
        S.preVars.push({ name: m[1] + m[2], value: m[3].trim().slice(0, 120), file: f, line: at(m.index) });
      }
      for (const m of text.matchAll(/@theme\b[^{]*\{/g)) S.themes.push({ file: f, line: at(m.index), kind: "tailwind @theme", excerpt: blockFrom(text, m.index, 80) });
      for (const m of text.matchAll(/@keyframes\s+([\w-]+)/g)) S.keyframes.push({ name: m[1], file: f, line: at(m.index) });
      for (const m of text.matchAll(/@font-face\s*\{[^}]*?font-family\s*:\s*([^;]+);/g)) S.fonts.push({ kind: "@font-face", what: m[1].trim().replace(/["']/g, ""), file: f, line: at(m.index) });
      for (const m of text.matchAll(/@import\s+(?:url\()?["']?([^"')]*fonts\.(?:googleapis|bunny)\.net[^"')]*)/g)) S.fonts.push({ kind: "веб-шрифт", what: m[1].slice(0, 120), file: f, line: at(m.index) });
      // селекторы классов → где определены (для привязки деталей)
      for (const m of text.matchAll(/([^{}]+)\{/g)) {
        // в SCSS перед вложенным селектором могут стоять объявления: берём хвост после последней «;»
        const cut = m[1].lastIndexOf(";") + 1;
        const sel = m[1].slice(cut);
        if (/^\s*@/.test(sel) || sel.length > 400 || !sel.trim()) continue;
        const ln = at(m.index + cut + sel.search(/\S/));
        for (const c of sel.matchAll(/\.(-?[A-Za-z_][\w-]*)/g)) if (!idx.selectors.has(c[1])) idx.selectors.set(c[1], { file: f, line: ln });
      }
    }

    if (isCode) {
      for (const m of text.matchAll(/\b(createTheme|extendTheme|createMuiTheme|createStitches|createGlobalTheme|createThemeContract|defineConfig|defineTokens|defineSemanticTokens|createSystem|definePreset)\s*\(/g)) {
        if (m[1] === "defineConfig" && !/tailwind|panda|uno|stitches|chakra/i.test(text.slice(0, 2000) + name)) continue;
        S.themes.push({ file: f, line: at(m.index), kind: m[1] + "()", excerpt: blockFrom(text, m.index, 60) });
      }
      for (const m of text.matchAll(/export\s+(?:const|let|var|default)\s+(theme|tokens|colors|palette|designTokens|lightTheme|darkTheme)\b/g)) S.themes.push({ file: f, line: at(m.index), kind: "объект " + m[1], excerpt: blockFrom(text, m.index, 60) });
      const constName = (i) => { const m = text.slice(Math.max(0, i - 120), i).match(/(?:const|let|var|export\s+const)\s+(\w+)\s*=\s*$/); return m ? m[1] : ""; };
      for (const m of text.matchAll(/\b(cva|tv)\s*\(/g)) S.variants.push({ kind: m[1] === "cva" ? "cva" : "tailwind-variants", name: constName(m.index), file: f, line: at(m.index) });
      for (const m of text.matchAll(/\bstyled(?:\.(\w+)|\(\s*(\w+))/g)) S.variants.push({ kind: "styled", name: constName(m.index) || m[1] || m[2], file: f, line: at(m.index) });
      for (const m of text.matchAll(/\b(?:recipe|sva|slotRecipe|defineRecipe|defineSlotRecipe|styleVariants)\s*\(/g)) S.variants.push({ kind: "recipe", name: constName(m.index), file: f, line: at(m.index) });
      for (const m of text.matchAll(/\bkeyframes\s*(?:`|\()/g)) S.keyframes.push({ name: constName(m.index) || "keyframes", file: f, line: at(m.index) });
      for (const m of text.matchAll(/(?:from\s+|import\s*\(\s*|require\s*\(\s*)["']([^"']+)["']/g)) {
        const mod = m[1];
        const root = mod.startsWith("@") ? mod.split("/").slice(0, 2).join("/") : mod.split("/")[0];
        if (STACK[4][1].test(root) || /^motion\/react$/.test(mod)) (S.motion[root] ||= new Set()).add(f);
        if (STACK[5][1].test(root) || /^react-icons\//.test(mod)) {
          const lib = /^react-icons\//.test(mod) || /^@heroicons\//.test(mod) ? mod : root;
          const names = (text.slice(Math.max(0, m.index - 600), m.index).match(/import\s*\{([^}]*)\}\s*$/) || [])[1];
          const I = (S.icons[lib] ||= { files: new Set(), names: new Map() });
          I.files.add(f);
          for (const n of (names || "").split(",").map((x) => x.trim().split(/\s+as\s+/)[0]).filter(Boolean)) I.names.set(n, (I.names.get(n) || 0) + 1);
        }
        if (/^next\/font\//.test(mod) || STACK[6][1].test(root)) {
          const names = (text.slice(Math.max(0, m.index - 300), m.index).match(/import\s*(?:\{([^}]*)\}|(\w+))\s*$/) || []);
          S.fonts.push({ kind: mod, what: (names[1] || names[2] || "").trim(), file: f, line: at(m.index) });
        }
      }
    }

    // компоненты: экспортируемые PascalCase-имена и однофайловые компоненты фреймворков
    if (isCode) {
      const seenHere = new Set();
      for (const m of text.matchAll(/export\s+(?:default\s+)?(?:async\s+)?(?:function|const|class|let)\s+([A-Z][A-Za-z0-9]+)/g)) {
        if (seenHere.has(m[1])) continue; seenHere.add(m[1]);
        S.components.push({ name: m[1], file: f, line: at(m.index) });
      }
      if (/\.(vue|svelte|astro)$/.test(ext) && /^[A-Z]/.test(name)) S.components.push({ name: name.replace(/\.\w+$/, ""), file: f, line: 1 });
    }
    if (isCode || MARKUP.has(ext)) {
      classLiterals(text, (i, toks, attr) => {
        const id = idx.literals.length;
        idx.literals.push({ file: f, line: at(i), toks, attr, near: text.slice(Math.max(0, i - 300), i + 600) });
        for (const t of new Set(toks)) { const a = idx.tokenLits.get(t); if (a) { if (a.length < 400) a.push(id); } else idx.tokenLits.set(t, [id]); }
      });
    }
  }
  S.motion = Object.fromEntries(Object.entries(S.motion).map(([k, v]) => [k, [...v].slice(0, 20)]));
  S.icons = Object.fromEntries(Object.entries(S.icons).map(([k, v]) => [k, { files: v.files.size, names: [...v.names].sort((a, b) => b[1] - a[1]).slice(0, 60).map(([n]) => n) }]));
  if (S.configs.some((c) => c.kind === "components")) (S.stack.ui ||= {})["shadcn/ui (components.json)"] = "";
  Object.defineProperty(S, "_index", { value: idx, enumerable: false });
  return S;
}

// Какой файл рисует деталь: CSS-модули (Button_primary__x1y2z → Button.module.css .primary), семантические классы
// (.btn-primary в CSS проекта) и строки классов в коде (Tailwind: className="…" с теми же утилитами).
export function matchParts(parts, S) {
  const idx = S && S._index;
  if (!idx) return {};
  const out = {};
  for (const list of Object.values(parts || {})) for (const p of list) {
    const cls = ((p.html || "").match(/^<[^>]*?\sclass="([^"]*)"/) || [])[1];
    if (!cls) continue;
    const C = [...new Set(cls.split(/\s+/).filter(Boolean))];
    const refs = [];
    for (const t of C) {
      const m = t.match(/^([A-Za-z][A-Za-z0-9]*)[_-]{1,2}([A-Za-z][\w-]*?)__[\w-]{5,}$/);
      if (!m) continue;
      for (const [sel, loc] of idx.selectors) if (sel === m[2] && basename(loc.file).startsWith(m[1] + ".module.")) { refs.push({ ...loc, how: "CSS-модуль", cls: `.${m[2]}` }); break; }
    }
    const sem = C.filter((t) => idx.selectors.has(t)).slice(0, 3);
    for (const t of sem) if (!refs.some((r) => r.cls === "." + t)) refs.push({ ...idx.selectors.get(t), how: "CSS", cls: "." + t });
    const hits = new Map();
    for (const t of C) for (const id of idx.tokenLits.get(t) || []) hits.set(id, (hits.get(id) || 0) + 1);
    const best = [...hits].map(([id, k]) => ({ L: idx.literals[id], k }))
      // строка классов похожа на деталь целиком — или целиком входит в неё (вариант cva поверх базовых классов)
      .filter(({ L, k }) => { const n = new Set(L.toks).size; return (k >= 2 && k / n >= 0.6 && k / C.length >= 0.5) || (k >= 3 && k === n) || (L.attr && k === n && k === C.length); })
      .sort((a, b) => b.k - a.k || a.L.toks.length - b.L.toks.length);
    const seen = new Set(refs.map((r) => r.file + ":" + r.line));
    // совпадение и по тексту рядом со строкой классов — надёжнее; только по классам — помечаем
    const txt = (p.text || "").trim();
    const withText = (L) => txt.length >= 2 && L.near.includes(txt);
    best.sort((a, b) => withText(b.L) - withText(a.L));
    for (const { L, k } of best) {
      const key = L.file + ":" + L.line;
      if (seen.has(key)) continue;
      seen.add(key);
      refs.push({ file: L.file, line: L.line, how: withText(L) ? "классы и текст в коде" : "те же классы в коде (возможно, другой экземпляр)", cls: `${k}/${C.length} классов` });
      if (refs.length >= 4) break;
    }
    if (refs.length) out[p.id] = refs.slice(0, 4);
  }
  return out;
}

// JSON-представление для кэша (пути — от корня проекта, чтобы кэш не зависел от машины)
export function toJson(S, base) {
  const rel = (f) => relative(base, f).split("\\").join("/");
  const fix = (a) => a.map((x) => ({ ...x, file: rel(x.file) }));
  return { ...S, roots: S.roots.map(rel), packages: (S.packages || []).map(rel), configs: fix(S.configs), cssVars: fix(S.cssVars), preVars: fix(S.preVars),
    themes: fix(S.themes), variants: fix(S.variants), keyframes: fix(S.keyframes), fonts: fix(S.fonts), components: fix(S.components),
    motion: Object.fromEntries(Object.entries(S.motion).map(([k, v]) => [k, v.map(rel)])) };
}
