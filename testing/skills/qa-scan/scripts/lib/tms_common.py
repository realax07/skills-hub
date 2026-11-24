"""Общее для адаптеров TMS: XML, таблицы (CSV/xlsx), разбор нумерованных шагов, каркас снимка."""
import csv
import io
import re
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

from qa import new_case, new_step, norm_list  # noqa: F401  (адаптеры берут отсюда)


def snapshot(tms, project="", origin=""):
    return {"tms": tms, "project": project, "origin": origin, "cases": [], "shared": [], "notes": [],
            "unknown_fields": {}}


def note_unknown(snap, name):
    snap["unknown_fields"][name] = snap["unknown_fields"].get(name, 0) + 1


# ---------------------------------------------------------------- XML

def parse_xml(path):
    data = Path(path).read_bytes()
    try:
        return ET.fromstring(data)
    except ET.ParseError as e:
        raise ValueError(f"{path}: не XML ({e})")


def tag(el):
    t = el.tag
    return (t.split("}", 1)[1] if "}" in t else t).lower()


def child(el, *names):
    names = [n.lower() for n in names]
    for c in el:
        if tag(c) in names:
            return c
    return None


def children(el, name):
    name = name.lower()
    return [c for c in el if tag(c) == name]


def text(el, *names):
    """Текст дочернего элемента (или самого, если имён нет), включая CDATA и вложенную разметку."""
    if el is None:
        return ""
    if names:
        el = child(el, *names)
        if el is None:
            return ""
    if len(el) and tag(el[0]) == "value" and not (el.text or "").strip():
        return text(el[0])
    s = el.text or ""
    if len(el):  # XHTML внутри элемента — вернуть как разметку
        s += "".join(ET.tostring(c, encoding="unicode") for c in el)
    return s.strip()


# ---------------------------------------------------------------- таблицы

def read_csv(path):
    raw = Path(path).read_bytes()
    for enc in ("utf-8-sig", "cp1251", "latin-1"):
        try:
            s = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    sample = s[:5000]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    rows = list(csv.reader(io.StringIO(s), dialect))
    return [r for r in rows if any(x.strip() for x in r)]


def _col(ref):
    n = 0
    for ch in re.match(r"[A-Z]+", ref).group(0):
        n = n * 26 + ord(ch) - 64
    return n - 1


def read_xlsx(path, sheet=None):
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
          "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}
    with zipfile.ZipFile(path) as z:
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            root = ET.fromstring(z.read("xl/sharedStrings.xml"))
            for si in root.findall("m:si", ns):
                shared.append("".join(t.text or "" for t in si.iter(f"{{{ns['m']}}}t")))
        wb = ET.fromstring(z.read("xl/workbook.xml"))
        rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
        target = {r.get("Id"): r.get("Target") for r in rels}
        sheets = [(s.get("name"), target.get(s.get(f"{{{ns['r']}}}id"))) for s in wb.find("m:sheets", ns)]
        if not sheets:
            raise ValueError(f"{path}: нет листов")
        pick = sheets[0]
        if sheet:
            m = [s for s in sheets if s[0] == sheet]
            if not m:
                raise ValueError(f"{path}: нет листа {sheet!r}; есть: {', '.join(s[0] for s in sheets)}")
            pick = m[0]
        t = pick[1].lstrip("/")
        t = t if t.startswith("xl/") else "xl/" + t
        root = ET.fromstring(z.read(t))
        rows = []
        for row in root.iter(f"{{{ns['m']}}}row"):
            vals = {}
            for c in row.findall("m:c", ns):
                typ, v = c.get("t"), c.find("m:v", ns)
                if typ == "s" and v is not None:
                    val = shared[int(v.text)]
                elif typ == "inlineStr":
                    val = "".join(x.text or "" for x in c.iter(f"{{{ns['m']}}}t"))
                else:
                    val = v.text if v is not None else ""
                vals[_col(c.get("r"))] = val or ""
            if vals:
                w = max(vals) + 1
                rows.append([vals.get(i, "") for i in range(w)])
        return [r for r in rows if any(str(x).strip() for x in r)]


def read_table(path, sheet=None):
    p = str(path).lower()
    if p.endswith((".xlsx", ".xlsm")):
        return read_xlsx(path, sheet)
    return read_csv(path)


# ---------------------------------------------------------------- шаги

_NUM = re.compile(r"^\s*(\d+)[.)]\s+")


def split_numbered(s):
    """«1. a\n2. b» → ["a", "b"]; без нумерации → [s]."""
    s = (s or "").strip()
    if not s:
        return []
    lines = s.splitlines()
    if not _NUM.match(lines[0]):
        return [s]
    out = []
    for l in lines:
        if _NUM.match(l):
            out.append(_NUM.sub("", l, count=1))
        elif out:
            out[-1] += "\n" + l
    return [x.strip() for x in out]


def pair_steps(actions, expected, data=""):
    a, e, d = split_numbered(actions), split_numbered(expected), split_numbered(data)
    if len(a) > 1 and len(e) in (0, len(a)) and len(d) in (0, len(a)):
        return [new_step(x, e[i] if e else "", d[i] if d else "") for i, x in enumerate(a)]
    if not a and not e:
        return []
    return [new_step(actions or "", expected or "", data or "")]


def split_path(s):
    s = (s or "").strip().strip("/\\>")
    if not s:
        return []
    return [x.strip() for x in re.split(r"\s*(?:>|»|\\|/)\s*", s) if x.strip()]
