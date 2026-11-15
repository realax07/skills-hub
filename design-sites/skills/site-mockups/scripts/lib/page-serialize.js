// Выполняется ВНУТРИ страницы (чистые DOM API, без зависимостей).
// Превращает текущее состояние страницы (или одного элемента) в статический HTML.
// Используется capture.mjs через page.evaluate, но годится и для любого другого
// браузерного инструмента агента: (SOURCE)(opts) → JSON.
//
// opts:
//   selector     — CSS-селектор элемента; без него — вся страница
//   index        — какой из найденных элементов брать (по умолчанию 0)
//   skipStyleIds — id <style>, которые не надо забирать (служебные стили раннера)
//   fitSize      — зафиксировать ширину и высоту элемента как на странице (по умолчанию true)
//
// Возвращает { ok, html, sheets:[{href,text}], assets:[url], title, lang, rect, error }
// В html и CSS все внешние URL заменены токенами __MOCKUP_ASSET_<n>__ (индекс в assets).
(opts) => {
  opts = opts || {};
  const skip = new Set(opts.skipStyleIds || []);
  const assets = [];
  const assetIndex = new Map();
  const token = (raw, base) => {
    if (!raw) return raw;
    const v = raw.trim();
    if (!v || v.startsWith("data:") || v.startsWith("#") || v.startsWith("%23") || v.startsWith("about:") || v.startsWith("javascript:")) return raw;
    let abs;
    try { abs = new URL(v, base || document.baseURI).href; } catch { return raw; }
    if (!/^https?:/.test(abs)) return raw;
    if (!assetIndex.has(abs)) { assetIndex.set(abs, assets.length); assets.push(abs); }
    return `__MOCKUP_ASSET_${assetIndex.get(abs)}__`;
  };
  const tokenCssUrls = (css, base) =>
    css.replace(/url\(\s*(['"]?)([^'")]+)\1\s*\)/g, (m, q, u) => `url("${token(u, base)}")`);
  const tokenSrcset = (s) =>
    s.split(",").map((part) => {
      const p = part.trim().split(/\s+/);
      if (p[0]) p[0] = token(p[0]);
      return p.join(" ");
    }).join(", ");

  // ---------- CSS: берём применённые правила из CSSOM (ловит и CSS-in-JS) ----------
  const rulesText = (sheet, depth) => {
    let rules;
    try { rules = sheet.cssRules; } catch { return null; } // cross-origin
    const out = [];
    for (const r of rules) {
      if (typeof CSSImportRule !== "undefined" && r instanceof CSSImportRule && r.styleSheet && depth < 5) {
        const inner = rulesText(r.styleSheet, depth + 1);
        const media = r.media && r.media.mediaText;
        if (inner !== null) out.push(media ? `@media ${media} {\n${inner}\n}` : inner);
        else out.push(r.cssText);
      } else out.push(r.cssText);
    }
    return out.join("\n");
  };
  const sheets = [];
  const allSheets = [...document.styleSheets, ...(document.adoptedStyleSheets || [])];
  for (const s of allSheets) {
    const owner = s.ownerNode;
    if (owner && owner.id && skip.has(owner.id)) continue;
    if (s.disabled) continue;
    const media = s.media && s.media.mediaText && s.media.mediaText !== "all" ? s.media.mediaText : "";
    const text = rulesText(s, 0);
    const base = s.href || document.baseURI;
    if (text === null) sheets.push({ href: s.href, media, text: null });
    else sheets.push({ href: s.href, media, text: tokenCssUrls(text, base) });
  }

  // ---------- DOM ----------
  let root = document.documentElement;
  let target = null;
  let rect = null;
  if (opts.selector) {
    const all = document.querySelectorAll(opts.selector);
    target = all[opts.index || 0];
    if (!target) return { ok: false, error: `элемент не найден: ${opts.selector}` };
    const r = target.getBoundingClientRect();
    rect = { x: r.x, y: r.y, width: r.width, height: r.height };
  }

  // Копируем живое состояние форм в атрибуты, чтобы оно пережило сериализацию.
  const freeze = (orig, clone) => {
    const o = orig.querySelectorAll ? [orig, ...orig.querySelectorAll("*")] : [orig];
    const c = clone.querySelectorAll ? [clone, ...clone.querySelectorAll("*")] : [clone];
    for (let i = 0; i < o.length && i < c.length; i++) {
      const a = o[i], b = c[i];
      const tag = a.tagName;
      if (tag === "INPUT") {
        if (a.type === "checkbox" || a.type === "radio") a.checked ? b.setAttribute("checked", "") : b.removeAttribute("checked");
        else if (a.type !== "file" && a.type !== "password") b.setAttribute("value", a.value);
      } else if (tag === "TEXTAREA") b.textContent = a.value;
      else if (tag === "SELECT") {
        [...b.options].forEach((opt, k) => (a.options[k] && a.options[k].selected ? opt.setAttribute("selected", "") : opt.removeAttribute("selected")));
      } else if (tag === "DETAILS") a.open ? b.setAttribute("open", "") : b.removeAttribute("open");
      else if (tag === "DIALOG" && a.open) b.setAttribute("open", "");
      else if (tag === "CANVAS") {
        try {
          const img = document.createElement("img");
          img.src = a.toDataURL();
          img.width = a.width; img.height = a.height;
          for (const at of a.attributes) if (at.name !== "width" && at.name !== "height") img.setAttribute(at.name, at.value);
          b.replaceWith(img);
        } catch {}
      }
      // Открытый shadow DOM → declarative shadow DOM, если браузер умеет.
      if (a.shadowRoot && a.shadowRoot.mode === "open" && typeof a.shadowRoot.getHTML === "function") {
        const t = document.createElement("template");
        t.setAttribute("shadowrootmode", "open");
        t.innerHTML = a.shadowRoot.getHTML();
        b.prepend(t);
      }
    }
  };

  let clone;
  if (!target) {
    clone = root.cloneNode(true);
    freeze(root, clone);
  } else {
    // «Скелет предков»: html > body > ...предки (без соседей) > элемент целиком.
    // Сохраняет контекст селекторов вида `.theme-dark .header .btn`.
    const deep = target.cloneNode(true);
    freeze(target, deep);
    // Фиксируем размер: в скелете у предков нет соседей, и размер, который задавали
    // соседи (flex/grid-растяжение) или inset (fixed-панель на всю высоту), схлопнулся бы.
    // computed width/height учитывают box-sizing, в отличие от getBoundingClientRect.
    if (opts.fitSize !== false && opts.fitWidth !== false) {
      const cs = getComputedStyle(target);
      if (cs.display !== "inline") {
        if (cs.width.endsWith("px")) deep.style.setProperty("width", cs.width, "important");
        if (cs.height.endsWith("px")) deep.style.setProperty("height", cs.height, "important");
      }
    }
    // Оверлей (dropdown, тултип, тост) позиционирован от предков, а у предков в скелете
    // нет соседей — он уехал бы за экран. Ставим его в поток, исходное позиционирование
    // сохраняем в data-mockup-position для справки.
    const tcs = getComputedStyle(target);
    if (tcs.position === "absolute" || tcs.position === "fixed") {
      deep.setAttribute("data-mockup-position", `${tcs.position}; top:${tcs.top}; right:${tcs.right}; bottom:${tcs.bottom}; left:${tcs.left}; transform:${tcs.transform}`);
      deep.style.setProperty("position", "relative", "important");
      for (const p of ["top", "right", "bottom", "left"]) deep.style.setProperty(p, "auto", "important");
      deep.style.setProperty("transform", "none", "important");
      deep.style.setProperty("display", tcs.display === "none" ? "block" : tcs.display, "important");
    }
    deep.setAttribute("data-mockup-root", "");
    let node = deep;
    let p = target.parentElement;
    while (p) {
      const shell = p.cloneNode(false);
      shell.appendChild(node);
      node = shell;
      if (p === document.documentElement) break;
      p = p.parentElement;
    }
    clone = node; // <html>
    const head = document.head.cloneNode(true);
    const body = clone.querySelector("body");
    if (body && body.parentNode === clone) clone.insertBefore(head, body);
    else clone.prepend(head);
  }

  // Чистка: скрипты, обработчики, внешние стили (CSS собран отдельно), служебное.
  clone.querySelectorAll("script, noscript, link[rel~=stylesheet], link[rel=preload], link[rel=modulepreload], link[rel=prefetch], link[rel=dns-prefetch], link[rel=preconnect], style, base, meta[http-equiv]").forEach((n) => n.remove());
  clone.querySelectorAll("*").forEach((el) => {
    for (const at of [...el.attributes]) if (/^on/i.test(at.name)) el.removeAttribute(at.name);
    if (el.getAttribute("loading") === "lazy") el.removeAttribute("loading");
  });
  clone.querySelectorAll("iframe").forEach((f) => {
    if (f.src) f.setAttribute("data-mockup-src", f.src);
    f.setAttribute("src", "about:blank");
  });

  // URL-атрибуты → токены
  const urlAttrs = [["img", "src"], ["source", "src"], ["video", "src"], ["video", "poster"], ["audio", "src"], ["track", "src"], ["input", "src"], ["link[rel~=icon]", "href"], ["link[rel=apple-touch-icon]", "href"], ["object", "data"], ["embed", "src"]];
  for (const [sel, attr] of urlAttrs) clone.querySelectorAll(sel).forEach((el) => el.hasAttribute(attr) && el.setAttribute(attr, token(el.getAttribute(attr))));
  clone.querySelectorAll("img[srcset], source[srcset]").forEach((el) => el.setAttribute("srcset", tokenSrcset(el.getAttribute("srcset"))));
  clone.querySelectorAll("image, use").forEach((el) => {
    for (const attr of ["href", "xlink:href"]) {
      const v = el.getAttribute(attr);
      if (v && !v.startsWith("#")) el.setAttribute(attr, token(v));
    }
  });
  clone.querySelectorAll("[style]").forEach((el) => el.setAttribute("style", tokenCssUrls(el.getAttribute("style"))));
  // Ссылки не скачиваем. Внутренние — путь от корня сайта (/about): адрес съёмки бывает
  // временным (локальный сервер на случайном порту, стейдж), а путь — это структура сайта.
  // Внешние — абсолютные.
  clone.querySelectorAll("a[href], form[action], area[href]").forEach((a) => {
    const attr = a.tagName === "FORM" ? "action" : "href";
    const h = a.getAttribute(attr);
    if (!h || h.startsWith("#") || /^(mailto|tel|javascript|sms|data):/i.test(h)) return;
    try {
      const u = new URL(h, document.baseURI);
      a.setAttribute(attr, u.origin === location.origin ? u.pathname + u.search + u.hash : u.href);
    } catch {}
  });

  const doctype = document.doctype ? `<!DOCTYPE ${document.doctype.name}>` : "<!DOCTYPE html>";
  return {
    ok: true,
    html: doctype + "\n" + clone.outerHTML,
    sheets,
    assets,
    title: document.title,
    lang: document.documentElement.lang || "",
    rect,
  };
}
