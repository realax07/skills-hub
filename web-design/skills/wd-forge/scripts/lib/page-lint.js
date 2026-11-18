// Выполняется ВНУТРИ страницы. Пол качества и «тела» шаблонного ИИ-дизайна на отрисованной странице.
// Правила — своими словами по мотивам Web Interface Guidelines (Vercel, MIT), frontend-design (Anthropic, Apache-2.0),
// Impeccable (Apache-2.0), taste-skill (MIT); см. references/sources.md.
//   opts: { mobile: bool, fonts: ["Fraunces", "Work Sans"] — шрифты направления }
// Возвращает { issues: [{ level: "error"|"warn", rule, what, n, ex }] , stats }
(opts) => {
  opts = opts || {};
  const issues = [];
  const add = (level, rule, what, n, ex) => issues.push({ level, rule, what, n: n || 1, ex: (ex || []).slice(0, 3) });
  const vis = (el) => { const r = el.getBoundingClientRect(); if (r.width < 1 || r.height < 1) return false; const s = getComputedStyle(el); return s.visibility !== "hidden" && s.display !== "none" && +s.opacity > 0.05; };
  const all = [...document.body.querySelectorAll("*")].filter((e) => !/^(SCRIPT|STYLE|NOSCRIPT|TEMPLATE|BR)$/.test(e.tagName));
  const visible = all.filter(vis);
  const label = (el) => { const t = (el.innerText || el.getAttribute("aria-label") || "").trim().replace(/\s+/g, " ").slice(0, 40); return `${el.tagName.toLowerCase()}${el.className && typeof el.className === "string" ? "." + el.className.trim().split(/\s+/)[0] : ""}${t ? ` «${t}»` : ""}`; };
  const cv = document.createElement("canvas").getContext("2d");
  const rgba = (c) => { cv.fillStyle = "#000"; cv.fillStyle = c; const v = cv.fillStyle; if (v.startsWith("#")) { const h = v.slice(1); return [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16)).concat(1); } const m = v.match(/[\d.]+/g); return m ? m.map(Number) : [0, 0, 0, 1]; };
  const lum = ([r, g, b]) => { const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; }; return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b); };
  const ratio = (a, b) => { const x = lum(a), y = lum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); };
  const over = (fg, bg) => [0, 1, 2].map((i) => fg[i] * fg[3] + bg[i] * (1 - fg[3])).concat(1);
  // фон под элементом: первый непрозрачный предок; картинка или градиент — «неизвестно»
  const bgOf = (el) => {
    let acc = null;
    for (let e = el; e; e = e.parentElement) {
      const s = getComputedStyle(e);
      if (s.backgroundImage && s.backgroundImage !== "none") return null;
      const c = rgba(s.backgroundColor);
      if (c[3] > 0) { acc = acc ? over(acc, c) : c; if (acc[3] >= 0.99 || c[3] >= 0.99) return over(acc, [255, 255, 255, 1]); }
    }
    return acc ? over(acc, [255, 255, 255, 1]) : [255, 255, 255, 1];
  };

  // ---- 1. горизонтальный скролл
  const sw = document.documentElement.scrollWidth;
  if (sw > innerWidth + 1) {
    const wide = visible.filter((e) => e.getBoundingClientRect().right > innerWidth + 1).sort((a, b) => b.getBoundingClientRect().right - a.getBoundingClientRect().right);
    add("error", "h-scroll", `горизонтальный скролл: ширина ${sw}px при окне ${innerWidth}px`, wide.length, wide.slice(0, 3).map(label));
  }

  // ---- 2. контраст текста (WCAG 2: 4.5, крупный — 3)
  const low = [];
  for (const el of visible) {
    const own = [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim());
    if (!own) continue;
    const s = getComputedStyle(el);
    const bg = bgOf(el);
    if (!bg) continue;
    const fg = over(rgba(s.color), bg);
    const size = parseFloat(s.fontSize), bold = +s.fontWeight >= 600;
    const need = size >= 24 || (size >= 18.66 && bold) ? 3 : 4.5;
    const r = ratio(fg, bg);
    if (r < need) low.push(`${label(el)} ${r.toFixed(2)} < ${need}`);
  }
  if (low.length) add("error", "contrast", "низкий контраст текста", low.length, low);

  // ---- 3. размер целей нажатия: ≥24px, на мобильном ≥44px (ссылки внутри текста не считаются)
  const minT = opts.mobile ? 44 : 24, small = [];
  for (const el of visible) {
    if (!el.matches("a[href],button,input:not([type=hidden]),select,textarea,[role=button],[role=tab],[role=menuitem]")) continue;
    const s = getComputedStyle(el);
    if (el.tagName === "A" && s.display === "inline" && el.parentElement && el.parentElement.closest("p,li,td,figcaption,blockquote")) continue;
    const r = el.getBoundingClientRect();
    if (Math.min(r.width, r.height) < minT - 0.5) small.push(`${label(el)} ${Math.round(r.width)}×${Math.round(r.height)}`);
  }
  if (small.length) add(opts.mobile ? "error" : "warn", "targets", `цели нажатия меньше ${minT}px`, small.length, small);

  // ---- 4. стили: фокус, reduced-motion, transition: all
  let focusRule = false, reduced = false, transAll = 0;
  const walk = (rules) => { for (const r of rules) {
    if (r.selectorText && /:focus(-visible)?/.test(r.selectorText)) focusRule = true;
    if (r.media && /prefers-reduced-motion/.test(r.media.mediaText)) reduced = true;
    if (r.style && /\ball\b/.test(r.style.transitionProperty || "") && parseFloat(r.style.transitionDuration || "0") > 0) transAll++;
    if (r.cssRules) walk(r.cssRules);
  } };
  for (const sh of document.styleSheets) { try { walk(sh.cssRules); } catch {} }
  if (!focusRule) add("error", "focus", "нет стиля :focus-visible — клавиатурный фокус не виден (подключи base.css)");
  const moving = visible.filter((e) => { const s = getComputedStyle(e); return (s.animationName && s.animationName !== "none") || parseFloat(s.transitionDuration) > 0; });
  if (moving.length && !reduced) add("error", "reduced-motion", "есть анимации, но нет @media (prefers-reduced-motion)", moving.length);
  if (transAll) add("warn", "transition-all", "transition: all — анимируй только нужные свойства (transform, opacity)", transAll);

  // ---- 5. картинки без размеров (сдвиг вёрстки)
  const noDim = [...document.images].filter((i) => vis(i) && !(i.getAttribute("width") && i.getAttribute("height")) && getComputedStyle(i).aspectRatio === "auto");
  if (noDim.length) add("warn", "img-size", "картинки без width/height или aspect-ratio", noDim.length, noDim.map((i) => i.getAttribute("src") || "img"));

  // ---- 6. «тела» шаблонного ИИ-дизайна
  const fam = (el) => getComputedStyle(el).fontFamily.split(",")[0].replace(/["']/g, "").trim();
  const DEFAULT = /^(Inter|Roboto|Arial|Helvetica|Helvetica Neue|system-ui|-apple-system|BlinkMacSystemFont|Segoe UI|sans-serif|serif|Times New Roman)$/i;
  const headings = visible.filter((e) => /^H[1-3]$/.test(e.tagName));
  const bodyFam = fam(document.body), headFam = headings[0] ? fam(headings[0]) : bodyFam;
  if (DEFAULT.test(bodyFam) || DEFAULT.test(headFam)) add("error", "default-font", `дефолтный шрифт основным: ${headFam} / ${bodyFam}`);
  if (opts.fonts && opts.fonts.length) {
    const want = opts.fonts.map((f) => f.toLowerCase());
    if (!want.includes(headFam.toLowerCase()) || !want.includes(bodyFam.toLowerCase())) add("error", "off-direction-font", `шрифты не из направления: ${headFam} / ${bodyFam}, ожидаются ${opts.fonts.join(" / ")}`);
    // загружено ли хоть одно начертание семейства (неиспользуемые начертания браузер не грузит — это нормально)
    const loaded = new Set([...(document.fonts || [])].filter((f) => f.status === "loaded").map((f) => f.family.replace(/["']/g, "").toLowerCase()));
    for (const f of opts.fonts) if (!loaded.has(f.toLowerCase())) add("warn", "font-not-loaded", `шрифт ${f} не загрузился (нет сети или ошибка в @import) — снимки будут с запасным`);
  }
  const hueOf = (c) => { const [r, g, b] = rgba(c).map((v, i) => (i < 3 ? v / 255 : v)); const mx = Math.max(r, g, b), mn = Math.min(r, g, b), d = mx - mn; if (d < 0.15) return null; let h = mx === r ? ((g - b) / d) % 6 : mx === g ? (b - r) / d + 2 : (r - g) / d + 4; return (h * 60 + 360) % 360; };
  let purple = 0;
  for (const el of visible) {
    const bi = getComputedStyle(el).backgroundImage;
    if (!/gradient/.test(bi)) continue;
    const hues = (bi.match(/rgba?\([^)]+\)|#[0-9a-f]{3,8}/gi) || []).map(hueOf).filter((x) => x !== null);
    if (hues.length >= 2 && hues.every((h) => h >= 220 && h <= 300)) purple++;
  }
  if (purple) add("error", "purple-gradient", "фиолетово-синий градиент — главный признак шаблонного SaaS", purple);
  const isCard = (e) => { const s = getComputedStyle(e); const box = s.boxShadow !== "none" || (parseFloat(s.borderTopWidth) > 0 && rgba(s.borderTopColor)[3] > 0); return box && parseFloat(s.borderTopLeftRadius) >= 6 && parseFloat(s.paddingTop) >= 12 && e.getBoundingClientRect().width >= 120; };
  const cards = visible.filter(isCard);
  const nested = cards.filter((c) => cards.some((o) => o !== c && o.contains(c)));
  if (nested.length) add("warn", "nested-cards", "карточка внутри карточки", nested.length, nested.map(label));
  const tiles = headings.concat(visible.filter((e) => e.tagName === "H4")).filter((h) => {
    const p = h.previousElementSibling; if (!p) return false;
    const r = p.getBoundingClientRect(), s = getComputedStyle(p);
    return r.width <= 72 && r.height <= 72 && Math.abs(r.width - r.height) < 8 && (rgba(s.backgroundColor)[3] > 0 || s.backgroundImage !== "none") && (p.querySelector("svg,img") || /\p{Extended_Pictographic}/u.test(p.textContent));
  });
  if (tiles.length >= 3) add("warn", "icon-tiles", "квадратная плитка с иконкой над каждым заголовком", tiles.length, tiles.map(label));
  const eyebrows = visible.filter((e) => { const s = getComputedStyle(e); return s.textTransform === "uppercase" && parseFloat(s.letterSpacing) >= 0.06 * parseFloat(s.fontSize) && parseFloat(s.fontSize) <= 14 && (e.innerText || "").trim().length > 2; });
  if (eyebrows.length >= 3) add("warn", "eyebrows", "мелкие заглавные с разрядкой над заголовками (eyebrow) — шаблонный приём", eyebrows.length, eyebrows.map(label));
  const emoji = visible.filter((e) => /^(BUTTON|A|LI|H[1-6]|SPAN|DIV)$/.test(e.tagName) && [...e.childNodes].some((n) => n.nodeType === 3 && /\p{Extended_Pictographic}/u.test(n.textContent)));
  if (emoji.length >= 3) add("warn", "emoji-icons", "эмодзи вместо иконок", emoji.length, emoji.map(label));
  const arrows = [...document.querySelectorAll("a,button")].filter((e) => vis(e) && /[→⟶➔›»]\s*$/.test((e.innerText || "").trim()));
  if (arrows.length >= 3) add("warn", "arrow-links", "«→» в конце каждой ссылки и кнопки", arrows.length, arrows.map(label));
  const blocks = visible.filter((e) => /^(P|H1|H2|H3|LI)$/.test(e.tagName) && (e.innerText || "").trim().length > 20);
  const centered = blocks.filter((e) => getComputedStyle(e).textAlign === "center");
  if (blocks.length >= 8 && centered.length / blocks.length > 0.7) add("warn", "all-centered", `почти всё выровнено по центру (${centered.length} из ${blocks.length} блоков текста)`);
  const anims = new Map();
  for (const e of visible) { const n = getComputedStyle(e).animationName; if (n && n !== "none") anims.set(n, (anims.get(n) || 0) + 1); }
  for (const [n, k] of anims) if (k >= 6) add("warn", "same-animation", `одна анимация «${n}» на ${k} элементах — вместо одного продуманного момента`, k);

  // ---- 7. сводка для меры различия
  const top = (m) => [...m.entries()].sort((a, b) => b[1] - a[1])[0];
  const radius = new Map();
  for (const e of visible) { const r = getComputedStyle(e).borderTopLeftRadius; if (r !== "0px") radius.set(r, (radius.get(r) || 0) + 1); }
  const navLeft = visible.some((e) => (e.tagName === "NAV" || e.getAttribute("role") === "navigation" || e.tagName === "ASIDE") && e.getBoundingClientRect().left < 40 && e.getBoundingClientRect().height > innerHeight * 0.6 && e.getBoundingClientRect().width < innerWidth * 0.35);
  const sections = [...document.querySelectorAll("main > *, body > section, body > header, body > footer, main section")].filter(vis).length;
  const bodyBg = bgOf(document.body) || [255, 255, 255, 1];
  return {
    issues,
    stats: { elements: visible.length, headFont: headFam, bodyFont: bodyFam, bgLum: +lum(bodyBg).toFixed(3), radius: (top(radius) || ["0px"])[0], layout: navLeft ? "sidebar" : "topbar", sections, centeredShare: blocks.length ? +(centered.length / blocks.length).toFixed(2) : 0 },
  };
}
