#!/usr/bin/env python3
"""Забрать тест-кейсы из TMS в нормализованный снимок test-cases/.source/snapshot.json.

  python3 fetch.py api <repo> --tms testrail --url https://acme.testrail.io --project 3 [--suite 7]
  python3 fetch.py api <repo> --tms testit   --url https://testit.acme.ru --project 12
  python3 fetch.py api <repo> --tms zephyr   --project SHOP                         # Cloud
  python3 fetch.py api <repo> --tms zephyr   --url https://jira.acme.ru --project SHOP   # Data Center
  python3 fetch.py api <repo> --tms testlink --url https://testlink.acme.ru --project "Магазин"
  python3 fetch.py file <repo> --file export.xml [--tms testrail|testlink|zephyr|testit|table]
  python3 fetch.py columns --file export.xlsx          # какие колонки нашлись и как разложатся

Токены — только из переменных окружения: TESTRAIL_USER + TESTRAIL_KEY, TESTIT_TOKEN, ZEPHYR_TOKEN, TESTLINK_DEVKEY.
Секреты в тексте кейсов (пароли, токены, ключи, реальные карты) маскируются до записи на диск: [скрыто: S-01].
ПДн (телефоны, email, СНИЛС) только отмечаются; --mask-pii — маскировать и их.
--record DIR пишет сырые ответы API (без заголовков) — держи DIR вне репозитория: в них секреты не скрыты.
--replay DIR берёт ответы из записанных файлов без сети.
"""
import argparse
import datetime as dt
import json
import os
import re
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import qa  # noqa: E402
import net  # noqa: E402
import tms_common  # noqa: E402
import tms_table  # noqa: E402
import tms_testit  # noqa: E402
import tms_testlink  # noqa: E402
import tms_testrail  # noqa: E402
import tms_zephyr  # noqa: E402

TMS = ["testrail", "testit", "zephyr", "testlink", "table"]
ENV = {"testrail": ["TESTRAIL_USER", "TESTRAIL_KEY"], "testit": ["TESTIT_TOKEN"], "zephyr": ["ZEPHYR_TOKEN"],
       "testlink": ["TESTLINK_DEVKEY"]}


def log(msg):
    print(f"  {msg}", file=sys.stderr)


def env(tms, replay):
    vals = []
    for name in ENV[tms]:
        v = os.environ.get(name, "")
        if not v and not replay:
            qa.die(f"нет переменной окружения {name}. Попроси человека задать её в своём терминале перед запуском "
                   f"(export {name}=…) — не проси вставить токен в чат. Нет токена — выгрузи файл и запусти `fetch.py file`.")
        vals.append(v or "replay")
    return vals


def clean_origin(url):
    u = urllib.parse.urlsplit(url)
    host = u.hostname or ""
    if u.port:
        host += f":{u.port}"
    return urllib.parse.urlunsplit((u.scheme, host, u.path, "", ""))


def make_client(a):
    if a.record:
        rec = Path(a.record).resolve()
        if str(rec).startswith(str(Path(a.repo).resolve())):
            qa.warn("--record внутри репозитория: в сырых ответах секреты не скрыты — не коммить эту папку")
    t = a.tms
    if t == "testrail":
        if not a.url:
            qa.die("TestRail: укажи --url https://<имя>.testrail.io")
        user, key = env(t, a.replay)
        return net.Client(a.url.rstrip("/") + "/index.php?/api/v2", {"Authorization": net.Client.basic(user, key)},
                          a.replay, a.record, delay=a.delay)
    if t == "testit":
        if not a.url:
            qa.die("Test IT: укажи --url https://<ваш test it>")
        (tok,) = env(t, a.replay)
        return net.Client(a.url.rstrip("/") + "/api/v2", {"Authorization": f"PrivateToken {tok}"}, a.replay, a.record, delay=a.delay)
    if t == "zephyr":
        url = (a.url or "https://api.zephyrscale.smartbear.com/v2").rstrip("/")
        if "smartbear.com" not in url and "/rest/atm/" not in url:
            url += "/rest/atm/1.0"
        a.url = url
        (tok,) = env(t, a.replay)
        return net.Client(url, {"Authorization": f"Bearer {tok}"}, a.replay, a.record, delay=a.delay)
    if t == "testlink":
        if not a.url:
            qa.die("TestLink: укажи --url https://<ваш testlink>")
        url = a.url.rstrip("/")
        if not url.endswith("xmlrpc.php"):
            url += "/lib/api/xmlrpc/v1/xmlrpc.php"
        a.url = url
        return net.Client(url, {}, a.replay, a.record)
    qa.die(f"для --tms {t} нет API — используй `fetch.py file`")


def detect(path):
    p = str(path).lower()
    if p.endswith(".json"):
        return "testit"
    if p.endswith((".csv", ".tsv", ".xlsx", ".xlsm", ".txt")):
        return "table"
    if p.endswith(".xml"):
        root = tms_common.parse_xml(path)
        t = tms_common.tag(root)
        if t in ("suite",):
            return "testrail"
        if t in ("testsuite", "testcases", "testcase"):
            return "testlink"
        if any(tms_common.tag(e) == "testcase" for e in root.iter()):
            return "zephyr"
        qa.die(f"{path}: не узнал формат XML (корень <{t}>) — укажи --tms")
    qa.die(f"{path}: не узнал формат по расширению — укажи --tms")


def load_file(a):
    path = Path(a.file)
    if not path.is_file():
        qa.die(f"нет файла {a.file}")
    t = a.tms or detect(path)
    p = str(path).lower()
    table = p.endswith((".csv", ".tsv", ".xlsx", ".xlsm", ".txt"))
    if table:
        return tms_table.load(path, t if t != "table" else "table", a.sheet, a.map)
    if t == "testrail":
        return tms_testrail.load_xml(path, a)
    if t == "testlink":
        return tms_testlink.load_xml(path, a)
    if t == "zephyr":
        return tms_zephyr.load_xml(path, a)
    if t == "testit":
        return tms_testit.load_json(json.loads(path.read_text(encoding="utf-8-sig")), path)
    qa.die(f"--tms {t}: для этого формата файла нет разбора")


def normalize(snap, a, red):
    def txt(v, where):
        return red(qa.html_to_md(v), where) if v else ""

    def steps(lst, sid):
        out = []
        for i, s in enumerate(lst, 1):
            out.append({"action": txt(s.get("action"), f"{sid}|шаг {i}"), "expected": txt(s.get("expected"), f"{sid}|шаг {i}"),
                        "data": txt(s.get("data"), f"{sid}|шаг {i}"), "shared": str(s.get("shared") or "")})
        return out

    seen = {}
    for c in snap["cases"]:
        sid = str(c["sid"] or c["key"] or c["title"])
        if sid in seen:
            seen[sid] += 1
            sid = f"{sid}#{seen[sid]}"
        else:
            seen[sid] = 1
        c["sid"] = sid
        c["title"] = red(re.sub(r"\s+", " ", qa.html_to_md(c["title"])).strip(), f"{sid}|название") or "(без названия)"
        for f in ("objective", "preconditions", "postconditions", "expected"):
            c[f] = txt(c.get(f), f"{sid}|{f}")
        c["steps"] = steps(c.get("steps") or [], sid)
        c["priority"] = qa.norm_priority(c.get("priority"))
        c["status"] = qa.norm_status(c.get("status"))
        c["tags"] = qa.norm_list(c.get("tags"))
        c["requirements"] = qa.norm_list(c.get("requirements"))
        c["path"] = [re.sub(r"\s+", " ", qa.html_to_md(x)).strip() or "—" for x in c.get("path") or []]
        c["params"] = [{k: red(str(v), f"{sid}|параметры") for k, v in row.items()} for row in c.get("params") or []]
        c["custom"] = {k: red(qa.html_to_md(v) if isinstance(v, str) else v, f"{sid}|поле {k}") for k, v in (c.get("custom") or {}).items()}
        c["links"] = [{"title": red(l.get("title") or "", f"{sid}|ссылки"), "url": red(l.get("url") or "", f"{sid}|ссылки")}
                      for l in c.get("links") or []]
    for s in snap["shared"]:
        s["sid"] = str(s["sid"])
        s["title"] = red(qa.html_to_md(s.get("title")), f"{s['sid']}|название") or "(без названия)"
        s["steps"] = steps(s.get("steps") or [], s["sid"])
    return snap


def apply_filters(snap, a):
    cases = snap["cases"]
    if a.section:
        want = [qa.slug(x) for x in tms_common.split_path(a.section)]
        cases = [c for c in cases if [qa.slug(x) for x in c["path"]][:len(want)] == want]
        snap["partial"] = True
    if a.tag:
        cases = [c for c in cases if a.tag in c["tags"]]
        snap["partial"] = True
    if getattr(a, "limit", 0) and len(cases) > a.limit:
        cases = cases[:a.limit]
        snap["partial"] = True
    snap["cases"] = cases
    return snap


def download(snap, client, P, root_url):
    ok = miss = 0
    for c in snap["cases"]:
        for att in c.get("attachments") or []:
            name = re.sub(r"[^\w.\-]+", "_", str(att.get("name") or "file"))[:80]
            dest = P.source / "files" / qa.slug(c["sid"], 60) / name
            url = att.get("url") or ""
            if url.startswith("/api/") and root_url:
                url = root_url.rstrip("/") + url
            if url and client.download(url, dest):
                att["file"] = P.rel(dest)
                ok += 1
            else:
                miss += 1
    return ok, miss


def finish(snap, a, P, red, extra_cfg):
    snap["fetched"] = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    snap.setdefault("partial", False)
    qa.save_json(P.snapshot, snap)
    qa.write_if_changed(P.source / ".gitignore", "# снимок TMS и временное — не коммитить; ids.json, config.json, redactions.json — коммитить\n"
                        "snapshot.json\nincoming/\nfiles/\n")
    cfg = P.load_config()
    cfg.update({"tms": snap["tms"], "project": snap.get("project", ""), "origin": extra_cfg["origin"], "mode": extra_cfg["mode"],
                "fetched": snap["fetched"], "partial": snap["partial"], "lang": a.lang or cfg.get("lang", "ru"),
                "filters": {k: v for k, v in (("section", a.section), ("tag", a.tag)) if v}})
    qa.save_json(P.config, cfg)
    prev = {e["id"]: e for e in (qa.load_json(P.redactions, []) or [])}
    for e in red.entries():
        prev[e["id"]] = e
    qa.save_json(P.redactions, sorted(prev.values(), key=lambda e: e["id"]))
    secrets = [e for e in red.entries() if e["secret"]]
    pii = [e for e in red.entries() if not e["secret"]]
    steps = sum(len(c["steps"]) for c in snap["cases"])
    print(f"✓ {P.rel(P.snapshot)}: кейсов {len(snap['cases'])}, шагов {steps}, общих шагов {len(snap['shared'])}"
          + (" (часть проекта — по фильтру или --limit)" if snap["partial"] else ""))
    if secrets:
        print(f"  секреты скрыты: {len(secrets)} ({', '.join(e['id'] + ' ' + e['kind'] for e in secrets[:8])}{' …' if len(secrets) > 8 else ''})")
    if pii:
        print(f"  ПДн найдено: {len(pii)} ({'скрыты' if a.mask_pii else 'не скрыты — вопрос в QUESTIONS.md'})")
    if snap["unknown_fields"]:
        top = sorted(snap["unknown_fields"].items(), key=lambda x: -x[1])[:10]
        print("  поля TMS, ушедшие в custom: " + ", ".join(f"{k} ({v})" for k, v in top))
    for n in snap.get("notes") or []:
        print(f"  ! {n}")
    print(f"Дальше: python3 <skill>/scripts/build.py {a.repo}")


def cmd_api(a):
    P = qa.Paths(a.repo)
    client = make_client(a)
    red = qa.Redactor(a.mask_pii)
    try:
        if a.tms == "testrail":
            snap = tms_testrail.fetch_api(client, a, log)
        elif a.tms == "testit":
            snap = tms_testit.fetch_api(client, a, log)
        elif a.tms == "zephyr":
            snap = tms_zephyr.fetch_api(client, a, log)
        else:
            (devkey,) = env("testlink", a.replay)
            snap = tms_testlink.fetch_api(client, a, log, devkey)
    except net.HttpError as e:
        if e.status in (401, 403):
            qa.die(f"TMS отказала в доступе ({e.status}): проверь токен в {', '.join(ENV[a.tms])} и права на проект. Запрос: {e.key}")
        if e.status == 404:
            qa.die(f"не найдено (404): {e.key}. Проверь --url, --project; в --replay — есть ли такой ответ")
        qa.die(f"ошибка TMS: {e}")
    except ValueError as e:
        qa.die(str(e))
    normalize(snap, a, red)
    apply_filters(snap, a)
    if a.attachments:
        root = a.url.split("/api/")[0] if a.tms == "testit" else ""
        ok, miss = download(snap, client, P, root)
        print(f"  вложения: скачано {ok}, не скачано {miss}")
    print(f"  запросов к API: {client.calls}", file=sys.stderr)
    finish(snap, a, P, red, {"origin": clean_origin(a.url or ""), "mode": "api"})


def cmd_file(a):
    P = qa.Paths(a.repo)
    red = qa.Redactor(a.mask_pii)
    try:
        snap = load_file(a)
    except ValueError as e:
        qa.die(str(e))
    normalize(snap, a, red)
    apply_filters(snap, a)
    finish(snap, a, P, red, {"origin": Path(a.file).name, "mode": "file"})


def cmd_columns(a):
    try:
        print(tms_table.describe(a.file, a.sheet, a.map))
    except (ValueError, OSError) as e:
        qa.die(str(e))


def main():
    ap = argparse.ArgumentParser(description="Тест-кейсы из TMS в нормализованный снимок", formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p):
        p.add_argument("--section", help="только эта ветка дерева: \"Заказы/Отмена\"")
        p.add_argument("--tag", help="только кейсы с этим тегом")
        p.add_argument("--limit", type=int, default=0, help="не больше N кейсов (пробный прогон)")
        p.add_argument("--mask-pii", action="store_true", help="маскировать и ПДн (телефоны, email, СНИЛС)")
        p.add_argument("--lang", choices=["ru", "en"], help="язык заголовков в md (по умолчанию ru)")
        p.add_argument("--prefix", default="", help="TestLink: префикс проекта для ключей (SHOP → SHOP-12)")

    p = sub.add_parser("api", help="через API TMS")
    p.add_argument("repo")
    p.add_argument("--tms", required=True, choices=TMS[:4])
    p.add_argument("--url", help="адрес TMS (Zephyr Cloud — не нужен)")
    p.add_argument("--project", required=True, help="TestRail: id; Test IT: id/globalId; Zephyr: ключ; TestLink: имя")
    p.add_argument("--suite", help="TestRail: только этот сьют (id)")
    p.add_argument("--jira", default="", help="Zephyr Cloud: адрес Jira для ссылок на кейсы")
    p.add_argument("--attachments", action="store_true", help="скачать вложения кейсов (долго: запрос на кейс)")
    p.add_argument("--record", help="папка для записи сырых ответов (вне репозитория)")
    p.add_argument("--replay", help="папка записанных ответов — без сети")
    p.add_argument("--delay", type=float, default=0.0, help="пауза между запросами, сек (лимиты API)")
    common(p)
    p.set_defaults(func=cmd_api)

    p = sub.add_parser("file", help="из файла выгрузки")
    p.add_argument("repo")
    p.add_argument("--file", required=True)
    p.add_argument("--tms", choices=TMS, help="по умолчанию — по формату файла")
    p.add_argument("--sheet", help="xlsx: имя листа")
    p.add_argument("--map", action="append", help="таблица: поле=Колонка (поля: " + ", ".join(tms_table.ALIASES) + ")")
    common(p)
    p.set_defaults(func=cmd_file)

    p = sub.add_parser("columns", help="показать колонки таблицы и как они разложатся")
    p.add_argument("--file", required=True)
    p.add_argument("--sheet")
    p.add_argument("--map", action="append")
    p.set_defaults(func=cmd_columns)

    a = ap.parse_args()
    return a.func(a) or 0


if __name__ == "__main__":
    sys.exit(main())
