# Пример 3: раздутый SKILL.md → полная структура

## Запрос

> вот мой скилл pdf-extract, он на 700 строк, агент путается. приведи в порядок по нормальной структуре

Было: один `pdf-extract/SKILL.md` — 700 строк. Внутри: 3 больших блока Python-кода (извлечь текст, таблицы, картинки),
которые агент каждый раз перепечатывает; 40 правил вперемешку; «используй pypdf» без установки; ни примеров, ни тестов.

## Ход работы

1. `python3 scripts/validate_skill.py pdf-extract` → тело > 500 строк, нет examples/, нет evals/, нет «когда» в description.
2. Разметить содержимое по уровням загрузки:
   - **процесс** (что делать по шагам) → остаётся в теле;
   - **код** → три точки входа в `scripts/`: `extract_text.py`, `extract_tables.py`, `extract_images.py`, общее — в `scripts/lib/pdf.py`; каждому `--help`, `--json`, коды выхода;
   - **правила** (OCR для сканов, пароли, многоколоночная вёрстка, кодировки) → `references/rules.md` с таблицей крайних случаев;
   - **специфика таблиц** (60 строк о границах ячеек) → `references/tables.md`, в теле — «открой, если в PDF таблицы».
3. **Зависимости.** pypdf и pdfplumber → `compatibility` во frontmatter + `scripts/setup.py` (шаблон `assets/extras/setup.py.tmpl`),
   пиннованные версии, установка в `~/.cache/agent-skills/pdf-extract`. Первый шаг процесса — `setup.py --check`.
4. **description** переписать по [references/description.md](../references/description.md).
5. **Примеры:** `examples/01-invoice.md` (счёт → JSON с позициями), `examples/02-scanned.md` (плохо: пустой текст без предупреждения / хорошо: определить скан и предложить OCR).
6. **Тесты:** `new_eval.py` ×2 с `--files` (текстовый PDF с таблицей; скан).
7. `validate_skill.py pdf-extract --strict --run-scripts` → 0 ошибок. Прогнать один запрос старой и новой версией: новая не перепечатывает код и не забывает про сканы.

## Плохо

Механически разрезать файл: `references/part1.md`, `part2.md`, `part3.md`, а в теле — «подробности в references/».

Почему плохо: агент не знает, какой файл когда открывать, и либо читает всё (тот же раздутый контекст), либо ничего.
Код по-прежнему в markdown — его всё так же перепечатывают.

## Хорошо

```
pdf-extract/
├── SKILL.md                 ~120 строк: процесс, 7 ключевых правил, таблица ресурсов с «когда открывать»
├── references/rules.md      правила, крайние случаи, типичные ошибки
├── references/tables.md     извлечение таблиц — «открой, если в PDF таблицы»
├── examples/01-invoice.md
├── examples/02-scanned.md
├── scripts/setup.py         зависимости, --check
├── scripts/extract_text.py
├── scripts/extract_tables.py
├── scripts/extract_images.py
├── scripts/lib/pdf.py
└── evals/{text-pdf-with-table, scanned-pdf}/
```

Почему хорошо: каждый кусок лежит на своём уровне загрузки, у каждого ресурса — условие открытия,
повторяющийся код стал запускаемыми скриптами, зависимости ставятся явно, есть проверка, что стало лучше.
