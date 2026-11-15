#!/usr/bin/env python3
"""TODO: что делает скрипт (одна строка — её видно в --help).

Скрипты в скилле — для детерминированной или повторяющейся работы,
которую агент иначе писал бы заново каждый раз. Правила:
- только стандартная библиотека Python 3.9+ (или укажи зависимости в `compatibility` в SKILL.md);
- работает на macOS / Linux / Windows: пути через pathlib, без bash-специфики;
- понятный --help, ненулевой код выхода при ошибке;
- машиночитаемый вывод (--json), чтобы агенту было легко разобрать результат.

Пример: python3 scripts/example.py input.txt --json
"""
import argparse
import json
import sys
from pathlib import Path


def run(path: Path) -> dict:
    # TODO: настоящая логика
    text = path.read_text(encoding="utf-8")
    return {"file": str(path), "lines": len(text.splitlines()), "chars": len(text)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("input", type=Path, help="входной файл")
    parser.add_argument("--json", action="store_true", help="вывод в JSON")
    args = parser.parse_args()

    if not args.input.is_file():
        print(f"error: файл не найден: {args.input}", file=sys.stderr)
        return 1

    result = run(args.input)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        for key, value in result.items():
            print(f"{key}: {value}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
