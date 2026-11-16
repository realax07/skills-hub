#!/usr/bin/env python3
"""Создать каркас скилла со всей структурой: SKILL.md, references/, examples/, scripts/, assets/, evals/.

  python3 scripts/init_skill.py csv-report --dest ~/.claude/skills
  python3 scripts/init_skill.py csv-report --dest . --lang node --setup node
  python3 scripts/init_skill.py csv-report --topic data            # внутри репо-хаба скиллов

Шаблоны берутся из assets/skeleton/ и assets/extras/ этого скилла (файлы *.tmpl),
плейсхолдеры {{name}} {{title}} {{script}} {{run}} {{env}} подставляются.

Режим хаба: если текущая папка (или её родитель) — репо-хаб скиллов (есть agents.conf
и папки <тема>/skills/), скилл кладётся в <тема>/skills/<имя>/, имя проверяется на
уникальность во всём хабе и в README темы добавляется строка.

Код выхода: 0 — создано, 1 — конфликт (папка/имя уже есть), 2 — неверные аргументы.
"""
import argparse
import json
import re
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
SKELETON = HERE / "assets" / "skeleton"
EXTRAS = HERE / "assets" / "extras"
STUB = "TO" + "DO"  # склеено, чтобы валидатор не считал этот файл заглушкой
NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")

TOPIC_README = """# {topic}

Скиллы темы {topic}.

```
{topic}/
  skills/<skill-name>/   # скиллы этой темы (ставятся инсталлятором)
```

## Скиллы

| Скилл | Что делает |
|---|---|
"""


def find_hub(start: Path):
    """Корень репо-хаба скиллов: папка с agents.conf и хотя бы одной <тема>/skills/."""
    for d in [start, *start.parents]:
        if (d / "agents.conf").is_file() and (any(d.glob("*/skills")) or (d / "_template").is_dir()):
            return d
    return None


def render(text: str, ctx: dict) -> str:
    for key, value in ctx.items():
        text = text.replace("{{" + key + "}}", value)
    return text


def write(src: Path, dst: Path, ctx: dict, created: list, transform=None):
    dst.parent.mkdir(parents=True, exist_ok=True)
    text = src.read_text(encoding="utf-8")
    if transform:
        text = transform(text)
    dst.write_text(render(text, ctx), encoding="utf-8")
    if dst.suffix in {".py", ".mjs", ".sh"}:
        dst.chmod(0o755)
    created.append(dst)


def skill_md_transform(lang: str, setup):
    """Подогнать шаблон SKILL.md под флаги, пока плейсхолдеры ещё не подставлены."""
    def transform(text: str) -> str:
        if lang == "none":  # без скрипта — убрать строки про него, чтобы не было битых ссылок
            text = "\n".join(l.replace(" Детерминированную работу отдай скрипту:", "")
                             for l in text.splitlines()
                             if "{{run}}" not in l and "{{script}}" not in l) + "\n"
        if setup:
            cmd = "python3 scripts/setup.py" if setup == "py" else "node scripts/setup.mjs"
            compat = "compatibility: " + STUB + " — рантайм, пакеты, сколько весит, куда ставится."
            if re.search(r"(?m)^# compatibility:.*$", text):  # раскомментировать подсказку из шаблона
                text = re.sub(r"(?m)^# compatibility:.*$", compat, text, count=1)
            else:
                text = text.replace("\n---\n", "\n" + compat + "\n---\n", 1)
            text = text.replace("1. **Понять задачу.**",
                                f"1. **Зависимости.** `{cmd} --check`; если не ок — `{cmd}` (ставит вне папки скилла).\n"
                                "2. **Понять задачу.**", 1).replace("2. **Сделать.**", "3. **Сделать.**", 1) \
                       .replace("3. **Проверить результат.**", "4. **Проверить результат.**", 1)
            name = "setup.py" if setup == "py" else "setup.mjs"
            text = text.replace("| `assets/template.md` |",
                                f"| `scripts/{name}` | установщик зависимостей, `--check` — проверка | первым шагом |\n"
                                "| `assets/template.md` |", 1)
        return text
    return transform


def add_readme_row(topic_dir: Path, name: str, messages: list):
    readme = topic_dir / "README.md"
    if not readme.exists():
        readme.write_text(TOPIC_README.format(topic=topic_dir.name), encoding="utf-8")
        messages.append(f"новая тема {topic_dir.name}/ — добавь её в таблицу тем в корневом README.md")
    lines = readme.read_text(encoding="utf-8").splitlines()
    if any(f"[{name}]" in l for l in lines):
        return
    row = f"| [{name}](skills/{name}/) | (описание — заполни) |"
    last_row = max((i for i, l in enumerate(lines) if l.startswith("|")), default=len(lines) - 1)
    lines.insert(last_row + 1, row)
    readme.write_text("\n".join(lines) + "\n", encoding="utf-8")
    messages.append(f"в {readme.name} темы добавлена строка — впиши описание")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("name", help="имя скилла: kebab-case, до 64 символов, = имя папки")
    ap.add_argument("--dest", type=Path, help="папка, в которой создать <name>/ (вне хаба обязательно)")
    ap.add_argument("--topic", help="тема в репо-хабе: скилл ляжет в <тема>/skills/<name>/")
    ap.add_argument("--title", help="заголовок в SKILL.md (по умолчанию из имени)")
    ap.add_argument("--lang", choices=["py", "node", "none"], default="py",
                    help="язык стартового скрипта в scripts/ (none — без скрипта)")
    ap.add_argument("--script", default="main", help="имя стартового скрипта без расширения (по умолчанию main)")
    ap.add_argument("--setup", choices=["py", "node"], help="добавить scripts/setup.* для внешних зависимостей")
    ap.add_argument("--evals-files", action="store_true", help="добавить в тест-кейс files/ и place-files.sh")
    ap.add_argument("--json", action="store_true", help="вывод в JSON")
    a = ap.parse_args()

    if not NAME_RE.match(a.name) or len(a.name) > 64:
        print(f"error: имя '{a.name}' должно быть kebab-case до 64 символов", file=sys.stderr)
        return 2
    if not NAME_RE.match(a.script.replace("_", "-")):
        print(f"error: имя скрипта '{a.script}' — латиница, цифры, - и _", file=sys.stderr)
        return 2

    messages = []
    hub = None if a.dest else find_hub(Path.cwd())
    if hub:
        if not a.topic:
            topics = sorted(p.parent.name for p in hub.glob("*/skills") if not p.parent.name.startswith((".", "_")))
            print(f"error: это репо-хаб скиллов ({hub}); укажи --topic (есть: {', '.join(topics) or 'нет'})"
                  " или --dest, чтобы положить скилл в другое место", file=sys.stderr)
            return 2
        if not NAME_RE.match(a.topic):
            print(f"error: тема '{a.topic}' должна быть kebab-case", file=sys.stderr)
            return 2
        clash = list(hub.glob(f"*/skills/{a.name}/SKILL.md"))
        if clash:
            print(f"error: скилл '{a.name}' уже есть: {clash[0].parent.relative_to(hub)} "
                  "(агенты кладут скиллы в одну плоскую папку — имена уникальны)", file=sys.stderr)
            return 1
        parent = hub / a.topic / "skills"
    elif a.dest:
        parent = a.dest.expanduser()
    else:
        print("error: укажи --dest <папка> (например, папку скиллов агента или проекта)", file=sys.stderr)
        return 2

    dest = (parent / a.name).resolve()
    if dest.exists() and any(dest.iterdir()):
        print(f"error: {dest} уже существует и не пуста — улучшай существующий скилл, а не пересоздавай", file=sys.stderr)
        return 1

    ext = {"py": ".py", "node": ".mjs"}.get(a.lang, "")
    script = a.script + ext
    ctx = {
        "name": a.name,
        "title": a.title or a.name.replace("-", " ").title(),
        "script": script,
        "run": {"py": f"python3 scripts/{script}", "node": f"node scripts/{script}"}.get(a.lang, ""),
        "env": a.name.upper().replace("-", "_"),
    }

    created = []
    for src in sorted(SKELETON.rglob("*.tmpl")):
        rel = src.relative_to(SKELETON).with_suffix("")  # SKILL.md.tmpl -> SKILL.md
        if rel.parts[0] == "scripts":
            continue
        tf = skill_md_transform(a.lang, a.setup) if rel.name == "SKILL.md" else None
        write(src, dest / rel, ctx, created, tf)
    if a.lang == "py":
        write(SKELETON / "scripts" / "main.py.tmpl", dest / "scripts" / script, ctx, created)
    elif a.lang == "node":
        write(EXTRAS / "main.mjs.tmpl", dest / "scripts" / script, ctx, created)
    if a.setup:
        name = f"setup.{'py' if a.setup == 'py' else 'mjs'}"
        write(EXTRAS / f"{name}.tmpl", dest / "scripts" / name, ctx, created)
        messages.append(f"добавлен scripts/{name}: впиши пакеты и заполни compatibility во frontmatter")
    if a.evals_files:
        case = dest / "evals" / "basic-usage"
        write(EXTRAS / "place-files.sh.tmpl", case / "place-files.sh", ctx, created)
        (case / "files").mkdir(exist_ok=True)
        cy = case / "case.yaml"
        cy.write_text(cy.read_text(encoding="utf-8").replace(
            "name: basic-usage\n", "name: basic-usage\ncontext:\n  scaffold_script: place-files.sh\n"), encoding="utf-8")
    for d in ("references", "examples", "scripts", "assets"):
        (dest / d).mkdir(parents=True, exist_ok=True)

    if hub:
        add_readme_row(hub / a.topic, a.name, messages)

    result = {
        "skill": str(dest),
        "hub": str(hub) if hub else None,
        "files": [str(p.relative_to(dest)) for p in created],
        "notes": messages,
    }
    if a.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"+ {dest}")
        for f in result["files"]:
            print(f"  {f}")
        for m in messages:
            print(f"! {m}")
        print("Дальше: заполни заглушки (начни с description), затем")
        print(f"  python3 {HERE / 'scripts' / 'validate_skill.py'} {dest} --strict")
    return 0


if __name__ == "__main__":
    sys.exit(main())
