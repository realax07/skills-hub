# notifications (`notifications`)

Карточка системы в ландшафте: кто от неё зависит и от кого зависит она. Блок `sa:auto` пересобирает `landscape.py build`; заметки пиши под ним.

<!-- sa:auto id="card" -->
- Репозиторий: `notifications` (../repos/notifications)
- Слой sa-scan: нет
- Назначение: Письма покупателям по событиям заказов (docs/architecture.md:9)
- Владелец: Команда «Коммуникации» (docs/architecture.md:9)

**Кто зависит от неё** (меняешь её вход или событие — эти сломаются первыми, выкатываются отдельно):
- никто в ландшафте

**От кого зависит она:**
- `orders` слушает его событие: orders.created — orders:src/routes/orders.ts:13 → notifications:notifications/worker.py:9
- `sendgrid` вызывает: адрес api.sendgrid.com — notifications:notifications/mailer.py:8

**Общая инфраструктура и данные:**
- orders db (ORDERS_DB_URL) — также orders

**О системе в документах:**
- ../docs/architecture.md — Архитектура магазина

**Расхождения и вопросы:**
- payments → notifications: «payments.completed» (RECONCILE.md)
- notifications → crm: «контакты покупателя» (RECONCILE.md)
- orders db (ORDERS_DB_URL): notifications, orders (RECONCILE.md)
- Q-001 [блокирует] Можно ли notifications читать базу заказов напрямую, если ADR-0001 это запрещает?
- Q-002 [уточняет] Должны ли уведомления писать покупателю об успешной оплате?
<!-- sa:auto-end -->

## Заметки

- **Как с ней работать:** <!-- заполнить: для изменений в соседних системах — что важно знать (SLA, окна выкатки, кто согласует контракт), со ссылкой на источник; не знаешь — «не известно» и вопрос -->
