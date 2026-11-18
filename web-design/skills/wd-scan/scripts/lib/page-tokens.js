// Выполняется ВНУТРИ страницы. Собирает дизайн-токены из реально применённых стилей:
// CSS-переменные :root и частотность цветов, шрифтов, размеров, радиусов, теней, отступов.
// Возвращает { vars:{name:value}, stats:{category:{value:count}}, themeHints:[строка] }
// themeHints — признаки второй темы в CSS: @media (prefers-color-scheme: dark), селекторы .dark / [data-theme=…].
() => {
  const vars = {};
  const hints = new Set();
  const DARK_SEL = /()(\.(?:theme-)?dark(?![\w-])|\[data-(?:theme|mode|color-scheme|bs-theme)[^\]]*dark[^\]]*\])/i;
  const collectVars = (rules) => {
    for (const r of rules) {
      if (r.cssRules && !r.selectorText) {
        // переменные тёмной темы по медиа-запросу — не значения :root (иначе светлые затрутся тёмными); это признак темы
        const cond = (r.conditionText || (r.media && r.media.mediaText) || "");
        if (/prefers-color-scheme:\s*dark/i.test(cond)) { hints.add("@media (prefers-color-scheme: dark)"); continue; }
        try { collectVars(r.cssRules); } catch {}
        continue;
      }
      if (!r.style || !r.selectorText) continue;
      const dm = r.selectorText.match(DARK_SEL);
      if (dm && [...r.style].some((p) => p.startsWith("--"))) hints.add(dm[2]);
      if (!/(^|,)\s*(:root|html|body|\[data-theme[^\]]*\]|\.theme-[\w-]+|\.dark|\.light)\s*(,|$)/.test(r.selectorText)) continue;
      for (const prop of r.style) {
        if (prop.startsWith("--")) {
          const plain = /^\s*(:root|html)\s*$/.test(r.selectorText) || (r.selectorText.includes(":root") && !DARK_SEL.test(r.selectorText));
          const key = plain ? prop : `${prop} @ ${r.selectorText}`;
          vars[key] = r.style.getPropertyValue(prop).trim();
        }
      }
    }
  };
  for (const s of document.styleSheets) { try { collectVars(s.cssRules); } catch {} }

  const stats = { color: {}, background: {}, border: {}, fontFamily: {}, fontSize: {}, fontWeight: {}, lineHeight: {}, letterSpacing: {}, radius: {}, shadow: {}, spacing: {}, gap: {} };
  const add = (cat, v) => { if (!v || v === "none" || v === "normal" || v === "0px" || v === "rgba(0, 0, 0, 0)" || v === "auto") return; stats[cat][v] = (stats[cat][v] || 0) + 1; };
  const els = document.body ? document.body.querySelectorAll("*") : [];
  let n = 0;
  for (const el of els) {
    if (++n > 8000) break;
    const r = el.getBoundingClientRect();
    if (!r.width || !r.height) continue;
    const s = getComputedStyle(el);
    const hasText = [...el.childNodes].some((c) => c.nodeType === 3 && c.textContent.trim());
    if (hasText) {
      add("color", s.color);
      add("fontFamily", s.fontFamily);
      add("fontSize", s.fontSize);
      add("fontWeight", s.fontWeight);
      add("lineHeight", s.lineHeight);
      add("letterSpacing", s.letterSpacing);
    }
    add("background", s.backgroundColor);
    if (parseFloat(s.borderTopWidth) > 0) add("border", `${s.borderTopWidth} ${s.borderTopStyle} ${s.borderTopColor}`);
    add("radius", s.borderTopLeftRadius);
    add("shadow", s.boxShadow);
    for (const p of ["paddingTop", "paddingRight", "paddingBottom", "paddingLeft", "marginTop", "marginBottom"]) add("spacing", s[p]);
    add("gap", s.rowGap); add("gap", s.columnGap);
  }
  return { vars, stats, themeHints: [...hints] };
}
