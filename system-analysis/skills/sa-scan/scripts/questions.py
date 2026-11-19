#!/usr/bin/env python3
"""Открытые вопросы системного анализа — system-context/QUESTIONS.md.

  python3 questions.py add <repo> --title "…?" --category "внешний сервис" --seen "…" --affects "cap / Требование"
                                 --assume "…" --who "владелец интеграции" [--importance блокирует|уточняет]
  python3 questions.py answer <repo> Q-003 "текст ответа"
  python3 questions.py set <repo> Q-003 --status внесён|снят|открыт [--note "…"]
  python3 questions.py list <repo> [--status открыт|отвечен|внесён|снят] [--json]
  python3 questions.py top <repo> [--n 7]
  python3 questions.py sync <repo>

add — следующий номер сам, формат сам, оглавление-чек-лист в начале файла обновляется само.
top — короткий список для чата: открытые, сначала блокирующие и затрагивающие больше всего требований.
sync — пересобрать чек-лист (после того как человек вписал ответы руками).
Статусы: открыт → отвечен (ответ вписан) → внесён (спека поправлена) | снят (вопрос не актуален).
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import sa  # noqa: E402


def read(P):
    if not P.questions.is_file():
        sa.die(f"нет {P.rel(P.questions)} — сначала plan.py init {P.repo}")
    return P.questions.read_text(encoding="utf-8")


def write(P, text):
    qs = sa.parse_questions(text)
    P.questions.write_text(sa.replace_index(text, qs), encoding="utf-8")
    return qs


def find(qs, qid):
    for q in qs:
        if q["id"] == qid:
            return q
    sa.die(f"нет вопроса {qid}")


def set_field(text, q, field, value):
    """Заменить значение поля вопроса (вместе со строками-продолжениями)."""
    lines = text.split("\n")
    start = q["line"]  # 1-based строка заголовка → индекс следующей строки
    end = len(lines)
    for i in range(start, len(lines)):
        if re.match(r"^#{1,3}\s", lines[i]):
            end = i
            break
    val_lines = value.strip().split("\n")
    new = [f"- **{field}:** {val_lines[0]}".rstrip()] + [f"  {x}" for x in val_lines[1:]]
    for i in range(start, end):
        m = re.match(r"^\s*[-*]\s*\*\*([^*:]+):\*\*", lines[i])
        if m and m.group(1).strip() == field:
            j = i + 1
            while j < end and lines[j].strip() and not re.match(r"^\s*[-*]\s*\*\*", lines[j]) and not lines[j].startswith("#"):
                j += 1
            lines[i:j] = new
            return "\n".join(lines)
    # поля нет — вставить после последнего поля
    k = start
    for i in range(start, end):
        if re.match(r"^\s*[-*]\s*\*\*", lines[i]):
            k = i + 1
    lines[k:k] = new
    return "\n".join(lines)


def cmd_add(a):
    P = sa.Paths(a.repo)
    text = read(P)
    qs = sa.parse_questions(text)
    if a.category not in sa.CATEGORIES:
        sa.die(f"категория «{a.category}» не из списка: " + "; ".join(sa.CATEGORIES))
    if a.importance not in sa.IMPORTANCE:
        sa.die("важность: блокирует | уточняет")
    plan = sa.load_plan(P) if P.plan.is_file() else {"capabilities": []}
    caps = {c["id"] for c in plan["capabilities"]}
    fake = {"id": "Q-000", "fields": {"Затрагивает": a.affects}}
    bad = [c for c, _ in sa.affects(fake) if c not in caps]
    if bad:
        sa.die(f"в --affects неизвестные возможности: {', '.join(bad)} — есть: {', '.join(sorted(caps)) or 'нет'}; "
               f"общий вопрос — --affects \"—\"")
    title = a.title.strip()
    for q in qs:
        if q["title"].strip().lower() == title.lower():
            sa.die(f"такой вопрос уже есть: {q['id']}")
    n = max([int(q["id"][2:]) for q in qs] + [0]) + 1
    qid = f"Q-{n:03d}"
    block = "\n".join([
        f"### {qid}. {title}",
        f"- **Статус:** открыт",
        f"- **Важность:** {a.importance}",
        f"- **Категория:** {a.category}",
        f"- **Что видно:** {a.seen.strip()}",
        f"- **Затрагивает:** {a.affects.strip()}",
        f"- **Допущение:** {a.assume.strip()}",
        f"- **Кто ответит:** {a.who.strip()}",
        f"- **Ответ:** ",
    ])
    text = text.rstrip() + "\n\n" + block + "\n"
    write(P, text)
    print(f"✓ {qid}. {title}")
    print(f"  в спеке у требования, написанного по допущению, поставь пометку: (допущение: {qid})")
    return 0


def cmd_answer(a):
    P = sa.Paths(a.repo)
    text = read(P)
    q = find(sa.parse_questions(text), a.id)
    text = set_field(text, q, "Ответ", a.text)
    q = find(sa.parse_questions(text), a.id)
    text = set_field(text, q, "Статус", "отвечен")
    write(P, text)
    print(f"✓ {a.id}: ответ записан. Внеси в спеки, сними пометки «(допущение: {a.id})», затем: questions.py set {a.repo} {a.id} --status внесён")
    return 0


def cmd_set(a):
    P = sa.Paths(a.repo)
    text = read(P)
    q = find(sa.parse_questions(text), a.id)
    if a.status == "внесён" and not q["fields"].get("Ответ", "").strip() and not a.note:
        sa.die(f"у {a.id} пустой ответ — сначала questions.py answer (или --note, чем закрыт)")
    if a.status in ("внесён", "снят"):
        left = []
        if P.specs.is_dir():
            for sp in P.specs.glob("*/spec.md"):
                if re.search(rf"\b{re.escape(a.id)}\b", sp.read_text(encoding="utf-8")):
                    left.append(P.rel(sp))
        if left:
            sa.die(f"{a.id} ещё упоминается в спеках: {', '.join(left)} — сними пометки «(допущение: {a.id})» и поправь требования")
    text = set_field(text, q, "Статус", a.status)
    if a.note:
        q = find(sa.parse_questions(text), a.id)
        text = set_field(text, q, "Ответ", (q["fields"].get("Ответ", "") + "\n" + a.note).strip())
    write(P, text)
    print(f"✓ {a.id}: {a.status}")
    return 0


def rank(q):
    imp = 0 if q["fields"].get("Важность", "") == "блокирует" else 1
    return (imp, -len(sa.affects(q)), q["id"])


def cmd_list(a):
    P = sa.Paths(a.repo)
    qs = sa.parse_questions(read(P))
    if a.status:
        qs = [q for q in qs if sa.effective_status(q) == a.status]
    if a.json:
        print(json.dumps([{"id": q["id"], "title": q["title"], "status": sa.effective_status(q), **q["fields"]} for q in qs],
                         ensure_ascii=False, indent=1))
        return 0
    for q in qs:
        print(f"{q['id']} [{sa.effective_status(q)}] {q['fields'].get('Важность', '')} · {q['title']}")
        if a.status == "отвечен":
            print(f"    затрагивает: {q['fields'].get('Затрагивает', '')}\n    ответ: {q['fields'].get('Ответ', '')}")
    print(f"— {len(qs)}", file=sys.stderr)
    return 0


def cmd_top(a):
    P = sa.Paths(a.repo)
    qs = [q for q in sa.parse_questions(read(P)) if sa.effective_status(q) == "открыт"]
    qs.sort(key=rank)
    total = len(qs)
    if not qs:
        print("Открытых вопросов нет.")
        return 0
    print(f"Открытых вопросов: {total}. Главные — ответь здесь, остальные можно в файле {P.rel(P.questions)}:\n")
    for i, q in enumerate(qs[:a.n], 1):
        f = q["fields"]
        print(f"{i}. **{q['id']}** {q['title']}")
        print(f"   Видно: {f.get('Что видно', '')}")
        print(f"   Пока считаю: {f.get('Допущение', '')}  · кто знает: {f.get('Кто ответит', '')}")
    if total > a.n:
        print(f"\n…и ещё {total - a.n} в {P.rel(P.questions)}.")
    return 0


def cmd_sync(a):
    P = sa.Paths(a.repo)
    qs = write(P, read(P))
    ans = [q["id"] for q in qs if sa.effective_status(q) == "отвечен"]
    print(f"✓ чек-лист пересобран: {len(qs)} вопросов" + (f"; ответ есть, не внесён: {', '.join(ans)}" if ans else ""))
    return 0


def main():
    ap = argparse.ArgumentParser(description="Открытые вопросы: QUESTIONS.md")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def sp(name, fn, help_):
        p = sub.add_parser(name, help=help_)
        p.add_argument("repo", help="корень репозитория")
        p.set_defaults(fn=fn)
        return p

    p = sp("add", cmd_add, "добавить вопрос")
    p.add_argument("--title", required=True, help="сам вопрос, одной фразой, с «?»")
    p.add_argument("--category", required=True, help="; ".join(sa.CATEGORIES))
    p.add_argument("--seen", required=True, help="что видно в коде или документе, со ссылкой путь:строка")
    p.add_argument("--affects", required=True, help="«cap / Требование; cap2» или «—»")
    p.add_argument("--assume", required=True, help="по какому допущению написана спека, пока нет ответа")
    p.add_argument("--who", required=True, help="кто может ответить (роль, не имя)")
    p.add_argument("--importance", default="уточняет", help="блокирует | уточняет")
    p = sp("answer", cmd_answer, "записать ответ")
    p.add_argument("id")
    p.add_argument("text")
    p = sp("set", cmd_set, "сменить статус")
    p.add_argument("id")
    p.add_argument("--status", required=True, choices=list(sa.STATUSES))
    p.add_argument("--note")
    p = sp("list", cmd_list, "список")
    p.add_argument("--status", choices=list(sa.STATUSES))
    p.add_argument("--json", action="store_true")
    sp("top", cmd_top, "главные открытые — для чата").add_argument("--n", type=int, default=7)
    sp("sync", cmd_sync, "пересобрать чек-лист")
    a = ap.parse_args()
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
