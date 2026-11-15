// Общие утилиты: где лежат зависимости скилла и как загрузить Playwright.
import { createRequire } from "node:module";
import { existsSync, mkdirSync, writeFileSync, readFileSync } from "node:fs";
import { join, dirname, resolve } from "node:path";
import { homedir } from "node:os";
import { createHash } from "node:crypto";

export const PLAYWRIGHT_VERSION = process.env.SITE_MOCKUPS_PLAYWRIGHT || "1.65.1";

// Кэш зависимостей вне папки скилла: скилл может быть симлинком в git-репо
// или read-only копией, а node_modules туда класть нельзя.
export function depsHome() {
  if (process.env.SITE_MOCKUPS_HOME) return resolve(process.env.SITE_MOCKUPS_HOME);
  const base =
    process.platform === "win32"
      ? process.env.LOCALAPPDATA || join(homedir(), "AppData", "Local")
      : process.env.XDG_CACHE_HOME || join(homedir(), ".cache");
  return join(base, "agent-skills", "site-mockups");
}

// Ищем playwright: сначала в кэше скилла, потом в проекте пользователя (cwd).
export async function loadPlaywright() {
  const candidates = [join(depsHome(), "package.json"), join(process.cwd(), "package.json")];
  for (const c of candidates) {
    try {
      const req = createRequire(c);
      const mod = req("playwright");
      return mod.chromium ? mod : mod.default;
    } catch {}
  }
  console.error(
    "error: Playwright не найден. Установи зависимости скилла:\n" +
      "  node scripts/setup.mjs\n" +
      "(или задай SITE_MOCKUPS_HOME, если зависимости стоят в другом месте)"
  );
  process.exit(3);
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
