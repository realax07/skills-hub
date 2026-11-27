# Сверка кода и документов

Каждый пункт — то, что не сходится между источниками или не нашло пары: связь есть в документе, но не в коде (и наоборот),
событие без подписчика, поля события у издателя и подписчика разные, общая база данных, узел схемы без системы, адрес вне ландшафта.

Решение — одно из:
- `вопрос Q-012` — спросить человека (вопрос — `landscape.py q`);
- `ок: <почему>` — расхождение объяснимо, одной конкретной фразой: что проверил и где;
- `не связь: <почему>` — это не связь между системами (ссылка в комментарии, пример в документе, тестовый адрес).

Узел схемы — система под другим именем → `landscape.py system <id> --alias "<имя>"`; внешняя → `system <новый-id> --external --title "<имя>"`;
после `build` пункт исчезнет сам. Пересборка сохраняет решения по ключу пункта.

## Документ без кода

- [x] R-01 payments → notifications: «payments.completed» <!-- key: doc-only:payments→notifications -->
  - В документе: ../docs/architecture.md:21
  - В коде связи не найдено
  - **Решение:** вопрос Q-002
- [x] R-02 orders → crm: «новый покупатель» <!-- key: doc-only:orders→crm -->
  - В документе: ../docs/architecture.md:22
  - В коде `orders` обращения к `crm` не найдено (у `crm` нет репозитория — искал по алиасам и адресам; проверь клиент или SDK)
  - **Решение:** ок: в коде orders нет ни адреса, ни клиента CRM (repos/orders/src — только payments и Kafka); схема описывает план или устарела
- [x] R-03 notifications → crm: «контакты покупателя» <!-- key: doc-only:notifications→crm -->
  - В документе: docs/architecture.md:30
  - В коде `notifications` обращения к `crm` не найдено (у `crm` нет репозитория — искал по алиасам и адресам; проверь клиент или SDK)
  - **Решение:** ок: контакты notifications берёт не из CRM, а из базы заказов (repos/notifications/notifications/worker.py:12) — путь другой, риск в Q-001
- [x] R-04 событие `payments.refunded` (payments) <!-- key: doc-event:payments.refunded -->
  - В документе: ../docs/asyncapi/payments.yaml
  - В коде публикации и подписки нет: ещё не сделано, удалено или другое имя
  - **Решение:** ок: возвратов в коде payments нет (repos/payments/app/api/payments.py — только списание и чтение), событие описано заранее в docs/asyncapi/payments.yaml

## Общие базы данных

- [x] R-05 orders db (ORDERS_DB_URL): notifications, orders <!-- key: shared-db:orders db (ORDERS_DB_URL) -->
  - notifications: notifications:.env.example:2
  - orders: orders:.env.example:2
  - Две системы в одной базе: схема меняется только вместе, «чужие» таблицы читаются в обход контракта
  - **Решение:** вопрос Q-001
