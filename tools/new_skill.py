#!/usr/bin/env python3
"""Создать новый скилл из шаблона _template/skill-name.

  python3 tools/new_skill.py web-design wd-hero
  python3 tools/new_skill.py new-topic my-skill --title "My Skill"

Создаёт <тема>/skills/<имя>/ со всей структурой (SKILL.md, references/, examples/,
scripts/, assets/, evals/), подставляет имя и добавляет строку в README темы.
"""
import argparse
import re
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TEMPLATE = REPO / "_template" / "skill-name"
NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")

TOPIC_README = """# {topic}

TODO: о чём эта тема.

```
{topic}/
  skills/<skill-name>/   # скиллы этой темы (ставятся инсталлятором)
  harness/               # (опционально) правила, команды, хуки под агентов
```

## Скиллы

| Скилл | Что делает |
|---|---|
"""


def main():
    ap = argparse.ArgumentParser(description="Создать скилл из шаблона")
    ap.add_argument("topic", help="тема (папка верхнего уровня), например web-design")
    ap.add_argument("name", help="имя скилла, kebab-case, уникально во всём репо")
    ap.add_argument("--title", help="заголовок в SKILL.md (по умолчанию из имени)")
    a = ap.parse_args()

    for value, what in ((a.topic, "тема"), (a.name, "имя")):
        if not NAME_RE.match(value) or len(value) > 64:
            print(f"error: {what} '{value}' должно быть kebab-case до 64 символов", file=sys.stderr)
            return 2
    clash = list(REPO.glob(f"*/skills/{a.name}/SKILL.md"))
    if clash:
        print(f"error: скилл '{a.name}' уже есть: {clash[0].parent.relative_to(REPO)}", file=sys.stderr)
        return 1

    topic_dir = REPO / a.topic
    dest = topic_dir / "skills" / a.name
    title = a.title or a.name.replace("-", " ").title()

    shutil.copytree(TEMPLATE, dest, ignore=shutil.ignore_patterns("__pycache__", ".DS_Store"))
    md = dest / "SKILL.md"
    text = md.read_text(encoding="utf-8")
    text = text.replace("name: skill-name", f"name: {a.name}", 1).replace("# Skill Name", f"# {title}", 1)
    md.write_text(text, encoding="utf-8")
    rules = dest / "references" / "rules.md"
    rules.write_text(rules.read_text(encoding="utf-8").replace("Skill Name", title), encoding="utf-8")
    (topic_dir / "skills" / ".gitkeep").unlink(missing_ok=True)

    readme = topic_dir / "README.md"
    if not readme.exists():
        readme.write_text(TOPIC_README.format(topic=a.topic), encoding="utf-8")
        print(f"+ новая тема {a.topic}/ — добавь её в таблицу тем в корневом README.md")
    row = f"| [{a.name}](skills/{a.name}/) | TODO |"
    lines = readme.read_text(encoding="utf-8").splitlines()
    lines = [l for l in lines if not re.match(r"^\|\s*—\s*\|\s*пока пусто", l)]
    last_row = max((i for i, l in enumerate(lines) if l.startswith("|")), default=len(lines) - 1)
    lines.insert(last_row + 1, row)
    readme.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"+ {dest.relative_to(REPO)}/")
    print("Дальше: заполни TODO (начни с description), затем")
    print(f"  python3 tools/validate.py {dest.relative_to(REPO)} --strict")
    print(f"  ./install.sh install -s {a.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
