// Выполняется ВНУТРИ страницы. Собирает дизайн-токены из реально применённых стилей:
// CSS-переменные :root и частотность цветов, шрифтов, размеров, радиусов, теней, отступов.
// Возвращает { vars:{name:value}, stats:{category:{value:count}} }
() => {
  const vars = {};
  const collectVars = (rules) => {
    for (const r of rules) {
      if (r.cssRules && !r.selectorText) { try { collectVars(r.cssRules); } catch {} continue; }
      if (!r.style || !r.selectorText) continue;
      if (!/(^|,)\s*(:root|html|body|\[data-theme[^\]]*\]|\.theme-[\w-]+|\.dark|\.light)\s*(,|$)/.test(r.selectorText)) continue;
      for (const prop of r.style) {
        if (prop.startsWith("--")) {
          const key = r.selectorText.includes(":root") || r.selectorText === "html" ? prop : `${prop} @ ${r.selectorText}`;
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
  return { vars, stats };
}
