"""Общий код qa-scan: пути слоя, front-matter, HTML → md, кейс в md и обратно, поиск секретов.

Только стандартная библиотека Python 3.9+.
"""
import hashlib
import html
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

LAYER = "test-cases"
PRIORITIES = ["highest", "high", "medium", "low", "lowest"]
STATUSES = ["ready", "draft", "needs-work", "deprecated"]
TYPES = ["manual", "automated", "checklist"]
REQUIRED = ["id", "title", "priority", "status", "type"]
LIST_KEYS = ["tags", "requirements", "capabilities", "code", "autotests"]
KEY_ORDER = ["id", "title", "priority", "status", "type"] + LIST_KEYS + ["source", "custom"]
CASE_RE = re.compile(r"^TC-\d{4,}$")
SHARED_RE = re.compile(r"^SS-\d{3,}$")
SERVICE_FILES = {"ROUTING.md", "INDEX.md", "QUESTIONS.md", "QUALITY.md", "README.md"}


def die(msg, code=2):
    print(f"✗ {msg}", file=sys.stderr)
    sys.exit(code)


def warn(msg):
    print(f"! {msg}", file=sys.stderr)


# ---------------------------------------------------------------- пути

class Paths:
    def __init__(self, repo):
        self.repo = Path(repo).resolve()
        if not self.repo.is_dir():
            die(f"нет папки {repo}")
        self.root = self.repo / LAYER
        self.source = self.root / ".source"
        self.snapshot = self.source / "snapshot.json"
        self.ids = self.source / "ids.json"
        self.config = self.source / "config.json"
        self.redactions = self.source / "redactions.json"
        self.shared = self.root / "_shared"
        self.attachments = self.root / "_attachments"
        self.index_dir = self.root / "_index"
        self.index_json = self.index_dir / "index.json"
        self.routing = self.root / "ROUTING.md"
        self.questions = self.root / "QUESTIONS.md"
        self.quality = self.root / "QUALITY.md"

    def rel(self, p):
        try:
            return Path(p).resolve().relative_to(self.repo).as_posix()
        except ValueError:
            return str(p)

    def case_files(self):
        """Все файлы кейсов (TC-*.md) и общих шагов (SS-*.md) слоя."""
        if not self.root.is_dir():
            return []
        out = []
        for p in sorted(self.root.rglob("*.md")):
            parts = p.relative_to(self.root).parts
            if any(x.startswith(".") for x in parts) or parts[0] in ("_index", "_attachments"):
                continue
            if p.name in SERVICE_FILES:
                continue
            out.append(p)
        return out

    def load_config(self):
        return load_json(self.config, {"lang": "ru"})


def load_json(path, default=None):
    path = Path(path)
    if not path.is_file():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def write_if_changed(path, text):
    path = Path(path)
    if path.is_file() and path.read_text(encoding="utf-8") == text:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return True


# ---------------------------------------------------------------- slug

_TR = dict(zip("абвгдеёжзийклмнопрстуфхцчшщъыьэюя",
               ["a", "b", "v", "g", "d", "e", "e", "zh", "z", "i", "y", "k", "l", "m", "n", "o", "p", "r", "s", "t",
                "u", "f", "h", "ts", "ch", "sh", "sch", "", "y", "", "e", "yu", "ya"]))


def slug(text, limit=40, empty="untitled"):
    s = "".join(_TR.get(c, c) for c in str(text).lower())
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    if len(s) > limit:
        s = s[:limit].rsplit("-", 1)[0] if "-" in s[:limit] else s[:limit]
    return s or empty


# ---------------------------------------------------------------- front-matter (подмножество YAML)

_BARE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.\-/:+]*$")
_KEY = re.compile(r"^[^\W\d][\w\-.]*$")
_NESTED = re.compile(r'^("(?:[^"\\]|\\.)*"|[^\s:"#][^:]*?):(?:\s+(.*))?$')
_RESERVED = {"true", "false", "null", "yes", "no", "on", "off", "~"}


def _scalar(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if v is None:
        return '""'
    if isinstance(v, (int, float)):
        return str(v)
    v = str(v)
    if _BARE.match(v) and v.lower() not in _RESERVED and not v.endswith(":"):
        return v
    return json.dumps(v, ensure_ascii=False)


def dump_meta(meta):
    keys = [k for k in KEY_ORDER if k in meta] + [k for k in meta if k not in KEY_ORDER]
    lines = ["---"]
    for k in keys:
        v = meta[k]
        if isinstance(v, dict):
            if not v:
                continue
            lines.append(f"{k}:")
            for kk, vv in v.items():
                kk = str(kk) if _KEY.match(str(kk)) else json.dumps(str(kk), ensure_ascii=False)
                if isinstance(vv, list):
                    lines.append(f"  {kk}: [" + ", ".join(_scalar(x) for x in vv) + "]")
                else:
                    lines.append(f"  {kk}: {_scalar(vv)}")
        elif isinstance(v, list):
            lines.append(f"{k}: [" + ", ".join(_scalar(x) for x in v) + "]")
        else:
            lines.append(f"{k}: {_scalar(v)}")
    lines.append("---")
    return "\n".join(lines) + "\n"


def _split_flow(s):
    items, cur, q, esc = [], "", None, False
    for ch in s:
        if q:
            cur += ch
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == q:
                q = None
        elif ch in "\"'":
            q = ch
            cur += ch
        elif ch == ",":
            items.append(cur)
            cur = ""
        else:
            cur += ch
    if cur.strip():
        items.append(cur)
    return [_parse_scalar(x.strip()) for x in items if x.strip()]


def _parse_scalar(s):
    s = s.strip()
    if s.startswith("[") and s.endswith("]"):
        return _split_flow(s[1:-1])
    if s.startswith('"') and s.endswith('"') and len(s) >= 2:
        try:
            return json.loads(s)
        except ValueError:
            return s[1:-1]
    if s.startswith("'") and s.endswith("'") and len(s) >= 2:
        return s[1:-1].replace("''", "'")
    if s in ("true", "false"):
        return s == "true"
    if s in ("", "~", "null"):
        return ""
    return s


def parse_meta(text):
    """→ (meta, body, ошибка). Понимает то, что пишет dump_meta, и простые правки человека (списки через «- »)."""
    if not text.startswith("---"):
        return {}, text, "нет front-matter (файл должен начинаться с ---)"
    m = re.match(r"^---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|$)", text, re.S)
    if not m:
        return {}, text, "front-matter не закрыт строкой ---"
    meta, key = {}, None
    for n, line in enumerate(m.group(1).splitlines(), 2):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line.startswith((" ", "\t")):
            if key is None:
                return meta, text[m.end():], f"строка {n}: отступ без ключа"
            st = line.strip()
            if st.startswith("- "):
                if not isinstance(meta[key], list):
                    meta[key] = []
                meta[key].append(_parse_scalar(st[2:]))
                continue
            mm = _NESTED.match(st)
            if not mm:
                return meta, text[m.end():], f"строка {n}: не разобрать {st!r}"
            if not isinstance(meta[key], dict):
                meta[key] = {}
            k = mm.group(1)
            k = _parse_scalar(k) if k.startswith('"') else k.strip()
            meta[key][k] = _parse_scalar(mm.group(2) or "")
            continue
        mm = re.match(r"^([A-Za-z0-9_\-]+):\s*(.*)$", line)
        if not mm:
            return meta, text[m.end():], f"строка {n}: не разобрать {line!r}"
        key = mm.group(1)
        val = mm.group(2)
        meta[key] = _parse_scalar(val) if val.strip() else ""
    return meta, text[m.end():], None


_NOHASH = re.compile(r"^(?:\s+hash:|capabilities:|code:|autotests:)")


def content_hash(text):
    """Хеш файла без строки hash: и полей обогащения (capabilities, code, autotests) — по нему видно,
    правили ли кейс после импорта: обогащение (map.py) правкой не считается."""
    body = "\n".join(l for l in text.splitlines() if not _NOHASH.match(l))
    return hashlib.sha1(body.encode("utf-8")).hexdigest()[:12]


# ---------------------------------------------------------------- HTML → Markdown

_TAG = re.compile(r"<\s*/?\s*[a-zA-Z][a-zA-Z0-9]*(\s[^<>]*)?/?\s*>")


class _H2M(HTMLParser):
    BLOCK = {"p", "div", "section", "article", "blockquote", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "table"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out = []
        self.lists = []
        self.href = None
        self.link_text = None
        self.pre = 0
        self.table = None
        self.cell = None

    def _w(self, s):
        if self.cell is not None:
            self.cell.append(s)
        elif self.link_text is not None:
            self.link_text.append(s)
        else:
            self.out.append(s)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "table":
            self.table = []
            self.out.append("\n\n")
        elif tag == "tr" and self.table is not None:
            self.table.append([])
        elif tag in ("td", "th") and self.table is not None:
            self.cell = []
        elif tag in self.BLOCK:
            self._w("\n\n")
            if tag[0] == "h" and len(tag) == 2:
                self._w("**")
        elif tag == "br":
            self._w("\n")
        elif tag in ("strong", "b"):
            self._w("**")
        elif tag in ("em", "i"):
            self._w("*")
        elif tag == "code" and not self.pre:
            self._w("`")
        elif tag == "pre":
            self.pre += 1
            self._w("\n\n```\n")
        elif tag in ("ul", "ol"):
            self.lists.append([tag, 0])
            self._w("\n")
        elif tag == "li":
            ind = "  " * (len(self.lists) - 1)
            if self.lists and self.lists[-1][0] == "ol":
                self.lists[-1][1] += 1
                self._w(f"\n{ind}{self.lists[-1][1]}. ")
            else:
                self._w(f"\n{ind}- ")
        elif tag == "a":
            self.href = a.get("href") or ""
            self.link_text = []
        elif tag == "img":
            self._w(f"![{a.get('alt') or ''}]({a.get('src') or ''})")

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self.cell is not None and self.table is not None:
            if not self.table:
                self.table.append([])
            self.table[-1].append(re.sub(r"\s+", " ", "".join(self.cell)).strip().replace("|", "\\|"))
            self.cell = None
        elif tag == "table" and self.table is not None:
            rows = [r for r in self.table if r]
            self.table = None
            if rows:
                w = max(len(r) for r in rows)
                rows = [r + [""] * (w - len(r)) for r in rows]
                lines = ["| " + " | ".join(rows[0]) + " |", "|" + "---|" * w]
                lines += ["| " + " | ".join(r) + " |" for r in rows[1:]]
                self.out.append("\n".join(lines) + "\n\n")
        elif tag in self.BLOCK and tag not in ("tr", "table"):
            if tag[0] == "h" and len(tag) == 2:
                self._w("**")
            self._w("\n\n")
        elif tag in ("strong", "b"):
            self._w("**")
        elif tag in ("em", "i"):
            self._w("*")
        elif tag == "code" and not self.pre:
            self._w("`")
        elif tag == "pre":
            self.pre = max(0, self.pre - 1)
            self._w("\n```\n\n")
        elif tag in ("ul", "ol") and self.lists:
            self.lists.pop()
            self._w("\n")
        elif tag == "a" and self.link_text is not None:
            t = "".join(self.link_text).strip()
            href, self.link_text = self.href, None
            if href and t and t != href:
                self._w(f"[{t}]({href})")
            else:
                self._w(href or t)

    def handle_data(self, data):
        if not self.pre:
            data = re.sub(r"[ \t\r\n]+", " ", data)
        self._w(data)


def html_to_md(text):
    if text is None:
        return ""
    text = str(text)
    if not _TAG.search(text):
        return html.unescape(text).replace("\r\n", "\n").strip()
    p = _H2M()
    p.feed(text)
    p.close()
    s = "".join(p.out)
    s = re.sub(r"\*\*\s*\*\*", "", s)
    s = "\n".join(l.rstrip() for l in s.splitlines())
    s = re.sub(r"\n[ \t]*\n(?:[ \t]*\n)+", "\n\n", s)
    return s.strip()


# ---------------------------------------------------------------- секреты и ПДн

TEST_CARDS = {"4242424242424242", "4111111111111111", "5555555555554444", "4000056655665556", "5200828282828210",
              "378282246310005", "371449635398431", "6011111111111117", "2223003122003222", "4000000000000002",
              "4000000000000077", "4000000000009995", "5105105105105100", "4012888888881881", "3530111333300000"}
MASK = "[скрыто: {}]"
_NOT_MASK = r"(?!\[скрыто)"
SECRET_RULES = [
    ("пароль", re.compile(r"(?i)\b(?:парол[ьяеию]\w*|password|passwd|pwd)\b\s*[:=]\s*[\"'«]?" + _NOT_MASK + r"([^\s\"'»<>,;\[\]]{3,})")),
    ("пароль", re.compile(r"(?i)\b(?:парол[ьяеию]\w*|password|passwd)\s+[\"'«]?" + _NOT_MASK +
                          r"((?=[^\s\"'»<>,;]*[0-9!@#$%^&*_])[^\s\"'»<>,;\[\]]{5,})")),
    ("токен", re.compile(r"(?i)\b(?:token|api[_\-]?key|apikey|secret|client[_\-]?secret|access[_\-]?key|токен\w*|ключ\w* api)\b\s*[:=]\s*[\"'«]?"
                         + _NOT_MASK + r"([^\s\"'»<>,;\[\]]{6,})")),
    ("bearer", re.compile(r"(?i)\bbearer\s+" + _NOT_MASK + r"([A-Za-z0-9\-._~+/]{10,}=*)")),
    ("jwt", re.compile(r"\b(eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,})")),
    ("ключ облака", re.compile(r"\b(AKIA[0-9A-Z]{16})\b")),
    ("ключ платёжки", re.compile(r"\b((?:sk|rk)_live_[0-9A-Za-z]{10,})")),
    ("токен github", re.compile(r"\b(gh[pousr]_[A-Za-z0-9]{30,})")),
    ("токен slack", re.compile(r"\b(xox[baprs]-[A-Za-z0-9-]{10,})")),
    ("приватный ключ", re.compile(r"(-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?(?:-----END [A-Z ]*PRIVATE KEY-----|$))")),
    ("пароль в адресе", re.compile(r"://[^/\s:@]+:" + _NOT_MASK + r"([^/\s@]{3,})@")),
]
CARD_RE = re.compile(r"(?<![\d\-])((?:\d[ \-]?){12,18}\d)(?![\d\-])")
PII_RULES = [
    ("телефон", re.compile(r"(?<![\d\w])((?:\+7|8)[\s\-(]*\d{3}[\s\-)]*\d{3}[\s\-]*\d{2}[\s\-]*\d{2})(?!\d)")),
    ("email", re.compile(r"\b([A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,})\b")),
    ("СНИЛС", re.compile(r"\b(\d{3}-\d{3}-\d{3} \d{2})\b")),
]
SAFE_EMAIL = re.compile(r"(?i)@(?:[\w\-]+\.)*(example\.(?:com|org|net)|test|invalid|localhost|example)$|@(test|mailinator|example)\.")


def _luhn(d):
    s, alt = 0, False
    for ch in reversed(d):
        n = int(ch)
        if alt:
            n *= 2
            if n > 9:
                n -= 9
        s += n
        alt = not alt
    return s % 10 == 0


def find_sensitive(text, pii=True):
    """→ список (вид, значение, начало, конец, секрет?). Секрет маскируется всегда, ПДн — по флагу."""
    if not text:
        return []
    found = []
    for kind, rx in SECRET_RULES:
        for m in rx.finditer(text):
            found.append((kind, m.group(1), m.start(1), m.end(1), True))
    for m in CARD_RE.finditer(text):
        d = re.sub(r"\D", "", m.group(1))
        if 13 <= len(d) <= 19 and _luhn(d) and d not in TEST_CARDS and len(set(d)) > 2:
            found.append(("номер карты", m.group(1), m.start(1), m.end(1), True))
    if pii:
        for kind, rx in PII_RULES:
            for m in rx.finditer(text):
                if kind == "email" and SAFE_EMAIL.search(m.group(1)):
                    continue
                found.append((kind, m.group(1), m.start(1), m.end(1), False))
    found.sort(key=lambda x: (x[2], -x[3]))
    out, last = [], -1
    for f in found:  # без пересечений
        if f[2] >= last:
            out.append(f)
            last = f[3]
    return out


class Redactor:
    """Маскирует секреты одинаковым номером на одно значение (S-01), копит журнал без самих значений."""

    def __init__(self, mask_pii=False):
        self.mask_pii = mask_pii
        self.ids = {}
        self.log = {}

    def __call__(self, text, where):
        if not text or not isinstance(text, str):
            return text
        hits = find_sensitive(text)
        if not hits:
            return text
        out, pos = [], 0
        for kind, val, a, b, secret in hits:
            masked = secret or self.mask_pii
            key = hashlib.sha1(val.encode("utf-8")).hexdigest()
            if key not in self.ids:
                self.ids[key] = f"{'S' if secret else 'P'}-{len(self.ids) + 1:02d}"
            rid = self.ids[key]
            e = self.log.setdefault(rid, {"id": rid, "kind": kind, "secret": secret, "masked": masked,
                                          "length": len(val), "where": []})
            if where not in e["where"]:
                e["where"].append(where)
            if masked:
                out.append(text[pos:a])
                out.append(MASK.format(rid))
                pos = b
        out.append(text[pos:])
        return "".join(out)

    def entries(self):
        return sorted(self.log.values(), key=lambda e: e["id"])


# ---------------------------------------------------------------- нормализация полей

_PRI = {
    "highest": ["highest", "blocker", "critical", "крит", "блок", "наивыс", "urgent", "p0", "1 - critical"],
    "high": ["high", "major", "высок", "важн", "p1"],
    "medium": ["medium", "normal", "средн", "нормал", "обычн", "p2"],
    "low": ["low", "minor", "низк", "p3"],
    "lowest": ["lowest", "trivial", "наимен", "тривиал", "p4"],
}
_STA = {
    "ready": ["ready", "approved", "actual", "final", "active", "готов", "актуал", "утвержд", "согласов", "normal"],
    "draft": ["draft", "notready", "not ready", "new", "design", "черновик", "нов", "в работе", "in progress"],
    "needs-work": ["needswork", "needs work", "review", "rework", "на доработ", "требует", "на ревью"],
    "deprecated": ["deprecated", "obsolete", "archived", "outdated", "устар", "архив", "deleted", "удал"],
}


def norm_priority(v):
    s = str(v or "").strip().lower()
    if not s:
        return "medium"
    for k in ("lowest", "highest"):
        if any(s.startswith(x) or s == x for x in _PRI[k]):
            return k
    for k, words in _PRI.items():
        if any(s.startswith(x) or x == s for x in words):
            return k
    return s


def norm_status(v):
    s = str(v or "").strip().lower()
    if not s:
        return "ready"
    for k, words in _STA.items():
        if any(s.startswith(x) or s == x for x in words):
            return k
    return s


def norm_list(v):
    if v is None or v == "":
        return []
    if isinstance(v, str):
        v = re.split(r"[,;\n]", v)
    out = []
    for x in v:
        x = str(x).strip()
        if x and x not in out:
            out.append(x)
    return out


def new_case(**kw):
    c = {"sid": "", "key": "", "url": "", "title": "", "path": [], "priority": "medium", "status": "ready",
         "type": "manual", "tags": [], "requirements": [], "links": [], "objective": "", "preconditions": "",
         "postconditions": "", "expected": "", "steps": [], "params": [], "autotests": [], "custom": {},
         "attachments": [], "version": "", "updated": "", "owner": ""}
    c.update(kw)
    return c


def new_step(action="", expected="", data="", shared=""):
    return {"action": action or "", "expected": expected or "", "data": data or "", "shared": shared or ""}


# ---------------------------------------------------------------- кейс ↔ md

HEAD = {
    "ru": {"objective": "Цель", "preconditions": "Предусловия", "steps": "Шаги", "expected": "Ожидаемый результат",
           "postconditions": "Постусловия", "params": "Параметры", "attachments": "Вложения", "notes": "Заметки",
           "data": "Данные", "exp": "Ожидается", "shared": "Общий шаг", "call": "Вызов кейса", "links": "Ссылки"},
    "en": {"objective": "Objective", "preconditions": "Preconditions", "steps": "Steps", "expected": "Expected result",
           "postconditions": "Postconditions", "params": "Parameters", "attachments": "Attachments", "notes": "Notes",
           "data": "Test data", "exp": "Expected", "shared": "Shared step", "call": "Call test", "links": "Links"},
}
SECTION_NAMES = {}
for _lang, _h in HEAD.items():
    for _k, _v in _h.items():
        SECTION_NAMES[_v.lower()] = _k


def _indent(text, n):
    pad = " " * n
    lines = str(text).strip("\n").splitlines() or [""]
    return lines[0] + "".join("\n" + (pad + l if l.strip() else "") for l in lines[1:])


def render_steps(steps, lang, shared_link):
    h = HEAD[lang]
    out = []
    for i, s in enumerate(steps, 1):
        if s.get("shared"):
            sid, title, path = shared_link(s["shared"])
            label = h["call"] if sid.startswith("TC-") else h["shared"]
            line = f"{i}. [{label} {sid}: {title}]({path})" if path else f"{i}. {h['shared']} {s['shared']} (не найден)"
            if s.get("action"):
                line += " — " + _indent(s["action"], 3)
            out.append(line)
        else:
            out.append(f"{i}. " + _indent(s.get("action") or "—", 3))
        for key, label in (("data", h["data"]), ("expected", h["exp"])):
            v = s.get(key)
            if not v:
                continue
            if re.match(r"^\s*(\||```|- |\* |\d+[.)] )", v):  # таблица, код, список — с новой строки
                out.append(f"   - **{label}:**\n     " + _indent(v, 5))
            else:
                out.append(f"   - **{label}:** " + _indent(v, 5))
    return "\n".join(out)


def render_body(title, header_id, c, lang, shared_link, attach_link):
    h = HEAD[lang]
    parts = [f"# {header_id} {title}".rstrip()]
    for key in ("objective", "preconditions"):
        if c.get(key):
            parts.append(f"## {h[key]}\n\n{c[key]}")
    if c.get("steps"):
        parts.append(f"## {h['steps']}\n\n" + render_steps(c["steps"], lang, shared_link))
    if c.get("expected"):
        parts.append(f"## {h['expected']}\n\n{c['expected']}")
    if c.get("postconditions"):
        parts.append(f"## {h['postconditions']}\n\n{c['postconditions']}")
    if c.get("params"):
        names = []
        for row in c["params"]:
            for k in row:
                if k not in names:
                    names.append(k)
        t = ["| " + " | ".join(names) + " |", "|" + "---|" * len(names)]
        for row in c["params"]:
            t.append("| " + " | ".join(str(row.get(n, "")).replace("|", "\\|").replace("\n", " ") for n in names) + " |")
        parts.append(f"## {h['params']}\n\n" + "\n".join(t))
    if c.get("links"):
        parts.append(f"## {h['links']}\n\n" + "\n".join(
            f"- [{l.get('title') or l.get('url')}]({l.get('url')})" if l.get("url") else f"- {l.get('title')}"
            for l in c["links"]))
    if c.get("attachments"):
        lines = []
        for a in c["attachments"]:
            p = attach_link(a)
            lines.append(f"- [{a.get('name')}]({p})" if p else f"- {a.get('name')} (не скачано: {a.get('url') or 'нет ссылки'})")
        parts.append(f"## {h['attachments']}\n\n" + "\n".join(lines))
    return "\n\n".join(parts) + "\n"


def parse_body(body):
    """→ {sections: {ключ: текст}, steps: [...], title, header_id, unknown: [заголовки]}"""
    res = {"sections": {}, "steps": [], "title": "", "header_id": "", "unknown": []}
    cur = None
    buf = {}
    for line in body.splitlines():
        m = re.match(r"^#\s+(\S+)\s*(.*)$", line)
        if m and cur is None and not res["header_id"]:
            res["header_id"], res["title"] = m.group(1), m.group(2).strip()
            continue
        m = re.match(r"^##\s+(.+?)\s*$", line)
        if m:
            name = m.group(1).strip()
            cur = SECTION_NAMES.get(name.lower())
            if cur is None:
                cur = "x:" + name
                res["unknown"].append(name)
            buf.setdefault(cur, [])
            continue
        if cur is not None:
            buf[cur].append(line)
    for k, lines in buf.items():
        res["sections"][k] = "\n".join(lines).strip()
    res["steps"] = parse_steps(res["sections"].get("steps", ""))
    return res


_STEP = re.compile(r"^(\d+)\.\s+(.*)$")
_FIELD = re.compile(r"^\s{2,}- \*\*([^*:]+):\*\*\s?(.*)$")
_SHARED = re.compile(r"\[(?:Общий шаг|Shared step|Вызов кейса|Call test)\s+((?:SS|TC)-\d+)[^\]]*\]\(([^)]*)\)")


def parse_steps(text):
    steps, cur, field = [], None, None
    for line in text.splitlines():
        m = _STEP.match(line)
        if m:
            cur = {"n": int(m.group(1)), "action": m.group(2), "expected": "", "data": "", "shared": ""}
            sm = _SHARED.search(m.group(2))
            if sm:
                cur["shared"], cur["shared_path"] = sm.group(1), sm.group(2)
            steps.append(cur)
            field = "action"
            continue
        if cur is None:
            continue
        m = _FIELD.match(line)
        if m:
            label = m.group(1).strip().lower()
            key = SECTION_NAMES.get(label)
            field = {"exp": "expected", "data": "data"}.get(key)
            if field:
                cur[field] = m.group(2)
                continue
        if field and (line.startswith("   ") or not line.strip()):
            cur[field] += "\n" + line.strip()
    for s in steps:
        for k in ("action", "expected", "data"):
            s[k] = s[k].strip()
    return steps


def read_case(path):
    text = Path(path).read_text(encoding="utf-8")
    meta, body, err = parse_meta(text)
    parsed = parse_body(body)
    return {"path": Path(path), "text": text, "meta": meta, "body": body, "error": err, **parsed}


def words(text):
    """Нормализованные основы слов для сопоставления (грубо: первые 5 букв)."""
    out = []
    for w in re.findall(r"[A-Za-zА-Яа-яЁё0-9]+", str(text).lower().replace("ё", "е")):
        if len(w) < 3 or w in STOP:
            continue
        out.append(w[:5] if not w.isdigit() else w)
    return out


STOP = set("""и в во на не что как по для при или это его она они оно мы вы ты все всех из за от до под над без после
перед через если то так же уже ещё еще тоже был была были быть есть нет да шаг шаги открыть нажать проверить ввести
кнопку кнопка поле страницу страница отображается отображение выбрать перейти the and for with that this from into
are was were not open click check enter field page button select step steps test case user should verify""".split())


def set_block(path, name, content, head="# Вопросы по тест-кейсам\n\nОтвечай здесь или в чате. Текст вне блоков `qa:auto` скрипты не трогают.\n"):
    """Переписать блок <!-- qa:auto:NAME:start/end --> в файле, остальное сохранить."""
    path = Path(path)
    start, end = f"<!-- qa:auto:{name}:start -->", f"<!-- qa:auto:{name}:end -->"
    text = path.read_text(encoding="utf-8") if path.is_file() else head
    blk = f"{start}\n{content.rstrip()}\n{end}"
    i, j = text.find(start), text.find(end)
    if i != -1 and j != -1:
        text = text[:i] + blk + text[j + len(end):]
    else:
        text = text.rstrip() + "\n\n" + blk + "\n"
    return write_if_changed(path, text)
