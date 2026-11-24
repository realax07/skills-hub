#!/usr/bin/env python3
"""Указатель на тест-кейсы в файле инструкций проекта (AGENTS.md, CLAUDE.md…).

  python3 link.py <repo> --suggest
  python3 link.py <repo> --file AGENTS.md [--file CLAUDE.md]
  python3 link.py <repo> --file AGENTS.md --remove

Пишет блок между <!-- qa-scan:start --> и <!-- qa-scan:end -->: когда открывать test-cases/ROUTING.md,
как найти кейсы под задачу и как их менять. Текст вне меток не трогает.
"""
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import qa  # noqa: E402

START, END = "<!-- qa-scan:start -->", "<!-- qa-scan:end -->"
KNOWN = ["AGENTS.md", "CLAUDE.md", "GEMINI.md", "QWEN.md", ".github/copilot-instructions.md", "CONVENTIONS.md"]


def block(root_rel):
    r = root_rel
    return "\n".join([
        START,
        "## Тест-кейсы",
        "",
        f"Ручные и автоматизированные тест-кейсы — в `{r}/` (md первичен: кейсы правят здесь, а не в TMS).",
        "",
        "**Перед правкой поведения, интерфейса или API — по шагам:**",
        "",
        f"1. Открой `{r}/ROUTING.md`: там таблица «как найти кейсы под задачу».",
        f"2. Найди кейсы: по возможности — `{r}/_index/by-capability.md`; по файлу кода — "
        f"`grep -n \"<путь>\" {r}/_index/by-code.md`; по ключу задачи — `grep -n \"<КЛЮЧ>\" {r}/_index/by-requirement.md`;",
        f"   по словам — `grep -ril \"<слово>\" {r} --include=\"TC-*.md\"`.",
        "3. Прочитай найденные кейсы: шаги и «Ожидается» — это то, что не должно сломаться. Регресс после правки — по ним.",
        "4. Поведение изменилось намеренно — обнови шаги и ожидаемое в этих кейсах; новый сценарий — новый кейс",
        "   со следующим номером TC (id не меняй и не переиспользуй). Устарел — `status: deprecated`.",
        "5. `[скрыто: S-NN]` — секрет: не вписывай значение, бери из окружения.",
        f"6. `{r}/_index/`, `INDEX.md` и `ROUTING.md` руками не правь — их пересобирает qa-scan (`route.py index`, `check.py`).",
        END])


def main():
    ap = argparse.ArgumentParser(description="Указатель на test-cases/ в AGENTS.md и др.")
    ap.add_argument("repo")
    ap.add_argument("--suggest", action="store_true")
    ap.add_argument("--file", action="append")
    ap.add_argument("--remove", action="store_true")
    a = ap.parse_args()
    P = qa.Paths(a.repo)
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
            print(f + (f"  ({'; '.join(notes)})" if notes else ""))
        print("рекомендация: " + ("AGENTS.md" if "AGENTS.md" in found else found[0]))
        return 0
    if not a.file:
        qa.die("укажи --file AGENTS.md (варианты: --suggest)")
    if not a.remove and not P.routing.is_file():
        qa.die(f"нет {P.rel(P.routing)} — сначала build.py или route.py index")
    for f in a.file:
        path = (P.repo / f).resolve()
        text = path.read_text(encoding="utf-8") if path.is_file() else ""
        i, j = text.find(START), text.find(END)
        if (i == -1) != (j == -1):
            print(f"! {f}: одна метка qa-scan без пары — файл не тронут, поправь вручную")
            continue
        if a.remove:
            if i == -1:
                print(f"{f}: блока нет")
                continue
            path.write_text((text[:i].rstrip("\n") + "\n" + text[j + len(END):].lstrip("\n")).lstrip("\n"), encoding="utf-8")
            print(f"✓ {f}: убран")
            continue
        b = block(Path(os.path.relpath(P.root, path.parent)).as_posix())
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


if __name__ == "__main__":
    sys.exit(main())
