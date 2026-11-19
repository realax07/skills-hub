#!/usr/bin/env python3
"""План системного анализа: возможности (capabilities) и какие входы системы к ним относятся.

  python3 plan.py init <repo> [--source docs/prd.md --source https://…] [--language ru]
  python3 plan.py status <repo> [--json]
  python3 plan.py next <repo> [<cap>]
  python3 plan.py add-cap <repo> <cap> --title "Оформление заказа"
  python3 plan.py rename <repo> <cap> <new-cap> [--title …]
  python3 plan.py merge <repo> <from-cap> <into-cap>
  python3 plan.py move <repo> <шаблон-входа> <cap>
  python3 plan.py exclude <repo> <шаблон-входа> --reason "служебное: healthcheck"
  python3 plan.py prune <repo>
  python3 plan.py add-entry <repo> "<вид>:<имя>" --file src/x.ts --line 12 [--cap <cap>]
  python3 plan.py set <repo> <cap> [--status todo|done] [--title …] [--notes …]
  python3 plan.py drop-cap <repo> <cap>
  python3 plan.py guide <repo>

Шаблон входа — точный id из описи или шаблон с * (`http:* /api/orders*`); `re:<regex>` — регулярное выражение.
Пути слоя фиксированы: <repo>/system-context/ (план, опись, карта) и <repo>/openspec/ (спеки).
init не перезаписывает существующие файлы, кроме плана с --force.
"""
import argparse
import fnmatch
import json
import re
import shutil
import sys
from collections import OrderedDict, defaultdict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import sa  # noqa: E402

GENERIC_DIRS = {"src", "app", "apps", "lib", "libs", "internal", "pkg", "cmd", "server", "api", "routes", "router",
                "routers", "controllers", "controller", "handlers", "handler", "views", "endpoints", "resources",
                "jobs", "job", "workers", "worker", "tasks", "consumers", "listeners", "subscribers", "commands",
                "management", "services", "service", "modules", "main", "java", "kotlin", "com", "org", "core",
                "http", "web", "rest", "v1", "v2", "v3", "public", "private", "backend", "packages", "services"}
SKIP_SEG = re.compile(r"^(api|v\d+|rest|public|internal|private|\{.*\}|)$", re.I)


def draft_group(e):
    """Черновая группа для входа: первый значимый сегмент пути или папка/файл обработчика."""
    if e["kind"] == "http":
        path = e["name"].split(" ", 1)[-1]
        for seg in path.split("/"):
            if not SKIP_SEG.match(seg):
                return sa.kebab(seg)
    if e["kind"] == "graphql":
        name = e["name"].split(".", 1)[-1]
        words = re.findall(r"[A-Z]?[a-z]+", name)
        return sa.kebab(words[-1] if words else name)
    if e["kind"] == "grpc":
        return sa.kebab(re.sub(r"Service$", "", e["name"].split(".")[0]))
    parts = Path(e["file"]).parts
    for d in reversed(parts[:-1]):
        if d.lower() not in GENERIC_DIRS and not d.startswith("."):
            return sa.kebab(d)
    return sa.kebab(Path(e["file"]).stem)


def find_cap(plan, cap):
    for c in plan["capabilities"]:
        if c["id"] == cap:
            return c
    sa.die(f"нет возможности {cap} в плане — список: plan.py status")


def check_id(cap):
    if not sa.ID_RX.match(cap):
        sa.die(f"id возможности «{cap}» — kebab-case латиницей (order-checkout); русское название — в --title")


def match_entries(pattern, ids):
    if pattern.startswith("re:"):
        rx = re.compile(pattern[3:])
        return [i for i in ids if rx.search(i)]
    if any(ch in pattern for ch in "*?["):
        return [i for i in ids if fnmatch.fnmatchcase(i, pattern)]
    return [i for i in ids if i == pattern]


def detach(plan, eid):
    for c in plan["capabilities"]:
        if eid in c["entries"]:
            c["entries"].remove(eid)
    plan["excluded"] = [x for x in plan.get("excluded", []) if x["entry"] != eid]


def copy_asset(name, dest, subst=None):
    if dest.exists():
        return False
    text = (sa.ASSETS / name).read_text(encoding="utf-8")
    for k, v in (subst or {}).items():
        text = text.replace("{{" + k + "}}", v)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text, encoding="utf-8")
    return True


# ---------- команды

def cmd_init(a):
    P = sa.Paths(a.repo)
    inv = sa.load_inventory(P)
    created = []
    if P.plan.exists() and not a.force:
        print(f"план уже есть: {P.rel(P.plan)} — продолжай с plan.py status (пересоздать: --force)")
    else:
        groups = OrderedDict()
        excluded = []
        for e in inv["entries"]:
            if "служебное" in e.get("tags", []) or "ci" in e.get("tags", []):
                excluded.append({"entry": e["id"], "reason": "служебное (health, метрики, CI) — проверь"})
                continue
            groups.setdefault(draft_group(e), []).append(e["id"])
        plan = OrderedDict([
            ("version", 1), ("created", date.today().isoformat()), ("language", a.language),
            ("sources", [{"ref": s, "kind": "url" if re.match(r"^https?://", s) else "file", "note": ""} for s in a.source]),
            ("capabilities", [OrderedDict([("id", g), ("title", ""), ("status", "todo"), ("entries", ids), ("notes", "")])
                              for g, ids in groups.items()]),
            ("excluded", excluded), ("manual_entries", []),
        ])
        sa.save_json(P.plan, plan)
        created.append(P.rel(P.plan))
    lang = {"ru": "русский", "en": "английский"}.get(a.language, a.language)
    for asset, dest in [("QUESTIONS.template.md", P.questions), ("trace.template.md", P.trace),
                        ("glossary.template.md", P.ctx / "glossary.md"), ("domain.template.md", P.ctx / "domain.md"),
                        ("integrations.template.md", P.ctx / "integrations.md"),
                        ("config.template.yaml", P.config)]:
        if copy_asset(asset, dest, {"LANGUAGE": lang}):
            created.append(P.rel(dest))
    for d in (P.specs, P.openspec / "changes"):
        if not d.exists():
            d.mkdir(parents=True)
            (d / ".gitkeep").write_text("")
            created.append(P.rel(d) + "/")
    print("✓ создано: " + (", ".join(created) or "ничего — всё уже есть"))
    if inv.get("openspec_exists") or any(P.specs.glob("*/spec.md")):
        print("! в openspec/specs/ уже есть спеки — не перезаписывай: сверяй и дополняй (rules.md, «Если openspec/ уже есть»)")
    print("Дальше: plan.py status — черновые группы; переименуй и объедини их в возможности по поведению (rename, merge, move).")
    return 0


def cmd_status(a):
    P = sa.Paths(a.repo)
    plan, inv = sa.load_plan(P), sa.load_inventory(P)
    ents = sa.all_entries(inv, plan)
    asg = sa.assignment(plan)
    unassigned = [i for i in ents if i not in asg]
    missing = sorted(set(asg) - set(ents))
    caps = []
    for c in plan["capabilities"]:
        spec = P.spec(c["id"])
        caps.append({"id": c["id"], "title": c["title"], "status": c["status"], "entries": len(c["entries"]),
                     "spec": spec.is_file()})
    if a.json:
        print(json.dumps({"capabilities": caps, "excluded": len(plan.get("excluded", [])), "unassigned": unassigned,
                          "unknown_entries": missing}, ensure_ascii=False, indent=1))
        return 0
    print(f"Возможностей: {len(caps)} (готово {sum(c['status'] == 'done' for c in caps)}), входов: {len(ents)}, "
          f"исключено: {len(plan.get('excluded', []))}, без возможности: {len(unassigned)}")
    print()
    for c in caps:
        mark = "✓" if c["status"] == "done" else "·"
        print(f"{mark} {c['id']:<28} {c['entries']:>3} вх.  {'спека есть' if c['spec'] else 'спеки нет':<11} {c['title'] or '(нет названия)'}")
    if unassigned:
        print("\nБез возможности — отнеси (move) или исключи с причиной (exclude):")
        for i in unassigned:
            print(f"  {i}")
    if missing:
        print("\n! в плане есть входы, которых нет в описи (после пересканирования): " + ", ".join(missing))
        print("  маршрут переименован или удалён: plan.py prune — убрать их, затем отнести новые id (move)")
    nxt = next((c for c in caps if c["status"] != "done"), None)
    if unassigned or missing:
        print("\nДальше: разнеси входы без возможности (move / exclude), потом — возможности по очереди (next)")
    elif nxt:
        print(f"\nДальше: plan.py next {a.repo} {nxt['id']}")
    else:
        print(f"\nВсе возможности готовы. Проверка: check.py {a.repo}")
    return 0


def related_tests(inv, files, words):
    out = []
    words = {w.lower() for w in words if len(w) > 2}
    stems = {Path(f).stem.lower().split(".")[0] for f in files}
    for t in inv.get("tests", []):
        name = t["file"].lower()
        blob = (name + " " + " ".join(t["titles"])).lower()
        if any(s in name for s in stems) or any(w in blob for w in words):
            out.append(t)
    return out


def cmd_next(a):
    P = sa.Paths(a.repo)
    plan, inv = sa.load_plan(P), sa.load_inventory(P)
    if a.cap:
        c = find_cap(plan, a.cap)
    else:
        c = next((x for x in plan["capabilities"] if x["status"] != "done"), None)
        if not c:
            print("Все возможности готовы. Проверка: check.py " + a.repo)
            return 0
    ents = sa.all_entries(inv, plan)
    print(f"# {c['id']} — {c['title'] or '(дай название: plan.py set … --title)'}  [{c['status']}]")
    if c["notes"]:
        print(f"Заметки: {c['notes']}")
    print("\nВходы:")
    files = OrderedDict()
    for eid in c["entries"]:
        e = ents.get(eid)
        if not e:
            print(f"  {eid}  (нет в описи)")
            continue
        print(f"  {eid}  → {e['file']}:{e['line']}" + (f"  (+ {', '.join(e['also'])})" if e.get("also") else ""))
        files[e["file"]] = True
    words = set(re.findall(r"[a-z]+", c["id"])) | {w for eid in c["entries"] for w in re.findall(r"[a-z]{4,}", eid.lower())}
    print("\nЧитай: файлы входов и то, что они вызывают (сервисы, модели, клиенты внешних систем):")
    for f in files:
        print(f"  {f}")
    sdk = [u for u in inv.get("outbound", {}).get("sdk", []) if u["file"] in files]
    calls = [x for x in inv.get("outbound", {}).get("calls", []) if x["file"] in files]
    if sdk or calls:
        print("\nВнешние вызовы в этих файлах (остальные найдёшь, идя по вызовам):")
        for u in sdk:
            print(f"  {u['file']}:{u['line']}  SDK {u['sdk']} ({u['category']})")
        for x in calls:
            print(f"  {x['file']}:{x['line']}  {x['code']}")
    tests = related_tests(inv, files, words)
    if tests:
        print("\nТесты — готовые сценарии (что проверено, то и есть поведение):")
        for t in tests[:15]:
            print(f"  {t['file']}: " + "; ".join(t["titles"][:8]))
    todos = [t for t in inv.get("todos", []) if t["file"] in files]
    if todos:
        print("\nTODO/FIXME в этих файлах — кандидаты в вопросы «баг или так задумано»:")
        for t in todos:
            print(f"  {t['file']}:{t['line']} {t['tag']}: {t['text']}")
    if plan.get("sources"):
        print("\nЧеловеческие спеки — найди разделы про эту возможность и сверь с кодом:")
        for s in plan["sources"]:
            print(f"  {s['ref']}")
    if P.questions.is_file():
        qs = [q for q in sa.parse_questions(P.questions.read_text(encoding="utf-8"))
              if any(cap == c["id"] for cap, _ in sa.affects(q))]
        if qs:
            print("\nВопросы по возможности:")
            for q in qs:
                print(f"  {q['id']} [{sa.effective_status(q)}] {q['title']}")
    spec = P.spec(c["id"])
    print(f"\nПиши: {P.rel(spec)} (шаблон — assets/spec.template.md), строки в {P.rel(P.trace)} под `## {c['id']}`,")
    print(f"вопросы — questions.py add. Затем: check.py {a.repo} --cap {c['id']} → plan.py set {a.repo} {c['id']} --status done")
    return 0


def cmd_add_cap(a):
    P = sa.Paths(a.repo)
    plan = sa.load_plan(P)
    check_id(a.cap)
    if any(c["id"] == a.cap for c in plan["capabilities"]):
        sa.die(f"{a.cap} уже есть")
    plan["capabilities"].append(OrderedDict([("id", a.cap), ("title", a.title or ""), ("status", "todo"),
                                             ("entries", []), ("notes", "")]))
    sa.save_json(P.plan, plan)
    print(f"✓ добавлена {a.cap}")
    return 0


def cmd_rename(a):
    P = sa.Paths(a.repo)
    plan = sa.load_plan(P)
    check_id(a.new)
    c = find_cap(plan, a.cap)
    if a.new != a.cap and any(x["id"] == a.new for x in plan["capabilities"]):
        sa.die(f"{a.new} уже есть — объединяй: plan.py merge {a.repo} {a.cap} {a.new}")
    c["id"] = a.new
    if a.title:
        c["title"] = a.title
    old_spec = P.specs / a.cap
    if old_spec.is_dir() and not (P.specs / a.new).exists():
        shutil.move(str(old_spec), str(P.specs / a.new))
        print(f"  папка спеки перенесена: openspec/specs/{a.new}/")
    sa.save_json(P.plan, plan)
    print(f"✓ {a.cap} → {a.new}" + (f" «{a.title}»" if a.title else ""))
    return 0


def cmd_merge(a):
    P = sa.Paths(a.repo)
    plan = sa.load_plan(P)
    src, dst = find_cap(plan, a.src), find_cap(plan, a.dst)
    if src is dst:
        sa.die("одна и та же возможность")
    dst["entries"] += [e for e in src["entries"] if e not in dst["entries"]]
    if src["notes"]:
        dst["notes"] = (dst["notes"] + " " + src["notes"]).strip()
    plan["capabilities"].remove(src)
    sa.save_json(P.plan, plan)
    if (P.specs / a.src).is_dir():
        print(f"! есть openspec/specs/{a.src}/ — перенеси требования в {a.dst} вручную и удали папку")
    print(f"✓ {a.src} влита в {a.dst} ({len(dst['entries'])} вх.)")
    return 0


def cmd_move(a):
    P = sa.Paths(a.repo)
    plan, inv = sa.load_plan(P), sa.load_inventory(P)
    c = find_cap(plan, a.cap)
    ids = match_entries(a.pattern, list(sa.all_entries(inv, plan)))
    if not ids:
        sa.die(f"под «{a.pattern}» нет входов — точные id: inventory.py show {a.repo}")
    for eid in ids:
        detach(plan, eid)
        c["entries"].append(eid)
    sa.save_json(P.plan, plan)
    print(f"✓ в {a.cap}: " + ", ".join(ids))
    return 0


def cmd_exclude(a):
    P = sa.Paths(a.repo)
    plan, inv = sa.load_plan(P), sa.load_inventory(P)
    if not a.reason.strip():
        sa.die("нужна причина: --reason")
    ids = match_entries(a.pattern, list(sa.all_entries(inv, plan)) + [x for c in plan["capabilities"] for x in c["entries"]])
    ids = list(OrderedDict.fromkeys(ids))
    if not ids:
        sa.die(f"под «{a.pattern}» нет входов")
    for eid in ids:
        detach(plan, eid)
        plan.setdefault("excluded", []).append({"entry": eid, "reason": a.reason})
    sa.save_json(P.plan, plan)
    print(f"✓ исключено ({a.reason}): " + ", ".join(ids))
    return 0


def cmd_prune(a):
    P = sa.Paths(a.repo)
    plan, inv = sa.load_plan(P), sa.load_inventory(P)
    ents = sa.all_entries(inv, plan)
    gone = [eid for eid in sa.assignment(plan) if eid not in ents]
    if not gone:
        print("✓ все входы плана есть в описи")
        return 0
    for eid in gone:
        detach(plan, eid)
    sa.save_json(P.plan, plan)
    print("✓ убраны из плана (нет в описи): " + ", ".join(gone))
    print("  их новые id (если вход переименован) — в plan.py status, раздел «Без возможности»")
    return 0


def cmd_add_entry(a):
    P = sa.Paths(a.repo)
    plan = sa.load_plan(P)
    if ":" not in a.id:
        sa.die("id входа — «<вид>:<имя>», например «http:POST /api/import» или «consumer:kafka orders.created»")
    if not (P.repo / a.file).is_file():
        sa.die(f"нет файла {a.file} (путь — от корня репозитория)")
    kind = a.id.split(":", 1)[0]
    plan.setdefault("manual_entries", []).append({"id": a.id, "kind": kind, "name": a.id.split(":", 1)[1], "file": a.file,
                                                  "line": a.line, "how": "вручную", "tags": [], "also": []})
    if a.cap:
        find_cap(plan, a.cap)["entries"].append(a.id)
    sa.save_json(P.plan, plan)
    print(f"✓ вход {a.id}" + (f" → {a.cap}" if a.cap else " (отнеси к возможности: move)"))
    return 0


def cmd_set(a):
    P = sa.Paths(a.repo)
    plan = sa.load_plan(P)
    c = find_cap(plan, a.cap)
    if a.status:
        if a.status == "done" and not P.spec(a.cap).is_file():
            sa.die(f"нет {P.rel(P.spec(a.cap))} — сначала спека, потом done")
        c["status"] = a.status
    if a.title is not None:
        c["title"] = a.title
    if a.notes is not None:
        c["notes"] = a.notes
    sa.save_json(P.plan, plan)
    print(f"✓ {a.cap}: {c['status']} «{c['title']}»")
    return 0


def cmd_drop(a):
    P = sa.Paths(a.repo)
    plan = sa.load_plan(P)
    c = find_cap(plan, a.cap)
    if c["entries"]:
        sa.die(f"в {a.cap} есть входы ({len(c['entries'])}) — сначала move или merge")
    plan["capabilities"].remove(c)
    sa.save_json(P.plan, plan)
    print(f"✓ удалена {a.cap}")
    return 0


def first_sentence(s):
    s = re.sub(r"\s+", " ", s).strip()
    m = re.match(r"(.+?[.!?])(\s|$)", s)
    return (m.group(1) if m else s)[:200]


def cmd_guide(a):
    P = sa.Paths(a.repo)
    plan = sa.load_plan(P)
    qs = sa.parse_questions(P.questions.read_text(encoding="utf-8")) if P.questions.is_file() else []
    q_by_cap = defaultdict(int)
    for q in qs:
        if sa.effective_status(q) in ("открыт", "отвечен"):
            for cap, _ in sa.affects(q):
                q_by_cap[cap] += 1
    rows = []
    for c in plan["capabilities"]:
        spec = P.spec(c["id"])
        purpose, nreq = "", 0
        if spec.is_file():
            s = sa.parse_spec(spec.read_text(encoding="utf-8"))
            purpose, nreq = first_sentence(s["purpose"]), len(s["requirements"])
        link = f"[`{c['id']}`](../openspec/specs/{c['id']}/spec.md)" if spec.is_file() else f"`{c['id']}` (спеки нет)"
        rows.append(f"| {link} | {c['title']} | {purpose.replace('|', '/')} | {nreq} | {q_by_cap.get(c['id'], 0) or ''} |")
    open_q = sum(1 for q in qs if sa.effective_status(q) == "открыт")
    srcs = ", ".join(s["ref"] for s in plan.get("sources", [])) or "нет — только код"
    text = f"""# Системный контекст

Как сервис работает **сейчас**: восстановлено по коду{', тестам и документам' if plan.get('sources') else ' и тестам'}
(sa-scan, {plan.get('created', '')}; человеческие спеки: {srcs}). Требования — в `openspec/specs/` (формат OpenSpec),
карта системы — в этой папке. Грузи только нужный под задачу файл.

## Задача → файл

| Задача | Открой |
|---|---|
| понять, что делает возможность, и поменять её поведение | `openspec/specs/<id>/spec.md` → затем `openspec/changes/` (дельта) |
| где в коде требование и какие тесты его проверяют | [`trace.md`](trace.md) |
| что значит термин, как назвать новое | [`glossary.md`](glossary.md) |
| сущности, статусы и переходы, роли и права, бизнес-константы | [`domain.md`](domain.md) |
| внешний сервис: когда вызываем, что при отказе, какие настройки | [`integrations.md`](integrations.md) |
| все входы системы (маршруты, очереди, расписания, CLI), env, тесты | [`inventory.md`](inventory.md) |
| что неизвестно и на каком допущении держится спека | [`QUESTIONS.md`](QUESTIONS.md) — открыто: {open_q} |

## Возможности

| id | Название | Назначение | Требований | Открытых вопросов |
|---|---|---|---|---|
""" + "\n".join(rows) + """

## Правила работы

- **Поведение меняется через `openspec/changes/<изменение>/`** — proposal, дельта спеки (`## ADDED/MODIFIED/REMOVED Requirements`), tasks.
  Основные спеки руками не правь: они обновляются при архивации изменения.
- **Пометка `(допущение: Q-…)`** в требовании — поведение описано по догадке. Прежде чем на него опираться, проверь вопрос в `QUESTIONS.md`.
- **Спека описывает «как есть», с багами.** Требование, помеченное как возможная ошибка, — не повод чинить молча: исправление — отдельное изменение.
- **После изменения кода** обнови строки в `trace.md` и, если менялся внешний обмен, `integrations.md`.
- Пересобрать опись после крупных изменений: `inventory.py scan .` (скилл sa-scan), сверка: `check.py .`.
"""
    P.guide.write_text(text, encoding="utf-8")
    print(f"✓ {P.rel(P.guide)}: {len(rows)} возможностей, открытых вопросов {open_q}")
    return 0


def main():
    ap = argparse.ArgumentParser(description="План системного анализа: возможности и входы")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def sp(name, fn, help_):
        p = sub.add_parser(name, help=help_)
        p.add_argument("repo", help="корень репозитория")
        p.set_defaults(fn=fn)
        return p

    p = sp("init", cmd_init, "черновой план из описи + заготовки system-context/ и openspec/")
    p.add_argument("--source", action="append", default=[], help="человеческая спека: путь или URL (можно несколько)")
    p.add_argument("--language", default="ru", help="язык спек (ru, en…), по умолчанию ru")
    p.add_argument("--force", action="store_true", help="пересоздать plan.json")
    sp("status", cmd_status, "что сделано, что осталось, входы без возможности").add_argument("--json", action="store_true")
    sp("next", cmd_next, "что читать и писать для следующей возможности").add_argument("cap", nargs="?")
    p = sp("add-cap", cmd_add_cap, "новая возможность")
    p.add_argument("cap")
    p.add_argument("--title")
    p = sp("rename", cmd_rename, "переименовать возможность")
    p.add_argument("cap")
    p.add_argument("new")
    p.add_argument("--title")
    p = sp("merge", cmd_merge, "влить одну возможность в другую")
    p.add_argument("src")
    p.add_argument("dst")
    p = sp("move", cmd_move, "отнести входы к возможности")
    p.add_argument("pattern")
    p.add_argument("cap")
    p = sp("exclude", cmd_exclude, "исключить входы с причиной")
    p.add_argument("pattern")
    p.add_argument("--reason", required=True)
    sp("prune", cmd_prune, "убрать из плана входы, которых больше нет в описи")
    p = sp("add-entry", cmd_add_entry, "вход, которого нет в описи")
    p.add_argument("id")
    p.add_argument("--file", required=True)
    p.add_argument("--line", type=int, default=1)
    p.add_argument("--cap")
    p = sp("set", cmd_set, "статус, название, заметки возможности")
    p.add_argument("cap")
    p.add_argument("--status", choices=["todo", "done"])
    p.add_argument("--title")
    p.add_argument("--notes")
    sp("drop-cap", cmd_drop, "удалить пустую возможность").add_argument("cap")
    sp("guide", cmd_guide, "собрать system-context/GUIDE.md")
    a = ap.parse_args()
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
