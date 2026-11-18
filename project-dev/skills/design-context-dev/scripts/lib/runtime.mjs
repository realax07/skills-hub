// Общие утилиты: поиск и запуск Playwright, куда ставить зависимости, разбор аргументов.
import { createRequire } from "node:module";
import { existsSync, mkdirSync, writeFileSync, readFileSync } from "node:fs";
import { join, dirname, resolve } from "node:path";
import { homedir } from "node:os";
import { createHash } from "node:crypto";
import { spawnSync } from "node:child_process";

export const PLAYWRIGHT_VERSION = process.env.WEB_DESIGN_CONTEXT_PLAYWRIGHT || "1.65.1";

// Куда setup.mjs ставит Playwright, если его нигде нет: вне папки скилла (скилл бывает симлинком в git-репо
// или read-only копией). Это место установки, а не условие работы: найденный в проекте или глобально тоже годится.
export function depsHome() {
  if (process.env.WEB_DESIGN_CONTEXT_HOME) return resolve(process.env.WEB_DESIGN_CONTEXT_HOME);
  const base =
    process.platform === "win32"
      ? process.env.LOCALAPPDATA || join(homedir(), "AppData", "Local")
      : process.env.XDG_CACHE_HOME || join(homedir(), ".cache");
  return join(base, "agent-skills", "web-design-context");
}

// Playwright ищем не по известному пути, а так, как его нашёл бы Node в окружении агента:
// проект (cwd и выше), глобальные пакеты (npm root -g, NODE_PATH), кэш, куда ставит setup.mjs.
// Готовность проверяется реальным запуском браузера (probe), а не наличием файлов.
const MODULES = ["playwright", "@playwright/test", "playwright-core"];
let globalRoot;
function npmGlobalRoot() {
  if (globalRoot !== undefined) return globalRoot;
  try {
    const r = spawnSync(process.platform === "win32" ? "npm.cmd" : "npm", ["root", "-g"], { encoding: "utf8", timeout: 8000, shell: process.platform === "win32" });
    globalRoot = r.status === 0 ? r.stdout.trim() : null;
  } catch { globalRoot = null; }
  return globalRoot;
}
function bases() {
  const out = [{ base: join(process.cwd(), "noop.js"), where: "проект" }, { base: join(depsHome(), "package.json"), where: "кэш скиллов" }];
  for (const d of (process.env.NODE_PATH || "").split(process.platform === "win32" ? ";" : ":").filter(Boolean)) out.push({ base: join(d, "noop.js"), where: "NODE_PATH" });
  const g = npmGlobalRoot();
  if (g) out.push({ base: join(g, "noop.js"), where: "глобально" });
  return out;
}
export function findPlaywright() {
  for (const { base, where } of bases()) {
    const req = createRequire(base);
    for (const m of MODULES) {
      try {
        const mod = req(m);
        const pw = mod.chromium ? mod : mod.default;
        if (pw && pw.chromium) return { pw, module: m, where, dir: dirname(req.resolve(m + "/package.json")) };
      } catch {}
    }
  }
  return null;
}

// Запуск Chromium: скачанный Playwright-ом, иначе системный Chrome или Edge (channel). Удачный способ запоминается.
let launchWay;
export async function launchChromium(pw, opts = {}) {
  const ways = launchWay ? [launchWay] : [{}, { channel: "chrome" }, { channel: "msedge" }];
  let first;
  for (const w of ways) {
    try {
      const b = await pw.chromium.launch({ ...opts, ...w });
      launchWay = w;
      return b;
    } catch (e) { first ||= e; }
  }
  throw first;
}
export const browserLabel = (b) => `${launchWay && launchWay.channel ? `системный ${launchWay.channel}` : "chromium"} ${b.version()}`;

// Реальная проверка: найти Playwright и запустить браузер. { ok, found, browser, error }
export async function probe() {
  const found = findPlaywright();
  if (!found) return { ok: false, found: null, error: "Playwright не найден (ни в проекте, ни глобально, ни в кэше скиллов)" };
  try {
    const b = await launchChromium(found.pw);
    const browser = browserLabel(b);
    await b.close();
    return { ok: true, found, browser };
  } catch (e) {
    return { ok: false, found, error: "браузер не запускается: " + String(e.message).split("\n")[0] };
  }
}

export async function loadPlaywright() {
  const found = findPlaywright();
  if (!found) {
    console.error("error: Playwright не найден. Проверь и поставь зависимости скилла:\n  node scripts/setup.mjs");
    process.exit(3);
  }
  // наружу — тот же API, но launch с запасными браузерами
  return { ...found.pw, chromium: { launch: (o) => launchChromium(found.pw, o) } };
}

export function parseArgs(argv, spec) {
  // spec: { name: { alias, type: 'string'|'bool'|'int', default } }
  const out = { _: [] };
  for (const [k, v] of Object.entries(spec)) if ("default" in v) out[k] = v.default;
  const byFlag = {};
  for (const [k, v] of Object.entries(spec)) {
    byFlag["--" + k] = k;
    if (v.alias) byFlag["-" + v.alias] = k;
  }
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    const [flag, inline] = a.startsWith("--") && a.includes("=") ? a.split(/=(.*)/s) : [a, undefined];
    const key = byFlag[flag];
    if (!key) {
      if (a.startsWith("-") && a !== "-") throw new Error(`неизвестный флаг: ${a}`);
      out._.push(a);
      continue;
    }
    const t = spec[key].type || "string";
    if (t === "bool") out[key] = true;
    else {
      const val = inline ?? argv[++i];
      if (val === undefined) throw new Error(`флагу ${flag} нужно значение`);
      out[key] = t === "int" ? parseInt(val, 10) : val;
    }
  }
  return out;
}

export function ensureDir(p) {
  mkdirSync(p, { recursive: true });
  return p;
}
export function writeFile(p, data) {
  ensureDir(dirname(p));
  writeFileSync(p, data);
}
export function readJson(p) {
  return JSON.parse(readFileSync(p, "utf8"));
}
export function hash(data, len = 10) {
  return createHash("sha1").update(data).digest("hex").slice(0, len);
}
export function slugify(s) {
  return (
    String(s)
      .toLowerCase()
      .replace(/^https?:\/\/[^/]+/, "")
      .replace(/[^a-z0-9а-яё]+/gi, "-")
      .replace(/^-+|-+$/g, "") || "index"
  );
}
export { existsSync };
