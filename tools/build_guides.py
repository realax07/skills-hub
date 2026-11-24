#!/usr/bin/env python3
"""Сборка guide.html для каждого скилла: наглядный разбор для людей — что даёт скилл, как работает, куда что кладёт
и как результат используется дальше.

  python3 tools/build_guides.py                 # все скиллы с guide.json
  python3 tools/build_guides.py web-design      # тема или папка скилла
  python3 tools/build_guides.py --check         # ничего не пишет; код 1, если гайд устарел или его нет

Источники: <скилл>/guide.json (содержание, правится руками) + tools/guide/template.html (вид, общий для всех).
В guide.html записывается хэш SKILL.md и guide.json: validate.py предупредит, когда скилл поменялся, а гайд — нет.
Формат guide.json — в docs/skill-guide.md, раздел «Гайд для людей». Только стандартная библиотека.
"""
import argparse
import hashlib
import html
import json
import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TEMPLATE = REPO / "tools" / "guide" / "template.html"
LANES = [("human", "Человек"), ("model", "Модель"), ("script", "Скрипт")]
LANE_NAME = dict(LANES)
REQUIRED = ("title", "tagline", "gives", "flow", "tree", "lifecycle")
GIT = {"yes": ("yes", "в git"), "no": ("no", "не коммитить"), "opt": ("opt", "по желанию")}


def esc(s):
    return html.escape(str(s), quote=True)


def inline(s):
    """Мини-разметка в текстах guide.json: `код`, **жирный**, [текст](ссылка)."""
    s = esc(s)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", r'<a href="\2">\1</a>', s)
    return s


def slug(s):
    return "f-" + re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def all_skills():
    return sorted(p.parent for p in REPO.glob("*/skills/*/SKILL.md") if not p.parent.parent.parent.name.startswith((".", "_")))


def source_hash(skill):
    h = hashlib.sha256()
    for name in ("SKILL.md", "guide.json"):
        p = skill / name
        h.update(p.read_bytes() if p.is_file() else b"")
    h.update(TEMPLATE.read_bytes())
    h.update(Path(__file__).read_bytes())
    return h.hexdigest()[:16]


def skill_hash_in(guide_html):
    m = re.search(r'<meta name="skill-hash" content="([0-9a-f]+)">', guide_html)
    return m.group(1) if m else None


def link_to(skill, other):
    """Относительная ссылка из гайда скилла на гайд другого скилла хаба."""
    target = next((s for s in all_skills() if s.name == other), None)
    if not target:
        return None
    return Path(os.path.relpath(target / "guide.html", skill)).as_posix()


# ---------------------------------------------------------------- разделы

def sec_gives(d):
    cards = "".join(f'<div class="card"><h3>{inline(g["title"])}</h3><p>{inline(g["text"])}</p></div>' for g in d["gives"])
    return f'<section id="gives"><div class="wrap"><h2>Что даёт</h2><p class="sub">{inline(d.get("gives_intro", ""))}</p>' \
           f'<div class="grid cards">{cards}</div></div></section>'


def sec_when(d):
    w = d.get("when")
    if not w:
        return ""
    yes = "".join(f"<li>{inline(x)}</li>" for x in w.get("yes", []))
    no = "".join(f"<li>{inline(x)}</li>" for x in w.get("no", []))
    inputs = ""
    if d.get("inputs"):
        rows = "".join(f'<tr><td><b>{inline(i["name"])}</b></td><td>{inline(i.get("need", ""))}</td><td>{inline(i.get("note", ""))}</td></tr>'
                       for i in d["inputs"])
        inputs = f'<h3 style="margin:26px 0 10px">Что нужно на входе</h3><div class="tablebox"><table><tr><th>Что</th><th>Нужно</th>' \
                 f'<th>Зачем и как</th></tr>{rows}</table></div>'
    return f'<section id="when"><div class="wrap"><h2>Когда звать</h2><p class="sub">{inline(w.get("intro", ""))}</p>' \
           f'<div class="grid two"><div class="card yes"><h3>Подходит</h3><ul class="list">{yes}</ul></div>' \
           f'<div class="card no"><h3>Не подходит</h3><ul class="list">{no}</ul></div></div>{inputs}</div></section>'


def sec_flow(d, tree_ids):
    rows = []
    for i, st in enumerate(d["flow"], 1):
        who = st["who"] if isinstance(st["who"], list) else [st["who"]]
        main = who[0]
        outs = ""
        if st.get("out"):
            chips = []
            for o in st["out"]:
                sid = slug(o)
                chips.append(f'<a class="chip file" href="#{sid}">{esc(o)}</a>' if sid in tree_ids else f'<span class="chip file">{esc(o)}</span>')
            outs = '<div class="outs">' + "".join(chips) + "</div>"
        cmd = f'<code class="cmd">{esc(st["cmd"])}</code>' if st.get("cmd") else ""
        also = "".join(f'<span class="chip {w}">{LANE_NAME[w]}</span> ' for w in who[1:])
        card = (f'<div class="step {main}"><span class="chip {main} badge-mob">{LANE_NAME[main]}</span>'
                f'<h4>{inline(st["title"])}</h4><p>{inline(st.get("text", ""))}</p>{cmd}{outs}'
                + (f'<div style="margin-top:6px">{also}</div>' if also else "") + "</div>")
        cells = []
        for lane, _ in LANES:
            if lane == main:
                cells.append(f'<div class="lane">{card}</div>')
            else:
                cls = "lane dim also" if lane in who else "lane dim"
                color = f' style="color:var(--{lane})"' if lane in who else ""
                cells.append(f'<div class="{cls}"{color}></div>')
        rows.append(f'<div class="frow"><div class="num">{esc(st.get("n", i))}</div>{"".join(cells)}</div>')
    legend = "".join(f'<span class="chip {k}">{v}</span>' for k, v in LANES)
    return (f'<section id="flow"><div class="wrap"><h2>Как работает</h2><p class="sub">{inline(d.get("flow_intro", ""))}</p>'
            f'<div class="legend">{legend}<span style="color:var(--muted)">— кто делает шаг; файлы под шагом — что он создаёт (нажми, чтобы найти в дереве)</span></div>'
            f'<div class="flow"><div class="lanes-head"><span></span><div class="h">Человек</div><div class="m">Модель</div><div class="s">Скрипт</div></div>'
            f'{"".join(rows)}</div></div></section>')


def tree_rows(items):
    """Плоский список путей → строки дерева: папки выводятся сами, файлы — с описанием."""
    seen, out = set(), []
    for it in items:
        parts = it["path"].rstrip("/").split("/")
        for k in range(1, len(parts)):
            d = "/".join(parts[:k]) + "/"
            if d not in seen and d not in {x["path"] for x in items}:
                seen.add(d)
                out.append(({"path": d, "auto": True}, k - 1))
        seen.add(it["path"])
        out.append((it, len(parts) - 1))
    return out


def sec_tree(d):
    rows = []
    ids = set()
    for it, depth in tree_rows(d["tree"]):
        name = it["path"].rstrip("/").split("/")[-1] + ("/" if it["path"].endswith("/") else "")
        ind = f'<span class="ind" style="width:{depth * 18}px"></span>'
        icon = "📁 " if it["path"].endswith("/") else "📄 "
        if it.get("auto"):
            rows.append(f'<tr class="dir"><td class="path">{ind}{icon}{esc(name)}</td><td></td><td></td><td></td></tr>')
            continue
        sid = slug(it["path"])
        ids.add(sid)
        g = GIT.get(it.get("git", ""), None)
        git = f'<span class="git {g[0]}">{g[1]}</span>' if g else ""
        rows.append(f'<tr id="{sid}" class="{"dir" if it["path"].endswith("/") else ""}"><td class="path">{ind}{icon}{esc(name)}</td>'
                    f'<td>{inline(it.get("desc", ""))}</td><td class="who">{inline(it.get("by", ""))}<br>→ {inline(it.get("for", ""))}</td><td>{git}</td></tr>')
    html_ = (f'<section id="tree"><div class="wrap"><h2>Куда что складывает</h2><p class="sub">{inline(d.get("tree_intro", ""))}</p>'
             f'<div class="tablebox tree"><table><tr><th>Путь</th><th>Что внутри</th><th>Кто пишет → кто читает</th><th>Git</th></tr>'
             f'{"".join(rows)}</table></div></div></section>')
    return html_, ids


def sec_life(d, skill):
    stages = []
    for st in d["lifecycle"]:
        sk = ""
        if st.get("skill"):
            href = link_to(skill, st["skill"])
            if href and st["skill"] != skill.name:
                sk = f'<a class="skill" href="{href}">{esc(st["skill"])} →</a>'
            elif not href:
                sk = f'<span class="skill" style="color:var(--muted)">{esc(st["skill"])} · в планах</span>'
            else:
                sk = f'<span class="skill">{esc(st["skill"])} · этот скилл</span>'
        cur = " cur" if st.get("skill") == skill.name or st.get("current") else ""
        stages.append(f'<div class="stage{cur}"><div class="box"><h4>{inline(st["title"])}</h4><p>{inline(st.get("text", ""))}</p>{sk}</div>'
                      f'<div class="arrow">→</div></div>')
    modes = ""
    if d.get("modes"):
        modes = '<div class="grid modes">' + "".join(
            f'<div class="card"><h3>{inline(m["name"])}</h3><p><b>Когда:</b> {inline(m.get("when", ""))}</p>'
            f'<p style="margin-top:6px">{inline(m.get("text", ""))}</p></div>' for m in d["modes"]) + "</div>"
    use = ""
    if d.get("usage"):
        use = '<h3 style="margin:26px 0 10px">Как результат используется потом</h3><div class="grid cards">' + "".join(
            f'<div class="card"><h3>{inline(u["who"])}</h3><p>{inline(u["text"])}</p></div>' for u in d["usage"]) + "</div>"
    return (f'<section id="life"><div class="wrap"><h2>Что дальше</h2><p class="sub">{inline(d.get("lifecycle_intro", ""))}</p>'
            f'<div class="pipe">{"".join(stages)}</div>{modes}{use}</div></section>')


def sec_examples(d):
    ex = d.get("examples") or []
    if not ex:
        return ""
    tabs = "".join(f'<button type="button" aria-selected="{"true" if i == 0 else "false"}">{esc(e["title"])}</button>' for i, e in enumerate(ex))
    panes = "".join(f'<div class="example{" on" if i == 0 else ""}"><p class="note">{inline(e.get("note", ""))}</p>'
                    f'<pre class="code">{esc(e["code"].rstrip())}</pre></div>' for i, e in enumerate(ex))
    return (f'<section id="examples"><div class="wrap"><h2>Примеры из прогонов</h2><p class="sub">{inline(d.get("examples_intro", ""))}</p>'
            f'<div data-tabs><div class="tabs" role="tablist">{tabs}</div>{panes}</div></div></section>')


def sec_metrics(d):
    ms = d.get("metrics") or []
    if not ms:
        return ""
    out = []
    for m in ms:
        mx = m.get("max") or max(v["value"] for v in m["values"]) or 1
        bars = "".join(f'<div class="bar"><span>{inline(v["name"])}</span><div class="track"><div class="fill{" alt" if v.get("alt") else ""}" '
                       f'style="width:{min(100, 100 * v["value"] / mx):.0f}%"></div></div><span class="val">{esc(v.get("label", v["value"]))}</span></div>'
                       for v in m["values"])
        out.append(f'<div class="metric card"><h4>{inline(m["title"])}</h4>{bars}<p class="note">{inline(m.get("note", ""))}</p></div>')
    return (f'<section id="metrics"><div class="wrap"><h2>Замеры</h2><p class="sub">{inline(d.get("metrics_intro", ""))}</p>'
            f'<div class="grid two">{"".join(out)}</div></div></section>')


def sec_rules(d):
    rs = d.get("rules") or []
    pit = d.get("pitfalls") or []
    if not rs and not pit:
        return ""
    r = "".join(f'<li><b>{inline(x["title"])}</b>{inline(x["text"])}</li>' for x in rs)
    p = "".join(f'<tr><td>{inline(x["symptom"])}</td><td>{inline(x["fix"])}</td></tr>' for x in pit)
    ptab = f'<h3 style="margin:26px 0 10px">Если что-то пошло не так</h3><div class="tablebox"><table><tr><th>Симптом</th><th>Что делать</th></tr>{p}</table></div>' if p else ""
    return (f'<section id="rules"><div class="wrap"><h2>Главные правила</h2><p class="sub">Почему скилл ведёт себя так, а не иначе.</p>'
            f'<ul class="list rules">{r}</ul>{ptab}</div></section>')


def render(skill):
    d = json.loads((skill / "guide.json").read_text(encoding="utf-8"))
    miss = [k for k in REQUIRED if not d.get(k)]
    if miss:
        raise ValueError(f"{skill}/guide.json: нет полей {', '.join(miss)}")
    tree_html, tree_ids = sec_tree(d)
    toc = [("gives", "Что даёт"), ("when", "Когда звать"), ("flow", "Как работает"), ("tree", "Куда складывает"), ("life", "Что дальше")]
    if d.get("examples"):
        toc.append(("examples", "Примеры"))
    if d.get("metrics"):
        toc.append(("metrics", "Замеры"))
    if d.get("rules"):
        toc.append(("rules", "Правила"))
    theme = skill.parent.parent.name
    readme = Path(os.path.relpath(skill.parent.parent / "README.md", skill)).as_posix()
    body = (f'<header class="top"><div class="wrap"><span class="crumbs"><a href="{readme}">{esc(theme)}</a> / <b>{esc(skill.name)}</b></span>'
            f'<nav class="toc">{"".join(f"<a href=#{a}>{b}</a>" for a, b in toc)}</nav>'
            f'<button class="theme-btn" id="theme" type="button">тема</button></div></header>'
            f'<div class="hero"><div class="wrap"><div class="kicker">{esc(d.get("kicker", skill.name))}</div><h1>{inline(d["title"])}</h1>'
            f'<p class="lead">{inline(d["tagline"])}</p></div></div>'
            + sec_gives(d) + sec_when(d) + sec_flow(d, tree_ids) + tree_html + sec_life(d, skill)
            + sec_examples(d) + sec_metrics(d) + sec_rules(d)
            + f'<footer><div class="wrap">Подробно для агента — <a href="SKILL.md">SKILL.md</a>. Гайд собран <code>tools/build_guides.py</code> '
              f'из <code>guide.json</code>; правь его, а не этот файл.</div></footer>')
    tpl = TEMPLATE.read_text(encoding="utf-8")
    return tpl.replace("{{TITLE}}", esc(f"{skill.name} — гайд")).replace("{{HASH}}", source_hash(skill)).replace("{{BODY}}", body)


def status(skill):
    """'нет данных' | 'нет гайда' | 'устарел' | 'ок'"""
    if not (skill / "guide.json").is_file():
        return "нет данных"
    g = skill / "guide.html"
    if not g.is_file():
        return "нет гайда"
    return "ок" if skill_hash_in(g.read_text(encoding="utf-8")) == source_hash(skill) else "устарел"


def main():
    ap = argparse.ArgumentParser(description="Сборка guide.html скиллов из guide.json")
    ap.add_argument("paths", nargs="*", help="тема или папка скилла; по умолчанию все")
    ap.add_argument("--check", action="store_true", help="только проверить: код 1, если гайд устарел или его нет")
    a = ap.parse_args()
    skills = all_skills()
    if a.paths:
        want = [Path(p).resolve() for p in a.paths]
        skills = [s for s in skills if any(s == w or w in s.parents for w in want)]
    bad = 0
    for s in skills:
        rel = s.relative_to(REPO).as_posix()
        st = status(s)
        if a.check:
            print(f"{'✓' if st == 'ок' else '✗'} {rel}: {st}")
            bad += st != "ок"
            continue
        if st == "нет данных":
            print(f"· {rel}: нет guide.json — пропускаю")
            continue
        try:
            (s / "guide.html").write_text(render(s), encoding="utf-8")
        except (ValueError, KeyError, json.JSONDecodeError) as e:
            print(f"✗ {rel}: {e}")
            bad += 1
            continue
        print(f"✓ {rel}/guide.html")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
