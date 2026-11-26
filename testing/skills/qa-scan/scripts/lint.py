#!/usr/bin/env python3
"""Отчёт о качестве кейсов → test-cases/QUALITY.md. Ничего в кейсах не меняет.

  python3 lint.py <repo> [--json]

Ищет: нет шагов, шаги без ожидаемого результата, размытое ожидаемое («работает», «корректно»), дубли (одинаковое
название в папке или одинаковые шаги), очень длинные кейсы, картинки-ссылки на TMS (модель их не увидит),
устаревшие, скрытые секреты. Это материал для человека: переписывать кейсы скилл не должен.
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import qa  # noqa: E402

VAGUE = re.compile(r"(?i)^\s*(ok|ок|работает|всё работает|все работает|корректно|успешно|верно|как ожидается|без ошибок|"
                   r"отображается корректно|всё ок|все ок|works|works fine|as expected|correct|success|passed|—|-)\s*\.?\s*$")
VAGUE_STEP = re.compile(r"(?i)^\s*(проверить,? что всё работает|проверить работу|проверить|check|verify)\s*\.?\s*$")
TMS_IMG = re.compile(r"!\[[^\]]*\]\((?!\.\.?/|_attachments)[^)]*\)")
LONG = 25

CHECKS = [
    ("no_steps", "Нет шагов", "Кейс без шагов и без ожидаемого результата — проверять нечего."),
    ("no_expected", "Есть шаги без ожидаемого результата", "У части шагов нет «Ожидается», и общего ожидаемого результата нет — что проверять на этих шагах?"),
    ("vague", "Размытое ожидаемое", "«Работает», «корректно» — агент не поймёт, что именно проверить."),
    ("vague_step", "Размытый шаг", "«Проверить» без того, что именно проверить."),
    ("dup_title", "Одинаковые названия в одной папке", "Возможно, дубли."),
    ("dup_steps", "Одинаковые шаги", "Тексты шагов совпадают — возможно, дубли или копия без правок."),
    ("long", f"Длинные (больше {LONG} шагов)", "Такие кейсы лучше разбить: агенту трудно держать их целиком."),
    ("tms_image", "Картинки со ссылкой на TMS", "Ссылка ведёт в TMS: без входа и без зрения модель картинку не увидит — опиши словами."),
    ("deprecated", "Устаревшие", "status: deprecated — не используй для проверки, пока человек не решит."),
    ("secret", "Скрытые секреты", "[скрыто: S-NN] — тесту нужно настоящее значение из окружения (см. QUESTIONS.md)."),
    ("copy", "Похоже на копию", "Название начинается с «Копия», «Copy of» — проверь, нужен ли кейс."),
]


def main():
    ap = argparse.ArgumentParser(description="Качество тест-кейсов → QUALITY.md")
    ap.add_argument("repo")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    P = qa.Paths(a.repo)
    files = [f for f in P.case_files() if f.name.startswith("TC-")]
    if not files:
        qa.die("кейсов нет — сначала fetch.py и build.py")
    found = {k: [] for k, _, _ in CHECKS}
    titles, sigs = {}, {}
    for f in files:
        c = qa.read_case(f)
        tid = str(c["meta"].get("id") or f.stem)
        steps = c["steps"]
        overall = c["sections"].get("expected", "")
        if not steps and not overall:
            found["no_steps"].append(tid)
        own = [s for s in steps if not s.get("shared") and "```gherkin" not in s["action"]]  # BDD: ожидаемое внутри Then
        if own and not overall and str(c["meta"].get("type")) != "checklist" and any(not s["expected"] for s in own):
            found["no_expected"].append(tid)
        if any(VAGUE.match(s["expected"]) for s in steps if s["expected"]) or (overall and VAGUE.match(overall)):
            found["vague"].append(tid)
        if any(VAGUE_STEP.match(s["action"]) for s in steps):
            found["vague_step"].append(tid)
        if len(steps) > LONG:
            found["long"].append(tid)
        if TMS_IMG.search(c["body"]):
            found["tms_image"].append(tid)
        if str(c["meta"].get("status")) == "deprecated":
            found["deprecated"].append(tid)
        if "[скрыто:" in c["text"]:
            found["secret"].append(tid)
        title = str(c["meta"].get("title") or "")
        if re.match(r"(?i)^(копия|copy of|клон|clone)\b", title):
            found["copy"].append(tid)
        key = (f.parent.as_posix(), re.sub(r"\W+", " ", title.lower()).strip())
        titles.setdefault(key, []).append(tid)
        if len(own) >= 1:
            sig = tuple(" ".join(qa.words(s["action"] + " " + s["expected"])) for s in own)
            if any(sig):
                sigs.setdefault(sig, []).append(tid)
    for ids in titles.values():
        if len(ids) > 1:
            found["dup_title"].append(" = ".join(ids))
    for ids in sigs.values():
        if len(ids) > 1:
            found["dup_steps"].append(" = ".join(ids))
    if a.json:
        print(json.dumps(found, ensure_ascii=False, indent=1))
    L = ["# Качество тест-кейсов", "", "<!-- собирает qa-scan (lint.py) — руками не правь; кейсы правит человек -->", "",
         f"Проверено кейсов: {len(files)}. Отчёт — для человека: скилл кейсы не переписывает.", "",
         "| Проверка | Кейсов |", "|---|---|"]
    for k, title, _ in CHECKS:
        L.append(f"| {title} | {len(found[k])} |")
    L.append("")
    for k, title, why in CHECKS:
        if found[k]:
            L += [f"## {title} ({len(found[k])})", "", why, ""]
            items = found[k]
            L.append(", ".join(items[:200]) + (f" … и ещё {len(items) - 200}" if len(items) > 200 else ""))
            L.append("")
    qa.write_if_changed(P.quality, "\n".join(L))
    if not a.json:
        bad = {title: len(found[k]) for k, title, _ in CHECKS if found[k]}
        print(f"✓ {P.rel(P.quality)}: " + (", ".join(f"{t.lower()} {n}" for t, n in bad.items()) if bad else "замечаний нет"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
