#!/usr/bin/env python3
"""Планирование изменения по слою sa-scan: что затронуто, кого это заденет, пакет для dev-агентов, проверка пакета.

  python3 change.py layer <repo>                                     слой на месте и свежий? что ещё есть (design-context, test-cases)
  python3 change.py find <repo> --text "отмена оплаченного заказа"   какие возможности, входы, события, сущности затронуты
  python3 change.py new <repo> <id> --title "…"                      openspec/changes/<id>/: proposal, design, tasks из шаблонов
  python3 change.py analyze <repo> <id> --cap a,b [--entry …] [--event …] [--entity …] [--file …]
                                                                     impact.md: вызывающие, подписчики, места поля, вопросы, кейсы, проверки
  python3 change.py req <repo> <cap> ["<Имя требования>"]            требование целиком — для MODIFIED (без имени — список имён)
  python3 change.py check <repo> <id>                                пакет готов для dev-агентов? (дельты, влияние, задачи, вопросы)
  python3 change.py waves <repo>                                     активные изменения → волны без общих файлов

Читает слой sa-scan (system-context/, openspec/specs/) и, если есть, test-cases/ (qa-scan) и design-context/ (wd-scan).
Пишет только в openspec/changes/<id>/ и system-context/WAVES.md. Python 3.9+, только стандартная библиотека.
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
from collections import OrderedDict, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import sa  # noqa: E402

PLACEHOLDER = "<!-- заполнить"
ASSETS = Path(__file__).resolve().parent.parent / "assets" / "change"
ITEM_RX = re.compile(r"^- \[[ xX]\] ([A-Z]{1,2}-\d{2,}) (.*)$")
TASK_RX = re.compile(r"^\s*- \[[ xX]\] (\d+\.\d+)\s+(.+)$")
DECISION_RX = re.compile(r"^\s+- \*\*Решение:\*\*\s*(.*)$")
REF_RX = re.compile(r"[\w./-]+\.[A-Za-z]{1,6}(?::\d+)?|`[^`]+`")


def ok(msg):
    print(f"✓ {msg}")


def warn(msg):
    print(f"! {msg}")


def words(s):
    """Грубая основа слова: первые 5 букв — хватает, чтобы «отмена» нашла «отменить», «отменённый»."""
    return {w[:5] for w in re.findall(r"[a-zа-яё0-9]{3,}", (s or "").lower()) if len(w) >= 3}


class Layer:
    def __init__(self, repo):
        self.P = sa.Paths(repo)
        P = self.P
        self.plan = json.loads(P.plan.read_text(encoding="utf-8")) if P.plan.is_file() else None
        cj = P.ctx / "contracts.json"
        self.cj = json.loads(cj.read_text(encoding="utf-8")) if cj.is_file() else {}
        self.trace = sa.parse_trace(P.trace.read_text(encoding="utf-8")) if P.trace.is_file() else {}
        self.qs = sa.parse_questions(P.questions.read_text(encoding="utf-8")) if P.questions.is_file() else []
        self.notes = self._notes(P.ctx / "contracts.md")
        self.design = (P.repo / "design-context" / "GUIDE.md").is_file()
        tc = P.repo / "test-cases" / "_index" / "index.json"
        self.cases = json.loads(tc.read_text(encoding="utf-8")).get("cases", []) if tc.is_file() else None

    @staticmethod
    def _notes(path):
        out = {}
        if not path.is_file():
            return out
        for m in re.finditer(r"^### (.+)\n([\s\S]*?)(?=^### |^## |\Z)", path.read_text(encoding="utf-8"), re.M):
            tail = m.group(2).split("<!-- sa:auto-end -->", 1)[-1]
            tail = re.sub(r"<!--[\s\S]*?-->", "", tail).strip()
            if tail:
                out[m.group(1).strip()] = re.sub(r"\s+", " ", tail)
        return out

    def caps(self):
        return OrderedDict((c["id"], c) for c in (self.plan or {}).get("capabilities", []))

    def spec(self, cap):
        p = self.P.spec(cap)
        return sa.parse_spec(p.read_text(encoding="utf-8")) if p.is_file() else None


def need_layer(L):
    miss = [x for x in ("plan.json", "trace.md", "QUESTIONS.md", "GUIDE.md") if not (L.P.ctx / x).is_file()]
    if miss or not L.P.specs.is_dir():
        sa.die(f"нет слоя sa-scan ({', '.join(miss) or 'openspec/specs/'}) — сначала скилл sa-scan: без карты системы влияние не посчитать")


# ---------------------------------------------------------------- layer

def git(repo, *args):
    try:
        r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, timeout=30)
        return r.stdout.strip() if r.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def cmd_layer(a):
    L = Layer(a.repo)
    P = L.P
    problems = 0
    for name, what in [("GUIDE.md", "гайд"), ("plan.json", "план"), ("trace.md", "трассировка"), ("QUESTIONS.md", "вопросы"),
                       ("contracts.json", "контракты (contracts.py scan)"), ("data.md", "данные (contracts.py scan)")]:
        if (P.ctx / name).is_file():
            ok(f"{P.rel(P.ctx / name)}")
        else:
            warn(f"нет {P.rel(P.ctx / name)} — {what}: без него влияние будет неполным")
            problems += 1
    caps = list(L.caps())
    cards = [c for c in caps if (P.ctx / "caps" / f"{c}.md").is_file()]
    print(f"· возможностей {len(caps)}, карточек {len(cards)}, спек {len(list(P.specs.glob('*/spec.md'))) if P.specs.is_dir() else 0}")
    if len(cards) < len(caps):
        warn("карточек меньше, чем возможностей — в слое: python3 <sa-scan>/scripts/plan.py guide .")
    # свежесть: коммиты в коде после последнего изменения слоя
    last = git(P.repo, "log", "-1", "--format=%H", "--", "system-context")
    if last:
        n = git(P.repo, "rev-list", "--count", f"{last}..HEAD", "--", ".", ":!system-context", ":!openspec")
        if n and int(n) > 0:
            warn(f"после последнего обновления слоя {n} коммитов в коде — слой мог устареть (sa-scan, режим C), затронутое сверяй с кодом")
        else:
            ok("слой не старше кода (по git)")
    else:
        print("· git-история слоя не найдена — свежесть не проверить")
    print(f"· design-context/: {'есть — интерфейсные правки проверяются wd-fit' if L.design else 'нет'}")
    print(f"· test-cases/: {'есть, кейсов ' + str(len(L.cases)) if L.cases is not None else 'нет (или нет индекса — qa-scan: route.py index)'}")
    active = [d.name for d in sorted((P.openspec / "changes").glob("*")) if d.is_dir() and d.name != "archive"]
    print(f"· активные изменения: {', '.join(active) or 'нет'}")
    print(f"· CLI openspec: {'есть' if shutil.which('openspec') else 'нет — проверка формата только своя'}")
    if L.qs:
        blk = [q for q in L.qs if sa.effective_status(q) == "открыт" and q["fields"].get("Важность") == "блокирует"]
        print(f"· открытых блокирующих вопросов: {len(blk)}")
    return 1 if problems > 2 else 0


# ---------------------------------------------------------------- find

def cmd_find(a):
    L = Layer(a.repo)
    need_layer(L)
    q = words(a.text)
    if not q:
        sa.die("нужен --text со словами задачи")
    rows = []
    for cid, c in L.caps().items():
        card = L.P.ctx / "caps" / f"{cid}.md"
        sp = L.spec(cid) or {"purpose": "", "requirements": []}
        hay_title = words(c.get("title", "") + " " + cid + " " + sp["purpose"])
        hay_req = words(" ".join(r["name"] for r in sp["requirements"]))
        hay_card = words(card.read_text(encoding="utf-8")) if card.is_file() else set()
        score = 3 * len(q & hay_title) + 2 * len(q & hay_req) + len(q & hay_card)
        if score:
            hits = [r["name"] for r in sp["requirements"] if q & words(r["name"])][:4]
            rows.append((score, cid, c.get("title", ""), hits))
    rows.sort(reverse=True)
    print("Возможности (чем выше балл, тем вероятнее затронута; проверь карточку system-context/caps/<id>.md):")
    for score, cid, title, hits in rows[:a.limit]:
        print(f"  {score:3}  {cid} — {title}" + (f"\n        требования: {'; '.join(hits)}" if hits else ""))
    if not rows:
        print("  ничего — переформулируй словами из GUIDE.md (таблица «Возможности») или открой её глазами")
    ents = [r for r in L.cj.get("entries", []) if q & words(r["id"] + " " + (r.get("symbol") or ""))]
    if ents:
        print("\nВходы:")
        for r in ents[:a.limit]:
            print(f"  {r['id']}  → {r.get('symbol') or r['file']}")
    evs = [n for n in L.cj.get("events", {}) if q & words(re.sub(r"([a-z])([A-Z])", r"\1 \2", n))]
    if evs:
        print("\nСобытия:\n  " + "\n  ".join(evs[:a.limit]))
    en = [e for e in L.cj.get("data", {}).get("entities", []) if q & words(re.sub(r"([a-z])([A-Z])", r"\1 \2", e["name"]))]
    if en:
        print("\nСущности:\n  " + "\n  ".join(e["name"] for e in en[:a.limit]))
    print("\nДальше: change.py new <repo> <id> --title \"…\", затем analyze с выбранными --cap/--entry/--event/--entity")
    return 0


# ---------------------------------------------------------------- new

def cmd_new(a):
    L = Layer(a.repo)
    need_layer(L)
    if not sa.ID_RX.match(a.id):
        sa.die("id изменения — kebab-case латиницей: cancel-paid-order")
    d = L.P.openspec / "changes" / a.id
    if d.exists() and not a.force:
        sa.die(f"{L.P.rel(d)} уже есть — продолжай в нём или --force (перезапишет заготовки)")
    d.mkdir(parents=True, exist_ok=True)
    for name in ("proposal.md", "design.md", "tasks.md"):
        t = (ASSETS / name).read_text(encoding="utf-8").replace("{{ID}}", a.id).replace("{{TITLE}}", a.title)
        if a.force or not (d / name).exists():
            (d / name).write_text(t, encoding="utf-8")
    (d / "specs").mkdir(exist_ok=True)
    ok(f"{L.P.rel(d)}/: proposal.md, design.md, tasks.md, specs/")
    print(f"Дальше: change.py analyze {a.repo} {a.id} --cap <возможности> [--entry …] [--entity …] — влияние до того, как писать proposal")
    return 0


# ---------------------------------------------------------------- analyze

def cap_files(L, cap):
    files = set()
    for r in L.trace.get(cap, {}).values():
        files |= {sa.strip_loc(x) for x in r["code"]}
    entries = set(L.caps().get(cap, {}).get("entries", []))
    for r in L.cj.get("entries", []):
        if r["id"] in entries:
            files.add(r["file"])
            if r.get("handler"):
                files.add(r["handler"].split(":")[0])
    return files


def cap_ranges(L, caps, entries):
    """Файл → диапазоны строк кода затронутых возможностей (трассировка и тела обработчиков); None — файл целиком."""
    rg = defaultdict(list)
    for c in caps:
        for r in L.trace.get(c, {}).values():
            for x in r["code"]:
                m = re.match(r"^(.+?):(\d+)(?:-(\d+))?$", x)
                if m:
                    rg[m.group(1)].append((int(m.group(2)) - 1, int(m.group(3) or m.group(2)) + 1))
                else:
                    rg[x].append(None)
    for r in L.cj.get("entries", []):
        if r["id"] in entries:
            m = re.match(r"^(.+?):(\d+)$", r.get("handler") or "")
            if m:
                rg[m.group(1)].append((int(m.group(2)), max(int(m.group(2)), r.get("end") or int(m.group(2)))))
    return rg


def in_ranges(rg, loc):
    m = re.match(r"^([^:\s]+):(\d+)", loc)
    return bool(m) and any(x is None or x[0] <= int(m.group(2)) <= x[1] for x in rg.get(m.group(1), []))


def cap_tests(L, cap):
    out = []
    for name, r in L.trace.get(cap, {}).items():
        for t in r["tests"]:
            if t not in out and t not in ("—", "-"):
                out.append(t)
    return out


def build_items(L, caps, entries, events, entities, extra_files):
    """Пункты влияния: у каждого ключ (для сохранения решений при повторном анализе), вид, текст, подробности."""
    items, info = [], OrderedDict()
    cj = L.cj
    target_entries = set(entries)
    for c in caps:
        target_entries |= set(L.caps().get(c, {}).get("entries", []))
    files = set(extra_files)
    for c in caps:
        files |= cap_files(L, c)
    # вызывающие
    for g in cj.get("callers", []):
        if not (set(g.get("entries", [])) & target_entries or set(g.get("caps", [])) & set(caps)):
            continue
        if "только тесты" in g.get("kind", ""):
            continue
        head = f"{g['consumer']} → {g['what']}"
        det = []
        rel = L.notes.get(head)
        det.append("опирается на: " + (re.sub(r"^- \*\*Опирается на:\*\*\s*", "", rel)[:700] if rel else "не описано в contracts.md — открой его файлы"))
        det.append("где: " + ", ".join(list(g.get("files", {}))[:4]))
        items.append(("C", f"caller:{head}", f"`{head}`" + (" — клиентское приложение" if g.get("client") else ""), det))
    # события: публикуемые кодом затронутых возможностей (по строкам, а не по файлу) и названные явно
    rg = cap_ranges(L, caps, target_entries)
    for name, x in cj.get("events", {}).items():
        pub = any(in_ranges(rg, l) for l in x.get("publishers", []))
        if not (name in events or pub):
            continue
        det = []
        if x.get("defs"):
            det.append("поля: " + ", ".join(f"{f[0]} {f[1]}" for f in x["defs"][0].get("fields", [])[:10]))
        if x.get("copies_differ"):
            det.append("⚠ копии события в сервисах различаются по полям")
        elif len(x.get("defs", [])) > 1:
            det.append(f"копий определения: {len(x['defs'])} — новое поле добавлять во все")
        subs = x.get("subscribers", [])
        det.append("подписаны: " + ("; ".join(subs[:5]) if subs else "в репозитории никто — внешние подписчики?"))
        n = L.notes.get(f"`{name}`")
        if n:
            det.append("заметки: " + n[:400])
        items.append(("S", f"event:{name}", f"`{name}`" + (" (внутреннее)" if x.get("internal") else ""), det))
    # сущности и их поля
    ents = {e["name"]: e for e in cj.get("data", {}).get("entities", [])}
    for en in entities:
        e = ents.get(en)
        if not e:
            warn(f"сущности {en} нет в contracts.json (data) — имя как в data.md; пропускаю")
            continue
        for loc in (e.get("creates_sym") or e.get("creates") or []):
            items.append(("E", f"create:{en}:{loc}", f"`{en}` создаётся: {loc}", ["новое поле здесь не заполнится само"]))
        for cp in e.get("copies", []):
            items.append(("E", f"copy:{en}:{cp['name']}:{cp['file']}",
                          f"`{en}` → копия `{cp['name']}` ({cp['file']}:{cp['line']})",
                          [f"общих полей {cp['common']} из {cp['of']}" + (f", нет: {', '.join(cp['missing'][:6])}" if cp.get("missing") else "")]))
        for s in sorted(set(e.get("seeds", []))):
            items.append(("E", f"seed:{en}:{s}", f"`{en}` засев: {s}", ["засев только в пустую таблицу — существующим данным нужна миграция данных"
                                                                         if "пустую" in s else "новое поле — в данные засева"]))
        for ai in e.get("ai", []):
            items.append(("E", f"ai:{en}:{ai}", f"`{en}` уходит в модель ИИ: {ai}", ["новое поле может попасть в промпт или эмбеддинг само"]))
        for m in cj.get("data", {}).get("migrations", []):
            mdir = m.split(":")[0].strip()
            if e.get("file", "").startswith(mdir + "/") or e.get("file", "").split("/")[:2] == mdir.split("/")[:2]:
                items.append(("E", f"migr:{en}", f"`{en}` миграция схемы: {m[:160]}", ["новая миграция, снимок схемы сверить с моделью"]))
                break
    # вопросы
    for q in L.qs:
        st = sa.effective_status(q)
        if st not in ("открыт", "отвечен"):
            continue
        if not any(c in caps for c, _ in sa.affects(q)):
            continue
        imp = q["fields"].get("Важность", "уточняет")
        det = [f"допущение: {q['fields'].get('Допущение', '')[:200]}", f"статус: {st}" + (f", ответ: {q['fields'].get('Ответ', '')[:160]}" if st == "отвечен" else "")]
        if imp == "блокирует":
            items.append(("Q", f"q:{q['id']}", f"[блокирует] {q['title']}", det))
        else:
            info.setdefault("Уточняющие вопросы по затронутым возможностям", []).append(f"{q['id']} {q['title']}")
    # тест-кейсы qa-scan
    if L.cases is not None:
        for c in L.cases:
            if set(c.get("capabilities", [])) & set(caps):
                items.append(("T", f"tc:{c['id']}", f"{c['id']} {c.get('title', '')}",
                              [f"файл: test-cases/{c['path']}", f"приоритет: {c.get('priority', '—')}, статус: {c.get('status', '—')}"]))
    # интерфейс
    if L.design:
        ui = [e for e in target_entries if e.startswith("ui:")]
        clients = [it for it in items if it[0] == "C" and "клиентское" in it[2]]
        if ui or clients or any(re.search(r"\.(razor|tsx|jsx|vue|svelte|html|cshtml)$", f) for f in files):
            items.append(("D", "design:check", "Интерфейсная правка: проверка `check.mjs` скилла wd-fit по design-context/",
                          ["страницы: " + (", ".join(ui[:5]) or "по задачам интерфейса")]))
    # сведения без решений
    for c in caps:
        tests = cap_tests(L, c)
        if tests:
            info.setdefault("Тесты затронутых возможностей (запустить и обновить)", []).append(f"{c}: " + ", ".join(tests[:8]))
    near = sorted({n for n, e in ents.items() if n not in entities and (e.get("def") or {}).get("file", e.get("file")) in files})
    if near:
        info.setdefault("Сущности в коде затронутых возможностей (если меняешь их поля — добавь --entity)", []).append(", ".join(near))
    return items, info, sorted(files)


IMPACT_HEAD = """# Влияние изменения `{id}`

Собрано `change.py analyze` из слоя sa-scan{extra}. Затронуто: возможности {caps}{more}.
У каждого пункта — **Решение**: `задача N.N` (номер из tasks.md, можно несколько) или `не затрагивается: <почему>`.
Для вопросов [блокирует]: изменение на него не опирается — `не затрагивается: <почему>`; опирается — `ответ: …` (человек ответил)
или `в proposal: <что принято до ответа>` (тогда вопрос — в «Открытые вопросы» proposal и в чат).
Повторный `analyze` обновит пункты и сохранит решения. Пункты, которых нет в слое, добавь сам в конце с буквой X (X-01…).
"""
KIND_TITLE = OrderedDict([("C", "Кто вызывает затронутые входы"), ("S", "События: публикуемые и названные"),
                          ("E", "Сущности: где поле потеряется молча"), ("Q", "Блокирующие вопросы затронутых возможностей — опирается ли на них изменение?"),
                          ("T", "Тест-кейсы (qa-scan)"), ("D", "Проверка интерфейса"), ("X", "Добавлено вручную")])


def read_impact(path):
    """Существующий impact.md → {ключ: (id, решение)} и ручные пункты X."""
    keep, manual = {}, []
    if not path.is_file():
        return keep, manual
    cur_id, cur_key = None, None
    lines = path.read_text(encoding="utf-8").splitlines()
    for i, ln in enumerate(lines):
        m = ITEM_RX.match(ln)
        if m:
            cur_id = m.group(1)
            km = re.search(r"<!-- key: (.*?) -->", ln)
            cur_key = km.group(1) if km else None
            if cur_id.startswith("X-"):
                blk = [ln]
                for nx in lines[i + 1:]:
                    if nx.startswith("  "):
                        blk.append(nx)
                    else:
                        break
                manual.append(blk)
            continue
        d = DECISION_RX.match(ln)
        if d and cur_key:
            keep[cur_key] = (cur_id, d.group(1).strip())
    return keep, manual


def cmd_analyze(a):
    L = Layer(a.repo)
    need_layer(L)
    d = L.P.openspec / "changes" / a.id
    if not d.is_dir():
        sa.die(f"нет {L.P.rel(d)} — сначала change.py new {a.repo} {a.id} --title \"…\"")
    caps = [x.strip() for x in ",".join(a.cap or []).split(",") if x.strip()]
    unknown = [c for c in caps if c not in L.caps()]
    if unknown:
        sa.die(f"нет возможностей {', '.join(unknown)}; есть: {', '.join(L.caps())}")
    if not caps and not (a.entry or a.event or a.entity):
        sa.die("укажи хотя бы --cap (возможности, которые меняются) — найти их поможет change.py find")
    items, info, files = build_items(L, caps, a.entry or [], a.event or [], a.entity or [], a.file or [])
    keep, manual = read_impact(d / "impact.md")
    used = defaultdict(int)
    for k, (iid, _) in keep.items():
        p, n = iid.split("-")
        if p != "Q":
            used[p] = max(used[p], int(n))
    out = [IMPACT_HEAD.format(id=a.id, caps=", ".join(f"`{c}`" for c in caps) or "—",
                              more=(f"; входы {', '.join(a.entry)}" if a.entry else "") + (f"; события {', '.join(a.event)}" if a.event else "")
                              + (f"; сущности {', '.join(a.entity)}" if a.entity else ""),
                              extra=(", test-cases/" if L.cases is not None else "") + (", design-context/" if L.design else ""))]
    js_items = []
    for kind, title in KIND_TITLE.items():
        if kind == "X":
            continue
        group = [it for it in items if it[0] == kind]
        if not group:
            continue
        out += ["", f"## {title}", ""]
        for _, key, text, det in group:
            if key in keep:
                iid, dec = keep[key]
            elif kind == "Q":
                iid, dec = key[2:], ""      # пункт-вопрос — под номером самого вопроса
            else:
                used[kind] += 1
                iid, dec = f"{kind}-{used[kind]:02d}", ""
            done = "x" if dec and PLACEHOLDER not in dec else " "
            out.append(f"- [{done}] {iid} {text} <!-- key: {key} -->")
            out += [f"  - {x}" for x in det]
            out.append(f"  - **Решение:** {dec or PLACEHOLDER + ': задача N.N или не затрагивается: почему -->'}")
            js_items.append({"id": iid, "key": key, "kind": kind})
    if manual:
        out += ["", f"## {KIND_TITLE['X']}", ""]
        for blk in manual:
            out += blk
    for title, lines in info.items():
        out += ["", f"## {title}", ""] + [f"- {x}" for x in lines]
    out += ["", "## Код затронутых возможностей", "", "Файлы из трассировки и обработчиков — по ним волны и пересечения с другими изменениями.", ""]
    out += [f"- {f}" for f in files[:60]] + ([f"- … ещё {len(files) - 60}"] if len(files) > 60 else [])
    (d / "impact.md").write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")
    (d / "impact.json").write_text(json.dumps({"id": a.id, "caps": caps, "entries": a.entry or [], "events": a.event or [],
                                               "entities": a.entity or [], "files": files, "items": js_items},
                                              ensure_ascii=False, indent=1), encoding="utf-8")
    cnt = defaultdict(int)
    for it in js_items:
        cnt[it["kind"]] += 1
    todo = sum(1 for it in js_items if not keep.get(it["key"], (0, ""))[1] or PLACEHOLDER in keep.get(it["key"], (0, ""))[1])
    ok(f"{L.P.rel(d / 'impact.md')}: " + (", ".join(f"{KIND_TITLE[k].split(':')[0].lower()} {v}" for k, v in cnt.items()) or "пунктов влияния нет — проверь, те ли --cap и нужен ли --entity")
       + f"; без решения {todo}")
    others = overlap(L, a.id, set(files))
    for oid, common in others:
        warn(f"пересекается с изменением {oid} по {len(common)} файлам ({', '.join(sorted(common)[:3])}) — одной волной не раздавать (change.py waves)")
    print("Дальше: proposal.md (раздел «Влияние» — по пунктам impact.md), дельты specs/<cap>/spec.md (MODIFIED — change.py req),"
          " design.md, tasks.md; затем Решение у каждого пункта и change.py check")
    return 0


# ---------------------------------------------------------------- req

def cmd_req(a):
    L = Layer(a.repo)
    p = L.P.spec(a.cap)
    if not p.is_file():
        sa.die(f"нет {L.P.rel(p)}")
    lines = p.read_text(encoding="utf-8").splitlines()
    starts = [i for i, ln in enumerate(lines) if ln.startswith("### Requirement:")]
    if not a.name:
        print("\n".join(lines[i].split(":", 1)[1].strip() for i in starts))
        return 0
    for k, i in enumerate(starts):
        if lines[i].split(":", 1)[1].strip() == a.name.strip():
            end = starts[k + 1] if k + 1 < len(starts) else next((j for j in range(i + 1, len(lines)) if lines[j].startswith("## ")), len(lines))
            print("\n".join(lines[i:end]).rstrip())
            return 0
    sa.die(f"в {L.P.rel(p)} нет требования «{a.name}» — имена: change.py req {a.repo} {a.cap}")


# ---------------------------------------------------------------- check

def overlap(L, me, files):
    out = []
    for d in sorted((L.P.openspec / "changes").glob("*/impact.json")):
        if d.parent.name in (me, "archive"):
            continue
        other = set(json.loads(d.read_text(encoding="utf-8")).get("files", []))
        common = files & other
        if common:
            out.append((d.parent.name, common))
    return out


def tasks_of(text):
    return OrderedDict((m.group(1), m.group(2)) for m in (TASK_RX.match(ln) for ln in text.splitlines()) if m)


def cmd_check(a):
    L = Layer(a.repo)
    need_layer(L)
    d = L.P.openspec / "changes" / a.id
    if not d.is_dir():
        sa.die(f"нет {L.P.rel(d)}")
    err, wrn = [], []
    rel = L.P.rel
    for name in ("proposal.md", "design.md", "tasks.md", "impact.md"):
        f = d / name
        if not f.is_file():
            err.append(f"нет {rel(f)}" + (" — change.py analyze" if name == "impact.md" else ""))
        elif PLACEHOLDER in f.read_text(encoding="utf-8"):
            n = f.read_text(encoding="utf-8").count(PLACEHOLDER)
            err.append(f"{rel(f)}: незаполненных мест «{PLACEHOLDER}»: {n}")
    tasks = tasks_of((d / "tasks.md").read_text(encoding="utf-8")) if (d / "tasks.md").is_file() else OrderedDict()
    if (d / "tasks.md").is_file() and not tasks:
        err.append(f"{rel(d / 'tasks.md')}: нет задач вида `- [ ] 1.1 …`")
    # дельты
    deltas = sorted((d / "specs").glob("*/spec.md"))
    if not deltas:
        err.append(f"нет дельт {rel(d / 'specs')}/<cap>/spec.md — изменение без поведения не планируют через OpenSpec")
    delta_reqs = []
    for f in deltas:
        cap = f.parent.name
        if cap not in L.caps():
            wrn.append(f"{rel(f)}: возможности «{cap}» нет в плане — новая возможность? тогда это ADDED целиком, имя — kebab-case по поведению")
        text = f.read_text(encoding="utf-8")
        main = L.spec(cap)
        for e in sa.delta_problems(text, main):
            err.append(f"{rel(f)}: {e}")
        for m in re.finditer(r"^##\s+(ADDED|MODIFIED|REMOVED|RENAMED)\s+Requirements\s*$([\s\S]*?)(?=^##\s|\Z)", text, re.M):
            for r in re.findall(r"^###\s+Requirement:\s*(.+)$", m.group(2), re.M):
                delta_reqs.append((m.group(1), cap, r.strip()))
    # задачи покрывают требования дельт
    alltasks = " ".join(tasks.values())
    for op, cap, name in delta_reqs:
        if op in ("ADDED", "MODIFIED") and name not in alltasks:
            err.append(f"требование «{name}» ({cap}, {op}) не названо ни в одной задаче — dev-агент не узнает, что его реализовать и проверить")
    # задачи — исполнимы
    vague = [n for n, t in tasks.items() if not REF_RX.search(t)]
    if vague:
        wrn.append(f"задачи без файла или символа ({len(vague)}): {', '.join(vague[:8])} — dev-агенту нужна точка входа: путь или `Класс.Метод`")
    if tasks and not re.search(r"trace\.md", (d / "tasks.md").read_text(encoding="utf-8")):
        err.append(f"{rel(d / 'tasks.md')}: нет задачи обновить system-context/trace.md (и слой) после реализации")
    # влияние: у каждого пункта решение, ссылки на задачи существуют
    imp = d / "impact.md"
    if imp.is_file():
        cur = None
        for ln in imp.read_text(encoding="utf-8").splitlines():
            m = ITEM_RX.match(ln)
            if m:
                cur = m.group(1)
                continue
            dm = DECISION_RX.match(ln)
            if not (dm and cur):
                continue
            dec = dm.group(1).strip()
            if not dec or PLACEHOLDER in dec:
                continue   # о заглушке уже сказано
            refs = re.findall(r"\b(\d+\.\d+)\b", dec)
            low = dec.lower()
            if refs:
                missing = [r for r in refs if r not in tasks]
                if missing:
                    err.append(f"{rel(imp)} {cur}: задачи {', '.join(missing)} нет в tasks.md")
            elif low.startswith("не затрагивается"):
                if len(dec) < 30:
                    err.append(f"{rel(imp)} {cur}: «не затрагивается» без причины — почему именно (одной фразой)")
            elif cur.startswith("Q-") and (low.startswith("ответ") or low.startswith("в proposal")):
                pass
            else:
                err.append(f"{rel(imp)} {cur}: решение — «задача N.N», «не затрагивается: почему»" + (", «ответ: …» или «в proposal: …»" if cur.startswith("Q-") else ""))
    # proposal: разделы влияния и вопросов
    pp = d / "proposal.md"
    if pp.is_file():
        pt = pp.read_text(encoding="utf-8")
        for sec in ("Влияние", "Открытые вопросы"):
            if not re.search(rf"^##\s+{sec}", pt, re.M):
                err.append(f"{rel(pp)}: нет раздела «## {sec}»")
        blocking = [x["key"][2:] for x in json.loads((d / "impact.json").read_text(encoding="utf-8"))["items"]
                    if x["kind"] == "Q"] if (d / "impact.json").is_file() else []
        sec = re.search(r"^##\s+Открытые вопросы\s*$([\s\S]*?)(?=^##\s|\Z)", pt, re.M)
        decisions = {}
        if imp.is_file():
            cur = None
            for ln in imp.read_text(encoding="utf-8").splitlines():
                m = ITEM_RX.match(ln)
                if m:
                    cur = m.group(1)
                dm = DECISION_RX.match(ln)
                if dm and cur:
                    decisions[cur] = dm.group(1).strip().lower()
        for qid in blocking:
            q = next((x for x in L.qs if x["id"] == qid), None)
            if decisions.get(qid, "").startswith("не затрагивается"):
                continue   # изменение на этот вопрос не опирается — в proposal ему не место
            if q and sa.effective_status(q) == "открыт" and (not sec or qid not in sec.group(1)):
                err.append(f"{rel(pp)}: блокирующий вопрос {qid} не назван в «Открытые вопросы» — dev-агент опрётся на допущение молча")
    # пересечения с другими изменениями
    if (d / "impact.json").is_file():
        files = set(json.loads((d / "impact.json").read_text(encoding="utf-8")).get("files", []))
        for oid, common in overlap(L, a.id, files):
            wrn.append(f"пересекается с {oid} по {len(common)} файлам — change.py waves: в одну волну не раздавать")
    # CLI
    if shutil.which("openspec") and not a.no_cli:
        r = subprocess.run(["openspec", "validate", a.id, "--strict", "--no-interactive"], cwd=L.P.repo, capture_output=True, text=True)
        if r.returncode != 0:
            msg = [ln.strip() for ln in (r.stdout + r.stderr).splitlines()
                   if re.search(r"✗|error|ERROR|must|should|missing|Missing", ln) and "Debug" not in ln][:3]
            err.append("openspec validate: " + ("; ".join(msg) or "ошибки — запусти openspec validate " + a.id)[:400])
    for m in err:
        print(f"✗ {m}")
    for m in wrn:
        print(f"! {m}")
    print(f"\n{'✓ пакет готов для dev-агентов' if not err else '✗ ошибок: ' + str(len(err))}, предупреждений: {len(wrn)}, задач: {len(tasks)}, требований в дельтах: {len(delta_reqs)}")
    return 1 if err else 0


# ---------------------------------------------------------------- waves

def cmd_waves(a):
    L = Layer(a.repo)
    need_layer(L)
    ch = OrderedDict()
    for f in sorted((L.P.openspec / "changes").glob("*/impact.json")):
        if f.parent.name != "archive":
            ch[f.parent.name] = set(json.loads(f.read_text(encoding="utf-8")).get("files", []))
    if not ch:
        sa.die("нет активных изменений с impact.json — сначала change.py analyze")
    ids = list(ch)
    conf = {i: {j for j in ids if j != i and ch[i] & ch[j]} for i in ids}
    waves = []
    for i in sorted(ids, key=lambda x: -len(conf[x])):
        for w in waves:
            if not (conf[i] & set(w)):
                w.append(i)
                break
        else:
            waves.append([i])
    lines = ["# Волны изменений", "", "Собрано `change.py waves`: изменения одной волны не делят файлов — их можно отдать dev-агентам одновременно.",
             "Следующая волна — после слияния предыдущей (общие файлы правятся по очереди).", ""]
    for k, w in enumerate(waves, 1):
        lines.append(f"## Волна {k}")
        lines += [f"- `{i}` — файлов {len(ch[i])}" + (f"; конфликтует с: {', '.join(sorted(conf[i]))}" if conf[i] else "") for i in w]
        lines.append("")
    hot = defaultdict(list)
    for i, fs in ch.items():
        for f in fs:
            hot[f].append(i)
    shared = sorted(((f, v) for f, v in hot.items() if len(v) > 1), key=lambda x: -len(x[1]))
    if shared:
        lines += ["## Общие файлы", ""] + [f"- {f}: {', '.join(v)}" for f, v in shared[:20]]
    out = L.P.ctx / "WAVES.md"
    out.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    ok(f"{L.P.rel(out)}: изменений {len(ids)}, волн {len(waves)}")
    for k, w in enumerate(waves, 1):
        print(f"  волна {k}: {', '.join(w)}")
    return 0


def main():
    ap = argparse.ArgumentParser(description="Планирование изменения по слою sa-scan")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("layer", help="слой на месте и свежий? что ещё есть в репозитории")
    p.add_argument("repo")
    p.set_defaults(fn=cmd_layer)
    p = sub.add_parser("find", help="затронутые возможности, входы, события, сущности по словам задачи")
    p.add_argument("repo")
    p.add_argument("--text", required=True)
    p.add_argument("--limit", type=int, default=8)
    p.set_defaults(fn=cmd_find)
    p = sub.add_parser("new", help="заготовка изменения openspec/changes/<id>/")
    p.add_argument("repo")
    p.add_argument("id")
    p.add_argument("--title", required=True)
    p.add_argument("--force", action="store_true")
    p.set_defaults(fn=cmd_new)
    p = sub.add_parser("analyze", help="impact.md: кого заденет изменение")
    p.add_argument("repo")
    p.add_argument("id")
    p.add_argument("--cap", action="append", help="возможности, которые меняются (через запятую или несколько раз)")
    p.add_argument("--entry", action="append", help="id входа из описи, например \"http:PUT /api/orders/cancel\"")
    p.add_argument("--event", action="append", help="имя события, которое меняется")
    p.add_argument("--entity", action="append", help="сущность, у которой меняются поля (имя как в data.md)")
    p.add_argument("--file", action="append", help="файл кода, который точно меняется")
    p.set_defaults(fn=cmd_analyze)
    p = sub.add_parser("req", help="требование целиком (для MODIFIED); без имени — список имён")
    p.add_argument("repo")
    p.add_argument("cap")
    p.add_argument("name", nargs="?")
    p.set_defaults(fn=cmd_req)
    p = sub.add_parser("check", help="пакет изменения готов для dev-агентов?")
    p.add_argument("repo")
    p.add_argument("id")
    p.add_argument("--no-cli", action="store_true", help="не запускать openspec validate")
    p.set_defaults(fn=cmd_check)
    p = sub.add_parser("waves", help="активные изменения → волны без общих файлов (system-context/WAVES.md)")
    p.add_argument("repo")
    p.set_defaults(fn=cmd_waves)
    a = ap.parse_args()
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
