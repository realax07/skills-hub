// Выполняется ВНУТРИ страницы. Извлекает дизайн-контекст: основы и детали.
//   opts: { serviceStyleId, iconMax: 64 }
// Возвращает { foundations, motion, parts, icons, logos }:
//   foundations — цвета по ролям (с именами CSS-переменных), типографика, отступы, радиусы, тени, шрифты;
//   motion      — переходы, анимации, @keyframes, признаки JS-анимаций (GSAP, Framer, Lottie, canvas, WebGL);
//   parts       — детали по группам (buttons, inputs, links, badges, cards): кластеры по визуальной подписи
//                 с устойчивым id (хэш подписи), числом употреблений, компактной разметкой и data-kit-id примера;
//   icons/logos — svg-разметка иконок (до iconMax px) и логотипы шапки.
// Примеры помечаются атрибутом data-kit-id (для вырезок); раннер снимает метки после вырезок.
(opts) => {
  opts = opts || {};
  const iconMax = opts.iconMax || 64;
  // Служебный стиль съёмки гасит transition/animation — на время замера его выключаем.
  const service = opts.serviceStyleId && document.getElementById(opts.serviceStyleId);
  if (service) service.disabled = true;
  try {
    const vis = (el) => {
      const r = el.getBoundingClientRect();
      if (r.width < 2 || r.height < 2) return false;
      const s = getComputedStyle(el);
      return s.visibility !== "hidden" && s.display !== "none" && +s.opacity > 0.05;
    };
    // прозрачный: transparent, rgba(..., 0), color(... / 0)
    const transparent = (c) => !c || c === "transparent" || /^rgba\([^,]+,[^,]+,[^,]+,\s*0\)$/.test(c) || /\/\s*0\)$/.test(c);
    const cv = document.createElement("canvas").getContext("2d");
    const norm = (c) => { try { cv.fillStyle = "#010203"; cv.fillStyle = c; return cv.fillStyle; } catch { return c; } };
    const h32 = (s) => { let h = 2166136261; for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); } return (h >>> 0).toString(36); };
    const bump = (m, k, ex) => { if (!m.has(k)) m.set(k, { n: 0, ex: [] }); const e = m.get(k); e.n++; if (ex && e.ex.length < 2) e.ex.push(ex); };

    // ---- CSS-переменные: имя → цвет (для подписи цветов смысловыми именами)
    const varNames = new Map();
    const rootStyle = getComputedStyle(document.documentElement);
    const props = new Set();
    const keyframes = new Set();
    for (const sh of document.styleSheets) {
      let rules; try { rules = sh.cssRules; } catch { continue; }
      const walk = (rs) => { for (const r of rs) {
        if (r.type === 7) keyframes.add(r.name);
        if (r.style) for (const p of r.style) if (p.startsWith("--")) props.add(p);
        if (r.cssRules) walk(r.cssRules);
      } };
      walk(rules);
    }
    for (const p of props) {
      const v = rootStyle.getPropertyValue(p).trim();
      if (!v || !/^(#|rgb|hsl|lab|lch|oklab|oklch|color\(|transparent)/i.test(v)) continue;
      const n = norm(v);
      if (!varNames.has(n)) varNames.set(n, []);
      if (varNames.get(n).length < 4) varNames.get(n).push(p);
    }

    const skipTags = new Set(["SCRIPT", "STYLE", "NOSCRIPT", "TEMPLATE", "META", "LINK", "BR", "HEAD", "TITLE"]);
    const all = [...document.body.querySelectorAll("*")].filter((el) => !skipTags.has(el.tagName));
    const visible = all.filter(vis).slice(0, 20000);
    const ownText = (el) => [...el.childNodes].filter((n) => n.nodeType === 3).map((n) => n.textContent).join("").replace(/\s+/g, " ").trim();

    const colors = { text: new Map(), background: new Map(), border: new Map(), icon: new Map() };
    const type = new Map(), spacing = new Map(), radius = new Map(), shadow = new Map(), fonts = new Map(), transitions = new Map(), animations = new Map();
    for (const el of visible) {
      const s = getComputedStyle(el);
      const t = ownText(el);
      if (t) {
        bump(colors.text, norm(s.color));
        const fam = s.fontFamily.split(",")[0].replace(/["']/g, "").trim();
        bump(fonts, fam);
        bump(type, [fam, s.fontSize, s.fontWeight, s.lineHeight, s.letterSpacing, s.textTransform, s.fontStyle].join("|"), { tag: el.tagName.toLowerCase(), text: t.slice(0, 60) });
      }
      if (!transparent(s.backgroundColor)) bump(colors.background, norm(s.backgroundColor));
      if (parseFloat(s.borderTopWidth) > 0 && s.borderTopStyle !== "none" && !transparent(s.borderTopColor)) bump(colors.border, norm(s.borderTopColor));
      if (el instanceof SVGElement && s.fill && s.fill !== "none" && !s.fill.startsWith("url")) bump(colors.icon, norm(s.fill));
      for (const p of ["paddingTop", "paddingLeft", "marginTop", "marginBottom", "rowGap", "columnGap"]) { const v = s[p]; if (v && v !== "0px" && v !== "normal" && v !== "auto" && !v.startsWith("-")) bump(spacing, v); }
      if (s.borderTopLeftRadius !== "0px") bump(radius, s.borderTopLeftRadius);
      if (s.boxShadow !== "none") bump(shadow, s.boxShadow.replace(/rgba\(0, 0, 0, 0\) 0px 0px 0px 0px,?\s*/g, "").replace(/,\s*$/, "").trim() || "none");
      if (s.transitionDuration && !/^0s(, 0s)*$/.test(s.transitionDuration)) bump(transitions, `${s.transitionProperty.slice(0, 80)} | ${s.transitionDuration} | ${s.transitionTimingFunction}`);
      if (s.animationName && s.animationName !== "none") bump(animations, `${s.animationName} | ${s.animationDuration} | ${s.animationTimingFunction} | ${s.animationIterationCount}`);
    }
    const canvases = [...document.querySelectorAll("canvas")];
    const js = {
      gsap: !!window.gsap, framerMotion: !!document.querySelector("[data-framer-appear-id],[data-projection-id],[data-framer-name]"),
      lottie: !!document.querySelector("lottie-player,dotlottie-player,[class*=lottie]"), canvas: canvases.length,
      webgl: canvases.filter((c) => { try { return !!(c.getContext("webgl2") || c.getContext("webgl")); } catch { return false; } }).length,
      video: document.querySelectorAll("video").length, threeJs: !!window.THREE,
    };

    // ---- иконки и логотипы: svg-разметка
    const cleanSvg = (svg) => {
      const c = svg.cloneNode(true);
      c.removeAttribute("data-kit-id");
      if (!c.getAttribute("xmlns")) c.setAttribute("xmlns", "http://www.w3.org/2000/svg");
      return c.outerHTML.replace(/\s+/g, " ");
    };
    const icons = new Map();
    const logos = [];
    // ссылка на главную: "/", "/home", "/homepage", "index.html" или aria-label «home / главная»
    const isHome = (a) => {
      if (!a) return false;
      const href = a.getAttribute("href") || "";
      let path = href;
      try { const u = new URL(href, location.href); if (u.origin !== location.origin) return false; path = u.pathname; } catch {}
      return /^\/(home(page)?|index\.html?)?\/?$/i.test(path) || /\b(home|главн)/i.test(`${a.getAttribute("aria-label") || ""} ${a.getAttribute("title") || ""}`);
    };
    for (const svg of document.querySelectorAll("svg")) {
      if (!vis(svg) || svg.closest("svg") !== svg) continue;
      const r = svg.getBoundingClientRect();
      const hint = `${svg.getAttribute("aria-label") || ""} ${svg.getAttribute("class") || ""} ${svg.closest("a")?.getAttribute("aria-label") || ""}`;
      // логотип сайта — в шапке: ссылка на главную или явный признак logo; стены логотипов клиентов — не он
      const inHeader = svg.closest("header,[role=banner]") || (svg.closest("nav") && svg.getBoundingClientRect().top < 120);
      const homeLink = isHome(svg.closest("a"));
      const logoish = /logo|brand|wordmark/i.test(hint) || !!svg.closest("[class*=logo i],[class*=brand i],[id*=logo i]");
      if (inHeader && (homeLink || logoish) && r.height <= 80) {
        const sig = h32(svg.innerHTML.replace(/\s+/g, " "));
        if (logos.length < 3 && !logos.some((l) => l.id === sig)) logos.push({ id: sig, svg: cleanSvg(svg), w: Math.round(r.width), h: Math.round(r.height) });
        continue;
      }
      if (r.width > iconMax || r.height > iconMax) continue;
      const markup = cleanSvg(svg);
      if (markup.length > 20000) continue;
      const key = h32(svg.innerHTML.replace(/\s+/g, " "));
      if (!icons.has(key)) icons.set(key, { id: key, n: 0, svg: markup, w: Math.round(r.width), h: Math.round(r.height), label: svg.getAttribute("aria-label") || svg.closest("[aria-label]")?.getAttribute("aria-label") || "" });
      icons.get(key).n++;
    }
    for (const img of document.querySelectorAll("header img, [role=banner] img, nav img")) {
      const homeLink = isHome(img.closest("a"));
      const logoish = /logo|brand/i.test(`${img.alt} ${img.className} ${img.src}`) || !!img.closest("[class*=logo i],[class*=brand i]");
      if (!vis(img) || img.getBoundingClientRect().top > 120 || !(homeLink || logoish)) continue;
      const src = img.currentSrc || img.src;
      if (logos.length < 3 && !logos.some((l) => l.src === src)) logos.push({ id: (() => { try { const u = new URL(src); return u.origin === location.origin ? u.pathname : src; } catch { return src; } })(), src, alt: img.alt, w: Math.round(img.getBoundingClientRect().width), h: Math.round(img.getBoundingClientRect().height) });
    }

    // ---- детали: кластеры по визуальной подписи
    let kid = 0;
    const mark = (el) => { if (!el.dataset.kitId) el.dataset.kitId = "k" + kid++; return el.dataset.kitId; };
    const KEEP = /^(class|href|type|role|aria-label|placeholder|name|value|alt|for|disabled|checked|aria-expanded|aria-selected|aria-current|data-state|data-variant|data-size)$/;
    const compact = (el) => {
      const c = el.cloneNode(true);
      c.querySelectorAll("svg").forEach((s) => { s.innerHTML = ""; [...s.attributes].forEach((a) => { if (a.name !== "class" && a.name !== "viewBox") s.removeAttribute(a.name); }); });
      const strip = (n) => { for (const a of [...n.attributes]) if (!KEEP.test(a.name)) n.removeAttribute(a.name); };
      strip(c); c.querySelectorAll("*").forEach(strip);
      c.querySelectorAll("*").forEach((n) => { for (const t of [...n.childNodes]) if (t.nodeType === 3 && t.textContent.length > 80) t.textContent = t.textContent.slice(0, 80) + "…"; });
      const h = c.outerHTML.replace(/\s+/g, " ");
      return h.length > 900 ? h.slice(0, 900) + "…" : h;
    };
    const bgOf = (el) => { let e = el; while (e && e !== document.documentElement) { const b = getComputedStyle(e).backgroundColor; if (!transparent(b)) return norm(b); e = e.parentElement; } return "#ffffff"; };
    // Подпись «мягкая»: отступы и размеры шрифта округлены, чтобы почти одинаковые не дробились.
    const q = (v, step) => Math.round(parseFloat(v) / step) * step;
    const sig = (el, s) => {
      const border = parseFloat(s.borderTopWidth) > 0 && !transparent(s.borderTopColor) ? norm(s.borderTopColor) : "-";
      const r = parseFloat(s.borderTopLeftRadius);
      return [
        transparent(s.backgroundColor) ? "-" : norm(s.backgroundColor), norm(s.color), border,
        r >= 999 ? "pill" : q(r, 2) + "px", q(s.fontSize, 1) + "px", s.fontWeight,
        q(s.paddingTop, 4) + "/" + q(s.paddingLeft, 4), s.boxShadow === "none" ? "" : "shadow", s.textDecorationLine === "none" ? "" : s.textDecorationLine,
      ].join(" · ");
    };
    const groups = { buttons: new Map(), inputs: new Map(), links: new Map(), badges: new Map(), cards: new Map() };
    const add = (g, el, s) => {
      const k = sig(el, s);
      const r = el.getBoundingClientRect();
      if (!groups[g].has(k)) groups[g].set(k, {
        id: h32(g + k), sig: k, n: 0, kit: mark(el), html: compact(el), w: Math.round(r.width), h: Math.round(r.height),
        text: (el.innerText || el.value || el.placeholder || el.getAttribute("aria-label") || "").trim().replace(/\s+/g, " ").slice(0, 40),
        style: { background: s.backgroundColor, color: s.color, border: `${s.borderTopWidth} ${s.borderTopStyle} ${s.borderTopColor}`, radius: s.borderTopLeftRadius,
          font: `${s.fontWeight} ${s.fontSize}/${s.lineHeight} ${s.fontFamily.split(",")[0]}`, padding: s.padding, shadow: s.boxShadow === "none" ? "" : s.boxShadow.slice(0, 120), transition: s.transitionDuration !== "0s" ? `${s.transitionProperty.slice(0, 40)} ${s.transitionDuration} ${s.transitionTimingFunction}` : "" },
      });
      groups[g].get(k).n++;
    };
    for (const el of visible) {
      const s = getComputedStyle(el), tag = el.tagName, r = el.getBoundingClientRect();
      if (el.closest("svg") && tag !== "svg") continue;
      const boxBg = !transparent(s.backgroundColor) && norm(s.backgroundColor) !== bgOf(el.parentElement);
      const hasBox = boxBg || parseFloat(s.borderTopWidth) > 0 && !transparent(s.borderTopColor) || s.boxShadow !== "none";
      const text = ownText(el);
      if ((tag === "INPUT" && /^(submit|button|reset)$/.test(el.type)) || tag === "BUTTON" || el.getAttribute("role") === "button" || (tag === "A" && hasBox && parseFloat(s.paddingLeft) >= 6 && r.height <= 64)) {
        if (r.height <= 80 && r.width <= 480) add("buttons", el, s);
      } else if ((tag === "INPUT" && !/^(hidden|submit|button|reset|image)$/.test(el.type)) || tag === "SELECT" || tag === "TEXTAREA") add("inputs", el, s);
      else if (tag === "A" && (text || el.innerText.trim())) add("links", el, s);
      else if (!/^(A|BUTTON|INPUT|LABEL)$/.test(tag) && hasBox && r.height <= 32 && r.width <= 220 && text && text.length <= 24 && parseFloat(s.borderTopLeftRadius) > 0) add("badges", el, s);
      else if (!el.closest("dialog,[role=dialog],[role=alertdialog],[aria-modal=true]") && hasBox && parseFloat(s.borderTopLeftRadius) >= 4 && r.width >= 160 && r.height >= 100 && r.width < innerWidth * 0.9 && el.querySelector("h1,h2,h3,h4,h5,h6,img,p,strong")) add("cards", el, s);
    }

    const top = (m, n) => [...m.entries()].sort((a, b) => b[1].n - a[1].n).slice(0, n);
    const colorList = (m) => top(m, 40).map(([c, e]) => ({ color: c, n: e.n, vars: varNames.get(c) || [] }));
    return {
      elements: visible.length,
      foundations: {
        colors: { text: colorList(colors.text), background: colorList(colors.background), border: colorList(colors.border), icon: colorList(colors.icon) },
        type: top(type, 40).map(([k, e]) => { const [family, size, weight, lineHeight, letterSpacing, transform, style] = k.split("|"); return { key: k, family, size, weight, lineHeight, letterSpacing, transform, style, n: e.n, ex: e.ex }; }),
        fonts: top(fonts, 10).map(([k, e]) => ({ family: k, n: e.n })),
        fontFaces: [...document.fonts].filter((f) => f.status === "loaded").map((f) => `${f.family.replace(/["']/g, "")} ${f.weight} ${f.style}`),
        spacing: top(spacing, 24).map(([v, e]) => ({ v, n: e.n })), radius: top(radius, 16).map(([v, e]) => ({ v, n: e.n })), shadow: top(shadow, 12).map(([v, e]) => ({ v: v.slice(0, 200), n: e.n })),
        cssVars: props.size,
      },
      motion: { transitions: top(transitions, 16).map(([v, e]) => ({ v, n: e.n })), animations: top(animations, 16).map(([v, e]) => ({ v, n: e.n })), keyframes: [...keyframes], js },
      icons: [...icons.values()].sort((a, b) => b.n - a.n).slice(0, 80),
      logos,
      parts: Object.fromEntries(Object.entries(groups).map(([g, m]) => [g, top(m, 60).map(([, e]) => e)])),
    };
  } finally {
    if (service) service.disabled = false;
  }
}
