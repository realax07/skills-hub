#!/usr/bin/env python3
"""Роутинг: найти кейсы под задачу и пересобрать индексы слоя test-cases/.

  python3 route.py index <repo>
  python3 route.py find <repo> --cap order-cancellation
  python3 route.py find <repo> --path src/routes/orders.ts           # файл кода → кейсы (code:, автотесты, трассировка sa-scan)
  python3 route.py find <repo> --req SHOP-12 --tag smoke --priority high
  python3 route.py find <repo> --text "отмена оплаченного заказа" --limit 10
  python3 route.py find <repo> --section otmena-zakaza --status ready --json

Фильтры --cap/--req/--tag/--section/--status/--priority/--type/--unmapped складываются через «и»;
--path и --text ранжируют. Вывод: id, приоритет, статус, путь к файлу, название и почему кейс попал.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import indexer  # noqa: E402
import qa  # noqa: E402

PRI_ORDER = {p: i for i, p in enumerate(qa.PRIORITIES)}


def load_index(P):
    idx = qa.load_json(P.index_json)
    if not idx or idx.get("files_hash") != indexer.files_hash(P):
        qa.warn("индекс устарел или его нет — пересобираю (route.py index)")
        indexer.build(P, quiet=True)
        idx = qa.load_json(P.index_json)
    return idx


def path_match(code, p):
    code, p = code.strip("/"), p.strip("/")
    return code == p or p.startswith(code + "/") or code.startswith(p + "/")


def cmd_find(a):
    P = qa.Paths(a.repo)
    if not P.root.is_dir():
        qa.die(f"нет {qa.LAYER}/ — сначала fetch.py и build.py")
    idx = load_index(P)
    cases = idx["cases"]
    caps = idx.get("capabilities") or {}
    out = []
    for r in cases:
        why, score = [], 0.0
        if a.cap and not set(a.cap) & set(r["capabilities"]):
            continue
        if a.req and not any(q.lower() == x.lower() for q in a.req for x in r["requirements"]):
            continue
        if a.tag and not set(a.tag) & set(r["tags"]):
            continue
        if a.section and not (r["dir"] == a.section.strip("/") or r["dir"].startswith(a.section.strip("/") + "/")):
            continue
        if a.status and r["status"] not in a.status:
            continue
        if a.priority and r["priority"] not in a.priority:
            continue
        if a.type and r["type"] not in a.type:
            continue
        if a.id and r["id"] not in a.id and r["key"] not in a.id:
            continue
        if a.unmapped and r["capabilities"]:
            continue
        if a.cap:
            why.append("cap")
        if a.path:
            hit = False
            for p in a.path:
                if any(path_match(c, p) for c in r["code"]):
                    why.append(f"code {p}")
                    score += 3
                    hit = True
                if any(path_match(t.rsplit(":", 1)[0], p) for t in r["autotests"] if not t.startswith("ext:")):
                    why.append(f"автотест {p}")
                    score += 2
                    hit = True
                for c in r["capabilities"]:
                    files = (caps.get(c) or {}).get("files", []) + (caps.get(c) or {}).get("tests", [])
                    if any(path_match(f, p) for f in files):
                        why.append(f"{c} (trace)")
                        score += 1
                        hit = True
                        break
            if not hit:
                continue
        if a.text:
            q = set(qa.words(a.text))
            title = set(qa.words(r["title"] + " " + r["section"]))
            s = 3 * len(q & title)
            if s < 3 * len(q):
                c = qa.read_case(P.root / r["path"])
                body = set(qa.words(" ".join(x["action"] + " " + x["expected"] for x in c["steps"])
                                    + " " + " ".join(c["sections"].values())))
                s += len(q & body)
            if s == 0:
                continue
            score += s
            why.append(f"слова {s:g}")
        out.append((score, r, why))
    out.sort(key=lambda x: (-x[0], PRI_ORDER.get(x[1]["priority"], 9), x[1]["id"]))
    total = len(out)
    out = out[:a.limit]
    if a.json:
        print(json.dumps([{**r, "file": f"{qa.LAYER}/{r['path']}", "why": why, "score": s} for s, r, why in out], ensure_ascii=False, indent=1))
        return 0
    for s, r, why in out:
        extra = f"  [{'; '.join(why)}]" if why else ""
        print(f"{r['id']}  {r['priority']:<7} {r['status']:<10} {qa.LAYER}/{r['path']}  — {r['title']}{extra}")
    print(f"найдено: {total}" + (f", показано {len(out)} (--limit)" if total > len(out) else ""))
    if not total:
        print("ничего: ослабь фильтры или поищи словами (--text); по коду без trace.md и code: ищутся только автотесты")
    return 0


def cmd_index(a):
    P = qa.Paths(a.repo)
    if not P.root.is_dir():
        qa.die(f"нет {qa.LAYER}/ — сначала fetch.py и build.py")
    res = indexer.build(P)
    return 1 if res["errors"] else 0


def main():
    ap = argparse.ArgumentParser(description="Роутинг тест-кейсов", formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("index")
    p.add_argument("repo")
    p.set_defaults(func=cmd_index)
    p = sub.add_parser("find")
    p.add_argument("repo")
    for f in ("cap", "req", "tag", "path", "status", "priority", "type", "id"):
        p.add_argument(f"--{f}", action="append")
    p.add_argument("--section")
    p.add_argument("--text")
    p.add_argument("--unmapped", action="store_true")
    p.add_argument("--limit", type=int, default=40)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_find)
    a = ap.parse_args()
    return a.func(a) or 0


if __name__ == "__main__":
    sys.exit(main())
