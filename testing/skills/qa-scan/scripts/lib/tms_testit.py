"""Test IT: API v2 (/api/v2/…) и JSON-выгрузка в форме ответов API. xlsx — через tms_table.

API: токен — переменная TESTIT_TOKEN (профиль → «Приватный токен»), заголовок `Authorization: PrivateToken …`.
Сквозной номер кейса — globalId (его видно в интерфейсе и в аннотациях автотестов WorkItemIds), он же sid.
"""
import re

from tms_common import new_case, new_step, snapshot

REQ = re.compile(r"\b[A-Z][A-Z0-9_]+-\d+\b")
KNOWN = {"id", "globalId", "name", "entityTypeName", "sectionId", "sectionName", "state", "priority", "steps",
         "preconditionSteps", "postconditionSteps", "tags", "links", "attributes", "autoTests", "iterations", "duration",
         "isAutomated", "modifiedDate", "createdDate", "versionNumber", "versionId", "projectId", "isDeleted",
         "createdById", "modifiedById", "attachments", "medianDuration", "isFlaky", "sourceType", "description",
         "sectionPreconditionSteps", "sectionPostconditionSteps", "externalKey"}


def _text_steps(steps):
    parts = [(s.get("action") or "").strip() for s in steps or [] if (s.get("action") or "").strip()]
    if len(parts) <= 1:
        return parts[0] if parts else ""
    return "\n".join(f"{i}. {p}" for i, p in enumerate(parts, 1))


def _steps(raw, shared_refs):
    out = []
    for s in raw or []:
        ref = s.get("workItemId") or (s.get("workItem") or {}).get("id") or s.get("sharedStepReference")
        if ref:
            gid = (s.get("workItem") or {}).get("globalId")
            shared_refs.add(str(ref))
            out.append(new_step(shared=f"ref:{ref}" if not gid else str(gid)))
            continue
        out.append(new_step(s.get("action") or "", s.get("expected") or "", s.get("testData") or ""))
        if s.get("comments"):
            out[-1]["data"] = (out[-1]["data"] + "\n" if out[-1]["data"] else "") + s["comments"]
    return out


def convert(items, sections, attrs, base_url, project_gid, snap):
    secs = {s["id"]: s for s in sections or []}

    def path(sid):
        out, seen = [], set()
        while sid and sid in secs and sid not in seen:
            seen.add(sid)
            if secs[sid].get("parentId"):  # корневая секция проекта не нужна в пути
                out.insert(0, secs[sid].get("name") or "")
            sid = secs[sid].get("parentId")
        return out

    uuid2gid = {w.get("id"): str(w.get("globalId")) for w in items}
    refs = set()
    for w in items:
        if w.get("isDeleted"):
            continue
        gid = str(w.get("globalId") or w.get("id"))
        et = (w.get("entityTypeName") or "TestCases").lower()
        steps = _steps(w.get("steps"), refs)
        if et == "sharedsteps":
            snap["shared"].append({"sid": gid, "title": w.get("name") or "", "steps": steps,
                                   "updated": w.get("modifiedDate") or ""})
            continue
        links = [{"title": l.get("title") or "", "url": l.get("url") or ""} for l in w.get("links") or []]
        reqs = []
        for l in links:
            for m in REQ.findall((l["title"] or "") + " " + (l["url"] or "")):
                if m not in reqs:
                    reqs.append(m)
        c = new_case(
            sid=gid, key=gid, title=w.get("name") or "",
            url=f"{base_url.rstrip('/')}/projects/{project_gid}/tests/{gid}" if base_url and project_gid else "",
            path=path(w.get("sectionId")) or ([w["sectionName"]] if w.get("sectionName") else []),
            priority=w.get("priority") or "", status=w.get("state") or "",
            type="checklist" if et == "checklists" else ("automated" if w.get("isAutomated") else "manual"),
            tags=[t.get("name") if isinstance(t, dict) else str(t) for t in w.get("tags") or []],
            requirements=reqs, links=links, steps=steps,
            preconditions=_text_steps(w.get("preconditionSteps")), postconditions=_text_steps(w.get("postconditionSteps")),
            objective=w.get("description") or "", updated=w.get("modifiedDate") or "", version=str(w.get("versionNumber") or ""))
        c["custom"]["uuid"] = w.get("id") or ""
        if w.get("duration"):
            c["custom"]["duration_ms"] = w["duration"]
        for k, v in (w.get("attributes") or {}).items():
            a = attrs.get(k, {})
            name = a.get("name") or k
            opts = a.get("options") or {}
            if isinstance(v, list):
                v = ", ".join(opts.get(str(x), str(x)) for x in v)
            else:
                v = opts.get(str(v), v)
            if v not in (None, ""):
                c["custom"][name] = v
                snap["unknown_fields"][name] = snap["unknown_fields"].get(name, 0) + 1
        rows = []
        for it in w.get("iterations") or []:
            row = {}
            for p in it.get("parameters") or []:
                row[p.get("name") or p.get("parameterKeyName") or "?"] = p.get("value") or ""
            if row:
                rows.append(row)
        c["params"] = rows
        c["autotests"] = [a.get("externalId") for a in w.get("autoTests") or [] if a.get("externalId")]
        for a in w.get("attachments") or []:
            c["attachments"].append({"name": a.get("name") or a.get("id"), "url": f"/api/Attachments/{a.get('id')}"})
        for k in w:
            if k not in KNOWN and w[k] not in (None, "", [], {}):
                snap["unknown_fields"][k] = snap["unknown_fields"].get(k, 0) + 1
        snap["cases"].append(c)
    # ссылки на общие шаги — по globalId
    for c in snap["cases"] + snap["shared"]:
        for s in c["steps"]:
            if s["shared"].startswith("ref:"):
                s["shared"] = uuid2gid.get(s["shared"][4:], s["shared"][4:])
    return snap


def fetch_api(client, args, log):
    if not args.project:
        raise ValueError("Test IT: укажи --project <id или globalId проекта> (из адреса /projects/<номер>/tests)")
    proj = client.get(f"/projects/{args.project}")
    pid = proj.get("id")
    snap = snapshot("testit", proj.get("name") or "", args.url)
    sections = client.get(f"/projects/{pid}/sections") or []
    attrs = {}
    try:
        for a in client.get(f"/projects/{pid}/attributes") or []:
            attrs[a.get("id")] = {"name": a.get("name"), "options": {o.get("id"): o.get("value") for o in a.get("options") or []}}
    except Exception as e:
        snap["notes"].append(f"атрибуты проекта не получены ({e}) — в custom будут id атрибутов")
    short, skip, take = [], 0, 100
    while True:
        page = client.get(f"/projects/{pid}/workItems?Skip={skip}&Take={take}&includeIterations=true")
        page = page or []
        short += page
        if len(page) < take or (args.limit and len(short) >= args.limit):
            break
        skip += take
    log(f"рабочих элементов: {len(short)}")
    full = []
    for i, w in enumerate(short, 1):
        if args.limit and len([x for x in full if (x.get("entityTypeName") or "") != "SharedSteps"]) >= args.limit:
            snap["partial"] = True
            break
        d = client.get(f"/workItems/{w['id']}")
        if d.get("isAutomated") and not d.get("autoTests"):
            try:
                d["autoTests"] = client.get(f"/workItems/{w['id']}/autoTests") or []
            except Exception:
                pass
        full.append(d)
        if i % 100 == 0:
            log(f"  … {i}/{len(short)}")
    return convert(full, sections, attrs, args.url, proj.get("globalId"), snap)


def load_json(data, path):
    snap = snapshot("testit", origin=str(path))
    if isinstance(data, list):
        items, sections, attrs = data, [], {}
    elif isinstance(data, dict):
        items = data.get("workItems") or data.get("testCases") or data.get("items") or []
        items += data.get("sharedSteps") or []
        sections = data.get("sections") or []
        attrs = {a.get("id"): {"name": a.get("name"), "options": {o.get("id"): o.get("value") for o in a.get("options") or []}}
                 for a in data.get("attributes") or []}
        snap["project"] = (data.get("project") or {}).get("name", "") if isinstance(data.get("project"), dict) else ""
    else:
        raise ValueError(f"{path}: ждал список рабочих элементов или объект с workItems")
    if not items or not isinstance(items[0], dict) or "name" not in items[0]:
        raise ValueError(f"{path}: не похоже на выгрузку Test IT (нет рабочих элементов с полем name). "
                         "Если это xlsx/csv — используй --tms table")
    return convert(items, sections, attrs, "", "", snap)
