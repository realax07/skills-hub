// Шаги, которые приводят страницу в нужное состояние перед снимком (открыть модалку, меню и т.п.).
// Каждый шаг — объект с одним ключом действия:
//   {click: sel} {dblclick: sel} {hover: sel} {focus: sel} {fill: sel, value} {select: sel, value}
//   {check: sel} {press: "Escape"} {waitFor: sel} {wait: ms} {scroll: sel|"bottom"} {goto: path}
//   {eval: "js-выражение"}  {nth: N} — индекс элемента для click/hover/... (по умолчанию 0)
export async function runSteps(page, steps = [], baseUrl, timeout = 8000) {
  for (const [i, step] of steps.entries()) {
    const where = `шаг ${i + 1} ${JSON.stringify(step)}`;
    const loc = (sel) => page.locator(sel).nth(step.nth || 0);
    try {
      if (step.click) await loc(step.click).click({ timeout });
      else if (step.dblclick) await loc(step.dblclick).dblclick({ timeout });
      else if (step.hover) await loc(step.hover).hover({ timeout });
      else if (step.focus) await loc(step.focus).focus({ timeout });
      else if (step.fill) await loc(step.fill).fill(String(step.value ?? ""), { timeout });
      else if (step.select) await loc(step.select).selectOption(step.value, { timeout });
      else if (step.check) await loc(step.check).check({ timeout });
      else if (step.press) await page.keyboard.press(step.press);
      else if (step.waitFor) await page.locator(step.waitFor).first().waitFor({ state: "visible", timeout });
      else if (step.wait) await page.waitForTimeout(step.wait);
      else if (step.scroll === "bottom") await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
      else if (step.scroll) await loc(step.scroll).scrollIntoViewIfNeeded({ timeout });
      else if (step.goto) await page.goto(new URL(step.goto, baseUrl).href, { waitUntil: "load" });
      else if (step.eval) await page.evaluate(step.eval);
      else throw new Error("неизвестное действие");
      await page.waitForTimeout(step.settle ?? 150);
    } catch (e) {
      throw new Error(`${where}: ${String(e.message).split("\n")[0]}`);
    }
  }
}

// Тема из плана (plan.themes.<имя>): как включить её на странице. Поля сочетаются:
//   colorScheme: "dark"            — медиа prefers-color-scheme (сайты на @media)
//   localStorage: {"theme":"dark"} — до загрузки страницы (next-themes, самописные переключатели)
//   htmlClass: "dark"              — класс на <html> после загрузки (Tailwind darkMode: "class")
//   htmlAttr: {"data-theme":"dark"} — атрибут на <html> после загрузки
//   steps: [{"click":"…"}]         — шаги после загрузки (кнопка переключения темы)
// Порядок: themeBefore(page, theme) → page.goto → themeAfter(page, theme, url).
export async function themeBefore(page, theme = {}) {
  if (theme.colorScheme) await page.emulateMedia({ colorScheme: theme.colorScheme });
  if (theme.localStorage) {
    await page.addInitScript((kv) => {
      try { for (const [k, v] of Object.entries(kv)) localStorage.setItem(k, typeof v === "string" ? v : JSON.stringify(v)); } catch {}
    }, theme.localStorage);
  }
}

export async function themeAfter(page, theme = {}, baseUrl, timeout = 8000) {
  const mark = (t) => {
    const h = document.documentElement;
    for (const c of String(t.htmlClass || "").split(/\s+/).filter(Boolean)) h.classList.add(c);
    for (const [k, v] of Object.entries(t.htmlAttr || {})) h.setAttribute(k, v);
  };
  const plain = { htmlClass: theme.htmlClass, htmlAttr: theme.htmlAttr };
  if (theme.htmlClass || theme.htmlAttr) await page.evaluate(mark, plain);
  if (theme.steps && theme.steps.length) await runSteps(page, theme.steps, baseUrl, timeout);
  await page.waitForTimeout(300);
  // фреймворк мог сбросить класс при гидратации — ставим ещё раз
  if (theme.htmlClass || theme.htmlAttr) await page.evaluate(mark, plain);
  await page.evaluate(() => document.fonts && document.fonts.ready);
}

// Действующие значения CSS-переменных (с учётом темы): имена → значения на <html>.
export async function readVars(page, names) {
  return page.evaluate((list) => {
    const s = getComputedStyle(document.documentElement);
    const out = {};
    for (const n of list) { const v = s.getPropertyValue(n).trim(); if (v) out[n] = v; }
    return out;
  }, names);
}
