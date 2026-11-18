#!/usr/bin/env node
// Проверка эталона: открывает каждый HTML из reference/manifest.json без сети (скриптов в снимках нет),
// снимает скриншот и сравнивает с оригинальным скриншотом сайта.
//
//   node scripts/verify.mjs <out>                 все снимки (<out> — папка контекста или её reference/)
//   node scripts/verify.mjs <out> --only header   отдельные
//   node scripts/verify.mjs <out> --threshold 5   допустимое расхождение, % пикселей (по умолчанию 3)
//
// Две группы проверок:
//   1) прямые: не загрузились картинки, CSS, шрифты; снимок ходит во внешнюю сеть;
//   2) пиксельные: расхождение с оригиналом (YIQ + игнор сглаживания + сдвиг до 1px) и размер.
//      Заглушки контента (data-mockup-placeholder) из сравнения исключаются.
// Пишет reference/verify-report.json. Код выхода 1, если хоть одна проверка не прошла.
import { readFileSync, existsSync } from "node:fs";
import { join, resolve, dirname } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { loadPlaywright, parseArgs, readJson, writeFile } from "./lib/runtime.mjs";

const args = parseArgs(process.argv.slice(2), {
  only: {}, threshold: { default: "3" }, help: { alias: "h", type: "bool" },
});
if (args.help || !args._[0]) {
  console.log(readFileSync(fileURLToPath(import.meta.url), "utf8").split("\n").filter((l) => l.startsWith("//")).map((l) => l.slice(3)).join("\n"));
  process.exit(args.help ? 0 : 2);
}
const ARG = resolve(args._[0]);
const OUT = existsSync(join(ARG, "reference", "manifest.json")) ? join(ARG, "reference") : ARG;
const doc = readJson(join(OUT, "manifest.json"));
const only = args.only ? new Set(args.only.split(",")) : null;
const threshold = parseFloat(args.threshold);

// Сравнение двух PNG в браузере через canvas — без внешних зависимостей.
const DIFF = async ([a, b, masks]) => {
  const load = (src) => new Promise((ok, err) => { const i = new Image(); i.onload = () => ok(i); i.onerror = err; i.src = src; });
  const [ia, ib] = await Promise.all([load(a), load(b)]);
  const w = Math.max(ia.width, ib.width), h = Math.max(ia.height, ib.height);
  const px = (img) => { const c = document.createElement("canvas"); c.width = w; c.height = h; const x = c.getContext("2d"); x.fillStyle = "#fff"; x.fillRect(0, 0, w, h); x.drawImage(img, 0, 0); return x.getImageData(0, 0, w, h).data; };
  const da = px(ia), db = px(ib);
  // Заглушки контента (data-mockup-placeholder) намеренно отличаются от оригинала — не сравниваем.
  const mask = new Uint8Array(w * h);
  for (const m of masks || []) {
    for (let y = Math.max(0, Math.floor(m.y)); y < Math.min(h, Math.ceil(m.y + m.height)); y++)
      for (let x = Math.max(0, Math.floor(m.x)); x < Math.min(w, Math.ceil(m.x + m.width)); x++) mask[y * w + x] = 1;
  }
  let masked = 0;
  for (let k = 0; k < mask.length; k++) masked += mask[k];
  // Сравнение по схеме pixelmatch: разница цвета в YIQ (близко к восприятию) и игнор пикселей
  // сглаживания. Элементы на дробных координатах в оригинале и на целых в снимке растеризуются
  // по-разному (края букв, скругления) — это не ошибка снимка. Плюс лучший из сдвигов до 1px:
  // при обрезке элемента на дробной координате весь кадр смещается.
  const MAX = 35215 * 0.1 * 0.1;
  const yiq = (r, g, b) => [r * 0.29889531 + g * 0.58662247 + b * 0.11448223, r * 0.59597799 - g * 0.2741761 - b * 0.32180189, r * 0.21147017 - g * 0.52261711 + b * 0.31114694];
  const delta = (p, i, q, j, yOnly) => {
    const a = yiq(p[i], p[i + 1], p[i + 2]), b = yiq(q[j], q[j + 1], q[j + 2]);
    const dy = a[0] - b[0];
    if (yOnly) return dy;
    const di = a[1] - b[1], dq = a[2] - b[2];
    return 0.5053 * dy * dy + 0.299 * di * di + 0.1957 * dq * dq;
  };
  const at = (x, y) => (y * w + x) * 4;
  const hasManySiblings = (img, x, y) => {
    const i = at(x, y); let n = 0;
    for (let yy = Math.max(y - 1, 0); yy <= Math.min(y + 1, h - 1); yy++)
      for (let xx = Math.max(x - 1, 0); xx <= Math.min(x + 1, w - 1); xx++) {
        if (xx === x && yy === y) continue;
        const j = at(xx, yy);
        if (img[i] === img[j] && img[i + 1] === img[j + 1] && img[i + 2] === img[j + 2] && ++n > 2) return true;
      }
    return false;
  };
  const antialiased = (img, x, y, other) => {
    let zeroes = (x === 0 || x === w - 1 || y === 0 || y === h - 1) ? 1 : 0, min = 0, max = 0, minX, minY, maxX, maxY;
    const i = at(x, y);
    for (let yy = Math.max(y - 1, 0); yy <= Math.min(y + 1, h - 1); yy++)
      for (let xx = Math.max(x - 1, 0); xx <= Math.min(x + 1, w - 1); xx++) {
        if (xx === x && yy === y) continue;
        const d = delta(img, i, img, at(xx, yy), true);
        if (d === 0) { if (++zeroes > 2) return false; }
        else if (d < min) { min = d; minX = xx; minY = yy; }
        else if (d > max) { max = d; maxX = xx; maxY = yy; }
      }
    if (min === 0 || max === 0) return false;
    return (hasManySiblings(img, minX, minY) && hasManySiblings(other, minX, minY)) ||
           (hasManySiblings(img, maxX, maxY) && hasManySiblings(other, maxX, maxY));
  };
  // a — снимок, b — оригинал; сдвиг применяется к оригиналу.
  // Крайнее кольцо в 1px не считаем: при обрезке на дробной координате оно частично захватывает фон.
  const E = w > 8 && h > 8 ? 1 : 0;
  const count = (sx, sy) => {
    let diff = 0;
    for (let y = E; y < h - E; y++) {
      const yb = y + sy;
      if (yb < 0 || yb >= h) continue;
      for (let x = E; x < w - E; x++) {
        const xb = x + sx;
        if (xb < 0 || xb >= w || mask[y * w + x]) continue;
        const i = at(x, y), j = at(xb, yb);
        if (delta(da, i, db, j) <= MAX) continue;
        if (antialiased(da, x, y, db) || antialiased(db, xb, yb, da)) continue;
        diff++;
      }
    }
    return diff;
  };
  let best = count(0, 0);
  if (best > 0) for (const [sx, sy] of [[1, 0], [-1, 0], [0, 1], [0, -1], [1, 1], [-1, -1], [1, -1], [-1, 1]]) { best = Math.min(best, count(sx, sy)); if (!best) break; }
  const area = Math.max(1, (w - 2 * E) * (h - 2 * E) - masked);
  return { diffPct: (best / area) * 100, maskedPct: (masked / (w * h)) * 100, size: [ia.width, ia.height, ib.width, ib.height] };
};

async function main() {
  const { chromium } = await loadPlaywright();
  const browser = await chromium.launch();
  const cmp = await (await browser.newContext()).newPage();
  const results = [];
  const items = doc.items.filter((i) => !only || only.has(i.id) || only.has(i.baseId));
  for (const it of items) {
    const r = { id: it.id, file: it.file, external: [] };
    results.push(r);
    const file = join(OUT, it.file);
    if (!existsSync(file)) { r.status = "missing"; console.log(`  ✗ ${it.id}: нет файла`); continue; }
    const vp = (doc.viewports || {})[it.viewport] || { width: 1440, height: 900 };
    // Тот же режим устройства, что и при съёмке, иначе мобильная вёрстка не совпадёт.
    const ctx = await browser.newContext({
      viewport: { width: vp.width, height: vp.height }, deviceScaleFactor: vp.deviceScaleFactor || 1,
      isMobile: !!vp.isMobile, hasTouch: !!vp.isMobile, userAgent: vp.userAgent, colorScheme: vp.colorScheme,
      // Скриптов в снимках нет, но JS включён: без него Chrome рисует у <video> нативные
      // кнопки плеера, которых в обычном просмотре нет.
      javaScriptEnabled: true,
    });
    await ctx.route(/^https?:/, (route) => { r.external.push(route.request().url()); route.abort(); });
    const page = await ctx.newPage();
    const failed = [];
    // Браузер отменяет загрузки (ERR_ABORTED) — например, видео и постеры при закрытии страницы.
    // Ошибка — только если файла действительно нет на диске.
    page.on("requestfailed", (req) => {
      const u = req.url();
      if (!u.startsWith("file:")) return;
      let exists = false;
      try { exists = existsSync(fileURLToPath(u.split("#")[0].split("?")[0])); } catch {}
      if (!exists) failed.push(u.replace(pathToFileURL(OUT).href + "/", ""));
    });
    await page.goto(pathToFileURL(file).href, { waitUntil: "load" });
    await page.evaluate(() => document.fonts && document.fonts.ready);
    // Прямые проверки типичных сбоев съёмки — пиксельное сравнение их почти не видит:
    // пропавший логотип или упавший шрифт меняют доли процента площади.
    const broken = await page.evaluate(() => ({
      images: [...document.images].filter((i) => i.complete && i.naturalWidth === 0 && i.getAttribute("src")).map((i) => i.getAttribute("src")),
      styles: [...document.querySelectorAll("link[rel=stylesheet]")].filter((l) => !l.sheet).map((l) => l.getAttribute("href")),
      fonts: [...(document.fonts || [])].filter((f) => f.status === "error").map((f) => f.family),
    }));
    r.problems = [
      ...broken.images.map((x) => `картинка не загрузилась: ${x}`),
      ...broken.styles.map((x) => `CSS не подключился: ${x}`),
      ...broken.fonts.map((x) => `шрифт не загрузился: ${x}`),
      ...failed.filter((u) => !broken.images.some((x) => u.endsWith(x)) && !broken.styles.some((x) => u.endsWith(x))).map((x) => `файл не найден: ${x}`),
      ...r.external.map((x) => `внешний запрос: ${x}`),
    ];
    let shot;
    try {
      shot = it.kind === "page" || it.kind === "state"
        ? await page.screenshot({ fullPage: true })
        : await page.locator("[data-mockup-root]").first().screenshot({ timeout: 5000 });
    } catch (e) {
      r.status = "render-failed"; r.error = String(e.message).split("\n")[0];
      console.log(`  ✗ ${it.id}: не отрисовался (${r.error})`);
      await ctx.close(); continue;
    }
    // Области заглушек в координатах скриншота (страница — от начала документа, компонент — от его рамки).
    const masks = await page.evaluate(([isPage, dpr]) => {
      const root = isPage ? null : document.querySelector("[data-mockup-root]");
      const o = root ? root.getBoundingClientRect() : { x: -window.scrollX, y: -window.scrollY };
      return [...document.querySelectorAll("[data-mockup-placeholder]")].map((el) => {
        const r = el.getBoundingClientRect();
        return { x: (r.x - o.x) * dpr, y: (r.y - o.y) * dpr, width: r.width * dpr, height: r.height * dpr };
      }).filter((m) => m.width > 0 && m.height > 0);
    }, [it.kind === "page" || it.kind === "state", vp.deviceScaleFactor || 1]);
    await ctx.close();
    if (!it.screenshot || !existsSync(join(OUT, it.screenshot))) { r.status = "no-reference"; console.log(`  ? ${it.id}: нет оригинального скриншота`); continue; }
    const ref = readFileSync(join(OUT, it.screenshot));
    const d = await cmp.evaluate(DIFF, ["data:image/png;base64," + shot.toString("base64"), (it.screenshot.endsWith(".jpg") ? "data:image/jpeg;base64," : "data:image/png;base64,") + ref.toString("base64"), masks]);
    if (d.maskedPct > 0.5) r.maskedPct = +d.maskedPct.toFixed(1);
    r.diffPct = +d.diffPct.toFixed(2);
    r.sizeMockup = d.size.slice(0, 2); r.sizeOriginal = d.size.slice(2);
    // Недостающая область при сравнении заливается белым и почти не влияет на процент,
    // поэтому разный размер — отдельная ошибка (допуск: 2% или 4 пикселя скриншота).
    const off = (a, b) => Math.abs(a - b) > Math.max(4, 0.02 * Math.max(a, b));
    r.sizeMismatch = off(d.size[0], d.size[2]) || off(d.size[1], d.size[3]);
    r.status = r.diffPct > threshold || r.sizeMismatch || r.problems.length ? "mismatch" : "ok";
    const mark = r.status === "ok" ? "✓" : "✗";
    console.log(`  ${mark} ${it.id}: расхождение ${r.diffPct}%${r.maskedPct ? ` (заглушки контента не сравнивались: ${r.maskedPct}% площади)` : ""}${r.sizeMockup.join() !== r.sizeOriginal.join() ? ` (размер ${r.sizeMockup.join("×")} vs ${r.sizeOriginal.join("×")})` : ""}`);
    for (const pr of r.problems.slice(0, 5)) console.log(`      ! ${pr}`);
  }
  await browser.close();
  // --only: дописываем к прошлому отчёту, а не затираем его
  const repFile = join(OUT, "verify-report.json");
  if (only && existsSync(repFile)) {
    try { const prev = JSON.parse(readFileSync(repFile, "utf8")).results || []; const ids = new Set(results.map((r) => r.id)); results.unshift(...prev.filter((r) => !ids.has(r.id))); } catch {}
  }
  writeFile(repFile, JSON.stringify({ threshold, checkedAt: new Date().toISOString(), results }, null, 2));
  const bad = results.filter((r) => r.status !== "ok" && r.status !== "no-reference");
  console.log(`\n${results.length - bad.length}/${results.length} ок, порог ${threshold}% → verify-report.json`);
  process.exit(bad.length ? 1 : 0);
}
main().catch((e) => { console.error("error: " + e.message); process.exit(1); });
