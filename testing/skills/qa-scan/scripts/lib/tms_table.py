"""Табличная выгрузка (CSV / xlsx) любой TMS: TestRail CSV, Zephyr Scale CSV/xlsx, TestIT xlsx и др.

Колонки находятся по синонимам (ALIASES); не нашлось — `--map поле=Колонка`. Строки без id и названия —
продолжение шагов предыдущего кейса (так выгружают TestRail и Zephyr). Прочие колонки — в custom.
"""
import re

from tms_common import new_case, new_step, norm_list, pair_steps, read_table, snapshot, split_path

ALIASES = {
    "id": ["id", "key", "case id", "test case id", "test case key", "идентификатор", "ид", "ключ", "global id", "globalid",
           "сквозной идентификатор", "id кейса", "номер"],
    "title": ["title", "name", "test case name", "summary", "наименование", "название", "заголовок", "имя"],
    "section": ["section hierarchy", "section", "folder", "path", "location", "раздел", "секция", "папка", "расположение",
                "директория", "suite", "путь"],
    "priority": ["priority", "приоритет", "importance", "важность"],
    "status": ["status", "state", "статус", "состояние"],
    "type": ["automation type", "automation", "automated", "type", "тип", "автоматизация"],
    "tags": ["tags", "labels", "keywords", "теги", "метки", "ключевые слова"],
    "requirements": ["references", "refs", "requirements", "coverage (issues)", "issues", "issue links", "требования",
                     "связанные задачи", "ссылки на требования"],
    "preconditions": ["preconditions", "precondition", "предусловия", "предусловие"],
    "postconditions": ["postconditions", "postcondition", "постусловия", "постусловие"],
    "objective": ["objective", "description", "goal", "mission", "цель", "описание"],
    "steps": ["steps (step)", "test script (step-by-step) - step", "steps", "step", "шаги", "шаг", "действие", "действия",
              "action", "test step", "step description"],
    "expected": ["steps (expected result)", "test script (step-by-step) - expected result", "expected result",
                 "expected results", "expected", "ожидаемый результат", "ожидаемые результаты", "ожидание", "результат"],
    "data": ["steps (test data)", "test script (step-by-step) - test data", "test data", "data", "тестовые данные",
             "данные"],
    "owner": ["owner", "author", "created by", "автор", "владелец"],
    "updated": ["updated", "updated on", "modified", "modified date", "изменён", "изменено", "дата изменения"],
}


def auto_map(header):
    low = [h.strip().lower() for h in header]
    used, res = set(), {}
    for field, names in ALIASES.items():
        for n in names:
            if n in low and low.index(n) not in used:
                res[field] = low.index(n)
                used.add(low.index(n))
                break
    return res


def apply_overrides(header, mapping, overrides):
    low = [h.strip().lower() for h in header]
    for o in overrides or []:
        if "=" not in o:
            raise ValueError(f"--map ждёт поле=Колонка, а не {o!r}")
        f, col = o.split("=", 1)
        f, col = f.strip(), col.strip()
        if f not in ALIASES:
            raise ValueError(f"--map: нет поля {f!r}; есть: {', '.join(ALIASES)}")
        if col.lower() not in low:
            raise ValueError(f"--map: нет колонки {col!r}; есть: {', '.join(header)}")
        for k in [k for k, v in mapping.items() if v == low.index(col.lower())]:
            del mapping[k]
        mapping[f] = low.index(col.lower())
    return mapping


def find_header(rows):
    for i, r in enumerate(rows[:10]):
        m = auto_map(r)
        if "title" in m or ("id" in m and "steps" in m):
            return i
    return 0


def describe(path, sheet=None, overrides=None):
    rows = read_table(path, sheet)
    if not rows:
        raise ValueError(f"{path}: пустая таблица")
    h = find_header(rows)
    header = rows[h]
    m = apply_overrides(header, auto_map(header), overrides)
    inv = {v: k for k, v in m.items()}
    sample = rows[h + 1] if len(rows) > h + 1 else []
    lines = [f"строка заголовков: {h + 1}, строк данных: {len(rows) - h - 1}", "колонка → поле (пример значения):"]
    for i, col in enumerate(header):
        val = (sample[i] if i < len(sample) else "").replace("\n", " ")[:60]
        lines.append(f"  {col!r:40} → {inv.get(i, 'custom')}   {val!r}")
    miss = [f for f in ("title", "steps") if f not in m]
    if miss:
        lines.append(f"! не найдены поля: {', '.join(miss)} — укажи --map поле=Колонка")
    return "\n".join(lines)


def load(path, tms="table", sheet=None, overrides=None):
    rows = read_table(path, sheet)
    if not rows:
        raise ValueError(f"{path}: пустая таблица")
    h = find_header(rows)
    header = [x.strip() for x in rows[h]]
    m = apply_overrides(header, auto_map(header), overrides)
    if "title" not in m:
        raise ValueError(f"{path}: не нашёл колонку с названием кейса. Посмотри `fetch.py columns --file {path}` и укажи --map title=Колонка")
    snap = snapshot(tms, origin=str(path))
    custom_cols = [i for i in range(len(header)) if i not in m.values()]

    def g(row, f):
        i = m.get(f)
        return (row[i] if i is not None and i < len(row) else "").strip()

    cur, n = None, 0
    for row in rows[h + 1:]:
        n += 1
        cid, title = g(row, "id"), g(row, "title")
        same = cur is not None and cid and cid == cur["sid"] and (not title or title == cur["title"])
        cont = cur is not None and ((not cid and not title) or same)
        if not cont:
            cur = new_case(sid=cid or f"row{n + h + 1}", key=cid, title=title, path=split_path(g(row, "section")),
                           priority=g(row, "priority"), status=g(row, "status"),
                           tags=norm_list(g(row, "tags")), requirements=norm_list(g(row, "requirements")),
                           preconditions=g(row, "preconditions"), postconditions=g(row, "postconditions"),
                           objective=g(row, "objective"), owner=g(row, "owner"), updated=g(row, "updated"))
            t = g(row, "type").lower()
            cur["type"] = "automated" if re.search(r"auto|автомат", t) and not re.search(r"\bnone\b|manual|ручн|нет", t) else "manual"
            if t:
                cur["custom"]["type"] = g(row, "type")
            for i in custom_cols:
                if i < len(row) and str(row[i]).strip():
                    cur["custom"][header[i]] = str(row[i]).strip()
            snap["cases"].append(cur)
            cur["steps"] = pair_steps(g(row, "steps"), g(row, "expected"), g(row, "data"))
        else:
            a, e, d = g(row, "steps"), g(row, "expected"), g(row, "data")
            if a or e or d:
                cur["steps"].append(new_step(a, e, d))
    for i in custom_cols:
        snap["unknown_fields"][header[i]] = sum(1 for c in snap["cases"] if header[i] in c["custom"])
    return snap
