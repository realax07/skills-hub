#!/usr/bin/env python3
"""Собирает фикстуры qa-scan: выгрузки всех TMS и записанные ответы API (для fetch.py --replay).

  python3 evals/files/make_fixtures.py        # перезаписывает evals/files/exports и evals/files/replay

Один и тот же маленький магазин во всех форматах — чтобы сравнивать адаптеры между собой.
Ответы API собраны по документации TMS (форма полей), а не записаны с живого сервера: см. references/tms.md.
"""
import hashlib
import json
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

HERE = Path(__file__).resolve().parent
EXP = HERE / "exports"
REP = HERE / "replay"


def rec(d, key, body, status=200):
    d.mkdir(parents=True, exist_ok=True)
    name = hashlib.sha1(key.encode()).hexdigest()[:16] + ".json"
    data = {"key": key, "body": body}
    if status != 200:
        data["status"] = status
    (d / name).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


# ---------------------------------------------------------------- Test IT (API v2)

def testit():
    d = REP / "testit"
    proj = "11111111-0000-0000-0000-000000000001"
    root, s1, s2 = "aaaa0000-0000-0000-0000-000000000000", "aaaa0000-0000-0000-0000-000000000001", "aaaa0000-0000-0000-0000-000000000002"
    rec(d, "GET /projects/12", {"id": proj, "globalId": 12, "name": "Магазин"})
    rec(d, f"GET /projects/{proj}/sections", [
        {"id": root, "name": "Магазин", "parentId": None},
        {"id": s1, "name": "Оформление заказа", "parentId": root},
        {"id": s2, "name": "Отмена заказа", "parentId": root}])
    rec(d, f"GET /projects/{proj}/attributes", [
        {"id": "attr-1", "name": "Компонент", "options": [{"id": "opt-1", "value": "Корзина"}, {"id": "opt-2", "value": "Админка"}]}])
    items = [
        {"id": "wi-0001", "globalId": 1001, "name": "Вход покупателем", "entityTypeName": "SharedSteps", "sectionId": root,
         "steps": [{"action": "<p>Открыть /login</p>", "expected": "", "testData": ""},
                   {"action": "Ввести логин buyer@example.com и пароль из $SHOP_BUYER_PASSWORD", "expected": "Открыт личный кабинет", "testData": ""}],
         "modifiedDate": "2026-10-01T10:00:00Z"},
        {"id": "wi-0002", "globalId": 1002, "name": "Оформление заказа с картой", "entityTypeName": "TestCases", "sectionId": s1,
         "state": "Ready", "priority": "High", "isAutomated": True, "tags": [{"name": "smoke"}, {"name": "checkout"}],
         "links": [{"title": "SHOP-12 Оформление", "url": "https://jira.example.com/browse/SHOP-12", "type": "Requirement"}],
         "preconditionSteps": [{"action": "В каталоге есть товары"}],
         "steps": [{"workItemId": "wi-0001"},
                   {"action": "<ol><li>Добавить товар в корзину</li><li>Нажать <b>Оформить</b></li></ol>",
                    "expected": "<p>Открыта оплата, сумма = цене товара</p>", "testData": "Карта: {card}"},
                   {"action": "Оплатить", "expected": "Заказ в статусе PAID", "testData": ""}],
         "iterations": [{"parameters": [{"name": "card", "value": "4242 4242 4242 4242"}]},
                        {"parameters": [{"name": "card", "value": "5555 5555 5555 4444"}]}],
         "attributes": {"attr-1": "opt-1"}, "versionNumber": 3, "modifiedDate": "2026-10-02T10:00:00Z"},
        {"id": "wi-0003", "globalId": 1003, "name": "Покупатель не отменяет оплаченный заказ", "entityTypeName": "TestCases",
         "sectionId": s2, "state": "NeedsWork", "priority": "Medium", "isAutomated": False, "tags": [],
         "steps": [{"workItemId": "wi-0001"},
                   {"action": "Открыть оплаченный заказ", "expected": "Кнопки «Отменить» нет", "testData": ""},
                   {"action": "Вызвать API с заголовком Authorization: Bearer abcdefghijklmnopqrstuvwxyz0123", "expected": "409", "testData": ""}],
         "modifiedDate": "2026-10-03T10:00:00Z"},
        {"id": "wi-0004", "globalId": 1004, "name": "Чек-лист отмены менеджером", "entityTypeName": "CheckLists", "sectionId": s2,
         "state": "Ready", "priority": "Low", "steps": [{"action": "Возврат в Stripe создан"}, {"action": "Письмо покупателю ушло"}],
         "modifiedDate": "2026-10-04T10:00:00Z"},
    ]
    rec(d, f"GET /projects/{proj}/workItems?Skip=0&Take=100&includeIterations=true",
        [{"id": w["id"], "globalId": w["globalId"], "name": w["name"], "entityTypeName": w["entityTypeName"]} for w in items])
    for w in items:
        rec(d, f"GET /workItems/{w['id']}", w)
    rec(d, "GET /workItems/wi-0002/autoTests", [{"externalId": "shop.checkout.test_card_payment", "name": "test_card_payment"}])


# ---------------------------------------------------------------- TestRail (API v2)

def testrail():
    d = REP / "testrail"
    rec(d, "GET get_project/1", {"id": 1, "name": "Магазин", "suite_mode": 1})
    rec(d, "GET get_priorities", [{"id": 1, "name": "Low"}, {"id": 2, "name": "Medium"}, {"id": 3, "name": "High"}, {"id": 4, "name": "Critical"}])
    rec(d, "GET get_case_types", [{"id": 1, "name": "Acceptance"}, {"id": 6, "name": "Functional"}])
    rec(d, "GET get_case_fields", [
        {"system_name": "custom_automation_type", "label": "Automation Type", "type_id": 6,
         "configs": [{"options": {"items": "0, None\n1, Automated"}}]},
        {"system_name": "custom_component", "label": "Компонент", "type_id": 6, "configs": [{"options": {"items": "1, Корзина\n2, Склад"}}]}])
    rec(d, "GET get_suites/1", [{"id": 1, "name": "Master"}])
    rec(d, "GET get_sections/1&suite_id=1", {"offset": 0, "limit": 250, "size": 3, "_links": {"next": None},
                                            "sections": [{"id": 10, "name": "Оформление", "parent_id": None},
                                                         {"id": 11, "name": "Доставка", "parent_id": None},
                                                         {"id": 12, "name": "Склад", "parent_id": 11}]})
    rec(d, "GET get_cases/1&suite_id=1", {"offset": 0, "limit": 2, "size": 2, "_links": {"next": "/api/v2/get_cases/1&suite_id=1&limit=2&offset=2"},
                                         "cases": [
        {"id": 201, "title": "Оформление из корзины", "section_id": 10, "priority_id": 4, "type_id": 6, "refs": "SHOP-12",
         "custom_automation_type": 1, "custom_preconds": "Есть товары", "updated_on": 1760000000,
         "custom_steps_separated": [{"shared_step_id": 5}, {"content": "Оформить заказ", "expected": "Заказ NEW"}]},
        {"id": 202, "title": "Пустая корзина", "section_id": 10, "priority_id": 2, "type_id": 6, "custom_automation_type": 0,
         "custom_steps": "1. Открыть пустую корзину\n2. Нажать «Оформить»", "custom_expected": "Кнопка неактивна"}]})
    rec(d, "GET get_cases/1&suite_id=1&limit=2&offset=2", {"offset": 2, "limit": 2, "size": 1, "_links": {"next": None}, "cases": [
        {"id": 203, "title": "Передача на склад", "section_id": 12, "priority_id": 1, "type_id": 6, "custom_component": 2,
         "custom_steps_separated": [{"content": "Запустить отгрузку", "expected": "Склад получил задание"}]}]})
    rec(d, "GET get_shared_steps/1", {"offset": 0, "limit": 250, "size": 1, "_links": {"next": None}, "shared_steps": [
        {"id": 5, "title": "Вход покупателем", "custom_steps_separated": [{"content": "Войти как buyer@example.com", "expected": "Кабинет открыт"}]}]})


# ---------------------------------------------------------------- Zephyr Scale Cloud (API v2)

def zephyr():
    d = REP / "zephyr"
    q = "maxResults=100&startAt=0"
    rec(d, f"GET /folders?projectKey=SHOP&folderType=TEST_CASE&{q}", {"isLast": True, "values": [
        {"id": 1, "parentId": None, "name": "Заказы"}, {"id": 2, "parentId": 1, "name": "Отмена"}]})
    rec(d, f"GET /priorities?projectKey=SHOP&{q}", {"isLast": True, "values": [{"id": 10, "name": "High"}, {"id": 11, "name": "Normal"}]})
    rec(d, f"GET /statuses?projectKey=SHOP&statusType=TEST_CASE&{q}", {"isLast": True, "values": [{"id": 20, "name": "Approved"}, {"id": 21, "name": "Draft"}]})
    rec(d, f"GET /testcases?projectKey=SHOP&{q}", {"isLast": True, "values": [
        {"id": 1, "key": "SHOP-T1", "name": "Вход покупателем", "folder": {"id": 1}, "priority": {"id": 11}, "status": {"id": 20},
         "labels": ["auth"], "testScript": {"self": "https://api.zephyrscale.smartbear.com/v2/testcases/SHOP-T1/teststeps"}},
        {"id": 2, "key": "SHOP-T2", "name": "Отмена неоплаченного заказа", "folder": {"id": 2}, "priority": {"id": 10},
         "status": {"id": 20}, "labels": ["regress"], "objective": "<p>Покупатель отменяет заказ <b>NEW</b></p>",
         "links": {"issues": [{"issueId": 10042}], "webLinks": [{"url": "https://wiki.example.com/cancel", "description": "Правила отмены"}]},
         "customFields": {"Компонент": "Заказы"},
         "testScript": {"self": "https://api.zephyrscale.smartbear.com/v2/testcases/SHOP-T2/teststeps"}},
        {"id": 3, "key": "SHOP-T3", "name": "Автоотмена через 30 минут", "folder": {"id": 2}, "priority": {"id": 11}, "status": {"id": 21},
         "testScript": {"self": "https://api.zephyrscale.smartbear.com/v2/testcases/SHOP-T3/testscript"}}]})
    rec(d, f"GET /testcases/SHOP-T1/teststeps?{q}", {"isLast": True, "values": [
        {"inline": {"description": "Открыть /login", "testData": "login=buyer@example.com; password=Buyer#2024", "expectedResult": "Кабинет открыт"}}]})
    rec(d, f"GET /testcases/SHOP-T2/teststeps?{q}", {"isLast": True, "values": [
        {"testCase": {"testCaseKey": "SHOP-T1"}},
        {"inline": {"description": "Открыть заказ NEW и нажать «Отменить»", "testData": "", "expectedResult": "Статус CANCELLED"}}]})
    rec(d, "GET /testcases/SHOP-T3/testscript", {"type": "bdd", "text": "Given заказ NEW\nWhen прошло 30 минут\nThen заказ CANCELLED"})


# ---------------------------------------------------------------- TestLink (XML-RPC)

def testlink():
    d = REP / "testlink"

    def x(method, params, body):
        rec(d, f"xmlrpc {method} " + json.dumps(params, ensure_ascii=False, sort_keys=True), body)

    x("tl.getTestProjectByName", {"testprojectname": "Магазин"}, {"id": "1", "name": "Магазин", "prefix": "SHOP"})
    x("tl.getFirstLevelTestSuitesForTestProject", {"testprojectid": "1"}, [{"id": "10", "name": "Оплата", "parent_id": "1"}])
    x("tl.getTestCasesForTestSuite", {"deep": False, "details": "full", "testsuiteid": "10"}, [
        {"id": "100", "name": "Оплата картой", "tc_external_id": "7", "summary": "<p>Оплата <em>картой</em></p>", "preconditions": "",
         "importance": "3", "execution_type": "1", "status": "7", "version": "2",
         "steps": [{"step_number": "1", "actions": "<p>Ввести карту</p>", "expected_results": "<p>Платёж прошёл</p>"}]}])
    x("tl.getTestSuitesForTestSuite", {"testsuiteid": "10"}, {"id": "11", "name": "Возвраты", "parent_id": "10"})
    x("tl.getTestCasesForTestSuite", {"deep": False, "details": "full", "testsuiteid": "11"}, [
        {"id": "101", "name": "Возврат при отмене", "tc_external_id": "8", "importance": "2", "execution_type": "2", "status": "1"}])
    x("tl.getTestCase", {"testcaseid": "101"}, [{"id": "101", "steps": [
        {"step_number": "1", "actions": "Отменить оплаченный заказ", "expected_results": "Возврат создан"}]}])
    x("tl.getTestSuitesForTestSuite", {"testsuiteid": "11"}, [])


# ---------------------------------------------------------------- файлы выгрузки

TESTLINK_XML = """<?xml version="1.0" encoding="UTF-8"?>
<testsuite id="1" name="Магазин">
  <node_order><![CDATA[1]]></node_order>
  <details><![CDATA[]]></details>
  <testsuite id="10" name="Оплата">
    <testcase internalid="100" name="Оплата картой">
      <node_order><![CDATA[1]]></node_order>
      <externalid><![CDATA[7]]></externalid>
      <version><![CDATA[2]]></version>
      <summary><![CDATA[<p>Оплата <em>картой</em> по ссылке из письма</p>]]></summary>
      <preconditions><![CDATA[<p>Заказ в статусе NEW</p>]]></preconditions>
      <execution_type><![CDATA[1]]></execution_type>
      <importance><![CDATA[3]]></importance>
      <status><![CDATA[7]]></status>
      <steps>
        <step><step_number><![CDATA[1]]></step_number><actions><![CDATA[<p>Ввести карту 4000 0000 0000 0002</p>]]></actions><expectedresults><![CDATA[<p>Отказ банка, заказ остаётся NEW</p>]]></expectedresults><execution_type><![CDATA[1]]></execution_type></step>
        <step><step_number><![CDATA[2]]></step_number><actions><![CDATA[<p>Ввести карту 4242 4242 4242 4242</p>]]></actions><expectedresults><![CDATA[<table><tr><th>Поле</th><th>Значение</th></tr><tr><td>Статус</td><td>PAID</td></tr></table>]]></expectedresults><execution_type><![CDATA[1]]></execution_type></step>
      </steps>
      <keywords><keyword name="smoke"><notes><![CDATA[]]></notes></keyword><keyword name="payment"><notes><![CDATA[]]></notes></keyword></keywords>
      <custom_fields><custom_field><name><![CDATA[Браузер]]></name><value><![CDATA[Chrome]]></value></custom_field></custom_fields>
      <requirements><requirement><req_spec_title><![CDATA[Оплата]]></req_spec_title><doc_id><![CDATA[REQ-PAY-1]]></doc_id><title><![CDATA[Оплата картой]]></title></requirement></requirements>
    </testcase>
    <testsuite id="11" name="Возвраты">
      <testcase internalid="101" name="Возврат при отмене">
        <externalid><![CDATA[8]]></externalid>
        <summary><![CDATA[]]></summary>
        <execution_type><![CDATA[2]]></execution_type>
        <importance><![CDATA[2]]></importance>
        <status><![CDATA[5]]></status>
        <steps><step><step_number>1</step_number><actions><![CDATA[Отменить оплаченный заказ]]></actions><expectedresults><![CDATA[Возврат создан]]></expectedresults></step></steps>
      </testcase>
    </testsuite>
  </testsuite>
</testsuite>
"""

ZEPHYR_XML = """<?xml version="1.0" encoding="UTF-8"?>
<project>
  <projectId>10000</projectId>
  <projectKey>SHOP</projectKey>
  <folders><folder fullPath="Заказы" index="0"/><folder fullPath="Заказы/Отмена" index="1"/></folders>
  <testCases>
    <testCase id="1" key="SHOP-T1">
      <name><![CDATA[Вход покупателем]]></name>
      <folder><![CDATA[Заказы]]></folder>
      <priority><![CDATA[Normal]]></priority>
      <status><![CDATA[Approved]]></status>
      <labels><label><![CDATA[auth]]></label></labels>
      <testScript type="steps"><steps>
        <step index="0"><description><![CDATA[Открыть /login]]></description><testData><![CDATA[login=buyer@example.com; password=Buyer#2024]]></testData><expectedResult><![CDATA[Кабинет открыт]]></expectedResult></step>
      </steps></testScript>
    </testCase>
    <testCase id="2" key="SHOP-T2">
      <name><![CDATA[Отмена неоплаченного заказа]]></name>
      <folder><![CDATA[Заказы/Отмена]]></folder>
      <objective><![CDATA[<p>Покупатель отменяет заказ <b>NEW</b></p>]]></objective>
      <priority><![CDATA[High]]></priority>
      <status><![CDATA[Approved]]></status>
      <labels><label><![CDATA[regress]]></label></labels>
      <issues><issue><key><![CDATA[SHOP-31]]></key></issue></issues>
      <customFields><customField name="Компонент" type="SINGLE_CHOICE_SELECT_LIST"><value><![CDATA[Заказы]]></value></customField></customFields>
      <testScript type="steps"><steps>
        <step index="0"><testCaseKey><![CDATA[SHOP-T1]]></testCaseKey></step>
        <step index="1"><description><![CDATA[Открыть заказ NEW и нажать «Отменить»]]></description><expectedResult><![CDATA[Статус CANCELLED]]></expectedResult></step>
      </steps></testScript>
    </testCase>
    <testCase id="3" key="SHOP-T3">
      <name><![CDATA[Автоотмена через 30 минут]]></name>
      <folder><![CDATA[Заказы/Отмена]]></folder>
      <priority><![CDATA[Normal]]></priority>
      <status><![CDATA[Draft]]></status>
      <testScript type="bdd"><![CDATA[Given заказ NEW
When прошло 30 минут
Then заказ CANCELLED]]></testScript>
    </testCase>
  </testCases>
</project>
"""

TESTRAIL_CSV = """ID,Title,Section Hierarchy,Priority,Type,References,Preconditions,Steps (Step),Steps (Expected Result),Automation Type
C301,Оформление заказа,Заказы > Оформление,High,Functional,SHOP-12,Пользователь вошёл,Добавить товар в корзину,Товар в корзине,Automated
,,,,,,,Оформить заказ,Заказ NEW,
,,,,,,,Оплатить,Заказ PAID,
C302,Отмена заказа,Заказы > Отмена,Medium,Functional,,,"Открыть заказ
и нажать «Отменить»",Заказ CANCELLED,None
"""

TESTIT_XLSX_ROWS = [
    ["ID", "Расположение", "Наименование", "Приоритет", "Статус", "Шаги", "Ожидаемый результат", "Тестовые данные", "Теги", "Автор"],
    ["2001", "Магазин/Корзина", "Пересчёт суммы корзины", "Высокий", "Готов", "1. Добавить два товара\n2. Удалить один",
     "1. Сумма = двум ценам\n2. Сумма = одной цене", "", "smoke; cart", "Иванова"],
    ["2002", "Магазин/Корзина", "Пустая корзина", "Низкий", "Черновик", "Открыть корзину", "Текст «Корзина пуста»", "", "", "Иванова"],
]


def xlsx(path, rows):
    def cell(ref, v):
        return f'<c r="{ref}" t="inlineStr"><is><t xml:space="preserve">{escape(str(v))}</t></is></c>'
    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    sheet = "".join(f'<row r="{i + 1}">' + "".join(cell(f"{letters[j]}{i + 1}", v) for j, v in enumerate(r)) + "</row>"
                    for i, r in enumerate(rows))
    m = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    r = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                   '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                   '<Default Extension="xml" ContentType="application/xml"/>'
                   '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
                   '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>')
        z.writestr("_rels/.rels", '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        z.writestr("xl/workbook.xml", f'<?xml version="1.0" encoding="UTF-8"?><workbook xmlns="{m}" xmlns:r="{r}"><sheets><sheet name="Тест-кейсы" sheetId="1" r:id="rId1"/></sheets></workbook>')
        z.writestr("xl/_rels/workbook.xml.rels", '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>')
        z.writestr("xl/worksheets/sheet1.xml", f'<?xml version="1.0" encoding="UTF-8"?><worksheet xmlns="{m}"><sheetData>{sheet}</sheetData></worksheet>')


def main():
    for f in list(REP.rglob("*.json")):
        f.unlink()
    EXP.mkdir(parents=True, exist_ok=True)
    testit()
    testrail()
    zephyr()
    testlink()
    (EXP / "testlink-shop.xml").write_text(TESTLINK_XML, encoding="utf-8")
    (EXP / "zephyr-shop.xml").write_text(ZEPHYR_XML, encoding="utf-8")
    (EXP / "testrail-shop.csv").write_text(TESTRAIL_CSV, encoding="utf-8")
    xlsx(EXP / "testit-shop.xlsx", TESTIT_XLSX_ROWS)
    print(f"✓ {EXP}, {REP}")


if __name__ == "__main__":
    main()
