"""Индексы слоя test-cases/: index.json, INDEX.md по папкам, _index/by-*.md, ROUTING.md.

Строится по front-matter md-файлов (md первичен), а не по снимку TMS: правки людей и агентов попадают в индекс.
"""
import hashlib
import re
from pathlib import Path

import qa

ROUTING_BUDGET = 9000  # символов ≈ 3 тыс. токенов


def collect(P):
    recs, errors = [], []
    for f in P.case_files():
        text = f.read_text(encoding="utf-8")
        meta, body, err = qa.parse_meta(text)
        rel = f.relative_to(P.root).as_posix()
        if err:
            errors.append(f"{rel}: {err}")
            continue
        src = meta.get("source") if isinstance(meta.get("source"), dict) else {}
        rid = str(meta.get("id") or "")
        kind = "shared" if qa.SHARED_RE.match(rid) else "case"
        recs.append({
            "id": rid, "kind": kind, "title": str(meta.get("title") or ""), "path": rel,
            "dir": str(Path(rel).parent.as_posix()) if "/" in rel else "",
            "priority": str(meta.get("priority") or ""), "status": str(meta.get("status") or ""),
            "type": str(meta.get("type") or ""),
            **{k: [str(x) for x in (meta.get(k) or [])] if isinstance(meta.get(k), list) else qa.norm_list(meta.get(k))
               for k in qa.LIST_KEYS},
            "section": str(src.get("section") or ""), "key": str(src.get("key") or src.get("id") or ""),
            "tms": str(src.get("tms") or ""),
        })
    return recs, errors


def files_hash(P):
    h = hashlib.sha1()
    for f in P.case_files():
        text = f.read_text(encoding="utf-8")
        end = text.find("\n---", 3)
        h.update(f.relative_to(P.root).as_posix().encode())
        h.update(text[:end if end > 0 else 0].encode("utf-8"))
    return h.hexdigest()[:16]


def load_caps(repo):
    """Возможности sa-scan: openspec/specs/<cap>/spec.md + файлы кода из system-context/trace.md."""
    repo = Path(repo)
    caps = {}
    specs = repo / "openspec" / "specs"
    if specs.is_dir():
        for spec in sorted(specs.glob("*/spec.md")):
            text = spec.read_text(encoding="utf-8", errors="replace")
            m = re.search(r"^#\s+(.+)$", text, re.M)
            pm = re.search(r"^##\s+Purpose\s*\n(.*?)(?=^##\s|\Z)", text, re.M | re.S)
            caps[spec.parent.name] = {
                "title": (m.group(1).strip() if m else spec.parent.name),
                "purpose": (pm.group(1).strip() if pm else ""),
                "requirements": re.findall(r"^###\s+Requirement:\s*(.+)$", text, re.M),
                "text": text, "files": [], "tests": []}
    trace = repo / "system-context" / "trace.md"
    if trace.is_file():
        cur = None
        for line in trace.read_text(encoding="utf-8", errors="replace").splitlines():
            m = re.match(r"^##\s+(\S+)", line)
            if m:
                cur = m.group(1)
                caps.setdefault(cur, {"title": cur, "purpose": "", "requirements": [], "text": "", "files": [], "tests": []})
                continue
            if cur and line.lstrip().startswith("- ") and "→" in line:
                right = line.split("→", 1)[1]
                code, _, tests = right.partition("|")
                tests = tests.split(":", 1)[1] if ":" in tests else tests
                for part, key in ((code, "files"), (tests, "tests")):
                    part = re.sub(r"\([^)]*\)", "", part)
                    for x in part.split(","):
                        x = re.sub(r":[\d\-–]+$", "", x.strip().strip("`"))
                        if x and x != "—" and ("/" in x or ("." in x and " " not in x)):
                            if x not in caps[cur][key]:
                                caps[cur][key].append(x)
    return caps


def _line(r, base):
    rel = Path(r["path"]).as_posix()
    href = rel if not base else Path(_relpath(rel, base)).as_posix()
    bits = [f"- [{r['id']}]({href}) {r['title']}", r["priority"], r["status"]]
    if r["type"] and r["type"] != "manual":
        bits.append(r["type"])
    if r["tags"]:
        bits.append(" ".join("#" + t for t in r["tags"][:6]))
    if r["capabilities"]:
        bits.append("cap: " + ", ".join(r["capabilities"]))
    if r["requirements"]:
        bits.append("req: " + ", ".join(r["requirements"][:5]))
    return " · ".join(b for b in bits if b)


def _relpath(target, base):
    t, b = Path(target).parts, Path(base).parts if base else ()
    i = 0
    while i < len(t) and i < len(b) and t[i] == b[i]:
        i += 1
    return "/".join([".."] * (len(b) - i) + list(t[i:]))


def dir_names(recs):
    """Человеческие имена папок: из source.section кейсов (по уровням)."""
    names = {}
    for r in recs:
        if not r["dir"] or r["kind"] != "case":
            continue
        parts = r["dir"].split("/")
        sec = [x.strip() for x in r["section"].split(" / ")] if r["section"] else []
        if len(sec) == len(parts):
            for i in range(len(parts)):
                names.setdefault("/".join(parts[:i + 1]), sec[i])
    return names


def build(P, quiet=False):
    recs, errors = collect(P)
    cfg = P.load_config()
    caps = load_caps(P.repo)
    cases = [r for r in recs if r["kind"] == "case"]
    shared = [r for r in recs if r["kind"] == "shared"]
    names = dir_names(recs)
    changed = []
    qa.save_json(P.index_json, {"files_hash": files_hash(P), "cases": cases, "shared": shared,
                                "capabilities": {k: {"title": v["title"], "files": v["files"], "tests": v["tests"]} for k, v in caps.items()}})

    # INDEX.md по папкам
    dirs = {}
    for r in recs:
        d = r["dir"]
        dirs.setdefault(d, {"cases": [], "subs": set()})["cases"].append(r)
        parts = d.split("/") if d else []
        for i in range(len(parts)):
            parent = "/".join(parts[:i])
            dirs.setdefault(parent, {"cases": [], "subs": set()})["subs"].add("/".join(parts[:i + 1]))
    total = {d: sum(1 for r in cases if r["dir"] == d or r["dir"].startswith(d + "/") or not d) for d in dirs}
    for d, info in dirs.items():
        if not d:
            continue
        title = names.get(d, d.split("/")[-1])
        crumbs = " / ".join(names.get("/".join(d.split("/")[:i + 1]), p) for i, p in enumerate(d.split("/")))
        here = [r for r in info["cases"]]
        up = "../" * len(d.split("/"))
        lines = [f"# {crumbs}", "", f"Папка `{qa.LAYER}/{d}/`. Кейсов: {total[d]}"
                 + (f" (здесь {len(here)})" if info["subs"] else "") + f". Карта — [ROUTING.md]({up}ROUTING.md).", ""]
        if info["subs"]:
            lines += ["## Подпапки", ""]
            for s in sorted(info["subs"]):
                lines.append(f"- [{names.get(s, s.split('/')[-1])}]({s.split('/')[-1]}/INDEX.md) — {total.get(s, 0)}")
            lines.append("")
        if here:
            lines += ["## Кейсы" if d != "_shared" else "## Общие шаги", ""]
            lines += [_line(r, d) for r in sorted(here, key=lambda r: r["id"])]
            lines.append("")
        if qa.write_if_changed(P.root / d / "INDEX.md", "\n".join(lines)):
            changed.append(f"{d}/INDEX.md")
    # убрать INDEX.md из опустевших папок
    for f in P.root.rglob("INDEX.md"):
        d = f.parent.relative_to(P.root).as_posix()
        if d not in dirs and not d.startswith(("_index", ".")):
            f.unlink()

    by = {}
    head = "<!-- собирает qa-scan (route.py index) — руками не правь -->\n"

    def group(title, key_fn, intro, file, empty_label=None):
        groups, none = {}, []
        for r in cases:
            keys = key_fn(r)
            if not keys:
                none.append(r)
            for k in keys:
                groups.setdefault(k, []).append(r)
        lines = [head + f"# {title}", "", intro, ""]
        for k in sorted(groups):
            extra = ""
            if file == "by-capability.md" and k in caps and caps[k]["title"] != k:
                extra = f" — {caps[k]['title']}"
            lines += [f"## {k}{extra} ({len(groups[k])})", ""]
            lines += [_line(r, "_index") for r in sorted(groups[k], key=lambda r: r["id"])]
            lines.append("")
        if empty_label and none:
            lines += [f"## {empty_label} ({len(none)})", ""]
            lines += [_line(r, "_index") for r in sorted(none, key=lambda r: r["id"])]
            lines.append("")
        by[file] = len(groups)
        if qa.write_if_changed(P.index_dir / file, "\n".join(lines)):
            changed.append(f"_index/{file}")
        return groups, none

    gcap, nocap = group("Кейсы по возможностям", lambda r: r["capabilities"],
                        "Возможность — из `openspec/specs/<возможность>/` (sa-scan). Меняешь поведение возможности — проверь и обнови её кейсы.",
                        "by-capability.md", "без возможности")
    group("Кейсы по требованиям", lambda r: r["requirements"], "Ключ требования или задачи (Jira и т.п.) → кейсы. Ищи: `grep -n \"SHOP-12\" by-requirement.md`.",
          "by-requirement.md", "без требований")
    group("Кейсы по тегам", lambda r: r["tags"], "Теги из TMS: наборы регресса, smoke, компоненты.", "by-tag.md")

    # по автотестам
    lines = [head + "# Кейсы и автотесты", "",
             "`ext:<id>` — автотест, привязанный в TMS (externalId); `путь:строка` — найден в коде (`map.py autotests`).", ""]
    auto = [r for r in cases if r["autotests"]]
    for r in sorted(auto, key=lambda r: r["id"]):
        lines.append(_line(r, "_index") + " → " + ", ".join(f"`{a}`" for a in r["autotests"]))
    manual_auto = [r for r in cases if r["type"] == "automated" and not r["autotests"]]
    if manual_auto:
        lines += ["", f"## Помечены автоматизированными, но автотест не найден ({len(manual_auto)})", ""]
        lines += [_line(r, "_index") for r in manual_auto]
    if qa.write_if_changed(P.index_dir / "by-autotest.md", "\n".join(lines) + "\n"):
        changed.append("_index/by-autotest.md")

    # по коду
    lines = [head + "# Кейсы по коду", "", "Файл или папка кода → возможность → кейсы. Ищи: `grep -n \"src/orders\" test-cases/_index/by-code.md`.", ""]
    file_caps = {}
    for cap, info in caps.items():
        for f in info["files"]:
            file_caps.setdefault(f, []).append(cap)
    if file_caps:
        lines += ["## По трассировке sa-scan (`system-context/trace.md`)", ""]
        for f in sorted(file_caps):
            parts = [f"{c} ({len(gcap.get(c, []))})" for c in sorted(file_caps[f])]
            lines.append(f"- `{f}` → " + ", ".join(parts))
        lines.append("")
    code_map = {}
    for r in cases:
        for c in r["code"]:
            code_map.setdefault(c, []).append(r["id"])
        for a in r["autotests"]:
            if not a.startswith("ext:"):
                code_map.setdefault(re.sub(r":\d+$", "", a) + " (автотест)", []).append(r["id"])
    if code_map:
        lines += ["## Указаны в кейсах (`code:`, `autotests:`)", ""]
        for c in sorted(code_map):
            lines.append(f"- `{c}` → " + ", ".join(sorted(set(code_map[c]))))
        lines.append("")
    if not file_caps and not code_map:
        lines.append("Пока пусто: нет `system-context/trace.md` (sa-scan) и полей `code:` в кейсах.")
    if qa.write_if_changed(P.index_dir / "by-code.md", "\n".join(lines) + "\n"):
        changed.append("_index/by-code.md")

    routing = render_routing(P, cfg, cases, shared, dirs, total, names, gcap, nocap, caps)
    if qa.write_if_changed(P.routing, routing):
        changed.append("ROUTING.md")
    if not quiet:
        print(f"✓ индексы: кейсов {len(cases)}, общих шагов {len(shared)}, папок {len([d for d in dirs if d])}, "
              f"возможностей {len(gcap)}{' (без возможности ' + str(len(nocap)) + ')' if caps else ''}; изменено файлов {len(changed)}")
    for e in errors:
        qa.warn(e)
    return {"cases": len(cases), "errors": errors, "changed": changed}


TMS_NAMES = {"testrail": "TestRail", "testit": "Test IT", "zephyr": "Zephyr Scale", "testlink": "TestLink", "table": "таблица"}


def render_routing(P, cfg, cases, shared, dirs, total, names, gcap, nocap, caps):
    src = ""
    if cfg.get("tms"):
        src = (f"Перенесены из {TMS_NAMES.get(cfg['tms'], cfg['tms'])}"
               + (f" «{cfg['project']}»" if cfg.get("project") else "")
               + (f" ({'API' if cfg.get('mode') == 'api' else 'файл'} {cfg.get('origin', '')}, {cfg.get('fetched', '')[:10]})" if cfg.get("origin") else "")
               + ". ")
    L = ["# Тест-кейсы — карта", "",
         f"{src}Кейсов {len(cases)}, общих шагов {len(shared)}. **md первичен**: кейсы правят здесь, TMS — только источник переноса.", "",
         "## Как найти кейсы под задачу", "",
         "| Задача | Где искать |", "|---|---|"]
    if caps:
        L.append("| Меняю поведение возможности (из `openspec/specs/`) | `_index/by-capability.md`, раздел `## <возможность>` |")
    L += ["| Меняю файл кода | `grep -n \"<путь>\" test-cases/_index/by-code.md` |",
          "| Есть ключ требования или задачи | `grep -n \"<КЛЮЧ-12>\" test-cases/_index/by-requirement.md` |",
          "| Набор регресса, тег (smoke…) | `_index/by-tag.md` |",
          "| Кейс ↔ автотест | `_index/by-autotest.md` |",
          "| По словам | `grep -ril \"<слово>\" test-cases --include=\"TC-*.md\"` |",
          "| Область целиком | «Области» ниже → `INDEX.md` папки |", "",
          "Со скиллом qa-scan — одной командой: `python3 <qa-scan>/scripts/route.py find . --cap <возможность> --path <файл> --text \"<слова>\"`.", ""]
    L += ["## Области", "", "| Папка | Раздел | Кейсов |", "|---|---|---|"]
    tops = sorted(d for d in dirs if d and "/" not in d and d != "_shared")
    rows = []
    for t in tops:
        rows.append(f"| [{t}/]({t}/INDEX.md) | {names.get(t, t)} | {total.get(t, 0)} |")
        subs = sorted(s for s in dirs if s.startswith(t + "/") and s.count("/") == 1)
        for s in subs:
            rows.append(f"| &nbsp;&nbsp;[{s}/]({s}/INDEX.md) | {names.get(s, s.split('/')[-1])} | {total.get(s, 0)} |")
    if len(rows) > 70:
        rows = [r for r in rows if "&nbsp;" not in r]
    L += rows
    if shared:
        L.append(f"| [_shared/](_shared/INDEX.md) | общие шаги | {len(shared)} |")
    L.append("")
    if caps:
        L += ["## Возможности", "", "| Возможность | Кейсов |", "|---|---|"]
        for c in sorted(caps):
            L.append(f"| {c} | {len(gcap.get(c, []))} |")
        if nocap:
            L.append(f"| без возможности | {len(nocap)} |")
        L.append("")
    lang = cfg.get("lang", "ru")
    h = qa.HEAD[lang]
    L += ["## Формат кейса", "",
          "Файл `TC-NNNN-<slug>.md`: front-matter (`id`, `title`, `priority`, `status`, `type`, `tags`, `requirements`, "
          "`capabilities`, `code`, `autotests`, `source`, `custom`) и разделы "
          f"«{h['objective']}», «{h['preconditions']}», «{h['steps']}», «{h['postconditions']}», «{h['params']}». "
          f"Шаг — `1. действие`, под ним `   - **{h['exp']}:** …` и `   - **{h['data']}:** …`. "
          "Общий шаг — файл `_shared/SS-NNN-*.md`, в кейсе на него ссылка.", "",
          "## Как менять", "",
          "1. Поведение изменилось — поправь шаги и ожидаемое в кейсах, найденных выше. Новый сценарий — новый кейс со следующим номером "
          "(`new.py`), id не меняй и не переиспользуй.",
          "2. Кейс устарел — `status: deprecated`, файл не удаляй, пока человек не решит.",
          "3. `[скрыто: S-NN]` — секрет из TMS: не вписывай настоящее значение, бери его из окружения (см. `QUESTIONS.md`).",
          "4. После правок: `route.py index .` и `check.py .` (скилл qa-scan). `_index/`, `INDEX.md` и этот файл руками не правь.", ""]
    text = "\n".join(L)
    if len(text) > ROUTING_BUDGET:
        text = text.replace("\n## Возможности", "\n## Возможности (сокращено — полный список в _index/by-capability.md)")
    return text
