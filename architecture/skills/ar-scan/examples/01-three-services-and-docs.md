# Пример 1: несколько репозиториев и документация — решения плохо и хорошо

Запрос: «Репозитории booking (Go), billing (Java) и reminders (Python) и выгрузка Confluence с C4-схемой. Как они связаны и где документация устарела?»

## Ход работы

```
python3 <skill>/scripts/landscape.py init architecture
python3 <skill>/scripts/landscape.py add-repo architecture repos/booking
python3 <skill>/scripts/landscape.py add-repo architecture repos/billing
python3 <skill>/scripts/landscape.py add-repo architecture repos/reminders
python3 <skill>/scripts/landscape.py add-docs architecture confluence-export
python3 <skill>/scripts/landscape.py build architecture
```

`build`: 3 системы (по одной на репозиторий), связи из кода — HTTP booking → billing (`/api/invoices`), событие `visit.booked`
(booking → reminders); в сверке — узлы C4 «Клиника» и «SMS-шлюз» без системы, хост `api.smsc.ru` в reminders, общая база
`BOOKING_DB_URL` у booking и reminders, событие `visit.cancelled` у reminders без издателя.

Шаг 4–5: системы — все три настоящие. Из документов:

```
python3 <skill>/scripts/landscape.py system architecture sms-gateway --external --title "SMS-шлюз" --alias api.smsc.ru
python3 <skill>/scripts/landscape.py system architecture clinic-portal --title "Клиника" --purpose "Кабинет клиники: расписание врачей" --source confluence-export/portal.html:12
python3 <skill>/scripts/landscape.py system architecture billing --purpose "Счета за приёмы" --source confluence-export/billing.html:5 --owner "Команда финансов" 
python3 <skill>/scripts/landscape.py claim architecture --from reminders --to booking --kind data --what "расписание приёмов на завтра" --source confluence-export/reminders.html:20
python3 <skill>/scripts/landscape.py build architecture
```

## Решения в RECONCILE.md

**Плохо:**

```
- [x] R-02 `visit.cancelled` слушает reminders
  - **Решение:** ок: так задумано
- [x] R-03 BOOKING_DB_URL: booking, reminders
  - **Решение:** ок: reminders только читает
- [x] R-04 reminders → booking: «расписание приёмов на завтра»
  - **Решение:** не связь: в коде нет
```

«Так задумано» — ничего не проверено. «Только читает» — догадка, и чтение чужих таблиц ломается при изменении схемы booking.
«Не связь: в коде нет» — связь есть, только через базу, а не по API: документ и код описывают одно и то же разными путями.

**Хорошо:**

```
- [x] R-02 `visit.cancelled` слушает reminders
  - Подписка: reminders:reminders/consumer.py:31 (kafka)
  - **Решение:** вопрос Q-003
- [x] R-03 BOOKING_DB_URL: booking, reminders
  - **Решение:** вопрос Q-001
- [x] R-04 reminders → booking: «расписание приёмов на завтра»
  - **Решение:** ок: reminders берёт расписание не по API, а из базы booking (reminders/jobs/tomorrow.py:14, BOOKING_DB_URL) — связь та же, путь другой; риск — в Q-001
```

Q-003: «Кто должен публиковать `visit.cancelled`: в booking отмена (`POST /api/visits/{id}/cancel`) события не шлёт — напоминание об отменённом приёме уйдёт?»
— блокирует, затрагивает booking и reminders: в коде видно, что подписка мёртвая, а последствие — письмо пациенту об отменённом приёме.

## Почему так

- Каждое «ок» называет файл и строку: следующий читатель проверит за минуту.
- Мёртвая подписка — не «ок»: её последствие для пользователя сформулировано в вопросе.
- Связь из документа сверена по смыслу, а не по форме: «через базу» — тоже связь, и она рискованнее API.
- Владелец — только там, где документ его называет; у reminders владельца в выгрузке нет — вопрос, а не «команда напоминаний».
