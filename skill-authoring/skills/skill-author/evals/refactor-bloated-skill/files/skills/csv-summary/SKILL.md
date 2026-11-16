---
name: csv-summary
description: Делает сводку по CSV.
---

# CSV Summary

## Когда использовать

Используй этот скилл, когда пользователь присылает CSV или Excel-выгрузку (из CRM, 1С, банка, маркетплейса)
и просит посчитать итоги, сводку по категориям, итоги по месяцам, топ клиентов или менеджеров.
Также когда спрашивают «сколько продали», «какая выручка», «что по динамике».

## ВАЖНО

ВСЕГДА используй код ниже. НИКОГДА не пиши свой парсер. ОБЯЗАТЕЛЬНО проверяй кодировку.
ВСЕГДА пропускай пустые строки. НИКОГДА не округляй до сохранения.

## Шаг 1. Прочитать файл

Скопируй этот код в файл и запусти:

```python
import csv, sys, io

def read_rows(path):
    raw = open(path, "rb").read()
    for enc in ("utf-8-sig", "cp1251", "latin-1"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=";,\t")
    except csv.Error:
        dialect = csv.excel
    rows = list(csv.DictReader(io.StringIO(text), dialect=dialect))
    return [r for r in rows if any((v or "").strip() for v in r.values())]
```

## Шаг 2. Привести числа

Суммы бывают вида `1 234,50`, `1234.5`, `1,234.50`, `-` и пустые. Используй:

```python
import re

def to_number(value):
    if value is None:
        return None
    v = value.strip().replace(" ", "").replace(" ", "")
    if v in ("", "-", "—"):
        return None
    if re.match(r"^-?\d{1,3}(,\d{3})+(\.\d+)?$", v):
        v = v.replace(",", "")
    else:
        v = v.replace(",", ".")
    try:
        return float(v)
    except ValueError:
        return None
```

## Шаг 3. Привести даты

Даты бывают `31.12.2025`, `2025-12-31`, `12/31/2025`. Используй:

```python
from datetime import datetime

def to_date(value):
    for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%m/%d/%Y", "%d.%m.%y"):
        try:
            return datetime.strptime(value.strip(), fmt).date()
        except (ValueError, AttributeError):
            continue
    return None
```

## Шаг 4. Посчитать

```python
from collections import defaultdict

def summarize(rows, amount_col, date_col, group_col=None):
    by_month = defaultdict(float)
    by_group = defaultdict(float)
    skipped = 0
    for r in rows:
        amount = to_number(r.get(amount_col))
        d = to_date(r.get(date_col, ""))
        if amount is None or d is None:
            skipped += 1
            continue
        by_month[d.strftime("%Y-%m")] += amount
        if group_col:
            by_group[r.get(group_col, "").strip() or "(пусто)"] += amount
    return by_month, by_group, skipped
```

## Шаг 5. Вывести

Выведи таблицу Markdown: месяц | сумма. Потом топ-10 по группе. Потом сколько строк пропущено и почему.
Суммы с разделителем тысяч пробелом и двумя знаками.

## Правила

- Колонку суммы ищи по названиям: сумма, amount, выручка, revenue, итого.
- Колонку даты: дата, date, created, период.
- Если колонок несколько — спроси пользователя.
- Если файл Excel — сначала сохрани как CSV (нужен openpyxl).
- Отрицательные суммы — возвраты, считай отдельно.
- Валюты не смешивай: если есть колонка валюты — группируй по ней.
- Не показывай персональные данные клиентов (телефоны, email) в отчёте.
- Если пропущено больше 10% строк — предупреди.
