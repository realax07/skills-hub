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
  python3 plan.py brief <repo> <cap> [<cap>…] | --all          (режим раздачи)
  python3 plan.py collect <repo> [<cap>…]                       (режим раздачи)

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
                "http", "web", "rest", "v1", "v2", "v3", "public", "private", "backend", "packages", "services",
                "eventhandling", "integrationevents", "domaineventhandlers", "application", "apis", "components",
                "infrastructure", "quickstart", "endpoints", "pages"}
SKIP_SEG = re.compile(r"^(api|v\d+|rest|public|internal|private|\{.*\}|)$", re.I)


def draft_group(e, multi=False):
    """Черновая группа для входа: первый значимый сегмент пути или папка/файл обработчика.
    В монорепо (multi) — по сервису: всё, что не /api/<сегмент>, группируется по пакету."""
    pkg = e.get("package") or "."
    short = sa.kebab(Path(pkg).name) if pkg != "." else ""
    if multi and short:
        if e["kind"] == "http":
            m = re.match(r"^\w+ /api/(?:v\d+/)?([^/{]+)", e["name"])
            return sa.kebab(m.group(1)) if m else short
        if e["kind"] == "consumer":
            return f"{short}-events"
        if e["kind"] in ("ui", "schedule", "cli"):
            return f"{short}-{e['kind']}"
        return short
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


def no_match(pattern, ids, repo):
    words = [w for w in re.findall(r"[\w{}/.-]{3,}", pattern.lower()) if w not in ("http", "get", "post")]
    near = [i for i in ids if any(w in i.lower() for w in words)][:8]
    msg = (f"под «{pattern}» нет входов. id — с видом в начале («http:GET /documents», «consumer:…»); "
           f"шаблон — с * («http:* /documents*»), регулярное выражение — «re:…». Все id: inventory.py show {repo}")
    if near:
        msg += "\n  похожие: " + "; ".join(near)
    return msg


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
        multi = len({e.get("package") for e in inv["entries"] if e.get("package") not in (None, ".")}) >= 3
        for e in inv["entries"]:
            if "служебное" in e.get("tags", []) or "ci" in e.get("tags", []):
                excluded.append({"entry": e["id"], "reason": "служебное (health, метрики, CI) — проверь"})
                continue
            groups.setdefault(draft_group(e, multi), []).append(e["id"])
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


GENERIC_WORDS = {"order", "orders", "item", "items", "test", "tests", "user", "api", "http", "post", "get", "put",
                 "delete", "event", "events", "service", "handler", "status", "data", "create", "update"}


def related_tests(inv, files, words):
    """Тесты возможности: файл теста назван как файл кода, или в названии теста/файла есть слово возможности (не общее).
    Тесты без проверок (0 названий) не показываются."""
    out = []
    words = {w.lower() for w in words if len(w) > 3 and w.lower() not in GENERIC_WORDS}
    stems = {Path(f).stem.lower().split(".")[0] for f in files}
    stems = {s for s in stems if len(s) > 3 and s not in ("program", "extensions", "index", "main", "server", "globalusings")}
    for t in inv.get("tests", []):
        if not t.get("count"):
            continue
        name = Path(t["file"]).name.lower()
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
            stub = f" [заглушек или пропусков: {t['stubs']} — не доказательство поведения]" if t.get("stubs") else ""
            print(f"  {t['file']}{stub}: " + "; ".join(t["titles"][:8]))
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
    cpath = P.ctx / "contracts.md"
    if cpath.is_file():
        import subprocess
        r = subprocess.run([sys.executable, str(Path(__file__).resolve().parent / "contracts.py"), "show", str(P.repo), "--cap", c["id"]],
                           capture_output=True, text=True)
        body = re.sub(r"<!-- sa:auto(?: id=\"[^\"]*\")? -->\n|<!-- sa:auto-end -->\n?", "", r.stdout).strip()
        lines = body.split("\n")
        print("\nКонтракты и данные (из contracts.md и data.md — сверь с кодом; требование называет вход: метод и путь, RPC, событие):")
        print("\n".join("  " + x for x in lines[:120]) if body and "ничего не найдено" not in body else "  разделов не найдено")
        if len(lines) > 120:
            print(f"  … ещё {len(lines) - 120} строк: contracts.py show {a.repo} --cap {c['id']}")
    else:
        print(f"\n! нет {P.rel(cpath)} — сначала contracts.py scan {a.repo}: поля, ответы, события и вызывающие для этой возможности")
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
        sa.die(no_match(a.pattern, list(sa.all_entries(inv, plan)), a.repo))
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
        sa.die(no_match(a.pattern, list(sa.all_entries(inv, plan)), a.repo))
    for eid in ids:
        detach(plan, eid)
        plan.setdefault("excluded", []).append({"entry": eid, "reason": a.reason})
    sa.save_json(P.plan, plan)
    print(f"✓ исключено ({a.reason}), входов: {len(ids)}: " + ", ".join(ids))
    ents = sa.all_entries(inv, plan)
    client = [i for i in ids if re.search(r"(^|/)[\w.-]*(client|mobile|maui|android|ios|hybrid|frontend|spa|desktop)[\w.-]*(/|$)",
                                           (ents.get(i) or {}).get("file", "") + " " + i, re.I)
              or re.search(r"клиент|мобильн|maui|hybrid|приложени", a.reason, re.I)]
    if client:
        print(f"! {len(client)} из них — клиентский код. Клиент — не вход, но потребитель контрактов: что он вызывает и на что опирается "
              f"(статусы, коды ответа, поля), должно попасть в contracts.md, раздел «Кто вызывает входы» — contracts.py scan его найдёт, "
              f"заполни «Опирается на». Исключать вход клиента можно, забывать клиента — нет.")
    if len(ids) > 5:
        print(f"! шаблон захватил {len(ids)} входов — проверь список; вернуть нужный: plan.py move {a.repo} \"<id>\" <cap>")
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
        if a.status == "done" and not a.force:
            import subprocess
            r = subprocess.run([sys.executable, str(Path(__file__).resolve().parent / "check.py"), str(P.repo), "--cap", a.cap,
                                "--no-cli", "--json"], capture_output=True, text=True)
            try:
                errs = json.loads(r.stdout).get("errors", [])
            except ValueError:
                errs = [r.stderr.strip() or "check.py не отработал"]
            if errs:
                print("\n".join(f"✗ {e}" for e in errs), file=sys.stderr)
                sa.die(f"{a.cap}: check.py --cap нашёл ошибки ({len(errs)}) — исправь, потом done (обойти: --force)")
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


def _ranges(path):
    """«a.ts:10-20» → ('a.ts', (10, 20)); без строк — весь файл."""
    m = re.match(r"^(.*?):(\d+)(?:-(\d+))?$", path.strip())
    if not m:
        return path.strip(), None
    lo = int(m.group(2))
    return m.group(1), (lo, int(m.group(3) or lo))


def parallel_map(P, plan):
    """По trace.md: где возможности делят код. Жёстко — пересекаются строки (или файл без строк), мягко — тот же файл, разные места.
    Возвращает (pairs, waves, hot): pairs — (x, y, hard_files, soft_files)."""
    if not P.trace.is_file():
        return [], [], []
    tr = sa.parse_trace(P.trace.read_text(encoding="utf-8"))
    ids = [c["id"] for c in plan["capabilities"] if c["id"] in tr]
    spans = {}
    for cap in ids:
        d = defaultdict(list)
        for rec in tr[cap].values():
            for pth in rec["code"]:
                f, r = _ranges(pth)
                d[f].append(r)
        spans[cap] = d

    def overlap(r1, r2):
        if r1 is None or r2 is None:
            return True
        return r1[0] <= r2[1] + 3 and r2[0] <= r1[1] + 3   # рядом стоящие строки — тоже столкновение

    pairs = []
    for i, x in enumerate(ids):
        for y in ids[i + 1:]:
            hard, soft = [], []
            for f in sorted(set(spans[x]) & set(spans[y])):
                if any(overlap(r1, r2) for r1 in spans[x][f] for r2 in spans[y][f]):
                    hard.append(f)
                else:
                    soft.append(f)
            if hard or soft:
                pairs.append((x, y, hard, soft))
    conflict = defaultdict(set)
    for x, y, hard, _ in pairs:
        if hard:
            conflict[x].add(y)
            conflict[y].add(x)
    waves = []
    for cap in sorted(ids, key=lambda c: -len(conflict[c])):
        for w in waves:
            if not (conflict[cap] & set(w)):
                w.append(cap)
                break
        else:
            waves.append([cap])
    use = defaultdict(list)
    for cap in ids:
        for f in spans[cap]:
            use[f].append(cap)
    hot = sorted(((f, cs) for f, cs in use.items() if len(cs) >= 3), key=lambda x: -len(x[1]))
    return pairs, waves, hot


def parallel_section(P, plan):
    pairs, waves, hot = parallel_map(P, plan)
    if not waves:
        return ""
    out = ["", "## Параллельная работа", "",
           "Посчитано по `trace.md`. **Конфликт** — возможности трогают одни и те же строки: параллельно разным агентам не отдавай.",
           "**Тот же файл** — разные места одного файла: можно параллельно, но сливай по очереди и проверь сборку.",
           "Смысловые пересечения (общая сущность, статус, внешняя система) отсюда не видны — смотри `domain.md` и `integrations.md`.", "",
           "**Волны** — внутри волны нет конфликтов, возможности можно менять параллельно:", ""]
    for i, w in enumerate(waves, 1):
        out.append(f"{i}. " + ", ".join(f"`{c}`" for c in w))
    if pairs:
        out += ["", "| Возможность | С чем | Конфликт (те же строки) | Тот же файл, разные места |", "|---|---|---|---|"]
        for x, y, hard, soft in pairs:
            fmt = lambda fs: ", ".join(f"`{f}`" for f in fs[:5]) + (" …" if len(fs) > 5 else "") if fs else "—"
            out.append(f"| `{x}` | `{y}` | {fmt(hard)} | {fmt(soft)} |")
    else:
        out += ["", "Общего кода у возможностей нет — любые изменения можно вести параллельно."]
    if hot:
        out += ["", "**Общие файлы** (в трёх и больше возможностях) — их рефакторинг затрагивает всех; делай его отдельной задачей:", ""]
        out += [f"- `{f}` — " + ", ".join(f"`{c}`" for c in cs) for f, cs in hot[:15]]
    return "\n".join(out) + "\n"


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
| поля запроса и ответа, коды ответа, события и подписчики, **кто ещё вызывает вход** (клиенты, шлюзы, ИИ) | [`contracts.md`](contracts.md) |
| новое поле или таблица: где сущность создаётся и копируется, миграции, засев, конкурентность, транзакции, валидация | [`data.md`](data.md) |
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
- **Прежде чем менять вход, событие или сущность** — её раздел в `contracts.md` и `data.md`: кто ещё на неё опирается
  и куда копируются поля. Ломающее изменение контракта — отдельный пункт в proposal изменения.
- **После изменения кода** обнови строки в `trace.md` и, если менялся внешний обмен, `integrations.md`.
- Пересобрать опись после крупных изменений: `inventory.py scan .`, `contracts.py scan .` (скилл sa-scan; заметки вне блоков сохранятся), сверка: `check.py .`.
- Раздаёшь изменения нескольким агентам — сначала раздел «Параллельная работа» ниже.
""" + parallel_section(P, plan)
    P.guide.write_text(text, encoding="utf-8")
    print(f"✓ {P.rel(P.guide)}: {len(rows)} возможностей, открытых вопросов {open_q}")
    return 0


# ---------- режим раздачи: бриф работнику и сборка результатов

WORK_Q_HEAD = """# Вопросы работника — {cap}

Формат — как в system-context/QUESTIONS.md, но номера временные: TMP-1, TMP-2… (по порядку, без пропусков).
Пометка в спеке — (допущение: TMP-1). Настоящие номера присвоит `plan.py collect`.
Поля: Статус (всегда «открыт»), Важность (блокирует | уточняет), Категория (из списка), Что видно (с путь:строка),
Затрагивает ({cap} / <Имя требования>), Допущение, Кто ответит (роль), Ответ (строка обязательна, значение пустое).
Образец (скопируй ниже, без строк ```, N замени на номер; заголовок заканчивается «?»):

```
### TMP-N. Сколько позиций допускается в заказе: 30 или 50?
- **Статус:** открыт
- **Важность:** блокирует
- **Категория:** расхождение кода и документа
- **Что видно:** PRD п.1 — до 30; код — MAX_ITEMS = 50 (src/routes/orders.ts:10)
- **Затрагивает:** {cap} / Проверка состава заказа
- **Допущение:** спека описывает код: до 50
- **Кто ответит:** владелец продукта
- **Ответ:**
```

Категории: внешний сервис; потребители API; конфигурация и окружение; данные в проде; расхождение кода и документа;
баг или так задумано; мёртвый код; ручные процессы; права и роли; нефункциональное; правовое и регуляторное; другое.
Твои вопросы — ниже этой строки.
"""
WORK_TRACE_HEAD = """# Трассировка работника — {cap}

Строка на каждое требование: - <Имя требования, как в spec.md> → путь:строка, путь:10-20, 31-35 | тесты: путь (пояснение)
Заголовок `## <возможность>` не нужен. Нет тестов — `| тесты: —`. Номера строк — по коду (`grep -n`): проверка сверяет их с длиной файла.
"""
WORK_NOTES_HEAD = """# Заметки работника — {cap}

Для главного агента: он перенесёт их в общие файлы. Пиши фактами со ссылками путь:строка. Нечего сказать — «нет».

## Интеграции
<!-- внешние системы, которые трогает эта возможность: направление, когда, данные, что при отказе, env-имена, где в коде -->

## Предметная область
<!-- сущности и поля, переходы статусов «ИЗ → В: когда», проверки прав, константы -->

## Глоссарий
<!-- новые термины: термин | значение | в коде -->

## Контракты
<!-- уточнения к contracts.md по входам и событиям этой возможности: ответы и ошибки из глубины вызовов (исключение → 500),
поля, которые вызывающие читают или сравнивают (клиент ждёт статус Submitted, ловит только 400), расхождения копий событий -->

## Ограничения
<!-- транзакции и их границы, что публикуется вне транзакции, повторы и порядок событий, идемпотентность,
гонки и конкурентные изменения, валидация (подключена ли), задержки и таймауты — со ссылками путь:строка -->

## Границы
<!-- поведение, которое увидел, но оно относится к другой возможности: какой и что именно (вопрос по нему не заводи — это сделает её работник) -->

## Прочее
<!-- всё остальное, что важно главному агенту: тесты-заглушки, неиспользуемые флаги, запуск в нескольких экземплярах и т.п. -->
"""


def _capture(fn, *args):
    import io
    from contextlib import redirect_stdout
    buf = io.StringIO()
    with redirect_stdout(buf):
        fn(*args)
    return buf.getvalue()


def cmd_brief(a):
    P = sa.Paths(a.repo)
    plan = sa.load_plan(P)
    caps = [c for c in plan["capabilities"] if c["status"] != "done"] if a.all else [find_cap(plan, x) for x in a.caps]
    if not caps:
        sa.die("нечего раздавать: укажи возможности или --all (берёт все со статусом todo)")
    qs = sa.parse_questions(P.questions.read_text(encoding="utf-8")) if P.questions.is_file() else []
    skill = sa.SKILL_DIR
    made = []
    for c in caps:
        if not c["title"].strip():
            sa.die(f"у {c['id']} нет названия — plan.py set {a.repo} {c['id']} --title \"…\" до раздачи")
        d = P.workdir(c["id"])
        if (d / "BRIEF.md").exists() and not a.force:
            print(f"· {c['id']}: бриф уже есть ({P.rel(d / 'BRIEF.md')}), пересоздать — --force")
            made.append(c["id"])
            continue
        d.mkdir(parents=True, exist_ok=True)
        ns = argparse.Namespace(repo=a.repo, cap=c["id"])
        task = _capture(cmd_next, ns)
        task = task.split("\nПиши:")[0].rstrip()
        task = re.sub(r"\nЧеловеческие спеки — [^\n]*\n(?:  [^\n]*\n?)*", "\n", task)
        others = "\n".join(f"- `{x['id']}` — {x['title']}" for x in plan["capabilities"] if x["id"] != c["id"])
        known = "\n".join(f"- {q['id']}: {q['title']}" for q in qs if sa.effective_status(q) == "открыт") or "- нет"
        srcs = plan.get("sources") or []
        human = ("Человеческие спеки: " + ", ".join(f"`{x['ref']}`" for x in srcs) + " — найди разделы про эту возможность и сверь с кодом.") if srcs \
            else "Человеческих спек нет — сверяй только с кодом и тестами; в отчёте напиши «человеческой спеки нет»."
        repo = P.repo
        brief = f"""# Бриф: возможность `{c['id']}` — {c['title']}

Ты — работник системного анализа (скилл sa-scan, режим раздачи). Опиши, **как эта возможность работает сейчас**, по коду.
Пиши **только** файлы ниже. Общие файлы (`system-context/QUESTIONS.md`, `trace.md`, `integrations.md`, `domain.md`, `glossary.md`, `plan.json`)
не трогай: их соберёт главный агент. Скрипты, меняющие общие файлы (`questions.py add`, `plan.py set`), не запускай.

Репозиторий: `{repo}`

## Что прочитать о формате и правилах

- `{skill}/references/openspec-format.md` — формат spec.md, разделы «Структура» и «Основная спека» (обязательно; дельты не нужны).
- `{skill}/references/rules.md` — разделы «Требования и сценарии», «Источники и конфликты».
- `{skill}/references/questions.md` — какие вопросы задавать и как.
- `{skill}/assets/spec.template.md` — заготовка спеки.
- Термины: `{P.rel(P.ctx / 'glossary.md')}` (пиши этими словами), статусы: `{P.rel(P.ctx / 'domain.md')}`.

## Что исследовать

{human}

{task}

Иди по вызовам от входов до БД и внешних систем. Код не запускай, внешние системы не вызывай.
Поведение соседней возможности не описывай и вопросов по нему не заводи — запиши в заметки, раздел «Границы»
(TODO из общего файла тоже может быть чужим). Поведение, общее для двух возможностей, описывай с той стороны, где вход,
а у себя — только как оно влияет на твою возможность. Тест без реальной проверки (`expect(true)`, `assert True`) — не доказательство:
отметь в «Прочее». Поведение библиотеки, которое не проверить без запуска, — «вероятно» и вопрос, в «Что видно» — «по знанию X, не проверено». Соседи:

{others}

Уже открытые вопросы (не дублируй — сошлись в заметках, если твоя возможность тоже от них зависит):

{known}

## Что написать

1. `openspec/specs/{c['id']}/spec.md` (папку создай) — спека по формату OpenSpec, «как есть», с багами; 2–12 требований
   (больше — скажи в отчёте, главный агент поделит возможность), текст требования до 500 символов вместе с пометками; расхождение с человеческой спекой
   и всё про внешний мир — вопросом, в требовании пометка `(допущение: TMP-1)`. Зависишь от уже открытого вопроса — пометка с его номером `(допущение: Q-004)`.
2. `{P.rel(d / 'questions.md')}` — твои вопросы с номерами TMP-1, TMP-2… (формат — в заголовке файла).
3. `{P.rel(d / 'trace.md')}` — строка «требование → код | тесты» на каждое требование.
4. `{P.rel(d / 'notes.md')}` — заметки для интеграций, предметной области, глоссария, контрактов, ограничений и о границах.
   Контракты и данные твоих входов собраны в разделе «Контракты и данные» выше: сверь ответы и поля с кодом, недостающее
   (ошибки из глубины вызовов, что вызывающие ждут от ответа) — в «Контракты», транзакции, повторы, гонки, валидацию — в «Ограничения».

## Проверка — до сдачи

`python3 {skill}/scripts/check.py {repo} --cap {c['id']} --work` — без ✗ (предупреждения можно оставить, если понятно, почему).
Затем короткий отчёт главному агенту: сколько требований и вопросов, расхождения с человеческой спекой (нет — так и напиши),
главные находки, что вынес в «Границы».
"""
        (d / "BRIEF.md").write_text(brief, encoding="utf-8")
        for name, head in (("questions.md", WORK_Q_HEAD), ("trace.md", WORK_TRACE_HEAD), ("notes.md", WORK_NOTES_HEAD)):
            if not (d / name).exists():
                (d / name).write_text(head.format(cap=c["id"]), encoding="utf-8")
        made.append(c["id"])
        print(f"✓ {P.rel(d / 'BRIEF.md')}")
    print(f"\nРаздай: по одному работнику на возможность (мелкие — по 2–3 на работника), задание — assets/worker-prompt.md с путём к брифу.")
    print(f"Сдали — plan.py collect {a.repo}")
    return 0


def _set_section(text, cap, body):
    """Вставить или заменить раздел `## cap` в trace.md."""
    lines = text.rstrip("\n").split("\n")
    start = next((i for i, ln in enumerate(lines) if re.match(rf"^##\s+`?{re.escape(cap)}`?\s*$", ln)), None)
    block = [f"## {cap}"] + body
    if start is None:
        return "\n".join(lines + [""] + block) + "\n"
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
    return "\n".join(lines[:start] + block + [""] + lines[end:]).rstrip("\n") + "\n"


def cmd_collect(a):
    import subprocess
    P = sa.Paths(a.repo)
    plan = sa.load_plan(P)
    if not P.work.is_dir():
        sa.die(f"нет {P.rel(P.work)} — раздачи не было (plan.py brief)")
    caps = a.caps or sorted(d.name for d in P.work.iterdir() if d.is_dir() and not d.name.startswith("_"))
    if not caps:
        print("нечего собирать: все результаты уже собраны")
        return 0
    qtext = P.questions.read_text(encoding="utf-8")
    done, failed, new_q, big = [], [], [], []
    check = Path(__file__).resolve().parent / "check.py"
    for cap in caps:
        find_cap(plan, cap)
        d = P.workdir(cap)
        if not d.is_dir():
            failed.append((cap, f"нет {P.rel(d)}"))
            continue
        r = subprocess.run([sys.executable, str(check), str(P.repo), "--cap", cap, "--work", "--no-cli", "--json"],
                           capture_output=True, text=True)
        try:
            errs = json.loads(r.stdout).get("errors", [])
        except ValueError:
            errs = [r.stderr.strip() or "check.py не отработал"]
        if errs:
            failed.append((cap, f"{len(errs)} ошибок: " + "; ".join(errs[:3])))
            continue
        # вопросы: TMP → настоящие номера
        wq = sa.parse_questions((d / "questions.md").read_text(encoding="utf-8")) if (d / "questions.md").is_file() else []
        mapping = {}
        for q in wq:
            num = sa.next_qnum(sa.parse_questions(qtext))
            qid = f"Q-{num:03d}"
            mapping[q["id"]] = qid
            fields = dict(q["fields"])
            fields["Статус"] = "открыт"
            qtext = qtext.rstrip() + "\n\n" + sa.question_block(qid, q["title"], fields) + "\n"
            new_q.append((qid, q["title"], cap))
        spec = P.spec(cap)
        st = spec.read_text(encoding="utf-8")
        st = sa.TMP_RX.sub(lambda m: mapping.get(m.group(0), m.group(0)), st)
        spec.write_text(st, encoding="utf-8")
        # трассировка
        body = [ln for ln in (d / "trace.md").read_text(encoding="utf-8").splitlines() if re.match(r"^\s*[-*]\s+.+(→|->)", ln)]
        P.trace.write_text(_set_section(P.trace.read_text(encoding="utf-8"), cap, body), encoding="utf-8")
        # заметки — в общий файл для главного агента
        notes = (d / "notes.md").read_text(encoding="utf-8") if (d / "notes.md").is_file() else ""
        notes = re.sub(r"<!--[\s\S]*?-->\n?", "", notes.split("\n", 1)[-1]).strip()
        notes = sa.TMP_RX.sub(lambda m: mapping.get(m.group(0), m.group(0)), notes)
        with (P.work / "NOTES.md").open("a", encoding="utf-8") as fh:
            fh.write(f"\n# {cap}\n\n{notes}\n")
        # те же заметки по разделам — чтобы сводить каждый общий файл отдельно (можно раздать субагентам)
        for sec, body in re.findall(r"^##\s+(.+?)\s*\n([\s\S]*?)(?=^##\s|\Z)", notes, re.M):
            body = body.strip()
            if not body or body.lower() in ("нет", "нет.", "—"):
                continue
            key = {"интеграции": "integrations", "предметная область": "domain", "глоссарий": "glossary",
                   "границы": "boundaries", "контракты": "contracts", "ограничения": "constraints"}.get(sec.strip().lower(), "other")
            with (P.work / f"NOTES-{key}.md").open("a", encoding="utf-8") as fh:
                fh.write(f"\n# {cap}\n\n{body}\n")
        nreq = len(sa.parse_spec(st)["requirements"])
        if nreq > 12:
            big.append((cap, nreq))
        dest = P.work / "_done" / cap
        if dest.exists():
            shutil.rmtree(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(d), str(dest))
        find_cap(plan, cap)["status"] = "done"
        done.append((cap, len(mapping)))
    P.questions.write_text(sa.replace_index(qtext, sa.parse_questions(qtext)), encoding="utf-8")
    sa.save_json(P.plan, plan)
    for cap, n in done:
        print(f"✓ {cap}: спека, трассировка, вопросов {n}")
    for cap, why in failed:
        print(f"✗ {cap}: не собрано — {why}. Верни работнику или исправь и повтори collect {cap}")
    # похожие вопросы — кандидаты в дубли
    allq = [q for q in sa.parse_questions(qtext) if sa.effective_status(q) == "открыт"]
    newids = {x[0] for x in new_q}
    pairs = []
    for i, q1 in enumerate(allq):
        for q2 in allq[i + 1:]:
            if (q1["id"] in newids or q2["id"] in newids) and sa.near_duplicate(q1, q2):
                pairs.append((q1["id"], q2["id"], q1["title"], q2["title"]))
    if pairs:
        print("\nПохожие вопросы — проверь, не дубли ли (объединить: questions.py merge <repo> <дубль> <оставить>):")
        for x, y, tx, ty in pairs:
            print(f"  {x} ≈ {y}: «{tx}» / «{ty}»")
    for cap, n in big:
        print(f"! {cap}: {n} требований — больше 12, подумай, не поделить ли возможность (rules.md, «Возможности»)")
    if done:
        print(f"\nЗаметки работников по разделам — {P.rel(P.work)}/NOTES-integrations.md, NOTES-domain.md, NOTES-glossary.md,")
        print("NOTES-contracts.md, NOTES-constraints.md, NOTES-boundaries.md, NOTES-other.md (всё вместе — NOTES.md).")
        print("Сведи каждый в свой общий файл — сам или по субагенту на файл: integrations.md, domain.md, glossary.md;")
        print("контракты — в contracts.md строкой «Заметки: …» под блоком входа или события (не внутри блока sa:auto),")
        print("ограничения — в data.md («Что это значит») и integrations.md («При отказе»); «Границы» сверь с соседними спеками.")
        print(f"Затем сократи вопросы (references/fan-out.md, шаг 8) и удали {P.rel(P.work)}/.")
    return 1 if failed else 0


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
    p.add_argument("--force", action="store_true", help="done без проверки check.py --cap")
    p.add_argument("--title")
    p.add_argument("--notes")
    sp("drop-cap", cmd_drop, "удалить пустую возможность").add_argument("cap")
    sp("guide", cmd_guide, "собрать system-context/GUIDE.md")
    p = sp("brief", cmd_brief, "режим раздачи: бриф работнику в system-context/.work/<cap>/")
    p.add_argument("caps", nargs="*")
    p.add_argument("--all", action="store_true", help="все возможности со статусом todo")
    p.add_argument("--force", action="store_true", help="пересоздать бриф")
    p = sp("collect", cmd_collect, "режим раздачи: собрать результаты работников в общие файлы")
    p.add_argument("caps", nargs="*")
    a = ap.parse_args()
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
