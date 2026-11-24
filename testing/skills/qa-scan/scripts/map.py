#!/usr/bin/env python3
"""Сопоставить кейсы с возможностями sa-scan, кодом и автотестами — ключи роутинга.

  python3 map.py caps <repo>                      # возможности из openspec/specs (+ файлы из trace.md)
  python3 map.py auto <repo> [--dry-run]          # эвристики: требования в спеках, слова; + автотесты в коде
  python3 map.py list <repo> --unmapped [--section orders]   # что осталось — по папкам, для решения модели
  python3 map.py set <repo> TC-0003 TC-0004 --cap order-cancellation [--code src/routes/orders.ts]
  python3 map.py set <repo> --section otmena-zakaza --cap order-cancellation   # вся папка
  python3 map.py autotests <repo> [--tests test/ --tests e2e/]               # только автотесты

Пишет поля capabilities, code, autotests во front-matter (это обогащение — повторный импорт его сохраняет),
блок «Сопоставление» в QUESTIONS.md и пересобирает индексы.
"""
import argparse
import math
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import indexer  # noqa: E402
import qa  # noqa: E402

CODE_EXT = {".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".java", ".kt", ".kts", ".cs", ".go", ".rb", ".php",
            ".feature", ".robot", ".swift", ".scala", ".groovy", ".rs", ".dart"}
SKIP = {"node_modules", ".git", "dist", "build", "vendor", ".venv", "venv", "__pycache__", qa.LAYER, "target", "bin", "obj",
        "coverage", ".next", "openspec", "system-context", "design-context"}


def update_meta(path, changes):
    text = path.read_text(encoding="utf-8")
    meta, body, err = qa.parse_meta(text)
    if err:
        qa.warn(f"{path}: {err} — пропускаю")
        return False
    new = dict(meta)
    for k, v in changes.items():
        new[k] = v
    out = qa.dump_meta(new) + body if body.startswith("\n") else qa.dump_meta(new) + "\n" + body.lstrip("\n")
    return qa.write_if_changed(path, out)


def load(P):
    recs, errors = indexer.collect(P)
    files = {r["id"]: P.root / r["path"] for r in recs}
    return [r for r in recs if r["kind"] == "case"], files


def cmd_caps(a):
    P = qa.Paths(a.repo)
    caps = indexer.load_caps(P.repo)
    if not caps:
        print("возможностей нет: нет openspec/specs/*/spec.md и system-context/trace.md (их делает sa-scan). "
              "Роутинг будет по папкам, требованиям, тегам и коду.")
        return 0
    for k, v in caps.items():
        print(f"{k} — {v['title']}")
        if v["purpose"]:
            print(f"   {v['purpose'][:200]}")
        if v["requirements"]:
            print(f"   требования: {'; '.join(v['requirements'][:8])}")
        if v["files"]:
            print(f"   код: {', '.join(v['files'][:6])}")
    return 0


def case_text(path):
    c = qa.read_case(path)
    steps = " ".join(s["action"] + " " + s["expected"] for s in c["steps"][:6])
    return c, steps + " " + c["sections"].get("preconditions", "") + " " + c["sections"].get("objective", "")


def score_caps(caps):
    docs = {}
    for k, v in caps.items():
        w = {}
        for t, weight in ((k.replace("-", " "), 3), (v["title"], 3), (" ".join(v["requirements"]), 2), (v["purpose"], 1),
                          (v["text"][:6000], 0.3)):
            for x in qa.words(t):
                w[x] = w.get(x, 0) + weight
        docs[k] = w
    df = {}
    for w in docs.values():
        for x in w:
            df[x] = df.get(x, 0) + 1
    n = len(docs)
    idf = {x: math.log((n + 1) / d) + 0.1 for x, d in df.items()}
    return docs, idf


def guess(r, ctext, caps, docs, idf, min_score):
    """→ (возможность, счёт, почему) или (None, …)."""
    for k, v in caps.items():  # ключ требования прямо в спеке — надёжнее слов
        for req in r["requirements"]:
            if re.search(r"\b" + re.escape(req) + r"\b", v["text"]):
                return k, 99, f"требование {req} есть в спеке"
    q = {}
    for t, weight in ((r["title"], 3), (r["section"].replace(" / ", " "), 2), (" ".join(r["tags"]), 2), (ctext, 0.5)):
        for x in qa.words(t):
            q[x] = q.get(x, 0) + weight
    scores = []
    for k, w in docs.items():
        s = sum(min(qv, 4) * min(w[x], 4) * idf[x] for x, qv in q.items() if x in w)
        scores.append((s, k))
    scores.sort(reverse=True)
    if not scores or scores[0][0] < min_score:
        return None, scores[0][0] if scores else 0, "мало совпадений"
    if len(scores) > 1 and scores[1][0] > 0 and scores[0][0] < scores[1][0] * 1.5:
        return None, scores[0][0], f"спорно: {scores[0][1]} или {scores[1][1]}"
    common = [x for x in q if x in docs[scores[0][1]]][:5]
    return scores[0][1], scores[0][0], "слова: " + ", ".join(common)


def find_autotests(P, recs, dirs):
    """Ищет в коде тестов упоминания кейсов: TC-0001, ключи TMS в аннотациях (C123, SHOP-T12, WorkItemIds(123))."""
    by_token = {}
    for r in recs:
        by_token[r["id"]] = r["id"]
        key, tms = r["key"], r["tms"]
        if key and tms in ("zephyr", "testlink") and re.match(r"^[A-Z][A-Z0-9_]*-T?\d+$", key):
            by_token[key] = r["id"]
        if key and tms == "testrail":
            by_token["C" + key.lstrip("C")] = r["id"]
        if key and tms == "testit":
            by_token["testit:" + key] = r["id"]
    for r in recs:  # externalId из TMS
        for a in r["autotests"]:
            if a.startswith("ext:"):
                by_token["ext:" + a[4:]] = r["id"]
    tokens = [t for t in by_token if not t.startswith(("testit:", "ext:", "C"))]
    rx_plain = re.compile(r"(?<![\w-])(" + "|".join(re.escape(t) for t in sorted(tokens, key=len, reverse=True)) + r")(?![\w-])") if tokens else None
    rx_tr = re.compile(r"(?i)(?:testrail|case_?id|@case|pytestrail\.case|\[)\W{0,12}(C\d+)\b")
    rx_tr2 = re.compile(r"\[(C\d+)\]")
    rx_ti = re.compile(r"(?i)work_?item_?ids?\W{0,10}((?:[\"']?\d+[\"']?[\s,]*)+)")
    exts = [t[4:] for t in by_token if t.startswith("ext:")]
    found = {}
    roots = [P.repo / d for d in dirs] if dirs else [P.repo]
    for root in roots:
        if not root.exists():
            qa.warn(f"нет папки {root}")
            continue
        it = [root] if root.is_file() else root.rglob("*")
        for f in it:
            if f.is_dir() or f.suffix.lower() not in CODE_EXT:
                continue
            rel = f.relative_to(P.repo).parts
            if any(x in SKIP for x in rel[:-1]):
                continue
            try:
                lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            relp = f.relative_to(P.repo).as_posix()
            for n, line in enumerate(lines, 1):
                hits = set()
                if rx_plain:
                    hits |= {by_token[m] for m in rx_plain.findall(line)}
                for m in rx_tr.findall(line) + rx_tr2.findall(line):
                    if m in by_token:
                        hits.add(by_token[m])
                for m in rx_ti.findall(line):
                    for num in re.findall(r"\d+", m):
                        if "testit:" + num in by_token:
                            hits.add(by_token["testit:" + num])
                for e in exts:
                    if e and e in line:
                        hits.add(by_token["ext:" + e])
                for h in hits:
                    found.setdefault(h, [])
                    if f"{relp}:{n}" not in found[h]:
                        found[h].append(f"{relp}:{n}")
    return found


def cmd_auto(a):
    P = qa.Paths(a.repo)
    recs, files = load(P)
    if not recs:
        qa.die("кейсов нет — сначала fetch.py и build.py")
    caps = indexer.load_caps(P.repo)
    assigned, unsure = [], []
    if caps:
        docs, idf = score_caps(caps)
        for r in recs:
            if r["capabilities"] and not a.redo:
                continue
            _, ctext = case_text(files[r["id"]])
            cap, sc, why = guess(r, ctext, caps, docs, idf, a.min_score)
            if cap:
                assigned.append((r["id"], cap, why))
                if not a.dry_run:
                    update_meta(files[r["id"]], {"capabilities": [cap]})
            else:
                unsure.append((r["id"], why))
        print(f"возможности: назначено {len(assigned)}, не решено {len(unsure)} (из {len(recs)})")
        for tid, cap, why in assigned[:a.show]:
            print(f"  {tid} → {cap}  ({why})")
        if len(assigned) > a.show:
            print(f"  … ещё {len(assigned) - a.show}")
    else:
        print("возможностей нет (нет openspec/specs) — пропускаю, роутинг по папкам, требованиям, тегам и коду")
    if not a.no_autotests:
        found = find_autotests(P, recs, a.tests)
        n = 0
        for r in recs:
            refs = found.get(r["id"])
            if not refs:
                continue
            merged = list(r["autotests"]) + [x for x in refs if x not in r["autotests"]]
            if merged != r["autotests"]:
                n += 1
                if not a.dry_run:
                    update_meta(files[r["id"]], {"autotests": merged})
        print(f"автотесты: найдены для {len(found)} кейсов, обновлено {n}")
        for tid in sorted(found)[:a.show]:
            print(f"  {tid} ← {', '.join(found[tid][:3])}")
    if a.dry_run:
        return 0
    indexer.build(P, quiet=True)
    write_block(P)
    print(f"Дальше: python3 <skill>/scripts/map.py list {a.repo} --unmapped — реши оставшиеся (map.py set), затем lint.py")
    return 0


def write_block(P):
    recs, _ = load(P)
    caps = indexer.load_caps(P.repo)
    L = ["## Сопоставление", ""]
    if caps:
        none = [r for r in recs if not r["capabilities"]]
        if none:
            by_dir = {}
            for r in none:
                by_dir.setdefault(r["dir"] or "(корень)", []).append(r["id"])
            L += [f"Кейсы без возможности: {len(none)}. Если кейс ни к одной возможности не относится — так и оставь; "
                  "если возможности не хватает в `openspec/specs/` — это вопрос к sa-scan.", ""]
            for d in sorted(by_dir):
                ids = by_dir[d]
                L.append(f"- [ ] `{d}`: {', '.join(ids[:12])}{' …' if len(ids) > 12 else ''} ({len(ids)})")
            L.append("")
        else:
            L += ["У всех кейсов есть возможность.", ""]
    else:
        L += ["Возможностей нет (нет `openspec/specs/`): роутинг по папкам, требованиям, тегам и коду. "
              "Снять спеку — скилл sa-scan, затем `map.py auto`.", ""]
    noauto = [r["id"] for r in recs if r["type"] == "automated" and not r["autotests"]]
    if noauto:
        L += ["Помечены автоматизированными, но автотест в коде не найден — где он? "
              f"{', '.join(noauto[:20])}{' …' if len(noauto) > 20 else ''}", ""]
    qa.set_block(P.questions, "map", "\n".join(L))


def cmd_list(a):
    P = qa.Paths(a.repo)
    recs, files = load(P)
    sel = [r for r in recs if (not a.unmapped or not r["capabilities"]) and (not a.section or r["dir"].startswith(a.section.strip("/")))]
    by_dir = {}
    for r in sel:
        by_dir.setdefault(r["dir"] or "(корень)", []).append(r)
    for d in sorted(by_dir):
        names = by_dir[d][0]["section"]
        print(f"## {d}  ({names}, {len(by_dir[d])})")
        for r in by_dir[d][:a.limit]:
            extra = f"  cap: {', '.join(r['capabilities'])}" if r["capabilities"] else ""
            req = f"  req: {', '.join(r['requirements'][:3])}" if r["requirements"] else ""
            print(f"  {r['id']}  {r['title']}{req}{extra}")
        if len(by_dir[d]) > a.limit:
            print(f"  … ещё {len(by_dir[d]) - a.limit}")
    print(f"всего: {len(sel)}")
    return 0


def cmd_set(a):
    P = qa.Paths(a.repo)
    recs, files = load(P)
    caps = indexer.load_caps(P.repo)
    for c in a.cap or []:
        if caps and c not in caps:
            qa.die(f"нет возможности {c!r}; есть: {', '.join(caps)} (map.py caps)")
    ids = list(a.ids)
    if a.section:
        ids += [r["id"] for r in recs if r["dir"] == a.section.strip("/") or r["dir"].startswith(a.section.strip("/") + "/")]
    if not ids:
        qa.die("укажи id кейсов или --section <папка>")
    byid = {r["id"]: r for r in recs}
    n = 0
    for tid in ids:
        if tid not in byid:
            qa.die(f"нет кейса {tid}")
        r = byid[tid]
        ch = {}
        for key, vals in (("capabilities", a.cap), ("code", a.code)):
            if vals is None:
                continue
            cur = [] if a.replace else list(r[key])
            for v in vals:
                if v and v not in cur:
                    cur.append(v)
            ch[key] = cur
        if a.clear_cap:
            ch["capabilities"] = []
        if a.clear_code:
            ch["code"] = []
        if ch and update_meta(files[tid], ch):
            n += 1
    indexer.build(P, quiet=True)
    write_block(P)
    print(f"✓ изменено кейсов: {n} из {len(ids)}")
    return 0


def cmd_autotests(a):
    a.no_autotests = False
    P = qa.Paths(a.repo)
    recs, files = load(P)
    found = find_autotests(P, recs, a.tests)
    n = 0
    for r in recs:
        refs = found.get(r["id"]) or []
        merged = list(r["autotests"]) + [x for x in refs if x not in r["autotests"]]
        if merged != r["autotests"] and update_meta(files[r["id"]], {"autotests": merged}):
            n += 1
    indexer.build(P, quiet=True)
    write_block(P)
    print(f"✓ автотесты найдены для {len(found)} кейсов, обновлено {n}")
    return 0


def main():
    ap = argparse.ArgumentParser(description="Кейсы → возможности, код, автотесты", formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("caps")
    p.add_argument("repo")
    p.set_defaults(func=cmd_caps)
    p = sub.add_parser("auto")
    p.add_argument("repo")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--redo", action="store_true", help="пересчитать и у кейсов, где возможность уже стоит")
    p.add_argument("--min-score", type=float, default=6.0)
    p.add_argument("--tests", action="append", help="где искать автотесты (по умолчанию весь репозиторий)")
    p.add_argument("--no-autotests", action="store_true")
    p.add_argument("--show", type=int, default=20)
    p.set_defaults(func=cmd_auto)
    p = sub.add_parser("list")
    p.add_argument("repo")
    p.add_argument("--unmapped", action="store_true")
    p.add_argument("--section", help="папка от test-cases/, например otmena-zakaza")
    p.add_argument("--limit", type=int, default=40)
    p.set_defaults(func=cmd_list)
    p = sub.add_parser("set")
    p.add_argument("repo")
    p.add_argument("ids", nargs="*")
    p.add_argument("--section", help="все кейсы папки и подпапок")
    p.add_argument("--cap", action="append")
    p.add_argument("--code", action="append", help="файл или папка кода от корня репозитория")
    p.add_argument("--replace", action="store_true", help="заменить, а не добавить")
    p.add_argument("--clear-cap", action="store_true", help="убрать все возможности")
    p.add_argument("--clear-code", action="store_true", help="убрать все пути кода")
    p.set_defaults(func=cmd_set)
    p = sub.add_parser("autotests")
    p.add_argument("repo")
    p.add_argument("--tests", action="append")
    p.set_defaults(func=cmd_autotests)
    a = ap.parse_args()
    return a.func(a) or 0


if __name__ == "__main__":
    sys.exit(main())
