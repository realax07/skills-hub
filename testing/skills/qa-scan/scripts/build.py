#!/usr/bin/env python3
"""Разложить снимок TMS (test-cases/.source/snapshot.json) в md: кейс — файл, иерархия TMS — папки.

  python3 build.py <repo>                    # импорт / повторный импорт
  python3 build.py <repo> --dry-run          # только показать, что изменится
  python3 build.py <repo> --accept TC-0007   # конфликт: взять версию из TMS (локальные правки пропадут)
  python3 build.py <repo> --keep TC-0007     # конфликт: оставить md, версию TMS забыть

md первичен. Кейс, который правили после импорта (хеш в source.hash не совпадает), повторный импорт не перезаписывает:
если в TMS он тоже изменился — новая версия кладётся в .source/incoming/ и в QUESTIONS.md появляется конфликт.
Поля обогащения (capabilities, code, autotests) правкой не считаются и при перезаписи сохраняются.
В конце пересобирает индексы (как route.py index).
"""
import argparse
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import indexer  # noqa: E402
import qa  # noqa: E402

ENRICH = ("capabilities", "code", "autotests")


def load_ids(P):
    ids = qa.load_json(P.ids, None) or {"cases": {}, "shared": {}}
    ids.setdefault("cases", {})
    ids.setdefault("shared", {})
    return ids


def next_num(existing, prefix):
    n = 0
    for v in existing:
        if v.startswith(prefix):
            try:
                n = max(n, int(v[len(prefix):]))
            except ValueError:
                pass
    return n + 1


def existing_files(P):
    out = {}
    for f in P.case_files():
        meta, _, err = qa.parse_meta(f.read_text(encoding="utf-8"))
        if not err and meta.get("id"):
            out.setdefault(str(meta["id"]), f)
    return out


def assign_dirs(cases):
    """Путь разделов → папки из slug; разные имена с одним slug в одной папке получают суффикс."""
    taken, out = {}, {}
    for c in cases:
        parent, parts = "", []
        for name in c["path"]:
            key = (parent, name)
            if key not in taken:
                base = qa.slug(name, 40, "razdel")
                s, i = base, 2
                used = {v for (p, _), v in taken.items() if p == parent}
                while s in used or s.startswith("_"):
                    s, i = f"{base}-{i}", i + 1
                taken[key] = s
            parts.append(taken[key])
            parent = "/".join(parts)
        out[c["sid"]] = "/".join(parts)
    return out


def main():
    ap = argparse.ArgumentParser(description="Снимок TMS → md-кейсы", formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    ap.add_argument("repo")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--accept", action="append", default=[], help="конфликт: взять версию TMS")
    ap.add_argument("--keep", action="append", default=[], help="конфликт: оставить md")
    a = ap.parse_args()
    P = qa.Paths(a.repo)
    snap = qa.load_json(P.snapshot)
    if not snap:
        qa.die(f"нет {P.rel(P.snapshot)} — сначала fetch.py")
    cfg = P.load_config()
    lang = cfg.get("lang", "ru")
    ids = load_ids(P)
    files = existing_files(P)
    stats = {k: [] for k in ("new", "updated", "moved", "same", "edited", "conflict", "gone")}

    first = {}  # порядок разделов — как в TMS (первое появление), внутри раздела — порядок TMS
    for c in snap["cases"]:
        for i in range(len(c["path"]) + 1):
            first.setdefault(tuple(c["path"][:i]), len(first))
    cases = sorted(snap["cases"], key=lambda c: [first[tuple(c["path"][:i + 1])] for i in range(len(c["path"]))])
    for c in cases:
        if c["sid"] not in ids["cases"]:
            ids["cases"][c["sid"]] = f"TC-{next_num(list(ids['cases'].values()) + list(files), 'TC-'):04d}"
    for s in snap["shared"]:
        if s["sid"] not in ids["shared"]:
            ids["shared"][s["sid"]] = f"SS-{next_num(list(ids['shared'].values()) + list(files), 'SS-'):03d}"
    dirs = assign_dirs(cases)
    by_sid = {c["sid"]: c for c in cases}
    key2sid = {c["key"]: c["sid"] for c in cases if c.get("key")}

    def target(c):
        tid = ids["cases"][c["sid"]]
        d = dirs[c["sid"]]
        name = f"{tid}-{qa.slug(c['title'], 40)}.md"
        return P.root / d / name if d else P.root / name

    shared_files = {}
    for s in snap["shared"]:
        sid = ids["shared"][s["sid"]]
        shared_files[s["sid"]] = (sid, s["title"], P.shared / f"{sid}-{qa.slug(s['title'], 40)}.md")

    def linker(from_path):
        def shared_link(ref):
            if ref in shared_files:
                sid, title, p = shared_files[ref]
            else:
                sref = ref if ref in by_sid else key2sid.get(ref)
                if not sref:
                    return ref, "", ""
                sid, title, p = ids["cases"][sref], by_sid[sref]["title"], target(by_sid[sref])
            return sid, title, os.path.relpath(p, from_path.parent).replace(os.sep, "/")

        def attach_link(att):
            if att.get("local"):
                return os.path.relpath(P.repo / att["local"], from_path.parent).replace(os.sep, "/")
            return ""
        return shared_link, attach_link

    def render(meta, title, header, body_src, path):
        sl, al = linker(path)
        body = qa.render_body(title, header, body_src, lang, sl, al)
        text = qa.dump_meta(meta) + "\n" + body
        meta["source"]["hash"] = qa.content_hash(text)
        return qa.dump_meta(meta) + "\n" + body

    incoming = P.source / "incoming"
    conflicts = []
    writes = []  # (path, text, old_path)

    for c in cases:
        tid = ids["cases"][c["sid"]]
        path = target(c)
        if c.get("attachments"):
            for att in c["attachments"]:
                if att.get("file"):
                    att["local"] = f"{qa.LAYER}/_attachments/{tid}/{Path(att['file']).name}"
        meta = {"id": tid, "title": c["title"], "priority": c["priority"], "status": c["status"], "type": c["type"],
                "tags": c["tags"], "requirements": c["requirements"], "capabilities": [], "code": [],
                "autotests": [f"ext:{x}" for x in c.get("autotests") or []],
                "source": {"tms": snap["tms"], "id": c["sid"], "key": c.get("key") or "", "url": c.get("url") or "",
                           "section": " / ".join(c["path"]), "version": c.get("version") or "",
                           "updated": c.get("updated") or "", "hash": ""},
                "custom": c.get("custom") or {}}
        meta["source"] = {k: v for k, v in meta["source"].items() if v != "" or k == "hash"}
        old = files.get(tid)
        old_meta = {}
        if old:
            old_text = old.read_text(encoding="utf-8")
            old_meta, _, _ = qa.parse_meta(old_text)
            for k in ENRICH:
                vals = old_meta.get(k) or []
                if isinstance(vals, list):
                    merged = list(meta.get(k) or [])
                    merged += [str(v) for v in vals if str(v) not in merged]
                    meta[k] = merged
        text = render(meta, c["title"], tid, c, path)
        new_hash = meta["source"]["hash"]
        if not old:
            writes.append((path, text, None))
            stats["new"].append(tid)
            continue
        src = old_meta.get("source") if isinstance(old_meta.get("source"), dict) else {}
        stored = str(src.get("hash") or "")
        edited = qa.content_hash(old_text) != stored
        if tid in a.accept:
            writes.append((path, text, old if old != path else None))
            stats["updated"].append(tid)
            (incoming / f"{tid}.md").unlink(missing_ok=True)
            continue
        if tid in a.keep:
            fixed = old_text.replace(f"hash: {stored}", f"hash: {new_hash}", 1) if stored else old_text
            writes.append((old, fixed, None))
            stats["edited"].append(tid)
            (incoming / f"{tid}.md").unlink(missing_ok=True)
            continue
        if not edited:
            if new_hash == stored and old == path:
                if old_text != text:  # только обогащение
                    writes.append((path, text, None))
                stats["same"].append(tid)
            else:
                writes.append((path, text, old if old != path else None))
                stats["moved" if old != path and new_hash == stored else "updated"].append(tid)
            continue
        if new_hash == stored:
            stats["edited"].append(tid)
            continue
        conflicts.append((tid, old, text))
        stats["conflict"].append(tid)

    for s in snap["shared"]:
        sid, title, path = shared_files[s["sid"]]
        meta = {"id": sid, "title": title, "type": "shared",
                "source": {"tms": snap["tms"], "id": s["sid"], "updated": s.get("updated") or "", "hash": ""}}
        meta["source"] = {k: v for k, v in meta["source"].items() if v != "" or k == "hash"}
        text = render(meta, title, sid, {"steps": s["steps"]}, path)
        old = files.get(sid)
        if not old:
            writes.append((path, text, None))
            stats["new"].append(sid)
            continue
        old_text = old.read_text(encoding="utf-8")
        om, _, _ = qa.parse_meta(old_text)
        stored = str((om.get("source") or {}).get("hash") or "") if isinstance(om.get("source"), dict) else ""
        if qa.content_hash(old_text) == stored:
            if old_text != text or old != path:
                writes.append((path, text, old if old != path else None))
                stats["updated"].append(sid)
            else:
                stats["same"].append(sid)
        elif meta["source"]["hash"] != stored:
            conflicts.append((sid, old, text))
            stats["conflict"].append(sid)
        else:
            stats["edited"].append(sid)

    if not snap.get("partial"):
        present = set(by_sid)
        for sid, tid in ids["cases"].items():
            if sid not in present and tid in files:
                stats["gone"].append(tid)

    print(f"{'(проба) ' if a.dry_run else ''}новых {len(stats['new'])}, обновлено {len(stats['updated'])}, перенесено {len(stats['moved'])}, "
          f"без изменений {len(stats['same'])}, правлены в md {len(stats['edited'])}, конфликтов {len(stats['conflict'])}, "
          f"нет в TMS {len(stats['gone'])}")
    if a.dry_run:
        for k in ("updated", "moved", "conflict", "gone"):
            if stats[k]:
                print(f"  {k}: {', '.join(stats[k][:30])}{' …' if len(stats[k]) > 30 else ''}")
        return 0

    for path, text, old in writes:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        if old and old.resolve() != path.resolve() and old.exists():
            old.unlink()
            d = old.parent
            while d != P.root and d.is_dir() and not [x for x in d.iterdir() if x.name != "INDEX.md"]:
                shutil.rmtree(d)
                d = d.parent
    for tid, old, text in conflicts:
        qa.write_if_changed(incoming / f"{tid}.md", text)
    # вложения: .source/files → _attachments/TC-…
    for c in cases:
        for att in c.get("attachments") or []:
            if att.get("file") and att.get("local"):
                src, dst = P.repo / att["file"], P.repo / att["local"]
                if src.is_file() and not dst.exists():
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(src), str(dst))
    qa.save_json(P.ids, ids)
    write_questions(P, snap, ids, stats, conflicts)
    indexer.build(P)
    print(f"Дальше: python3 <skill>/scripts/map.py auto {a.repo}  (сопоставить с возможностями и автотестами), затем lint.py и check.py")
    return 0


def write_questions(P, snap, ids, stats, conflicts):
    sid2id = {**ids["cases"], **ids["shared"]}
    red = qa.load_json(P.redactions, []) or []
    L = ["## Импорт из TMS", ""]
    secrets = [e for e in red if e.get("secret")]
    pii = [e for e in red if not e.get("secret")]

    def where(e):
        out = []
        for w in e["where"][:8]:
            sid, _, field = w.partition("|")
            out.append(f"{sid2id.get(sid, sid)} ({field})")
        return ", ".join(out) + (f" и ещё {len(e['where']) - 8}" if len(e["where"]) > 8 else "")

    if secrets:
        L += ["### Секреты в тексте кейсов — скрыты", "",
              "Значения не сохранены нигде в слое. Реши, откуда тест берёт настоящее значение (переменная окружения, хранилище секретов), "
              "и при желании замени `[скрыто: S-NN]` на ссылку вида `$SHOP_ADMIN_PASSWORD`.", ""]
        L += [f"- [ ] {e['id']} {e['kind']} (длина {e['length']}) — {where(e)}" for e in secrets]
        L.append("")
    if pii:
        masked = any(e.get("masked") for e in pii)
        L += ["### Персональные данные — " + ("скрыты" if masked else "не скрыты"), "",
              "Это тестовые данные или реальные люди? Реальные — перезапусти `fetch.py … --mask-pii` и `build.py`.", ""]
        L += [f"- [ ] {e['id']} {e['kind']} — {where(e)}" for e in pii]
        L.append("")
    if conflicts:
        L += ["### Конфликты: кейс правили в md, а в TMS он тоже изменился", "",
              "Сравни файл с версией из TMS и реши: `build.py <repo> --accept <id>` (взять TMS) или `--keep <id>` (оставить md).", ""]
        L += [f"- [ ] {tid}: `{P.rel(old)}` ↔ `{qa.LAYER}/.source/incoming/{tid}.md`" for tid, old, _ in conflicts]
        L.append("")
    if stats["gone"]:
        L += ["### Нет в TMS (удалены или перенесены в другой проект)", "",
              "md первичен — файлы не удалены. Не нужен — поставь `status: deprecated` или удали файл.", ""]
        L += [f"- [ ] {t}" for t in stats["gone"]]
        L.append("")
    missing = []
    known = set(ids["shared"]) | {c["sid"] for c in snap["cases"]} | {c.get("key") for c in snap["cases"]}
    for c in snap["cases"]:
        for s in c["steps"]:
            if s.get("shared") and s["shared"] not in known:
                missing.append(f"{ids['cases'][c['sid']]} → {s['shared']}")
    if missing:
        L += ["### Ссылки на общие шаги или кейсы, которых нет в снимке", "",
              "Шаг сохранён как ссылка без текста. Догрузи проект целиком или впиши шаги вручную.", ""]
        L += [f"- [ ] {m}" for m in missing[:50]]
        L.append("")
    notatt = [ids["cases"][c["sid"]] for c in snap["cases"] if any(not a.get("file") for a in c.get("attachments") or [])]
    if notatt:
        L += ["### Вложения не скачаны", "", "В кейсе — имя и ссылка на TMS. Нужны картинки — `fetch.py api … --attachments` (нужен доступ к API).", "",
              f"- [ ] {', '.join(notatt[:40])}{' …' if len(notatt) > 40 else ''}", ""]
    info = []
    if snap.get("unknown_fields"):
        top = sorted(snap["unknown_fields"].items(), key=lambda x: -x[1])
        info.append("Поля TMS, сохранённые в `custom:` кейсов: " + ", ".join(f"{k} ({v})" for k, v in top[:20]))
    info += snap.get("notes") or []
    if snap.get("partial"):
        info.append("Снимок — часть проекта (фильтр или --limit): удалённые в TMS кейсы не ищутся.")
    if info:
        L += ["### К сведению", ""] + [f"- {x}" for x in info] + [""]
    if len(L) == 2:
        L.append("Вопросов по импорту нет.")
    qa.set_block(P.questions, "build", "\n".join(L))


if __name__ == "__main__":
    sys.exit(main())
