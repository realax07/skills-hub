#!/usr/bin/env node
// Зависимости скилла: Playwright + браузер Chromium.
//
//   node scripts/setup.mjs              проверить реальным запуском; ставить, только если не работает
//   node scripts/setup.mjs --check      только проверить (код 0 — готово, 1 — нет), ничего не ставить
//   node scripts/setup.mjs --force      поставить в кэш скиллов, даже если уже работает
//   node scripts/setup.mjs --with-deps  Linux: доставить системные библиотеки Chromium (нужен sudo)
//
// Проверка — не по путям: Playwright ищется так, как его найдёт Node в окружении агента (проект, глобальные пакеты,
// NODE_PATH, кэш скиллов), затем реально запускается браузер (скачанный Chromium, иначе системный Chrome или Edge).
// Работает — ставить нечего. Нет Playwright — ставится в кэш вне папки скилла:
//   macOS/Linux: ~/.cache/agent-skills/web-design (общий для набора wd-*)    Windows: %LOCALAPPDATA%\agent-skills\web-design
//   (переопределить: WD_HOME=<dir>; версия: WD_PLAYWRIGHT=<ver>).
// Playwright есть, а браузер не запускается — докачивается только браузер, той же версией Playwright.
import { spawnSync } from "node:child_process";
import { existsSync, writeFileSync, mkdirSync } from "node:fs";
import { join, basename, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { depsHome, probe, PLAYWRIGHT_VERSION } from "./lib/runtime.mjs";

const args = new Set(process.argv.slice(2));
const CHECK = args.has("--check");
const FORCE = args.has("--force");
const WITH_DEPS = args.has("--with-deps");
const SKILL = basename(dirname(dirname(fileURLToPath(import.meta.url))));
const isWin = process.platform === "win32";
const npm = isWin ? "npm.cmd" : "npm";

const ok = (m) => console.log("  ✓ " + m);
const fail = (m) => console.log("  ✗ " + m);
function run(cmd, argv, opts = {}) {
  const r = spawnSync(cmd, argv, { stdio: "inherit", shell: isWin, ...opts });
  if (r.status !== 0) throw new Error(`команда упала: ${cmd} ${argv.join(" ")}`);
}

async function report() {
  const r = await probe();
  if (r.found) ok(`playwright (${r.found.module}) — ${r.found.where}: ${r.found.dir}`);
  if (r.ok) ok(`браузер запускается: ${r.browser}`);
  else fail(r.error);
  return r;
}

function installBrowser(pwDir) {
  console.log("→ playwright install chromium" + (WITH_DEPS ? " --with-deps" : ""));
  run(process.execPath, [join(pwDir, "cli.js"), "install", "chromium", ...(WITH_DEPS ? ["--with-deps"] : [])]);
}

async function main() {
  console.log(`${SKILL}: зависимости`);
  const [major] = process.versions.node.split(".").map(Number);
  if (major < 18) {
    fail(`нужен Node.js 18+, сейчас ${process.versions.node}. Установи с https://nodejs.org`);
    process.exit(1);
  }
  ok(`node ${process.versions.node}`);

  const before = await report();
  if (CHECK) process.exit(before.ok ? 0 : 1);
  if (before.ok && !FORCE) { console.log("Готово: всё уже работает, ставить нечего."); return; }

  if (before.found && !FORCE) {
    // Playwright есть (проект, глобально, кэш), браузера нет — докачиваем только браузер его же CLI
    installBrowser(before.found.dir);
  } else {
    const home = depsHome();
    mkdirSync(home, { recursive: true });
    const pkg = join(home, "package.json");
    if (!existsSync(pkg)) writeFileSync(pkg, JSON.stringify({ name: "agent-skills-deps", private: true }, null, 2));
    console.log(`→ npm install playwright@${PLAYWRIGHT_VERSION} в ${home}`);
    run(npm, ["install", "--no-audit", "--no-fund", "--loglevel=error", `playwright@${PLAYWRIGHT_VERSION}`], { cwd: home });
    installBrowser(join(home, "node_modules", "playwright"));
  }

  console.log("→ проверка");
  const after = await report();
  if (!after.ok) {
    if (process.platform === "linux" && !WITH_DEPS) console.log("Похоже, не хватает системных библиотек. Запусти: node scripts/setup.mjs --with-deps");
    process.exit(1);
  }
  console.log("Готово.");
}

main().catch((e) => {
  console.error("error: " + e.message);
  process.exit(1);
});
