# TMS: доступ, выгрузка, что переносится

Для каждой TMS: где взять токен, какой адрес и проект передать в `fetch.py api`, как выгрузить файл для `fetch.py file`,
что переносится и чего нет. Ответы API в фикстурах (`evals/files/replay/`) собраны по документации TMS, а не записаны с живого
сервера: на первом реальном прогоне запиши ответы (`--record <папка вне репо>`) и сверь — расхождения полей видны в сводке
«поля TMS, ушедшие в custom» и в `notes`.

## Оглавление

- [TestRail](#testrail)
- [Test IT](#test-it)
- [Zephyr Scale](#zephyr-scale)
- [TestLink](#testlink)
- [Любая таблица (CSV, xlsx)](#любая-таблица-csv-xlsx)
- [Общее для API](#общее-для-api)

## TestRail

- **Токен:** My Settings → API Keys → Add Key. Переменные `TESTRAIL_USER` (email входа) и `TESTRAIL_KEY`. API должен быть включён
  администратором (Administration → Site Settings → API).
- **Команда:** `fetch.py api <repo> --tms testrail --url https://acme.testrail.io --project 3 [--suite 7] [--attachments]`.
  `--url` — корень сайта, без `/index.php`. Проект — число из адреса `index.php?/projects/overview/3`.
- **Выгрузка:** Test Cases → Export → XML (полнее всего: секции, шаги, пользовательские поля) или CSV (Steps (Step) / Steps (Expected Result)
  — строки-продолжения разбираются). `fetch.py file <repo> --file suite.xml`, CSV — с `--tms testrail`.
- **Переносится:** сьюты (в режиме нескольких сьютов — верхним уровнем папок), вложенные секции, кейсы, шаблоны «Steps» и «Text»
  (нумерованный текст делится на шаги), общие шаги (shared steps, TestRail 7.0+), приоритет и тип по справочникам, refs → requirements,
  Automation Type → `type`, пользовательские поля с подписями и значениями списков → `custom`, labels → tags, вложения с `--attachments`.
- **Не переносится:** история версий, прогоны и результаты, вехи (milestone — только id в custom, если есть), картинки внутри текста
  (`![](index.php?/attachments/get/…)` остаются ссылкой на TMS — видны в `QUALITY.md`).
- Пагинация (TestRail 6.7+, по 250) и старый ответ списком поддержаны; на облаке есть лимит запросов — при 429 скрипт ждёт и повторяет,
  можно добавить `--delay 0.3`.

## Test IT

- **Токен:** профиль → «Приватный токен» (Private token). Переменная `TESTIT_TOKEN`, заголовок `Authorization: PrivateToken …`.
- **Команда:** `fetch.py api <repo> --tms testit --url https://testit.acme.ru --project 12`. `--url` — корень сайта, `/api/v2` скрипт
  добавит сам. Проект — номер из адреса `/projects/12/tests` (или uuid).
- **Выгрузка:** экспорт проекта в xlsx — `fetch.py file <repo> --file project.xlsx --tms testit` (колонки находятся по русским и английским
  названиям; проверь `fetch.py columns`). JSON в форме ответов API (`workItems`, `sections`, `sharedSteps`) — `--tms testit`.
- **Переносится:** секции (корневая секция проекта не становится папкой), тест-кейсы и чек-листы (`type: checklist`), общие шаги
  (SharedSteps — в `_shared/`, в кейсе ссылка), шаги с ожидаемым и тестовыми данными, предусловия и постусловия, итерации параметров →
  таблица «Параметры», теги, ссылки (ключи задач вида `SHOP-12` в ссылках → requirements), атрибуты с именами и значениями → `custom`,
  привязанные автотесты (externalId → `autotests: [ext:…]`), состояние и приоритет.
- **Сквозной номер** — globalId (виден в интерфейсе, его же пишут в `WorkItemIds` автотестов); он в `source.id`, uuid — в `custom.uuid`.
- **Проверить на живом сервере:** путь `GET /api/v2/projects/{id}/workItems` (в новых версиях может требоваться `POST /api/v2/workItems/search`)
  и форму ссылки шага на общий шаг (`workItemId`). Если сводка показывает 0 кейсов при непустом проекте — запиши ответы `--record` и поправь адаптер.

## Zephyr Scale

Только Zephyr **Scale** (бывший TM4J). Zephyr Squad и Zephyr Enterprise — другие продукты с другим API; для них — выгрузка в CSV/xlsx и `--tms table`.

- **Cloud:** токен — Jira → Zephyr → API Access Tokens; `ZEPHYR_TOKEN`. Команда: `fetch.py api <repo> --tms zephyr --project SHOP`
  (адрес по умолчанию `https://api.zephyrscale.smartbear.com/v2`; европейский регион — `--url https://eu.api.zephyrscale.smartbear.com/v2`).
  Ссылки на кейсы — `--jira https://acme.atlassian.net`.
- **Data Center / Server:** токен — личный токен Jira (Profile → Personal Access Tokens); `ZEPHYR_TOKEN`.
  `fetch.py api <repo> --tms zephyr --url https://jira.acme.ru --project SHOP` (`/rest/atm/1.0` скрипт добавит сам).
- **Выгрузка:** Tests → Export → XML или CSV/Excel. XML — `fetch.py file <repo> --file export.xml`; таблица — `--tms zephyr`.
- **Переносится:** папки, кейсы, objective → «Цель», precondition, шаги (description / testData / expectedResult), вызов другого кейса как шага
  (call to test — ссылка «Вызов кейса TC-…»), скрипт Plain и BDD (BDD — блоком gherkin), метки → tags, задачи Jira → requirements,
  веб-ссылки, пользовательские поля, приоритет и статус по справочникам.
- **Ограничение Cloud API:** связи с задачами приходят числом (`issueId`), без ключа — в кейсе `jira:10042` и заметка в сводке.
  Ключи даёт XML-выгрузка или Jira API.

## TestLink

- **Ключ:** My Settings → API interface → Generate a new key; `TESTLINK_DEVKEY`. API включается в `config.inc.php`
  (`$tlCfg->api->enabled = TRUE`).
- **Команда:** `fetch.py api <repo> --tms testlink --url https://testlink.acme.ru --project "Магазин"` (имя проекта как в TestLink;
  адрес XML-RPC `/lib/api/xmlrpc/v1/xmlrpc.php` скрипт добавит сам).
- **Выгрузка (рекомендуется):** Test Specification → корневой сьют → Export All Test Suites, XML, с ключевыми словами, требованиями и полями.
  `fetch.py file <repo> --file testsuites.xml --prefix SHOP` (префикс проекта нужен для ключей `SHOP-12`).
- **Переносится:** вложенные сьюты, кейсы, summary → «Цель», preconditions, шаги, важность → priority, тип исполнения → type,
  статус (1.9.x: draft…final, obsolete → deprecated). Только в XML: ключевые слова → tags, требования → requirements, пользовательские поля.
- Через API TestLink не отдаёт ключевые слова и требования кейсов — об этом заметка в сводке; для полного переноса — XML.

## Любая таблица (CSV, xlsx)

`fetch.py columns --file x.xlsx` показывает, какая колонка в какое поле ляжет: `id`, `title`, `section` (путь через `/`, `>` или `\`),
`priority`, `status`, `type`, `tags`, `requirements`, `preconditions`, `postconditions`, `objective`, `steps`, `expected`, `data`, `owner`, `updated`.
Остальные колонки — в `custom`. Не нашлось — `--map поле="Колонка"`. Шаги: строка без id и названия — следующий шаг того же кейса;
нумерованные «1. … 2. …» в одной ячейке делятся, если в «ожидаемом» столько же пунктов.

## Общее для API

- `--record <папка>` — записать ответы (без заголовков и токена, но **с секретами в тексте** — держи вне репозитория);
  `--replay <папка>` — прогнать без сети по записанным ответам. Так проверяют адаптер и разбирают проблемы без доступа к TMS.
- `--limit N` — пробный прогон; `--section`, `--tag` — часть проекта (тогда удалённые в TMS кейсы не ищутся).
- 429 и 5xx повторяются с паузой (до 3 раз, учитывается Retry-After); 401/403 — сразу ошибка: дело в токене или правах.
