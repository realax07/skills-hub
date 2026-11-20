"""Общее для скриптов sa-scan: пути слоя, план, разбор спек OpenSpec, вопросов и трассировки.

Python 3.9+, только стандартная библиотека.
"""
import json
import re
import sys
from collections import OrderedDict
from pathlib import Path

CTX = "system-context"
SPEC_ROOT = "openspec"
SKILL_DIR = Path(__file__).resolve().parent.parent.parent
ASSETS = SKILL_DIR / "assets"

STATUSES = ("открыт", "отвечен", "внесён", "снят")
IMPORTANCE = ("блокирует", "уточняет")
CATEGORIES = (
    "внешний сервис", "потребители API", "конфигурация и окружение", "данные в проде",
    "расхождение кода и документа", "баг или так задумано", "мёртвый код", "ручные процессы",
    "права и роли", "нефункциональное", "правовое и регуляторное", "другое",
)
Q_FIELDS = ("Статус", "Важность", "Категория", "Что видно", "Затрагивает", "Допущение", "Кто ответит", "Ответ")
INDEX_START = "<!-- sa-scan:index:start -->"
INDEX_END = "<!-- sa-scan:index:end -->"
Q_RX = re.compile(r"\bQ-\d{3,}\b")
TMP_RX = re.compile(r"\bTMP-\d+\b")   # временные номера вопросов у работника (режим раздачи)
ID_RX = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def die(msg, code=2):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(code)


class Paths:
    def __init__(self, repo):
        self.repo = Path(repo).resolve()
        if not self.repo.is_dir():
            die(f"нет папки {self.repo}")
        self.ctx = self.repo / CTX
        self.inventory = self.ctx / "inventory.json"
        self.plan = self.ctx / "plan.json"
        self.questions = self.ctx / "QUESTIONS.md"
        self.trace = self.ctx / "trace.md"
        self.guide = self.ctx / "GUIDE.md"
        self.openspec = self.repo / SPEC_ROOT
        self.specs = self.openspec / "specs"
        self.config = self.openspec / "config.yaml"
        self.work = self.ctx / ".work"

    def workdir(self, cap):
        return self.work / cap

    def spec(self, cap):
        return self.specs / cap / "spec.md"

    def rel(self, p):
        try:
            return Path(p).resolve().relative_to(self.repo).as_posix()
        except ValueError:
            return str(p)


def kebab(s):
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    return re.sub(r"-{2,}", "-", s) or "misc"


def load_json(p, what):
    if not p.is_file():
        die(f"нет {p} — {what}")
    return json.loads(p.read_text(encoding="utf-8"), object_pairs_hook=OrderedDict)


def save_json(p, data):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def load_plan(P):
    return load_json(P.plan, f"сначала plan.py init {P.repo}")


def load_inventory(P):
    return load_json(P.inventory, f"сначала inventory.py scan {P.repo}")


def all_entries(inv, plan):
    """Все входы: из описи и добавленные вручную. id -> запись."""
    out = OrderedDict((e["id"], e) for e in inv.get("entries", []))
    for e in plan.get("manual_entries", []):
        out[e["id"]] = e
    return out


def assignment(plan):
    """id входа -> ('cap', id) | ('excluded', причина)."""
    out = {}
    for c in plan["capabilities"]:
        for e in c["entries"]:
            out[e] = ("cap", c["id"])
    for x in plan.get("excluded", []):
        out[x["entry"]] = ("excluded", x["reason"])
    return out


# ---------- спеки OpenSpec

SCEN_STEP = re.compile(r"^\s*[-*]\s*\*{0,2}(GIVEN|WHEN|THEN|AND|BUT)\*{0,2}\b", re.M)


def parse_spec(text):
    """Разбор основного spec.md: заголовок, Purpose, требования со сценариями, ошибки структуры."""
    lines = text.splitlines()
    res = {"title": None, "purpose": "", "requirements": [], "sections": [], "problems": []}
    cur_sec = None
    req = None
    scen = None
    purpose = []
    for i, ln in enumerate(lines, 1):
        if res["title"] is None and ln.startswith("# "):
            res["title"] = ln[2:].strip()
            continue
        m = re.match(r"^##\s+(.+?)\s*$", ln)
        if m and not ln.startswith("###"):
            cur_sec = m.group(1)
            res["sections"].append((cur_sec, i))
            req = scen = None
            continue
        m = re.match(r"^###\s+Requirement:\s*(.*)$", ln)
        if m:
            req = {"name": m.group(1).strip(), "line": i, "body": [], "scenarios": [], "section": cur_sec}
            res["requirements"].append(req)
            scen = None
            continue
        m = re.match(r"^####\s+Scenario:\s*(.*)$", ln)
        if m:
            if req is None:
                res["problems"].append((i, "сценарий вне требования"))
                continue
            scen = {"name": m.group(1).strip(), "line": i, "steps": []}
            req["scenarios"].append(scen)
            continue
        if re.match(r"^#{2,6}\s*Scenario:|^\s*[-*]\s*\**Scenario:|^#{5,6}\s", ln):
            res["problems"].append((i, "сценарий оформляется ровно `#### Scenario: <имя>` (4 решётки)"))
            continue
        if re.match(r"^#{2,4}\s*Requirement\b", ln) and not ln.startswith("### Requirement:"):
            res["problems"].append((i, "требование оформляется ровно `### Requirement: <имя>`"))
            continue
        if scen is not None:
            sm = SCEN_STEP.match(ln)
            if sm:
                scen["steps"].append(sm.group(1))
            continue
        if req is not None:
            req["body"].append(ln)
            continue
        if cur_sec == "Purpose":
            purpose.append(ln)
    res["purpose"] = "\n".join(purpose).strip()
    for r in res["requirements"]:
        r["text"] = "\n".join(r["body"]).strip()
    return res


def spec_problems(text):
    """Ошибки и предупреждения формата основного spec.md. Возвращает (errors, warnings, parsed)."""
    s = parse_spec(text)
    err, warn = [], []
    secs = [n for n, _ in s["sections"]]
    if not s["title"]:
        err.append("нет заголовка `# <Название>` первой строкой")
    for n, ln in s["sections"]:
        if re.match(r"^(ADDED|MODIFIED|REMOVED|RENAMED)\s+Requirements$", n):
            err.append(f"стр. {ln}: `## {n}` — это раздел дельты изменения (changes/), а не основной спеки")
    if "Purpose" not in secs:
        err.append("нет раздела `## Purpose`")
    elif not s["purpose"]:
        err.append("раздел `## Purpose` пустой")
    if "Requirements" not in secs:
        err.append("нет раздела `## Requirements`")
    if not s["requirements"]:
        err.append("нет ни одного `### Requirement: <имя>`")
    seen = set()
    for ln, msg in s["problems"]:
        err.append(f"стр. {ln}: {msg}")
    for r in s["requirements"]:
        tag = f"стр. {r['line']} «{r['name'] or '?'}»"
        if not r["name"]:
            err.append(f"{tag}: у требования нет имени")
        if r["name"].lower() in seen:
            err.append(f"{tag}: имя требования повторяется")
        seen.add(r["name"].lower())
        if r["section"] != "Requirements":
            err.append(f"{tag}: требование вне раздела `## Requirements`")
        if not re.search(r"\b(SHALL|MUST)\b", r["text"]):
            err.append(f"{tag}: в тексте требования нет SHALL или MUST (ключевое слово — по-английски, заглавными)")
        if len(r["text"]) > 500:
            err.append(f"{tag}: текст требования {len(r['text'])} символов, больше 500 — раздели на два требования")
        if not r["scenarios"]:
            err.append(f"{tag}: нет ни одного `#### Scenario:`")
        for sc in r["scenarios"]:
            st = set(sc["steps"])
            if not ({"WHEN", "GIVEN"} & st) or "THEN" not in st:
                err.append(f"стр. {sc['line']} сценарий «{sc['name']}»: нужны шаги `- **WHEN** …` (или GIVEN) и `- **THEN** …`")
        if re.search(r"(?:^|[\s`(])(?:src|lib|app|internal|pkg)/[\w./-]+|\b\w+\.(?:ts|tsx|js|py|go|java|kt|rb|php|cs)\b", r["text"]):
            warn.append(f"{tag}: похоже на путь к файлу в требовании — ссылки на код держи в system-context/trace.md")
    return err, warn, s


# ---------- вопросы

def parse_questions(text):
    """QUESTIONS.md → список вопросов {id, title, line, fields}. Поля — `- **Имя:** значение`, продолжение — с отступом."""
    qs = []
    cur = None
    last = None
    fence = False
    for i, ln in enumerate(text.splitlines(), 1):
        if ln.lstrip().startswith("```"):
            fence = not fence
            cur = None
            continue
        if fence:
            continue
        m = re.match(r"^###\s+(Q-\d{3,}|TMP-\d+)\.?\s*(.*)$", ln)
        if m:
            cur = {"id": m.group(1), "title": m.group(2).strip(), "line": i, "fields": OrderedDict()}
            qs.append(cur)
            last = None
            continue
        if re.match(r"^#{1,3}\s", ln):
            cur = None
            continue
        if cur is None:
            continue
        m = re.match(r"^\s*[-*]\s*\*\*([^*:]+):\*\*\s?(.*)$", ln)
        if m:
            last = m.group(1).strip()
            cur["fields"][last] = m.group(2).strip()
            continue
        if last and ln.strip() and (ln.startswith(("  ", "\t", ">")) or not ln.lstrip().startswith("-")):
            cur["fields"][last] = (cur["fields"][last] + "\n" + ln.strip()).strip()
    return qs


def effective_status(q):
    st = q["fields"].get("Статус", "").strip().lower()
    if st == "открыт" and q["fields"].get("Ответ", "").strip():
        return "отвечен"
    return st


def affects(q):
    """«Затрагивает: cap / Требование; cap2» → [(cap, требование|None)]."""
    raw = q["fields"].get("Затрагивает", "").strip()
    out = []
    if not raw or raw in ("—", "-", "нет"):
        return out
    for part in re.split(r"[;\n]", raw):
        part = part.strip().strip("`")
        if not part:
            continue
        if "/" in part:
            cap, req = part.split("/", 1)
            req = req.strip().strip("`")
            out.append((cap.strip().strip("`"), None if req in ("", "—", "-", "нет") else req))
        else:
            out.append((part, None))
    return out


def question_block(qid, title, fields):
    """Блок вопроса в формате QUESTIONS.md."""
    lines = [f"### {qid}. {title.strip()}"]
    for k in Q_FIELDS:
        v = (fields.get(k) or "").strip()
        if k == "Статус" and not v:
            v = "открыт"
        vl = v.split("\n")
        lines.append(f"- **{k}:** {vl[0]}".rstrip())
        lines += [f"  {x}" for x in vl[1:]]
    return "\n".join(lines)


def next_qnum(qs):
    return max([int(q["id"][2:]) for q in qs if q["id"].startswith("Q-")] + [0]) + 1


def similar(a, b):
    """Похожесть заголовков вопросов (доля общих слов длиннее 3 букв)."""
    wa = {w for w in re.findall(r"\w{4,}", a.lower())}
    wb = {w for w in re.findall(r"\w{4,}", b.lower())}
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


def code_refs(text):
    """Ссылки «путь:строка[-строка]» из текста → [(путь, начало, конец)]."""
    out = []
    for m in re.finditer(r"([\w./-]+\.\w{1,5}):(\d+)(?:-(\d+))?", text or ""):
        lo = int(m.group(2))
        out.append((m.group(1).split("/")[-1], lo, int(m.group(3) or lo)))
    return out


def near_duplicate(q1, q2):
    """Похожи ли вопросы: заголовки близки или ссылаются на одно место кода (±3 строки) и хоть немного похожи словами."""
    t = similar(q1["title"], q2["title"])
    if t >= 0.4:
        return True
    r1 = code_refs(q1["fields"].get("Что видно", ""))
    r2 = code_refs(q2["fields"].get("Что видно", ""))
    same_place = any(a[0] == b[0] and a[1] <= b[2] + 3 and b[1] <= a[2] + 3 for a in r1 for b in r2)
    return same_place and t >= 0.2


def index_block(qs):
    lines = [INDEX_START, ""]
    if not qs:
        lines.append("Вопросов пока нет.")
    for q in qs:
        st = effective_status(q)
        box = "x" if st in ("внесён", "снят") else " "
        imp = q["fields"].get("Важность", "")
        caps = ", ".join(sorted({c for c, _ in affects(q)})) or "общее"
        note = {"отвечен": " — **ответ есть, внести в спеку**", "снят": " — снят", "внесён": ""}.get(st, "")
        lines.append(f"- [{box}] **{q['id']}** {q['title']} — {imp} · {caps}{note}")
    open_n = sum(1 for q in qs if effective_status(q) == "открыт")
    ans_n = sum(1 for q in qs if effective_status(q) == "отвечен")
    lines += ["", f"Открыто: {open_n} · ответ есть, не внесён: {ans_n} · всего: {len(qs)}", INDEX_END]
    return "\n".join(lines)


def replace_index(text, qs):
    block = index_block(qs)
    a, b = text.find(INDEX_START), text.find(INDEX_END)
    if a != -1 and b > a:
        return text[:a] + block + text[b + len(INDEX_END):]
    m = re.search(r"^## ", text, re.M)
    if m:
        return text[:m.start()] + block + "\n\n" + text[m.start():]
    return text.rstrip() + "\n\n" + block + "\n"


# ---------- трассировка

def parse_trace(text):
    """trace.md: `## <cap>` и строки `- <Требование> → путь[:строка], путь [| тесты: путь, …]`."""
    out = OrderedDict()
    cap = None
    for i, ln in enumerate(text.splitlines(), 1):
        m = re.match(r"^##\s+`?([a-z0-9][a-z0-9-]*)`?\s*$", ln)
        if m:
            cap = m.group(1)
            out.setdefault(cap, OrderedDict())
            continue
        m = re.match(r"^\s*[-*]\s+(.+?)\s+(?:→|->)\s+(.+)$", ln)
        if m and cap:
            name = m.group(1).strip().strip("*`")
            rest = m.group(2)
            tests = ""
            if "|" in rest:
                rest, tests = rest.split("|", 1)
                tests = re.sub(r"^\s*тесты?\s*:\s*", "", tests.strip(), flags=re.I)
            code = _paths(rest)
            tl = _paths(tests)
            out[cap][name] = {"code": code, "tests": tl, "line": i}
    return out


def _paths(raw):
    """«a.py:9, 18-20, b.py (заглушка)» → ['a.py:9', 'a.py:18-20', 'b.py']: голые номера строк относятся к предыдущему файлу,
    пояснения в скобках (с запятыми и вложенными скобками) отбрасываются."""
    out = []
    parts, depth, cur = [], 0, ""
    for ch in raw:
        depth += ch == "("
        depth -= ch == ")" and depth > 0
        if ch == "," and depth == 0:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    parts.append(cur)
    for x in parts:
        x = x.strip().strip("`")
        i = x.find("(")
        if i > 0:
            x = x[:i]
        x = x.strip().strip("`")
        if not x or x in ("—", "-", "нет") or x.startswith(("— ", "- ", "нет ")):
            continue
        if re.match(r"^\d+(-\d+)?$", x) and out:
            out.append(strip_loc(out[-1]) + ":" + x)
            continue
        out.append(x)
    return out


def strip_loc(path):
    return re.sub(r":\d+(?:-\d+)?$", "", path.strip())


def delta_problems(text, main_specs):
    """Дельта спеки изменения (changes/<id>/specs/<cap>/spec.md). main_specs: cap -> parsed основной спеки или None."""
    err = []
    secs = re.findall(r"^##\s+(ADDED|MODIFIED|REMOVED|RENAMED)\s+Requirements\s*$", text, re.M)
    if not secs:
        err.append("нет ни одного раздела `## ADDED|MODIFIED|REMOVED Requirements`")
    cur = None
    blocks = []
    for i, ln in enumerate(text.splitlines(), 1):
        m = re.match(r"^##\s+(ADDED|MODIFIED|REMOVED|RENAMED)\s+Requirements", ln)
        if m:
            cur = m.group(1)
            continue
        m = re.match(r"^###\s+Requirement:\s*(.*)$", ln)
        if m:
            blocks.append({"op": cur, "name": m.group(1).strip(), "line": i, "body": [], "steps": [], "scen": 0})
            continue
        if blocks:
            b = blocks[-1]
            sm2 = re.match(r"^####\s+Scenario:\s*(.*)$", ln)
            if sm2:
                b["scen"] += 1
                b.setdefault("scen_names", []).append(sm2.group(1).strip())
            sm = SCEN_STEP.match(ln)
            if sm:
                b["steps"].append(sm.group(1))
            elif b["scen"] == 0:
                b["body"].append(ln)
    for b in blocks:
        tag = f"стр. {b['line']} «{b['name']}»"
        body = "\n".join(b["body"])
        if b["op"] in ("ADDED", "MODIFIED"):
            if not re.search(r"\b(SHALL|MUST)\b", body):
                err.append(f"{tag}: нет SHALL или MUST")
            if b["scen"] == 0 or "THEN" not in b["steps"] or not ({"WHEN", "GIVEN"} & set(b["steps"])):
                err.append(f"{tag}: нужен сценарий с WHEN и THEN")
        if b["op"] in ("MODIFIED", "REMOVED") and main_specs is not None:
            names = {r["name"] for r in main_specs["requirements"]}
            if b["name"] not in names:
                err.append(f"{tag}: в основной спеке нет требования с таким именем — имя должно совпадать дословно")
            elif b["op"] == "MODIFIED":
                cur = next(r for r in main_specs["requirements"] if r["name"] == b["name"])
                lost = [sc["name"] for sc in cur["scenarios"] if sc["name"] not in b.get("scen_names", [])]
                if lost:
                    err.append(f"{tag}: MODIFIED заменяет требование целиком — перенеси и сценарии текущей спеки: "
                               + ", ".join(f"«{x}»" for x in lost) + " (поправь их текст, если поведение меняется)")
        if b["op"] == "ADDED" and main_specs is not None and b["name"] in {r["name"] for r in main_specs["requirements"]}:
            err.append(f"{tag}: такое требование уже есть — тогда это MODIFIED")
    return err
