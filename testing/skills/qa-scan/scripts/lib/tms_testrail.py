"""TestRail: API v2 (index.php?/api/v2/…) и XML-выгрузка сьюта. CSV — через tms_table.

API: ключ — переменные TESTRAIL_USER и TESTRAIL_KEY (Basic-авторизация, ключ API из «My Settings»).
"""
import re

from tms_common import child, children, new_case, new_step, norm_list, parse_xml, snapshot, split_numbered, tag, text

SYSTEM = {"id", "title", "section_id", "template_id", "type_id", "priority_id", "milestone_id", "refs", "created_by",
          "created_on", "updated_by", "updated_on", "estimate", "estimate_forecast", "suite_id", "display_order",
          "is_deleted", "case_assignedto_id", "labels", "comments"}
KNOWN_CUSTOM = {"custom_preconds", "custom_steps", "custom_expected", "custom_steps_separated", "custom_mission",
                "custom_goals", "custom_automation_type"}


def _items(cfg):
    """Варианты выпадающего поля: «1, Да\\n2, Нет» → {"1": "Да"}."""
    out = {}
    for c in cfg or []:
        for line in str((c.get("options") or {}).get("items") or "").splitlines():
            if "," in line:
                k, v = line.split(",", 1)
                out[k.strip()] = v.strip()
    return out


def _pages(client, path, key):
    out = []
    while path:
        r = client.get(path)
        if isinstance(r, list):
            return out + r
        out += r.get(key) or []
        nxt = (r.get("_links") or {}).get("next")
        path = re.sub(r"^/?(?:index\.php\?)?/?api/v2/", "", nxt) if nxt else None
    return out


def _steps(raw, shared_ids):
    steps = []
    for s in raw or []:
        if s.get("shared_step_id"):
            shared_ids.add(s["shared_step_id"])
            steps.append(new_step(shared=f"SS{s['shared_step_id']}"))
        else:
            data = s.get("additional_info") or ""
            steps.append(new_step(s.get("content") or "", s.get("expected") or "", data))
    return steps


def fetch_api(client, args, log):
    pid = args.project
    if not pid:
        raise ValueError("TestRail: укажи --project <id проекта> (число из адреса index.php?/projects/overview/<id>)")
    proj = client.get(f"get_project/{pid}")
    snap = snapshot("testrail", proj.get("name", ""), args.url)
    pri = {str(p["id"]): p.get("name") for p in (client.get("get_priorities") or [])}
    types = {str(t["id"]): t.get("name") for t in (client.get("get_case_types") or [])}
    fields = client.get("get_case_fields") or []
    labels = {f.get("system_name"): f.get("label") or f.get("name") for f in fields}
    options = {f.get("system_name"): _items(f.get("configs")) for f in fields if f.get("type_id") in (6, 12)}
    multi = proj.get("suite_mode") == 3
    suites = client.get(f"get_suites/{pid}") or []
    if args.suite:
        suites = [s for s in suites if str(s.get("id")) == str(args.suite)]
        if not suites:
            raise ValueError(f"TestRail: в проекте {pid} нет сьюта {args.suite}")
    shared_ids = set()
    for su in suites:
        sid = su["id"]
        log(f"сьют {su.get('name')} ({sid})")
        secs = _pages(client, f"get_sections/{pid}&suite_id={sid}", "sections")
        byid = {s["id"]: s for s in secs}

        def path(sec_id):
            out, seen = [], set()
            while sec_id and sec_id in byid and sec_id not in seen:
                seen.add(sec_id)
                out.insert(0, byid[sec_id].get("name") or "")
                sec_id = byid[sec_id].get("parent_id")
            return ([su.get("name")] if multi else []) + out

        cases = _pages(client, f"get_cases/{pid}&suite_id={sid}", "cases")
        for c in cases:
            if c.get("is_deleted"):
                continue
            auto = options.get("custom_automation_type", {}).get(str(c.get("custom_automation_type")), "")
            t = types.get(str(c.get("type_id")), "")
            case = new_case(
                sid=f"C{c['id']}", key=f"C{c['id']}", url=f"{args.url.rstrip('/')}/index.php?/cases/view/{c['id']}",
                title=c.get("title") or "", path=path(c.get("section_id")),
                priority=pri.get(str(c.get("priority_id")), ""),
                type="automated" if (auto and auto.lower() not in ("none", "manual", "нет")) or t.lower() == "automated" else "manual",
                requirements=norm_list(c.get("refs")), preconditions=c.get("custom_preconds") or "",
                objective=c.get("custom_mission") or c.get("custom_goals") or "",
                updated=str(c.get("updated_on") or ""), tags=[l.get("title") for l in (c.get("labels") or []) if l.get("title")])
            if t:
                case["custom"]["type"] = t
            if auto:
                case["custom"]["automation_type"] = auto
            if c.get("estimate"):
                case["custom"]["estimate"] = c["estimate"]
            if c.get("custom_steps_separated"):
                case["steps"] = _steps(c["custom_steps_separated"], shared_ids)
            elif c.get("custom_steps"):
                case["steps"] = [new_step(x) for x in split_numbered(c["custom_steps"])]
                case["expected"] = c.get("custom_expected") or ""
            elif c.get("custom_expected"):
                case["expected"] = c["custom_expected"]
            for k, v in c.items():
                if k in SYSTEM or k in KNOWN_CUSTOM or v in (None, "", [], {}):
                    continue
                name = labels.get(k[7:] if k.startswith("custom_") else k) or labels.get(k) or k
                opt = options.get(k[7:] if k.startswith("custom_") else k) or options.get(k) or {}
                if isinstance(v, list):
                    v = ", ".join(opt.get(str(x), str(x)) for x in v)
                else:
                    v = opt.get(str(v), v)
                case["custom"][name] = v
                snap["unknown_fields"][name] = snap["unknown_fields"].get(name, 0) + 1
            if args.attachments:
                att = client.get(f"get_attachments_for_case/{c['id']}")
                att = att.get("attachments", []) if isinstance(att, dict) else (att or [])
                for a in att:
                    case["attachments"].append({"name": a.get("name") or a.get("filename") or str(a.get("id")),
                                                "url": f"get_attachment/{a.get('id')}"})
            snap["cases"].append(case)
    try:
        shared = _pages(client, f"get_shared_steps/{pid}", "shared_steps")
    except Exception as e:  # старые версии TestRail без общих шагов
        shared = []
        if shared_ids:
            snap["notes"].append(f"общие шаги не получены: {e}")
    for s in shared:
        ignore = set()
        snap["shared"].append({"sid": f"SS{s['id']}", "title": s.get("title") or "",
                               "steps": _steps(s.get("custom_steps_separated"), ignore), "updated": str(s.get("updated_on") or "")})
    return snap


def load_xml(path, args):
    root = parse_xml(path)
    if tag(root) not in ("suite", "sections", "section"):
        raise ValueError(f"{path}: корень <{tag(root)}>, а TestRail выгружает <suite> — это точно XML TestRail?")
    snap = snapshot("testrail", text(root, "name"), str(path))

    def walk(sections, path_):
        for sec in sections:
            p = path_ + [text(sec, "name")]
            for c in children(child(sec, "cases") or [], "case"):
                snap["cases"].append(_xml_case(c, p, snap))
            walk(children(child(sec, "sections") or [], "section"), p)

    if tag(root) == "section":
        walk([root], [])
    else:
        walk(children((child(root, "sections") or []) if tag(root) == "suite" else root, "section"), [])
    return snap


def _xml_case(c, path, snap):
    cid = text(c, "id")
    case = new_case(sid=cid if cid.startswith("C") else (f"C{cid}" if cid else ""), title=text(c, "title"), path=path,
                    priority=text(c, "priority"), requirements=norm_list(text(c, "references")))
    case["key"] = case["sid"]
    t = text(c, "type")
    if t:
        case["custom"]["type"] = t
    if text(c, "estimate"):
        case["custom"]["estimate"] = text(c, "estimate")
    cu = child(c, "custom")
    auto = ""
    if cu is not None:
        for f in cu:
            name = tag(f)
            if name == "preconds":
                case["preconditions"] = text(f)
            elif name in ("mission", "goals"):
                case["objective"] = case["objective"] or text(f)
            elif name == "steps":
                case["steps"] = [new_step(x) for x in split_numbered(text(f))]
            elif name == "expected":
                case["expected"] = text(f)
            elif name == "steps_separated":
                for s in children(f, "step"):
                    if text(s, "shared_step_id"):
                        case["steps"].append(new_step(shared="SS" + text(s, "shared_step_id")))
                    else:
                        case["steps"].append(new_step(text(s, "content"), text(s, "expected"), text(s, "additional_info")))
            elif name == "automation_type":
                auto = text(f, "value") or text(f)
                case["custom"]["automation_type"] = auto
            else:
                v = text(f, "value") or text(f)
                if v:
                    case["custom"][name] = v
                    snap["unknown_fields"][name] = snap["unknown_fields"].get(name, 0) + 1
    case["type"] = "automated" if (auto and auto.lower() not in ("none", "manual", "нет")) or t.lower() == "automated" else "manual"
    return case
