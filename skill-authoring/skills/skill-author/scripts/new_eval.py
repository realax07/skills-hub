#!/usr/bin/env python3
"""Добавить тест-кейс в evals/ скилла (формат совместим с `claude plugin eval`).

  python3 scripts/new_eval.py path/to/my-skill messy-csv-input \\
      --prompt "вот выгрузка из crm, сделай отчёт по продажам за квартал" \\
      --expect "Агент строит отчёт по кварталу, не падает на пустых строках" \\
      --grader "the report contains totals per month for July, August and September" \\
      --grader "rows with empty amount are skipped and the report says how many" \\
      --files ./fixtures/crm-export

Создаёт evals/<case>/prompt.md, case.yaml, graders/NN-<slug>.md; с --files копирует
входные файлы в files/, кладёт place-files.sh и прописывает context.scaffold_script.

Код выхода: 0 — создано, 1 — кейс уже есть / нет скилла, 2 — неверные аргументы.
"""
import argparse
import json
import re
import shutil
import sys
from pathlib import Path

CASE_RE = re.compile(r"^[a-z][a-z0-9-]*$")
RESERVED = {"results", "mocks", "node_modules", "files", "true", "false", "null"}
PLACE_FILES = '#!/usr/bin/env bash\n# Кладёт входные файлы кейса (files/) в рабочую папку теста.\nset -eu\ncp -R "$(dirname "$0")/files/." .\n'


def slug(text: str, n: int) -> str:
    words = re.findall(r"[a-z0-9]+", text.lower())
    s = "-".join(words)[:40].rstrip("-")
    return f"{n:02d}-{s or 'check'}"


def indent_block(text: str) -> str:
    return "\n".join("  " + line if line.strip() else "" for line in text.strip().splitlines())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("skill", type=Path, help="папка скилла (с SKILL.md)")
    ap.add_argument("case", help="имя кейса, kebab-case: что проверяет (messy-csv-input)")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--prompt", help="запрос пользователя — как его напишет живой человек")
    src.add_argument("--prompt-file", type=Path, help="файл с запросом")
    ap.add_argument("--expect", required=True, help="expected_outcome: как выглядит хороший результат")
    ap.add_argument("--grader", action="append", default=[], required=True,
                    help="одно проверяемое утверждение о результате (можно повторять)")
    ap.add_argument("--files", type=Path, help="папка с входными файлами кейса")
    ap.add_argument("--max-turns", type=int, default=30)
    ap.add_argument("--timeout", type=int, default=900, help="timeout_seconds")
    ap.add_argument("--tools", default="Read, Glob, Grep, Skill, Write, Edit, Bash", help="allowed_tools через запятую")
    ap.add_argument("--json", action="store_true", help="вывод в JSON")
    a = ap.parse_args()

    skill = a.skill.expanduser().resolve()
    if not (skill / "SKILL.md").is_file():
        print(f"error: {skill} — не скилл (нет SKILL.md)", file=sys.stderr)
        return 1
    if not CASE_RE.match(a.case) or a.case in RESERVED:
        print(f"error: имя кейса '{a.case}' — kebab-case с буквы, не из {sorted(RESERVED)}", file=sys.stderr)
        return 2
    case = skill / "evals" / a.case
    if case.exists():
        print(f"error: кейс уже есть: {case}", file=sys.stderr)
        return 1
    if a.files and not a.files.is_dir():
        print(f"error: --files не папка: {a.files}", file=sys.stderr)
        return 2
    prompt = a.prompt if a.prompt is not None else a.prompt_file.read_text(encoding="utf-8")
    if not prompt.strip():
        print("error: пустой запрос", file=sys.stderr)
        return 2

    (case / "graders").mkdir(parents=True)
    created = []

    if a.files:
        shutil.copytree(a.files, case / "files", ignore=shutil.ignore_patterns(".DS_Store", "__pycache__"))
        listed = sorted(str(p.relative_to(case / "files")) for p in (case / "files").rglob("*") if p.is_file())
        prompt = prompt.rstrip() + "\n\nInput files: " + ", ".join(listed)
        pf = case / "place-files.sh"
        pf.write_text(PLACE_FILES, encoding="utf-8")
        pf.chmod(0o755)
        created.append(pf)

    tools = ", ".join(t.strip() for t in a.tools.split(",") if t.strip())
    skill_name = skill.name
    (case / "prompt.md").write_text(
        f"---\ntags: [{skill_name}]\nmax_turns: {a.max_turns}\ntimeout_seconds: {a.timeout}\n"
        f"allowed_tools: [{tools}]\n---\n\n{prompt.strip()}\n", encoding="utf-8")
    context = "context:\n  scaffold_script: place-files.sh\n" if a.files else ""
    (case / "case.yaml").write_text(
        f'schema_version: "1.1"\nname: {a.case}\n{context}expected_outcome: |\n{indent_block(a.expect)}\n',
        encoding="utf-8")
    created += [case / "prompt.md", case / "case.yaml"]
    for i, claim in enumerate(a.grader, 1):
        g = case / "graders" / f"{slug(claim, i)}.md"
        g.write_text(f"---\ntype: llm\nfocus: trace\nweight: 1\n---\n\n{claim.strip()}\n", encoding="utf-8")
        created.append(g)

    files = [str(p.relative_to(skill)) for p in created]
    if a.json:
        print(json.dumps({"case": str(case), "files": files}, ensure_ascii=False, indent=2))
    else:
        print(f"+ {case}")
        for f in files:
            print(f"  {f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
