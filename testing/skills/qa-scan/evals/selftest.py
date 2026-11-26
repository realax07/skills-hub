#!/usr/bin/env python3
"""Самопроверка скриптов qa-scan на фикстурах (без сети): все адаптеры, повторный импорт, роутинг, проверки.

  python3 evals/selftest.py            # из папки скилла; код 0 — всё прошло

Фикстуры — evals/files/ (собирает evals/files/make_fixtures.py). Рабочие папки — во временном каталоге.
"""
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
S = SKILL / "scripts"
F = SKILL / "evals" / "files"
FAILS = []


def run(*args, ok=True):
    r = subprocess.run([sys.executable, *map(str, args)], capture_output=True, text=True)
    if ok and r.returncode != 0:
        FAILS.append(f"{' '.join(map(str, args[:3]))}: код {r.returncode}\n{r.stdout}\n{r.stderr}")
    return r.stdout + r.stderr


def expect(cond, msg):
    if not cond:
        FAILS.append(msg)


def cases(w):
    return {p.name.split("-", 2)[0] + "-" + p.name.split("-", 2)[1]: p.read_text(encoding="utf-8")
            for p in (w / "test-cases").rglob("*.md") if re.match(r"^(TC|SS)-\d+", p.name)}


def fresh(name):
    w = Path(tempfile.mkdtemp(prefix=f"qa-{name}-"))
    return w


def adapter(name, *fetch_args, checks=()):
    w = fresh(name)
    out = run(S / "fetch.py", fetch_args[0], w, *fetch_args[1:])
    run(S / "build.py", w)
    out += run(S / "check.py", w, "--no-pointer")
    cs = cases(w)
    for fn, msg in checks:
        try:
            expect(fn(cs, out, w), f"{name}: {msg}")
        except Exception as e:  # noqa: BLE001
            FAILS.append(f"{name}: {msg} — {e!r}")
    shutil.rmtree(w)
    return cs


def main():
    R, E = F / "replay", F / "exports"
    adapter("testit-api", "api", "--tms", "testit", "--url", "https://testit.example.com", "--project", "12", "--replay", R / "testit", checks=[
        (lambda c, o, w: "SS-001" in c and "[Общий шаг SS-001" in c["TC-0001"], "общий шаг вынесен и связан"),
        (lambda c, o, w: "| 4242 4242 4242 4242 |" in c["TC-0001"], "параметры таблицей"),
        (lambda c, o, w: "ext:shop.checkout.test_card_payment" in c["TC-0001"], "автотест из TMS"),
        (lambda c, o, w: "[скрыто: S-01]" in c["TC-0002"] and "abcdefghijklmnop" not in c["TC-0002"], "bearer скрыт"),
        (lambda c, o, w: "type: checklist" in c["TC-0003"], "чек-лист"),
        (lambda c, o, w: "Компонент: \"Корзина\"" in c["TC-0001"], "атрибут по имени и значению"),
        (lambda c, o, w: "ошибок 0" in o, "check без ошибок"),
    ])
    adapter("testrail-api", "api", "--tms", "testrail", "--url", "https://acme.testrail.io", "--project", "1", "--replay", R / "testrail", checks=[
        (lambda c, o, w: len([k for k in c if k.startswith("TC")]) == 3, "три кейса (две страницы)"),
        (lambda c, o, w: "[Общий шаг SS-001: Вход покупателем]" in c["TC-0001"], "общий шаг TestRail"),
        (lambda c, o, w: "priority: highest" in c["TC-0001"] and "type: automated" in c["TC-0001"], "приоритет и автоматизация по справочникам"),
        (lambda c, o, w: "2. Нажать «Оформить»" in c["TC-0002"], "текстовый шаблон разбит на шаги"),
        (lambda c, o, w: (w / "test-cases/dostavka/sklad").is_dir(), "вложенные секции → папки"),
        (lambda c, o, w: "ошибок 0" in o, "check без ошибок"),
    ])
    adapter("zephyr-api", "api", "--tms", "zephyr", "--project", "SHOP", "--replay", R / "zephyr", checks=[
        (lambda c, o, w: "[Вызов кейса TC-0001: Вход покупателем](../TC-0001-vhod-pokupatelem.md)" in c["TC-0002"], "вызов кейса — ссылка на кейс"),
        (lambda c, o, w: "jira:10042" in c["TC-0002"], "ссылка на задачу числом"),
        (lambda c, o, w: "```gherkin" in c["TC-0003"], "BDD-скрипт"),
        (lambda c, o, w: "Buyer#2024" not in json.dumps(c), "пароль в тестовых данных скрыт"),
        (lambda c, o, w: "ошибок 0" in o, "check без ошибок"),
    ])
    adapter("testlink-api", "api", "--tms", "testlink", "--url", "https://tl.example.com", "--project", "Магазин", "--replay", R / "testlink", checks=[
        (lambda c, o, w: "key: SHOP-7" in c["TC-0001"], "ключ с префиксом"),
        (lambda c, o, w: "Возврат создан" in c["TC-0002"], "шаги догружены getTestCase"),
        (lambda c, o, w: "ошибок 0" in o, "check без ошибок"),
    ])
    adapter("testlink-xml", "file", "--file", E / "testlink-shop.xml", "--prefix", "SHOP", checks=[
        (lambda c, o, w: "tags: [smoke, payment]" in c["TC-0001"] and "REQ-PAY-1" in c["TC-0001"], "ключевые слова и требования"),
        (lambda c, o, w: "**Ожидается:**\n     | Поле | Значение |" in c["TC-0001"], "HTML-таблица → md с новой строки"),
        (lambda c, o, w: "status: deprecated" in c["TC-0002"], "статус obsolete"),
        (lambda c, o, w: "ошибок 0" in o, "check без ошибок"),
    ])
    adapter("zephyr-xml", "file", "--file", E / "zephyr-shop.xml", checks=[
        (lambda c, o, w: "requirements: [SHOP-31]" in c["TC-0002"], "issue-ключи"),
        (lambda c, o, w: "status: draft" in c["TC-0003"], "статус Draft"),
        (lambda c, o, w: "ошибок 0" in o, "check без ошибок"),
    ])
    adapter("testrail-csv", "file", "--file", E / "testrail-shop.csv", "--tms", "testrail", checks=[
        (lambda c, o, w: "3. Оплатить" in c["TC-0001"], "строки-продолжения → шаги"),
        (lambda c, o, w: "type: automated" in c["TC-0001"] and "type: manual" in c["TC-0002"], "тип по Automation Type"),
        (lambda c, o, w: "ошибок 0" in o, "check без ошибок"),
    ])
    adapter("testit-xlsx", "file", "--file", E / "testit-shop.xlsx", "--tms", "testit", checks=[
        (lambda c, o, w: "2. Удалить один" in c["TC-0001"] and "Сумма = одной цене" in c["TC-0001"], "нумерованные шаги и ожидаемое попарно"),
        (lambda c, o, w: "priority: high" in c["TC-0001"] and "status: draft" in c["TC-0002"], "русские приоритет и статус"),
        (lambda c, o, w: "ошибок 0" in o, "check без ошибок"),
    ])

    # полный цикл на проекте магазина: TestRail XML + openspec + автотесты
    w = fresh("shop")
    shutil.copytree(F / "shop", w, dirs_exist_ok=True)
    shutil.copytree(SKILL, w / ".opencode" / "skills" / "qa-scan", ignore=shutil.ignore_patterns("evals"))  # скилл в проекте
    (w / "exports").mkdir()
    shutil.copy(E / "testrail-shop.xml", w / "exports")
    out = run(S / "fetch.py", "file", w, "--file", w / "exports" / "testrail-shop.xml")
    expect("лежит в репозитории и содержит секреты" in out, f"shop: предупреждение о выгрузке с секретами в репозитории\n{out}")
    run(S / "build.py", w)
    out = run(S / "map.py", "auto", w)
    allauto = " ".join(cases(w).values())
    expect(".opencode" not in allauto, "shop: автотесты не ищутся в папке установленного скилла")
    expect("назначено 8" in out, f"shop: все 8 кейсов сопоставлены с возможностями\n{out}")
    expect("найдены для 3" in out, f"shop: автотесты по аннотациям\n{out}")
    out = run(S / "route.py", "find", w, "--cap", "order-cancellation")
    expect("найдено: 3" in out, f"shop: route --cap\n{out}")
    out = run(S / "route.py", "find", w, "--req", "SHOP-12")
    expect("найдено: 2" in out, f"shop: route --req\n{out}")
    out = run(S / "lint.py", w)
    expect("размытое ожидаемое 1" in out and "одинаковые шаги 1" in out and "есть шаги без ожидаемого результата 1" in out, f"shop: lint\n{out}")
    out = run(S / "link.py", w, "--file", "AGENTS.md")
    expect("CLAUDE.md: создан" in out and (w / "CLAUDE.md").read_text() == "@AGENTS.md\n", f"shop: CLAUDE.md с импортом AGENTS.md\n{out}")
    out = run(S / "check.py", w)
    expect("ошибок 0, предупреждений 0" in out, f"shop: check после link\n{out}")
    q = (w / "test-cases/QUESTIONS.md").read_text(encoding="utf-8")
    expect("S-01 пароль" in q and "Qwerty" not in json.dumps(cases(w)), "shop: секрет скрыт и в вопросах")
    # повторный импорт: правка в md + изменение в TMS → конфликт; без правки → обновление; enrichment сохраняется
    tc = next((w / "test-cases").rglob("TC-0004-*.md"))
    tc.write_text(tc.read_text(encoding="utf-8").replace("Ответ 409, статус не изменился", "Ответ 409 и сообщение"), encoding="utf-8")
    v2 = w / "v2.xml"
    s = (E / "testrail-shop.xml").read_text(encoding="utf-8")
    s = s.replace("<expected>Ответ 422</expected>", "<expected>Ответ 422 и текст ошибки</expected>")
    s = s.replace("Кнопки «Отменить» нет", "Кнопка «Отменить» скрыта")
    s = re.sub(r"<case>\s*<id>C131</id>.*?</case>", "", s, flags=re.S)
    v2.write_text(s, encoding="utf-8")
    run(S / "fetch.py", "file", w, "--file", v2)
    out = run(S / "build.py", w)
    expect("обновлено 1" in out and "конфликтов 1" in out and "нет в TMS 1" in out, f"shop: повторный импорт\n{out}")
    t2 = next((w / "test-cases").rglob("TC-0002-*.md")).read_text(encoding="utf-8")
    expect("capabilities: [order-checkout]" in t2 and "текст ошибки" in t2, "shop: обогащение сохранено при обновлении")
    out = run(S / "build.py", w, "--keep", "TC-0004")
    out = run(S / "build.py", w)
    expect("конфликтов 0" in out, f"shop: --keep снял конфликт\n{out}")
    out = run(S / "new.py", w, "--title", "Отмена после отгрузки", "--section", "Отмена заказа/Менеджер", "--cap", "order-cancellation")
    expect("otmena-zakaza/menedzher/TC-0009" in out, f"shop: new.py в существующую папку по имени раздела\n{out}")
    out = run(S / "check.py", w, ok=False)
    expect("заполнить" in out and "ошибок 0" in out, f"shop: check видит каркас\n{out}")
    tc9 = next((w / "test-cases").rglob("TC-0009-*.md"))
    tc9.write_text(tc9.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    bad = next((w / "test-cases").rglob("TC-0001-*.md"))
    bad.write_text(bad.read_text(encoding="utf-8").replace("[скрыто: S-01]", "Qwerty!2024"), encoding="utf-8")
    out = run(S / "check.py", w, ok=False)
    expect("похоже на секрет" in out, f"shop: check ловит секрет, вписанный руками\n{out}")
    shutil.rmtree(w)

    if FAILS:
        print("✗ провалено:", len(FAILS))
        for f in FAILS:
            print(" -", f)
        return 1
    print("✓ selftest: все проверки прошли")
    return 0


if __name__ == "__main__":
    sys.exit(main())
