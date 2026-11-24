"""TestLink: XML-выгрузка сьютов (полнее всего: ключевые слова, требования, поля) и XML-RPC API.

API: ключ — переменная TESTLINK_DEVKEY (My Settings → API interface), адрес — <testlink>/lib/api/xmlrpc/v1/xmlrpc.php.
Через API приходят шаги, важность, тип исполнения; ключевые слова и требования — только в XML-выгрузке.
"""
from tms_common import child, children, new_case, new_step, parse_xml, snapshot, tag, text

IMPORTANCE = {"3": "high", "2": "medium", "1": "low"}
STATUS = {"1": "draft", "2": "needs-work", "3": "needs-work", "4": "needs-work", "5": "deprecated", "6": "draft", "7": "ready"}


def _case_xml(t, path, prefix, snap):
    ext = text(t, "externalid")
    key = f"{prefix}-{ext}" if prefix and ext else ext
    c = new_case(sid=t.get("internalid") or key or t.get("name"), key=key, title=t.get("name") or "", path=path,
                 objective=text(t, "summary"), preconditions=text(t, "preconditions"),
                 priority=IMPORTANCE.get(text(t, "importance"), text(t, "importance")),
                 status=STATUS.get(text(t, "status"), text(t, "status")),
                 type="automated" if text(t, "execution_type") == "2" else "manual", version=text(t, "version"))
    steps = child(t, "steps")
    if steps is not None:
        for s in sorted(children(steps, "step"), key=lambda s: int(text(s, "step_number") or 0)):
            c["steps"].append(new_step(text(s, "actions"), text(s, "expectedresults")))
    kw = child(t, "keywords")
    if kw is not None:
        c["tags"] = [k.get("name") for k in children(kw, "keyword") if k.get("name")]
    rq = child(t, "requirements")
    if rq is not None:
        c["requirements"] = [text(r, "doc_id") or text(r, "title") for r in children(rq, "requirement")]
    cf = child(t, "custom_fields")
    if cf is not None:
        for f in children(cf, "custom_field"):
            n, v = text(f, "name"), text(f, "value")
            if n and v:
                c["custom"][n] = v
                snap["unknown_fields"][n] = snap["unknown_fields"].get(n, 0) + 1
    if text(t, "estimated_exec_duration"):
        c["custom"]["estimated_min"] = text(t, "estimated_exec_duration")
    return c


def load_xml(path, args):
    root = parse_xml(path)
    if tag(root) not in ("testsuite", "testcases", "testcase"):
        raise ValueError(f"{path}: корень <{tag(root)}>, а TestLink выгружает <testsuite> или <testcases>")
    prefix = getattr(args, "prefix", "") or ""
    snap = snapshot("testlink", origin=str(path))
    if not prefix:
        snap["notes"].append("префикс проекта не указан (--prefix) — ключи кейсов без префикса, только номер")

    def walk(el, path_):
        for t in children(el, "testcase"):
            snap["cases"].append(_case_xml(t, path_, prefix, snap))
        for s in children(el, "testsuite"):
            walk(s, path_ + [s.get("name") or ""])

    if tag(root) == "testcase":
        snap["cases"].append(_case_xml(root, [], prefix, snap))
    else:
        top = [root.get("name")] if tag(root) == "testsuite" and root.get("name") else []
        snap["project"] = root.get("name") or ""
        walk(root, top)
    return snap


def _as_list(r):
    if r is None or r == "":
        return []
    if isinstance(r, dict):
        if "id" in r and not isinstance(r.get("id"), dict):
            return [r]
        return list(r.values())
    return list(r)


def _check(r, what):
    if isinstance(r, list) and r and isinstance(r[0], dict) and "code" in r[0] and "message" in r[0]:
        raise ValueError(f"TestLink {what}: {r[0]['code']} {r[0]['message']}")
    return r


def fetch_api(client, args, log, devkey):
    if not args.project:
        raise ValueError("TestLink: укажи --project <имя проекта, как в TestLink>")
    p = _check(client.xmlrpc("tl.getTestProjectByName", {"devKey": devkey, "testprojectname": args.project}), "проект")
    if isinstance(p, list):
        p = p[0]
    prefix = args.prefix or p.get("prefix") or ""
    snap = snapshot("testlink", p.get("name") or args.project, args.url)
    base = args.url.split("/lib/api/")[0]
    tops = _as_list(_check(client.xmlrpc("tl.getFirstLevelTestSuitesForTestProject",
                                         {"devKey": devkey, "testprojectid": p["id"]}), "сьюты"))
    n = 0

    def walk(suite, path_):
        nonlocal n
        if args.limit and n >= args.limit:
            snap["partial"] = True
            return
        tcs = _as_list(_check(client.xmlrpc("tl.getTestCasesForTestSuite", {
            "devKey": devkey, "testsuiteid": suite["id"], "deep": False, "details": "full"}), "кейсы"))
        for t in tcs:
            if args.limit and n >= args.limit:
                snap["partial"] = True
                break
            tid = t.get("id") or t.get("testcase_id")
            if "steps" not in t:
                full = _check(client.xmlrpc("tl.getTestCase", {"devKey": devkey, "testcaseid": tid}), "кейс")
                t = {**t, **(full[0] if isinstance(full, list) and full else full or {})}
            ext = t.get("tc_external_id") or t.get("external_id") or ""
            if prefix and ext and not str(ext).startswith(prefix):
                ext = f"{prefix}-{ext}"
            c = new_case(sid=str(tid), key=str(ext), title=t.get("name") or "", path=path_,
                         url=f"{base}/linkto.php?tprojectPrefix={prefix}&item=testcase&id={ext}" if ext else "",
                         objective=t.get("summary") or "", preconditions=t.get("preconditions") or "",
                         priority=IMPORTANCE.get(str(t.get("importance")), str(t.get("importance") or "")),
                         status=STATUS.get(str(t.get("status")), str(t.get("status") or "")),
                         type="automated" if str(t.get("execution_type")) == "2" else "manual", version=str(t.get("version") or ""))
            for s in sorted(t.get("steps") or [], key=lambda s: int(s.get("step_number") or 0)):
                c["steps"].append(new_step(s.get("actions") or "", s.get("expected_results") or ""))
            snap["cases"].append(c)
            n += 1
        subs = _as_list(_check(client.xmlrpc("tl.getTestSuitesForTestSuite", {"devKey": devkey, "testsuiteid": suite["id"]}), "подсьюты"))
        for s in subs:
            if isinstance(s, dict) and s.get("id"):
                walk(s, path_ + [s.get("name") or ""])

    for s in tops:
        log(f"сьют {s.get('name')}")
        walk(s, [s.get("name") or ""])
    snap["notes"].append("через API TestLink не отдаёт ключевые слова и требования кейсов — для них нужна XML-выгрузка")
    return snap
