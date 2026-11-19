# Формат OpenSpec

Сверено с OpenSpec 2.1.0 (Fission-AI/OpenSpec, ноябрь 2026) и с русскоязычными спеками, которые проходят `openspec validate --strict`.
Если CLI ругается на то, что здесь разрешено, — верь CLI и сверься с openspec.dev/docs: формат мог измениться.

## Структура

```
openspec/
  config.yaml                         настройки проекта (вместо устаревшего project.md)
  specs/<capability>/spec.md          основные спеки: как система работает сейчас
  changes/<change-id>/                предложенное изменение
    proposal.md  tasks.md  design.md  (design.md — по желанию)
    specs/<capability>/spec.md        дельта: что меняется в спеке
  changes/archive/YYYY-MM-DD-<id>/    принятые изменения (создаёт openspec archive)
```

`<capability>` и `<change-id>` — kebab-case латиницей.

## Основная спека

```markdown
# Оформление заказа

## Purpose
Покупатель создаёт заказ из набора позиций и получает данные для оплаты.

## Requirements

### Requirement: Проверка состава заказа
Система SHALL принимать заказ, в котором от 1 до 50 позиций.

#### Scenario: Пустой заказ
- **WHEN** покупатель отправляет заказ без позиций
- **THEN** заказ не создаётся и возвращается ошибка 422
```

Что проверяет `openspec validate --strict` и `check.py`:
- первая строка — `# <Название>`; разделы `## Purpose` (не пустой) и `## Requirements`;
- требование — ровно `### Requirement: <имя>`, имена уникальны в спеке;
- в тексте требования (до первого сценария) есть **SHALL** или **MUST** — по-английски, заглавными, даже в русском тексте;
- текст требования не длиннее 500 символов;
- у каждого требования есть `#### Scenario: <имя>` — ровно четыре решётки (три или жирный текст парсер не видит);
- в сценарии есть шаг WHEN (или GIVEN) и шаг THEN: строки списка `- **WHEN** …`, `- **THEN** …`, `- **AND** …`, `- **GIVEN** …`;
- в основной спеке нет разделов дельты (`## ADDED Requirements` и т.п.).

Язык: заголовки разделов (`Purpose`, `Requirements`, `Requirement:`, `Scenario:`) и ключевые слова — по-английски, остальное — на языке проекта.

## Дельта изменения

`openspec/changes/<id>/specs/<capability>/spec.md`:

```markdown
# Delta for Оформление заказа

## MODIFIED Requirements

### Requirement: Проверка состава заказа
Система SHALL принимать заказ, в котором от 1 до 30 позиций. (Previously: до 50)

#### Scenario: Больше 30 позиций
- **WHEN** покупатель отправляет заказ из 31 позиции
- **THEN** заказ не создаётся и возвращается ошибка 422
```

- `## ADDED Requirements` — новые требования; при архивации добавляются в основную спеку.
- `## MODIFIED Requirements` — **полная** новая версия требования, имя — дословно как в основной спеке (по нему идёт замена).
  Все сценарии, которые должны остаться, — тоже в новой версии.
- `## REMOVED Requirements` — удаляемые (имя дословно).
- `## Purpose` в дельте — только для новой возможности.

`proposal.md`: `## Why` (почему, со ссылкой на вопрос Q-…), `## What Changes` (список), `## Impact` (возможности, код).
`tasks.md`: нумерованный чек-лист `- [ ] 1.1 …`. Заготовки — `assets/change/`.

## config.yaml

```yaml
schema: spec-driven
context: |
  2–4 строки о продукте + указатель на system-context/GUIDE.md
rules:
  proposal: [...]
  specs: [...]
  tasks: [...]
```

- `context` подмешивается во все артефакты — держи коротким. Документация проекта сюда не идёт (так советует сам OpenSpec): она в `system-context/`.
- `rules.<артефакт>` — правила только для этого артефакта.
- `openspec init --language ru` пишет в `context` строку о языке — если `config.yaml` уже создан CLI, не затирай её.

## CLI (необязателен)

Нужен Node.js 22.20+: `npm install -g @fission-ai/openspec@latest` (или `brew install openspec`). Ставит пользователь — без спроса не ставь.

```bash
openspec validate --specs --strict --no-interactive     # основные спеки
openspec validate <change-id> --strict                   # изменение
openspec list --specs                                    # что есть
openspec show <capability> --type spec
```

`check.py` сам запускает первую команду, если `openspec` есть в PATH. Нет CLI — `check.py` проверяет те же правила своим разбором.

## Как дальше работают агенты (стадия после sa-scan)

1. Задача → предложение изменения `openspec/changes/<id>/` (proposal, дельта, tasks).
2. Реализация по `tasks.md`, обновление `system-context/trace.md`.
3. `openspec archive <id>` — дельта вливается в основные спеки.

Основные спеки руками не правят — только через изменения: так спека не расходится с историей решений.
