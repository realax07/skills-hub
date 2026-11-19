#!/usr/bin/env python3
"""Указатель на системный контекст в файле инструкций проекта (AGENTS.md, CLAUDE.md…).

  python3 link.py <repo> --suggest
  python3 link.py <repo> --file AGENTS.md [--file CLAUDE.md]
  python3 link.py <repo> --file AGENTS.md --remove

Пишет короткий блок между метками <!-- sa-scan:start --> и <!-- sa-scan:end -->: когда открывать
system-context/GUIDE.md и как менять поведение через openspec/changes/. Текст вне меток не трогает.
"""
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import sa  # noqa: E402

START, END = "<!-- sa-scan:start -->", "<!-- sa-scan:end -->"
KNOWN = ["AGENTS.md", "CLAUDE.md", "GEMINI.md", "QWEN.md", ".github/copilot-instructions.md", "CONVENTIONS.md"]


def block(guide_rel, specs_rel):
    return "\n".join([
        START,
        "## Системный контекст и спецификации",
        "",
        f"Как сервис работает сейчас — требования и сценарии по возможностям в [`{specs_rel}/`]({specs_rel}/) (OpenSpec).",
        "Карта системы — входы, внешние сервисы, сущности и статусы, роли, глоссарий, требование → код, открытые вопросы —",
        f"в [`{guide_rel}`]({guide_rel}). Открой гайд, когда:",
        "",
        "- берёшь задачу на новую фичу или изменение поведения — найди затронутые возможности и их требования;",
        "- нужно понять, где в коде требование и какие тесты его проверяют;",
        "- трогаешь интеграцию, статусы, права или термины предметной области.",
        "",
        "Поведение меняй через `openspec/changes/<изменение>/` (proposal, дельта спеки, tasks), а не правкой основных спек.",
        "Требование с пометкой `(допущение: Q-…)` написано по догадке — сначала проверь вопрос в `QUESTIONS.md`.",
        END])


def cmd(a):
    P = sa.Paths(a.repo)
    if a.suggest:
        found = [f for f in KNOWN if (P.repo / f).is_file()]
        if not found:
            print("файлов инструкций нет — по умолчанию создать AGENTS.md (его читают большинство агентов)")
            return 0
        for f in found:
            text = (P.repo / f).read_text(encoding="utf-8", errors="replace")
            notes = []
            if START in text:
                notes.append("указатель уже есть")
            if f != "AGENTS.md" and "@AGENTS.md" in text:
                notes.append("подключает AGENTS.md — достаточно вписать в AGENTS.md")
            print(f"{f}" + (f"  ({'; '.join(notes)})" if notes else ""))
        print("рекомендация: " + ("AGENTS.md" if "AGENTS.md" in found else found[0]))
        return 0
    if not a.file:
        sa.die("укажи --file AGENTS.md (варианты: --suggest)")
    if not a.remove and not P.guide.is_file():
        sa.die(f"нет {P.rel(P.guide)} — сначала plan.py guide {a.repo}")
    for f in a.file:
        path = (P.repo / f).resolve()
        text = path.read_text(encoding="utf-8") if path.is_file() else ""
        i, j = text.find(START), text.find(END)
        if (i == -1) != (j == -1):
            print(f"! {f}: одна метка sa-scan без пары — файл не тронут, поправь вручную")
            continue
        if a.remove:
            if i == -1:
                print(f"{f}: блока нет")
                continue
            new = (text[:i].rstrip("\n") + "\n" + text[j + len(END):].lstrip("\n")).lstrip("\n")
            path.write_text(new, encoding="utf-8")
            print(f"✓ {f}: убран")
            continue
        guide_rel = Path(os.path.relpath(P.guide, path.parent)).as_posix()
        specs_rel = Path(os.path.relpath(P.specs, path.parent)).as_posix()
        b = block(guide_rel, specs_rel)
        if i != -1:
            new = text[:i] + b + text[j + len(END):]
            action = "без изменений" if new == text else "обновлён"
        else:
            new = (text.rstrip() + "\n\n" + b + "\n") if text.strip() else b + "\n"
            action = "добавлен" if text else "создан"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(new, encoding="utf-8")
        print(f"✓ {f}: {action}")
    return 0


def main():
    ap = argparse.ArgumentParser(description="Указатель на system-context в AGENTS.md и др.")
    ap.add_argument("repo")
    ap.add_argument("--suggest", action="store_true", help="какие файлы инструкций есть")
    ap.add_argument("--file", action="append", help="файл от корня репозитория (можно несколько)")
    ap.add_argument("--remove", action="store_true", help="убрать блок")
    return cmd(ap.parse_args())


if __name__ == "__main__":
    sys.exit(main())
