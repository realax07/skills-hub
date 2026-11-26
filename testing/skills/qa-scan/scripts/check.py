#!/usr/bin/env python3
"""Проверка слоя test-cases/: формат каждого кейса, ссылки, секреты, свежесть индексов, указатель.

  python3 check.py <repo> [--json] [--no-pointer]

✗ — ошибка (код возврата 1), ! — предупреждение. Запускай после импорта и после каждой правки кейсов:
md первичен, поэтому формат держит этот скрипт, а не TMS.
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import indexer  # noqa: E402
import qa  # noqa: E402

LINK = re.compile(r"\]\(((?:\.\./|\./|_shared/|_attachments/)[^)\s]+|[^):\s]+\.md)\)")
POINTER = "<!-- qa-scan:start -->"
INSTR = ["AGENTS.md", "CLAUDE.md", "GEMINI.md", "QWEN.md", ".github/copilot-instructions.md", "CONVENTIONS.md"]


def main():
    ap = argparse.ArgumentParser(description="Проверка слоя test-cases/")
    ap.add_argument("repo")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--no-pointer", action="store_true", help="не проверять указатель в AGENTS.md")
    a = ap.parse_args()
    P = qa.Paths(a.repo)
    err, warn = [], []
    if not P.root.is_dir():
        qa.die(f"нет {qa.LAYER}/ — сначала fetch.py и build.py")
    seen = {}
    files = P.case_files()
    shared_ids = set()
    for f in files:
        meta, _, e = qa.parse_meta(f.read_text(encoding="utf-8"))
        if not e and qa.SHARED_RE.match(str(meta.get("id") or "")):
            shared_ids.add(str(meta["id"]))
    for f in files:
        rel = P.rel(f)
        c = qa.read_case(f)
        if c["error"]:
            err.append(f"{rel}: {c['error']}")
            continue
        m = c["meta"]
        cid = str(m.get("id") or "")
        is_shared = bool(qa.SHARED_RE.match(cid))
        if not (qa.CASE_RE.match(cid) or is_shared):
            err.append(f"{rel}: id {cid!r} — ждал TC-0001 (кейс) или SS-001 (общий шаг)")
            continue
        if cid in seen:
            err.append(f"{rel}: id {cid} уже у {seen[cid]} — номер не переиспользуют, возьми следующий (new.py)")
        seen[cid] = rel
        if not f.name.startswith(cid + "-") and f.name != cid + ".md":
            err.append(f"{rel}: имя файла должно начинаться с {cid}-")
        if c["header_id"] != cid:
            err.append(f"{rel}: первый заголовок должен быть «# {cid} <название>»")
        req = ["id", "title"] if is_shared else qa.REQUIRED
        for k in req:
            if not str(m.get(k) or "").strip():
                err.append(f"{rel}: нет поля {k}")
        if not is_shared:
            if m.get("priority") and m["priority"] not in qa.PRIORITIES:
                warn.append(f"{rel}: priority {m['priority']!r} — не из {', '.join(qa.PRIORITIES)}")
            if m.get("status") and m["status"] not in qa.STATUSES:
                warn.append(f"{rel}: status {m['status']!r} — не из {', '.join(qa.STATUSES)}")
            if m.get("type") and m["type"] not in qa.TYPES:
                warn.append(f"{rel}: type {m['type']!r} — не из {', '.join(qa.TYPES)}")
            for k in qa.LIST_KEYS:
                if k in m and not isinstance(m[k], list):
                    err.append(f"{rel}: {k} должен быть списком: {k}: [a, b]")
        for u in c["unknown"]:
            if u.lower() not in ("заметки", "notes"):
                warn.append(f"{rel}: раздел «{u}» не из формата — агенты его прочтут, но индекс не разбирает")
        if "steps" in c["sections"] and c["sections"]["steps"].strip():
            nums = [s["n"] for s in c["steps"]]
            if not nums:
                err.append(f"{rel}: в «Шаги» нет нумерованных шагов «1. …»")
            elif nums != list(range(1, len(nums) + 1)):
                warn.append(f"{rel}: шаги пронумерованы не подряд: {nums[:10]}")
            for s in c["steps"]:
                if s.get("shared", "").startswith("SS-") and s["shared"] not in shared_ids:
                    err.append(f"{rel}: шаг {s['n']} ссылается на {s['shared']}, а такого общего шага нет")
        for link in LINK.findall(c["body"]):
            target = (f.parent / link.split("#")[0]).resolve()
            if not target.exists():
                err.append(f"{rel}: ссылка {link} никуда не ведёт")
        if "<!-- заполнить" in c["text"]:
            warn.append(f"{rel}: есть места «заполнить»")
        for kind, val, *_rest, secret in qa.find_sensitive(c["text"], pii=False):
            if secret:
                err.append(f"{rel}: похоже на секрет ({kind}) — замени на ссылку на переменную окружения, не храни значение в репозитории")
    incoming = P.source / "incoming"
    if incoming.is_dir():
        pend = sorted(x.stem for x in incoming.glob("*.md"))
        if pend:
            warn.append(f"неразобранные конфликты импорта: {', '.join(pend)} (QUESTIONS.md; build.py --accept/--keep)")
    idx = qa.load_json(P.index_json)
    if not idx:
        err.append("нет _index/index.json — route.py index")
    elif idx.get("files_hash") != indexer.files_hash(P):
        err.append("индексы устарели (кейсы правили после сборки) — route.py index")
    if not P.routing.is_file():
        err.append("нет ROUTING.md — route.py index")
    elif len(P.routing.read_text(encoding="utf-8")) > indexer.ROUTING_BUDGET * 1.5:
        warn.append("ROUTING.md длиннее бюджета (~3 тыс. токенов) — слабые модели прочтут его не целиком")
    if not a.no_pointer:
        has = [f for f in INSTR if (P.repo / f).is_file() and POINTER in (P.repo / f).read_text(encoding="utf-8", errors="replace")]
        if not has:
            warn.append("нет указателя на test-cases/ в AGENTS.md (link.py --file AGENTS.md) — агенты проекта не найдут кейсы")
        elif "AGENTS.md" in has and "CLAUDE.md" not in has:
            cm = P.repo / "CLAUDE.md"
            if not cm.is_file() or "@AGENTS.md" not in cm.read_text(encoding="utf-8", errors="replace"):
                warn.append("указатель только в AGENTS.md, а Claude Code читает CLAUDE.md — добавь в CLAUDE.md строку @AGENTS.md (link.py --file AGENTS.md создаст его сам)")
    n_cases = sum(1 for k in seen if k.startswith("TC-"))
    if a.json:
        print(json.dumps({"cases": n_cases, "errors": err, "warnings": warn}, ensure_ascii=False, indent=1))
    else:
        for e in err:
            print(f"✗ {e}")
        for w in warn:
            print(f"! {w}")
        print(f"{'✓' if not err else '✗'} кейсов {n_cases}, общих шагов {len(seen) - n_cases}: ошибок {len(err)}, предупреждений {len(warn)}")
    return 1 if err else 0


if __name__ == "__main__":
    sys.exit(main())
