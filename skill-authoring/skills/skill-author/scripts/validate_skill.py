#!/usr/bin/env python3
"""Проверить скилл: frontmatter, структура, ссылки, ресурсы, скрипты, evals, заглушки.

  python3 scripts/validate_skill.py path/to/my-skill
  python3 scripts/validate_skill.py path/to/my-skill --strict --run-scripts
  python3 scripts/validate_skill.py path/to/skills-dir --json   # все скиллы в папке

Правила — из спецификации Agent Skills (agentskills.io) и гайда skill-creator:
name/description и их лимиты, один SKILL.md, длина тела, битые ссылки, формат evals
(совместим с `claude plugin eval`). Сверху — проверки качества: упомянуты ли ресурсы
в SKILL.md, есть ли оглавление у длинных справочников, пример «плохо/хорошо»,
работает ли --help у скриптов (с --run-scripts).

Код выхода: 0 — ошибок нет (предупреждения допустимы), 1 — есть ошибки, 2 — нечего проверять.
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ALLOWED_KEYS = {"name", "description", "license", "allowed-tools", "metadata", "compatibility"}
SKIP_DIRS = {"__pycache__", "node_modules", ".git"}
RESERVED_CASES = {"results", "mocks", "node_modules", "files", "true", "false", "null"}
NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
CASE_RE = re.compile(r"^[a-z][a-z0-9-]*$")
BODY_LINES_LIMIT = 500
REFERENCE_TOC_LIMIT = 300
LINK_RE = re.compile(r"\]\(([^)#\s]+)(?:#[^)]*)?\)")
TICK_RE = re.compile(r"`((?:references|scripts|assets|examples)/[^`\s<>]*)`")
PLACEHOLDER_RE = re.compile(r"\{\{(name|title|script|run|env)\}\}")
STUB = "TO" + "DO"  # склеено, чтобы сам валидатор не считался заглушкой
TEXT_SUFFIXES = {".md", ".py", ".sh", ".yaml", ".yml", ".ps1", ".js", ".mjs", ".json", ".txt"}
WHEN_RE = re.compile(r"(?im)^#{1,6}\s+((?:когда\s+(?:применять|использовать|брать|вызывать)|when\s+to\s+use|use\s+when)\b.*)$")
TRIGGER_HINTS = ("когда", "используй", "применяй", "use when", "when ", "даже если", "trigger")


def parse_frontmatter(text):
    """Минимальный разбор YAML-frontmatter: ключ: значение, блоки | и >, вложенные ключи пропускаются."""
    if not text.startswith("---\n"):
        return None, "нет YAML-frontmatter (файл должен начинаться с ---)"
    end = text.find("\n---", 4)
    if end == -1:
        return None, "frontmatter не закрыт строкой ---"
    data, key, block = {}, None, None
    for line in text[4:end].splitlines():
        if block is not None:
            if line.startswith((" ", "\t")) or not line.strip():
                block.append(line.strip())
                data[key] = " ".join(x for x in block if x)
                continue
            block = None
        if not line.strip() or line.lstrip().startswith("#") or line.startswith((" ", "\t")):
            continue
        m = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", line)
        if not m:
            return None, f"не разобрать строку frontmatter: {line!r}"
        key, value = m.group(1), m.group(2).strip()
        if value in ("|", ">", "|-", ">-"):
            block, data[key] = [], ""
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        data[key] = value
    return data, text[end + 4:]


def skill_files(skill: Path):
    for f in sorted(skill.rglob("*")):
        if f.is_file() and not (set(f.relative_to(skill).parts) & SKIP_DIRS) and f.name != ".DS_Store":
            yield f


class Report:
    def __init__(self, path):
        self.path, self.errors, self.warnings = path, [], []

    def err(self, msg):
        self.errors.append(msg)

    def warn(self, msg):
        self.warnings.append(msg)

    def as_dict(self):
        return {"skill": str(self.path), "ok": not self.errors, "errors": self.errors, "warnings": self.warnings}


def check_frontmatter(skill: Path, fm: dict, r: Report):
    extra = set(fm) - ALLOWED_KEYS
    if extra:
        r.err(f"лишние ключи frontmatter: {', '.join(sorted(extra))} (можно: {', '.join(sorted(ALLOWED_KEYS))})")
    name, desc = fm.get("name", ""), fm.get("description", "")
    if not name:
        r.err("нет name")
    else:
        if not NAME_RE.match(name):
            r.err(f"name '{name}' должен быть kebab-case")
        if len(name) > 64:
            r.err(f"name длиннее 64 символов ({len(name)})")
        if name != skill.name:
            r.err(f"name '{name}' не совпадает с папкой '{skill.name}'")
    if not desc:
        r.err("нет description")
    else:
        if len(desc) > 1024:
            r.err(f"description длиннее 1024 символов ({len(desc)}) — агент проигнорирует скилл")
        if "<" in desc or ">" in desc:
            r.err("description не должен содержать угловые скобки")
        if len(desc) < 80:
            r.warn("description короткий: опиши не только что делает скилл, но и когда его брать")
        if not any(h in desc.lower() for h in TRIGGER_HINTS):
            r.warn("в description не видно, когда применять скилл (нет «используй, когда…» / «use when…»)")
    if len(fm.get("compatibility", "")) > 500:
        r.err("compatibility длиннее 500 символов")
    setup = [p for p in ("setup.mjs", "setup.py", "setup.sh", "setup.ps1") if (skill / "scripts" / p).is_file()]
    if setup and not fm.get("compatibility"):
        r.warn(f"есть scripts/{setup[0]}, но нет compatibility: опиши зависимости во frontmatter")
    if fm.get("compatibility") and not setup:
        r.warn("compatibility задан, но нет scripts/setup.* — дай установщик, чтобы скилл раскатывался на любую машину")


def check_body(skill: Path, body: str, r: Report):
    n = len(body.splitlines())
    if n > BODY_LINES_LIMIT:
        r.warn(f"тело SKILL.md {n} строк (> {BODY_LINES_LIMIT}): вынеси детали в references/")
    # условия срабатывания живут в description: тело грузится уже после решения брать скилл
    m = WHEN_RE.search(body)
    if m:
        r.warn(f"в теле раздел «{m.group(1).strip()}»: условия срабатывания перенеси в description, тело — только про выполнение")
    for target in sorted(set(LINK_RE.findall(body)) | set(TICK_RE.findall(body))):
        if re.match(r"^[a-z]+:", target):  # http:, mailto:
            continue
        if not (skill / target).exists():
            r.err(f"ссылка на несуществующий файл: {target}")
    # ресурсы, о которых SKILL.md молчит, агент не откроет
    for folder in ("references", "examples", "scripts", "assets"):
        d = skill / folder
        if not d.is_dir():
            continue
        entries = [p for p in d.iterdir() if p.name not in {".gitkeep", ".DS_Store", "__pycache__", "lib"}]
        if not entries:
            continue
        if f"{folder}/" not in body:
            r.warn(f"{folder}/ не упомянута в SKILL.md — агент не узнает, что там есть и когда открывать")
            continue
        if folder in ("references", "scripts"):
            for p in entries:
                if p.is_file() and p.name not in body:
                    r.warn(f"{folder}/{p.name} не упомянут в SKILL.md — укажи, когда его читать/запускать")


def check_resources(skill: Path, strict: bool, r: Report):
    nested = [p for p in skill.rglob("SKILL.md")
              if p != skill / "SKILL.md" and not (set(p.relative_to(skill).parts) & SKIP_DIRS)
              and p.relative_to(skill).parts[0] != "evals"]
    if nested:
        r.err("лишние SKILL.md внутри скилла: " + ", ".join(str(p.relative_to(skill)) for p in nested))
    for f in skill_files(skill):
        rel = f.relative_to(skill)
        if f.suffix not in TEXT_SUFFIXES:
            continue
        text = f.read_text(encoding="utf-8", errors="ignore")
        if STUB in text:
            (r.err if strict else r.warn)(f"заглушка {STUB}: {rel}")
        # плейсхолдеры шаблона init_skill.py: в готовом SKILL.md и evals их быть не должно
        if (rel.name == "SKILL.md" or rel.parts[0] == "evals") and PLACEHOLDER_RE.search(text):
            r.err(f"неподставленный плейсхолдер {PLACEHOLDER_RE.search(text).group(0)}: {rel}")
        if rel.parts[0] == "references" and f.suffix == ".md":
            lines = text.splitlines()
            if len(lines) > REFERENCE_TOC_LIMIT and not re.search(r"(?im)^#+\s*(оглавление|содержание|contents)", text):
                r.warn(f"{rel}: {len(lines)} строк без оглавления — добавь его, агент читает справочник кусками")
    examples = list((skill / "examples").glob("*.md")) if (skill / "examples").is_dir() else []
    if not examples:
        r.warn("нет examples/*.md — разобранный пример лучше всего калибрует качество")
    elif not any(re.search(r"(?im)^#+\s*(плохо|bad|неправильно)", e.read_text(encoding="utf-8")) for e in examples):
        r.warn("в examples/ нет пары «плохо / хорошо» для крайнего случая")


def check_scripts(skill: Path, r: Report):
    d = skill / "scripts"
    if not d.is_dir():
        return
    for f in sorted(d.iterdir()):
        if not f.is_file() or f.name.startswith("setup."):  # setup без аргументов ставит пакеты — не трогаем
            continue
        if f.suffix == ".py":
            cmd = [sys.executable, str(f), "--help"]
        elif f.suffix in {".mjs", ".js"}:
            cmd = ["node", str(f), "--help"]
        else:
            continue
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=30, cwd=skill)
        except FileNotFoundError:
            r.warn(f"scripts/{f.name}: не найден интерпретатор {cmd[0]}")
            continue
        except subprocess.TimeoutExpired:
            r.err(f"scripts/{f.name} --help висит дольше 30 с")
            continue
        if p.returncode != 0:
            tail = (p.stderr or p.stdout).strip().splitlines()[-1:] or [""]
            r.err(f"scripts/{f.name} --help завершился с кодом {p.returncode}: {tail[0]}")
        elif not (p.stdout or p.stderr).strip():
            r.warn(f"scripts/{f.name} --help ничего не печатает")


def check_evals(skill: Path, r: Report):
    evals = skill / "evals"
    if not evals.is_dir():
        r.warn("нет evals/ — добавь 2–3 тест-кейса (scripts/new_eval.py)")
        return
    cases = [d for d in evals.iterdir() if d.is_dir() and d.name not in {"results", "files"}]
    if not cases and not (evals / "evals.json").exists():
        r.warn("evals/ пустая")
    elif len(cases) < 2:
        r.warn("один тест-кейс — добавь ещё хотя бы один (крайний случай)")
    for case in cases:
        rel = f"evals/{case.name}"
        if not CASE_RE.match(case.name) or case.name in RESERVED_CASES:
            r.err(f"{rel}: недопустимое имя кейса")
        prompt = case / "prompt.md"
        if not prompt.is_file():
            r.err(f"{rel}: нет prompt.md")
        else:
            pt = prompt.read_text(encoding="utf-8")
            if not pt.startswith("---\n") or pt.find("\n---", 4) == -1:
                r.err(f"{rel}/prompt.md: нет блока настроек --- ... ---")
            elif not pt[pt.find("\n---", 4) + 4:].strip():
                r.err(f"{rel}/prompt.md: пустой запрос после блока настроек")
        cy = case / "case.yaml"
        if not cy.is_file():
            r.err(f"{rel}: нет case.yaml")
        else:
            t = cy.read_text(encoding="utf-8")
            if not re.search(r'^schema_version:\s*["\']', t, re.M):
                r.err(f"{rel}/case.yaml: schema_version должен быть в кавычках")
            m = re.search(r"^name:\s*(\S+)", t, re.M)
            if not m or m.group(1) != case.name:
                r.err(f"{rel}/case.yaml: name должен совпадать с именем папки")
            if "expected_outcome" not in t:
                r.err(f"{rel}/case.yaml: нет expected_outcome")
            m = re.search(r"scaffold_script:\s*(\S+)", t)
            if m and not (case / m.group(1)).is_file():
                r.err(f"{rel}: scaffold_script {m.group(1)} не найден")
            if (case / "files").is_dir() and not m:
                r.warn(f"{rel}: есть files/, но нет context.scaffold_script — файлы не попадут в тест")
        graders = list((case / "graders").glob("*.md")) if (case / "graders").is_dir() else []
        if not graders:
            r.err(f"{rel}: нет graders/*.md (кейс без грейдера не загрузится)")
        for g in graders:
            if not re.match(r"^---\n(.*\n)*?type:\s*\S+", g.read_text(encoding="utf-8")):
                r.err(f"{rel}/graders/{g.name}: нет блока --- type: ... ---")


def validate(skill: Path, strict: bool, run_scripts: bool) -> Report:
    r = Report(skill)
    md = skill / "SKILL.md"
    if not md.is_file():
        r.err("нет SKILL.md")
        return r
    fm, body = parse_frontmatter(md.read_text(encoding="utf-8"))
    if fm is None:
        r.err(body)
        return r
    check_frontmatter(skill, fm, r)
    check_body(skill, body, r)
    check_resources(skill, strict, r)
    if run_scripts:
        check_scripts(skill, r)
    check_evals(skill, r)
    return r


def find_skills(paths):
    out = []
    for p in paths:
        p = p.expanduser().resolve()
        if (p / "SKILL.md").is_file():
            out.append(p)
        else:
            out += sorted({s.parent for s in p.glob("*/SKILL.md")} | {s.parent for s in p.glob("*/skills/*/SKILL.md")}
                          | {s.parent for s in p.glob("skills/*/SKILL.md")})
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("paths", nargs="+", type=Path, help="папка скилла или папка со скиллами")
    ap.add_argument("--strict", action="store_true", help=f"заглушки {STUB} считать ошибками")
    ap.add_argument("--run-scripts", action="store_true", help="запустить scripts/* --help (кроме setup.*)")
    ap.add_argument("--json", action="store_true", help="вывод в JSON")
    a = ap.parse_args()

    skills = find_skills(a.paths)
    if not skills:
        print("скиллы не найдены (нужна папка с SKILL.md)", file=sys.stderr)
        return 2
    reports = [validate(s, a.strict, a.run_scripts) for s in skills]
    names = {}
    for s in skills:
        names.setdefault(s.name, []).append(s)
    dupes = {n: [str(p) for p in ps] for n, ps in names.items() if len(ps) > 1}
    total = sum(len(r.errors) for r in reports) + len(dupes)

    if a.json:
        print(json.dumps({"ok": total == 0, "errors": total, "duplicates": dupes,
                          "skills": [r.as_dict() for r in reports]}, ensure_ascii=False, indent=2))
    else:
        for r in reports:
            status = "FAIL" if r.errors else ("warn" if r.warnings else "ok")
            print(f"[{status}] {r.path}")
            for e in r.errors:
                print(f"   ✗ {e}")
            for w in r.warnings:
                print(f"   ! {w}")
        for n, ps in dupes.items():
            print(f"[FAIL] имя '{n}' повторяется: {', '.join(ps)}")
        print(f"\n{len(reports)} скилл(ов), ошибок: {total}")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
