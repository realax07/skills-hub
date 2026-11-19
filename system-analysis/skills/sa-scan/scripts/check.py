#!/usr/bin/env python3
"""Проверка результата sa-scan: покрытие входов, формат спек OpenSpec, трассировка, вопросы, интеграции, указатель.

  python3 check.py <repo> [--cap <cap>] [--partial] [--no-cli] [--json]

Без --cap — всё; с --cap — одна возможность (её спека, трассировка, вопросы) и общий формат.
--partial — незаконченные возможности (status todo) не ошибка, а предупреждение: для промежуточных проверок.
Если в PATH есть CLI openspec, дополнительно запускает `openspec validate --all --strict --no-interactive` (спеки и изменения).
Код выхода: 0 — ошибок нет, 1 — есть ошибки, 2 — нечего проверять.
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import sa  # noqa: E402

PLACEHOLDER = "<!-- заполнить"
INFRA = {"базы данных", "кэш и Redis", "очереди задач"}


class Report:
    def __init__(self):
        self.err, self.warn, self.info = [], [], []

    def e(self, where, msg):
        self.err.append(f"{where}: {msg}")

    def w(self, where, msg):
        self.warn.append(f"{where}: {msg}")


def check_files(P, R):
    for p, what in [(P.config, "настройки OpenSpec"), (P.ctx / "glossary.md", "глоссарий"), (P.ctx / "domain.md", "предметная область"),
                    (P.ctx / "integrations.md", "внешние системы"), (P.trace, "трассировка"), (P.questions, "вопросы"),
                    (P.guide, "гайд (plan.py guide)"), (P.ctx / "inventory.md", "опись")]:
        if not p.is_file():
            R.e(P.rel(p), f"нет файла ({what})")
            continue
        text = p.read_text(encoding="utf-8")
        if PLACEHOLDER in text:
            n = text.count(PLACEHOLDER)
            R.e(P.rel(p), f"остались незаполненные места «{PLACEHOLDER} …» ({n}) — заполни или удали комментарий, если разделу нечего сказать")
    if P.config.is_file():
        t = P.config.read_text(encoding="utf-8")
        if not re.search(r"^schema:\s*\S", t, re.M):
            R.e(P.rel(P.config), "нет `schema:`")
        if not re.search(r"^context:\s*\|", t, re.M):
            R.e(P.rel(P.config), "нет `context: |`")
        rules = re.search(r"^rules:\s*\n((?:[ \t]+.*\n?|\s*\n)*)", t, re.M)
        if rules:
            for ln in rules.group(1).splitlines():
                m = re.match(r"^\s+-\s+(.*)$", ln)
                if m and not m.group(1).startswith(("'", '"')) and re.search(r":(\s|$)", m.group(1)):
                    R.e(P.rel(P.config), f"правило с «: » без кавычек — YAML прочтёт его как пару ключ: значение, и OpenSpec проигнорирует все правила артефакта: {m.group(1)[:60]}…")
    g = P.ctx / "glossary.md"
    if g.is_file():
        rows = [ln for ln in g.read_text(encoding="utf-8").splitlines() if ln.startswith("|") and not re.match(r"^\|\s*(Термин|---)", ln)]
        if len(rows) < 3:
            R.w(P.rel(g), f"терминов {len(rows)} — обычно их хотя бы 5–10: сущности, статусы, роли, процессы")


def check_coverage(P, R, plan, inv, only):
    ents = sa.all_entries(inv, plan)
    asg = sa.assignment(plan)
    if not only:
        for eid in ents:
            if eid not in asg:
                R.e("plan.json", f"вход «{eid}» не относится ни к одной возможности и не исключён (plan.py move / exclude)")
    if not only:
        for eid in asg:
            if eid not in ents:
                R.e("plan.json", f"вход «{eid}» есть в плане, но нет в описи — после пересканирования он переименован или удалён: "
                                 f"plan.py prune, затем новый id — move")
    for x in plan.get("excluded", []):
        if not x.get("reason", "").strip():
            R.e("plan.json", f"исключение «{x['entry']}» без причины")
    caps = {c["id"] for c in plan["capabilities"]}
    for c in plan["capabilities"]:
        if only and c["id"] != only:
            continue
        if not sa.ID_RX.match(c["id"]):
            R.e("plan.json", f"id «{c['id']}» не kebab-case")
        if not c["title"].strip():
            R.e("plan.json", f"у {c['id']} нет названия (plan.py set … --title)")
        if not c["entries"]:
            R.info.append(f"{c['id']}: без своих входов — нормально для сквозной возможности (доступ, общие ошибки API)")
        if c["status"] != "done":
            (R.w if R.partial else R.e)("plan.json", f"{c['id']} не готова (status {c['status']})")
        if c["status"] == "done" and not P.spec(c["id"]).is_file():
            R.e("plan.json", f"{c['id']} отмечена done, но нет {P.rel(P.spec(c['id']))}")
    if not only and P.specs.is_dir():
        for d in sorted(P.specs.iterdir()):
            if d.is_dir() and d.name not in caps and (d / "spec.md").is_file():
                R.w(P.rel(d), "спека есть, а возможности в плане нет — добавь (plan.py add-cap) или это чужая спека")


def check_specs(P, R, plan, only):
    specs = {}
    for c in plan["capabilities"]:
        if only and c["id"] != only:
            continue
        p = P.spec(c["id"])
        if not p.is_file():
            continue
        err, warn, parsed = sa.spec_problems(p.read_text(encoding="utf-8"))
        for m in err:
            R.e(P.rel(p), m)
        for m in warn:
            R.w(P.rel(p), m)
        specs[c["id"]] = parsed
    return specs


def check_trace(P, R, specs, text=None, where=None):
    if text is None:
        if not P.trace.is_file():
            return
        text = P.trace.read_text(encoding="utf-8")
    tr = sa.parse_trace(text)
    tpath = where or P.trace
    for cap, parsed in specs.items():
        names = {r["name"] for r in parsed["requirements"]}
        got = tr.get(cap, {})
        if not got:
            R.e(P.rel(tpath), f"нет раздела `## {cap}` со строками «требование → код»")
            continue
        for r in parsed["requirements"]:
            if r["name"] not in got:
                R.e(P.rel(tpath), f"{cap}: нет строки для требования «{r['name']}»")
        for name, rec in got.items():
            if name not in names:
                R.w(P.rel(tpath), f"стр. {rec['line']}: «{name}» — такого требования в {cap}/spec.md нет (имя должно совпадать)")
            if not rec["code"]:
                R.e(P.rel(tpath), f"стр. {rec['line']}: у «{name}» нет ни одного пути к коду")
            for path in rec["code"] + rec["tests"]:
                fp = sa.strip_loc(path)
                if fp and not (P.repo / fp).exists():
                    R.e(P.rel(tpath), f"стр. {rec['line']}: нет файла {fp}")


def validate_question(R, where, q, caps, specs):
    f = q["fields"]
    for k in sa.Q_FIELDS:
        if k not in f:
            R.e(where, f"нет поля «{k}»")
        elif k not in ("Ответ",) and not f[k].strip():
            R.e(where, f"пустое поле «{k}»")
    st = f.get("Статус", "").strip().lower()
    if st and st not in sa.STATUSES:
        R.e(where, f"статус «{st}» — допустимы: {', '.join(sa.STATUSES)}")
    if f.get("Важность", "").strip() and f["Важность"].strip() not in sa.IMPORTANCE:
        R.e(where, f"важность «{f['Важность']}» — блокирует | уточняет")
    if f.get("Категория", "").strip() and f["Категория"].strip() not in sa.CATEGORIES:
        R.w(where, f"категория «{f['Категория']}» не из списка (references/questions.md)")
    if not q["title"].rstrip().endswith("?"):
        R.w(where, "заголовок — сам вопрос, с «?» в конце")
    for cap, req in sa.affects(q):
        if cap not in caps:
            R.e(where, f"затрагивает неизвестную возможность «{cap}»")
        elif req and cap in specs and req not in {r["name"] for r in specs[cap]["requirements"]}:
            R.w(where, f"затрагивает «{cap} / {req}» — такого требования нет")


def check_work(P, R, plan, specs, cap):
    """Режим раздачи: результат работника до сборки — трассировка и вопросы из .work/<cap>/, пометки TMP-…"""
    d = P.workdir(cap)
    if not d.is_dir():
        R.e(P.rel(d), "нет папки работника — бриф: plan.py brief")
        return
    if cap not in specs:
        R.e(P.rel(P.spec(cap)), "нет спеки")
        return
    tp = d / "trace.md"
    check_trace(P, R, specs, f"## {cap}\n" + (tp.read_text(encoding="utf-8") if tp.is_file() else ""), tp)
    qp = d / "questions.md"
    wq = sa.parse_questions(qp.read_text(encoding="utf-8")) if qp.is_file() else []
    caps = {c["id"]: c for c in plan["capabilities"]}
    ids = []
    for q in wq:
        where = f"{P.rel(qp)} {q['id']}"
        if not q["id"].startswith("TMP-"):
            R.e(where, "у работника номера временные: TMP-1, TMP-2…")
        if q["id"] in ids:
            R.e(where, "номер повторяется")
        ids.append(q["id"])
        validate_question(R, where, q, caps, specs)
    st = P.spec(cap).read_text(encoding="utf-8")
    used = set(sa.TMP_RX.findall(st))
    for m in sorted(used - set(ids)):
        R.e(P.rel(P.spec(cap)), f"пометка {m}, а в {P.rel(qp)} такого вопроса нет")
    for m in sorted(set(ids) - used):
        R.w(P.rel(qp), f"{m} не помечен ни в одном требовании — если вопрос общий, это нормально")
    if sa.Q_RX.search(st):
        for m in sorted(set(sa.Q_RX.findall(st))):
            known = sa.parse_questions(P.questions.read_text(encoding="utf-8")) if P.questions.is_file() else []
            if m not in {q["id"] for q in known}:
                R.e(P.rel(P.spec(cap)), f"ссылка на {m}, такого вопроса нет — свои вопросы работник нумерует TMP-…")
    notes = d / "notes.md"
    if not notes.is_file():
        R.w(P.rel(notes), "нет заметок для главного агента")


def check_questions(P, R, plan, specs, only):
    if not P.questions.is_file():
        return
    text = P.questions.read_text(encoding="utf-8")
    qs = sa.parse_questions(text)
    by_id = {}
    caps = {c["id"]: c for c in plan["capabilities"]}
    for q in qs:
        if only and q["id"] not in by_id and not any(c == only for c, _ in sa.affects(q)):
            by_id[q["id"]] = q
            continue
        where = f"{P.rel(P.questions)} {q['id']}"
        if q["id"] in by_id:
            R.e(where, "номер повторяется")
        by_id[q["id"]] = q
        validate_question(R, where, q, caps, specs)
        if sa.effective_status(q) == "отвечен":
            R.w(where, "ответ есть, но не внесён в спеку — режим «внести ответы» (SKILL.md)")
    # пометки допущений в спеках
    for cap, parsed in specs.items():
        p = P.spec(cap)
        for m in sorted(set(sa.Q_RX.findall(p.read_text(encoding="utf-8")))):
            q = by_id.get(m)
            if not q:
                R.e(P.rel(p), f"ссылка на {m}, а в QUESTIONS.md такого вопроса нет")
            elif sa.effective_status(q) in ("внесён", "снят"):
                R.e(P.rel(p), f"пометка {m} осталась, а вопрос уже {sa.effective_status(q)} — сними пометку")
    for cap, parsed in specs.items():
        p = P.spec(cap)
        left = sorted(set(sa.TMP_RX.findall(p.read_text(encoding="utf-8"))))
        if left and not (P.workdir(cap)).is_dir():
            R.e(P.rel(p), f"временные пометки {', '.join(left)} — результат работника не собран: plan.py collect")
    # пересобранный чек-лист совпадает
    if sa.replace_index(text, qs) != text:
        R.w(P.rel(P.questions), "чек-лист в начале файла устарел — questions.py sync")
    if not only:
        n_open = sum(1 for q in qs if sa.effective_status(q) == "открыт")
        R.info.append(f"вопросов: {len(qs)}, открыто: {n_open}")


def check_changes(P, R):
    """Изменения, которые предложил скилл (из ответов «в коде ошибка»): proposal, tasks, корректная дельта."""
    ch = P.openspec / "changes"
    if not ch.is_dir():
        return
    for d in sorted(ch.iterdir()):
        if not d.is_dir() or d.name == "archive":
            continue
        where = P.rel(d)
        if not sa.ID_RX.match(d.name):
            R.e(where, "имя изменения — kebab-case (fix-order-item-limit)")
        for f in ("proposal.md", "tasks.md"):
            if not (d / f).is_file():
                R.e(where, f"нет {f}")
        deltas = list((d / "specs").glob("*/spec.md")) if (d / "specs").is_dir() else []
        if not deltas:
            R.e(where, "нет дельты спеки specs/<возможность>/spec.md")
        for sp in deltas:
            cap = sp.parent.name
            main = P.spec(cap)
            parsed = sa.parse_spec(main.read_text(encoding="utf-8")) if main.is_file() else None
            for m in sa.delta_problems(sp.read_text(encoding="utf-8"), parsed):
                R.e(P.rel(sp), m)


def check_integrations(P, R, inv):
    p = P.ctx / "integrations.md"
    if not p.is_file():
        return
    text = p.read_text(encoding="utf-8").lower()
    for host in inv.get("outbound", {}).get("hosts", {}):
        rec = inv["outbound"]["hosts"][host]
        if all("(тест)" in f for f in rec["files"]):
            continue
        base = host.split(":")[0]
        parts = base.split(".")
        short = ".".join(parts[-2:]) if len(parts) >= 2 else base
        if base not in text and short not in text:
            R.e(P.rel(p), f"внешний хост {host} из описи не описан (или впиши его в «Инфраструктура» / «Не интеграции» с пояснением)")
    seen = set()
    for u in inv.get("outbound", {}).get("sdk", []):
        if u["category"] in INFRA or u["sdk"] in seen:
            continue
        seen.add(u["sdk"])
        name = u["sdk"].split("/")[-1].lower()
        if u["sdk"].lower() not in text and name not in text:
            R.e(P.rel(p), f"SDK {u['sdk']} ({u['category']}) используется в {u['file']}, но в integrations.md не упомянут — "
                          f"впиши имя пакета `{u['sdk']}` буквально в раздел его системы (например, в строку «В коде»)")


def check_link(P, R):
    for f in ("AGENTS.md", "CLAUDE.md", "GEMINI.md", "QWEN.md", ".github/copilot-instructions.md"):
        fp = P.repo / f
        if fp.is_file() and "<!-- sa-scan:start -->" in fp.read_text(encoding="utf-8", errors="replace"):
            return
    R.w("AGENTS.md", "указатель на system-context не вписан ни в один файл инструкций (link.py) — если пользователь не просил не трогать их")


def run_cli(P, R):
    exe = shutil.which("openspec")
    if not exe:
        R.info.append("CLI openspec не найден — формат проверен своим разбором (тот же набор правил)")
        return
    try:
        r = subprocess.run([exe, "validate", "--all", "--strict", "--no-interactive"], cwd=str(P.repo),
                           capture_output=True, text=True, timeout=180)
    except (OSError, subprocess.TimeoutExpired) as ex:
        R.w("openspec", f"CLI не отработал: {ex}")
        return
    out = (r.stdout + r.stderr).strip()
    if r.returncode != 0:
        R.e("openspec validate --all --strict", out[-2000:] or f"код {r.returncode}")
    else:
        n = len([d for d in (P.openspec / "changes").iterdir() if d.is_dir() and d.name != "archive"]) if (P.openspec / "changes").is_dir() else 0
        R.info.append(f"openspec validate --all --strict: ✓ (спеки и изменений: {n})")


def main():
    ap = argparse.ArgumentParser(description="Проверка system-context/ и openspec/")
    ap.add_argument("repo")
    ap.add_argument("--cap", help="проверить одну возможность")
    ap.add_argument("--partial", action="store_true", help="незаконченные возможности — предупреждение, не ошибка")
    ap.add_argument("--no-cli", action="store_true", help="не запускать CLI openspec")
    ap.add_argument("--work", action="store_true", help="с --cap: проверить результат работника в system-context/.work/<cap>/")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    if a.work and not a.cap:
        sa.die("--work — только вместе с --cap <cap>")
    P = sa.Paths(a.repo)
    if not P.plan.is_file() or not P.inventory.is_file():
        print(f"нечего проверять: нет {P.rel(P.plan)} или {P.rel(P.inventory)} — сначала inventory.py scan и plan.py init", file=sys.stderr)
        return 2
    plan, inv = sa.load_plan(P), sa.load_inventory(P)
    R = Report()
    R.partial = a.partial or bool(a.cap)
    if a.cap:
        sa_ids = {c["id"] for c in plan["capabilities"]}
        if a.cap not in sa_ids:
            sa.die(f"нет возможности {a.cap}")
    check_coverage(P, R, plan, inv, a.cap)
    specs = check_specs(P, R, plan, a.cap)
    if a.work:
        R.err = [m for m in R.err if not m.startswith("plan.json")]
        R.warn = [m for m in R.warn if not m.startswith("plan.json")]
        check_work(P, R, plan, specs, a.cap)
    else:
        check_trace(P, R, specs)
        check_questions(P, R, plan, specs, a.cap)
    if not a.cap:
        check_files(P, R)
        check_integrations(P, R, inv)
        check_changes(P, R)
        check_link(P, R)
        if P.work.is_dir():
            rest = [d.name for d in P.work.iterdir() if d.is_dir() and not d.name.startswith("_")]
            (R.e if rest else R.w)(P.rel(P.work), (f"не собраны результаты работников: {', '.join(rest)} — plan.py collect" if rest else
                                                  "раздача собрана — перенеси .work/NOTES.md в общие файлы и удали папку .work/"))
        if not a.no_cli:
            run_cli(P, R)
    nreq = sum(len(s["requirements"]) for s in specs.values())
    nsc = sum(len(r["scenarios"]) for s in specs.values() for r in s["requirements"])
    R.info.insert(0, f"спек: {len(specs)}, требований: {nreq}, сценариев: {nsc}")
    if a.json:
        print(json.dumps({"errors": R.err, "warnings": R.warn, "info": R.info}, ensure_ascii=False, indent=1))
    else:
        for m in R.err:
            print(f"✗ {m}")
        for m in R.warn:
            print(f"! {m}")
        for m in R.info:
            print(f"· {m}")
        print(f"\n{'✓ готово' if not R.err else '✗ ошибок: ' + str(len(R.err))}, предупреждений: {len(R.warn)}")
    return 1 if R.err else 0


if __name__ == "__main__":
    sys.exit(main())
