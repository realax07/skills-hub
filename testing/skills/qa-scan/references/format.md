# Формат слоя test-cases/

md первичен: этот формат держит `check.py`, а пишут его люди, агенты и `build.py`/`new.py`.

## Кейс — `TC-NNNN-<slug>.md`

```markdown
---
id: TC-0004
title: "Покупатель не может отменить оплаченный заказ"
priority: high
status: ready
type: automated
tags: [regress]
requirements: [SHOP-31]
capabilities: [order-cancellation]
code: [src/routes/orders.ts]
autotests: [test/orders.test.ts:8, ext:shop.orders.test_cancel_paid]
source:
  tms: testrail
  id: C110
  key: C110
  url: "https://acme.testrail.io/index.php?/cases/view/110"
  section: "Отмена заказа / Покупатель"
  updated: 1760000000
  hash: 9f2c1a0b7d3e
custom:
  type: Functional
  "Automation Type": Automated
---

# TC-0004 Покупатель не может отменить оплаченный заказ

## Цель

Что проверяет кейс (если было в TMS: objective, summary, mission).

## Предусловия

Покупатель вошёл, есть заказ в статусе PAID.

## Шаги

1. [Общий шаг SS-001: Вход покупателем](../../_shared/SS-001-vhod-pokupatelem.md)
2. Открыть свой заказ в статусе PAID
   - **Ожидается:** Кнопки «Отменить» нет
3. Вызвать PUT /api/orders/{id}/cancel с токеном покупателя
   - **Данные:** токен: [скрыто: S-02]
   - **Ожидается:** Ответ 409, статус не изменился

## Ожидаемый результат

Только если в TMS ожидаемое было одно на весь кейс (TestRail «Text», таблица без разбивки).

## Постусловия

## Параметры

| card | result |
|---|---|
| 4242 4242 4242 4242 | PAID |

## Ссылки

- [Правила отмены](https://wiki.example.com/cancel)

## Вложения

- [screen.png](../../_attachments/TC-0004/screen.png)
```

### Поля front-matter

| Поле | Значения | Откуда |
|---|---|---|
| `id` | `TC-0001`… — постоянный, не переиспользуется | `build.py`, `new.py` |
| `title` | название | TMS |
| `priority` | `highest`, `high`, `medium`, `low`, `lowest` | TMS: Critical/Blocker → highest, Major → high, Normal → medium, Minor → low, Trivial → lowest; русские тоже |
| `status` | `ready`, `draft`, `needs-work`, `deprecated` | TMS: Approved/Ready/Final → ready, Draft/New → draft, Review/Rework → needs-work, Obsolete/Archived → deprecated |
| `type` | `manual`, `automated`, `checklist` | TMS: тип автоматизации, Test IT CheckLists |
| `tags` | список | метки, ключевые слова, теги TMS |
| `requirements` | ключи задач и требований | refs, issue links, требования TestLink; `jira:<число>` — ключ не пришёл |
| `capabilities` | возможности из `openspec/specs/` | `map.py` (обогащение) |
| `code` | файлы и папки кода от корня | `map.py set --code`, правка руками (обогащение) |
| `autotests` | `путь:строка` (найдено в коде) или `ext:<externalId>` (привязка в TMS) | TMS, `map.py` (обогащение) |
| `source` | откуда кейс: `tms`, `id`, `key`, `url`, `section`, `version`, `updated`, `hash` | `build.py`; у кейса из `new.py` — `tms: md` |
| `custom` | прочие поля TMS как есть | TMS |

Списки — в квадратных скобках через запятую; строки с пробелами и не-латиницей — в кавычках. Так пишет скрипт;
список строками `- x` под ключом скрипты тоже читают.

**`source.hash`** — хеш файла на момент импорта без полей обогащения. Не совпадает с файлом — кейс правили в md, повторный импорт его не тронет.
Поэтому `hash` руками не правят.

### Шаги

- Шаг — строка `N. действие` с начала строки; нумерация подряд с 1 (`check.py` предупредит о пропусках).
- Под шагом с отступом 3 пробела — `- **Ожидается:** …` и `- **Данные:** …`; продолжение текста — с отступом 5.
  Таблица, код или список в значении — с новой строки после метки.
- Общий шаг — ссылка `[Общий шаг SS-001: <название>](<путь к _shared/…>)`; вызов другого кейса (Zephyr) — `[Вызов кейса TC-0001: …](…)`.
- Заголовки разделов — по-русски (`Цель`, `Предусловия`, `Шаги`, `Ожидаемый результат`, `Постусловия`, `Параметры`, `Ссылки`, `Вложения`, `Заметки`)
  или по-английски (`Objective`, `Preconditions`, `Steps`, `Expected result`, `Postconditions`, `Parameters`, `Links`, `Attachments`, `Notes`) —
  как задано при импорте (`--lang`). Раздел «Заметки» — свободный, для людей и агентов.

## Общий шаг — `_shared/SS-NNN-<slug>.md`

```markdown
---
id: SS-001
title: "Вход покупателем"
type: shared
source:
  tms: testit
  id: 1001
  hash: …
---

# SS-001 Вход покупателем

## Шаги

1. Открыть /login
2. Ввести логин buyer@example.com и пароль из $SHOP_BUYER_PASSWORD
   - **Ожидается:** Открыт личный кабинет
```

## Служебные файлы

| Файл | Что | Правят руками? |
|---|---|---|
| `ROUTING.md` | карта для агента | нет — `route.py index` |
| `<папка>/INDEX.md` | список кейсов папки | нет |
| `_index/by-*.md`, `_index/index.json` | индексы роутинга | нет |
| `QUESTIONS.md` | вопросы человеку | да — вне блоков `<!-- qa:auto:… -->` |
| `QUALITY.md` | отчёт `lint.py` | нет |
| `.source/ids.json` | номер TC ↔ id в TMS, выданные номера | нет; коммитить обязательно |
| `.source/config.json` | TMS, адрес без токена, проект, фильтры, язык | нет |
| `.source/redactions.json` | скрытые секреты и ПДн: номер, вид, длина, где — без значений | нет |
| `.source/snapshot.json`, `incoming/`, `files/` | снимок TMS, конфликтные версии, скачанные вложения до раскладки | нет; не коммитятся (`.gitignore`) |

## Папки

Имя папки — транслит названия раздела TMS (`Отмена заказа` → `otmena-zakaza`), человеческое имя — в `source.section` кейсов и в `INDEX.md`.
Разные разделы с одинаковым транслитом в одной папке получают суффикс `-2`. Папки с `_` в начале — служебные.
