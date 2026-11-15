#!/usr/bin/env python3
"""Проверка скиллов skills-hub: frontmatter, структура, ссылки, evals, уникальность имён.

  python3 tools/validate.py                      # все скиллы репо + шаблон
  python3 tools/validate.py design-sites         # одна тема
  python3 tools/validate.py design-sites/skills/hero-section
  python3 tools/validate.py --strict             # TODO-заглушки = ошибка

Только стандартная библиотека. Правила взяты из спецификации Agent Skills
и skill-creator (name/description, лимиты, один SKILL.md, формат evals).
"""
import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ALLOWED_KEYS = {"name", "description", "license", "allowed-tools", "metadata", "compatibility"}
SKIP_DIRS = {"__pycache__", "node_modules", ".git"}
RESERVED_CASES = {"results", "mocks", "node_modules", "files", "true", "false", "null"}
NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
CASE_RE = re.compile(r"^[a-z][a-z0-9-]*$")
BODY_LINES_LIMIT = 500
# ссылки на ресурсы скилла: [текст](path) и `path` с известными папками
LINK_RE = re.compile(r"\]\(([^)#\s]+)(?:#[^)]*)?\)")
TICK_RE = re.compile(r"`((?:references|scripts|assets|examples)/[^`\s<>]*)`")


def parse_frontmatter(text):
    """Минимальный разбор YAML-frontmatter (ключ: значение, блоки | и >, вложенный metadata)."""
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
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line.startswith((" ", "\t")):  # вложенные ключи (metadata)
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


class Report:
    def __init__(self, path):
        self.path, self.errors, self.warnings = path, [], []

    def err(self, msg):
        self.errors.append(msg)

    def warn(self, msg):
        self.warnings.append(msg)


def check_evals(skill: Path, r: Report):
    evals = skill / "evals"
    if not evals.is_dir():
        r.warn("нет evals/ — добавь хотя бы один тест-кейс (см. docs/skill-guide.md)")
        return
    cases = [d for d in evals.iterdir() if d.is_dir() and d.name not in {"results", "files"}]
    if not cases and not (evals / "evals.json").exists():
        r.warn("evals/ пустая")
    for case in cases:
        rel = f"evals/{case.name}"
        if not CASE_RE.match(case.name) or case.name in RESERVED_CASES:
            r.err(f"{rel}: недопустимое имя кейса")
        prompt = case / "prompt.md"
        if not prompt.is_file():
            r.err(f"{rel}: нет prompt.md")
        elif not prompt.read_text(encoding="utf-8").startswith("---\n"):
            r.err(f"{rel}/prompt.md: нет блока настроек --- ... ---")
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
        graders = list((case / "graders").glob("*.md")) if (case / "graders").is_dir() else []
        if not graders:
            r.err(f"{rel}: нет graders/*.md (кейс без грейдера не загрузится)")
        for g in graders:
            if not re.match(r"^---\n(.*\n)*?type:\s*\S+", g.read_text(encoding="utf-8")):
                r.err(f"{rel}/graders/{g.name}: нет блока --- type: ... ---")


def validate(skill: Path, strict: bool) -> Report:
    r = Report(skill)
    md = skill / "SKILL.md"
    if not md.is_file():
        r.err("нет SKILL.md")
        return r
    text = md.read_text(encoding="utf-8")
    fm, body = parse_frontmatter(text)
    if fm is None:
        r.err(body)
        return r

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
    if len(fm.get("compatibility", "")) > 500:
        r.err("compatibility длиннее 500 символов")

    nested = [p for p in skill.rglob("SKILL.md")
              if p != md and not (set(p.relative_to(skill).parts) & SKIP_DIRS)
              and p.relative_to(skill).parts[0] != "evals"]
    if nested:
        r.err("лишние SKILL.md внутри скилла: " + ", ".join(str(p.relative_to(skill)) for p in nested))

    n = len(body.splitlines())
    if n > BODY_LINES_LIMIT:
        r.warn(f"SKILL.md {n} строк (> {BODY_LINES_LIMIT}): вынеси детали в references/")

    for target in set(LINK_RE.findall(body)) | set(TICK_RE.findall(body)):
        if re.match(r"^[a-z]+:", target):  # http:, mailto:
            continue
        if not (skill / target).exists():
            r.err(f"ссылка на несуществующий файл: {target}")

    for f in skill.rglob("*"):
        if f.is_file() and f.suffix in {".md", ".py", ".sh", ".yaml", ".ps1"} \
                and not (set(f.relative_to(skill).parts) & SKIP_DIRS):
            if "TODO" in f.read_text(encoding="utf-8", errors="ignore"):
                (r.err if strict else r.warn)(f"TODO-заглушка: {f.relative_to(skill)}")

    check_evals(skill, r)
    return r


def find_skills(args):
    if not args:
        found = sorted(REPO.glob("*/skills/*/SKILL.md")) + sorted(REPO.glob("_template/*/SKILL.md"))
        return [p.parent for p in found if not p.parent.parent.parent.name.startswith(".")]
    out = []
    for a in args:
        p = Path(a).resolve()
        if (p / "SKILL.md").is_file():
            out.append(p)
        else:
            out += [s.parent for s in sorted(p.glob("skills/*/SKILL.md"))]
    return out


def main():
    ap = argparse.ArgumentParser(description="Проверка скиллов skills-hub")
    ap.add_argument("paths", nargs="*", help="скилл, тема или пусто = всё")
    ap.add_argument("--strict", action="store_true", help="TODO-заглушки считать ошибками")
    a = ap.parse_args()

    skills = find_skills(a.paths)
    if not skills:
        print("скиллы не найдены")
        return 1
    total_err = 0
    names = {}
    for s in skills:
        is_template = s.parent.name == "_template"
        r = validate(s, a.strict and not is_template)
        if is_template:  # в шаблоне TODO — норма
            r.warnings = [w for w in r.warnings if not w.startswith("TODO")]
        else:
            names.setdefault(s.name, []).append(s)
        rel = s.relative_to(REPO) if s.is_relative_to(REPO) else s
        status = "FAIL" if r.errors else ("warn" if r.warnings else "ok")
        print(f"[{status}] {rel}")
        for e in r.errors:
            print(f"   ✗ {e}")
        for w in r.warnings:
            print(f"   ! {w}")
        total_err += len(r.errors)
    if not a.paths:
        for n, paths in names.items():
            if len(paths) > 1:
                print(f"[FAIL] имя '{n}' повторяется: " + ", ".join(str(p.relative_to(REPO)) for p in paths))
                total_err += 1
    print(f"\n{len(skills)} скилл(ов), ошибок: {total_err}")
    return 1 if total_err else 0


if __name__ == "__main__":
    sys.exit(main())
