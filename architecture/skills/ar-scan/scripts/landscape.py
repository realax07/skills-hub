#!/usr/bin/env python3
"""Ландшафт систем за рамками одного проекта: склейка нескольких репозиториев и документации в слой architecture/.

Код систем сканирует копией скриптов sa-scan (опись, события, типы): слой sa-scan в репозитории не обязателен, но если он есть,
из него берутся возможности и открытые вопросы. Документы (md, html-выгрузки Confluence, mermaid, PlantUML, Structurizr,
AsyncAPI) разбираются на связи между системами; расхождения кода и документов — пункты RECONCILE.md с решениями.

Команды (arch — папка слоя, например architecture/):
  init <arch>                                  создать слой
  add-repo <arch> <repo> [--name N] [--split auto|repo|packages]
  add-docs <arch> <path>                       папка или файл документации
  build <arch>                                 сканировать, связать, записать слой (заметки и решения сохраняются)
  system <arch> <id> [--title …] [--purpose … --source …] [--owner …] [--alias …] [--external] [--exclude …] [--merge-into …]
  claim <arch> --from A --to B --kind call|event|data --what … --source путь:строка
  q <arch> --title … --category … --seen … --affects … --assume … --who …
  show <arch> (--system ID | --event ИМЯ | --entry ЧАСТЬ)
  check <arch>                                 проверка слоя
  status <arch>                                что устарело с последней сборки
  link <arch> <repo>                           карточки систем репозитория → <repo>/system-context/landscape.md + указатель в AGENTS.md

Python 3.9+, только стандартная библиотека.
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from collections import OrderedDict, defaultdict
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "lib"))
import sa  # noqa: E402
import contracts as C  # noqa: E402
from inventory import Inv, read, rel, walk  # noqa: E402

TEST_PATH = Inv.TEST_PATH
CARD_BUDGET = 10000          # ~3 тыс. токенов: карточку системы целиком читает и слабая модель
MAX_LINES = 8
DOC_EXT = {".md", ".markdown", ".txt", ".adoc", ".rst", ".html", ".htm", ".mmd", ".puml", ".plantuml", ".pu", ".dsl",
           ".yaml", ".yml", ".json"}
STRIP_SUFFIX = re.compile(r"(?:api|service|services|svc|server|srv)$")
INFRA_IMAGES = re.compile(r"postgres|mysql|mariadb|mongo|redis|rabbitmq|kafka|zookeeper|elasticsearch|opensearch|nats|memcached|"
                          r"minio|localstack|seq|jaeger|prometheus|grafana|keycloak|mssql|sqlserver|clickhouse|cassandra", re.I)
DB_IMAGES = re.compile(r"postgres|mysql|mariadb|mongo|mssql|sqlserver|clickhouse|cassandra|oracle", re.I)
URL_ENV = re.compile(r"^(.+?)[_:.-]*(?:BaseUrl|BaseUri|BaseAddress|Url|Uri|Host|Endpoint|Address|Addr)$", re.I)
SVC_ENV = re.compile(r"^services__([\w-]+)__", re.I)
DECISION_RX = re.compile(r"^(вопрос\s+(Q-\d{3,})|ок:\s*(.+)|не связь:\s*(.+))$", re.I)
REF_RX = re.compile(r"[\w./-]+\.\w{1,6}(?::\d+)?|https?://\S+")
AUTO_START = "<!-- sa:auto id=\""
FILL = "<!-- заполнить"
DB_ENV = re.compile(r"^([A-Z][A-Z0-9]*?)_(?:DB|DATABASE|PG|POSTGRES|MYSQL|MONGO)_(?:URL|URI|DSN|HOST|NAME|CONNECTION)$")
SEARCH_RX = re.compile(r"grep|поиск|искал|ищу|вхожден|не найден|нет ни|нигде", re.I)
PRODUCER_RX = re.compile(r"produc|kafka|publish|bus|broker|channel|queue|topic|nats|sns|sqs|pubsub|emitter", re.I)
KINDS = {"call": "вызов", "event": "событие", "data": "данные"}


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def norm(s):
    return re.sub(r"[^a-z0-9а-яё]+", "", (s or "").lower())


def stripped(s):
    n = norm(s)
    t = STRIP_SUFFIX.sub("", n)
    return t if len(t) >= 3 else n


def git(repo, *args):
    try:
        r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, timeout=30)
        return r.stdout.strip() if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def squash(s, n=140):
    s = re.sub(r"\s+", " ", s or "").strip()
    return s if len(s) <= n else s[:n - 1] + "…"


def sub(items, n=MAX_LINES, pad="  "):
    items = list(items)
    out = [f"{pad}- {x}" for x in items[:n]]
    if len(items) > n:
        out.append(f"{pad}- … ещё {len(items) - n}")
    return out


# ---------------------------------------------------------------- слой

class Arch:
    def __init__(self, path, must=True):
        self.dir = Path(path).resolve()
        self.sources = self.dir / "sources.json"
        self.cache = self.dir / ".cache"
        self.landscape_md = self.dir / "landscape.md"
        self.landscape_json = self.dir / "landscape.json"
        self.contracts = self.dir / "contracts.md"
        self.reconcile = self.dir / "RECONCILE.md"
        self.questions = self.dir / "QUESTIONS.md"
        self.guide = self.dir / "GUIDE.md"
        self.systems_dir = self.dir / "systems"
        if must and not self.sources.is_file():
            sa.die(f"нет {self.sources} — сначала: landscape.py init {path}")
        self.data = json.loads(self.sources.read_text(encoding="utf-8")) if self.sources.is_file() else None

    def save(self):
        self.data["modified"] = now()
        self.sources.write_text(json.dumps(self.data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    def rel(self, p):
        p = Path(p).resolve()
        try:
            return os.path.relpath(p, self.dir).replace(os.sep, "/")
        except ValueError:
            return p.as_posix()

    def repo_path(self, r):
        p = Path(r["path"])
        return (self.dir / p).resolve() if not p.is_absolute() else p

    def systems(self, live=True):
        s = self.data["systems"]
        return OrderedDict((k, v) for k, v in s.items() if not live or not (v.get("excluded") or v.get("merged_into")))

    def resolve(self, name):
        """id системы по имени, алиасу или заголовку; None — не нашлось или неоднозначно."""
        if not name:
            return None
        live = self.systems()
        if name in live:
            return name
        n, st = norm(name), stripped(name)
        hits = set()
        for sid, s in live.items():
            keys = {norm(sid), norm(s.get("title", ""))} | {norm(a) for a in s.get("aliases", [])}
            skeys = {stripped(k) for k in keys if k}
            if n in keys or (st and st in skeys):
                hits.add(sid)
        return hits.pop() if len(hits) == 1 else None


def tmpl(name):
    return (HERE.parent / "assets" / name).read_text(encoding="utf-8")


# ---------------------------------------------------------------- init / add

def cmd_init(a):
    A = Arch(a.arch, must=False)
    if A.data:
        print(f"слой уже есть: {A.sources}")
        return 0
    A.dir.mkdir(parents=True, exist_ok=True)
    A.data = OrderedDict([("version", 1), ("created", now()), ("modified", now()), ("built", ""), ("repos", []), ("docs", []),
                          ("systems", OrderedDict()), ("claims", [])])
    A.save()
    gi = A.dir / ".gitignore"
    if not gi.is_file():
        gi.write_text(".cache/\n", encoding="utf-8")
    if not A.guide.is_file():
        A.guide.write_text(tmpl("GUIDE.md"), encoding="utf-8")
    if not A.questions.is_file():
        A.questions.write_text(tmpl("QUESTIONS.md"), encoding="utf-8")
    print(f"✓ {A.dir}: sources.json, GUIDE.md, QUESTIONS.md")
    print(f"Дальше: landscape.py add-repo {a.arch} <repo> (по одному на репозиторий), add-docs {a.arch} <папка документов>, build {a.arch}")
    return 0


def cmd_add_repo(a):
    A = Arch(a.arch)
    p = Path(a.repo).resolve()
    if not p.is_dir():
        sa.die(f"нет папки {p}")
    name = sa.kebab(a.name or p.name)
    rp = A.rel(p)
    for r in A.data["repos"]:
        if r["name"] == name or A.repo_path(r) == p:
            r.update({"path": rp, "split": a.split or r.get("split", "auto")})
            A.save()
            print(f"✓ репозиторий {r['name']} обновлён ({rp}, split={r['split']})")
            return 0
    A.data["repos"].append(OrderedDict([("name", name), ("path", rp), ("split", a.split or "auto"), ("head", ""), ("built", "")]))
    A.save()
    layer = (p / "system-context" / "plan.json").is_file()
    print(f"✓ репозиторий {name}: {rp}, split={a.split or 'auto'}" + (" — слой sa-scan есть, возможности и вопросы возьму из него" if layer else
                                                                       " — слоя sa-scan нет, код сканирую сам"))
    return 0


def cmd_add_docs(a):
    A = Arch(a.arch)
    p = Path(a.path).resolve()
    if not p.exists():
        sa.die(f"нет {p}")
    rp = A.rel(p)
    if any(d["path"] == rp for d in A.data["docs"]):
        print(f"уже добавлено: {rp}")
        return 0
    A.data["docs"].append(OrderedDict([("path", rp), ("note", a.note or "")]))
    A.save()
    n = sum(1 for _ in doc_files(p))
    print(f"✓ документы: {rp} (файлов {n})")
    return 0


# ---------------------------------------------------------------- скан репозитория

def csproj_refs(root, texts):
    """пакет → пакеты, на которые он ссылается (ProjectReference, workspace-зависимости, replace в go.mod)."""
    refs = defaultdict(set)
    for relp, t in texts.items():
        if relp.endswith((".csproj", ".fsproj", ".vbproj")):
            d = str(Path(relp).parent.as_posix())
            for m in re.finditer(r"<ProjectReference\s+Include=\"([^\"]+)\"", t):
                tgt = (Path(root) / d / m.group(1).replace("\\", "/")).resolve()
                try:
                    refs[d].add(Path(os.path.relpath(tgt.parent, root)).as_posix())
                except ValueError:
                    pass
    return refs


def parse_aspire(texts):
    """AppHost .NET Aspire: проекты с именами, ресурсы, WithReference. → (projects{var: (Projects.X, name)}, res{var: (kind, name, parent)}, refs[(var, var)])."""
    # WaitFor — только порядок запуска (например, ждать миграций), не вызов: связи — по WithReference и адресам в WithEnvironment
    projects, res, refs = {}, {}, []
    add_rx = re.compile(r"^\s*(?:(?:var|const|let)\s+(\w+)\s*=\s*)?(\w+)\s*\.\s*Add(\w*)\s*(?:<\s*Projects\.(\w+)\s*>)?\s*\(\s*\"([\w.-]+)\""
                        r"(?:\s*,\s*\"([^\"]+)\")?")
    for relp, t in texts.items():
        if "DistributedApplication.CreateBuilder" not in t:
            continue
        endpoints = {}
        for stmt in re.split(r";", re.sub(r"//[^\n]*", "", t)):
            src_var = None
            m = add_rx.search(stmt)
            if m and m.group(3) not in ("ForwardedHeaders",):
                var, parent, kind, proj, name, path = m.groups()
                src_var = var or "_" + name
                if not proj and path and re.search(r"[/\\]|\.\w+proj$", path):
                    proj = re.sub(r"\.\w+proj$", "", Path(path.replace("\\", "/")).name).replace(".", "_")
                if proj:
                    projects[src_var] = (proj, name, relp)
                else:
                    res[src_var] = (kind.lower(), name, parent if parent != "builder" else "")
            else:
                me = re.search(r"^\s*(?:var\s+)?(\w+)\s*=\s*(\w+)\s*\.\s*GetEndpoint\(", stmt)
                if me:
                    endpoints[me.group(1)] = me.group(2)
                    continue
                m2 = re.search(r"^\s*(\w+)\s*\.\s*With", stmt)
                if m2:
                    src_var = m2.group(1)
            if src_var:
                for r in re.finditer(r"\.\s*WithReference\s*\(\s*(\w+)", stmt):
                    refs.append((src_var, r.group(1)))
                for r in re.finditer(r"\.\s*WithEnvironment\s*\(\s*\"[^\"]+\"\s*,\s*(\w+)\s*\)", stmt):
                    if r.group(1) in endpoints:
                        refs.append((src_var, endpoints[r.group(1)]))
                if src_var in res and res[src_var][0] in ("yarp", "reverseproxy"):
                    for r in re.finditer(r"\(\s*([\w\s,]+)\)", stmt):
                        for v in re.findall(r"\w+", r.group(1)):
                            refs.append((src_var, v))
    return projects, res, refs


def parse_compose(root, texts):
    """docker-compose: сервис → {dir, image, depends, env_hosts}."""
    out = {}
    for relp, t in texts.items():
        if not re.search(r"(^|/)(docker-)?compose[\w.-]*\.ya?ml$", relp):
            continue
        base = Path(relp).parent
        in_services, cur, sect = False, None, None
        for ln in t.split("\n"):
            if re.match(r"^services:\s*$", ln):
                in_services = True
                continue
            if in_services and re.match(r"^\S", ln):
                in_services = False
            if not in_services:
                continue
            m = re.match(r"^  ([\w.-]+):\s*$", ln)
            if m:
                cur = out.setdefault(m.group(1), {"dir": "", "image": "", "depends": [], "env_hosts": [], "file": relp})
                sect = None
                continue
            if not cur:
                continue
            m = re.match(r"^    (\w[\w_-]*):\s*(.*)$", ln)
            if m:
                sect, val = m.group(1), m.group(2).strip().strip("'\"")
                if sect == "build" and val:
                    cur["dir"] = (base / val).as_posix()
                if sect == "image":
                    cur["image"] = val
                if sect == "depends_on" and val.startswith("["):
                    cur["depends"] += [x.strip(" '\"") for x in val.strip("[]").split(",") if x.strip()]
                continue
            m = re.match(r"^      context:\s*(.+)$", ln)
            if m and sect == "build":
                cur["dir"] = (base / m.group(1).strip().strip("'\"")).as_posix()
                continue
            if sect == "depends_on":
                m = re.match(r"^      -\s*([\w.-]+)|^      ([\w.-]+):\s*$", ln)
                if m:
                    cur["depends"].append(m.group(1) or m.group(2))
            if sect == "environment":
                for h in re.findall(r"://([\w.-]+)", ln):
                    cur["env_hosts"].append(h)
    for s in out.values():
        s["dir"] = os.path.normpath(s["dir"]).replace(os.sep, "/") if s["dir"] else ""
        s["dir"] = "." if s["dir"] in ("", ".") and not s["image"] else s["dir"]
    return out


def scan_repo(A, r):
    root = A.repo_path(r)
    if not root.is_dir():
        print(f"  ! {r['name']}: нет папки {root} — пропускаю")
        return None
    print(f"  · {r['name']}: опись и события…", flush=True)
    inv = Inv(root).run().result()
    src = C.Src(root, inv)
    T = C.Types().build(src)
    evs = C.events(src, T, inv, {})
    layer = root / "system-context"
    plan = json.loads((layer / "plan.json").read_text(encoding="utf-8")) if (layer / "plan.json").is_file() else None
    qs = sa.parse_questions((layer / "QUESTIONS.md").read_text(encoding="utf-8")) if (layer / "QUESTIONS.md").is_file() else []
    return {"root": root, "inv": inv, "src": src, "T": T, "events": evs, "plan": plan, "questions": qs,
            "refs": csproj_refs(root, src.texts), "aspire": parse_aspire(src.texts), "compose": parse_compose(root, src.texts),
            "head": git(root, "rev-parse", "HEAD")}


def is_test_pkg(d):
    return bool(TEST_PATH.search(d + "/")) or bool(re.search(r"(^|[/.])(Tests?|UnitTests|FunctionalTests|IntegrationTests|e2e)($|[/.])", d))


def assign_systems(A, r, S):
    """Пакеты репозитория → системы. Новые системы заводятся сами; уже заведённые (переименованные, исключённые) не трогаются."""
    inv, src = S["inv"], S["src"]
    pkgs = [pk["dir"] for pk in inv.get("stack", []) if pk["dir"] not in (".", "")]
    has_entries = defaultdict(int)
    for e in inv.get("entries", []):
        if not TEST_PATH.search(e["file"]):
            has_entries[src.package_of(e["file"])] += 1
    host_pk = defaultdict(int)
    for h in inv.get("outbound", {}).get("hosts", {}).values():
        for f in h.get("files", []):
            host_pk[src.package_of(f.split(":")[0])] += 1
    projects = S["aspire"][0]
    deploy_dirs = {d for d in pkgs for (proj, _, _) in projects.values() if Path(d).name.replace(".", "_").lower() == proj.lower()}
    deploy_dirs |= {s["dir"] for s in S["compose"].values() if s["dir"] and not s["image"]}
    apps = [d for d in pkgs if not is_test_pkg(d) and (has_entries[d] or d in deploy_dirs)
            and not re.search(r"(AppHost|ServiceDefaults)$", d)]
    split = r.get("split", "auto")
    if split == "auto":
        split = "packages" if len(apps) >= 2 else "repo"
    r["split_used"] = split
    pkg_sys = {}
    sysmap = A.data["systems"]
    if split == "repo":
        sid = next((k for k, v in sysmap.items() if v.get("repo") == r["name"] and v.get("package") == "."), None) or sa.kebab(r["name"])
        pkg_sys["."] = sid
        for d in pkgs:
            pkg_sys[d] = sid
        if sid not in sysmap:
            sysmap[sid] = new_system(r["name"], r["name"], ".")
    else:
        for d in apps:
            sid = next((k for k, v in sysmap.items() if v.get("repo") == r["name"] and v.get("package") == d), None)
            if not sid:
                sid = sa.kebab(Path(d).name)
                if sid in sysmap:
                    sid = sa.kebab(r["name"] + "-" + Path(d).name)
                sysmap[sid] = new_system(Path(d).name, r["name"], d)
            pkg_sys[d] = sid
        # библиотеки: к той системе, что на них ссылается (одна) или по общему префиксу имени
        users = defaultdict(set)
        for d, tg in S["refs"].items():
            if d in pkg_sys:
                for x in tg:
                    users[x].add(pkg_sys[d])
        for d in pkgs:
            if d in pkg_sys or is_test_pkg(d):
                continue
            u = users.get(d, set())
            if len(u) == 1:
                pkg_sys[d] = next(iter(u))
                continue
            if not u:
                pre = re.split(r"[.\-_]", Path(d).name)[0].lower()
                cand = {s for p, s in pkg_sys.items() if re.split(r"[.\-_]", Path(p).name)[0].lower() == pre}
                if len(cand) == 1:
                    pkg_sys[d] = next(iter(cand))
    # слияния и исключения — по настройкам систем
    for d, sid in list(pkg_sys.items()):
        s = sysmap.get(sid, {})
        while s.get("merged_into"):
            sid = s["merged_into"]
            s = sysmap.get(sid, {})
        pkg_sys[d] = None if s.get("excluded") else sid
    # алиасы из развёртывания
    for var, (proj, name, _) in projects.items():
        for d, sid in pkg_sys.items():
            if sid and Path(d).name.replace(".", "_").lower() == proj.lower():
                add_alias(sysmap[sid], name)
    for name, s in S["compose"].items():
        if s["dir"] and not s["image"]:
            sid = pkg_sys.get(s["dir"]) if split == "packages" else pkg_sys.get(".")
            if sid:
                add_alias(sysmap[sid], name)
    return pkg_sys


def new_system(title, repo, package):
    return OrderedDict([("title", title), ("repo", repo), ("package", package), ("aliases", []), ("purpose", ""), ("purpose_src", ""),
                        ("owner", ""), ("owner_src", ""), ("external", False), ("excluded", ""), ("merged_into", "")])


def add_alias(s, a):
    if a and a not in s["aliases"] and norm(a) not in (norm(s["title"]),):
        s["aliases"].append(a)


# ---------------------------------------------------------------- документы

def doc_files(p):
    p = Path(p)
    if p.is_file():
        yield p
        return
    for f in walk(p):
        if f.suffix.lower() in DOC_EXT:
            yield f


def html_text(t):
    t = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", "", t)
    t = re.sub(r"(?i)<h([1-3])[^>]*>", lambda m: "\n" + "#" * int(m.group(1)) + " ", t)
    t = re.sub(r"(?i)<br\s*/?>|</p>|</li>|</tr>|</h[1-6]>|</div>", "\n", t)
    t = re.sub(r"<[^>]+>", " ", t)
    t = t.replace("&nbsp;", " ").replace("&gt;", ">").replace("&lt;", "<").replace("&amp;", "&").replace("&quot;", "\"")
    return re.sub(r"[ \t]+", " ", t)


MER_NODE = re.compile(r"(?<![\w.-])([A-Za-z0-9_][\w.]*)\s*(?:\[\(|\(\[|\[\[|\(\(|\{\{|\[/|\[\\|\[|\(|\{)\s*\"?([^\]\)\}\"]+?)\"?\s*(?:\)\]|\]\)|\]\]|\)\)|\}\}|/\]|\\\]|\]|\)|\})")
MER_EDGE = re.compile(r"([A-Za-z0-9_][\w.]*)\s*(?:-->|---|==>|-\.->|--o|--x|-->>|--\s+([^-|>]+?)\s+-->|==\s+([^=]+?)\s+==>|-\.\s+([^.]+?)\s+\.->)\s*"
                      r"(?:\|\"?([^|\"]*)\"?\|)?\s*([A-Za-z0-9_][\w.]*)")
SEQ_EDGE = re.compile(r"^\s*([\w.-]+)\s*(--?>>|--?>|--?\)|--?x)\s*([\w.-]+)\s*:\s*(.*)$")
SEQ_PART = re.compile(r"^\s*(?:participant|actor)\s+([\w.-]+)(?:\s+as\s+(.+))?$")
PUML_PART = re.compile(r"^\s*(?:participant|actor|component|database|queue|node|rectangle|boundary|control|entity|collections|"
                       r"system|System|System_Ext|Container|ContainerDb|ContainerQueue|Component)\s*\(?\s*\"?([^\"]+?)\"?\s+as\s+([\w.-]+)", re.I)
PUML_C4 = re.compile(r"^\s*(?:System|System_Ext|Container|ContainerDb|ContainerQueue|Component|Person)\s*\(\s*([\w.-]+)\s*,\s*\"([^\"]+)\"")
PUML_REL = re.compile(r"^\s*Rel\w*\s*\(\s*([\w.-]+)\s*,\s*([\w.-]+)\s*,\s*\"([^\"]*)\"")
PUML_EDGE = re.compile(r"^\s*(\[[^\]]+\]|\"[^\"]+\"|[\w.-]+)\s*(<?[-.]+(?:\[[^\]]*\])?[-.]*>?>?)\s*(\[[^\]]+\]|\"[^\"]+\"|[\w.-]+)\s*(?::\s*(.*))?$")
DSL_SYS = re.compile(r"^\s*([\w.-]+)\s*=\s*(?:softwareSystem|container|person|component)\s+\"([^\"]+)\"")
DSL_EDGE = re.compile(r"^\s*([\w.-]+)\s*->\s*([\w.-]+)\s*(?:\"([^\"]*)\")?")
EVENT_WORDS = re.compile(r"event|событ|topic|топик|queue|очеред|publish|публик|subscribe|подпис|kafka|rabbit|amqp|message|сообщен|async", re.I)


def parse_diagrams(text, relp, base_line=0):
    """→ [(откуда, куда, подпись, вид, строка)] по mermaid, PlantUML (включая C4), Structurizr DSL."""
    edges, labels = [], {}
    lines = text.split("\n")
    mode = None
    for i, ln in enumerate(lines, 1):
        s = ln.strip()
        if s.startswith("```"):
            lang = s[3:].strip().lower()
            mode = (lang if lang in ("mermaid", "plantuml", "puml", "structurizr", "dsl") else "other") if mode is None else None
            continue
        if re.match(r"^@startuml", s):
            mode = "plantuml"
            continue
        if re.match(r"^@enduml", s):
            mode = None
            continue
        if mode is None and relp.endswith(".mmd"):
            mode = "mermaid"
        if mode is None and relp.endswith((".puml", ".plantuml", ".pu")):
            mode = "plantuml"
        if mode is None and relp.endswith(".dsl"):
            mode = "dsl"
        ln_no = base_line + i
        if mode == "mermaid":
            m = SEQ_PART.match(s)
            if m:
                labels[m.group(1)] = (m.group(2) or m.group(1)).strip()
                continue
            m = SEQ_EDGE.match(s)
            if m:
                a, arrow, b, txt = m.groups()
                edges.append((a, b, txt.strip(), "event" if ")" in arrow or EVENT_WORDS.search(txt) else "call", ln_no))
                continue
            for nm in MER_NODE.finditer(s):
                labels.setdefault(nm.group(1), nm.group(2).strip())
            plain = MER_NODE.sub(lambda m: m.group(1), s)
            pos = 0
            while True:
                m = MER_EDGE.search(plain, pos)
                if not m:
                    break
                a, t1, t2, t3, t4, b = m.groups()
                txt = (t1 or t2 or t3 or t4 or "").strip()
                if a.lower() not in ("graph", "flowchart", "subgraph", "end", "classdef", "class", "style"):
                    edges.append((a, b, txt, "event" if EVENT_WORDS.search(txt) or "-.->" in m.group(0) else "call", ln_no))
                pos = m.start(6)
        elif mode in ("plantuml", "puml"):
            m = PUML_C4.match(s)
            if m:
                labels[m.group(1)] = m.group(2)
                continue
            m = PUML_REL.match(s)
            if m:
                edges.append((m.group(1), m.group(2), m.group(3), "event" if EVENT_WORDS.search(m.group(3)) else "call", ln_no))
                continue
            m = PUML_PART.match(s)
            if m:
                labels[m.group(2)] = m.group(1).strip()
                continue
            m = PUML_EDGE.match(s)
            if m and ("-" in m.group(2) or "." in m.group(2)) and (">" in m.group(2) or "<" in m.group(2)):
                a, arrow, b, txt = m.groups()
                a, b = a.strip("[]\""), b.strip("[]\"")
                if arrow.startswith("<"):
                    a, b = b, a
                txt = (txt or "").strip()
                edges.append((a, b, txt, "event" if EVENT_WORDS.search(txt) or "." in arrow else "call", ln_no))
        elif mode in ("dsl", "structurizr"):
            m = DSL_SYS.match(s)
            if m:
                labels[m.group(1)] = m.group(2)
                continue
            m = DSL_EDGE.match(s)
            if m:
                edges.append((m.group(1), m.group(2), (m.group(3) or "").strip(), "event" if EVENT_WORDS.search(m.group(3) or "") else "call", ln_no))
    return [(labels.get(a, a), labels.get(b, b), t, k, n, a, b) for a, b, t, k, n in edges]


def parse_asyncapi(text):
    """AsyncAPI 2/3 (грубо, без YAML-библиотеки) → (title, [(канал, 'send'|'receive')])."""
    if not re.search(r"^asyncapi:", text, re.M):
        return None
    title = (re.search(r"^info:\s*\n(?:\s+.*\n)*?\s+title:\s*['\"]?([^'\"\n]+)", text, re.M) or [None, ""])[1]
    ops = []
    v3 = re.search(r"^asyncapi:\s*['\"]?3", text, re.M)
    lines = text.split("\n")
    if not v3:
        in_ch, ch = False, None
        for ln in lines:
            if re.match(r"^channels:\s*$", ln):
                in_ch = True
                continue
            if in_ch and re.match(r"^\S", ln):
                in_ch = False
            if not in_ch:
                continue
            m = re.match(r"^  ['\"]?([^'\":\s][^'\":]*)['\"]?:\s*$", ln)
            if m:
                ch = m.group(1).strip()
                continue
            m = re.match(r"^    (publish|subscribe):", ln)
            if m and ch:
                # v2: subscribe — приложение отправляет (другие подписываются), publish — приложение получает
                ops.append((ch, "send" if m.group(1) == "subscribe" else "receive"))
    else:
        chans, cur = {}, None
        in_ch = False
        for ln in lines:
            if re.match(r"^channels:\s*$", ln):
                in_ch = True
                continue
            if in_ch and re.match(r"^\S", ln):
                in_ch = False
            if in_ch:
                m = re.match(r"^  ([\w.-]+):\s*$", ln)
                if m:
                    cur = m.group(1)
                    chans[cur] = cur
                m = re.match(r"^    address:\s*['\"]?([^'\"\n]+)", ln)
                if m and cur:
                    chans[cur] = m.group(1).strip()
        for m in re.finditer(r"action:\s*['\"]?(send|receive)['\"]?\s*\n\s*channel:\s*\n?\s*\$ref:\s*['\"]?#/channels/([\w.-]+)", text):
            ops.append((chans.get(m.group(2), m.group(2)), m.group(1)))
        for m in re.finditer(r"channel:\s*\n?\s*\$ref:\s*['\"]?#/channels/([\w.-]+)['\"]?\s*\n\s*action:\s*['\"]?(send|receive)", text):
            ops.append((chans.get(m.group(1), m.group(1)), m.group(2)))
    return title.strip(), ops


def is_adr(relp, text):
    if re.search(r"(^|/)(adr|adrs|decisions|architecture-decisions)(/|$)", relp, re.I):
        return True
    head = text[:1500]
    return bool(re.search(r"^#\s*(ADR[-\s]?\d+|\d{1,4}[.\s-]+\S)", head, re.M | re.I)
                and re.search(r"^\s*(?:#+\s*)?(Status|Статус)\b", head, re.M | re.I))


def scan_docs(A):
    docs = []
    for d in A.data["docs"]:
        base = (A.dir / d["path"]).resolve() if not Path(d["path"]).is_absolute() else Path(d["path"])
        if not base.exists():
            print(f"  ! нет документов {d['path']}")
            continue
        for f in doc_files(base):
            t = read(f)
            if not t.strip():
                continue
            relp = A.rel(f)
            ext = f.suffix.lower()
            if ext in (".yaml", ".yml", ".json"):
                aa = parse_asyncapi(t)
                if aa:
                    docs.append({"file": relp, "title": aa[0] or f.stem, "kind": "asyncapi", "asyncapi": aa[1], "edges": [], "text": "",
                                 "adr": False})
                continue
            if ext in (".html", ".htm"):
                t = html_text(t)
            title = (re.search(r"^#\s+(.+)$", t, re.M) or re.search(r"^(.{3,80})$", t.strip(), re.M) or [None, f.stem])[1].strip()
            docs.append({"file": relp, "title": squash(title, 90), "kind": "doc", "edges": parse_diagrams(t, relp), "text": t,
                         "adr": is_adr(relp, t), "lines": t.count("\n") + 1})
    return docs


def docs_hash(A):
    out = {}
    for d in A.data["docs"]:
        base = (A.dir / d["path"]).resolve() if not Path(d["path"]).is_absolute() else Path(d["path"])
        if base.exists():
            for f in doc_files(base):
                try:
                    out[A.rel(f)] = hashlib.sha1(f.read_bytes()).hexdigest()[:12]
                except OSError:
                    pass
    return out


def mentions(A, text):
    """системы, упомянутые в тексте (по id, заголовку и алиасам от 4 букв)."""
    found = set()
    low = text.lower()
    for sid, s in A.systems().items():
        for k in {sid, s.get("title", "")} | set(s.get("aliases", [])):
            k = (k or "").strip()
            if len(k) < 4:
                continue
            if re.search(r"(?<![\w-])" + re.escape(k.lower()) + r"(?![\w-])", low):
                found.add(sid)
                break
    return found


# ---------------------------------------------------------------- связи из кода

class Links:
    def __init__(self):
        self.edges = OrderedDict()   # (from, to, kind) -> {"what": set, "evidence": [..]}
        self.events = OrderedDict()  # name -> {"pub": {sys: [loc]}, "sub": {sys: [loc]}, "defs": {sys: [def]}}
        self.http = OrderedDict()    # (owner, prefix) -> {"entries": [...], "consumers": {sys: [loc+code]}}
        self.grpc = OrderedDict()    # (owner, svc) -> {"rpcs": [...], "consumers": {sys: [loc]}}
        self.infra = defaultdict(lambda: {"kind": "", "users": defaultdict(list)})   # name -> users {sys: [evidence]}
        self.hosts = defaultdict(lambda: defaultdict(list))   # host -> {sys: [loc]}  (не сопоставленные с системами)
        self.deploy = []

    def edge(self, a, b, kind, what, ev):
        if not a or not b or a == b:
            return
        e = self.edges.setdefault((a, b, kind), {"what": OrderedDict(), "evidence": []})
        e["what"][what] = 1
        if ev and ev not in e["evidence"]:
            e["evidence"].append(ev)


def link_code(A, scans, L):
    def sys_of(rname, relp):
        if TEST_PATH.search(relp):
            return None
        S = scans[rname]
        return S["pkg_sys"].get(S["src"].package_of(relp))

    # события
    for rname, S in scans.items():
        for name, x in S["events"].items():
            if x.get("internal"):
                continue
            ev = L.events.setdefault(name, {"pub": defaultdict(list), "sub": defaultdict(list), "defs": defaultdict(list)})
            for loc in x["publishers"]:
                s = sys_of(rname, loc.split(":")[0])
                if s:
                    ev["pub"][s].append(f"{rname}:{loc}")
            for loc in x["subscribers"] + x["registrations"]:
                s = sys_of(rname, loc.split(":")[0])
                if s:
                    ev["sub"][s].append(f"{rname}:{loc}")
            for d in x["defs"]:
                s = sys_of(rname, d["file"])
                if s:
                    ev["defs"][s].append(dict(d, file=f"{rname}:{d['file']}"))
    # публикация в тему по имени: подписчик может быть в другом репозитории, поэтому ищем по всем темам ландшафта
    known = set(L.events)
    for rname, S in scans.items():
        for relp, t in S["src"].code():
            me = sys_of(rname, relp)
            if not me:
                continue
            for m in C.TOPIC_PUB.finditer(t):
                name = m.group(1)
                recv = re.search(r"(\w+)\s*$", t[max(0, m.start() - 40):m.start()])
                if name not in known and not (recv and PRODUCER_RX.search(recv.group(1))):
                    continue
                ev = L.events.setdefault(name, {"pub": defaultdict(list), "sub": defaultdict(list), "defs": defaultdict(list)})
                loc = f"{rname}:{relp}:{C.line_of(t, m.start())}"
                if loc not in ev["pub"][me]:
                    ev["pub"][me].append(loc)
    for name, ev in L.events.items():
        for p in ev["pub"]:
            for s in ev["sub"]:
                L.edge(p, s, "event", name, ev["pub"][p][0] + " → " + ev["sub"][s][0])

    # HTTP: префиксы входов каждой системы ищем в коде остальных
    prefixes = defaultdict(list)   # prefix -> [(owner, entry)]
    for rname, S in scans.items():
        for e in S["inv"].get("entries", []):
            if e["kind"] != "http" or TEST_PATH.search(e["file"]):
                continue
            owner = sys_of(rname, e["file"])
            if not owner:
                continue
            path = e["name"].split(" ", 1)[1] if " " in e["name"] else e["name"]
            segs = path.strip("/").split("/")
            n = 2 if segs and segs[0].lower() in ("api", "v1", "v2", "v3", "rest", "public", "internal") else 1
            if segs and len(segs) > n and re.fullmatch(r"v\d+", segs[n - 1], re.I):
                n += 1
            pre = C.static_prefix(path, n)
            if "/" not in pre and (len(pre) < 5 or pre.lower() in C.COMMON_SEGS):
                continue
            if len(pre) < 4:
                continue
            prefixes[pre].append((owner, e))
            L.http.setdefault((owner, pre), {"entries": [], "consumers": defaultdict(list)})["entries"].append(e["name"])
    if prefixes:
        alts = sorted(prefixes, key=len, reverse=True)
        rx = re.compile(r"['\"`/{]((?:" + "|".join(re.escape(p) for p in alts) + r"))(?:['\"`/?{]|$)", re.M | re.I)
        low = {p.lower(): p for p in alts}
        for rname, S in scans.items():
            for relp, t in S["src"].texts.items():
                me = sys_of(rname, relp)
                if not me:
                    continue
                for i, ln in enumerate(S["src"].ln(relp), 1):
                    if ln.lstrip().startswith(("//", "#", "*", "<!--")):
                        continue
                    for m in rx.finditer(ln):
                        pre = low.get(m.group(1).lower())
                        owners = {o for o, _ in prefixes.get(pre, [])}
                        if me in owners or len(owners) != 1:
                            continue
                        o = next(iter(owners))
                        L.http[(o, pre)]["consumers"][me].append(f"{rname}:{relp}:{i} `{squash(ln.replace('`', ''), 110)}`")
                        L.edge(me, o, "call", f"HTTP /{pre}", f"{rname}:{relp}:{i}")
    # gRPC
    for rname, S in scans.items():
        svcs = defaultdict(list)
        for e in S["inv"].get("entries", []):
            if e["kind"] == "grpc" and not TEST_PATH.search(e["file"]):
                o = sys_of(rname, e["file"])
                if o:
                    svcs[(o, e["name"].split(".")[0])].append(e["name"])
        for (o, svc), rpcs in svcs.items():
            L.grpc[(o, svc)] = {"rpcs": rpcs, "consumers": defaultdict(list)}
    for (o, svc), g in L.grpc.items():
        rx = re.compile(rf"\b{re.escape(svc)}(?:\.{re.escape(svc)})?Client\b|\b{re.escape(svc)}ServiceClient\b|\b{re.escape(svc)}GrpcClient\b")
        for rname, S in scans.items():
            for relp, t in S["src"].code():
                me = sys_of(rname, relp)
                if not me or me == o or relp.endswith(".proto"):
                    continue
                m = rx.search(t)
                if m:
                    loc = f"{rname}:{relp}:{C.line_of(t, m.start())}"
                    g["consumers"][me].append(loc)
                    L.edge(me, o, "call", f"gRPC {svc}", loc)
    # адреса: хосты по имени сервиса, env с адресами, развёртывание
    for rname, S in scans.items():
        inv = S["inv"]
        for host, h in inv.get("outbound", {}).get("hosts", {}).items():
            token = host.replace(" (сервис по имени)", "").split(":")[0]
            for f in h.get("files", []):
                me = sys_of(rname, f.split(":")[0])
                if not me:
                    continue
                fp, _, ln = f.partition(":")
                line = S["src"].ln(fp)[int(ln) - 1] if ln.isdigit() and int(ln) <= len(S["src"].ln(fp)) else ""
                code_part = re.split(r"(?<![:\"'])//|\s#\s|<!--", line)[0]
                if line and (re.match(r"\s*(#|\*|/\*)", line) or token.split(".")[0] not in code_part):
                    continue   # ссылка в комментарии — не связь
                tgt = A.resolve(token) or A.resolve(token.split(".")[0])
                if tgt and tgt != me:
                    L.edge(me, tgt, "call", f"адрес {token}", f"{rname}:{f}")
                elif not tgt and "." in token:
                    L.hosts[token][me].append(f"{rname}:{f}")
        for name, x in inv.get("env", {}).items():
            m = SVC_ENV.match(name) or URL_ENV.match(name)
            if not m:
                continue
            tgt = A.resolve(m.group(1))
            for f in x.get("files", []):
                me = sys_of(rname, f.split(":")[0])
                if tgt and me and tgt != me:
                    L.edge(me, tgt, "call", f"адрес из настройки {name}", f"{rname}:{f}")
        for name, x in inv.get("env", {}).items():
            m = DB_ENV.match(name)
            if m:   # ORDERS_DB_URL у двух систем — одна база
                for f in x.get("files", []):
                    me = sys_of(rname, f.split(":")[0])
                    if me:
                        x2 = L.infra[f"{m.group(1).lower()} db ({name})"]
                        x2["kind"] = "база данных"
                        x2["users"][me].append(f"{rname}:{f}")
                continue
            m = re.match(r"^ConnectionStrings[:_]+(\w[\w-]*)$", name, re.I)
            if m:
                for f in x.get("files", []):
                    me = sys_of(rname, f.split(":")[0])
                    if me and not A.resolve(m.group(1)):
                        x2 = L.infra[m.group(1)]
                        x2["kind"] = x2["kind"] or ("база данных" if re.search(r"db$|database|sql", m.group(1), re.I) else "ресурс по строке подключения")
                        x2["users"][me].append(f"{rname}:{f}")
        projects, res, refs = S["aspire"]
        p_sys = {}
        for var, (proj, name, relp) in projects.items():
            for d, sid in S["pkg_sys"].items():
                if sid and Path(d).name.replace(".", "_").lower() == proj.lower():
                    p_sys[var] = sid
        for a, b in refs:
            sa_, sb = p_sys.get(a), p_sys.get(b)
            if sa_ and sb:
                L.edge(sa_, sb, "call", "зависимость при запуске (Aspire)", f"{rname}:{projects[a][2]}")
            elif a in res and res[a][0] in ("yarp", "reverseproxy") and sb:
                L.infra[res[a][1]]["kind"] = "шлюз"
                L.infra[res[a][1]]["users"][sb].append(f"{rname}:{projects[b][2]}")
            elif sa_ and b in res:
                kind, name, parent = res[b]
                pk = res.get(parent, ("", "", ""))[0] if parent else ""
                x2 = L.infra[name]
                x2["kind"] = "база данных" if kind == "database" or (pk or kind) in ("postgres", "sqlserver", "mysql", "mongodb", "azurecosmosdb") \
                    else ("брокер сообщений" if kind in ("rabbitmq", "kafka", "azureservicebus", "nats") else "шлюз" if kind in ("yarp",) else kind)
                x2["users"][sa_].append(f"{rname}:{projects[a][2]}")
        comp = S["compose"]
        c_sys = {}
        for name, s in comp.items():
            if s["dir"] and not s["image"]:
                c_sys[name] = S["pkg_sys"].get(s["dir"]) if r_split(A, rname) == "packages" else S["pkg_sys"].get(".")
        for name, s in comp.items():
            me = c_sys.get(name)
            if not me:
                continue
            for dep in s["depends"] + [h.split(".")[0] for h in s["env_hosts"]]:
                if c_sys.get(dep) and c_sys[dep] != me:
                    L.edge(me, c_sys[dep], "call", "зависимость при запуске (compose)", f"{rname}:{s['file']}")
                elif dep in comp and comp[dep]["image"] and INFRA_IMAGES.search(comp[dep]["image"]):
                    kind = "база данных" if DB_IMAGES.search(comp[dep]["image"]) else comp[dep]["image"].split(":")[0]
                    L.infra[f"{dep} ({comp[dep]['image'].split(':')[0]})"]["kind"] = kind
                    if f"{rname}:{s['file']}" not in L.infra[f"{dep} ({comp[dep]['image'].split(':')[0]})"]["users"][me]:
                        L.infra[f"{dep} ({comp[dep]['image'].split(':')[0]})"]["users"][me].append(f"{rname}:{s['file']}")


def r_split(A, rname):
    return next((r.get("split_used", r.get("split")) for r in A.data["repos"] if r["name"] == rname), "repo")


# ---------------------------------------------------------------- связи из документов

def link_docs(A, docs):
    """→ (doc_edges [{from, to, kind, what, source}], unmapped {метка: [source]})"""
    out, unmapped = [], defaultdict(list)
    for d in docs:
        if d["kind"] == "asyncapi":
            owner = A.resolve(d["title"])
            for ch, op in d["asyncapi"]:
                out.append({"from": owner if op == "send" else None, "to": owner if op == "receive" else None, "kind": "event",
                            "what": ch, "source": d["file"], "channel": ch, "op": op})
            if not owner:
                unmapped[d["title"]].append(d["file"])
            continue
        for la, lb, txt, kind, n, ia, ib in d["edges"]:
            sa_, sb = A.resolve(la) or A.resolve(ia), A.resolve(lb) or A.resolve(ib)
            src = f"{d['file']}:{n}"
            for lab, s in ((la, sa_), (lb, sb)):
                if not s and src not in unmapped[lab]:
                    unmapped[lab].append(src)
            if sa_ and sb and sa_ != sb:
                out.append({"from": sa_, "to": sb, "kind": kind, "what": txt, "source": src})
    # AsyncAPI: отправитель и получатель одного канала — связь
    by_ch = defaultdict(lambda: {"send": set(), "receive": set(), "src": []})
    for e in [x for x in out if x.get("channel")]:
        c = by_ch[e["channel"]]
        if e["from"]:
            c["send"].add(e["from"])
        if e["to"]:
            c["receive"].add(e["to"])
        c["src"].append(e["source"])
    out = [x for x in out if not x.get("channel")]
    for ch, c in by_ch.items():
        for a in c["send"]:
            for b in c["receive"]:
                if a != b:
                    out.append({"from": a, "to": b, "kind": "event", "what": ch, "source": c["src"][0]})
        if c["send"] and not c["receive"]:
            out.append({"from": next(iter(c["send"])), "to": None, "kind": "event", "what": ch, "source": c["src"][0]})
    for cl in A.data.get("claims", []):
        fa, tb = A.resolve(cl["from"]), A.resolve(cl["to"])
        if fa and tb:
            out.append({"from": fa, "to": tb, "kind": cl["kind"], "what": cl["what"], "source": cl["source"], "claim": cl["id"]})
    # метки, которые потом сопоставили через алиасы, уже не «несопоставлены»
    unmapped = {k: v for k, v in unmapped.items() if not A.resolve(k) and len(norm(k)) >= 2}
    return out, unmapped


# ---------------------------------------------------------------- сверка

def read_decisions(path):
    """RECONCILE.md → {key: {"check": что проверено, "decision": решение}}"""
    dec = {}
    if not path.is_file():
        return dec
    key = None
    for ln in path.read_text(encoding="utf-8").split("\n"):
        m = re.search(r"<!-- key: (.+?) -->", ln)
        if m:
            key = m.group(1)
            dec.setdefault(key, {"check": "", "decision": ""})
            continue
        if not key:
            continue
        m = re.match(r"^\s+- (?:\*\*)?Проверка:(?:\*\*)?\s*(.*)$", ln)
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


def fields_of(defs):
    out = set()
    for d in defs:
        out |= {f[0].lower() for f in d.get("fields", [])}
    return out


def co_mentions(A, docs):
    """пары систем, упомянутых в одном абзаце документа: связь описана словами, хоть и не на схеме"""
    pairs = defaultdict(list)
    for d in docs:
        if d["kind"] != "doc":
            continue
        line = 1
        for para in re.split(r"\n\s*\n", d["text"]):
            ms = mentions(A, para)
            for a in ms:
                for b in ms:
                    if a != b:
                        pairs[(a, b)].append(f"{d['file']}:{line}")
            line += para.count("\n") + 2
    return pairs


def reconcile_items(A, L, doc_edges, unmapped, have_docs, loose=None):
    items = []   # (группа, key, заголовок, [строки])

    def add(group, key, title, lines):
        items.append((group, key, title, lines))
    code_pairs = defaultdict(list)
    for (a, b, k), e in L.edges.items():
        code_pairs[(a, b)].append((k, e))
    doc_pairs = defaultdict(list)
    for e in doc_edges:
        if e["from"] and e["to"]:
            doc_pairs[(e["from"], e["to"])].append(e)
    live = A.systems()
    loose = loose or {}
    for (a, b), es in doc_pairs.items():
        if (a, b) in code_pairs:
            continue
        if not live.get(a, {}).get("repo"):
            continue   # у вызывающей стороны нет кода в ландшафте — по коду не проверить; связь видна в landscape.md
        src = "; ".join(sorted({x["source"] for x in es})[:3])
        what = "; ".join(sorted({x["what"] for x in es if x["what"]})[:3]) or "без подписи"
        rev = (b, a) in code_pairs
        both_code = live.get(a, {}).get("repo") and live.get(b, {}).get("repo")
        add("Документ без кода", f"doc-only:{a}→{b}", f"{a} → {b}: «{what}»",
            [f"- В документе: {src}",
             ("- В коде есть только обратное направление: " + ", ".join(sorted({w for k, e in code_pairs[(b, a)] for w in e['what']})[:3]))
             if rev else ("- В коде связи не найдено" if both_code else
                          f"- В коде `{a}` обращения к `{b}` не найдено (у `{b}` нет репозитория — искал по алиасам и адресам; проверь клиент или SDK)")])
    if have_docs:
        for (a, b), ks in code_pairs.items():
            if (a, b) in doc_pairs or (a, b) in loose:
                continue
            whats = sorted({w for k, e in ks for w in e["what"]})
            evs = [x for k, e in ks for x in e["evidence"]][:3]
            add("Код без документа", f"code-only:{a}→{b}", f"{a} → {b}: {', '.join(whats[:4])}" + (f" … ещё {len(whats) - 4}" if len(whats) > 4 else ""),
                [f"- В коде: {'; '.join(evs)}", "- В документах связи нет (ни на схемах, ни в записанных утверждениях)"])
    for name, ev in L.events.items():
        if ev["pub"] and not ev["sub"]:
            add("События без подписчиков в ландшафте", f"no-sub:{name}", f"`{name}` публикует {', '.join(ev['pub'])}",
                [f"- Публикация: {ev['pub'][next(iter(ev['pub']))][0]}", "- Подписчиков среди систем ландшафта нет: внешний потребитель, система вне ландшафта или мёртвое событие"])
        if ev["sub"] and not ev["pub"]:
            add("Подписки без издателя в ландшафте", f"no-pub:{name}", f"`{name}` слушает {', '.join(ev['sub'])}",
                [f"- Подписка: {ev['sub'][next(iter(ev['sub']))][0]}", "- Издателя среди систем ландшафта нет: система вне ландшафта, другое имя события или мёртвая подписка"])
        for p in ev["pub"]:
            pf = fields_of(ev["defs"].get(p, []))
            for s in ev["sub"]:
                sf = fields_of(ev["defs"].get(s, []))
                # подписчик читает часть полей — норма (contracts.md); ждёт поле, которого издатель не шлёт, — расхождение
                if pf and sf and sf - pf:
                    add("Подписчик ждёт поля, которых издатель не шлёт", f"fields:{name}:{p}→{s}", f"`{name}`: {p} → {s}",
                        [f"- Есть только у подписчика: {', '.join(sorted(sf - pf))}",
                         f"- Определения: {ev['defs'][p][0]['file']}:{ev['defs'][p][0]['line']}; {ev['defs'][s][0]['file']}:{ev['defs'][s][0]['line']}"])
    for name, x in L.infra.items():
        if x["kind"] == "база данных" and len(x["users"]) > 1:
            add("Общие базы данных", f"shared-db:{name}", f"{name}: {', '.join(sorted(x['users']))}",
                [f"- {s}: {v[0]}" for s, v in sorted(x["users"].items())] +
                ["- Две системы в одной базе: схема меняется только вместе, «чужие» таблицы читаются в обход контракта"])
    for e in doc_edges:
        if e["kind"] == "event" and e["from"] and not e["to"] and e["what"] not in L.events:
            add("Документ без кода", f"doc-event:{e['what']}", f"событие `{e['what']}` ({e['from']})",
                [f"- В документе: {e['source']}", "- В коде публикации и подписки нет: ещё не сделано, удалено или другое имя"])
    for lab, srcs in unmapped.items():
        add("Узлы документов без системы", f"unmapped:{norm(lab)}", f"«{lab}»",
            [f"- Где: {'; '.join(srcs[:3])}", "- Это система ландшафта под другим именем (`system … --alias`), внешняя система (`system … --external`) или не система"])
    for host, users in L.hosts.items():
        add("Адреса вне ландшафта", f"host:{host}", f"`{host}` из {', '.join(sorted(users))}",
            [f"- Где: {'; '.join(v[0] for v in users.values())}", "- Внешний сервис (`system <id> --external --alias " + host + "`) или не связь (ссылка в комментарии, пример)"])
    return items


def write_reconcile(A, items):
    old = read_decisions(A.reconcile)
    groups = OrderedDict()
    for g, key, title, lines in items:
        groups.setdefault(g, []).append((key, title, lines))
    out = [tmpl("RECONCILE.head.md").rstrip(), ""]
    n = 0
    for g, its in groups.items():
        out += [f"## {g}", ""]
        for key, title, lines in its:
            n += 1
            o = old.get(key, {})
            dec, chk = o.get("decision", ""), o.get("check", "")
            out += [f"- [{'x' if dec else ' '}] R-{n:02d} {title} <!-- key: {key} -->"] + [f"  {ln}" for ln in lines]
            out.append(f"  - **Проверка:** {chk or FILL + ': что открыл и что увидел — путь:строка в коде, документ:строка -->'}")
            out.append(f"  - **Решение:** {dec or FILL + ': вопрос Q-… | ок: почему | не связь: почему -->'}")
        out.append("")
    if not items:
        out.append("Расхождений нет.")
    A.reconcile.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")
    return n, sum(1 for _, k, _, _ in items if old.get(k, {}).get("decision"))


# ---------------------------------------------------------------- запись слоя

def sys_line(sid, s):
    bits = [f"`{sid}`", s.get("title", sid)]
    return bits


def short_ev(ev):
    """«repo:файл:строка (отправка: 33) → repo:файл:строка (обработчик …)» → без пояснений в скобках"""
    return re.sub(r"\s*\([^)]*\)", "", ev)


def fit(lines, budget, tail):
    out, size = [], 0
    for i, ln in enumerate(lines):
        if size + len(ln) + 1 > budget:
            out.append(tail.format(n=len(lines) - i))
            break
        out.append(ln)
        size += len(ln) + 1
    return out


def card_body(A, L, sid, s, scans, docs, doc_edges, items, qs):
    lines = []
    if s.get("external"):
        lines.append(f"- Внешняя система (нет репозитория в ландшафте). Алиасы: {', '.join(s.get('aliases', [])) or '—'}")
    else:
        rp = next((r for r in A.data["repos"] if r["name"] == s.get("repo")), None)
        lines.append(f"- Репозиторий: `{s.get('repo')}` ({rp['path'] if rp else '?'})" + (f", пакет `{s['package']}`" if s.get("package") not in (".", "") else ""))
        S = scans.get(s.get("repo"))
        if S:
            pk = next((p for p in S["inv"].get("stack", []) if p["dir"] == s.get("package")), None) or next(
                (p for p in S["inv"].get("stack", []) if p["dir"] == "."), None)
            if pk and pk.get("frameworks"):
                lines.append(f"- Стек: {', '.join(pk['frameworks'][:6])}")
            if S["plan"]:
                lines.append(f"- Слой sa-scan: есть, возможностей {len(S['plan'].get('capabilities', []))}, "
                             f"открытых вопросов {sum(1 for q in S['questions'] if sa.effective_status(q) == 'открыт')}")
            else:
                lines.append("- Слой sa-scan: нет")
        if s.get("aliases"):
            lines.append(f"- Другие имена: {', '.join(s['aliases'])}")
    lines.append(f"- Назначение: {s['purpose']} ({s.get('purpose_src') or 'источник не указан'})" if s.get("purpose")
                 else "- Назначение: ⚠ не задано — `landscape.py system … --purpose … --source …`")
    lines.append(f"- Владелец: {s['owner']} ({s.get('owner_src') or 'источник не указан'})" if s.get("owner")
                 else "- Владелец: ⚠ не задан")
    # зависимость: вызывающий зависит от вызываемого, подписчик — от издателя
    dependents, deps = [], []
    for (a, b, k), e in L.edges.items():
        provider, consumer = (a, b) if k == "event" else (b, a)
        w = list(e["what"])
        txt = f"{', '.join(w[:5])}" + (f" … ещё {len(w) - 5}" if len(w) > 5 else "") + f" — {short_ev(e['evidence'][0]) if e['evidence'] else ''}"
        if provider == sid:
            dependents.append((consumer, (f"слушает её событие: " if k == "event" else "вызывает её: ") + txt))
        if consumer == sid:
            deps.append((provider, (f"слушает его событие: " if k == "event" else "вызывает: ") + txt))
    lines.append("")
    lines.append("**Кто зависит от неё** (меняешь её вход или событие — эти сломаются первыми, выкатываются отдельно):")
    lines += [f"- `{o}` {t}" for o, t in sorted(dependents)] or ["- никто в ландшафте"]
    lines.append("")
    lines.append("**От кого зависит она:**")
    lines += [f"- `{o}` {t}" for o, t in sorted(deps)] or ["- ни от кого в ландшафте"]
    pub = [(n, ev) for n, ev in L.events.items() if sid in ev["pub"]]
    if pub:
        lines.append("")
        lines.append("**Публикует события:**")
        for n, ev in pub:
            subs = ", ".join(sorted(ev["sub"])) or "подписчиков в ландшафте нет"
            f = ", ".join(x[0] for x in (ev["defs"].get(sid) or [{}])[0].get("fields", [])[:10]) if ev["defs"].get(sid) else "тип не найден — смотри место публикации"
            lines.append(f"- `{n}` → {subs}; поля: {f}")
    inf = [(n, x) for n, x in L.infra.items() if sid in x["users"]]
    if inf:
        lines.append("")
        lines.append("**Общая инфраструктура и данные:**")
        for n, x in inf:
            others = sorted(set(x["users"]) - {sid})
            lines.append(f"- {n}" + (f" — также {', '.join(others)}" if others else ""))
    ext = [h for h, u in L.hosts.items() if sid in u]
    if ext:
        lines.append("")
        lines.append("**Внешние адреса:** " + ", ".join(f"`{h}`" for h in ext[:10]))
    dd = [d for d in docs if d["kind"] == "doc" and sid in d.get("mentions", set())]
    if dd:
        lines.append("")
        lines.append("**О системе в документах:**")
        lines += [f"- {d['file']} — {d['title']}" + (" (ADR)" if d["adr"] else "") for d in dd[:MAX_LINES]]
        if len(dd) > MAX_LINES:
            lines.append(f"- … ещё {len(dd) - MAX_LINES} — landscape.md, «Документы»")
    mine = [(k, t) for g, k, t, _ in items if re.search(rf"(?<![\w-]){re.escape(sid)}(?![\w-])", t)]
    sq = [q for q in qs if sid in (q["fields"].get("Затрагивает") or "")]
    if mine or sq:
        lines.append("")
        lines.append("**Расхождения и вопросы:**")
        lines += [f"- {t} (RECONCILE.md)" for k, t in mine[:MAX_LINES]]
        lines += [f"- {q['id']} [{q['fields'].get('Важность', '')}] {q['title']}" for q in sq[:MAX_LINES]]
    return "\n".join(fit(lines, CARD_BUDGET, "- … ещё {n} строк — landscape.md и contracts.md"))


def write_cards(A, L, scans, docs, doc_edges, items, qs):
    A.systems_dir.mkdir(exist_ok=True)
    live = A.systems()
    for sid, s in live.items():
        p = A.systems_dir / f"{sid}.md"
        head = (f"# {s.get('title', sid)} (`{sid}`)\n\nКарточка системы в ландшафте: кто от неё зависит и от кого зависит она. "
                f"Блок `sa:auto` пересобирает `landscape.py build`; заметки пиши под ним.\n")
        body = card_body(A, L, sid, s, scans, docs, doc_edges, items, qs)
        if p.is_file():
            t = p.read_text(encoding="utf-8")
            if C.AUTO_RX.search(t):
                t = C.AUTO_RX.sub(lambda m: C.auto("card", body), t, count=1)
                p.write_text(t, encoding="utf-8")
                continue
        p.write_text(head + "\n" + C.auto("card", body) + "\n\n## Заметки\n\n" +
                     "- **Как с ней работать:** " + FILL + ": для изменений в соседних системах — что важно знать (SLA, окна выкатки, "
                     "кто согласует контракт), со ссылкой на источник; не знаешь — «не известно» и вопрос -->\n", encoding="utf-8")
    for p in A.systems_dir.glob("*.md"):
        if p.stem not in live:
            t = p.read_text(encoding="utf-8")
            if "⚠ системы больше нет" not in t:
                p.write_text("> ⚠ системы больше нет в ландшафте (исключена, слита или переименована) — удали файл, если заметки не нужны\n\n" + t,
                             encoding="utf-8")


def mermaid(A, L, doc_edges):
    live = A.systems()
    ids = {sid: f"s{i}" for i, sid in enumerate(live)}
    out = ["```mermaid", "flowchart LR"]
    for sid, s in live.items():
        shape = f"{ids[sid]}[[\"{s.get('title', sid)}\"]]" if s.get("external") else f"{ids[sid]}[\"{s.get('title', sid)}\"]"
        out.append(f"  {shape}")
    pairs = OrderedDict()
    for (a, b, k), e in L.edges.items():
        if a in ids and b in ids:
            pairs.setdefault((a, b), set()).add(k)
    for (a, b), ks in pairs.items():
        arrow = "-.->" if ks == {"event"} else "-->"
        out.append(f"  {ids[a]} {arrow} {ids[b]}")
    for e in doc_edges:
        if e["from"] in ids and e["to"] in ids and (e["from"], e["to"]) not in pairs:
            out.append(f"  {ids[e['from']]} -. \"только в документе\" .-> {ids[e['to']]}")
            pairs[(e["from"], e["to"])] = {"doc"}
    out.append("```")
    return "\n".join(out)


def write_landscape(A, L, scans, docs, doc_edges, items, loose):
    live = A.systems()
    rows = ["| Система | Назначение | Владелец | Где | Входящих / исходящих |", "|---|---|---|---|---|"]
    for sid, s in live.items():
        where = "внешняя" if s.get("external") else f"{s.get('repo')}" + (f" · {s['package']}" if s.get("package") not in (".", "") else "")
        nin = len({a for (a, b, k) in L.edges if b == sid})
        nout = len({b for (a, b, k) in L.edges if a == sid})
        rows.append(f"| [`{sid}`](systems/{sid}.md) {s.get('title', '')} | {s.get('purpose') or '⚠'} | {s.get('owner') or '⚠'} | {where} | {nin} / {nout} |")
    excl = [(k, v) for k, v in A.data["systems"].items() if v.get("excluded") or v.get("merged_into")]
    if excl:
        rows.append("")
        rows.append("Не системы: " + "; ".join(f"`{k}` — " + (f"слита в {v['merged_into']}" if v.get("merged_into") else v["excluded"]) for k, v in excl))
    groups = [("Системы", [("Список", "systems", "\n".join(rows), "")]),
              ("Схема", [("Кто от кого зависит", "diagram", mermaid(A, L, doc_edges) +
                          "\n\nСплошная стрелка — вызов, пунктир — только события; «только в документе» — связь есть на схеме, но не в коде.", "")])]
    pairs = OrderedDict()
    for (a, b, k), e in L.edges.items():
        p = pairs.setdefault((a, b), {"kinds": OrderedDict(), "evidence": []})
        p["kinds"].setdefault(k, OrderedDict()).update(e["what"])
        p["evidence"] += e["evidence"][:2]
    dsrc = defaultdict(list)
    for e in doc_edges:
        if e["from"] and e["to"]:
            dsrc[(e["from"], e["to"])].append(e["source"])
    secs = []
    for (a, b), p in pairs.items():
        body = [f"- {KINDS[k]}: {', '.join(list(w)[:6])}" + (f" … ещё {len(w) - 6}" if len(w) > 6 else "") for k, w in p["kinds"].items()]
        body.append("- В коде: " + "; ".join(p["evidence"][:3]))
        body.append("- В документах: " + ("; ".join(sorted(set(dsrc[(a, b)]))[:3]) if dsrc.get((a, b)) else
                                          ("упомянуты вместе: " + "; ".join(sorted(set(loose[(a, b)]))[:2])) if loose.get((a, b)) else "нет"))
        secs.append((f"{a} → {b}", f"link:{a}→{b}", "\n".join(body),
                     "- **Зачем и как:** " + FILL + ": зачем A обращается к B, синхронно или нет, что у A при отказе B; "
                     "источник — integrations.md слоя sa-scan, документ или код (путь:строка) -->"))
    for (a, b), srcs in dsrc.items():
        if (a, b) not in pairs:
            secs.append((f"{a} → {b} (только в документе)", f"doclink:{a}→{b}", "- В коде: не найдено\n- В документах: " + "; ".join(sorted(set(srcs))[:3]),
                         "- **Зачем и как:** " + FILL + ": что говорит документ; связь — в RECONCILE.md -->"))
    groups.append(("Связи", secs))
    infra = []
    for n, x in L.infra.items():
        infra.append(f"- {n} ({x['kind'] or 'ресурс'}): " + ", ".join(sorted(x["users"])) + (" — ⚠ общая" if len(x["users"]) > 1 and x["kind"] == "база данных" else ""))
    groups.append(("Общая инфраструктура", [("Ресурсы", "infra", "\n".join(infra) or "- не найдено", "")]))
    drows = []
    for d in docs:
        ms = ", ".join(sorted(d.get("mentions", set()))[:6]) if d["kind"] == "doc" else "AsyncAPI"
        drows.append(f"- {d['file']} — {d['title']}" + (" · ADR" if d.get("adr") else "") +
                     (f" · схем: {len(d['edges'])} связей" if d.get("edges") else "") + (f" · о системах: {ms}" if ms else ""))
    groups.append(("Документы", [("Что прочитано", "docs", "\n".join(drows) or "- документы не добавлены (`landscape.py add-docs`)", "")]))
    adrs = [d for d in docs if d.get("adr")]
    if adrs:
        groups.append(("Архитектурные решения", [("ADR", "adr", "\n".join(f"- {d['file']} — {d['title']}" for d in adrs) +
                                                  "\n- Проверяемые принципы из них собирает ar-rules", "")]))
    C.merge_doc(A.landscape_md, tmpl("landscape.head.md"), groups)


def write_contracts(A, L):
    groups = []
    ev_secs = []
    for name, ev in L.events.items():
        body = ["- Владелец (публикует): " + (", ".join(f"`{s}`" for s in ev["pub"]) or "нет в ландшафте")]
        for s, locs in ev["pub"].items():
            body += sub(locs[:2])
        body.append("- Подписаны: " + (", ".join(f"`{s}`" for s in ev["sub"]) or "нет в ландшафте"))
        for s, locs in ev["sub"].items():
            body += sub(locs[:2])
        for s, ds in ev["defs"].items():
            body.append(f"- Поля у `{s}`: " + (", ".join(f"{f[0]} {f[1]}" for f in ds[0].get("fields", [])[:12]) or "не разобраны") + f" ({ds[0]['file']}:{ds[0]['line']})")
        ev_secs.append((f"`event:{name}`", f"event:{name}", "\n".join(body), ""))
    groups.append(("События между системами", ev_secs))
    h_secs = []
    for (o, pre), h in L.http.items():
        if not h["consumers"]:
            continue
        body = [f"- Владелец: `{o}`", "- Входы: " + ", ".join(f"`{x}`" for x in h["entries"][:8]) + (f" … ещё {len(h['entries']) - 8}" if len(h["entries"]) > 8 else "")]
        for s, locs in h["consumers"].items():
            body.append(f"- Потребитель `{s}`:")
            body += sub(locs, 4)
        h_secs.append((f"`http:{o} /{pre}`", f"http:{o}:{pre}", "\n".join(body), ""))
    groups.append(("HTTP-входы с потребителями в других системах", h_secs))
    g_secs = []
    for (o, svc), g in L.grpc.items():
        if not g["consumers"]:
            continue
        body = [f"- Владелец: `{o}`", "- Методы: " + ", ".join(g["rpcs"][:10])] + [f"- Потребитель `{s}`: " + "; ".join(v[:3]) for s, v in g["consumers"].items()]
        g_secs.append((f"`grpc:{o} {svc}`", f"grpc:{o}:{svc}", "\n".join(body), ""))
    groups.append(("gRPC-сервисы с потребителями в других системах", g_secs))
    C.merge_doc(A.contracts, tmpl("contracts.head.md"), groups)
    return len(ev_secs), len(h_secs), len(g_secs)


def write_json(A, L, doc_edges):
    js = OrderedDict([
        ("built", A.data["built"]),
        ("systems", OrderedDict((k, {kk: v[kk] for kk in ("title", "repo", "package", "aliases", "purpose", "owner", "external")})
                                for k, v in A.systems().items())),
        ("edges", [OrderedDict([("from", a), ("to", b), ("kind", k), ("what", list(e["what"])), ("evidence", e["evidence"][:5])])
                   for (a, b, k), e in L.edges.items()]),
        ("events", OrderedDict((n, {"publishers": list(ev["pub"]), "subscribers": list(ev["sub"]),
                                    "fields": {s: [f[0] for f in ds[0].get("fields", [])] for s, ds in ev["defs"].items()}})
                               for n, ev in L.events.items())),
        ("http", [OrderedDict([("owner", o), ("prefix", "/" + p), ("entries", h["entries"]), ("consumers", {s: v[:5] for s, v in h["consumers"].items()})])
                  for (o, p), h in L.http.items() if h["consumers"]]),
        ("grpc", [OrderedDict([("owner", o), ("service", s), ("consumers", {c: v[:5] for c, v in g["consumers"].items()})])
                  for (o, s), g in L.grpc.items() if g["consumers"]]),
        ("infra", OrderedDict((n, {"kind": x["kind"], "users": sorted(x["users"])}) for n, x in L.infra.items())),
        ("doc_edges", doc_edges),
    ])
    A.landscape_json.write_text(json.dumps(js, ensure_ascii=False, indent=1, default=list) + "\n", encoding="utf-8")


def cmd_build(a):
    A = Arch(a.arch)
    if not A.data["repos"] and not A.data["docs"]:
        sa.die("нет ни репозиториев, ни документов — landscape.py add-repo / add-docs")
    print("Сканирую репозитории…")
    scans = OrderedDict()
    for r in A.data["repos"]:
        S = scan_repo(A, r)
        if not S:
            continue
        S["pkg_sys"] = assign_systems(A, r, S)
        r["head"] = S["head"]
        r["built"] = now()
        scans[r["name"]] = S
    L = Links()
    link_code(A, scans, L)
    print("Разбираю документы…")
    docs = scan_docs(A)
    A.data["docs_hash"] = docs_hash(A)
    for d in docs:
        if d["kind"] == "doc":
            d["mentions"] = mentions(A, d["text"])
    doc_edges, unmapped = link_docs(A, docs)
    loose = co_mentions(A, docs)
    items = reconcile_items(A, L, doc_edges, unmapped, bool(docs), loose)
    A.data["built"] = now()
    A.save()
    qs = sa.parse_questions(A.questions.read_text(encoding="utf-8")) if A.questions.is_file() else []
    n_items, kept = write_reconcile(A, items)
    write_cards(A, L, scans, docs, doc_edges, items, qs)
    write_landscape(A, L, scans, docs, doc_edges, items, loose)
    ne, nh, ng = write_contracts(A, L)
    write_json(A, L, [{k: v for k, v in e.items()} for e in doc_edges])
    live = A.systems()
    print(f"✓ систем {len(live)} (внешних {sum(1 for s in live.values() if s.get('external'))}), связей в коде {len(L.edges)}, "
          f"событий между системами {ne}, HTTP с потребителями {nh}, gRPC {ng}")
    print(f"✓ документов {len(docs)}, связей из документов {len(doc_edges)}, ADR {sum(1 for d in docs if d.get('adr'))}")
    print(f"✓ RECONCILE.md: пунктов {n_items}, решения сохранены у {kept}")
    for r in A.data["repos"]:
        if r["name"] in scans:
            ss = [k for k, v in live.items() if v.get("repo") == r["name"]]
            print(f"  {r['name']}: split={r.get('split_used')} → {', '.join(ss) or '—'}")
    nofill = [k for k, s in live.items() if not s.get("purpose")]
    if nofill:
        print(f"  назначение не задано у {len(nofill)}: {', '.join(nofill[:8])}" + (" …" if len(nofill) > 8 else ""))
    print(f"Дальше: проверь список систем (SKILL.md, шаг 4), затем решения в RECONCILE.md и «заполнить» в landscape.md; "
          f"landscape.py check {a.arch}")
    return 0


# ---------------------------------------------------------------- system / claim / q

def cmd_system(a):
    A = Arch(a.arch)
    sysmap = A.data["systems"]
    sid = a.id
    if sid not in sysmap:
        r = A.resolve(sid)
        if r and not a.external:
            sid = r
        elif a.external or a.title:
            if not sa.ID_RX.match(sid):
                sa.die(f"id — kebab-case: {sa.kebab(sid)}")
            sysmap[sid] = new_system(a.title or sid, "", "")
            sysmap[sid]["external"] = bool(a.external)
            print(f"+ система {sid}" + (" (внешняя)" if a.external else " (без репозитория)"))
        else:
            sa.die(f"нет системы {sid}; есть: {', '.join(A.systems())}. Новую внешнюю — с --external, без репозитория — с --title")
    s = sysmap[sid]
    if a.rename:
        if not sa.ID_RX.match(a.rename) or a.rename in sysmap:
            sa.die(f"плохой или занятый id: {a.rename}")
        sysmap[a.rename] = s
        del sysmap[sid]
        for v in sysmap.values():
            if v.get("merged_into") == sid:
                v["merged_into"] = a.rename
        for cl in A.data.get("claims", []):
            cl["from"] = a.rename if cl["from"] == sid else cl["from"]
            cl["to"] = a.rename if cl["to"] == sid else cl["to"]
        add_alias(s, sid)
        sid = a.rename
        print(f"✓ переименована в {sid}; файл systems/{a.id}.md пересоберётся с новым именем")
    for k in ("title", "purpose", "owner"):
        v = getattr(a, k)
        if v is not None:
            s[k] = v.strip()
    if (a.purpose or a.owner) and not a.source:
        sa.die("--purpose и --owner — только с --source: документ (путь:строка), «код», «человек» или «не известно, Q-…»")
    if a.source:
        if a.purpose is not None:
            s["purpose_src"] = a.source
        if a.owner is not None:
            s["owner_src"] = a.source
    for al in a.alias or []:
        other = A.resolve(al)
        if other and other != sid:
            sa.die(f"алиас «{al}» уже ведёт к {other}")
        add_alias(s, al)
    if a.external:
        s["external"] = True
    if a.exclude is not None:
        s["excluded"] = a.exclude or "не система"
    if a.include:
        s["excluded"] = ""
        s["merged_into"] = ""
    if a.merge_into:
        if a.merge_into not in sysmap:
            sa.die(f"нет системы {a.merge_into}")
        s["merged_into"] = a.merge_into
        for al in [sid, s.get("title", "")] + s.get("aliases", []):
            add_alias(sysmap[a.merge_into], al)
    A.save()
    print(f"✓ {sid}: " + ", ".join(f"{k}={s[k]!s}" for k in ("title", "purpose", "owner", "aliases", "external", "excluded", "merged_into") if s.get(k)))
    print(f"Пересобери: landscape.py build {a.arch}")
    return 0


def cmd_claim(a):
    A = Arch(a.arch)
    fa, tb = A.resolve(a.from_), A.resolve(a.to)
    if not fa or not tb:
        sa.die(f"не нашёл систему: {a.from_ if not fa else a.to}. Есть: {', '.join(A.systems())}. Внешнюю заведи: system <id> --external")
    if a.kind not in KINDS:
        sa.die("--kind: call | event | data")
    if not REF_RX.search(a.source):
        sa.die("--source — где это сказано: путь:строка документа или ссылка")
    cl = A.data.setdefault("claims", [])
    for x in cl:
        if (x["from"], x["to"], x["kind"], x["what"]) == (fa, tb, a.kind, a.what):
            print(f"уже записано: {x['id']}")
            return 0
    cid = f"D-{len(cl) + 1:02d}"
    cl.append(OrderedDict([("id", cid), ("from", fa), ("to", tb), ("kind", a.kind), ("what", a.what), ("source", a.source)]))
    A.save()
    print(f"✓ {cid}: {fa} → {tb} ({KINDS[a.kind]}: {a.what}) — {a.source}")
    return 0


def cmd_q(a):
    A = Arch(a.arch)
    if a.category not in sa.CATEGORIES:
        sa.die("категория — одна из: " + "; ".join(sa.CATEGORIES))
    if a.importance not in sa.IMPORTANCE:
        sa.die("важность: блокирует | уточняет")
    if not a.title.strip().rstrip("»\"') ").endswith("?"):
        sa.die("вопрос — одной фразой с «?»")
    text = A.questions.read_text(encoding="utf-8") if A.questions.is_file() else tmpl("QUESTIONS.md")
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


# ---------------------------------------------------------------- show

def cmd_show(a):
    A = Arch(a.arch)
    if a.system:
        sid = A.resolve(a.system)
        if not sid:
            sa.die(f"нет системы {a.system}; есть: {', '.join(A.systems())}")
        p = A.systems_dir / f"{sid}.md"
        if not p.is_file():
            sa.die(f"нет {p} — landscape.py build {a.arch}")
        print(p.read_text(encoding="utf-8"))
        return 0
    want = (a.event or a.entry or "").lower()
    if not want:
        sa.die("укажи --system, --event или --entry")
    shown = 0
    for path in (A.contracts,):
        for h, body in C.sections(path):
            hl = h.lower()
            if (a.event and hl.startswith("`event:") and want in hl) or (a.entry and not hl.startswith("`event:") and want in hl):
                print(body.rstrip() + "\n")
                shown += 1
    if not shown:
        print("ничего не найдено — у этого входа или события нет потребителей в других системах (или пересобери слой)")
    return 0


# ---------------------------------------------------------------- check / status

def cmd_check(a):
    A = Arch(a.arch)
    err, warn = [], []
    if not A.data.get("built"):
        sa.die(f"слой не собран — landscape.py build {a.arch}")
    if A.data.get("modified", "") > A.data["built"]:
        warn.append("настройки систем менялись после сборки — landscape.py build")
    live = A.systems()
    for sid, s in live.items():
        if not s.get("purpose"):
            err.append(f"{sid}: не задано назначение — `system {sid} --purpose … --source …` (из документа, кода или «не известно, Q-…»)")
        elif not s.get("purpose_src"):
            err.append(f"{sid}: у назначения нет источника (--source)")
        if not s.get("owner") and not s.get("external"):
            warn.append(f"{sid}: не задан владелец — из документа или вопрос «кто владелец» (`--owner \"не известно\" --source Q-…`)")
    qs = sa.parse_questions(A.questions.read_text(encoding="utf-8")) if A.questions.is_file() else []
    qids = {q["id"] for q in qs}
    for q in qs:
        for f in ("Что видно", "Кто ответит", "Допущение"):
            if not (q["fields"].get(f) or "").strip():
                err.append(f"QUESTIONS.md {q['id']}: пусто поле «{f}»")
    for sid, s in live.items():
        for k in ("purpose_src", "owner_src"):
            for qid in sa.Q_RX.findall(s.get(k, "")):
                if qid not in qids:
                    err.append(f"{sid}: ссылка на {qid}, а такого вопроса в QUESTIONS.md нет")
    if A.reconcile.is_file():
        key = None
        for ln in A.reconcile.read_text(encoding="utf-8").split("\n"):
            m = re.search(r"(R-\d+) .*<!-- key: (.+?) -->", ln)
            if m:
                key = m.group(1)
                continue
            m = re.match(r"^\s+- (?:\*\*)?Проверка:(?:\*\*)?\s*(.*)$", ln)
            if m and key:
                v = m.group(1).strip()
                if not v or v.startswith(FILL):
                    err.append(f"RECONCILE.md {key}: не заполнена «Проверка» — сначала открой места из пункта и запиши, что увидел")
                elif not REF_RX.search(v) and not (SEARCH_RX.search(v) and any(
                        re.search(rf"(?<![\w-]){re.escape(x)}(?![\w-])", v) for r in A.data["repos"] for x in (r["name"],) + tuple(A.systems()))):
                    err.append(f"RECONCILE.md {key}: в «Проверке» нет ссылки (путь:строка, документ или «поиск X в <репозиторий> — 0»): «{squash(v, 50)}»")
                continue
            m = re.match(r"^\s+- \*\*Решение:\*\*\s*(.*)$", ln)
            if m and key:
                v = m.group(1).strip()
                d = DECISION_RX.match(v)
                if not v or v.startswith(FILL):
                    err.append(f"RECONCILE.md {key}: нет решения")
                elif not d:
                    err.append(f"RECONCILE.md {key}: решение «{squash(v, 50)}» — нужно «вопрос Q-…», «ок: почему» или «не связь: почему»")
                elif d.group(2) and d.group(2) not in qids:
                    err.append(f"RECONCILE.md {key}: {d.group(2)} нет в QUESTIONS.md")
                elif (d.group(3) or d.group(4)) and len((d.group(3) or d.group(4)).strip()) < 25:
                    err.append(f"RECONCILE.md {key}: причина короче одной конкретной фразы — что проверил и где")
                key = None
    for path in (A.landscape_md,) + tuple(sorted(A.systems_dir.glob("*.md"))):
        if not path.is_file():
            err.append(f"нет {A.rel(path)} — landscape.py build")
            continue
        t = path.read_text(encoding="utf-8")
        n = t.count(FILL)
        if n:
            (err if path == A.landscape_md else warn).append(f"{A.rel(path)}: мест «заполнить» — {n}")
        for m in re.finditer(r"^- \*\*(Зачем и как|Как с ней работать):\*\*\s*(.+)$", t, re.M):
            v = m.group(2)
            if not v.startswith(FILL) and not REF_RX.search(v) and not re.search(r"не известно|Q-\d{3}", v):
                warn.append(f"{A.rel(path)}: «{m.group(1)}» без источника (путь:строка, документ или Q-…): «{squash(v, 60)}»")
        if path.parent == A.systems_dir:
            if len(t) > CARD_BUDGET + 3000:
                warn.append(f"{A.rel(path)}: {len(t)} символов — больше бюджета карточки, заметки вынеси в landscape.md")
    if not A.guide.is_file():
        err.append("нет GUIDE.md — landscape.py init его создаёт")
    for r in A.data["repos"]:
        p = A.repo_path(r)
        if not p.is_dir():
            warn.append(f"репозиторий {r['name']}: нет папки {p}")
            continue
        head = git(p, "rev-parse", "HEAD")
        if head and r.get("head") and head != r["head"]:
            warn.append(f"репозиторий {r['name']}: код изменился после сборки ({git(p, 'rev-list', '--count', r['head'] + '..HEAD') or '?'} коммитов) — landscape.py build")
    for x in warn:
        print(f"  ! {x}")
    for x in err:
        print(f"  ✗ {x}")
    print(f"Ошибок: {len(err)}, предупреждений: {len(warn)}")
    return 1 if err else 0


def cmd_status(a):
    A = Arch(a.arch)
    print(f"Сборка: {A.data.get('built') or 'не было'}")
    for r in A.data["repos"]:
        p = A.repo_path(r)
        head = git(p, "rev-parse", "HEAD") if p.is_dir() else ""
        st = "нет папки" if not p.is_dir() else ("не собран" if not r.get("built") else
                                                  f"собран {r['built']}, не git — свежесть не проверить" if not r.get("head") else
                                                  "свежий" if head == r["head"] else f"код изменился: {git(p, 'rev-list', '--count', r['head'] + '..HEAD') or '?'} коммитов")
        print(f"- {r['name']} ({r['path']}): {st}")
    old, cur = A.data.get("docs_hash", {}), docs_hash(A)
    changed = sorted(f for f in cur if old.get(f) != cur[f])
    gone = sorted(set(old) - set(cur))
    print("- документы: " + (f"новых или изменённых {len(changed)}" + (f" ({', '.join(changed[:5])})" if changed else "") if changed else "без изменений") +
          (f", исчезло {len(gone)}" if gone else ""))
    return 0


# ---------------------------------------------------------------- link

def slice_for(A, ss, arch_ref):
    """Срез ландшафта для проекта: кто в других системах потребляет наши события, HTTP и gRPC, общие ресурсы.
    Читает sa-change (analyze): внешние потребители становятся пунктами влияния."""
    if not A.landscape_json.is_file():
        sa.die(f"нет {A.landscape_json} — landscape.py build")
    js = json.loads(A.landscape_json.read_text(encoding="utf-8"))
    sysd = js.get("systems", {})
    mine = set(ss)

    def who(s):
        x = sysd.get(s, {})
        return OrderedDict([("system", s), ("title", x.get("title", s)), ("repo", x.get("repo", "")), ("owner", x.get("owner", "")),
                            ("external", bool(x.get("external")))])

    def ev_evidence(a, b, name):
        for e in js.get("edges", []):
            if e["from"] == a and e["to"] == b and e["kind"] == "event" and name in e["what"]:
                return e["evidence"][:2]
        return []
    consumers = []
    for name, ev in js.get("events", {}).items():
        for p in ev.get("publishers", []):
            if p not in mine:
                continue
            for s in ev.get("subscribers", []):
                if s not in mine:
                    consumers.append(OrderedDict([("kind", "event"), ("what", name), ("owner", p), ("consumer", who(s)),
                                                  ("evidence", ev_evidence(p, s, name))]))
    for h in js.get("http", []):
        if h["owner"] in mine:
            for s, locs in h.get("consumers", {}).items():
                if s not in mine:
                    consumers.append(OrderedDict([("kind", "http"), ("what", h["prefix"]), ("entries", h.get("entries", [])), ("owner", h["owner"]),
                                                  ("consumer", who(s)), ("evidence", locs[:3])]))
    for g in js.get("grpc", []):
        if g["owner"] in mine:
            for s, locs in g.get("consumers", {}).items():
                if s not in mine:
                    consumers.append(OrderedDict([("kind", "grpc"), ("what", g["service"]), ("owner", g["owner"]), ("consumer", who(s)),
                                                  ("evidence", locs[:3])]))
    shared = [OrderedDict([("name", n), ("kind", x.get("kind", "")), ("ours", sorted(set(x["users"]) & mine)),
                           ("others", sorted(set(x["users"]) - mine))])
              for n, x in js.get("infra", {}).items() if set(x.get("users", [])) & mine and set(x.get("users", [])) - mine]
    return OrderedDict([("source", arch_ref), ("built", A.data.get("built", "")), ("systems", ss), ("consumers", consumers), ("shared", shared)])


LINK_START, LINK_END = "<!-- ar-scan:start -->", "<!-- ar-scan:end -->"


def cmd_link(a):
    A = Arch(a.arch)
    repo = Path(a.repo).resolve()
    r = next((x for x in A.data["repos"] if A.repo_path(x) == repo), None)
    if not r:
        sa.die(f"{repo} не добавлен в ландшафт — landscape.py add-repo {a.arch} {a.repo}")
    ss = [k for k, v in A.systems().items() if v.get("repo") == r["name"]]
    if not ss:
        sa.die("у репозитория нет систем в ландшафте — landscape.py build")
    ctx = repo / "system-context"
    ctx.mkdir(exist_ok=True)
    try:
        arch_ref = os.path.relpath(A.dir, repo).replace(os.sep, "/")
    except ValueError:
        arch_ref = A.dir.as_posix()
    parts = [f"# Ландшафт: системы этого репозитория\n\nКопия карточек из слоя архитектуры `{arch_ref}` (путь от корня репозитория) (собран {A.data['built']}). "
             f"Не правь здесь — пересобирается `landscape.py link`. Полный ландшафт — `landscape.md`, контракты между системами — `contracts.md` там же.\n"]
    for sid in ss:
        p = A.systems_dir / f"{sid}.md"
        if p.is_file():
            parts.append(re.sub(r"^# ", "## ", p.read_text(encoding="utf-8"), flags=re.M).replace("\n## Заметки", "\n### Заметки"))
    (ctx / "landscape.md").write_text("\n".join(parts), encoding="utf-8")
    (ctx / "landscape.json").write_text(json.dumps(slice_for(A, ss, arch_ref), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    block = (f"{LINK_START}\n## Архитектура за рамками проекта\n\n"
             f"Кто ещё вызывает наши входы и слушает наши события, кого вызываем мы — `system-context/landscape.md` "
             f"(копия из слоя архитектуры: `{arch_ref}`). Меняешь вход, событие или общие данные, у которых там есть потребители, — "
             f"это пункт влияния: потребитель в другой системе ломается первым и выкатывается отдельно. Чего там нет — вопрос, а не догадка.\n{LINK_END}")
    ag = repo / "AGENTS.md"
    t = ag.read_text(encoding="utf-8") if ag.is_file() else "# Инструкция для агентов\n"
    if LINK_START in t:
        t = re.sub(re.escape(LINK_START) + r"[\s\S]*?" + re.escape(LINK_END), lambda m: block, t)
    else:
        t = t.rstrip() + "\n\n" + block + "\n"
    ag.write_text(t, encoding="utf-8")
    cl = repo / "CLAUDE.md"
    if not cl.is_file():
        cl.write_text("@AGENTS.md\n", encoding="utf-8")
    print(f"✓ {repo.name}/system-context/landscape.md ({', '.join(ss)}), указатель в AGENTS.md")
    return 0


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description="Ландшафт систем: репозитории + документация → architecture/")
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("init", help="создать слой")
    p.add_argument("arch")
    p.set_defaults(fn=cmd_init)
    p = sp.add_parser("add-repo", help="добавить репозиторий системы (или монорепозиторий)")
    p.add_argument("arch")
    p.add_argument("repo")
    p.add_argument("--name")
    p.add_argument("--split", choices=["auto", "repo", "packages"], help="одна система на репозиторий или по пакетам (по умолчанию auto)")
    p.set_defaults(fn=cmd_add_repo)
    p = sp.add_parser("add-docs", help="добавить документацию (папка или файл)")
    p.add_argument("arch")
    p.add_argument("path")
    p.add_argument("--note")
    p.set_defaults(fn=cmd_add_docs)
    p = sp.add_parser("build", help="сканировать и записать слой")
    p.add_argument("arch")
    p.set_defaults(fn=cmd_build)
    p = sp.add_parser("system", help="настроить систему: имя, назначение, владелец, алиасы, внешняя, исключить, слить")
    p.add_argument("arch")
    p.add_argument("id")
    p.add_argument("--title")
    p.add_argument("--rename", help="новый id")
    p.add_argument("--purpose")
    p.add_argument("--owner")
    p.add_argument("--source", help="откуда назначение или владелец: путь:строка документа, «код», «человек», «не известно, Q-…»")
    p.add_argument("--alias", action="append", help="другое имя (в документах, хост, имя сервиса); можно несколько раз")
    p.add_argument("--external", action="store_true", help="внешняя система без репозитория (SaaS, партнёр, легаси)")
    p.add_argument("--exclude", nargs="?", const="не система", help="не система: библиотека, тесты, инструмент (причина)")
    p.add_argument("--include", action="store_true", help="вернуть исключённую или слитую")
    p.add_argument("--merge-into", help="это часть другой системы")
    p.set_defaults(fn=cmd_system)
    p = sp.add_parser("claim", help="записать связь из текста документа (не со схемы)")
    p.add_argument("arch")
    p.add_argument("--from", dest="from_", required=True)
    p.add_argument("--to", required=True)
    p.add_argument("--kind", required=True, choices=list(KINDS))
    p.add_argument("--what", required=True)
    p.add_argument("--source", required=True)
    p.set_defaults(fn=cmd_claim)
    p = sp.add_parser("q", help="добавить вопрос в QUESTIONS.md")
    p.add_argument("arch")
    p.add_argument("--title", required=True)
    p.add_argument("--category", required=True)
    p.add_argument("--seen", required=True)
    p.add_argument("--affects", required=True, help="id систем через запятую")
    p.add_argument("--assume", required=True)
    p.add_argument("--who", required=True)
    p.add_argument("--importance", default="уточняет")
    p.set_defaults(fn=cmd_q)
    p = sp.add_parser("show", help="карточка системы или контракт")
    p.add_argument("arch")
    p.add_argument("--system")
    p.add_argument("--event")
    p.add_argument("--entry")
    p.set_defaults(fn=cmd_show)
    p = sp.add_parser("check", help="проверить слой")
    p.add_argument("arch")
    p.set_defaults(fn=cmd_check)
    p = sp.add_parser("status", help="что устарело с последней сборки")
    p.add_argument("arch")
    p.set_defaults(fn=cmd_status)
    p = sp.add_parser("link", help="карточки систем → репозиторий, указатель в AGENTS.md")
    p.add_argument("arch")
    p.add_argument("repo")
    p.set_defaults(fn=cmd_link)
    a = ap.parse_args()
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
