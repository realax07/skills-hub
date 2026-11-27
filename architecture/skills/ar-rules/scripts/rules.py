#!/usr/bin/env python3
"""Принципы и стандарты архитектуры в проверяемом виде: architecture/principles.json и principles.md.

Источники — документы слоя ar-scan (ADR, вики, Confluence) и договорённости из чата. Скрипт выбирает из документов
утверждения-кандидаты, модель превращает их в принципы (правило, причина, источник, как проверить), скрипт проверяет код
и ландшафт и пишет нарушения с решениями. Проекты получают свои принципы командой link — для dev-агентов и sa-change.

Команды (arch — папка слоя architecture/ от ar-scan):
  scan <arch> [--docs путь …]          кандидаты из документов → RULE-CANDIDATES.md (решения сохраняются)
  add <arch> --title … --rule … --why … --area … --applies … --source … [--status …] [--systems …] --check …
  edit <arch> P-01 [те же поля]
  except <arch> P-01 --system ID --reason … --source …
  verify <arch>                        проверки скриптом → VIOLATIONS.md (решения сохраняются)
  show <arch> [--applies events]       принципы списком
  check <arch>                         проверка слоя принципов
  link <arch> <repo>                   принципы систем репозитория → system-context/principles.md, principles.json, указатель в AGENTS.md
  q <arch> …                           вопрос в QUESTIONS.md (формат sa-scan)

Python 3.9+, только стандартная библиотека.
"""
import argparse
import fnmatch
import hashlib
import json
import os
import re
import sys
from collections import OrderedDict, defaultdict
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "lib"))
import sa  # noqa: E402

AREAS = OrderedDict([("интеграция", "Интеграция"), ("данные", "Данные"), ("деньги", "Деньги и платежи"), ("надёжность", "Надёжность"),
                     ("безопасность", "Безопасность"), ("наблюдаемость", "Наблюдаемость"), ("выкатка", "Выкатка и совместимость"),
                     ("код", "Код и соглашения")])
APPLIES = ("events", "http", "data", "money", "security", "all")
APPLIES_RU = {"events": "события", "http": "вызовы API", "data": "данные и схема", "money": "деньги", "security": "доступ и секреты", "all": "любое изменение"}
STATUSES = ("принят", "предложен", "устарел")
CHECKS = ("no-shared-db", "timeout", "grep", "review")
FILL = "<!-- заполнить"
MODAL = re.compile(r"(?<![\w])(долж\w*|обязан\w*|запрещ\w*|нельзя|не допуска\w*|недопустим\w*|только|всегда|никогда|"
                   r"не мож\w*|MUST|SHALL|SHOULD|NEVER|must not|must|should|never|always|is required|are required|forbidden)(?![\w])")
DOC_EXT = {".md", ".markdown", ".txt", ".adoc", ".rst", ".html", ".htm"}
CODE_EXT = {".py", ".ts", ".tsx", ".js", ".mjs", ".cjs", ".jsx", ".go", ".java", ".kt", ".cs", ".rb", ".php", ".rs", ".scala"}
SKIP = {"node_modules", ".git", "dist", "build", "bin", "obj", "venv", ".venv", "__pycache__", "target", "vendor", ".next", "coverage",
        "system-context", "openspec", "test-cases", "design-context", ".claude"}
TEST_RX = re.compile(r"(^|/)(tests?|__tests__|spec|specs|e2e|testdata)(/|$)|[._-](test|spec)\.\w+$|_test\.\w+$|Tests?\.cs$", re.I)
CALL_RX = re.compile(r"\b(?:fetch|axios(?:\.(?:get|post|put|patch|delete|request))?|httpx\.(?:get|post|put|patch|delete|request|stream)|"
                     r"requests\.(?:get|post|put|patch|delete|request)|got(?:\.(?:get|post|put|patch|delete))?|"
                     r"urllib\.request\.urlopen|http\.(?:Get|Post|NewRequest)|restTemplate\.\w+|webClient\.\w+|"
                     r"\w*[Hh]ttp[Cc]lient\.(?:Get|Post|Put|Patch|Delete|Send)\w*Async)\s*\(")
TIMEOUT_RX = [(re.compile(r"\btimeout\s*[:=]\s*([\d.]+)"), "s?"), (re.compile(r"AbortSignal\.timeout\(\s*([\d_]+)\s*\)"), "ms"),
              (re.compile(r"TimeSpan\.FromSeconds\(\s*([\d.]+)"), "s"), (re.compile(r"TimeSpan\.FromMilliseconds\(\s*([\d.]+)"), "ms"),
              (re.compile(r"\bTimeout\s*=\s*([\d.]+)\s*\*\s*time\.Second"), "s"), (re.compile(r"timeout\s*\(\s*([\d.]+)"), "s?")]
DECISION_V = re.compile(r"^(нарушение:\s*(.{20,})|исключение:\s*(.{20,})|ложное:\s*(.{20,})|вопрос\s+(Q-\d{3,}))$", re.I)
DECISION_K = re.compile(r"^(принцип\s+(P-\d{2,})|дубль\s+(P-\d{2,})|не принцип:\s*(.{15,}))$", re.I)
REF_RX = re.compile(r"[\w./-]+\.\w{1,6}(?::\d+)?|https?://\S+|\bчат\b|\bчеловек\b|Q-\d{3}")


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def squash(s, n=160):
    s = re.sub(r"\s+", " ", s or "").strip()
    return s if len(s) <= n else s[:n - 1] + "…"


def h(s):
    return hashlib.sha1(re.sub(r"\W+", "", s.lower()).encode()).hexdigest()[:8]


class Arch:
    def __init__(self, path):
        self.dir = Path(path).resolve()
        if not (self.dir / "sources.json").is_file():
            sa.die(f"нет {self.dir / 'sources.json'} — сначала слой ar-scan (landscape.py init/add-repo/add-docs/build)")
        self.sources = json.loads((self.dir / "sources.json").read_text(encoding="utf-8"))
        lj = self.dir / "landscape.json"
        self.land = json.loads(lj.read_text(encoding="utf-8")) if lj.is_file() else {}
        self.pj = self.dir / "principles.json"
        self.pmd = self.dir / "principles.md"
        self.cand = self.dir / "RULE-CANDIDATES.md"
        self.viol = self.dir / "VIOLATIONS.md"
        self.questions = self.dir / "QUESTIONS.md"
        self.data = json.loads(self.pj.read_text(encoding="utf-8")) if self.pj.is_file() else OrderedDict(
            [("version", 1), ("modified", ""), ("verified", ""), ("principles", [])])

    def save(self):
        self.data["modified"] = now()
        self.pj.write_text(json.dumps(self.data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        render(self)

    def rel(self, p):
        try:
            return os.path.relpath(Path(p).resolve(), self.dir).replace(os.sep, "/")
        except ValueError:
            return Path(p).as_posix()

    def systems(self):
        return self.land.get("systems", {})

    def repo_path(self, name):
        r = next((x for x in self.sources.get("repos", []) if x["name"] == name), None)
        if not r:
            return None
        p = Path(r["path"])
        return (self.dir / p).resolve() if not p.is_absolute() else p

    def get(self, pid):
        p = next((x for x in self.data["principles"] if x["id"] == pid), None)
        if not p:
            sa.die(f"нет принципа {pid}; есть: {', '.join(x['id'] for x in self.data['principles']) or '—'}")
        return p


# ---------------------------------------------------------------- кандидаты

def html_text(t):
    t = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", "", t)
    t = re.sub(r"(?i)<h([1-3])[^>]*>", lambda m: "\n" + "#" * int(m.group(1)) + " ", t)
    t = re.sub(r"(?i)<br\s*/?>|</p>|</li>|</tr>|</h[1-6]>|</div>", "\n", t)
    t = re.sub(r"<[^>]+>", " ", t)
    for a, b in (("&nbsp;", " "), ("&gt;", ">"), ("&lt;", "<"), ("&amp;", "&"), ("&quot;", "\"")):
        t = t.replace(a, b)
    return re.sub(r"[ \t]+", " ", t)


def doc_paths(A, extra):
    roots = [((A.dir / d["path"]).resolve() if not Path(d["path"]).is_absolute() else Path(d["path"])) for d in A.sources.get("docs", [])]
    roots += [Path(x).resolve() for x in extra]
    for r in roots:
        if r.is_file():
            yield r
        elif r.is_dir():
            for dp, dn, fn in os.walk(r):
                dn[:] = [d for d in sorted(dn) if d not in SKIP and not d.startswith(".")]
                for f in sorted(fn):
                    if Path(f).suffix.lower() in DOC_EXT:
                        yield Path(dp) / f


def candidates(A, extra):
    out = []
    for f in doc_paths(A, extra):
        try:
            t = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if f.suffix.lower() in (".html", ".htm"):
            t = html_text(t)
        relp = A.rel(f)
        adr = bool(re.search(r"(^|/)(adr|adrs|decisions)(/|$)", relp, re.I)) or bool(re.search(r"^#\s*ADR", t, re.M))
        status = (re.search(r"^\s*(?:\*\*)?(?:Статус|Status)(?:\*\*)?\s*:\s*(.+)$", t, re.M | re.I) or [None, ""])[1].strip()
        fence, section = False, ""
        for i, ln in enumerate(t.split("\n"), 1):
            s = ln.strip()
            if s.startswith("```"):
                fence = not fence
                continue
            if fence or not s:
                continue
            m = re.match(r"^#{1,6}\s+(.+)$", s)
            if m:
                section = m.group(1).strip()
                continue
            in_decision = adr and re.search(r"решени|decision", section, re.I)
            if in_decision and re.match(r"^([-*]|\d+[.)])\s+", s) or MODAL.search(s):
                text = re.sub(r"^([-*]|\d+[.)])\s+", "", s)
                if len(text) < 15 or len(text) > 600:
                    continue
                out.append({"key": f"c:{h(text)}", "text": squash(text, 300), "source": f"{relp}:{i}",
                            "adr": adr, "status": status, "section": section})
    seen, uniq = set(), []
    for c in out:
        if c["key"] not in seen:
            seen.add(c["key"])
            uniq.append(c)
    return uniq


def read_decided(path, rx_key=r"<!-- key: (.+?) -->"):
    dec = {}
    if not path.is_file():
        return dec
    key = None
    for ln in path.read_text(encoding="utf-8").split("\n"):
        m = re.search(rx_key, ln)
        if m:
            key = m.group(1)
            dec.setdefault(key, {"check": "", "decision": ""})
            continue
        if not key:
            continue
        m = re.match(r"^\s+- \*\*Проверка:\*\*\s*(.*)$", ln)
        if m:
            v = m.group(1).strip()
            if v and not v.startswith(FILL):
                dec[key]["check"] = v
            continue
        m = re.match(r"^\s+- \*\*Решение:\*\*\s*(.*)$", ln)
        if m:
            v = m.group(1).strip()
            if v and not v.startswith(FILL):
                dec[key]["decision"] = v
            key = None
    return dec


CAND_HEAD = """# Кандидаты в принципы

Утверждения из документов, похожие на правило: решения ADR и фразы «должен», «запрещено», «только через», MUST/SHOULD.
Большинство — не принципы (описание, пожелание, частный случай). Решение — одно из:
- `принцип P-03` — заведён командой `rules.py add` (несколько кандидатов могут вести к одному принципу);
- `дубль P-03` — то же, что уже есть;
- `не принцип: <почему>` — описание поведения, план, частность одной системы.

Пересборка (`rules.py scan`) сохраняет решения по ключу пункта.
"""


def cmd_scan(a):
    A = Arch(a.arch)
    cs = candidates(A, a.docs or [])
    old = read_decided(A.cand)
    out = [CAND_HEAD.rstrip(), ""]
    groups = OrderedDict()
    for c in cs:
        groups.setdefault(c["source"].rsplit(":", 1)[0], []).append(c)
    n = 0
    for doc, its in groups.items():
        st = its[0]["status"]
        out += [f"## {doc}" + (f" — ADR, статус: {st}" if its[0]["adr"] else ""), ""]
        for c in its:
            n += 1
            d = old.get(c["key"], {}).get("decision", "")
            out.append(f"- [{'x' if d else ' '}] K-{n:02d} «{c['text']}» — {c['source']} <!-- key: {c['key']} -->")
            out.append(f"  - **Решение:** {d or FILL + ': принцип P-… | дубль P-… | не принцип: почему -->'}")
        out.append("")
    if not cs:
        out.append("Кандидатов не найдено — документов нет (`landscape.py add-docs`) или в них нет правил; принципы из чата — `rules.py add --source чат`.")
    A.cand.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")
    kept = sum(1 for c in cs if old.get(c["key"], {}).get("decision"))
    print(f"✓ {A.rel(A.cand)}: кандидатов {len(cs)} из {len(groups)} документов, решения сохранены у {kept}")
    print("Дальше: по каждому кандидату — принцип (rules.py add), дубль или «не принцип: почему» (SKILL.md, шаг 3)")
    return 0


# ---------------------------------------------------------------- принципы

def parse_check(a):
    if not a.check:
        return None
    t = a.check
    if t not in CHECKS:
        sa.die("--check: no-shared-db | timeout | grep | review")
    c = OrderedDict([("type", t)])
    if t == "timeout":
        if a.max is None:
            sa.die("--check timeout нужен --max <секунды>: внешний вызов без таймаута или дольше — нарушение")
        c["max"] = a.max
    if t == "grep":
        if not a.pattern or a.mode not in ("must", "must-not"):
            sa.die("--check grep нужны --pattern <регулярное выражение> и --mode must | must-not [--files '*.py,*.ts']")
        try:
            re.compile(a.pattern)
        except re.error as e:
            sa.die(f"--pattern не регулярное выражение: {e}")
        c.update([("pattern", a.pattern), ("mode", a.mode), ("files", a.files or "")])
    if t == "review" or a.question:
        if not a.question and t == "review":
            sa.die("--check review нужен --question «вопрос, который задать себе на ревью дизайна или кода»")
        c["question"] = a.question or ""
    return c


def apply_fields(A, p, a, new=False):
    for k in ("title", "rule", "why"):
        v = getattr(a, k)
        if v is not None:
            p[k] = v.strip()
    if a.area is not None:
        if a.area not in AREAS:
            sa.die("--area: " + " | ".join(AREAS))
        p["area"] = a.area
    if a.applies is not None:
        ap = [x.strip() for x in a.applies.split(",") if x.strip()]
        bad = [x for x in ap if x not in APPLIES]
        if bad or not ap:
            sa.die("--applies — через запятую из: " + ", ".join(APPLIES) + " (к каким изменениям относится)")
        p["applies"] = ap
    if a.source is not None:
        if not REF_RX.search(a.source):
            sa.die("--source — документ:строка, ссылка, «чат» (сказал пользователь) или Q-…")
        p["source"] = a.source
    if a.status is not None:
        if a.status not in STATUSES:
            sa.die("--status: " + " | ".join(STATUSES))
        p["status"] = a.status
    if a.systems is not None:
        ss = [x.strip() for x in a.systems.split(",") if x.strip()]
        unknown = [x for x in ss if x != "all" and A.systems() and x not in A.systems()]
        if unknown:
            sa.die(f"нет систем {', '.join(unknown)} в ландшафте; есть: {', '.join(A.systems())}")
        p["systems"] = "all" if ss in (["all"], []) else ss
    c = parse_check(a)
    if c:
        p["check"] = c
    if new:
        miss = [k for k in ("title", "rule", "why", "area", "applies", "source", "check") if not p.get(k)]
        if miss:
            sa.die("не хватает: " + ", ".join("--" + m for m in miss))


def cmd_add(a):
    A = Arch(a.arch)
    for x in A.data["principles"]:
        if sa.similar(x["title"], a.title or "") > 0.6:
            print(f"! похож на {x['id']}: {x['title']} — может, это дубль (rules.py edit {x['id']} …)")
    n = max([int(x["id"][2:]) for x in A.data["principles"]] + [0]) + 1
    p = OrderedDict([("id", f"P-{n:02d}"), ("title", ""), ("rule", ""), ("why", ""), ("area", ""), ("applies", []), ("source", ""),
                     ("status", "принят"), ("systems", "all"), ("check", None), ("exceptions", [])])
    apply_fields(A, p, a, new=True)
    A.data["principles"].append(p)
    A.save()
    print(f"✓ {p['id']}: {p['title']} ({p['area']}; проверка: {p['check']['type']})")
    return 0


def cmd_edit(a):
    A = Arch(a.arch)
    p = A.get(a.id)
    apply_fields(A, p, a)
    A.save()
    print(f"✓ {p['id']} обновлён")
    return 0


def cmd_except(a):
    A = Arch(a.arch)
    p = A.get(a.id)
    if A.systems() and a.system not in A.systems():
        sa.die(f"нет системы {a.system}; есть: {', '.join(A.systems())}")
    if not REF_RX.search(a.source):
        sa.die("--source — где решено: документ:строка, «чат» или Q-… (исключение без источника — просто нарушение)")
    if len(a.reason.strip()) < 20:
        sa.die("--reason — одной конкретной фразой: почему этой системе можно и до каких пор")
    p["exceptions"] = [x for x in p["exceptions"] if x["system"] != a.system] + [
        OrderedDict([("system", a.system), ("reason", a.reason.strip()), ("source", a.source)])]
    A.save()
    print(f"✓ {p['id']}: исключение для {a.system}; при verify её нарушения этого принципа не считаются")
    return 0


# ---------------------------------------------------------------- проверки

def sys_files(A, sid):
    """Файлы кода системы: репозиторий целиком или её пакет в монорепозитории."""
    s = A.systems().get(sid, {})
    root = A.repo_path(s.get("repo", "")) if s.get("repo") else None
    if not root or not root.is_dir():
        return None, []
    pkg = s.get("package") or "."
    base = root / pkg if pkg != "." else root
    others = [x.get("package") for k, x in A.systems().items() if k != sid and x.get("repo") == s.get("repo") and x.get("package") not in (None, "", ".")]
    files = []
    for dp, dn, fn in os.walk(base):
        dn[:] = [d for d in sorted(dn) if d not in SKIP and not d.startswith(".")]
        for f in sorted(fn):
            p = Path(dp) / f
            relp = p.relative_to(root).as_posix()
            if pkg == "." and any(o and relp.startswith(o + "/") for o in others):
                continue
            if p.suffix.lower() in CODE_EXT and not TEST_RX.search(relp):
                files.append((relp, p))
    return s.get("repo"), files


def in_scope(A, p, sid):
    s = A.systems().get(sid, {})
    if s.get("external") or not s.get("repo"):
        return False
    if any(x["system"] == sid for x in p.get("exceptions", [])):
        return False
    return p.get("systems") == "all" or sid in (p.get("systems") or [])


def read(p):
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def check_shared_db(A, p):
    out = []
    for name, x in A.land.get("infra", {}).items():
        users = [u for u in x.get("users", []) if in_scope(A, p, u)]
        allu = x.get("users", [])
        if x.get("kind") == "база данных" and len(allu) > 1:
            ev = x.get("evidence", {})
            excepted = {x["system"] for x in p.get("exceptions", [])}
            for u in users:
                others = [o for o in allu if o != u]
                if others and all(o in excepted for o in others):
                    continue   # остальные пользователи — заведённые исключения: нарушают они, а не владелец
                out.append((u, f"база `{name}` общая с {', '.join(others)}", (ev.get(u) or [""])[0], f"db:{name}:{u}"))
    return out


def check_timeout(A, p):
    out = []
    mx = float(p["check"]["max"])
    for sid in A.systems():
        if not in_scope(A, p, sid):
            continue
        repo, files = sys_files(A, sid)
        for relp, path in files:
            lines = read(path).split("\n")
            for i, ln in enumerate(lines):
                if ln.lstrip().startswith(("//", "#", "*")) or not CALL_RX.search(ln):
                    continue
                if re.search(r"\b(function|def|async function)\s+\w*\s*\(", ln) and "fetch(" not in ln:
                    continue
                win = "\n".join(lines[i:i + 10])
                depth, end = 0, len(win)
                for k, ch in enumerate(win):
                    depth += (ch == "(") - (ch == ")")
                    if depth == 0 and ch == ")":
                        end = k
                        break
                call = win[:end + 1]
                val = None
                for rx, unit in TIMEOUT_RX:
                    m = rx.search(call)
                    if m:
                        v = float(m.group(1).replace("_", ""))
                        val = v / 1000 if unit == "ms" or (unit == "s?" and v >= 100) else v
                        break
                loc = f"{repo}:{relp}:{i + 1}"
                code = squash(ln.strip().replace("`", ""), 110)
                if val is None:
                    out.append((sid, f"внешний вызов без таймаута (лимит {mx:g} с)", f"{loc} `{code}`", f"to:{sid}:{relp}:{h(code)}"))
                elif val > mx:
                    out.append((sid, f"таймаут {val:g} с больше лимита {mx:g} с", f"{loc} `{code}`", f"to:{sid}:{relp}:{h(code)}"))
    return out


def check_grep(A, p):
    out = []
    c = p["check"]
    rx = re.compile(c["pattern"])
    globs = [g.strip() for g in (c.get("files") or "").split(",") if g.strip()]
    for sid in A.systems():
        if not in_scope(A, p, sid):
            continue
        repo, files = sys_files(A, sid)
        files = [(r, f) for r, f in files if not globs or any(fnmatch.fnmatch(r, g) or fnmatch.fnmatch(Path(r).name, g) for g in globs)]
        hits = []
        for relp, path in files:
            for i, ln in enumerate(read(path).split("\n"), 1):
                if rx.search(ln):
                    hits.append((relp, i, ln))
        if c["mode"] == "must-not":
            for relp, i, ln in hits:
                code = squash(ln.strip().replace("`", ""), 110)
                out.append((sid, f"найдено запрещённое `{c['pattern']}`", f"{repo}:{relp}:{i} `{code}`", f"gn:{sid}:{relp}:{h(code)}"))
        elif files and not hits:
            out.append((sid, f"не найдено обязательное `{c['pattern']}`" + (f" в {', '.join(globs)}" if globs else ""),
                        f"{repo}: файлов проверено {len(files)}", f"gm:{sid}"))
    return out


CHECK_FN = {"no-shared-db": check_shared_db, "timeout": check_timeout, "grep": check_grep}

VIOL_HEAD = """# Нарушения принципов

Что нашли проверки `rules.py verify` в коде и ландшафте. Проверка — эвристика: сначала **Проверка** (открой место, что увидел,
со ссылкой), потом **Решение** — одно из:
- `нарушение: <что не так и что делать, кому>` — подтверждено; исправление — изменение в той системе (sa-change);
- `исключение: <почему этой системе можно>` — и заведи его: `rules.py except <arch> P-… --system … --reason … --source …`;
- `ложное: <почему проверка ошиблась>` — например, таймаут задан общим клиентом;
- `вопрос Q-…` — решить может только человек.

Пересборка сохраняет «Проверку» и «Решение» по ключу пункта.
"""


def cmd_verify(a):
    A = Arch(a.arch)
    if not A.land:
        sa.die(f"нет {A.dir / 'landscape.json'} — сначала landscape.py build {a.arch}")
    old = read_decided(A.viol)
    out = [VIOL_HEAD.rstrip(), ""]
    n = 0
    counts = {}
    for p in A.data["principles"]:
        c = p.get("check") or {}
        fn = CHECK_FN.get(c.get("type"))
        if not fn or p.get("status") == "устарел":
            continue
        found = fn(A, p)
        counts[p["id"]] = len(found)
        if not found:
            continue
        out += [f"## {p['id']}. {p['title']}", "", f"Правило: {p['rule']}", ""]
        for sid, what, ev, k in found:
            n += 1
            key = f"{p['id']}:{k}"
            o = old.get(key, {})
            out.append(f"- [{'x' if o.get('decision') else ' '}] V-{n:02d} `{sid}`: {what} <!-- key: {key} -->")
            if ev:
                out.append(f"  - Где: {ev}")
            out.append(f"  - **Проверка:** {o.get('check') or FILL + ': открой место — это правда нарушение? что увидел, путь:строка -->'}")
            out.append(f"  - **Решение:** {o.get('decision') or FILL + ': нарушение: … | исключение: … | ложное: … | вопрос Q-… -->'}")
        out.append("")
    if not n:
        out.append("Нарушений не найдено.")
    A.viol.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")
    for p in A.data["principles"]:
        p["violations"] = counts.get(p["id"], 0) if (p.get("check") or {}).get("type") in CHECK_FN else None
    A.data["verified"] = now()
    A.save()
    auto = sum(1 for p in A.data["principles"] if (p.get("check") or {}).get("type") in CHECK_FN)
    print(f"✓ {A.rel(A.viol)}: проверено принципов скриптом {auto}, нарушений {n}; "
          f"только на ревью: {sum(1 for p in A.data['principles'] if (p.get('check') or {}).get('type') == 'review')}")
    for pid, k in counts.items():
        if k:
            print(f"  {pid}: {k}")
    return 0


# ---------------------------------------------------------------- вывод

PMD_HEAD = """# Принципы и стандарты

Правила, которые действуют для всех систем ландшафта (или названных), в проверяемом виде: правило, почему, откуда, как проверить.
Их читают dev-агенты перед изменением (как превентивные правила), sa-change при планировании (пункты P в impact.md) и люди на ревью.

Собирает `rules.py` из `principles.json` — не правь руками: `rules.py add`, `edit`, `except`. Нарушения — `VIOLATIONS.md`.
"""


def check_text(c):
    if not c:
        return "⚠ не задано"
    t = c["type"]
    if t == "no-shared-db":
        base = "скрипт: общие базы данных в ландшафте (`rules.py verify`)"
    elif t == "timeout":
        base = f"скрипт: у внешних HTTP-вызовов таймаут не больше {float(c.get('max', 0)):g} с (`rules.py verify`)"
    elif t == "grep":
        base = (f"скрипт: в коде {'должно быть' if c.get('mode') == 'must' else 'не должно быть'} `{c.get('pattern', '')}`"
                + (f" (файлы {c['files']})" if c.get("files") else "") + " (`rules.py verify`)")
    else:
        base = "на ревью"
    return base + (f"; на ревью: «{c['question']}»" if c.get("question") else "")


def principle_md(p, systems=None):
    out = [f"### {p['id']}. {p['title']}", f"- **Правило:** {p['rule']}", f"- **Почему:** {p['why']}",
           f"- **Источник:** {p['source']} (статус: {p.get('status', 'принят')})",
           f"- **Касается:** {', '.join(APPLIES_RU.get(x, x) for x in p.get('applies', []))}; системы: "
           + ("все" if p.get("systems") == "all" else ", ".join(p.get("systems") or [])),
           f"- **Как проверить:** {check_text(p.get('check'))}"]
    ex = [x for x in p.get("exceptions", []) if not systems or x["system"] in systems]
    if ex:
        out.append("- **Исключения:** " + "; ".join(f"`{x['system']}` — {x['reason']} ({x['source']})" for x in ex))
    if p.get("violations") is not None:
        out.append(f"- **Нарушений сейчас:** {p['violations']}" + (" (VIOLATIONS.md)" if p["violations"] else ""))
    return "\n".join(out)


def render(A):
    out = [PMD_HEAD.rstrip(), ""]
    by = defaultdict(list)
    for p in A.data["principles"]:
        by[p.get("area", "код")].append(p)
    for area, title in AREAS.items():
        if by.get(area):
            out += [f"## {title}", ""]
            for p in by[area]:
                out += [principle_md(p), ""]
    if not A.data["principles"]:
        out.append("Принципов пока нет.")
    A.pmd.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")


def cmd_show(a):
    A = Arch(a.arch)
    for p in A.data["principles"]:
        if a.applies and a.applies not in p.get("applies", []) and "all" not in p.get("applies", []):
            continue
        print(f"{p['id']} [{p.get('area')}; {','.join(p.get('applies', []))}; {(p.get('check') or {}).get('type', '—')}] {p['title']}\n    {p['rule']}")
    return 0


# ---------------------------------------------------------------- q / check / link

def cmd_q(a):
    A = Arch(a.arch)
    if a.category not in sa.CATEGORIES:
        sa.die("категория — одна из: " + "; ".join(sa.CATEGORIES))
    if a.importance not in sa.IMPORTANCE:
        sa.die("важность: блокирует | уточняет")
    if not a.title.strip().rstrip("»\"') ").endswith("?"):
        sa.die("вопрос — одной фразой с «?»")
    text = A.questions.read_text(encoding="utf-8") if A.questions.is_file() else "# Вопросы по ландшафту\n\n## Вопросы\n"
    qs = sa.parse_questions(text)
    for q in qs:
        if sa.similar(q["title"], a.title) > 0.6:
            print(f"! похож на {q['id']}: {q['title']} — дополни его, если это тот же вопрос")
    qid = f"Q-{sa.next_qnum(qs):03d}"
    block = sa.question_block(qid, a.title, {"Важность": a.importance, "Категория": a.category, "Что видно": a.seen,
                                             "Затрагивает": a.affects, "Допущение": a.assume, "Кто ответит": a.who, "Ответ": ""})
    A.questions.write_text(text.rstrip() + "\n\n" + block + "\n", encoding="utf-8")
    print(f"✓ {qid}: {a.title}")
    return 0


def check_items(path, rx, label, qids, err):
    if not path.is_file():
        return 0
    key, n = None, 0
    for ln in path.read_text(encoding="utf-8").split("\n"):
        m = re.search(r"((?:K|V)-\d+) .*<!-- key: ", ln)
        if m:
            key = m.group(1)
            n += 1
            continue
        if not key:
            continue
        m = re.match(r"^\s+- \*\*Проверка:\*\*\s*(.*)$", ln)
        if m:
            v = m.group(1).strip()
            if not v or v.startswith(FILL):
                err.append(f"{label} {key}: не заполнена «Проверка» — открой место и запиши, что увидел")
            elif not REF_RX.search(v):
                err.append(f"{label} {key}: в «Проверке» нет ссылки (путь:строка)")
            continue
        m = re.match(r"^\s+- \*\*Решение:\*\*\s*(.*)$", ln)
        if m:
            v = m.group(1).strip()
            d = rx.match(v)
            if not v or v.startswith(FILL):
                err.append(f"{label} {key}: нет решения")
            elif not d:
                err.append(f"{label} {key}: решение «{squash(v, 60)}» не по форме (см. шапку файла)")
            else:
                for qid in sa.Q_RX.findall(v):
                    if qid not in qids:
                        err.append(f"{label} {key}: {qid} нет в QUESTIONS.md")
                yield_ids = re.findall(r"P-\d{2,}", v)
                for pid in yield_ids:
                    if pid not in check_items.pids:
                        err.append(f"{label} {key}: {pid} нет в principles.json")
            key = None
    return n


def cmd_check(a):
    A = Arch(a.arch)
    err, warn = [], []
    ps = A.data["principles"]
    check_items.pids = {p["id"] for p in ps}
    qs = sa.parse_questions(A.questions.read_text(encoding="utf-8")) if A.questions.is_file() else []
    qids = {q["id"] for q in qs}
    if not A.cand.is_file():
        err.append(f"нет {A.rel(A.cand)} — rules.py scan {a.arch}")
    nk = check_items(A.cand, DECISION_K, "RULE-CANDIDATES.md", qids, err)
    if not ps:
        err.append("принципов нет — rules.py add (из кандидатов или того, что сказал пользователь)")
    for p in ps:
        for k in ("rule", "why", "source"):
            if not p.get(k):
                err.append(f"{p['id']}: пусто «{k}»")
        if not p.get("check"):
            err.append(f"{p['id']}: не задано, как проверить (--check)")
        if len(p.get("rule", "")) > 300:
            warn.append(f"{p['id']}: правило длиннее 300 символов — одно правило, одно предложение; подробности — в «почему»")
        if (p.get("check") or {}).get("type") == "review" and not p["check"].get("question"):
            err.append(f"{p['id']}: проверка «на ревью» без вопроса (--question)")
        for x in p.get("exceptions", []):
            for qid in sa.Q_RX.findall(x.get("source", "")):
                if qid not in qids:
                    err.append(f"{p['id']}: исключение ссылается на {qid}, а его нет в QUESTIONS.md")
    used = set()
    if A.cand.is_file():
        used = set(re.findall(r"\*\*Решение:\*\*\s*(?:принцип|дубль)\s+(P-\d{2,})", A.cand.read_text(encoding="utf-8")))
    for p in ps:
        if p["id"] not in used and not re.search(r"\bчат\b|\bчеловек\b|Q-\d{3}", p.get("source", "")):
            warn.append(f"{p['id']}: ни один кандидат не ведёт к нему, а источник не «чат» — проверь источник")
    auto = [p for p in ps if (p.get("check") or {}).get("type") in CHECK_FN]
    if auto and not A.data.get("verified"):
        err.append(f"проверки не запускались — rules.py verify {a.arch}")
    elif auto and A.data.get("modified", "") > A.data.get("verified", ""):
        warn.append("принципы менялись после verify — rules.py verify")
    check_items(A.viol, DECISION_V, "VIOLATIONS.md", qids, err)
    for x in warn:
        print(f"  ! {x}")
    for x in err:
        print(f"  ✗ {x}")
    print(f"Принципов: {len(ps)} (скриптом проверяется {len(auto)}), кандидатов: {nk}. Ошибок: {len(err)}, предупреждений: {len(warn)}")
    return 1 if err else 0


LINK_START, LINK_END = "<!-- ar-rules:start -->", "<!-- ar-rules:end -->"


def cmd_link(a):
    A = Arch(a.arch)
    repo = Path(a.repo).resolve()
    names = [r["name"] for r in A.sources.get("repos", []) if A.repo_path(r["name"]) == repo]
    if not names:
        sa.die(f"{repo} нет в ландшафте — landscape.py add-repo {a.arch} {a.repo}")
    ss = [k for k, v in A.systems().items() if v.get("repo") in names]
    mine = [p for p in A.data["principles"] if p.get("status") != "устарел" and (p.get("systems") == "all" or set(p.get("systems") or []) & set(ss))]
    if not mine:
        sa.die("к системам этого репозитория принципов нет")
    viol = defaultdict(list)
    if A.viol.is_file():
        cur = None
        for ln in A.viol.read_text(encoding="utf-8").split("\n"):
            m = re.match(r"^## (P-\d{2,})\.", ln)
            if m:
                cur = m.group(1)
            m = re.match(r"^- \[.\] V-\d+ `([\w.-]+)`: (.+?) <!-- key", ln)
            if m and cur and m.group(1) in ss:
                viol[cur].append(m.group(2))
    try:
        ref = os.path.relpath(A.dir, repo).replace(os.sep, "/")
    except ValueError:
        ref = A.dir.as_posix()
    ctx = repo / "system-context"
    ctx.mkdir(exist_ok=True)
    md = [f"# Принципы для систем этого репозитория ({', '.join(ss)})\n",
          f"Копия из слоя архитектуры `{ref}` (путь от корня репозитория), пересобирается `rules.py link`. Перед задачей — прочти:",
          "это правила, которые нарушать нельзя без исключения (его заводит архитектор), а не пожелания.\n"]
    for p in mine:
        md.append(principle_md(p, ss))
        if viol.get(p["id"]):
            md.append("- **Нарушается здесь сейчас:** " + "; ".join(viol[p["id"]][:5]) + " — не повторяй и не расширяй")
        md.append("")
    (ctx / "principles.md").write_text("\n".join(md).rstrip() + "\n", encoding="utf-8")
    js = OrderedDict([("source", ref), ("modified", A.data.get("modified", "")), ("systems", ss), ("principles", [
        OrderedDict([("id", p["id"]), ("title", p["title"]), ("rule", p["rule"]), ("why", p["why"]), ("area", p.get("area")),
                     ("applies", p.get("applies", [])), ("check", check_text(p.get("check"))),
                     ("question", (p.get("check") or {}).get("question", "")),
                     ("exceptions", [x for x in p.get("exceptions", []) if x["system"] in ss]),
                     ("violations_here", viol.get(p["id"], []))]) for p in mine])])
    (ctx / "principles.json").write_text(json.dumps(js, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    block = (f"{LINK_START}\n## Принципы архитектуры\n\n"
             f"Перед любой задачей прочти `system-context/principles.md` — правила для этого репозитория из слоя архитектуры (`{ref}`): "
             f"интеграция, данные, деньги, надёжность, безопасность. Нарушить можно только с исключением, которое заводит архитектор; "
             f"не уверен, соблюдаешь ли, — вопрос, а не догадка.\n{LINK_END}")
    ag = repo / "AGENTS.md"
    t = ag.read_text(encoding="utf-8") if ag.is_file() else "# Инструкция для агентов\n"
    t = re.sub(re.escape(LINK_START) + r"[\s\S]*?" + re.escape(LINK_END), lambda m: block, t) if LINK_START in t else t.rstrip() + "\n\n" + block + "\n"
    ag.write_text(t, encoding="utf-8")
    if not (repo / "CLAUDE.md").is_file():
        (repo / "CLAUDE.md").write_text("@AGENTS.md\n", encoding="utf-8")
    print(f"✓ {repo.name}/system-context/principles.md и principles.json: принципов {len(mine)} ({', '.join(ss)}), указатель в AGENTS.md")
    return 0


# ---------------------------------------------------------------- main

def add_fields(p, new):
    p.add_argument("--title", help="коротко, как правило: «Сервис не читает чужую базу»")
    p.add_argument("--rule", help="одно проверяемое предложение: что делать или не делать")
    p.add_argument("--why", help="почему: что сломается без правила")
    p.add_argument("--area", help=" | ".join(AREAS))
    p.add_argument("--applies", help="к каким изменениям: " + ", ".join(APPLIES) + " (через запятую)")
    p.add_argument("--source", help="документ:строка, ссылка, «чат» или Q-…")
    p.add_argument("--status", help=" | ".join(STATUSES) + " (по умолчанию принят)")
    p.add_argument("--systems", help="all или id систем через запятую (по умолчанию all)")
    p.add_argument("--check", help=" | ".join(CHECKS))
    p.add_argument("--max", type=float, help="для timeout: лимит в секундах")
    p.add_argument("--pattern", help="для grep: регулярное выражение")
    p.add_argument("--mode", help="для grep: must | must-not")
    p.add_argument("--files", help="для grep: маски файлов через запятую ('*.py,src/payments/*')")
    p.add_argument("--question", help="вопрос на ревью (обязателен для review, можно и к другим)")


def main():
    ap = argparse.ArgumentParser(description="Принципы архитектуры: кандидаты, принципы, проверки, нарушения")
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("scan", help="кандидаты в принципы из документов")
    p.add_argument("arch")
    p.add_argument("--docs", action="append", help="ещё папка или файл документов")
    p.set_defaults(fn=cmd_scan)
    p = sp.add_parser("add", help="завести принцип")
    p.add_argument("arch")
    add_fields(p, True)
    p.set_defaults(fn=cmd_add)
    p = sp.add_parser("edit", help="изменить принцип")
    p.add_argument("arch")
    p.add_argument("id")
    add_fields(p, False)
    p.set_defaults(fn=cmd_edit)
    p = sp.add_parser("except", help="исключение для системы")
    p.add_argument("arch")
    p.add_argument("id")
    p.add_argument("--system", required=True)
    p.add_argument("--reason", required=True)
    p.add_argument("--source", required=True)
    p.set_defaults(fn=cmd_except)
    p = sp.add_parser("verify", help="проверить код и ландшафт")
    p.add_argument("arch")
    p.set_defaults(fn=cmd_verify)
    p = sp.add_parser("show", help="принципы списком")
    p.add_argument("arch")
    p.add_argument("--applies")
    p.set_defaults(fn=cmd_show)
    p = sp.add_parser("check", help="проверить слой принципов")
    p.add_argument("arch")
    p.set_defaults(fn=cmd_check)
    p = sp.add_parser("link", help="принципы → репозиторий")
    p.add_argument("arch")
    p.add_argument("repo")
    p.set_defaults(fn=cmd_link)
    p = sp.add_parser("q", help="вопрос в QUESTIONS.md")
    p.add_argument("arch")
    for k in ("title", "category", "seen", "affects", "assume", "who"):
        p.add_argument(f"--{k}", required=True)
    p.add_argument("--importance", default="уточняет")
    p.set_defaults(fn=cmd_q)
    a = ap.parse_args()
    if getattr(a, "cmd", "") in ("add", "edit") and a.check is None and getattr(a, "question", None):
        a.check = None
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
