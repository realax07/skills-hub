# Тест-кейсы — карта

Перенесены из TestRail «Магазин — регресс» (файл testrail-shop.xml, 2026-11-25). Кейсов 8, общих шагов 0. **md первичен**: кейсы правят здесь, TMS — только источник переноса.

## Как найти кейсы под задачу

| Задача | Где искать |
|---|---|
| Меняю поведение возможности (из `openspec/specs/`) | `_index/by-capability.md`, раздел `## <возможность>` |
| Меняю файл кода | `grep -n "<путь>" test-cases/_index/by-code.md` |
| Есть ключ требования или задачи | `grep -n "<КЛЮЧ-12>" test-cases/_index/by-requirement.md` |
| Набор регресса, тег (smoke…) | `_index/by-tag.md` |
| Кейс ↔ автотест | `_index/by-autotest.md` |
| По словам | `grep -ril "<слово>" test-cases --include="TC-*.md"` |
| Область целиком | «Области» ниже → `INDEX.md` папки |

Со скиллом qa-scan — одной командой: `python3 <qa-scan>/scripts/route.py find . --cap <возможность> --path <файл> --text "<слова>"`.

## Области

| Папка | Раздел | Кейсов |
|---|---|---|
| [dostavka/](dostavka/INDEX.md) | Доставка | 2 |
| [oformlenie-zakaza/](oformlenie-zakaza/INDEX.md) | Оформление заказа | 3 |
| [otmena-zakaza/](otmena-zakaza/INDEX.md) | Отмена заказа | 3 |
| &nbsp;&nbsp;[otmena-zakaza/menedzher/](otmena-zakaza/menedzher/INDEX.md) | Менеджер | 1 |
| &nbsp;&nbsp;[otmena-zakaza/pokupatel/](otmena-zakaza/pokupatel/INDEX.md) | Покупатель | 2 |

## Возможности

| Возможность | Кейсов |
|---|---|
| order-cancellation | 3 |
| order-checkout | 3 |
| order-payment | 0 |
| order-shipping | 2 |
| order-viewing | 0 |

## Формат кейса

Файл `TC-NNNN-<slug>.md`: front-matter (`id`, `title`, `priority`, `status`, `type`, `tags`, `requirements`, `capabilities`, `code`, `autotests`, `source`, `custom`) и разделы «Цель», «Предусловия», «Шаги», «Постусловия», «Параметры». Шаг — `1. действие`, под ним `   - **Ожидается:** …` и `   - **Данные:** …`. Общий шаг — файл `_shared/SS-NNN-*.md`, в кейсе на него ссылка.

## Как менять

1. Поведение изменилось — поправь шаги и ожидаемое в кейсах, найденных выше. Новый сценарий — новый кейс со следующим номером (`new.py`), id не меняй и не переиспользуй.
2. Кейс устарел — `status: deprecated`, файл не удаляй, пока человек не решит.
3. `[скрыто: S-NN]` — секрет из TMS: не вписывай настоящее значение, бери его из окружения (см. `QUESTIONS.md`).
4. После правок: `route.py index .` и `check.py .` (скилл qa-scan). `_index/`, `INDEX.md` и этот файл руками не правь.
