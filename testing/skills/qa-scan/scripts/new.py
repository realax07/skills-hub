#!/usr/bin/env python3
"""Новый кейс (или общий шаг) в md: следующий свободный номер, каркас по формату, индексы.

  python3 new.py <repo> --title "Отмена заказа после отгрузки" --section otmena-zakaza/menedzher \\
      [--priority high] [--tag smoke] [--req SHOP-40] [--cap order-cancellation] [--steps 3]
  python3 new.py <repo> --shared --title "Вход менеджером"

--section — папка от test-cases/ (как в ROUTING.md) или путь разделов словами «Отмена заказа/Менеджер».
Номер никогда не переиспользуется: учитываются и файлы, и выданные раньше номера (.source/ids.json).
Каркас — со статусом draft и местами <!-- заполнить … -->: check.py напомнит их заполнить.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import indexer  # noqa: E402
import qa  # noqa: E402
import tms_common  # noqa: E402


def next_id(P, prefix, width):
    ids = qa.load_json(P.ids, {}) or {}
    used = list((ids.get("cases") or {}).values()) + list((ids.get("shared") or {}).values())
    used += [f.name.split("-", 2)[0] + "-" + f.name.split("-", 2)[1] for f in P.case_files() if f.name.count("-") >= 1]
    n = int(ids.get(f"max_{prefix}", 0))
    for u in used:
        if u.startswith(prefix + "-"):
            try:
                n = max(n, int(u.split("-")[1].split(".")[0]))
            except (ValueError, IndexError):
                pass
    ids[f"max_{prefix}"] = n + 1
    qa.save_json(P.ids, ids)
    return f"{prefix}-{n + 1:0{width}d}"


def resolve_dir(P, section):
    """→ (папка от test-cases/, человеческий путь разделов)."""
    section = (section or "").strip().strip("/")
    if not section:
        return "", ""
    recs, _ = indexer.collect(P)
    names = indexer.dir_names(recs)
    if (P.root / section).is_dir():
        human = " / ".join(names.get("/".join(section.split("/")[:i + 1]), p) for i, p in enumerate(section.split("/")))
        return section, human
    parts = tms_common.split_path(section)
    rev = {}
    for d, n in names.items():
        rev[(d.rsplit("/", 1)[0] if "/" in d else "", n.lower())] = d
    cur, out = "", []
    for p in parts:
        d = rev.get((cur, p.lower())) or (f"{cur}/{qa.slug(p)}" if cur else qa.slug(p))
        out.append(d.split("/")[-1])
        cur = d
    return "/".join(out), " / ".join(parts)


def main():
    ap = argparse.ArgumentParser(description="Новый тест-кейс в md", formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    ap.add_argument("repo")
    ap.add_argument("--title", required=True)
    ap.add_argument("--section", default="")
    ap.add_argument("--shared", action="store_true", help="общий шаг (_shared/SS-…)")
    ap.add_argument("--priority", default="medium", choices=qa.PRIORITIES)
    ap.add_argument("--type", default="manual", choices=qa.TYPES)
    ap.add_argument("--tag", action="append", default=[])
    ap.add_argument("--req", action="append", default=[])
    ap.add_argument("--cap", action="append", default=[])
    ap.add_argument("--steps", type=int, default=2, help="сколько пустых шагов в каркасе")
    a = ap.parse_args()
    P = qa.Paths(a.repo)
    if not P.root.is_dir():
        qa.die(f"нет {qa.LAYER}/ — сначала импорт (fetch.py, build.py) или создай папку {qa.LAYER}/ вручную")
    lang = P.load_config().get("lang", "ru")
    h = qa.HEAD[lang]
    if a.shared:
        cid = next_id(P, "SS", 3)
        path = P.shared / f"{cid}-{qa.slug(a.title)}.md"
        meta = {"id": cid, "title": a.title, "type": "shared"}
        human = ""
    else:
        cid = next_id(P, "TC", 4)
        d, human = resolve_dir(P, a.section)
        path = (P.root / d if d else P.root) / f"{cid}-{qa.slug(a.title)}.md"
        meta = {"id": cid, "title": a.title, "priority": a.priority, "status": "draft", "type": a.type, "tags": a.tag,
                "requirements": a.req, "capabilities": a.cap, "code": [], "autotests": []}
        if human:
            meta["source"] = {"tms": "md", "section": human}
    steps = "\n".join(f"{i}. <!-- заполнить: действие -->\n   - **{h['exp']}:** <!-- заполнить: что должно получиться -->"
                      for i in range(1, max(1, a.steps) + 1))
    body = f"# {cid} {a.title}\n\n"
    if not a.shared:
        body += f"## {h['preconditions']}\n\n<!-- заполнить: что должно быть до начала, или удали раздел -->\n\n"
    body += f"## {h['steps']}\n\n{steps}\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(qa.dump_meta(meta) + "\n" + body, encoding="utf-8")
    indexer.build(P, quiet=True)
    print(f"✓ {P.rel(path)}")
    print("Заполни места «заполнить», статус draft → ready, когда кейс готов; затем check.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
