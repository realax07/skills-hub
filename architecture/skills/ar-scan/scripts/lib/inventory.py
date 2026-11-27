#!/usr/bin/env python3
"""Опись репозитория для системного анализа: что сервис принимает и что вызывает сам.

  python3 inventory.py scan <repo> [--out <repo>/system-context] [--json]
  python3 inventory.py show <repo> [--kind http] [--grep orders] [--section entries|outbound|env|entities|tests|todos]

scan — ищет эвристиками (регулярными выражениями, без запуска кода):
  точки входа  — HTTP-маршруты, GraphQL, gRPC, обработчики очередей и событий, расписания, CLI;
  выходы       — HTTP-клиенты, внешние хосты в коде и конфигах, SDK внешних сервисов из зависимостей;
  конфигурацию — имена переменных окружения (значения не читаются никогда);
  данные       — модели и таблицы, перечисления статусов, проверки прав;
  опору        — тесты с названиями, документацию, OpenAPI, TODO/FIXME в коде.
Пишет <out>/inventory.json (полностью) и <out>/inventory.md (сводка для чтения).
Эвристики пропускают редкие фреймворки — недостающие входы добавляй в план: plan.py add-entry.

show — выборка из готового inventory.json, чтобы не читать его целиком.

Python 3.9+, только стандартная библиотека.
"""
import argparse
import json
import os
import re
import sys
from collections import OrderedDict, defaultdict
from pathlib import Path

VERSION = 1
SKIP_DIRS = {
    ".git", ".hg", ".svn", "node_modules", "bower_components", "vendor", "dist", "build", "out", "target",
    ".next", ".nuxt", ".svelte-kit", ".output", ".turbo", ".cache", ".parcel-cache", "coverage", ".nyc_output",
    ".venv", "venv", "env", ".env", "__pycache__", ".mypy_cache", ".pytest_cache", ".tox", ".gradle", ".idea",
    ".vscode", "bin", "obj", "Pods", "DerivedData", ".terraform", "storybook-static", "public/build",
    "openspec", "system-context", "design-context", ".claude", ".agents", ".codex", ".opencode", ".qwen",
}
LOCKFILES = {"package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock", "go.sum", "Cargo.lock",
             "composer.lock", "Gemfile.lock", "Pipfile.lock", "bun.lockb", "uv.lock", "packages.lock.json"}
CODE_EXT = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".vue", ".svelte", ".py", ".go", ".java", ".kt", ".kts",
            ".scala", ".groovy", ".rb", ".php", ".cs", ".rs", ".ex", ".exs", ".erl", ".clj", ".razor", ".cshtml"}
JS = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}
PY = {".py"}
GO = {".go"}
JVM = {".java", ".kt", ".kts", ".scala", ".groovy"}
RB = {".rb"}
PHP = {".php"}
CS = {".cs", ".razor"}
RS = {".rs"}
CONF_EXT = {".yaml", ".yml", ".json", ".toml", ".ini", ".properties", ".conf", ".env", ".xml", ".tf", ".hcl"}
MAX_FILE = 1_000_000
CAP_TESTS_PER_FILE = 40
CAP_TEST_TITLES = 4000
CAP_TODOS = 400
CAP_AUTHZ = 400
CAP_CALLS = 2000
HTTP_METHODS = ("get", "post", "put", "patch", "delete", "options", "head", "all")

# хосты, которые не внешние интеграции, а документация, схемы и заглушки
NOISE_HOSTS = re.compile(
    r"(^|\.)(localhost|example\.(com|org|net)|w3\.org|schema\.org|xmlns\.com|json-schema\.org|github\.com|"
    r"githubusercontent\.com|gitlab\.com|bitbucket\.org|npmjs\.(com|org)|pypi\.org|python\.org|mozilla\.org|"
    r"developer\.mozilla\.org|stackoverflow\.com|wikipedia\.org|apache\.org|opensource\.org|creativecommons\.org|"
    r"spdx\.org|reactjs\.org|react\.dev|nodejs\.org|golang\.org|go\.dev|maven\.apache\.org|gradle\.org|"
    r"springframework\.org|microsoft\.com|docs\.\w+\.\w+|readthedocs\.io|swagger\.io|openapis\.org|"
    r"googleapis\.com/auth|fonts\.googleapis\.com|fonts\.gstatic\.com|gravatar\.com|shields\.io|"
    r"127\.0\.0\.1|0\.0\.0\.0|test|invalid|local)$")

# пакет зависимости → категория внешнего сервиса (ключ — префикс имени пакета)
SDK = OrderedDict([
    ("stripe", "платежи"), ("@stripe", "платежи"), ("yookassa", "платежи"), ("cloudpayments", "платежи"),
    ("tinkoff", "платежи"), ("paypal", "платежи"), ("@paypal", "платежи"), ("braintree", "платежи"),
    ("adyen", "платежи"), ("@adyen", "платежи"), ("robokassa", "платежи"), ("razorpay", "платежи"),
    ("nodemailer", "почта"), ("@sendgrid", "почта"), ("sendgrid", "почта"), ("mailgun", "почта"),
    ("postmark", "почта"), ("resend", "почта"), ("@mailchimp", "почта"), ("unisender", "почта"),
    ("django-anymail", "почта"), ("action_mailer", "почта"), ("spring-boot-starter-mail", "почта"),
    ("twilio", "SMS и мессенджеры"), ("vonage", "SMS и мессенджеры"), ("@vonage", "SMS и мессенджеры"),
    ("telegraf", "SMS и мессенджеры"), ("node-telegram-bot-api", "SMS и мессенджеры"), ("grammy", "SMS и мессенджеры"),
    ("python-telegram-bot", "SMS и мессенджеры"), ("telegram", "SMS и мессенджеры"), ("aiogram", "SMS и мессенджеры"), ("@slack", "SMS и мессенджеры"),
    ("slack-sdk", "SMS и мессенджеры"), ("slack_sdk", "SMS и мессенджеры"), ("firebase-admin", "пуши и Firebase"),
    ("web-push", "пуши и Firebase"), ("expo-server-sdk", "пуши и Firebase"),
    ("@aws-sdk", "облако AWS"), ("aws-sdk", "облако AWS"), ("boto3", "облако AWS"), ("botocore", "облако AWS"),
    ("software.amazon.awssdk", "облако AWS"), ("@google-cloud", "облако Google"), ("google-cloud", "облако Google"),
    ("@azure", "облако Azure"), ("azure-", "облако Azure"), ("minio", "файловое хранилище"),
    ("kafkajs", "брокер сообщений"), ("kafka-python", "брокер сообщений"), ("confluent-kafka", "брокер сообщений"),
    ("spring-kafka", "брокер сообщений"), ("amqplib", "брокер сообщений"), ("pika", "брокер сообщений"),
    ("aio-pika", "брокер сообщений"), ("spring-boot-starter-amqp", "брокер сообщений"), ("nats", "брокер сообщений"),
    ("bull", "очереди задач"), ("bullmq", "очереди задач"), ("@nestjs/bull", "очереди задач"), ("celery", "очереди задач"),
    ("rq", "очереди задач"), ("dramatiq", "очереди задач"), ("sidekiq", "очереди задач"), ("hangfire", "очереди задач"),
    ("pg", "базы данных"), ("postgres", "базы данных"), ("mysql", "базы данных"), ("mysql2", "базы данных"),
    ("mongoose", "базы данных"), ("mongodb", "базы данных"), ("@prisma/client", "базы данных"), ("prisma", "базы данных"),
    ("typeorm", "базы данных"), ("sequelize", "базы данных"), ("knex", "базы данных"), ("drizzle-orm", "базы данных"),
    ("sqlalchemy", "базы данных"), ("psycopg", "базы данных"), ("psycopg2", "базы данных"), ("asyncpg", "базы данных"),
    ("pymongo", "базы данных"), ("clickhouse", "базы данных"), ("@clickhouse", "базы данных"),
    ("gorm.io", "базы данных"), ("github.com/jackc/pgx", "базы данных"), ("spring-boot-starter-data", "базы данных"),
    ("redis", "кэш и Redis"), ("ioredis", "кэш и Redis"), ("github.com/redis", "кэш и Redis"),
    ("@elastic", "поиск"), ("elasticsearch", "поиск"), ("algoliasearch", "поиск"), ("meilisearch", "поиск"),
    ("@opensearch-project", "поиск"), ("opensearch-py", "поиск"),
    ("passport", "аутентификация"), ("next-auth", "аутентификация"), ("@auth", "аутентификация"),
    ("@auth0", "аутентификация"), ("auth0", "аутентификация"), ("keycloak", "аутентификация"),
    ("@okta", "аутентификация"), ("authlib", "аутентификация"), ("python-keycloak", "аутентификация"),
    ("spring-boot-starter-oauth2", "аутентификация"), ("@clerk", "аутентификация"), ("@supabase", "аутентификация"),
    ("openai", "ИИ-модели"), ("@anthropic-ai", "ИИ-модели"), ("anthropic", "ИИ-модели"), ("langchain", "ИИ-модели"),
    ("@langchain", "ИИ-модели"), ("@google/generative-ai", "ИИ-модели"), ("cohere", "ИИ-модели"),
    ("@sentry", "мониторинг"), ("sentry-sdk", "мониторинг"), ("sentry", "мониторинг"), ("dd-trace", "мониторинг"),
    ("datadog", "мониторинг"), ("newrelic", "мониторинг"), ("prom-client", "мониторинг"),
    ("prometheus", "мониторинг"), ("@opentelemetry", "мониторинг"), ("opentelemetry", "мониторинг"),
    ("mixpanel", "аналитика"), ("@amplitude", "аналитика"), ("@segment", "аналитика"), ("posthog", "аналитика"),
    ("@googlemaps", "карты и гео"), ("googlemaps", "карты и гео"), ("@mapbox", "карты и гео"),
    ("dadata", "справочники и проверки"), ("@dadata", "справочники и проверки"),
    ("RabbitMQ.Client", "брокер сообщений"), ("MassTransit", "брокер сообщений"), ("Confluent.Kafka", "брокер сообщений"),
    ("Azure.Messaging.ServiceBus", "брокер сообщений"), ("Aspire.RabbitMQ", "брокер сообщений"),
    ("Npgsql", "базы данных"), ("Aspire.Npgsql", "базы данных"), ("Microsoft.EntityFrameworkCore", "базы данных"),
    ("Pgvector", "базы данных"), ("Dapper", "базы данных"), ("MongoDB.Driver", "базы данных"),
    ("StackExchange.Redis", "кэш и Redis"), ("Aspire.StackExchange.Redis", "кэш и Redis"),
    ("Duende.IdentityServer", "аутентификация"), ("Microsoft.AspNetCore.Authentication", "аутентификация"),
    ("Microsoft.Identity", "аутентификация"), ("Stripe.net", "платежи"), ("SendGrid", "почта"), ("MailKit", "почта"),
    ("Microsoft.Extensions.AI", "ИИ-модели"), ("Azure.AI.OpenAI", "ИИ-модели"), ("Aspire.Azure.AI", "ИИ-модели"),
    ("OllamaSharp", "ИИ-модели"), ("CommunityToolkit.Aspire.OllamaSharp", "ИИ-модели"),
    ("Azure.Storage", "облако Azure"), ("AWSSDK", "облако AWS"), ("Grpc.Net.Client", "gRPC-клиент"),
])

MANIFESTS = ("package.json", "requirements.txt", "pyproject.toml", "setup.py", "Pipfile", "go.mod", "pom.xml",
             "build.gradle", "build.gradle.kts", "Gemfile", "composer.json", "Cargo.toml", "mix.exs")
FRAMEWORKS = OrderedDict([
    ("express", "Express"), ("@nestjs/core", "NestJS"), ("next", "Next.js"), ("nuxt", "Nuxt"), ("fastify", "Fastify"),
    ("koa", "Koa"), ("hono", "Hono"), ("@remix-run/node", "Remix"), ("@sveltejs/kit", "SvelteKit"),
    ("@trpc/server", "tRPC"), ("apollo-server", "Apollo GraphQL"), ("@apollo/server", "Apollo GraphQL"),
    ("django", "Django"), ("djangorestframework", "Django REST"), ("flask", "Flask"), ("fastapi", "FastAPI"),
    ("aiohttp", "aiohttp"), ("spring-boot", "Spring Boot"), ("quarkus", "Quarkus"), ("micronaut", "Micronaut"),
    ("ktor", "Ktor"), ("rails", "Rails"), ("sinatra", "Sinatra"), ("laravel/framework", "Laravel"),
    ("symfony/framework-bundle", "Symfony"), ("github.com/gin-gonic/gin", "Gin"), ("github.com/labstack/echo", "Echo"),
    ("github.com/gofiber/fiber", "Fiber"), ("github.com/go-chi/chi", "chi"), ("actix-web", "actix-web"),
    ("axum", "axum"), ("phoenix", "Phoenix"),
    ("Microsoft.NET.Sdk.Web", "ASP.NET Core"), ("Grpc.AspNetCore", "gRPC (ASP.NET Core)"), ("Aspire.Hosting", ".NET Aspire"),
    ("Microsoft.AspNetCore.Components", "Blazor"), ("MediatR", "MediatR"), ("Asp.Versioning.Http", "версионирование API"),
])


def rel(root, p):
    return Path(os.path.relpath(p, root)).as_posix()


def walk(root):
    root = Path(root)
    for dirpath, dirnames, filenames in os.walk(root):
        reld = rel(root, dirpath)
        dirnames[:] = sorted(d for d in dirnames
                             if d not in SKIP_DIRS and not (reld + "/" + d).lstrip("./") in SKIP_DIRS
                             and not d.startswith(".") or d in (".github", ".gitlab", ".circleci"))
        for f in sorted(filenames):
            if f in LOCKFILES:
                continue
            p = Path(dirpath) / f
            try:
                if p.stat().st_size > MAX_FILE:
                    continue
            except OSError:
                continue
            yield p


def read(p):
    try:
        return p.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return ""


def norm_path(path):
    path = path.strip()
    path = re.sub(r"<(?:\w+:)?(\w+)>", r"{\1}", path)          # Flask/Django <int:id>
    path = re.sub(r"\{(\w+):[^}]*\}", r"{\1}", path)            # {id:int}, {id:[0-9]+}
    path = re.sub(r"(?<=/):(\w+)\??", r"{\1}", path)            # Express :id
    path = re.sub(r"\[\.\.\.(\w+)\]", r"{\1*}", path)           # Next [...slug]
    path = re.sub(r"\[(\w+)\]", r"{\1}", path)                  # Next [id]
    path = re.sub(r"^\^|\$$", "", path)                         # Django re_path
    if path and not path.startswith("/"):
        path = "/" + path
    path = re.sub(r"/{2,}", "/", path)
    return path.rstrip("/") or "/"


def join_path(prefix, path):
    if not prefix:
        return norm_path(path or "/")
    return norm_path(prefix.rstrip("/") + "/" + (path or "").lstrip("/"))


def line_of(text, pos):
    return text.count("\n", 0, pos) + 1


def ident_after(text, pos, max_lines=4):
    """Имя функции/метода/класса после декоратора: ближайшее объявление в следующих строках."""
    chunk = "\n".join(text[pos:].split("\n")[1:max_lines + 1])
    m = re.search(r"(?:def|function|func|fun|class|sub)\s+(\w+)|(?:public|private|protected|async|static|\s)+[\w<>\[\], ?]+?\s+(\w+)\s*\(|(\w+)\s*\(", chunk)
    if not m:
        return None
    return m.group(1) or m.group(2) or m.group(3)


class Inv:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.entries = OrderedDict()
        self.calls = []
        self.hosts = defaultdict(lambda: {"count": 0, "files": []})
        self.env = defaultdict(lambda: {"files": []})
        self.entities = OrderedDict()
        self.enums = []
        self.authz = []
        self.tests = []
        self.test_titles = 0
        self.docs = []
        self.openapi = []
        self.todos = []
        self.packages = []
        self.deps = defaultdict(set)   # package dir -> deps
        self.migrations = defaultdict(int)
        self.files_by_ext = defaultdict(int)
        self.warnings = []
        self.js_router_entries = []   # (file, ident, entry id)
        self.js_mounts = []           # (file, prefix, ident)
        self.py_mounts = []           # (file, модуль роутера, префикс) — include_router / register_blueprint
        self.py_router_entries = []   # (file, eid)
        self.js_imports = {}          # (file, ident) -> относительный путь модуля
        self.sdk_uses = []            # импорты SDK внешних сервисов

    # ----- общее
    def package_of(self, relp):
        best = ""
        for pk in self.packages:
            d = pk["dir"]
            if d == "." or relp == d or relp.startswith(d + "/"):
                if len(d) > len(best) or best == "":
                    best = d
        return best or "."

    def add_entry(self, kind, name, relp, line, how, tags=None):
        pkg = self.package_of(relp)
        eid = f"{kind}:{name}"
        if eid in self.entries and self.entries[eid]["package"] != pkg:
            eid = f"{eid} @{pkg}"
        e = self.entries.get(eid)
        if e:
            loc = f"{relp}:{line}"
            if loc not in e["also"] and f'{e["file"]}:{e["line"]}' != loc:
                e["also"].append(loc)
            return eid
        self.entries[eid] = {"id": eid, "kind": kind, "name": name, "file": relp, "line": line, "how": how,
                             "package": pkg, "tags": sorted(set(tags or [])), "also": []}
        return eid

    # ----- манифесты и стек
    def scan_manifests(self, files):
        for p in files:
            if p.name not in MANIFESTS and p.suffix not in (".csproj", ".fsproj", ".vbproj") and p.name != "Directory.Packages.props":
                continue
            relp = rel(self.root, p)
            d = rel(self.root, p.parent)
            text = read(p)
            deps = set()
            name = None
            if p.name == "package.json":
                try:
                    js = json.loads(text)
                except ValueError:
                    self.warnings.append(f"{relp}: не разобрался JSON")
                    continue
                name = js.get("name")
                for k in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
                    deps.update((js.get(k) or {}).keys())
                b = js.get("bin")
                if isinstance(b, str):
                    self.add_entry("cli", name or d, relp, 1, "package.json bin")
                elif isinstance(b, dict):
                    for cmd in b:
                        self.add_entry("cli", cmd, relp, 1, "package.json bin")
            elif p.name == "requirements.txt" or p.name == "Pipfile":
                for ln in text.splitlines():
                    m = re.match(r"\s*([A-Za-z0-9_.\-\[\]]+)", ln)
                    if m and not ln.strip().startswith(("#", "-", "[")):
                        deps.add(m.group(1).split("[")[0].lower())
            elif p.name == "pyproject.toml":
                m = re.search(r'^name\s*=\s*"([^"]+)"', text, re.M)
                name = m.group(1) if m else None
                for m in re.finditer(r'^\s*"?([A-Za-z0-9_.\-]+)(?:\[[^\]]*\])?\s*(?:[<>=~!^;"]|$)', text, re.M):
                    deps.add(m.group(1).lower())
                for m in re.finditer(r'"([A-Za-z0-9_.\-]+)(?:\[[^\]]*\])?\s*[<>=~!;]', text):
                    deps.add(m.group(1).lower())
                for m in re.finditer(r'^\[(?:project\.)?scripts\]\s*\n((?:[^\[\n].*\n?)*)', text, re.M):
                    for sm in re.finditer(r'^\s*([\w\-]+)\s*=\s*"([\w.]+)', m.group(1), re.M):
                        self.add_entry("cli", sm.group(1), relp, line_of(text, m.start()), f"pyproject scripts → {sm.group(2)}")
            elif p.name == "go.mod":
                m = re.search(r"^module\s+(\S+)", text, re.M)
                name = m.group(1) if m else None
                deps.update(re.findall(r"^\s*(?:require\s+)?([\w.\-]+\.[\w.\-/]+)\s+v[\d.]", text, re.M))
            elif p.name == "pom.xml":
                deps.update(re.findall(r"<artifactId>([^<]+)</artifactId>", text))
                deps.update(re.findall(r"<groupId>([^<]+)</groupId>", text))
            elif p.name.startswith("build.gradle"):
                deps.update(m.group(1) + ":" + m.group(2) for m in
                            re.finditer(r"""['"]([\w.\-]+):([\w.\-]+)(?::[^'"]*)?['"]""", text))
                deps.update(m.group(2) for m in re.finditer(r"""['"]([\w.\-]+):([\w.\-]+)""", text))
            elif p.name == "Gemfile":
                deps.update(re.findall(r"""^\s*gem\s+['"]([^'"]+)['"]""", text, re.M))
            elif p.name == "composer.json":
                try:
                    js = json.loads(text)
                    name = js.get("name")
                    deps.update((js.get("require") or {}).keys())
                    deps.update((js.get("require-dev") or {}).keys())
                except ValueError:
                    pass
            elif p.name == "Cargo.toml":
                m = re.search(r'^name\s*=\s*"([^"]+)"', text, re.M)
                name = m.group(1) if m else None
                deps.update(re.findall(r"^([\w\-]+)\s*=", text.split("[dependencies]", 1)[-1], re.M))
            elif p.suffix in (".csproj", ".fsproj", ".vbproj") or p.name == "Directory.Packages.props":
                if p.name != "Directory.Packages.props":
                    name = p.stem
                    m = re.search(r'<Project\s+Sdk="([^"]+)"', text)
                    if m:
                        deps.add(m.group(1))
                deps.update(re.findall(r'<Package(?:Reference|Version)\s+Include="([^"]+)"', text))
                deps.update(re.findall(r'<Sdk\s+Name="([^"]+)"', text))
            elif p.name == "mix.exs":
                deps.update(re.findall(r"\{:(\w+),", text))
            if not any(pk["dir"] == d for pk in self.packages):
                self.packages.append({"dir": d, "manifests": [p.name], "name": name})
            else:
                for pk in self.packages:
                    if pk["dir"] == d and p.name not in pk["manifests"]:
                        pk["manifests"].append(p.name)
                        pk["name"] = pk["name"] or name
            self.deps[d].update(deps)

    def stack(self):
        out = []
        for pk in self.packages:
            deps = self.deps.get(pk["dir"], set())
            fw = []
            for k, v in FRAMEWORKS.items():
                if any(dep == k or dep.startswith(k + "/") or (k.startswith("spring-boot") and "spring-boot" in dep)
                       or ("." in k and k[0].isupper() and dep.startswith(k)) for dep in deps):
                    if v not in fw:
                        fw.append(v)
            sdk = defaultdict(list)
            for dep in sorted(deps):
                for k, cat in SDK.items():
                    if dep == k or dep.startswith(k + "/") or dep.startswith(k + "-") or (k.endswith(("-", ".")) and dep.startswith(k)) \
                            or (k[:1].isupper() and (dep.startswith(k + ".") or dep == k)) \
                            or (k.startswith(("github.com", "gorm.io", "software.")) and dep.startswith(k)):
                        sdk[cat].append(dep)
                        break
            out.append({"dir": pk["dir"], "name": pk["name"], "manifests": pk["manifests"],
                        "frameworks": fw, "integrations": dict(sdk)})
        return out

    # ----- входы
    def scan_code(self, p, relp, text):
        ext = p.suffix.lower()
        low = relp.lower()
        self.files_by_ext[ext] += 1

        if ext in JS:
            self.js_routes(relp, text)
        if ext in PY:
            self.py_routes(relp, text)
        if ext in GO:
            self.go_routes(relp, text)
        if ext in JVM:
            self.jvm_routes(relp, text)
        if ext in RB:
            self.rb_routes(relp, text)
        if ext in PHP:
            self.php_routes(relp, text)
        if ext in CS:
            self.cs_routes(relp, text)
        if ext in RS:
            self.rs_routes(relp, text)
        if ext in JS | PY | GO | JVM | RB | PHP | CS | RS and ("type Query" in text or "type Mutation" in text):
            self.graphql_sdl(relp, text)
        self.consumers(relp, text, ext)
        self.schedules(relp, text, ext)
        self.cli(relp, text, ext, low)
        self.outbound(relp, text, ext)
        self.sdk_imports(relp, text, ext)
        self.env_vars(relp, text, ext)
        self.data_model(relp, text, ext)
        self.authz_lines(relp, text)
        self.todo_lines(relp, text)

    def js_routes(self, relp, text):
        # Next.js app router: app/**/route.ts; pages router: pages/api/**
        m = re.search(r"(?:^|/)app/(.*)/route\.(?:ts|js|mjs|tsx|jsx)$", relp)
        if m:
            path = "/" + "/".join(seg for seg in m.group(1).split("/") if not re.match(r"^\(.*\)$", seg) and not seg.startswith("@"))
            for mm in re.finditer(r"export\s+(?:async\s+)?(?:function\s+|const\s+)(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\b", text):
                self.add_entry("http", f"{mm.group(1)} {norm_path(path)}", relp, line_of(text, mm.start()), "Next.js route")
            return
        m = re.search(r"(?:^|/)pages/(api/.*)\.(?:ts|js|mjs|tsx|jsx)$", relp)
        if m:
            path = re.sub(r"/index$", "", "/" + m.group(1))
            self.add_entry("http", f"ANY {norm_path(path)}", relp, 1, "Next.js API route")
            return
        # NestJS
        ctrl = re.search(r"@Controller\(\s*(?:\{[^}]*path\s*:\s*)?['\"`]?([^'\"`),}]*)", text)
        if ctrl:
            prefix = ctrl.group(1)
            for mm in re.finditer(r"@(Get|Post|Put|Patch|Delete|All|Head|Options)\(\s*(?:['\"`]([^'\"`]*)['\"`])?", text):
                self.add_entry("http", f"{mm.group(1).upper()} {join_path(prefix, mm.group(2) or '')}", relp,
                               line_of(text, mm.start()), "NestJS")
        # Express / Koa / Fastify / Hono и похожие: app.get('/x', ...), router.post(...)
        for mm in re.finditer(r"\b(app|router|routes|route|server|api|fastify|r|\w+Router|\w+Routes|\w+App)"
                              r"\.(get|post|put|patch|delete|options|head|all)\(\s*['\"`](/[^'\"`]*)['\"`]", text):
            eid = self.add_entry("http", f"{mm.group(2).upper()} {norm_path(mm.group(3))}", relp, line_of(text, mm.start()),
                                 "Express-подобный роутер")
            self.js_router_entries.append((relp, mm.group(1), eid))
        # монтирование роутеров: app.use("/api/orders", auth, ordersRouter) — префикс подставим после прохода
        for mm in re.finditer(r"\.(?:use|register|route)\(\s*['\"`](/[^'\"`]*)['\"`]\s*,(?:[^;]*?,)?\s*(\w+)\s*\)", text):
            self.js_mounts.append((relp, mm.group(1), mm.group(2)))
        for mm in re.finditer(r"import\s+(?:(\w+)|\{([^}]*)\}|\*\s+as\s+(\w+))\s+from\s+['\"](\.[^'\"]+)['\"]", text):
            names = [mm.group(1) or mm.group(3)] if (mm.group(1) or mm.group(3)) else \
                [n.split(" as ")[-1].strip() for n in mm.group(2).split(",") if n.strip()]
            for n in names:
                self.js_imports[(relp, n)] = mm.group(4)
        for mm in re.finditer(r"(?:const|let|var)\s+(\w+)\s*=\s*require\(\s*['\"](\.[^'\"]+)['\"]\s*\)", text):
            self.js_imports[(relp, mm.group(1))] = mm.group(2)
        for mm in re.finditer(r"\.route\(\s*['\"`](/[^'\"`]*)['\"`]\s*\)((?:\s*\.(?:get|post|put|patch|delete)\()+)", text):
            for meth in re.findall(r"\.(get|post|put|patch|delete)\(", mm.group(2)):
                self.add_entry("http", f"{meth.upper()} {norm_path(mm.group(1))}", relp, line_of(text, mm.start()),
                               "Express route()")
        for mm in re.finditer(r"\bfastify\.route\(\s*\{[^}]*method\s*:\s*['\"](\w+)['\"][^}]*url\s*:\s*['\"]([^'\"]+)", text):
            self.add_entry("http", f"{mm.group(1).upper()} {norm_path(mm.group(2))}", relp, line_of(text, mm.start()), "Fastify")
        # tRPC процедуры
        for mm in re.finditer(r"\b(\w+)\s*:\s*\w*[pP]rocedure\b[\s\S]{0,300}?\.(query|mutation|subscription)\(", text):
            self.add_entry("rpc", f"trpc {mm.group(1)} ({mm.group(2)})", relp, line_of(text, mm.start()), "tRPC")

    def py_routes(self, relp, text):
        prefix = ""
        m = re.search(r"(?:APIRouter|Blueprint)\([^)]*?(?:prefix|url_prefix)\s*=\s*['\"]([^'\"]+)", text, re.S)
        if m:
            prefix = m.group(1)
        for mm in re.finditer(r"@(\w+)\.(get|post|put|patch|delete|options|head|route|api_route|websocket)\(\s*['\"]([^'\"]*)['\"]([^\n]*)", text):
            meth = mm.group(2)
            rest = mm.group(4)
            if meth in ("route", "api_route"):
                ms = re.search(r"methods\s*=\s*\[([^\]]*)\]", rest)
                methods = [x.strip(" '\"").upper() for x in ms.group(1).split(",") if x.strip()] if ms else ["GET" if meth == "route" else "ANY"]
            elif meth == "websocket":
                methods = ["WS"]
            else:
                methods = [meth.upper()]
            for me in methods:
                eid = self.add_entry("http", f"{me} {join_path(prefix, mm.group(3))}", relp, line_of(text, mm.start()),
                                     "FastAPI/Flask")
                self.py_router_entries.append((relp, eid))
        for mm in re.finditer(r"\.(?:include_router|register_blueprint)\(\s*([\w.]+)\s*,[^)]*?(?:url_)?prefix\s*=\s*['\"]([^'\"]+)", text):
            self.py_mounts.append((relp, mm.group(1), mm.group(2)))
        if relp.endswith("urls.py"):
            for mm in re.finditer(r"\b(?:re_)?path\(\s*r?['\"]([^'\"]*)['\"]\s*,\s*([\w.]+(?:\.as_view\(\))?)", text):
                if mm.group(2).startswith("include"):
                    continue
                self.add_entry("http", f"ANY {norm_path(mm.group(1))}", relp, line_of(text, mm.start()),
                               f"Django → {mm.group(2)}")
            for mm in re.finditer(r"\.register\(\s*r?['\"]([^'\"]+)['\"]\s*,\s*(\w+)", text):
                self.add_entry("http", f"REST {norm_path(mm.group(1))}", relp, line_of(text, mm.start()),
                               f"DRF router → {mm.group(2)}")

    def go_routes(self, relp, text):
        for mm in re.finditer(r"\b(?:HandleFunc|Handle)\(\s*\"([^\"]+)\"", text):
            pat = mm.group(1)
            m2 = re.match(r"(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\s+(\S+)", pat)
            name = f"{m2.group(1)} {norm_path(m2.group(2))}" if m2 else f"ANY {norm_path(pat)}"
            self.add_entry("http", name, relp, line_of(text, mm.start()), "net/http")
        for mm in re.finditer(r"\.(GET|POST|PUT|PATCH|DELETE|Get|Post|Put|Patch|Delete|Any)\(\s*\"(/[^\"]*)\"", text):
            self.add_entry("http", f"{mm.group(1).upper()} {norm_path(mm.group(2))}", relp, line_of(text, mm.start()),
                           "Gin/Echo/chi/Fiber")

    def jvm_routes(self, relp, text):
        prefix = ""
        cls = re.search(r"\bclass\s+\w+", text)
        for mm in re.finditer(r"@RequestMapping\(\s*(?:value\s*=\s*|path\s*=\s*)?\{?\s*\"([^\"]*)\"", text):
            if cls and mm.start() < cls.start():
                prefix = mm.group(1)
            break
        for mm in re.finditer(r"@(Get|Post|Put|Patch|Delete)Mapping\b(?:\(\s*(?:value\s*=\s*|path\s*=\s*)?\{?\s*\"([^\"]*)\")?", text):
            self.add_entry("http", f"{mm.group(1).upper()} {join_path(prefix, mm.group(2) or '')}", relp,
                           line_of(text, mm.start()), "Spring")
        for mm in re.finditer(r"@RequestMapping\(([^)]*method\s*=\s*\{?\s*RequestMethod\.(\w+)[^)]*)\)", text):
            pm = re.search(r"\"([^\"]*)\"", mm.group(1))
            self.add_entry("http", f"{mm.group(2)} {join_path(prefix, pm.group(1) if pm else '')}", relp,
                           line_of(text, mm.start()), "Spring")
        jax = re.search(r"@Path\(\s*\"([^\"]*)\"\s*\)\s*(?:@\w+(?:\([^)]*\))?\s*)*(?:public\s+)?class", text)
        jprefix = jax.group(1) if jax else ""
        for mm in re.finditer(r"@(GET|POST|PUT|PATCH|DELETE)\b(?:\s*@Path\(\s*\"([^\"]*)\"\s*\))?", text):
            self.add_entry("http", f"{mm.group(1)} {join_path(jprefix, mm.group(2) or '')}", relp,
                           line_of(text, mm.start()), "JAX-RS")
        # Ktor
        for mm in re.finditer(r"\b(get|post|put|patch|delete)\(\s*\"(/[^\"]*)\"\s*\)\s*\{", text):
            self.add_entry("http", f"{mm.group(1).upper()} {norm_path(mm.group(2))}", relp, line_of(text, mm.start()), "Ktor")

    def rb_routes(self, relp, text):
        if not relp.endswith("routes.rb"):
            return
        for mm in re.finditer(r"^\s*(get|post|put|patch|delete|match)\s+['\"]([^'\"]+)['\"]", text, re.M):
            self.add_entry("http", f"{mm.group(1).upper()} {norm_path(mm.group(2))}", relp, line_of(text, mm.start()), "Rails")
        for mm in re.finditer(r"^\s*(resources?)\s+:(\w+)", text, re.M):
            self.add_entry("http", f"REST /{mm.group(2)}", relp, line_of(text, mm.start()), f"Rails {mm.group(1)}")

    def php_routes(self, relp, text):
        for mm in re.finditer(r"Route::(get|post|put|patch|delete|any|match|resource|apiResource)\(\s*['\"]([^'\"]+)['\"]", text):
            meth = mm.group(1)
            meth = "REST" if meth in ("resource", "apiResource") else meth.upper()
            self.add_entry("http", f"{meth} {norm_path(mm.group(2))}", relp, line_of(text, mm.start()), "Laravel")
        for mm in re.finditer(r"#\[Route\(\s*['\"]([^'\"]+)['\"]([^\]]*)\]", text):
            ms = re.search(r"methods:\s*\[([^\]]*)\]", mm.group(2))
            for me in ([x.strip(" '\"").upper() for x in ms.group(1).split(",")] if ms else ["ANY"]):
                self.add_entry("http", f"{me} {norm_path(mm.group(1))}", relp, line_of(text, mm.start()), "Symfony")

    def cs_routes(self, relp, text):
        prefix = ""
        m = re.search(r"\[Route\(\s*\"([^\"]*)\"\s*\)\][\s\S]{0,200}?class\s+(\w+)", text)
        if m:
            prefix = m.group(1).replace("[controller]", re.sub(r"Controller$", "", m.group(2)).lower())
        for mm in re.finditer(r"\[Http(Get|Post|Put|Patch|Delete)(?:\(\s*\"([^\"]*)\"\s*\))?\]", text):
            self.add_entry("http", f"{mm.group(1).upper()} {join_path(prefix, mm.group(2) or '')}", relp,
                           line_of(text, mm.start()), "ASP.NET")
        groups = {}
        for mm in re.finditer(r"(?:var|const)?\s*(\w+)\s*=\s*(\w+)\.MapGroup\(\s*\"([^\"]*)\"", text):
            parent = groups.get(mm.group(2), "")
            groups[mm.group(1)] = join_path(parent, mm.group(3)) if parent else mm.group(3)
        for mm in re.finditer(r"(\w+)\.Map(Get|Post|Put|Patch|Delete)\(\s*\"([^\"]*)\"", text):
            pre = groups.get(mm.group(1), "")
            self.add_entry("http", f"{mm.group(2).upper()} {join_path(pre, mm.group(3)) if pre else norm_path(mm.group(3))}", relp,
                           line_of(text, mm.start()), "ASP.NET minimal API" + (" (MapGroup)" if pre else ""))
        m = re.search(r"\bclass\s+(\w+)Controller\b", text)
        if m and not prefix and relp.endswith(".cs"):
            ctrl = m.group(1)
            for mm in re.finditer(r"\[Http(Get|Post|Put|Patch|Delete)\]", text):
                act = ident_after(text, mm.start(), 4)
                if act:
                    eid = f"{mm.group(1).upper()} /{ctrl}/{act}"
                    self.entries.pop(f"http:{mm.group(1).upper()} /", None)
                    self.add_entry("http", eid, relp, line_of(text, mm.start()), "MVC-контроллер (маршрут по соглашению)")
        if relp.endswith(".razor"):
            for mm in re.finditer(r"^@page\s+\"([^\"]+)\"", text, re.M):
                self.add_entry("ui", norm_path(mm.group(1)), relp, line_of(text, mm.start()), "Blazor @page")

    def rs_routes(self, relp, text):
        for mm in re.finditer(r"\.route\(\s*\"([^\"]+)\"\s*,\s*(get|post|put|patch|delete)", text):
            self.add_entry("http", f"{mm.group(2).upper()} {norm_path(mm.group(1))}", relp, line_of(text, mm.start()), "axum")
        for mm in re.finditer(r"#\[(get|post|put|patch|delete)\(\s*\"([^\"]+)\"", text):
            self.add_entry("http", f"{mm.group(1).upper()} {norm_path(mm.group(2))}", relp, line_of(text, mm.start()), "actix")

    def graphql_sdl(self, relp, text):
        for bm in re.finditer(r"(?:extend\s+)?type\s+(Query|Mutation|Subscription)\s*\{([^}]*)\}", text):
            body_start = bm.start(2)
            for fm in re.finditer(r"^\s*(\w+)\s*[(:]", bm.group(2), re.M):
                self.add_entry("graphql", f"{bm.group(1)}.{fm.group(1)}", relp, line_of(text, body_start + fm.start()), "GraphQL SDL")
        for mm in re.finditer(r"@(Query|Mutation|Subscription)\(", text):
            name = ident_after(text, mm.start(), 3)
            if name:
                self.add_entry("graphql", f"{mm.group(1)}.{name}", relp, line_of(text, mm.start()), "GraphQL code-first")

    def proto(self, relp, text):
        for sm in re.finditer(r"service\s+(\w+)\s*\{([\s\S]*?)\n\}", text):
            for rm in re.finditer(r"rpc\s+(\w+)\s*\(", sm.group(2)):
                self.add_entry("grpc", f"{sm.group(1)}.{rm.group(1)}", relp, line_of(text, sm.start(2) + rm.start()), "gRPC")

    def consumers(self, relp, text, ext):
        rules = [
            (r"@KafkaListener\([^)]*?topics\s*=\s*\{?\s*\"([^\"]+)\"", "kafka", None),
            (r"@RabbitListener\([^)]*?queues\s*=\s*\{?\s*\"([^\"]+)\"", "rabbitmq", None),
            (r"@SqsListener\(\s*(?:value\s*=\s*)?\{?\s*\"([^\"]+)\"", "sqs", None),
            (r"@JmsListener\([^)]*?destination\s*=\s*\"([^\"]+)\"", "jms", None),
            (r"@(?:EventPattern|MessagePattern)\(\s*['\"`]([^'\"`]+)['\"`]", "message", None),
            (r"@Processor\(\s*['\"`]([^'\"`]+)['\"`]", "bull-queue", None),
            (r"new\s+Worker\(\s*['\"`]([^'\"`]+)['\"`]", "bullmq-queue", None),
            (r"\.subscribe\(\s*\{\s*topics?\s*:\s*\[?\s*['\"`]([^'\"`]+)['\"`]", "kafka", None),
            (r"\.consume\(\s*['\"`]([^'\"`]+)['\"`]", "amqp", None),
            (r"KafkaConsumer\(\s*['\"]([^'\"]+)['\"]", "kafka", None),
            (r"\.Subscribe\(\s*\"([^\"]+)\"", "nats", None),
            (r"@OnEvent\(\s*['\"`]([^'\"`]+)['\"`]", "внутреннее событие", "internal"),
            (r"\.on\(\s*['\"`]([a-z][\w.:-]*[.:][\w.:-]+)['\"`]", "внутреннее событие", "internal"),
        ]
        for rx, how, tag in rules:
            for mm in re.finditer(rx, text):
                self.add_entry("consumer", f"{how} {mm.group(1)}", relp, line_of(text, mm.start()), how,
                               [tag] if tag else None)
        if ext in CS:
            for mm in re.finditer(r"class\s+(\w+)\s*(?:\([^)]*\))?\s*:\s*[^{]{0,300}?\bI(?:Integration)?EventHandler<(\w+)>", text):
                self.add_entry("consumer", f"event {mm.group(2)}", relp, line_of(text, mm.start()), f"обработчик интеграционного события → {mm.group(1)}")
            for mm in re.finditer(r"class\s+(\w+)\s*(?:\([^)]*\))?\s*:\s*[^{]{0,300}?\bINotificationHandler<(\w+)>", text):
                self.add_entry("consumer", f"доменное событие {mm.group(2)}", relp, line_of(text, mm.start()),
                               f"MediatR → {mm.group(1)}", ["internal"])
        named = [
            (r"@(?:\w+\.)?(?:task|shared_task)\b(?:\([^)]*\))?", "celery-задача"),
            (r"@dramatiq\.actor\b", "dramatiq-задача"),
            (r"@EventListener\b", "Spring событие"),
            (r"@Process\(", "bull-обработчик"),
        ]
        for rx, how in named:
            for mm in re.finditer(rx, text):
                name = ident_after(text, mm.start())
                if name:
                    self.add_entry("consumer", f"{how} {name}", relp, line_of(text, mm.start()), how,
                                   ["internal"] if "событие" in how else None)
        for rx, how in [(r"class\s+(\w+)[^\n]*\n(?:[^\n]*\n){0,3}?\s*include\s+Sidekiq::(?:Worker|Job)", "sidekiq"),
                        (r"class\s+(\w+)\s*<\s*(?:ApplicationJob|ActiveJob::Base)", "active-job"),
                        (r"class\s+(\w+)[^{\n]*implements[^{\n]*ShouldQueue", "laravel-queue"),
                        (r"class\s+(\w+)\s*:\s*(?:[\w.]+\s*,\s*)*IConsumer<", "masstransit"),
                        (r"class\s+(\w+)(?:<[^>]*>)?\s*(?:\([^)]*\))?\s*:\s*BackgroundService", "background-service")]:
            for mm in re.finditer(rx, text):
                self.add_entry("consumer", f"{how} {mm.group(1)}", relp, line_of(text, mm.start()), how)

    def schedules(self, relp, text, ext):
        for rx, how in [(r"@Scheduled\(([^)]*)\)", "Spring @Scheduled"), (r"@Cron\(\s*([^)]*)\)", "NestJS @Cron"),
                        (r"@(?:\w+\.)?scheduled_job\(([^)]*)\)", "APScheduler"),
                        (r"@(?:periodic_task|cron)\(([^)]*)\)", "periodic")]:
            for mm in re.finditer(rx, text):
                name = ident_after(text, mm.start()) or rel(self.root, relp)
                self.add_entry("schedule", f"{name} [{mm.group(1).strip()[:60]}]", relp, line_of(text, mm.start()), how)
        for rx, how in [(r"cron\.schedule\(\s*['\"`]([^'\"`]+)['\"`]", "node-cron"),
                        (r"new\s+CronJob\(\s*['\"`]([^'\"`]+)['\"`]", "cron"),
                        (r"\.AddFunc\(\s*\"([^\"]+)\"", "robfig/cron"),
                        (r"\$schedule->(?:command|job|call)\(\s*['\"]?([^'\",)]+)", "Laravel scheduler"),
                        (r"RecurringJob\.AddOrUpdate\w*\(\s*\"([^\"]+)\"", "Hangfire"),
                        (r"\.add_job\(\s*(\w+)", "APScheduler"),
                        (r"schedule\.every\([^)]*\)[\w.()]*\.do\(\s*(\w+)", "schedule")]:
            for mm in re.finditer(rx, text):
                self.add_entry("schedule", f"{Path(relp).name} [{mm.group(1).strip()[:80]}] ({how})", relp, line_of(text, mm.start()), how)
        if "beat_schedule" in text:
            for mm in re.finditer(r"['\"]([\w\-. ]+)['\"]\s*:\s*\{\s*['\"]task['\"]\s*:\s*['\"]([\w.]+)['\"]", text):
                self.add_entry("schedule", f"{mm.group(1)} → {mm.group(2)} (celery beat)", relp, line_of(text, mm.start()), "celery beat")

    def schedule_conf(self, relp, text):
        if re.search(r"^kind:\s*CronJob\b", text, re.M):
            for doc in re.split(r"^---\s*$", text, flags=re.M):
                if re.search(r"^kind:\s*CronJob\b", doc, re.M):
                    nm = re.search(r"^\s{2}name:\s*([\w\-.]+)", doc, re.M)
                    sc = re.search(r"schedule:\s*['\"]?([^'\"\n]+)", doc)
                    self.add_entry("schedule", f"{nm.group(1) if nm else relp} [{sc.group(1).strip() if sc else '?'}] (k8s CronJob)",
                                   relp, 1, "Kubernetes CronJob")
        if relp.startswith((".github/workflows/", ".gitlab-ci")) and re.search(r"^\s*-\s*cron:", text, re.M):
            for mm in re.finditer(r"^\s*-\s*cron:\s*['\"]([^'\"]+)['\"]", text, re.M):
                self.add_entry("schedule", f"{relp} [{mm.group(1)}] (CI)", relp, line_of(text, mm.start()), "CI schedule", ["ci"])
        if re.search(r"(^|/)(crontab|cron\.d/[^/]+|\w*\.cron)$", relp):
            for mm in re.finditer(r"^((?:[\d*/,\-]+\s+){4}[\d*/,\-]+)\s+(.+)$", text, re.M):
                self.add_entry("schedule", f"{mm.group(2).strip()[:80]} [{mm.group(1)}]", relp, line_of(text, mm.start()), "crontab")

    def cli(self, relp, text, ext, low):
        m = re.search(r"management/commands/(\w+)\.py$", relp)
        if m and not m.group(1).startswith("_"):
            self.add_entry("cli", f"manage.py {m.group(1)}", relp, 1, "Django command")
        for mm in re.finditer(r"@(?:\w+\.)?command\(\s*(?:(?:name\s*=\s*)?['\"]([\w\-:]+)['\"])?", text):
            if ext in PY:
                name = mm.group(1) or ident_after(text, mm.start())
                if name:
                    self.add_entry("cli", name, relp, line_of(text, mm.start()), "click/typer")
        if ext in PY and re.search(r"ArgumentParser\(", text) and "__main__" in text:
            self.add_entry("cli", f"python {relp}", relp, line_of(text, text.find("ArgumentParser(")), "argparse")
        if ext in GO:
            for mm in re.finditer(r"&cobra\.Command\{[\s\S]{0,200}?Use:\s*\"([^\"]+)\"", text):
                self.add_entry("cli", mm.group(1).split()[0], relp, line_of(text, mm.start()), "cobra")
            if re.search(r"^package main\b", text, re.M) and re.search(r"\bfunc main\(\)", text) and "/cmd/" in "/" + relp:
                self.add_entry("cli", f"go run ./{Path(relp).parent.as_posix()}", relp, line_of(text, text.find("func main(")), "Go main")
        if ext in JS:
            for mm in re.finditer(r"\.command\(\s*['\"`]([\w\-:]+)", text):
                if "commander" in text or "yargs" in text or "program." in text:
                    self.add_entry("cli", mm.group(1), relp, line_of(text, mm.start()), "commander/yargs")
        if ext in RB and (relp.endswith(".rake") or relp.endswith("Rakefile")):
            for mm in re.finditer(r"^\s*task\s+:?['\"]?(\w+)", text, re.M):
                self.add_entry("cli", f"rake {mm.group(1)}", relp, line_of(text, mm.start()), "rake")
        if ext in PHP:
            for mm in re.finditer(r"protected\s+\$signature\s*=\s*['\"]([^'\" {]+)", text):
                self.add_entry("cli", f"artisan {mm.group(1)}", relp, line_of(text, mm.start()), "artisan")
            for mm in re.finditer(r"#\[AsCommand\(\s*(?:name:\s*)?['\"]([^'\"]+)['\"]", text):
                self.add_entry("cli", mm.group(1), relp, line_of(text, mm.start()), "Symfony console")
        if ext in JVM:
            for mm in re.finditer(r"class\s+(\w+)[^{]*implements[^{]*(?:CommandLineRunner|ApplicationRunner)", text):
                self.add_entry("cli", f"при старте: {mm.group(1)}", relp, line_of(text, mm.start()), "Spring runner")

    # ----- выходы
    CALL_RX = re.compile(
        r"\bfetch\(|\baxios(?:\.\w+)?\(|\bgot(?:\.\w+)?\(|\bky(?:\.\w+)?\(|\bsuperagent\b|\bundici\b|\brequest\(\s*\{|"
        r"\brequests\.(?:get|post|put|patch|delete|request|Session)\b|\bhttpx\.(?:\w+)\b|\baiohttp\.ClientSession|"
        r"\burllib\.request\.urlopen|\burlopen\(|\bhttp\.(?:Get|Post|PostForm|NewRequest\w*)\(|\bresty\.|"
        r"\bRestTemplate\b|\bWebClient\b|@FeignClient\b|\bRestClient\b|\bOkHttpClient\b|\bHttpClient\b|"
        r"\bFaraday\.|\bNet::HTTP\b|\bHTTParty\b|\bRestClient\.|\bHttp::(?:get|post|put|patch|delete|withToken|withHeaders|acceptJson)\b|"
        r"\bGuzzleHttp\b|\bcurl_init\(|\breqwest::|\bnew\s+WebSocket\(|\bnodemailer\.createTransport|\bsmtplib\.SMTP|"
        r"\bgrpc\.(?:Dial|NewClient)\(|\bnew\s+\w+Client\(")
    SVC_RX = re.compile(r"(?:https?\+https?|https?)://([a-z][a-z0-9-]*-(?:api|service|svc|server|worker|gateway|app|processor))\b")
    COMMENT_LINE = ("//", "#", "*", "/*", "<!--", "--", "\'\'\'", '\"\"\"')
    URL_RX = re.compile(r"""(?:https?|wss?|amqps?|redis|postgres(?:ql)?|mongodb(?:\+srv)?|mysql|kafka)://([A-Za-z0-9][A-Za-z0-9.\-]*\.[A-Za-z]{2,}|[A-Za-z0-9\-]+:\d+)""")
    ENV_ON_LINE = re.compile(r"(?:process\.env\.|process\.env\[['\"]|os\.environ(?:\.get)?\(?\[?['\"]|os\.getenv\(['\"]|"
                             r"System\.getenv\(\"|os\.Getenv\(\"|ENV\[['\"]|ENV\.fetch\(['\"]|env\(['\"]|"
                             r"import\.meta\.env\.|Environment\.GetEnvironmentVariable\(\")([A-Z][A-Z0-9_]{2,})")

    def outbound(self, relp, text, ext):
        is_test = self.is_test(relp)
        for i, ln in enumerate(text.splitlines(), 1):
            if len(self.calls) < CAP_CALLS and self.CALL_RX.search(ln) and not is_test:
                hm = self.URL_RX.search(ln)
                em = self.ENV_ON_LINE.search(ln)
                self.calls.append({"file": relp, "line": i, "code": ln.strip()[:160],
                                   "host": hm.group(1) if hm else None, "env": em.group(1) if em else None})
            if ln.lstrip().startswith(self.COMMENT_LINE):
                continue   # ссылки в комментариях — документация, не интеграции
            for hm in self.URL_RX.finditer(ln):
                if re.search(r"(?:href|src|action)\s*=\s*[\"']?[^\"'\s]*$", ln[:hm.start()]):
                    continue   # ссылка в разметке — переход пользователя, не вызов
                self.add_host(hm.group(1), relp, i, is_test)
            for hm in self.SVC_RX.finditer(ln):
                self.add_host(hm.group(1) + " (сервис по имени)", relp, i, is_test)

    def add_host(self, host, relp, line, is_test=False):
        h = host.lower().rstrip(".")
        name = h.split(":")[0].split(" ")[0]
        if NOISE_HOSTS.search(name) or re.match(r"^\d+\.\d+\.\d+\.\d+$", name) or name.endswith((".example", ".local", ".test", ".invalid")):
            return
        if ":" in h and (len(name) < 3 or name in ("host", "hostname", "server", "domain", "your-host")):
            return
        rec = self.hosts[h]
        rec["count"] += 1
        loc = f"{relp}:{line}" + (" (тест)" if is_test else "")
        if len(rec["files"]) < 6 and loc not in rec["files"]:
            rec["files"].append(loc)

    ENV_RX = [
        re.compile(r"process\.env\.([A-Z][A-Z0-9_]{1,})"), re.compile(r"process\.env\[['\"]([A-Z][A-Z0-9_]+)['\"]\]"),
        re.compile(r"import\.meta\.env\.([A-Z][A-Z0-9_]+)"),
        re.compile(r"os\.environ(?:\.get)?\(?\[?\s*['\"]([A-Z][A-Z0-9_]+)['\"]"), re.compile(r"os\.getenv\(\s*['\"]([A-Z][A-Z0-9_]+)['\"]"),
        re.compile(r"(?:env|config)\(\s*['\"]([A-Z][A-Z0-9_]+)['\"]"), re.compile(r"System\.getenv\(\s*\"([A-Z][A-Z0-9_]+)\""),
        re.compile(r"os\.(?:Getenv|LookupEnv)\(\s*\"([A-Z][A-Z0-9_]+)\""), re.compile(r"ENV(?:\.fetch\(|\[)\s*['\"]([A-Z][A-Z0-9_]+)['\"]"),
        re.compile(r"Environment\.GetEnvironmentVariable\(\s*\"([A-Z][A-Z0-9_]+)\""),
        re.compile(r"(?:Configuration|configuration|config|section|Section)\s*\[\s*\"([\w:]+)\"\s*\]"),
        re.compile(r"\.(?:GetRequiredValue|GetValue<[\w?]+>)\(\s*\"([\w:]+)\""),
        re.compile(r"GetConnectionString\(\s*\"([\w-]+)\"\)"),
        re.compile(r"env::var\(\s*\"([A-Z][A-Z0-9_]+)\""), re.compile(r"@Value\(\s*\"\$\{([\w.\-]+)"),
        re.compile(r"(?:Field|BaseSettings)[\s\S]{0,0}env\s*=\s*['\"]([A-Z][A-Z0-9_]+)['\"]"),
    ]

    def env_vars(self, relp, text, ext):
        for rx in self.ENV_RX:
            for mm in rx.finditer(text):
                name = mm.group(1)
                if "GetConnectionString" in rx.pattern:
                    name = f"ConnectionStrings:{name}"
                self.add_env(name, relp, line_of(text, mm.start()))

    def env_conf(self, relp, text):
        name = Path(relp).name.lower()
        if re.match(r"^\.?env(\..*)?$|.*\.env(\..*)?$", name) or name.endswith((".env.example", ".env.sample")):
            if re.match(r"^\.env(\.local|\.production|\.prod|\.development)?$", name):
                return  # настоящие .env не читаем: там значения секретов
            for mm in re.finditer(r"^\s*(?:export\s+)?([A-Z][A-Z0-9_]{1,})\s*=", text, re.M):
                self.add_env(mm.group(1), relp, line_of(text, mm.start()))
        elif re.match(r"^(docker-)?compose.*\.ya?ml$", name) or "/helm/" in "/" + relp or "k8s" in relp or "deploy" in relp:
            for mm in re.finditer(r"^\s*-?\s*(?:name:\s*)?([A-Z][A-Z0-9_]{2,})\s*[:=]", text, re.M):
                self.add_env(mm.group(1), relp, line_of(text, mm.start()))
            for mm in self.URL_RX.finditer(text):
                self.add_host(mm.group(1), relp, line_of(text, mm.start()))
        elif name in ("application.yml", "application.yaml", "application.properties", "appsettings.json", "settings.py",
                      "config.yaml", "config.yml", "config.json", "default.json", "production.json"):
            for mm in self.URL_RX.finditer(text):
                self.add_host(mm.group(1), relp, line_of(text, mm.start()))
            for mm in re.finditer(r"\$\{([A-Z][A-Z0-9_]{2,})", text):
                self.add_env(mm.group(1), relp, line_of(text, mm.start()))

    def add_env(self, name, relp, line):
        rec = self.env[name]
        loc = f"{relp}:{line}"
        if len(rec["files"]) < 5 and loc not in rec["files"]:
            rec["files"].append(loc)

    # ----- данные и права
    def data_model(self, relp, text, ext):
        rules = [
            (r"^model\s+(\w+)\s*\{", "Prisma", {".prisma"}),
            (r"class\s+(\w+)\s*\(\s*(?:[\w.]*\.)?(?:Model|AbstractUser|TimeStampedModel)\s*\)", "Django", PY),
            (r"class\s+(\w+)\s*\([^)]*\b(?:Base|SQLModel|Model)\b[^)]*\)\s*:(?:(?!\nclass\s)[\s\S]){0,1500}?__tablename__", "SQLAlchemy", PY),
            (r"@Entity\b[\s\S]{0,300}?\bclass\s+(\w+)", "JPA/TypeORM", JVM | JS | CS),
            (r"(?:mongoose\.)?model\(\s*['\"](\w+)['\"]\s*,", "Mongoose", JS),
            (r"\.define\(\s*['\"](\w+)['\"]\s*,\s*\{", "Sequelize", JS),
            (r"(?:pgTable|mysqlTable|sqliteTable)\(\s*['\"](\w+)['\"]", "Drizzle", JS),
            (r"class\s+(\w+)\s*<\s*(?:ApplicationRecord|ActiveRecord::Base)", "ActiveRecord", RB),
            (r"class\s+(\w+)\s+extends\s+(?:Model|Authenticatable)\b", "Eloquent", PHP),
            (r"type\s+(\w+)\s+struct\s*\{[^}]*gorm\.Model", "GORM", GO),
            (r"DbSet<(\w+)>", "EF Core", CS),
            (r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[`\"\[]?(?:\w+[`\"\]]?\.)?[`\"\[]?(\w+)", "SQL", {".sql"}),
        ]
        for rx, how, exts in rules:
            if ext not in exts:
                continue
            for mm in re.finditer(rx, text, re.M | re.I if how == "SQL" else re.M):
                name = mm.group(1)
                key = name.lower()
                if key in self.entities:
                    loc = f"{relp}:{line_of(text, mm.start())}"
                    if loc not in self.entities[key]["also"] and len(self.entities[key]["also"]) < 5:
                        self.entities[key]["also"].append(loc)
                    continue
                self.entities[key] = {"name": name, "how": how, "file": relp, "line": line_of(text, mm.start()), "also": []}
        # перечисления статусов, ролей, типов — материал для состояний и прав
        for mm in re.finditer(r"\benum\s+(\w*(?:Status|State|Stage|Role|Type|Kind|Phase)\w*)\s*(?::\s*\w+\s*)?\{([^}]{0,1500})\}", text):
            vals = re.findall(r"^\s*([A-Za-z_]\w*)", mm.group(2), re.M)
            self.enums.append({"name": mm.group(1), "file": relp, "line": line_of(text, mm.start()), "values": vals[:30]})
        if ext in PY:
            for mm in re.finditer(r"class\s+(\w*(?:Status|State|Stage|Role|Type|Kind|Phase)\w*)\s*\([^)]*(?:Enum|TextChoices|IntegerChoices)[^)]*\)\s*:\s*\n((?:[ \t]+.*\n?)+)", text):
                vals = re.findall(r"^\s+([A-Z_][A-Z0-9_]*)\s*=", mm.group(2), re.M)
                self.enums.append({"name": mm.group(1), "file": relp, "line": line_of(text, mm.start()), "values": vals[:30]})
        if ext in JS:
            for mm in re.finditer(r"(?:type|const)\s+(\w*(?:Status|State|Stage|Role|Phase)\w*)\s*=\s*((?:['\"][\w\-]+['\"]\s*\|?\s*){2,})", text):
                vals = re.findall(r"['\"]([\w\-]+)['\"]", mm.group(2))
                self.enums.append({"name": mm.group(1), "file": relp, "line": line_of(text, mm.start()), "values": vals[:30]})

    AUTHZ_RX = re.compile(r"@Roles\(|@PreAuthorize\(|@Secured\(|@RolesAllowed\(|hasRole\(|hasAuthority\(|hasPermission\(|"
                          r"@UseGuards\(|@permission_required|@login_required|permission_classes\s*=|IsAuthenticated|IsAdminUser|"
                          r"\bauthorize[!(]|\bcan\?\(|Gate::|->can\(|\[Authorize|\bRequireAuth|requireRole\(|checkPermission\(|"
                          r"\bisAdmin\b|\brole\s*===?\s*['\"]|\.role\s*(?:==|!=|in)\s*|\w*[rR]ole\s*(?:===?|!==?)\s*['\"]|"
                          r"\brequire_?(?:admin|role|auth|login|permission|user)\w*\b|\b(?:owner|author|user)(?:_id|Id)\s*(?:!==?|===?)\s*\w")

    def authz_lines(self, relp, text):
        if len(self.authz) >= CAP_AUTHZ or self.is_test(relp):
            return
        for i, ln in enumerate(text.splitlines(), 1):
            if self.AUTHZ_RX.search(ln):
                self.authz.append({"file": relp, "line": i, "code": ln.strip()[:160]})
                if len(self.authz) >= CAP_AUTHZ:
                    break

    def todo_lines(self, relp, text):
        if len(self.todos) >= CAP_TODOS:
            return
        for i, ln in enumerate(text.splitlines(), 1):
            m = re.search(r"(?:#|//|/\*|^\s*\*|--|<!--)[^\n]*?\b(TODO|FIXME|HACK|XXX)\b[:\s(]*(.*)", ln)
            if m:
                self.todos.append({"file": relp, "line": i, "tag": m.group(1), "text": m.group(2).strip()[:160]})
                if len(self.todos) >= CAP_TODOS:
                    break

    # ----- тесты и документы
    TEST_PATH = re.compile(r"(^|/)(tests?|__tests__|spec|specs|e2e|cypress|playwright|integration|it)(/|$)|"
                           r"\.(test|spec|e2e|cy)\.[jt]sx?$|(^|/)test_[^/]+\.py$|_test\.(py|go)$|Tests?\.(java|kt|cs)$|_spec\.rb$|Test\.php$")

    def is_test(self, relp):
        return bool(self.TEST_PATH.search(relp))

    def scan_tests(self, relp, text, ext):
        if not self.is_test(relp) or ext not in CODE_EXT:
            return
        titles = []
        rx = {
            "js": r"\b(?:it|test|describe|context|scenario)(?:\.\w+)?\(\s*['\"`]([^'\"`]{3,})['\"`]",
            "py": r"^\s*(?:async\s+)?def\s+(test_\w+)",
            "go": r"^func\s+(Test\w+)",
            "rb": r"^\s*(?:it|describe|context|scenario)\s+['\"]([^'\"]+)['\"]",
            "jvm": r"@(?:Test|ParameterizedTest)\b[\s\S]{0,200}?(?:fun|void)\s+`?([^`(]+)`?\s*\(|@DisplayName\(\s*\"([^\"]+)\"",
            "cs": r"\[(?:Fact|Theory|Test|TestMethod)\][\s\S]{0,200}?\s(\w+)\s*\(",
            "php": r"function\s+(test\w+)\s*\(|\b(?:it|test)\(\s*['\"]([^'\"]+)['\"]",
        }
        key = "js" if ext in JS else "py" if ext in PY else "go" if ext in GO else "rb" if ext in RB else \
            "jvm" if ext in JVM else "cs" if ext in CS else "php" if ext in PHP else None
        if key:
            for mm in re.finditer(rx[key], text, re.M):
                t = next((g for g in mm.groups() if g), None)
                if t:
                    titles.append(t.strip())
        kind = "e2e" if re.search(r"(^|/)(e2e|cypress|playwright)(/|$)|\.(e2e|cy)\.", relp) else "unit/integration"
        if self.test_titles >= CAP_TEST_TITLES:
            titles = []
        shown = titles[:CAP_TESTS_PER_FILE]
        self.test_titles += len(shown)
        stubs = len(re.findall(r"expect\(\s*true\s*\)\.toBe\(\s*true\s*\)|^\s*assert\s+True\s*$|assertTrue\(\s*true\s*\)|"
                               r"assert\.ok\(\s*true\s*\)|t\.Skip\(|\.skip\(|@pytest\.mark\.skip|@Disabled|xit\(", text, re.M))
        self.tests.append({"file": relp, "kind": kind, "count": len(titles), "titles": shown, "stubs": stubs})

    def scan_doc(self, p, relp, text):
        name = p.name.lower()
        if name.endswith((".md", ".mdx", ".rst", ".adoc", ".txt")) and (
                relp.count("/") == 0 or re.search(r"(^|/)(docs?|documentation|adr|adrs|rfcs?|wiki|spec|specs|requirements)(/|$)", relp.lower())
                or name.startswith(("readme", "architecture", "contributing", "changelog"))):
            if name.endswith(".txt") and not re.search(r"(^|/)(docs?|spec|requirements)/", relp.lower()):
                return
            head = re.search(r"^#\s+(.+)$", text, re.M)
            self.docs.append({"file": relp, "title": head.group(1).strip()[:120] if head else "", "lines": text.count("\n") + 1})
        if re.search(r"(openapi|swagger)[^/]*\.(ya?ml|json)$", name) or (
                name.endswith((".yaml", ".yml", ".json")) and re.search(r"^\s*['\"]?(openapi|swagger)['\"]?\s*:", text[:2000], re.M)):
            self.parse_openapi(relp, text)

    def parse_openapi(self, relp, text):
        paths = []
        try:
            js = json.loads(text)
            for path, ops in (js.get("paths") or {}).items():
                for meth in ops:
                    if meth.lower() in HTTP_METHODS:
                        paths.append(f"{meth.upper()} {norm_path(path)}")
        except ValueError:
            m = re.search(r"^paths:\s*\n((?:[ \t]+.*\n?|\s*\n)*)", text, re.M)
            if m:
                cur = None
                for ln in m.group(1).splitlines():
                    pm = re.match(r"^  ['\"]?(/[^'\":]*)['\"]?\s*:\s*$", ln)
                    if pm:
                        cur = pm.group(1)
                        continue
                    mm = re.match(r"^    (get|post|put|patch|delete|options|head)\s*:", ln)
                    if mm and cur:
                        paths.append(f"{mm.group(1).upper()} {norm_path(cur)}")
        self.openapi.append({"file": relp, "operations": paths})

    def resolve_js(self, from_file, spec):
        base = (Path(from_file).parent / spec).as_posix()
        base = os.path.normpath(base).replace(os.sep, "/")
        cands = [base] + [base + e for e in (".ts", ".tsx", ".js", ".mjs", ".cjs", ".jsx")] + \
                [base + "/index" + e for e in (".ts", ".js", ".mjs")]
        base_noext = re.sub(r"\.(js|mjs|cjs)$", "", base)
        cands += [base_noext + e for e in (".ts", ".tsx")]
        for c in cands:
            if (self.root / c).is_file():
                return c
        return None

    def apply_py_mounts(self):
        """Префиксы FastAPI/Flask: app.include_router(payments.router, prefix="/api/payments") → префикс у входов модуля payments."""
        renamed = OrderedDict()
        for f, ident, pre in self.py_mounts:
            parts = [x for x in ident.split(".") if x not in ("router", "bp", "blueprint", "api", "routes", "views")]
            stem = parts[-1] if parts else ""
            for rf, eid in self.py_router_entries:
                if eid not in self.entries or not stem or Path(rf).stem != stem:
                    continue
                e = self.entries[eid]
                meth, path = e["name"].split(" ", 1)
                if path.startswith(pre.rstrip("/") + "/") or path == pre.rstrip("/"):
                    continue
                self.entries.pop(eid)
                e2 = dict(e, also=list(e["also"]))
                e2["name"] = f"{meth} {join_path(pre, path)}".rstrip("/") if path != "/" else f"{meth} {pre.rstrip('/')}"
                e2["id"] = f"http:{e2['name']}"
                renamed[e2["id"]] = e2
        self.entries.update(renamed)

    def apply_js_mounts(self):
        """Префиксы роутеров Express: app.use('/api/orders', ordersRouter) → /api/orders + путь из файла роутера."""
        if not self.js_mounts:
            return
        # (файл роутера, имя переменной в нём или None) -> список (файл, где смонтирован, префикс)
        targets = defaultdict(list)
        for f, prefix, ident in self.js_mounts:
            spec = self.js_imports.get((f, ident))
            tfile = self.resolve_js(f, spec) if spec else f
            if tfile:
                targets[tfile].append((ident if tfile == f else None, f, prefix))

        def prefixes(file, ident, depth=0):
            if depth > 5:
                return [""]
            out = []
            for mident, mfile, pre in targets.get(file, []):
                if mident is not None and ident is not None and mident != ident:
                    continue
                if mident is None and mfile == file:
                    continue
                parents = prefixes(mfile, None, depth + 1) if mfile != file else [""]
                out += [join_path(pp, pre) if pp else pre for pp in parents]
            return out or [""]

        renamed = OrderedDict()
        for f, ident, eid in self.js_router_entries:
            if ident == "app" or eid not in self.entries:
                continue
            pres = [p for p in prefixes(f, ident) if p]
            if not pres:
                continue
            e = self.entries.pop(eid)
            meth, path = e["name"].split(" ", 1)
            for pre in pres:
                e2 = dict(e, also=list(e["also"]))
                e2["name"] = f"{meth} {join_path(pre, path)}"
                e2["id"] = f"http:{e2['name']}"
                renamed[e2["id"]] = e2
        self.entries.update(renamed)

    def sdk_imports(self, relp, text, ext):
        """Импорты SDK внешних сервисов: где в коде используется Stripe, S3, почта и т.п."""
        if ext in JS:
            rx = r"(?:from\s+['\"]|require\(\s*['\"]|import\s+['\"])((?:@[\w.\-]+/)?[\w.\-]+)"
        elif ext in PY:
            rx = r"^\s*(?:from\s+([\w]+)[\w.]*\s+import|import\s+([\w]+))"
        elif ext in GO:
            rx = r"\"((?:github\.com|gorm\.io|cloud\.google\.com|go\.mongodb\.org)/[\w.\-/]+)\""
        elif ext in JVM:
            rx = r"^import\s+([\w.]+)"
        elif ext in CS:
            rx = r"^\s*(?:global\s+)?using\s+(?:static\s+)?([\w.]+)\s*;"
        else:
            return
        for mm in re.finditer(rx, text, re.M):
            mod = next(g for g in mm.groups() if g)
            modl = mod.lower().replace("_", "-")
            for k, cat in SDK.items():
                kl = k.lower()
                if modl == kl or modl.startswith(kl + "/") or modl.startswith(kl + ".") or (kl.endswith(("-", ".")) and modl.startswith(kl)):
                    if cat in ("мониторинг",):
                        break
                    ln = line_of(text, mm.start())
                    if not any(u["file"] == relp and u["sdk"] == k for u in self.sdk_uses):
                        self.sdk_uses.append({"file": relp, "line": ln, "sdk": k, "module": mod, "category": cat})
                    break

    # ----- проход
    def run(self):
        files = list(walk(self.root))
        self.scan_manifests(files)
        self.packages.sort(key=lambda x: x["dir"])
        for p in files:
            relp = rel(self.root, p)
            ext = p.suffix.lower()
            if ext in CODE_EXT or ext in {".graphql", ".gql", ".proto", ".prisma", ".sql"} or p.name in ("Rakefile", "crontab"):
                text = read(p)
                if not text:
                    continue
                if ext in {".graphql", ".gql"}:
                    self.graphql_sdl(relp, text)
                elif ext == ".proto":
                    self.proto(relp, text)
                elif ext in {".prisma", ".sql"}:
                    self.files_by_ext[ext] += 1
                    self.data_model(relp, text, ext)
                    if ext == ".sql" and re.search(r"(^|/)(migrations?|migrate|db/migrate|flyway|liquibase|changelog)(/|$)", relp):
                        self.migrations[Path(relp).parent.as_posix()] += 1
                    continue
                elif self.is_test(relp):
                    self.files_by_ext[ext] += 1
                    self.scan_tests(relp, text, ext)
                    self.outbound(relp, text, ext)  # хосты из тестов помечаются «(тест)»
                    continue
                else:
                    self.scan_code(p, relp, text)
                if re.search(r"(^|/)(migrations?|alembic/versions|db/migrate|database/migrations)(/|$)", relp):
                    self.migrations[Path(relp).parent.as_posix()] += 1
            if ext in CONF_EXT or p.name.lower().startswith((".env", "docker-compose", "compose")) or "crontab" in p.name or ext == ".cron":
                text = read(p)
                self.env_conf(relp, text)
                self.schedule_conf(relp, text)
            if ext in {".md", ".mdx", ".rst", ".adoc", ".txt", ".yaml", ".yml", ".json"}:
                self.scan_doc(p, relp, read(p))
        self.apply_js_mounts()
        self.apply_py_mounts()
        # один и тот же CLI: скрипт из pyproject (app.cli:main) и `python app/cli.py` — оставить скрипт
        targets = {e["how"].split("→", 1)[-1].strip() for e in self.entries.values() if e["how"].startswith("pyproject scripts")}
        for eid in [i for i, e in self.entries.items() if e["how"] == "argparse"]:
            mod = re.sub(r"\.py$", "", self.entries[eid]["file"]).replace("/", ".")
            if any(t == mod or t.endswith("." + mod) or mod.endswith("." + t) or mod == t for t in targets):
                del self.entries[eid]
        for e in self.entries.values():
            if e["kind"] == "http" and re.search(r"webhook|callback|/hooks?(/|$)|notify|ipn", e["name"], re.I):
                e["tags"] = sorted(set(e["tags"]) | {"webhook"})
            if e["kind"] == "http" and re.search(r"/(health|healthz|ready|readyz|live|livez|ping|metrics|status)(/|$)", e["name"], re.I):
                e["tags"] = sorted(set(e["tags"]) | {"служебное"})
        return self

    def result(self):
        env = OrderedDict()
        for k in sorted(self.env):
            tags = []
            if re.search(r"KEY|SECRET|TOKEN|PASSWORD|PASSWD|PASS\b|PRIVATE|CREDENTIAL|DSN", k):
                tags.append("секрет")
            if re.search(r"FEATURE|FLAG|ENABLE|DISABLE|TOGGLE|EXPERIMENT", k):
                tags.append("флаг")
            if re.search(r"URL|HOST|ENDPOINT|URI|ADDR|BASE", k):
                tags.append("адрес")
            env[k] = {"files": self.env[k]["files"], "tags": tags}
        hosts = OrderedDict(sorted(self.hosts.items(), key=lambda kv: -kv[1]["count"]))
        code_files = sum(v for k, v in self.files_by_ext.items() if k in CODE_EXT)
        openapi_ops = sorted({op for o in self.openapi for op in o["operations"]})
        code_http = {e["name"] for e in self.entries.values() if e["kind"] == "http"}
        return OrderedDict([
            ("version", VERSION), ("root", self.root.name),
            ("summary", OrderedDict([
                ("code_files", code_files),
                ("files_by_ext", dict(sorted(self.files_by_ext.items(), key=lambda kv: -kv[1]))),
                ("entries", dict(sorted(((k, sum(1 for e in self.entries.values() if e["kind"] == k))
                                         for k in {e["kind"] for e in self.entries.values()}), key=lambda kv: -kv[1]))),
                ("outbound_calls", len(self.calls)), ("external_hosts", len(hosts)), ("env_vars", len(env)),
                ("entities", len(self.entities)), ("enums", len(self.enums)), ("test_files", len(self.tests)),
                ("docs", len(self.docs)), ("todos", len(self.todos)),
            ])),
            ("stack", self.stack()),
            ("entries", list(self.entries.values())),
            ("outbound", OrderedDict([("calls", self.calls), ("hosts", hosts), ("sdk", self.sdk_uses)])),
            ("env", env),
            ("entities", list(self.entities.values())),
            ("enums", self.enums),
            ("migrations", dict(self.migrations)),
            ("authz", self.authz),
            ("tests", self.tests),
            ("docs", self.docs),
            ("openapi", OrderedDict([("files", [o["file"] for o in self.openapi]),
                                     ("only_in_openapi", [op for op in openapi_ops if op not in code_http])])),
            ("todos", self.todos),
            ("openspec_exists", (self.root / "openspec").is_dir()),
            ("warnings", self.warnings),
        ])


def md_escape(s):
    return str(s).replace("|", "\\|")


def to_markdown(r):
    s = r["summary"]
    out = [f"# Опись репозитория `{r['root']}`", "",
           "Собрано `inventory.py scan` эвристиками: пропуски возможны, лишнее тоже. Полные данные — `inventory.json`,",
           "выборка — `inventory.py show <repo> --kind <вид> --grep <текст>`.", "",
           "## Сводка", "",
           f"- файлов кода: {s['code_files']}; входов: " + (", ".join(f"{k} {v}" for k, v in s["entries"].items()) or "не найдено"),
           f"- исходящих вызовов: {s['outbound_calls']}; внешних хостов: {s['external_hosts']}; переменных окружения: {s['env_vars']}",
           f"- сущностей: {s['entities']}; перечислений статусов и ролей: {s['enums']}; файлов тестов: {s['test_files']}; "
           f"документов: {s['docs']}; TODO/FIXME: {s['todos']}", ""]
    out += ["## Стек и пакеты", "", "| Папка | Имя | Фреймворки | Внешние сервисы по зависимостям |", "|---|---|---|---|"]
    for pk in r["stack"]:
        integ = "; ".join(f"{c}: {', '.join(v)}" for c, v in pk["integrations"].items())
        out.append(f"| `{pk['dir']}` | {md_escape(pk['name'] or '')} | {', '.join(pk['frameworks'])} | {md_escape(integ)} |")
    out += ["", "## Точки входа", ""]
    kinds = OrderedDict()
    for e in r["entries"]:
        kinds.setdefault(e["kind"], []).append(e)
    titles = {"http": "HTTP", "graphql": "GraphQL", "grpc": "gRPC", "rpc": "RPC", "consumer": "Очереди, события, фоновые задачи",
              "schedule": "Расписания", "cli": "Команды (CLI)"}
    for k, items in kinds.items():
        out += [f"### {titles.get(k, k)} ({len(items)})", "", "| id | где | как найдено | метки |", "|---|---|---|---|"]
        for e in items:
            extra = f" (+{len(e['also'])})" if e["also"] else ""
            out.append(f"| `{md_escape(e['id'])}` | `{e['file']}:{e['line']}`{extra} | {md_escape(e['how'])} | {', '.join(e['tags'])} |")
        out.append("")
    if not kinds:
        out += ["Не найдено ни одной — стек не распознан. Найди входы вручную и добавь: `plan.py add-entry`.", ""]
    if r["openapi"]["files"]:
        out += ["## OpenAPI", "", "Файлы: " + ", ".join(f"`{f}`" for f in r["openapi"]["files"])]
        only = r["openapi"]["only_in_openapi"]
        if only:
            out += ["", f"Есть в OpenAPI, но не найдено в коде ({len(only)}) — проверь вручную или в вопросы:", ""]
            out += [f"- `{op}`" for op in only[:80]]
        out.append("")
    out += ["## Внешние хосты", "", "| Хост | Упоминаний | Где |", "|---|---|---|"]
    test_only = []
    for h, rec in list(r["outbound"]["hosts"].items())[:200]:
        if rec["files"] and all("(тест)" in f for f in rec["files"]):
            test_only.append(h)
            continue
        out.append(f"| `{h}` | {rec['count']} | {', '.join(f'`{x}`' for x in rec['files'][:3])} |")
    if test_only:
        out += ["", "Только в тестах (обычно заглушки): " + ", ".join(f"`{h}`" for h in test_only[:40])]
    if r["outbound"].get("sdk"):
        out += ["", "## SDK внешних сервисов в коде", "", "| Категория | Пакет | Где импортируется |", "|---|---|---|"]
        grp = OrderedDict()
        for u in r["outbound"]["sdk"]:
            grp.setdefault((u["category"], u["sdk"]), []).append(f"{u['file']}:{u['line']}")
        for (cat, sdk), locs in sorted(grp.items()):
            out.append(f"| {cat} | `{sdk}` | {', '.join(f'`{x}`' for x in locs[:6])}{' …' if len(locs) > 6 else ''} |")
    out += ["", f"## Исходящие вызовы ({len(r['outbound']['calls'])})", "",
            "Строки с HTTP-клиентами и SDK. Полный список — `show --section outbound`.", ""]
    by_file = OrderedDict()
    for c in r["outbound"]["calls"]:
        by_file.setdefault(c["file"], []).append(c)
    for f, cs in list(by_file.items())[:120]:
        hints = sorted({c["host"] or c["env"] for c in cs if c["host"] or c["env"]})
        out.append(f"- `{f}` — {len(cs)}: строки {', '.join(str(c['line']) for c in cs[:8])}" + (f"; {', '.join(hints)}" if hints else ""))
    out += ["", "## Переменные окружения", "", "Только имена — значения скилл не читает.", "", "| Имя | Метки | Где |", "|---|---|---|"]
    for k, v in r["env"].items():
        out.append(f"| `{k}` | {', '.join(v['tags'])} | {', '.join(f'`{x}`' for x in v['files'][:2])} |")
    out += ["", "## Данные", "", "| Сущность | Как найдено | Где |", "|---|---|---|"]
    for e in r["entities"]:
        out.append(f"| `{e['name']}` | {e['how']} | `{e['file']}:{e['line']}` |")
    if r["enums"]:
        out += ["", "Статусы, роли, типы:", ""]
        for e in r["enums"]:
            out.append(f"- `{e['name']}` (`{e['file']}:{e['line']}`): {', '.join(e['values'])}")
    if r["migrations"]:
        out += ["", "Миграции: " + ", ".join(f"`{d}` ({n})" for d, n in r["migrations"].items())]
    out += ["", f"## Проверки прав ({len(r['authz'])})", ""]
    af = OrderedDict()
    for a in r["authz"]:
        af.setdefault(a["file"], []).append(str(a["line"]))
    out += [f"- `{f}`: строки {', '.join(ls[:10])}" for f, ls in list(af.items())[:80]]
    out += ["", f"## Тесты ({len(r['tests'])} файлов)", ""]
    for t in r["tests"][:200]:
        stub = f", **заглушек или пропусков: {t['stubs']}**" if t.get("stubs") else ""
        out.append(f"- `{t['file']}` ({t['kind']}, {t['count']}{stub})" + (": " + "; ".join(t["titles"][:6]) if t["titles"] else ""))
    out += ["", "## Документация", ""]
    out += [f"- `{d['file']}` — {md_escape(d['title'])} ({d['lines']} строк)" for d in r["docs"][:150]] or ["Не найдено."]
    out += ["", f"## TODO / FIXME ({len(r['todos'])})", "", "Подсказки о известных проблемах и недоделках — проверь, не попадают ли в спеку как «так задумано».", ""]
    out += [f"- `{t['file']}:{t['line']}` {t['tag']}: {md_escape(t['text'])}" for t in r["todos"][:120]]
    if r["warnings"]:
        out += ["", "## Предупреждения", ""] + [f"- {w}" for w in r["warnings"]]
    return "\n".join(out) + "\n"


def cmd_scan(a):
    root = Path(a.repo).resolve()
    if not root.is_dir():
        print(f"error: нет папки {root}", file=sys.stderr)
        return 2
    out = Path(a.out).resolve() if a.out else root / "system-context"
    out.mkdir(parents=True, exist_ok=True)
    r = Inv(root).run().result()
    (out / "inventory.json").write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "inventory.md").write_text(to_markdown(r), encoding="utf-8")
    if a.json:
        print(json.dumps(r["summary"], ensure_ascii=False, indent=1))
    else:
        s = r["summary"]
        print(f"✓ {rel(Path.cwd(), out / 'inventory.json')}, {rel(Path.cwd(), out / 'inventory.md')}")
        print(f"  стек: " + "; ".join(f"{pk['dir']}: {', '.join(pk['frameworks']) or '—'}" for pk in r["stack"]) if r["stack"] else "  стек: манифестов не найдено")
        print("  входы: " + (", ".join(f"{k} {v}" for k, v in s["entries"].items()) or "0 — стек не распознан, ищи вручную"))
        print(f"  вызовы наружу: {s['outbound_calls']}, внешних хостов: {s['external_hosts']}, env: {s['env_vars']}, "
              f"сущностей: {s['entities']}, тестов: {s['test_files']}, документов: {s['docs']}")
        if r["openapi"]["only_in_openapi"]:
            print(f"  ! в OpenAPI есть {len(r['openapi']['only_in_openapi'])} операций, не найденных в коде — см. inventory.md")
        if r["openspec_exists"]:
            print("  ! openspec/ уже есть — не перезаписывай чужие спеки, сверяйся с ними (rules.md, «Если openspec/ уже есть»)")
        for w in r["warnings"]:
            print(f"  ! {w}")
    return 0


def load(repo):
    p = Path(repo).resolve() / "system-context" / "inventory.json"
    if not p.is_file():
        print(f"error: нет {p} — сначала inventory.py scan {repo}", file=sys.stderr)
        sys.exit(2)
    return json.loads(p.read_text(encoding="utf-8"))


def cmd_show(a):
    r = load(a.repo)
    sec = a.section
    g = re.compile(a.grep, re.I) if a.grep else None
    if sec == "entries":
        items = [e for e in r["entries"] if (not a.kind or e["kind"] == a.kind) and (not g or g.search(e["id"] + " " + e["file"]))]
        if a.json:
            print(json.dumps(items, ensure_ascii=False, indent=1))
        else:
            for e in items:
                print(f"{e['id']}\t{e['file']}:{e['line']}\t{','.join(e['tags'])}")
            print(f"— {len(items)}", file=sys.stderr)
    elif sec == "outbound":
        items = [c for c in r["outbound"]["calls"] if not g or g.search(json.dumps(c, ensure_ascii=False))]
        for c in items:
            print(f"{c['file']}:{c['line']}\t{c['code']}")
        print("\nхосты:")
        for h, rec in r["outbound"]["hosts"].items():
            if not g or g.search(h + " ".join(rec["files"])):
                print(f"{h}\t{rec['count']}\t{', '.join(rec['files'])}")
    elif sec == "env":
        for k, v in r["env"].items():
            if not g or g.search(k + " ".join(v["files"])):
                print(f"{k}\t{','.join(v['tags'])}\t{', '.join(v['files'])}")
    elif sec == "entities":
        for e in r["entities"]:
            if not g or g.search(e["name"] + e["file"]):
                print(f"{e['name']}\t{e['how']}\t{e['file']}:{e['line']}")
        for e in r["enums"]:
            if not g or g.search(e["name"] + e["file"]):
                print(f"enum {e['name']}\t{e['file']}:{e['line']}\t{', '.join(e['values'])}")
    elif sec == "tests":
        for t in r["tests"]:
            if not g or g.search(t["file"] + " ".join(t["titles"])):
                print(f"{t['file']} ({t['count']}): " + "; ".join(t["titles"]))
    elif sec == "todos":
        for t in r["todos"]:
            if not g or g.search(t["file"] + t["text"]):
                print(f"{t['file']}:{t['line']}\t{t['tag']}\t{t['text']}")
    elif sec == "authz":
        for t in r["authz"]:
            if not g or g.search(t["file"] + t["code"]):
                print(f"{t['file']}:{t['line']}\t{t['code']}")
    return 0


def main():
    ap = argparse.ArgumentParser(description="Опись репозитория: входы, выходы, конфигурация, данные, тесты, документы")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("scan", help="просканировать репозиторий")
    s.add_argument("repo", help="корень репозитория")
    s.add_argument("--out", help="куда писать (по умолчанию <repo>/system-context)")
    s.add_argument("--json", action="store_true", help="сводку — в JSON")
    s.set_defaults(fn=cmd_scan)
    sh = sub.add_parser("show", help="выборка из inventory.json")
    sh.add_argument("repo")
    sh.add_argument("--section", default="entries", choices=["entries", "outbound", "env", "entities", "tests", "todos", "authz"])
    sh.add_argument("--kind", help="вид входа: http, graphql, grpc, rpc, consumer, schedule, cli")
    sh.add_argument("--grep", help="регулярное выражение по id, файлу, тексту")
    sh.add_argument("--json", action="store_true")
    sh.set_defaults(fn=cmd_show)
    a = ap.parse_args()
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
