#!/usr/bin/env python3
"""Контракты и данные — то, по чему доработка не должна сломаться: поля входов и событий, кто вызывает и кто подписан,
сущности и их копии, места создания, миграции, засев, конкурентность и транзакции.

  python3 contracts.py scan <repo>
  python3 contracts.py show <repo> [--cap <cap>] [--entry <шаблон>] [--event <имя>] [--entity <имя>]

scan — читает system-context/inventory.json (сначала inventory.py scan) и код, пишет:
  system-context/contracts.md — по каждому входу: сигнатура обработчика, заголовки, доступ, ответы из кода, типы запроса
                                и ответа с полями; события: поля (и расхождения копий), кто публикует, кто подписан;
                                кто в репозитории вызывает эти входы (клиенты, шлюзы, промпты ИИ) — с местом «на что опирается»;
  system-context/data.md      — сущности с полями и ограничениями, где создаются, копии полей (DTO, модели клиентов),
                                миграции, засев, конкурентность, транзакции, валидация;
  system-context/contracts.json — то же для скриптов.
  Блоки между `<!-- sa:auto id="…" -->` и `<!-- sa:auto-end -->` скрипт переписывает при каждом запуске; всё вне блоков —
  твои заметки, они сохраняются. Эвристики (регулярные выражения, без запуска кода): найденное сверяй с кодом.

show — разделы обоих файлов по возможности, входу, событию или сущности (для брифа и цикла по возможностям).

Python 3.9+, только стандартная библиотека.
"""
import argparse
import fnmatch
import json
import re
import sys
from collections import OrderedDict, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "lib"))
sys.path.insert(0, str(HERE))
import sa  # noqa: E402
from inventory import (CODE_EXT, CS, GO, JS, JVM, PY, Inv, read, rel, walk)  # noqa: E402

MAX_FIELDS = 30
MAX_TYPES = 6
MAX_LINES = 12
DATA_EXT = {".json", ".csv", ".sql", ".yaml", ".yml"}
CONF_EXT = {".json", ".yaml", ".yml", ".toml", ".xml", ".conf", ".ini"}
TEST_PATH = Inv.TEST_PATH
NOT_CONTRACT = re.compile(r"^(?:I[A-Z]\w*|\w*(?:Service|Services|Repository|Repo|Context|DbContext|Logger|Options|Settings|Factory|"
                          r"Provider|Manager|Mediator|Controller|Extensions|Exception|Helper|Middleware|Configuration|Builder|"
                          r"Validator|Behavior|Behaviour|Queries|Program|Startup|Module|Api|Apis|Hub|Client|Handler)|Task|"
                          r"String|Guid|DateTime|Results|TypedResults|Ok|NotFound|BadRequest|List|Dictionary|Array|Promise|"
                          r"Response|Request|Optional|Map|Set|Object|Error|Number|Boolean|Date|Record|Partial|Pick|Omit)$")
EMPTY_ONLY = re.compile(r"if\s*\(\s*!\s*(?:await\s+)?[\w.]+\.Any(?:Async)?\(|\.Any(?:Async)?\(\)\s*\)\s*(?:return|\{)|"
                        r"(?:count|Count)\(\)\s*==\s*0|if\s+not\s+[\w.]+\.(?:first|exists)\(|\.exists\(\)\s*\)?\s*:?\s*return|"
                        r"if\s*\(\s*\(?await\s+[\w.]+\.count\(")
COMMON_SEGS = {"account", "accounts", "login", "logout", "signin", "signout", "signup", "register", "home", "index", "error",
               "errors", "health", "status", "users", "admin", "static", "assets", "public", "callback", "about"}
GATEWAY = re.compile(r"ReverseProxy|Yarp|MapForwarder|AddYarp|ocelot|http-proxy|createProxyMiddleware|proxy_pass|Traefik|Envoy", re.I)
CLIENT_RX = re.compile(r"(^|/)([\w.-]*(?:client|mobile|maui|android|ios|hybrid|frontend|spa|desktop|electron)[\w.-]*)(/|$)", re.I)
AI_CALL = re.compile(r"IChatClient|ChatClient|GetResponseAsync|CompleteAsync|chat\.completions|messages\.create|ChatCompletion|"
                     r"generateText|streamText|invoke_model|\.invoke\(|IEmbeddingGenerator|GenerateEmbedding|GenerateAsync|embeddings\.create|"
                     r"embed_documents|embed_query", re.I)
SERIALIZE = re.compile(r"JsonSerializer\.Serialize|JSON\.stringify|json\.dumps|model_dump|\.to_json|ToJson\(|GenerateEmbedding|"
                       r"GenerateAsync\(|embeddings\.create|embed_(?:documents|query)|\$\"[^\"]*\{\w+\.(?:Name|Description|Title)")
PUB_RX = re.compile(r"\b(?:Publish|publish|emit|Emit|produce|Produce|dispatch|Dispatch|AddDomainEvent|AddIntegrationEvent|"
                    r"AddAndSaveEventAsync|SaveEvent\w*|enqueue|Enqueue|apply_async|perform_async|perform_later|sendMessage|"
                    r"SendMessage|send_message|SendAsync|send)\w*\s*\(")
TOPIC_PUB = re.compile(r"\.(?:send|produce|publish|emit|sendToQueue|add)\(\s*\{?\s*(?:topic\s*:\s*)?['\"`]([\w.:/-]{3,})['\"`]")
SUB_RX = re.compile(r"(?:Subscribe|AddSubscription|subscribe|on)\s*<\s*([\w.]+)\s*(?:,\s*([\w.]+))?\s*>")
CONCURRENCY = re.compile(r"\[ConcurrencyCheck\]|\[Timestamp\]|IsRowVersion\(|IsConcurrencyToken\(|@Version\b|version_id_col|"
                         r"optimisticLock|@VersionColumn|lock_version|FOR\s+UPDATE|\.ForUpdate\(|select_for_update|LockModeType|"
                         r"\bxmin\b|UseXminAsConcurrencyToken|RowVersion\b|DbUpdateConcurrencyException|OptimisticLockException|"
                         r"RedLock|redlock|advisory_lock|pg_advisory|SETNX|\bWATCH\b")
LOCKS = re.compile(r"SemaphoreSlim|\bMutex\b|\block\s*\(|threading\.Lock|asyncio\.Lock|sync\.Mutex|synchronized\b|ReentrantLock")
VALID_REG = re.compile(r"AddValidation\(|AddFluentValidation|AddValidatorsFromAssembl|ValidatorBehavior|ValidationBehavior|ValidationPipe|"
                       r"useGlobalPipes|@Validated\b|ModelState\.IsValid|\.Validate\(\s*new\s+ValidationContext|ValidateDataAnnotations|"
                       r"\[ApiController\]|AddEndpointsApiExplorer\(\)\.AddValidation|validate_call|@validate_arguments|zValidator|celebrate\(")
TRANSACTION = re.compile(r"BeginTransaction(?:Async)?\(|TransactionScope|@Transactional|transaction\.atomic|\$transaction|"
                         r"session\.begin\(|db\.Transaction\(|\.transaction\(\s*(?:async)?|BEGIN\s+TRANSACTION|"
                         r"CommitTransaction(?:Async)?\(|CreateExecutionStrategy|SaveEntitiesAsync|UnitOfWork")
VALIDATION = re.compile(r"AbstractValidator<(\w+)>|AddValidation\(|AddFluentValidation|\[(?:Required|MaxLength|MinLength|StringLength|"
                        r"Range|RegularExpression|EmailAddress)\b|@(?:Valid|Validated|NotNull|NotBlank|NotEmpty|Size|Min|Max|Pattern|Email)\b|"
                        r"z\.object\(|\.safeParse\(|\.parse\(req\.|Joi\.object|class-validator|@Is[A-Z]\w+\(|ValidationPipe|"
                        r"BaseModel\)|Field\(\s*\.\.\.|validator\(|field_validator|@validates|ModelState\.IsValid|\.Validate\(")
STATUS_NAMES = {"ok": 200, "created": 201, "createdatroute": 201, "createdataction": 201, "accepted": 202, "nocontent": 204,
                "badrequest": 400, "validationproblem": 400, "unauthorized": 401, "forbid": 403, "forbidden": 403, "notfound": 404,
                "conflict": 409, "unprocessableentity": 422, "toomanyrequests": 429, "problem": 500, "internalservererror": 500,
                "serviceunavailable": 503, "permissiondenied": 403, "unauthenticated": 401, "invalidargument": 400,
                "alreadyexists": 409, "failedprecondition": 400, "unavailable": 503, "internal": 500}
CODE_RXS = [
    re.compile(r"\b(?:TypedResults|Results)\.(\w+)\s*(?:<[^>]*>)?\(([^)\n]{0,120})"),
    re.compile(r"\breturn\s+(Ok|BadRequest|NotFound|NoContent|Created\w*|Accepted|Conflict|Unauthorized|Forbid|Problem|"
               r"ValidationProblem|UnprocessableEntity)\s*\(([^)\n]{0,120})"),
    re.compile(r"\bResponseEntity\.(\w+)\(([^)\n]{0,120})"),
    re.compile(r"\bthrow\s+new\s+(\w+?)(?:Exception|HttpException)\(([^)\n]{0,120})"),
    re.compile(r"\bRpcException\(\s*new\s+Status\(\s*StatusCode\.(\w+)\s*,?([^)\n]{0,120})"),
    re.compile(r"\bstatus\.(\w+)\b()"),
]
NUM_RXS = [re.compile(r"(?:HTTPException|HttpException|HTTPError|abort|\.status|sendStatus|\.code|abort|StatusCode|status_code\s*=|status\s*[:=]|HTTP_|StatusCodes\.Status|"
                      r"c\.(?:JSON|String|Status|AbortWithStatus\w*))\(?\s*(\d{3})\b([^\n]{0,140})"),
           re.compile(r"\bHttpStatus\.([A-Z_]+)()"), re.compile(r"\bhttp\.Status(\w+)()")]
AUTH_RX = re.compile(r"RequireAuthorization\([^)]*\)|AllowAnonymous|\[Authorize[^\]]*\]|@PreAuthorize\([^)]*\)|@Secured\([^)]*\)|"
                     r"@RolesAllowed|@UseGuards\([^)]*\)|@login_required|@permission_required\([^)]*\)|Depends\(\s*\w*(?:user|auth|admin)\w*|"
                     r"permission_classes\s*=\s*\[[^\]]*\]|requireAuth\w*|authenticate\w*\(|isAuthenticated", re.I)
HEADER_RX = re.compile(r"FromHeader\(\s*Name\s*=\s*\"([^\"]+)\"|headers\[['\"]([\w-]+)['\"]\]|headers\.get\(['\"]([\w-]+)['\"]|"
                       r"@RequestHeader\(\s*(?:value\s*=\s*|name\s*=\s*)?\"([^\"]+)\"|Header\(\s*(?:alias\s*=\s*)?['\"]([\w-]+)['\"]|"
                       r"req\.get\(['\"]([\w-]+)['\"]|\.header\(['\"]([\w-]+)['\"]\)", re.I)


# ---------------------------------------------------------------- исходники

class Src:
    def __init__(self, root, inv):
        self.root = root
        self.texts = OrderedDict()
        self.lines = {}
        for p in walk(root):
            ext = p.suffix.lower()
            if ext in CODE_EXT or ext in {".proto", ".prisma", ".sql"} or ext in CONF_EXT or ext in DATA_EXT:
                relp = rel(root, p)
                if relp.startswith(("system-context/", "openspec/")):
                    continue
                t = read(p)
                if t:
                    self.texts[relp] = t
        self.packages = sorted({pk["dir"] for pk in inv.get("stack", [])} | {e.get("package", ".") for e in inv.get("entries", [])},
                               key=len, reverse=True)

    def ln(self, relp):
        if relp not in self.lines:
            self.lines[relp] = self.texts.get(relp, "").split("\n")
        return self.lines[relp]

    def package_of(self, relp):
        for d in self.packages:
            if d not in (".", "") and (relp == d or relp.startswith(d + "/")):
                return d
        return "."

    def code(self, tests=False):
        for relp, t in self.texts.items():
            if Path(relp).suffix.lower() in CODE_EXT and (tests or not TEST_PATH.search(relp)):
                yield relp, t


def line_of(text, pos):
    return text.count("\n", 0, pos) + 1


def block_end(text, open_pos, limit=40000):
    """Позиция закрывающей скобки для `{` в open_pos (строки и комментарии — грубо)."""
    depth, i, n = 0, open_pos, min(len(text), open_pos + limit)
    quote = None
    while i < n:
        ch = text[i]
        if quote:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                quote = None
        elif ch in "\"'`":
            quote = ch
        elif ch == "/" and text[i:i + 2] == "//":
            j = text.find("\n", i)
            i = n if j < 0 else j
            continue
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return n


def split_params(s):
    out, depth, cur = [], 0, ""
    for ch in s:
        if ch in "<([{":
            depth += 1
        elif ch in ">)]}":
            depth -= 1
        if ch == "," and depth == 0:
            out.append(cur)
            cur = ""
        else:
            cur += ch
    if cur.strip():
        out.append(cur)
    return [x.strip() for x in out if x.strip()]


def squash(s, n=300):
    s = re.sub(r"\s+", " ", s).strip()
    return s if len(s) <= n else s[:n] + "…"


# ---------------------------------------------------------------- индекс типов

class Types:
    def __init__(self):
        self.defs = defaultdict(list)   # name -> [{name, file, line, kind, fields:[[n,t]], base, attrs:[]}]
        self.rpcs = {}                  # "Service.Rpc" -> (req, resp, file, line)

    def add(self, name, relp, line, kind, fields, base="", attrs=None):
        seen, uniq = set(), []
        for f, t in fields:
            if f and f not in seen and not f.startswith("get_"):
                seen.add(f)
                uniq.append([f, squash(t, 60)])
        self.defs[name].append({"name": name, "file": relp, "line": line, "kind": kind, "fields": uniq[:MAX_FIELDS],
                                "more": max(0, len(uniq) - MAX_FIELDS), "base": squash(base, 80), "attrs": (attrs or [])[:15]})

    def pick(self, name, near="", entity=False):
        ds = self.defs.get(name) or []
        if not ds:
            return None
        def score(d):
            a, b = d["file"].split("/"), near.split("/")
            k = 0
            while k < min(len(a), len(b)) and a[k] == b[k]:
                k += 1
            client = bool(CLIENT_RX.search(d["file"])) and not CLIENT_RX.search(near)
            low = d["file"].lower()
            view = bool(re.search(r"viewmodel|dto|request|response|quer(?:y|ies)|contract|client", low))
            level = 2 if re.search(r"domain|entit|aggregate", low) else (1 if re.search(r"model|schema", low) else 0)
            if entity:
                return (not client, not view, level, k, len(d["fields"]))
            same = near.split("/")[:2] == d["file"].split("/")[:2]
            return (same, not client, k, len(d["fields"]))   # контракт входа — тип из того же сервиса, что и обработчик
        return max(ds, key=score)

    # --- языки
    CS_T = re.compile(r"^[ \t]*(?:\[[^\]\n]*\]\s*)*(?:(?:public|internal|private|protected|sealed|abstract|partial|static|readonly|file|ref)\s+)*"
                      r"(record(?:\s+struct|\s+class)?|class|struct|interface)\s+(\w+)(?:<[^>{(\n]*>)?\s*(?:\(([^)]*)\))?\s*(?::\s*([^{;\n]+))?", re.M)
    CS_PROP = re.compile(r"^\s*(?:\[[^\]\n]*\]\s*)*(?:public|internal|protected)\s+(?:required\s+|virtual\s+|override\s+|new\s+)*"
                         r"([\w<>\[\]?,. ]+?)\s+(\w+)\s*\{\s*(?:get|init|set)", re.M)
    CS_FIELD = re.compile(r"^\s*(?:private|protected)\s+(?!readonly|static|const)([\w<>\[\]?,. ]+?)\s+(_\w+)\s*[;=]", re.M)
    CS_ATTR = re.compile(r"\[(?:Required|MaxLength|MinLength|StringLength|Range|Key|Column|Index|Timestamp|ConcurrencyCheck|"
                         r"JsonPropertyName|JsonIgnore|DataMember)[^\]]*\]")

    def cs(self, relp, text):
        for m in self.CS_T.finditer(text):
            kind, name, params, base = m.group(1), m.group(2), m.group(3), m.group(4) or ""
            fields = []
            if params and kind.startswith("record"):
                for p in split_params(params):
                    p = re.sub(r"\[[^\]]*\]\s*", "", p).split("=")[0].strip()
                    bits = p.rsplit(None, 1)
                    if len(bits) == 2:
                        fields.append([bits[1], bits[0]])
            after = text[m.end():m.end() + 400]
            br = after.find("{")
            semi = after.find(";")
            body = ""
            if br >= 0 and (semi < 0 or br < semi):
                o = m.end() + br
                body = text[o:block_end(text, o)]
            for pm in self.CS_PROP.finditer(body):
                fields.append([pm.group(2), pm.group(1)])
            for fm in self.CS_FIELD.finditer(body):
                fields.append([fm.group(2), fm.group(1)])
            attrs = [squash(a.group(0), 80) for a in self.CS_ATTR.finditer(body)]
            self.add(name, relp, line_of(text, m.start(2)), kind.split()[0], fields, base, attrs)

    TS_T = re.compile(r"^\s*(?:export\s+)?(?:default\s+)?(?:declare\s+)?(?:abstract\s+)?(interface|class|type)\s+(\w+)(?:<[^>\n]*>)?\s*"
                      r"(?:extends\s+([\w.<>, ]+?)\s*)?(?:implements\s+[\w.<>, ]+?\s*)?(?:=\s*)?\{", re.M)
    TS_F = re.compile(r"^\s*(?:@\w+\([^)\n]*\)\s*)*(?:readonly\s+|public\s+|private\s+|protected\s+|declare\s+)*(\w+)\??!?\s*:\s*([^;,\n]+)", re.M)
    ZOD = re.compile(r"(?:export\s+)?const\s+(\w+)\s*=\s*z\.object\(\s*\{")

    def ts(self, relp, text):
        for m in self.TS_T.finditer(text):
            o = m.end() - 1
            body = text[o + 1:block_end(text, o)]
            body = re.sub(r"\([^()]*\)\s*(?::[^{;\n]*)?\{[\s\S]*?\n\s*\}", "", body)   # методы
            fields = [[f.group(1), f.group(2)] for f in self.TS_F.finditer(body) if f.group(1) not in ("constructor", "return")]
            self.add(m.group(2), relp, line_of(text, m.start(2)), m.group(1), fields, m.group(3) or "")
        for m in self.ZOD.finditer(text):
            o = m.end() - 1
            body = text[o + 1:block_end(text, o)]
            fields = [[f.group(1), "z." + f.group(2)] for f in re.finditer(r"^\s*(\w+)\s*:\s*z\.(\w+)", body, re.M)]
            self.add(m.group(1), relp, line_of(text, m.start(1)), "zod", fields)

    PY_T = re.compile(r"^class\s+(\w+)\s*(?:\(([^)]*)\))?\s*:\s*\n", re.M)

    def py(self, relp, text):
        for m in self.PY_T.finditer(text):
            body_lines = []
            for ln in text[m.end():].split("\n"):
                if ln.strip() and not ln.startswith((" ", "\t")):
                    break
                body_lines.append(ln)
            fields, attrs = [], []
            for ln in body_lines:
                f = re.match(r"^(?: {4}|\t)(\w+)\s*:\s*([^=\n]+?)(?:\s*=\s*(.+))?$", ln)
                g = re.match(r"^(?: {4}|\t)(\w+)\s*=\s*((?:models|db|sa|fields|serializers|mongoengine|orm)\.\w+\(.*|"
                             r"(?:Column|mapped_column|Field|relationship|CharField|IntegerField)\(.*)$", ln)
                if f and not f.group(1).startswith("_"):
                    fields.append([f.group(1), f.group(2) + (" = " + f.group(3) if f.group(3) and "Field(" in f.group(3) else "")])
                elif g:
                    fields.append([g.group(1), g.group(2)])
                    if re.search(r"unique|max_length|nullable|null=|blank=|index|primary_key|default", g.group(2)):
                        attrs.append(squash(ln, 100))
            if fields:
                self.add(m.group(1), relp, line_of(text, m.start(1)), "class", fields, m.group(2) or "", attrs)

    JV_T = re.compile(r"^[ \t]*(?:@\w+(?:\([^)]*\))?\s*)*(?:(?:public|private|protected|final|abstract|static|data|open|sealed)\s+)*"
                      r"(record|class|interface)\s+(\w+)(?:<[^>\n]*>)?\s*(?:\(([^)]*)\))?", re.M)

    def jvm(self, relp, text):
        for m in self.JV_T.finditer(text):
            fields = []
            for p in split_params(m.group(3) or ""):
                p = re.sub(r"@\w+(?:\([^)]*\))?\s*", "", p).split("=")[0].strip()
                k = re.match(r"(?:val|var)\s+(\w+)\s*:\s*(.+)", p)
                if k:
                    fields.append([k.group(1), k.group(2)])
                else:
                    bits = p.rsplit(None, 1)
                    if len(bits) == 2:
                        fields.append([bits[1], bits[0]])
            after = text[m.end():m.end() + 300]
            br = after.find("{")
            attrs = []
            if br >= 0:
                o = m.end() + br
                body = text[o:block_end(text, o)]
                for f in re.finditer(r"^\s*((?:@\w+(?:\([^)\n]*\))?\s*)*)(?:private|protected|public)\s+(?:final\s+)?([\w<>\[\], .?]+?)\s+(\w+)\s*[;=]", body, re.M):
                    fields.append([f.group(3), f.group(2)])
                    if f.group(1).strip():
                        attrs.append(squash(f.group(1) + " " + f.group(3), 100))
                for f in re.finditer(r"^\s*(?:override\s+)?(?:val|var)\s+(\w+)\s*:\s*([\w<>?.]+)", body, re.M):
                    fields.append([f.group(1), f.group(2)])
            self.add(m.group(2), relp, line_of(text, m.start(2)), m.group(1), fields, "", attrs)

    def go(self, relp, text):
        for m in re.finditer(r"type\s+(\w+)\s+struct\s*\{", text):
            o = m.end() - 1
            body = text[o + 1:block_end(text, o)]
            fields = []
            for f in re.finditer(r"^\s*(\w+)\s+([\w.\[\]*]+)(?:\s+`([^`]*)`)?", body, re.M):
                j = re.search(r'json:"([\w-]+)', f.group(3) or "")
                fields.append([f.group(1) + (f" (json {j.group(1)})" if j else ""), f.group(2)])
            self.add(m.group(1), relp, line_of(text, m.start(1)), "struct", fields)

    def proto(self, relp, text):
        for m in re.finditer(r"^\s*message\s+(\w+)\s*\{", text, re.M):
            o = m.end() - 1
            body = text[o + 1:block_end(text, o)]
            fields = [[f.group(3), (f.group(1) or "") + f.group(2)]
                      for f in re.finditer(r"^\s*(repeated\s+|optional\s+)?([\w.<>, ]+?)\s+(\w+)\s*=\s*\d+", body, re.M)]
            self.add(m.group(1), relp, line_of(text, m.start(1)), "message", fields)
        for sm in re.finditer(r"service\s+(\w+)\s*\{([\s\S]*?)\n\}", text):
            for r in re.finditer(r"rpc\s+(\w+)\s*\(\s*(?:stream\s+)?([\w.]+)\s*\)\s*returns\s*\(\s*(?:stream\s+)?([\w.]+)\s*\)", sm.group(2)):
                self.rpcs[f"{sm.group(1)}.{r.group(1)}"] = (r.group(2).split(".")[-1], r.group(3).split(".")[-1], relp,
                                                            line_of(text, sm.start(2) + r.start()))

    def prisma(self, relp, text):
        for m in re.finditer(r"^model\s+(\w+)\s*\{", text, re.M):
            o = m.end() - 1
            body = text[o + 1:block_end(text, o)]
            fields, attrs = [], []
            for f in re.finditer(r"^\s*(\w+)\s+([\w\[\]?]+)(.*)$", body, re.M):
                fields.append([f.group(1), f.group(2)])
                if "@" in f.group(3):
                    attrs.append(squash(f.group(1) + " " + f.group(3), 100))
            attrs += [squash(x, 100) for x in re.findall(r"^\s*@@.+$", body, re.M)]
            self.add(m.group(1), relp, line_of(text, m.start(1)), "prisma", fields, "", attrs)

    def build(self, src):
        for relp, t in src.texts.items():
            ext = Path(relp).suffix.lower()
            if TEST_PATH.search(relp):
                continue
            if ext in CS:
                self.cs(relp, t)
            elif ext in JS:
                self.ts(relp, t)
            elif ext in PY:
                self.py(relp, t)
            elif ext in JVM:
                self.jvm(relp, t)
            elif ext in GO:
                self.go(relp, t)
            elif ext == ".proto":
                self.proto(relp, t)
            elif ext == ".prisma":
                self.prisma(relp, t)
        return self


def fmt_type(d, show_attrs=False):
    fs = ", ".join(f"{n} {t}" for n, t in d["fields"]) or "полей не найдено — смотри определение"
    more = f" … ещё {d['more']}" if d.get("more") else ""
    base = f" : {d['base']}" if d.get("base") else ""
    s = f"`{d['name']}`{base} ({d['file']}:{d['line']}): {fs}{more}"
    if show_attrs and d.get("attrs"):
        s += "; атрибуты: " + "; ".join(f"`{a}`" for a in d["attrs"][:8])
    return s


# ---------------------------------------------------------------- входы

def handler_region(src, relp, line):
    """(начало, конец, сигнатура) обработчика входа: тело функции на строке входа или функции, на которую он ссылается."""
    text = src.texts.get(relp, "")
    if not text:
        return 0, 0, ""
    lines = src.ln(relp)
    ln = lines[line - 1] if 0 < line <= len(lines) else ""
    ext = Path(relp).suffix.lower()
    start = sum(len(x) + 1 for x in lines[:line - 1])
    m = re.search(r"Map\w+\(\s*\"[^\"]*\"\s*,\s*(\w+)\s*\)|\.\w+\(\s*['\"][^'\"]*['\"]\s*,\s*(?:\w+\s*,\s*)*(\w+)\s*\)", ln)
    name = m and (m.group(1) or m.group(2))
    if name and name not in ("async", "function"):
        d = re.search(rf"^[ \t]*(?:(?:public|private|protected|internal|static|async|override|virtual|final|suspend)\s+)+"
                      rf"(?:[\w<>\[\],.? ]+\s+)?{re.escape(name)}\s*(?:<[^>\n]*>)?\s*\(|^[ \t]*(?:export\s+)?(?:async\s+)?function\s+{re.escape(name)}\b|"
                      rf"^[ \t]*(?:export\s+)?(?:const|let)\s+{re.escape(name)}\s*=|^[ \t]*(?:async\s+)?def\s+{re.escape(name)}\b|"
                      rf"^func\s+(?:\([^)]*\)\s*)?{re.escape(name)}\s*\(|^[ \t]*(?:async\s+)?{re.escape(name)}\s*\([^)\n]*\)\s*(?::[^{{\n]*)?\{{", text, re.M)
        if d:
            start = d.start()
    elif ext in PY or ext in JVM or ext in CS:
        # декоратор/атрибут над функцией — функция ниже
        nxt = re.compile(r"^\s*(?:async\s+)?def\s+\w+|^\s*(?:public|private|protected|internal)[^\n;=]*\(", re.M).search(text, start)
        if nxt and line_of(text, nxt.start()) - line <= 6:
            start = nxt.start()
    if ext in PY:
        head = re.compile(r"\)\s*(?:->[^:\n]*)?:\s*$", re.M).search(text, start)
        sig_end = head.end() if head else start
        indent = None
        end = sig_end
        for mm in re.finditer(r"^(.*)$", text[sig_end:sig_end + 20000], re.M):
            s = mm.group(1)
            if not s.strip():
                continue
            ind = len(s) - len(s.lstrip())
            if indent is None:
                indent = ind
            elif ind < indent:
                break
            end = sig_end + mm.end()
        return start, end, squash(text[start:sig_end], 400)
    br = text.find("{", start)
    arrow = text.find("=>", start)
    if br < 0 or (0 <= arrow < br and text[arrow:br].count("\n") > 1):
        br = arrow
    if br < 0:
        return start, min(len(text), start + 2000), squash(lines[line - 1] if line <= len(lines) else "", 300)
    end = block_end(text, br) if text[br] == "{" else text.find(";", br)
    end = min(end if end > 0 else len(text), start + 20000)
    return start, end, squash(text[start:br], 400)


def codes_in(region):
    found = OrderedDict()
    for rx in CODE_RXS:
        for m in rx.finditer(region):
            key = re.sub(r"(?:Exception|HttpResult|ObjectResult|Result)$", "", m.group(1)).replace("_", "").lower()
            code = STATUS_NAMES.get(key)
            if code is None and rx is CODE_RXS[3]:
                continue
            msg = re.search(r"\"([^\"]{3,90})\"|'([^']{3,90})'", m.group(2) or "")
            label = f"{code or '?'} {m.group(1)}" + (f" «{msg.group(1) or msg.group(2)}»" if msg else "")
            found.setdefault(label, True)
    for rx in NUM_RXS:
        for m in rx.finditer(region):
            v = m.group(1)
            code = int(v) if v.isdigit() else STATUS_NAMES.get(v.replace("_", "").lower())
            if code:
                rest = m.group(2) or ""
                body = re.search(r"\.(?:json|send|JSON)\(\s*(?:\w+\s*,\s*)?(\{[^\n]{0,110}?\})\s*\)", rest)
                msg = re.search(r"\"([^\"]{3,90})\"|'([^']{3,90})'", rest)
                found.setdefault(f"{code}" + (f" тело `{squash(body.group(1), 90)}`" if body else
                                             f" «{msg.group(1) or msg.group(2)}»" if msg else ""), True)
    return list(found)[:12]


def referenced_types(T, text, near, skip=()):
    out = []
    for name in OrderedDict.fromkeys(re.findall(r"\b([A-Z]\w{2,})\b", text)):
        if name in skip or NOT_CONTRACT.match(name) or name not in T.defs:
            continue
        d = T.pick(name, near)
        if d and d["kind"] not in ("interface",) or (d and d["fields"]):
            out.append(d)
    return out


def entry_contract(src, T, e):
    rec = OrderedDict([("id", e["id"]), ("kind", e["kind"]), ("file", e["file"]), ("line", e["line"])])
    if e["kind"] == "grpc":
        rpc = T.rpcs.get(e["name"])
        svc, meth = (e["name"].split(".", 1) + [""])[:2]
        if rpc:
            rec["types"] = [d for d in (T.pick(rpc[0], e["file"]), T.pick(rpc[1], e["file"])) if d]
            rec["signature"] = f"rpc {meth}({rpc[0]}) returns ({rpc[1]})"
        # реализация на сервере
        for relp, t in src.code():
            m = re.search(rf"override\s+(?:async\s+)?[\w<>.]+\s+{re.escape(meth)}\s*\(", t)
            if m and re.search(rf"\b{re.escape(svc)}\w*Base\b|{re.escape(svc)}\.{re.escape(svc)}Base", t):
                o = t.find("{", m.end())
                region = t[m.start():block_end(t, o)] if o > 0 else ""
                rec["handler"] = f"{relp}:{line_of(t, m.start())}"
                rec["codes"] = codes_in(region)
                rec["auth"] = sorted({squash(x, 60) for x in AUTH_RX.findall(region)})[:4]
                break
        return rec
    if e["kind"] not in ("http", "graphql", "ui", "rpc"):
        return rec
    s, en, sig = handler_region(src, e["file"], e["line"])
    text = src.texts.get(e["file"], "")
    region = text[s:en]
    rec["handler"] = f"{e['file']}:{line_of(text, s)}" if text else ""
    rec["signature"] = sig
    lines_ = src.ln(e["file"]) if text else []
    deco = "\n".join(lines_[max(0, e["line"] - 1):e["line"] + 1]) if lines_ else ""   # status_code= в декораторе
    rec["codes"] = codes_in(deco + "\n" + region) if e["kind"] == "http" else []
    rec["headers"] = sorted({next(g for g in m.groups() if g) for m in HEADER_RX.finditer(sig + region)})[:6]
    entry_line = src.ln(e["file"])[e["line"] - 1] if text and e["line"] <= len(src.ln(e["file"])) else ""
    auth = {squash(x, 70) for x in AUTH_RX.findall(entry_line + "\n" + sig + "\n" + region[:3000])}
    rec["auth"] = sorted(auth)[:4]
    sig_types = referenced_types(T, sig + " " + entry_line, e["file"])
    body_types = [d for d in referenced_types(T, region, e["file"], {d["name"] for d in sig_types})
                  if not re.search(r"(?:Event|Command)$", d["name"]) or True]
    rec["types"] = (sig_types + body_types)[:MAX_TYPES]
    rec["more_types"] = max(0, len(sig_types) + len(body_types) - MAX_TYPES)
    return rec


# ---------------------------------------------------------------- события

def events(src, T, inv, plan_caps):
    ev = OrderedDict()

    def get(name):
        return ev.setdefault(name, OrderedDict([("name", name), ("internal", False), ("defs", []), ("publishers", []),
                                                ("subscribers", []), ("registrations", []), ("caps", [])]))
    for e in inv.get("entries", []):
        if e["kind"] != "consumer":
            continue
        m = re.match(r"^(?:event|доменное событие)\s+(\w+)$", e["name"]) or re.match(r"^(?:kafka|rabbitmq|sqs|jms|message|amqp|nats|"
                                                                                       r"bull-queue|bullmq-queue)\s+(\S+)$", e["name"])
        if not m:
            continue
        x = get(m.group(1))
        x["internal"] = x["internal"] or e["name"].startswith("доменное") or "internal" in e.get("tags", [])
        x["subscribers"].append(f"{e['file']}:{e['line']} ({e['how']})")
        if plan_caps.get(e["id"]):
            x["caps"].append(plan_caps[e["id"]])
    # кандидаты по именам типов
    for name, ds in T.defs.items():
        if re.search(r"(?:IntegrationEvent|DomainEvent|Event|Message)$", name) and name not in ("IntegrationEvent", "Event", "Message",
                                                                                               "DomainEvent"):
            if any(re.search(r"Event|INotification|Message", d["base"]) or d["kind"] in ("record", "class", "interface", "type")
                   for d in ds):
                get(name)
    names = set(ev)
    news = defaultdict(list)    # name -> [(file, line)]
    for relp, t in src.code():
        for m in re.finditer(r"\bnew\s+(\w+)\s*[({]", t):
            if m.group(1) in names:
                news[m.group(1)].append((relp, line_of(t, m.start())))
        for m in SUB_RX.finditer(t):
            nm = m.group(1).split(".")[-1]
            if nm in names:
                ev[nm]["registrations"].append(f"{relp}:{line_of(t, m.start())}" + (f" → {m.group(2).split('.')[-1]}" if m.group(2) else ""))
        for m in TOPIC_PUB.finditer(t):
            if m.group(1) in names:
                ev[m.group(1)]["publishers"].append(f"{relp}:{line_of(t, m.start())}")
    for name, locs in news.items():
        for relp, line in locs:
            lines = src.ln(relp)
            cur = lines[line - 1]
            v = re.search(r"(\w+)\s*=\s*new\s+" + re.escape(name), cur)
            if v:   # событие в переменной — публикация ниже по коду с этой переменной
                after = lines[line - 1:line + 30]
                hit = next((i for i, ln in enumerate(after) if PUB_RX.search(ln) and re.search(rf"\b{re.escape(v.group(1))}\b", ln)), None)
                if hit is not None:
                    ev[name]["publishers"].append(f"{relp}:{line} (отправка: {line + hit})")
                    continue
            win = "\n".join(lines[max(0, line - 3):line + 3])
            if PUB_RX.search(win):
                ev[name]["publishers"].append(f"{relp}:{line}")
    out = OrderedDict()
    for name, x in ev.items():
        x["defs"] = T.defs.get(name, [])[:4]
        if not (x["publishers"] or x["subscribers"] or x["registrations"]):
            continue
        sets = {tuple(sorted(f[0].lower() for f in d["fields"])) for d in x["defs"]}
        x["copies_differ"] = len(x["defs"]) > 1 and len(sets) > 1
        x["caps"] = sorted(set(x["caps"]))
        for k in ("publishers", "subscribers", "registrations"):
            x[k] = list(OrderedDict.fromkeys(x[k]))[:MAX_LINES]
        if not x["internal"] and any("DomainEvent" in name or "INotification" in d["base"] for d in x["defs"]):
            x["internal"] = True
        out[name] = x
    return out


# ---------------------------------------------------------------- кто вызывает входы

def static_prefix(path, n):
    segs = []
    for s in path.strip("/").split("/"):
        if not s or "{" in s or s.startswith(":") or s == "*":
            break
        segs.append(s)
    return "/".join(segs[:n])


def callers(src, inv, plan_caps):
    groups = OrderedDict()
    http = [e for e in inv.get("entries", []) if e["kind"] == "http"]
    by_prefix = defaultdict(list)
    for e in http:
        path = e["name"].split(" ", 1)[1] if " " in e["name"] else e["name"]
        segs = path.strip("/").split("/")
        n = 2 if segs and segs[0].lower() in ("api", "v1", "v2", "v3", "rest", "public", "internal") else 1
        if segs and len(segs) > n and re.fullmatch(r"v\d+", segs[n - 1], re.I):
            n += 1
        pre = static_prefix(path, n)
        if "/" not in pre and (len(pre) < 5 or pre.lower() in COMMON_SEGS):
            continue   # «/logout», «/account» есть у многих сервисов — по одному сегменту вызывающего не узнать
        if len(pre) >= 4:
            by_prefix[(e.get("package", "."), pre)].append(e)
    for (pkg, pre), es in by_prefix.items():
        rx = re.compile(r"['\"`/{]" + re.escape(pre) + r"(?:['\"`/?{]|$)", re.M | re.I)
        tails = {}
        for e in es:
            path = e["name"].split(" ", 1)[1]
            rest = [s for s in path.strip("/").split("/")[len(pre.split("/")):] if s and "{" not in s]
            if rest:
                tails.setdefault(rest[0], []).append(e["id"])
        for relp, t in src.texts.items():
            if relp in {x["file"] for x in es} or (src.package_of(relp) == pkg and not CLIENT_RX.search(relp)):
                continue   # свой сервис (маршруты, монтирование) — не вызывающий; клиентская папка внутри него — вызывающий
            hits = [line_of(t, m.start()) for m in rx.finditer(t)]
            if not hits:
                continue
            ext = Path(relp).suffix.lower()
            kind = "тест" if TEST_PATH.search(relp) else ("конфиг/шлюз" if ext in CONF_EXT or GATEWAY.search(t) else "код")
            g = groups.setdefault((src.package_of(relp), pkg, pre), OrderedDict([
                ("consumer", src.package_of(relp)), ("target", pkg), ("what", "/" + pre), ("kind", "http"),
                ("client", bool(CLIENT_RX.search(relp))), ("files", OrderedDict()), ("calls", OrderedDict()),
                ("entries", sorted({x["id"] for x in es})), ("caps", sorted({plan_caps[x["id"]] for x in es if plan_caps.get(x["id"])}))]))
            g["files"][f"{relp}:{hits[0]}"] = kind
            tail_rx = re.compile(r"[/\"'`](?:" + "|".join(re.escape(x) for x in tails) + r")(?:[/?{\"'`]|$)", re.I) if tails else None
            for i, ln in enumerate(src.ln(relp), 1):
                if ln.lstrip().startswith(("//", "#", "*", "<!--")):
                    continue
                if rx.search(ln) or (tail_rx and tail_rx.search(ln)):
                    g["calls"].setdefault(f"{relp}:{i}", squash(ln, 140))
    # gRPC-клиенты
    svcs = sorted({e["name"].split(".")[0] for e in inv.get("entries", []) if e["kind"] == "grpc"})
    for svc in svcs:
        es = [e for e in inv["entries"] if e["kind"] == "grpc" and e["name"].startswith(svc + ".")]
        pkg = es[0].get("package", ".")
        rx = re.compile(rf"\b{re.escape(svc)}(?:\.{re.escape(svc)})?Client\b|\b{re.escape(svc)}ServiceClient\b")
        for relp, t in src.code(tests=True):
            m = rx.search(t)
            if not m or Path(relp).suffix.lower() == ".proto":
                continue
            g = groups.setdefault((src.package_of(relp), pkg, svc), OrderedDict([
                ("consumer", src.package_of(relp)), ("target", pkg), ("what", f"gRPC {svc}"), ("kind", "grpc"),
                ("client", bool(CLIENT_RX.search(relp))), ("files", OrderedDict()), ("calls", OrderedDict()),
                ("entries", sorted(e["id"] for e in es)), ("caps", sorted({plan_caps[e["id"]] for e in es if plan_caps.get(e["id"])}))]))
            g["files"][f"{relp}:{line_of(t, m.start())}"] = "тест" if TEST_PATH.search(relp) else "код"
            for e in es:
                meth = e["name"].split(".", 1)[1]
                mm = re.search(rf"\.{re.escape(meth)}(?:Async)?\s*\(", t)
                if mm:
                    g["calls"].setdefault(f"{relp}:{line_of(t, mm.start())}", f"{meth}")
    # промпты и эмбеддинги ИИ: какие данные уходят в модель
    ai = []
    for relp, t in src.code():
        if not AI_CALL.search(t):
            continue
        for i, ln in enumerate(src.ln(relp), 1):
            if SERIALIZE.search(ln):
                ai.append(f"{relp}:{i}: `{squash(ln, 110)}`")
    out = list(groups.values())
    for g in out:
        if all(v == "тест" for v in g["files"].values()):
            g["kind"] += " (только тесты)"
    return out, ai[:40]


# ---------------------------------------------------------------- данные

def data_map(src, T, inv):
    ents = []
    all_types = [(n, d) for n, ds in T.defs.items() for d in ds]
    for en in inv.get("entities", []):
        name = en["name"]
        d = T.pick(name, en["file"], entity=True)
        if d and not d["fields"]:
            d = next((x for x in T.defs.get(name, []) if x["fields"]), d)
        rec = OrderedDict([("name", name), ("how", en["how"]), ("file", en["file"]), ("line", en["line"]),
                           ("def", d), ("config", []), ("creates", []), ("creates_tests", 0), ("copies", []), ("seeds", [])])
        rx_new = re.compile(rf"\bnew\s+{re.escape(name)}\s*[({{]|\b{re.escape(name)}\.objects\.(?:create|get_or_create|bulk_create)\(|"
                            rf"\b{re.escape(name)}\.(?:create|build|insert)\(|\bprisma\.{re.escape(name[:1].lower() + name[1:])}\.(?:create|upsert|createMany)\(|"
                            rf"(?<![\w.:])(?<!class )(?<!def ){re.escape(name)}\(\s*\w+\s*=")
        rx_cfg = re.compile(rf"IEntityTypeConfiguration<{re.escape(name)}>|Entity<{re.escape(name)}>\s*\(")
        for relp, t in src.code(tests=True):
            for m in rx_new.finditer(t):
                if TEST_PATH.search(relp):
                    rec["creates_tests"] += 1
                else:
                    rec["creates"].append(f"{relp}:{line_of(t, m.start())}")
            for m in rx_cfg.finditer(t):
                o = t.find("{", m.end())
                body = t[o:block_end(t, o)] if o > 0 else ""
                for ln in body.split("\n"):
                    if re.search(r"HasMaxLength|IsRequired|HasIndex|IsUnique|HasKey|HasConversion|ToTable|HasColumnName|HasDefaultValue|"
                                 r"HasPrecision|IsRowVersion|IsConcurrencyToken|OwnsOne|OwnsMany|HasMany|HasOne|Ignore\(|UseHiLo|"
                                 r"HasField|UsePropertyAccessMode|HasData|HasNoKey|HasDiscriminator", ln):
                        rec["config"].append(f"{relp}:{t.count(chr(10), 0, o) + 1 + body[:body.find(ln)].count(chr(10))}: `{squash(ln, 100)}`")
        rec["creates"] = rec["creates"][:MAX_LINES]
        rec["config"] = rec["config"][:15]
        # копии полей: другие типы с тем же или похожим именем и пересечением полей
        if d and d["fields"]:
            mine = {f[0].lstrip("_").lower() for f in d["fields"]}
            for n2, d2 in all_types:
                if d2 is d or not d2["fields"]:
                    continue
                theirs = {f[0].lstrip("_").lower() for f in d2["fields"]}
                common = mine & theirs
                related = name.lower() in n2.lower() or n2.lower() in name.lower() and len(n2) > 3
                if (related and len(common) >= 2) or (len(common) >= 3 and len(common) >= 0.6 * len(theirs)):
                    rec["copies"].append({"name": n2, "file": d2["file"], "line": d2["line"], "common": len(common), "of": len(theirs),
                                          "missing": sorted(mine - theirs)[:8]})
            rec["copies"].sort(key=lambda c: (-c["common"], c["file"]))
            rec["copies"] = rec["copies"][:12]
        ents.append(rec)
    # засев
    seeds = []
    for relp, t in src.texts.items():
        low = relp.lower()
        ext = Path(relp).suffix.lower()
        if TEST_PATH.search(relp) or re.search(r"(^|/)(migrations?|alembic)/", low):
            continue
        is_data = ext in DATA_EXT and re.search(r"seed(?!work)|fixture|setup/|sample|initial|catalog\.json|data/", low) \
            and not re.search(r"appsettings|package|tsconfig|launchsettings|manifest|\.github|docker|compose", low)
        is_code = ext in CODE_EXT and (re.search(r"seed(?!work)", low) or re.search(r"\bHasData\(|\bclass\s+\w*Seed\w*", t))
        if not (is_data or is_code):
            continue
        n = ""
        if ext == ".json":
            n = f", записей ~{len(re.findall(chr(123), t)) if t.lstrip().startswith('[') else '?'}"
        mentions = [en["name"] for en in inv.get("entities", []) if re.search(rf"\b{re.escape(en['name'])}\b", t)]
        empty = bool(is_code and EMPTY_ONLY.search(t))
        seeds.append(f"{relp}{n}" + (f" — {', '.join(mentions[:6])}" if mentions else "") +
                     (" — ⚠ засевает только пустую таблицу: в существующей БД новое поле само не заполнится, нужна миграция данных" if empty else ""))
        for rec in ents:
            if rec["name"] in mentions:
                rec["seeds"].append(relp + (" (только в пустую таблицу)" if empty else ""))
    # миграции и снимки схемы
    migr = []
    for d, cnt in sorted(inv.get("migrations", {}).items()):
        files = sorted(f for f in src.texts if f.startswith(d + "/") and not f.endswith(".Designer.cs"))
        snap = [f for f in files if re.search(r"ModelSnapshot|schema\.rb$|structure\.sql$", f)]
        last = [Path(f).name for f in files if f not in snap][-2:]
        migr.append(f"{d}: файлов {cnt}" + (f", последние: {', '.join(last)}" if last else "") + (f", снимок схемы: {', '.join(snap)}" if snap else ""))
    for f in src.texts:
        if re.search(r"ModelSnapshot\.cs$|(^|/)schema\.rb$|(^|/)schema\.prisma$", f) and not any(f in m for m in migr):
            d = f.rsplit("/", 1)[0]
            files = sorted(x for x in src.texts if x.rsplit("/", 1)[0] == d and x != f and not x.endswith(".Designer.cs")
                           and re.match(r"\d", Path(x).name))
            if f.endswith(".prisma"):
                files = sorted(x for x in src.texts if x.startswith(d + "/migrations/") and x.endswith("migration.sql"))
            migr.append(f"{d}: " + (f"миграций {len(files)}, последние: {', '.join(x.split('/')[-2] if x.endswith('migration.sql') else Path(x).name for x in files[-2:])}"
                                    if files else "файлов миграций рядом не найдено") +
                        f"; схема или снимок: {f} — сверь с моделью перед новой миграцией (расхождение уйдёт в миграцию)")

    def lines_of(rx, cap=30):
        """По файлу — номера строк и пример: так список не тонет в однотипных строках."""
        out = []
        for relp, t in src.code():
            if re.search(r"(^|/)(migrations?|alembic)/|\.Designer\.cs$|ModelSnapshot", relp, re.I):
                continue   # сгенерированное
            hits = [(i, ln) for i, ln in enumerate(src.ln(relp), 1) if rx.search(ln) and not ln.lstrip().startswith(("//", "#", "*"))]
            if hits:
                nums = ", ".join(str(i) for i, _ in hits[:8]) + (f" … ещё {len(hits) - 8}" if len(hits) > 8 else "")
                out.append(f"{relp}:{nums} — `{squash(hits[0][1], 90)}`")
                if len(out) >= cap:
                    out.append("… список обрезан — остальное: grep по коду")
                    return out
        return out
    # валидация: где есть атрибуты и правила, а где она подключена
    attr_pk, reg_pk = set(), set()
    for relp, t in src.code():
        pk = src.package_of(relp)
        if VALIDATION.search(t):
            attr_pk.add(pk)
        if VALID_REG.search(t):
            reg_pk.add(pk)
    unwired = sorted(pk for pk in attr_pk - reg_pk if pk != ".")
    return OrderedDict([("entities", ents), ("seeds", seeds[:30]), ("migrations", migr),
                        ("concurrency", lines_of(CONCURRENCY)), ("locks", lines_of(LOCKS, 10)), ("transactions", lines_of(TRANSACTION)),
                        ("validation_wiring", lines_of(VALID_REG, 20)), ("validation", lines_of(VALIDATION, 30)),
                        ("validation_unwired", unwired)])


# ---------------------------------------------------------------- запись с сохранением заметок

AUTO_RX = re.compile(r"<!-- sa:auto id=\"(.*?)\" -->\n([\s\S]*?)<!-- sa:auto-end -->")


def auto(key, body):
    return f"<!-- sa:auto id=\"{key}\" -->\n{body.rstrip()}\n<!-- sa:auto-end -->"


def merge_doc(path, head, groups):
    """groups: [(заголовок ##, [(заголовок ###, key, тело, хвост для новых)])]. Обновляет auto-блоки, остальное не трогает."""
    fresh = {}
    for _, secs in groups:
        for h, key, body, tail in secs:
            fresh[key] = body
    if not path.is_file():
        parts = [head.rstrip(), ""]
        for gh, secs in groups:
            parts += [f"## {gh}", ""]
            if not secs:
                parts += ["Не найдено.", ""]
            for h, key, body, tail in secs:
                parts += [f"### {h}", auto(key, body)] + ([tail] if tail else []) + [""]
        path.write_text("\n".join(parts).rstrip() + "\n", encoding="utf-8")
        return len(fresh), 0, 0
    text = path.read_text(encoding="utf-8")
    seen, stale = set(), 0

    def rep(m):
        nonlocal stale
        key = m.group(1)
        seen.add(key)
        if key in fresh:
            return auto(key, fresh[key])
        stale += 1
        return auto(key, "- ⚠ больше не найдено при пересканировании — проверь по коду и удали раздел, если вход или сущность исчезли")
    text = AUTO_RX.sub(rep, text)
    added = 0
    for gh, secs in groups:
        new = [s for s in secs if s[1] not in seen]
        if not new:
            continue
        chunk = "\n".join(f"### {h}\n{auto(key, body)}" + (f"\n{tail}" if tail else "") + "\n" for h, key, body, tail in new)
        m = re.search(rf"^## {re.escape(gh)}\s*$", text, re.M)
        if m:
            nxt = re.compile(r"^## ", re.M).search(text, m.end())
            pos = nxt.start() if nxt else len(text)
            text = text[:pos].rstrip() + "\n\n" + chunk + "\n" + text[pos:]
        else:
            text = text.rstrip() + f"\n\n## {gh}\n\n" + chunk
        added += len(new)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")
    return len(seen & set(fresh)), added, stale


CONTRACTS_HEAD = """# Контракты

То, по чему доработка не должна сломаться: что принимают входы и что отдают, какие события ходят между частями системы
и кто ещё в репозитории опирается на эти контракты. Поведение — в `openspec/specs/`, здесь — форма данных и связи.

Блоки `sa:auto` собирает `contracts.py scan` (эвристики — сверяй с кодом), пересканирование их переписывает.
Свои уточнения пиши **вне** блоков, строкой под блоком («Заметки: …»). Места с комментарием «заполнить» заполняет агент.
"""
DATA_HEAD = """# Данные

Сущности и их поля, где они создаются и куда копируются, схема и миграции, засев, конкурентность и транзакции.
Новое поле сущности — пройди по «Создаётся», «Копии полей» и «Засев»: там оно потеряется молча.

Блоки `sa:auto` собирает `contracts.py scan` (эвристики — сверяй с кодом), пересканирование их переписывает.
Свои уточнения пиши **вне** блоков. Места с комментарием «заполнить» заполняет агент.
"""
CALLER_TAIL = ("- **Опирается на:** <!-- заполнить: открой файлы выше — какие поля читает, какие статусы и коды ответа сравнивает, "
               "что сломается при изменении (например «кнопка отмены только для Submitted», «ждёт 400, сервер отдаёт 500») -->")
AI_TAIL = "- **Что уходит в модель:** <!-- заполнить: какие поля сущностей попадают в промпт или эмбеддинг; новое поле попадёт туда само? -->"
CONC_TAIL = ("- **Что это значит:** <!-- заполнить: что защищено от параллельных изменений, а что нет (последняя запись побеждает?); "
             "границы транзакций; что публикуется вне транзакции -->")
VALID_TAIL = "- **Что это значит:** <!-- заполнить: где проверяются входные данные и что не проверяется (подключена ли валидация вообще) -->"


def contract_body(rec, cap):
    out = [f"- Возможность: {cap or '— (не отнесён)'}; вход: {rec['file']}:{rec['line']}" +
           (f"; обработчик: {rec['handler']}" if rec.get("handler") and rec["handler"] != f"{rec['file']}:{rec['line']}" else "")]
    if rec.get("signature"):
        out.append(f"- Сигнатура: `{rec['signature'].replace('`', '')}`")
    if rec.get("headers"):
        out.append("- Заголовки: " + ", ".join(f"`{h}`" for h in rec["headers"]))
    if rec.get("auth"):
        out.append("- Доступ (в обработчике): " + "; ".join(f"`{x}`" for x in rec["auth"]))
    if rec.get("codes"):
        out.append("- Ответы из кода обработчика: " + "; ".join(rec["codes"]) + " (исключения из глубины вызовов сюда не попадают)")
    elif rec["kind"] == "http":
        out.append("- Ответы из кода обработчика: не найдены явно — по умолчанию 200; ошибки — смотри исключения и общий обработчик")
    for d in rec.get("types", []):
        out.append("- Тип " + fmt_type(d))
    if rec.get("more_types"):
        out.append(f"- … ещё типов: {rec['more_types']}")
    return "\n".join(out)


def event_body(x):
    out = []
    if x["defs"]:
        for d in x["defs"]:
            out.append("- Поля: " + fmt_type(d))
        if x.get("copies_differ"):
            out.append("- ⚠ копии события в разных сервисах различаются по полям — подписчик может не получить нужное")
        elif len(x["defs"]) > 1:
            out.append(f"- Копий определения: {len(x['defs'])} (поля совпадают) — новое поле добавляй во все")
    else:
        out.append("- Поля: тип не найден (событие по имени/теме) — смотри место публикации")
    out.append("- Публикует: " + ("; ".join(x["publishers"]) if x["publishers"] else "не найдено (публикация вне репозитория или по другому имени?)"))
    out.append("- Подписаны: " + ("; ".join(x["subscribers"]) if x["subscribers"] else "не найдено в репозитории (внешние подписчики?)"))
    if x["registrations"]:
        out.append("- Регистрация подписки: " + "; ".join(x["registrations"]))
    if x["caps"]:
        out.append("- Возможности подписчиков: " + ", ".join(x["caps"]))
    return "\n".join(out)


def caller_body(g):
    out = [f"- Что вызывает: {g['what']} ({g['target']}), вид: {g['kind']}" + (" — клиентское приложение" if g["client"] else "")]
    out.append("- Где: " + "; ".join(f"{f} ({k})" for f, k in list(g["files"].items())[:MAX_LINES]))
    if g["calls"]:
        out.append("- Пути в коде вызывающего: " + "; ".join(f"{loc} `{lit.replace('`', '')}`" for loc, lit in list(g["calls"].items())[:MAX_LINES]))
    if g["caps"]:
        out.append("- Возможности: " + ", ".join(g["caps"]))
    return "\n".join(out)


def entity_body(r):
    out = []
    if r["def"]:
        out.append("- Поля: " + fmt_type(r["def"], show_attrs=True))
    else:
        out.append(f"- Определение: {r['file']}:{r['line']} ({r['how']}) — поля не разобраны, смотри код")
    if r["config"]:
        out.append("- Схема и ограничения: " + "; ".join(r["config"]))
    out.append("- Создаётся: " + ("; ".join(r["creates"]) if r["creates"] else "явных мест не найдено (фабрика, маппер, ORM?)") +
               (f"; в тестах: {r['creates_tests']}" if r["creates_tests"] else ""))
    if r["copies"]:
        out.append("- Копии полей (DTO, модели клиентов, события) — новое поле проверь в каждой: " + "; ".join(
            f"`{c['name']}` {c['file']}:{c['line']} (общих полей {c['common']} из {c['of']}" +
            (f", нет: {', '.join(c['missing'][:5])}" if c["missing"] else "") + ")" for c in r["copies"]))
    if r["seeds"]:
        out.append("- Засев: " + ", ".join(sorted(set(r["seeds"]))[:6]))
    if r.get("ai"):
        out.append("- Уходит в модель ИИ (промпт, эмбеддинг — новое поле может попасть туда само): " + "; ".join(r["ai"][:5]))
    return "\n".join(out)


def cmd_scan(a):
    P = sa.Paths(a.repo)
    inv = sa.load_inventory(P)
    plan = json.loads(P.plan.read_text(encoding="utf-8")) if P.plan.is_file() else {"capabilities": [], "excluded": []}
    plan_caps = {eid: c["id"] for c in plan.get("capabilities", []) for eid in c["entries"]}
    excluded = {x["entry"] for x in plan.get("excluded", [])}
    src = Src(P.repo, inv)
    T = Types().build(src)
    entries = [e for e in inv.get("entries", []) if e["id"] not in excluded and e["kind"] != "consumer"]
    recs = [entry_contract(src, T, e) for e in entries]
    evs = events(src, T, inv, plan_caps)
    calls, ai = callers(src, inv, plan_caps)
    data = data_map(src, T, inv)
    for r in data["entities"]:   # сущность в файлах, откуда данные уходят в модель ИИ
        r["ai"] = [x.split(": `")[0] for x in ai if re.search(rf"\b{re.escape(r['name'])}\b", src.texts.get(x.split(":")[0], ""))]

    kinds = OrderedDict([("http", "HTTP"), ("grpc", "gRPC"), ("graphql", "GraphQL"), ("rpc", "RPC"), ("ui", "Страницы интерфейса"),
                         ("schedule", "Расписания"), ("cli", "Команды CLI")])
    groups = []
    for k, title in kinds.items():
        secs = [(f"`{r['id']}`", r["id"], contract_body(r, plan_caps.get(r["id"])), "") for r in recs if r["kind"] == k]
        if secs or k in ("http",):
            groups.append((title, secs))
    ext_ev = [(f"`{n}`", f"event:{n}", event_body(x), "") for n, x in evs.items() if not x["internal"]]
    int_ev = [(f"`{n}`", f"event:{n}", event_body(x), "") for n, x in evs.items() if x["internal"]]
    groups.append(("События между сервисами", ext_ev))
    groups.append(("Внутренние (доменные) события", int_ev))
    cl = [(f"{g['consumer']} → {g['what']}", f"caller:{g['consumer']}→{g['target']}:{g['what']}", caller_body(g),
           CALLER_TAIL if "только тесты" not in g["kind"] else "") for g in calls]
    groups.append(("Кто вызывает входы (в репозитории)", cl))
    if ai:
        groups.append(("Данные в промптах и эмбеддингах ИИ", [("Где данные уходят в модель", "ai", "\n".join(f"- {x}" for x in ai), AI_TAIL)]))
    n1 = merge_doc(P.ctx / "contracts.md", CONTRACTS_HEAD, groups)

    dgroups = [("Сущности", [(f"`{r['name']}` ({r['how']})", f"entity:{r['name']}", entity_body(r), "") for r in data["entities"]]),
               ("Миграции и схема", [("Где лежат", "migrations", "\n".join(f"- {x}" for x in data["migrations"]) or "- миграций не найдено", "")]),
               ("Засев и справочники", [("Файлы засева", "seeds", "\n".join(f"- {x}" for x in data["seeds"]) or "- засева не найдено", "")]),
               ("Конкурентность и транзакции", [
                   ("Конкурентность", "concurrency", ("\n".join(f"- {x}" for x in data["concurrency"]) or
                    "- ⚠ токенов конкурентности (версия строки, xmin), SELECT … FOR UPDATE и распределённых блокировок не найдено: "
                    "параллельные изменения одной записи — «последняя запись побеждает»") +
                    ("\n- Блокировки внутри процесса (не защищают от второго экземпляра): " + "; ".join(data["locks"]) if data["locks"] else ""), ""),
                   ("Транзакции", "transactions", "\n".join(f"- {x}" for x in data["transactions"]) or "- явных транзакций не найдено", CONC_TAIL)]),
               ("Валидация входных данных", [("Где проверяется", "validation",
                                              "\n".join(["- Подключение: " + ("; ".join(data["validation_wiring"]) if data["validation_wiring"] else "не найдено")] +
                                                        ([f"- ⚠ правила или атрибуты есть, а подключения в сервисе не найдено (атрибуты могут не проверяться): {', '.join(data['validation_unwired'])}"]
                                                         if data["validation_unwired"] else []) +
                                                        [f"- {x}" for x in data["validation"]]) if (data["validation"] or data["validation_wiring"])
                                              else "- ⚠ валидации не найдено", VALID_TAIL)])]
    n2 = merge_doc(P.ctx / "data.md", DATA_HEAD, dgroups)

    js = OrderedDict([("entries", recs), ("events", evs), ("callers", calls), ("ai", ai), ("data", data)])
    (P.ctx / "contracts.json").write_text(json.dumps(js, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    nf = sum(len(r.get("types", [])) for r in recs)
    print(f"✓ {P.rel(P.ctx / 'contracts.md')}: входов {len(recs)} (типов с полями {nf}), событий {len(ext_ev)} + внутренних {len(int_ev)}, "
          f"групп вызывающих {len(cl)}" + (f", мест с данными для ИИ {len(ai)}" if ai else ""))
    print(f"✓ {P.rel(P.ctx / 'data.md')}: сущностей {len(data['entities'])}, засев {len(data['seeds'])}, миграций {len(data['migrations'])}, "
          f"конкурентность {len(data['concurrency'])}, транзакции {len(data['transactions'])}, валидация {len(data['validation'])}")
    for name, (kept, added, stale) in (("contracts.md", n1), ("data.md", n2)):
        if added or stale:
            print(f"  {name}: обновлено {kept}, новых разделов {added}, исчезнувших {stale} (помечены ⚠)")
    clients = [g for g in calls if g["client"] and "только тесты" not in g["kind"]]
    if clients:
        print(f"  клиентские приложения среди вызывающих: {len(clients)} — их ожидания (статусы, коды, поля) — в «Опирается на»")
    diff = [n for n, x in evs.items() if x.get("copies_differ")]
    if diff:
        print(f"  ! копии событий расходятся по полям: {', '.join(diff[:6])}")
    nph = sum((P.ctx / f).read_text(encoding="utf-8").count("<!-- заполнить") for f in ("contracts.md", "data.md"))
    print((f"Дальше: заполни места «<!-- заполнить» ({nph}) — шаг 6 SKILL.md; " if nph else "Мест «заполнить» не осталось. ") +
          f"При описании возможности сверяйся с её разделами: contracts.py show {a.repo} --cap <cap>")
    return 0


# ---------------------------------------------------------------- show

def sections(path):
    if not path.is_file():
        return []
    text = path.read_text(encoding="utf-8")
    return [(m.group(1), m.group(0)) for m in re.finditer(r"^### (.+)\n[\s\S]*?(?=^### |^## |\Z)", text, re.M)]


def cmd_show(a):
    P = sa.Paths(a.repo)
    cpath, dpath = P.ctx / "contracts.md", P.ctx / "data.md"
    if not cpath.is_file():
        sa.die(f"нет {P.rel(cpath)} — сначала contracts.py scan {a.repo}")
    js = json.loads((P.ctx / "contracts.json").read_text(encoding="utf-8")) if (P.ctx / "contracts.json").is_file() else {}
    want = set()
    if a.cap:
        plan = sa.load_plan(P)
        c = next((x for x in plan["capabilities"] if x["id"] == a.cap), None)
        if not c:
            sa.die(f"нет возможности {a.cap}")
        ids = set(c["entries"])
        want |= {f"`{i}`" for i in ids}
        names = set()
        for i in ids:
            m = re.match(r"^consumer:(?:event|доменное событие)\s+(\w+)", i)
            if m:
                names.add(m.group(1))
        files = {r["file"] for r in js.get("entries", []) if r["id"] in ids} | {r.get("handler", "").split(":")[0] for r in js.get("entries", []) if r["id"] in ids}
        if P.trace.is_file():   # файлы из трассировки возможности: там обработчики, публикующие события
            for req in sa.parse_trace(P.trace.read_text(encoding="utf-8")).get(a.cap, {}).values():
                files |= {x.split(":")[0] for x in req["code"]}
        files.discard("")
        for n, x in js.get("events", {}).items():
            locs = " ".join(x["publishers"] + x["subscribers"])
            if n in names or any(f and f in locs for f in files) or a.cap in x.get("caps", []):
                want.add(f"`{n}`")
        # один шаг по цепочке: обработчик доменного события публикует интеграционное
        hop = {loc.split(":")[0] for n, x in js.get("events", {}).items() if f"`{n}`" in want and x.get("internal")
               for loc in x["subscribers"]}
        for n, x in js.get("events", {}).items():
            if any(loc.split(":")[0] in hop for loc in x["publishers"]):
                want.add(f"`{n}`")
        for g in js.get("callers", []):
            if a.cap in g.get("caps", []):
                want.add(f"{g['consumer']} → {g['what']}")
        types = {d["name"] for r in js.get("entries", []) if r["id"] in ids for d in r.get("types", [])}
        for en in js.get("data", {}).get("entities", []):
            if en["name"] in types:
                want.add(f"`{en['name']}` ({en['how']})")
    if a.entry:
        want |= {h for h, _ in sections(cpath) if fnmatch.fnmatch(h.strip("`"), a.entry) or a.entry in h}
    if a.event:
        want |= {h for h, _ in sections(cpath) if a.event.lower() in h.lower()}
    if a.entity:
        want |= {h for h, _ in sections(dpath) if a.entity.lower() in h.lower()}
    if not (a.cap or a.entry or a.event or a.entity):
        sa.die("укажи --cap, --entry, --event или --entity")
    shown = 0
    for path in (cpath, dpath):
        for h, body in sections(path):
            if h in want:
                print(body.rstrip() + "\n")
                shown += 1
    if not shown:
        print("ничего не найдено — проверь имя или пересканируй: contracts.py scan")
    return 0


def main():
    ap = argparse.ArgumentParser(description="Контракты входов и событий, вызывающие, данные")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("scan", help="собрать contracts.md и data.md (заметки вне блоков sa:auto сохраняются)")
    s.add_argument("repo")
    s.set_defaults(fn=cmd_scan)
    sh = sub.add_parser("show", help="разделы по возможности, входу, событию, сущности")
    sh.add_argument("repo")
    sh.add_argument("--cap")
    sh.add_argument("--entry", help="id входа или шаблон с *")
    sh.add_argument("--event", help="часть имени события")
    sh.add_argument("--entity", help="часть имени сущности")
    sh.set_defaults(fn=cmd_show)
    a = ap.parse_args()
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
