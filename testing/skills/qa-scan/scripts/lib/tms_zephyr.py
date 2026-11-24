"""Zephyr Scale: Cloud API v2 (api.zephyrscale.smartbear.com/v2), Data Center API (<jira>/rest/atm/1.0)
и XML-выгрузка. CSV/xlsx — через tms_table. Zephyr Squad и Enterprise — другие продукты, здесь не поддержаны.

API: токен — переменная ZEPHYR_TOKEN (Cloud: «Zephyr API keys» в Jira; DC: личный токен Jira), Bearer.
Вызов другого кейса как шага (call to test) — шаг-ссылка на тот кейс.
"""
import re

from tms_common import child, children, new_case, new_step, norm_list, parse_xml, snapshot, split_path, tag, text


def _cloud_pages(client, path):
    out, start = [], 0
    while True:
        sep = "&" if "?" in path else "?"
        r = client.get(f"{path}{sep}maxResults=100&startAt={start}")
        vals = r.get("values") or []
        out += vals
        if r.get("isLast", True) or not vals:
            return out
        start += len(vals)


def fetch_cloud(client, args, log):
    pk = args.project
    snap = snapshot("zephyr", pk, args.url)
    folders = {f["id"]: f for f in _cloud_pages(client, f"/folders?projectKey={pk}&folderType=TEST_CASE")}
    pri = {p["id"]: p.get("name") for p in _cloud_pages(client, f"/priorities?projectKey={pk}")}
    sta = {s["id"]: s.get("name") for s in _cloud_pages(client, f"/statuses?projectKey={pk}&statusType=TEST_CASE")}

    def path(fid):
        out, seen = [], set()
        while fid and fid in folders and fid not in seen:
            seen.add(fid)
            out.insert(0, folders[fid].get("name") or "")
            fid = folders[fid].get("parentId")
        return out

    tcs = _cloud_pages(client, f"/testcases?projectKey={pk}")
    if args.limit:
        tcs = tcs[:args.limit]
        snap["partial"] = True
    log(f"кейсов: {len(tcs)}")
    jira_ids = 0
    for i, t in enumerate(tcs, 1):
        key = t.get("key")
        c = new_case(sid=key, key=key, title=t.get("name") or "",
                     url=f"{args.jira.rstrip('/')}/projects/{pk}?selectedItem=com.atlassian.plugins.atlassian-connect-plugin:com.kanoah.test-manager__main-project-page#!/testCase/{key}" if args.jira else "",
                     path=path((t.get("folder") or {}).get("id")), priority=pri.get((t.get("priority") or {}).get("id"), ""),
                     status=sta.get((t.get("status") or {}).get("id"), ""), tags=t.get("labels") or [],
                     objective=t.get("objective") or "", preconditions=t.get("precondition") or "",
                     updated=t.get("updatedOn") or t.get("createdOn") or "")
        links = t.get("links") or {}
        for iss in links.get("issues") or []:
            if iss.get("issueKey"):
                c["requirements"].append(iss["issueKey"])
            elif iss.get("issueId"):
                c["requirements"].append(f"jira:{iss['issueId']}")
                jira_ids += 1
        c["links"] = [{"title": w.get("description") or "", "url": w.get("url") or ""} for w in links.get("webLinks") or []]
        for k, v in (t.get("customFields") or {}).items():
            if v not in (None, "", []):
                c["custom"][k] = ", ".join(map(str, v)) if isinstance(v, list) else v
                snap["unknown_fields"][k] = snap["unknown_fields"].get(k, 0) + 1
        if t.get("estimatedTime"):
            c["custom"]["estimated_ms"] = t["estimatedTime"]
        script = ((t.get("testScript") or {}).get("self") or "")
        if script.endswith("/testscript"):
            s = client.get(f"/testcases/{key}/testscript") or {}
            if s.get("type") == "bdd":
                c["steps"] = [new_step("```gherkin\n" + (s.get("text") or "") + "\n```")]
            elif s.get("text"):
                c["steps"] = [new_step(s.get("text"))]
        elif script:
            for st in _cloud_pages(client, f"/testcases/{key}/teststeps"):
                inl = st.get("inline")
                call = st.get("testCase")
                if call and call.get("testCaseKey"):
                    c["steps"].append(new_step(shared=call["testCaseKey"]))
                elif inl:
                    c["steps"].append(new_step(inl.get("description") or "", inl.get("expectedResult") or "", inl.get("testData") or ""))
        snap["cases"].append(c)
        if i % 100 == 0:
            log(f"  … {i}/{len(tcs)}")
    if jira_ids:
        snap["notes"].append(f"{jira_ids} ссылок на задачи Jira пришли числом (jira:<id>), а не ключом — ключи даст Jira API или выгрузка")
    return snap


def fetch_dc(client, args, log):
    pk = args.project
    snap = snapshot("zephyr", pk, args.url)
    out, start = [], 0
    q = f'projectKey = "{pk}"'
    while True:
        import urllib.parse as up
        page = client.get(f"/testcase/search?query={up.quote(q)}&startAt={start}&maxResults=200") or []
        out += page
        if len(page) < 200 or (args.limit and len(out) >= args.limit):
            break
        start += 200
    if args.limit:
        out = out[:args.limit]
        snap["partial"] = True
    for t in out:
        key = t.get("key")
        c = new_case(sid=key, key=key, title=t.get("name") or "",
                     url=f"{args.url.split('/rest/')[0]}/secure/Tests.jspa#/testCase/{key}",
                     path=split_path(t.get("folder") or ""), priority=t.get("priority") or "", status=t.get("status") or "",
                     tags=t.get("labels") or [], requirements=t.get("issueLinks") or [], objective=t.get("objective") or "",
                     preconditions=t.get("precondition") or "", updated=t.get("updatedOn") or t.get("createdOn") or "",
                     version=str(t.get("majorVersion") or ""), owner=t.get("owner") or "")
        for k, v in (t.get("customFields") or {}).items():
            if v not in (None, "", []):
                c["custom"][k] = ", ".join(map(str, v)) if isinstance(v, list) else v
                snap["unknown_fields"][k] = snap["unknown_fields"].get(k, 0) + 1
        ts = t.get("testScript") or {}
        if (ts.get("type") or "").upper() == "STEP_BY_STEP":
            for st in ts.get("steps") or []:
                if st.get("testCaseKey"):
                    c["steps"].append(new_step(shared=st["testCaseKey"]))
                else:
                    c["steps"].append(new_step(st.get("description") or "", st.get("expectedResult") or "", st.get("testData") or ""))
        elif ts.get("text"):
            body = ts["text"]
            if (ts.get("type") or "").upper() == "BDD":
                body = "```gherkin\n" + body + "\n```"
            c["steps"] = [new_step(body)]
        snap["cases"].append(c)
    return snap


def fetch_api(client, args, log):
    if not args.project:
        raise ValueError("Zephyr Scale: укажи --project <ключ проекта Jira>, например SHOP")
    if "/rest/atm/" in (args.url or ""):
        return fetch_dc(client, args, log)
    return fetch_cloud(client, args, log)


def load_xml(path, args):
    root = parse_xml(path)
    tcs = [e for e in root.iter() if tag(e) == "testcase"]
    if not tcs:
        raise ValueError(f"{path}: нет элементов <testCase> — это точно XML-выгрузка Zephyr Scale?")
    snap = snapshot("zephyr", text(root, "projectKey"), str(path))
    for t in tcs:
        key = t.get("key") or text(t, "key")
        c = new_case(sid=key or t.get("id") or "", key=key or "", title=text(t, "name"), path=split_path(text(t, "folder")),
                     priority=text(t, "priority"), status=text(t, "status"), objective=text(t, "objective"),
                     preconditions=text(t, "precondition"), owner=text(t, "owner"), updated=text(t, "updatedOn"))
        labels = child(t, "labels")
        c["tags"] = [text(l) for l in children(labels, "label")] if labels is not None else []
        issues = child(t, "issues")
        if issues is not None:
            c["requirements"] = [text(i, "key") or text(i) for i in children(issues, "issue")]
        cf = child(t, "customFields")
        if cf is not None:
            for f in children(cf, "customField"):
                v = text(f, "value")
                if v:
                    c["custom"][f.get("name") or "?"] = v
                    snap["unknown_fields"][f.get("name") or "?"] = snap["unknown_fields"].get(f.get("name") or "?", 0) + 1
        ts = child(t, "testScript")
        if ts is not None:
            steps = child(ts, "steps")
            if steps is not None:
                for s in sorted(children(steps, "step"), key=lambda s: int(s.get("index") or 0)):
                    if text(s, "testCaseKey"):
                        c["steps"].append(new_step(shared=text(s, "testCaseKey")))
                    else:
                        c["steps"].append(new_step(text(s, "description"), text(s, "expectedResult"), text(s, "testData")))
            elif text(ts, "text") or (ts.text or "").strip():
                body = text(ts, "text") or ts.text.strip()
                if (ts.get("type") or "").lower() == "bdd":
                    body = "```gherkin\n" + body + "\n```"
                c["steps"] = [new_step(body)]
        c["requirements"] = norm_list(c["requirements"])
        snap["cases"].append(c)
    return snap
