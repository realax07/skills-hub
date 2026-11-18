// Выполняется ВНУТРИ страницы. Сжатая схема разметки для чтения агентом (в 5–10 раз меньше HTML):
// svg без путей, длинный текст обрезан, повторяющиеся соседи и группы соседей свёрнуты в «…повтор ×N»,
// скрытое (display:none) пропущено, общие компоненты заменены ссылкой на их файл.
// Поддерево длиннее maxBlock строк (глубже 2 уровня) показывается началом и сворачивается: обычно это демо-контент
// (макеты приложения в HTML, графики, длинные списки), а агенту нужна структура.
//   opts: { selector?, index?, maxText: 80, maxBlock: 60, refs: [{ selector, ref }] }
// Возвращает строку (или null, если элемента нет).
(opts) => {
  opts = opts || {};
  const maxText = opts.maxText || 80;
  const maxBlock = opts.maxBlock || 60;
  const KEEP = /^(class|id|href|role|aria-label|aria-current|aria-expanded|type|placeholder|alt|name|for|data-state|data-variant|data-mockup-placeholder)$/;
  const root = opts.selector ? document.querySelectorAll(opts.selector)[opts.index || 0] : document.body;
  if (!root) return null;
  const refs = (opts.refs || []).map((r) => { try { return { el: document.querySelector(r.selector), ref: r.ref }; } catch { return null; } }).filter((r) => r && r.el && r.el !== root);
  const skip = new Set(["SCRIPT", "STYLE", "NOSCRIPT", "TEMPLATE", "LINK", "META"]);
  const shown = (el) => { const s = getComputedStyle(el); return s.display !== "none"; };
  const attrs = (el) => [...el.attributes].filter((a) => KEEP.test(a.name) && a.value !== "").map((a) => {
    let v = a.value;
    if (a.name === "href" && v.length > 60) v = v.slice(0, 60) + "…";
    if (a.name === "class" && v.length > 240) v = v.slice(0, 240) + "…";
    return `${a.name}="${v.replace(/"/g, "&quot;")}"`;
  }).join(" ");
  const kids = (el) => [...el.childNodes].filter((n) => (n.nodeType === 3 && n.textContent.trim()) || (n.nodeType === 1 && !skip.has(n.tagName) && shown(n)));
  const deep = (n, d = 0) => n.nodeType === 3 ? "#t" : n.tagName + "." + (n.getAttribute("class") || "") + (d < 2 ? "[" + kids(n).slice(0, 6).map((k) => deep(k, d + 1)).join(",") + "]" : "");
  const out = [];
  const render = (n, d) => {
    const pad = " ".repeat(d);
    if (n.nodeType === 3) { const t = n.textContent.replace(/\s+/g, " ").trim(); out.push(pad + (t.length > maxText ? t.slice(0, maxText) + "…" : t)); return; }
    const ref = refs.find((r) => r.el === n);
    if (ref) { out.push(`${pad}<!-- ${n.tagName.toLowerCase()}: ${ref.ref} -->`); return; }
    const tag = n.tagName.toLowerCase();
    const a = attrs(n);
    const open = `<${tag}${a ? " " + a : ""}`;
    if (tag === "svg") { out.push(`${pad}${open}/>`); return; }
    if (tag === "img" || tag === "video") { out.push(`${pad}${open}/>`); return; }
    const ks = kids(n);
    if (!ks.length) { out.push(`${pad}${open}/>`); return; }
    if (ks.length === 1 && ks[0].nodeType === 3) {
      const t = ks[0].textContent.replace(/\s+/g, " ").trim();
      if (t.length <= 60) { out.push(`${pad}${open}>${t}</${tag}>`); return; }
    }
    out.push(`${pad}${open}>`);
    const sigs = ks.map((k) => deep(k));
    let i = 0;
    while (i < ks.length) {
      let best = [1, 1];
      for (const per of [1, 2, 3, 4]) {
        let reps = 1;
        while (i + (reps + 1) * per <= ks.length && sigs.slice(i + reps * per, i + (reps + 1) * per).join("|") === sigs.slice(i, i + per).join("|")) reps++;
        if (reps >= 3 && per * reps > best[0] * best[1]) best = [per, reps];
      }
      const [per, reps] = best;
      if (reps >= 3) {
        for (const k of ks.slice(i, i + per)) renderChild(k, d + 1);
        out.push(`${pad} <!-- …повтор ×${reps - 1} -->`);
        i += per * reps;
      } else { renderChild(ks[i], d + 1); i++; }
    }
    out.push(`${pad}</${tag}>`);
  };
  // ребёнок с бюджетом строк: длинное поддерево — первые строки + пометка, сколько свёрнуто
  let folds = 0;
  const renderChild = (k, d) => {
    const start = out.length, foldsBefore = folds;
    render(k, d);
    const n = out.length - start;
    if (folds > foldsBefore) return; // внутри уже свёрнуто — это структура, её оставляем
    // контейнер из нескольких блоков получает бюджет на каждый: сворачиваются «глухие» демо-поддеревья, а не секции
    // обёртки с одним потомком не в счёт: ветвление — у первого узла цепочки, где потомков больше одного
    let elKids = 0;
    if (k.nodeType === 1) {
      let node = k, list = kids(node).filter((x) => x.nodeType === 1);
      while (list.length === 1) { node = list[0]; list = kids(node).filter((x) => x.nodeType === 1); }
      elKids = list.length;
    }
    if (d > 2 && n > maxBlock * Math.max(1, elKids)) {
      const keep = Math.floor(maxBlock / 2);
      const pad = " ".repeat(d + 1);
      out.splice(start + keep, n - keep - 1, `${pad}<!-- …свёрнуто ${n - keep - 1} строк: полная разметка — в эталоне -->`);
      folds++;
    }
  };
  render(root, 0);
  return out.join("\n");
}
