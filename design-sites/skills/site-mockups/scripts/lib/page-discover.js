// Выполняется ВНУТРИ страницы. Находит ссылки на другие страницы и кандидатов
// в компоненты/модалки, предлагая для каждого устойчивый CSS-селектор.
// Возвращает { title, links:[url], candidates:[{kind, group, selector, count, label, visible}] }
() => {
  const cssEsc = (s) => (window.CSS && CSS.escape ? CSS.escape(s) : s.replace(/[^\w-]/g, "\\$&"));
  const isHashy = (c) => /^(css|sc|jsx|emotion|svelte)-|^_|[0-9a-f]{5,}|__\w{5,}$/i.test(c) || c.length > 40;
  const selectorFor = (el) => {
    if (el.id && !/\d{3,}/.test(el.id)) return "#" + cssEsc(el.id);
    for (const a of ["data-testid", "data-test", "data-qa", "data-component", "aria-label", "name"]) {
      const v = el.getAttribute(a);
      if (v && v.length < 60) return `${el.tagName.toLowerCase()}[${a}="${v.replace(/"/g, '\\"')}"]`;
    }
    const parts = [];
    let cur = el;
    while (cur && cur.nodeType === 1 && cur !== document.documentElement && parts.length < 4) {
      let part = cur.tagName.toLowerCase();
      if (cur.id && !/\d{3,}/.test(cur.id)) { parts.unshift("#" + cssEsc(cur.id)); break; }
      const cls = [...cur.classList].filter((c) => !isHashy(c)).slice(0, 2);
      if (cls.length) part += "." + cls.map(cssEsc).join(".");
      const parent = cur.parentElement;
      if (parent) {
        const same = [...parent.children].filter((c) => c.tagName === cur.tagName);
        if (same.length > 1 && !cls.length) part += `:nth-of-type(${same.indexOf(cur) + 1})`;
      }
      parts.unshift(part);
      try { if (document.querySelectorAll(parts.join(" > ")).length === 1) break; } catch {}
      cur = parent;
    }
    return parts.join(" > ");
  };
  const visible = (el) => {
    const r = el.getBoundingClientRect();
    const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== "hidden" && s.display !== "none" && s.opacity !== "0";
  };
  const label = (el) => (el.getAttribute("aria-label") || el.textContent || "").replace(/\s+/g, " ").trim().slice(0, 60);

  const rules = [
    // [kind, group, selector]
    ["component", "layout", "header, [role=banner]"],
    ["component", "layout", "nav, [role=navigation]"],
    ["component", "layout", "footer, [role=contentinfo]"],
    ["component", "layout", "aside, [role=complementary]"],
    ["component", "sections", "main > section, main > div > section, body > section"],
    ["component", "forms", "form"],
    ["component", "controls", "button, [role=button], a[class*=btn], a[class*=button]"],
    ["component", "controls", "input:not([type=hidden]), select, textarea"],
    ["component", "content", "[class*=card], article"],
    ["component", "content", "table"],
    ["component", "content", "[class*=badge], [class*=tag], [class*=chip]"],
    ["component", "navigation", "[role=tablist], [class*=tabs]"],
    ["component", "navigation", "[class*=breadcrumb], [aria-label*=breadcrumb i]"],
    ["component", "navigation", "[class*=pagination], [aria-label*=pagination i]"],
    ["modal", "modals", "dialog, [role=dialog], [role=alertdialog], [aria-modal=true], [class*=modal]:not([class*=modal-] *), [class*=drawer], [class*=popup], [class*=offcanvas]"],
    ["overlay", "overlays", "[role=menu], [role=listbox], [role=tooltip], [class*=dropdown-menu], [class*=popover], [class*=tooltip], [class*=toast]"],
    // Триггеры проверяются отдельно: кнопка может быть и компонентом, и открывашкой модалки.
    ["trigger", "triggers", "[data-toggle], [data-bs-toggle], [aria-haspopup]:not([aria-haspopup=false]), [aria-controls], [aria-expanded], [data-open], [data-modal], [data-modal-target], [data-dialog], [data-target], [data-bs-target], [x-on\\:click], [\\@click]"],
  ];
  const seen = new Set();
  const candidates = [];
  for (const [kind, group, sel] of rules) {
    let els;
    try { els = [...document.querySelectorAll(sel)]; } catch { continue; }
    const bySel = new Map();
    for (const el of els) {
      if (kind !== "trigger" && seen.has(el)) continue;
      seen.add(el);
      const s = selectorFor(el);
      if (!bySel.has(s)) bySel.set(s, { kind, group, selector: s, count: 0, label: label(el), visible: visible(el), controls: el.getAttribute("aria-controls") || el.getAttribute("data-bs-target") || el.getAttribute("data-target") || undefined });
      bySel.get(s).count++;
    }
    candidates.push(...bySel.values());
  }
  const links = [...new Set([...document.querySelectorAll("a[href]")].map((a) => {
    try { const u = new URL(a.getAttribute("href"), document.baseURI); u.hash = ""; return u.href; } catch { return null; }
  }).filter(Boolean))];
  return { title: document.title, links, candidates: candidates.slice(0, 300) };
}
