#!/usr/bin/env node
// Установщик зависимостей скилла site-mockups.
//
//   node scripts/setup.mjs            поставить Playwright + Chromium (идемпотентно)
//   node scripts/setup.mjs --check    только проверить, ничего не ставить
//   node scripts/setup.mjs --with-deps  Linux: доставить системные библиотеки Chromium (нужен sudo)
//
// Ставит в кэш вне папки скилла (см. lib/runtime.mjs → depsHome):
//   macOS/Linux: ~/.cache/agent-skills/site-mockups
//   Windows:     %LOCALAPPDATA%\agent-skills\site-mockups
// Переопределить: SITE_MOCKUPS_HOME=<dir>, версию Playwright: SITE_MOCKUPS_PLAYWRIGHT=<ver>.
import { spawnSync } from "node:child_process";
import { existsSync, writeFileSync, mkdirSync } from "node:fs";
import { join } from "node:path";
import { depsHome, PLAYWRIGHT_VERSION } from "./lib/runtime.mjs";

const args = new Set(process.argv.slice(2));
const CHECK = args.has("--check");
const WITH_DEPS = args.has("--with-deps");
const home = depsHome();
const isWin = process.platform === "win32";
const npm = isWin ? "npm.cmd" : "npm";

function ok(m) { console.log("  ✓ " + m); }
function fail(m) { console.log("  ✗ " + m); }
function run(cmd, argv, opts = {}) {
  const r = spawnSync(cmd, argv, { stdio: "inherit", shell: isWin, ...opts });
  if (r.status !== 0) throw new Error(`команда упала: ${cmd} ${argv.join(" ")}`);
}

async function verify() {
  const { createRequire } = await import("node:module");
  let pw;
  try {
    pw = createRequire(join(home, "package.json"))("playwright");
  } catch {
    fail(`playwright не установлен в ${home}`);
    return false;
  }
  ok(`playwright ${pw.chromium ? "" : "(esm) "}найден в ${home}`);
  try {
    const browser = await pw.chromium.launch();
    const v = browser.version();
    await browser.close();
    ok(`chromium запускается (${v})`);
    return true;
  } catch (e) {
    fail("chromium не запускается: " + String(e.message).split("\n")[0]);
    return false;
  }
}

async function main() {
  console.log("site-mockups: зависимости");
  const [major] = process.versions.node.split(".").map(Number);
  if (major < 18) {
    fail(`нужен Node.js 18+, сейчас ${process.versions.node}. Установи с https://nodejs.org`);
    process.exit(1);
  }
  ok(`node ${process.versions.node}`);

  if (CHECK) process.exit((await verify()) ? 0 : 1);

  mkdirSync(home, { recursive: true });
  const pkg = join(home, "package.json");
  if (!existsSync(pkg)) {
    writeFileSync(pkg, JSON.stringify({ name: "site-mockups-deps", private: true }, null, 2));
  }
  console.log(`→ npm install playwright@${PLAYWRIGHT_VERSION} в ${home}`);
  run(npm, ["install", "--no-audit", "--no-fund", "--loglevel=error", `playwright@${PLAYWRIGHT_VERSION}`], { cwd: home });

  console.log("→ playwright install chromium" + (WITH_DEPS ? " --with-deps" : ""));
  const cli = join(home, "node_modules", "playwright", "cli.js");
  run(process.execPath, [cli, "install", "chromium", ...(WITH_DEPS ? ["--with-deps"] : [])], { cwd: home });

  if (!(await verify())) {
    if (process.platform === "linux" && !WITH_DEPS) {
      console.log("Похоже, не хватает системных библиотек. Запусти: node scripts/setup.mjs --with-deps");
    }
    process.exit(1);
  }
  console.log("Готово.");
}

main().catch((e) => {
  console.error("error: " + e.message);
  process.exit(1);
});
