# orders (`orders`)

Карточка системы в ландшафте: кто от неё зависит и от кого зависит она. Блок `sa:auto` пересобирает `landscape.py build`; заметки пиши под ним.

<!-- sa:auto id="card" -->
- Репозиторий: `orders` (../repos/orders)
- Стек: Express
- Слой sa-scan: нет
- Назначение: Заказы: оформление, статусы, отмена (docs/architecture.md:7)
- Владелец: Команда «Заказы» (docs/architecture.md:7)

**Кто зависит от неё** (меняешь её вход или событие — эти сломаются первыми, выкатываются отдельно):
- `notifications` слушает её событие: orders.created — orders:src/routes/orders.ts:13 → notifications:notifications/worker.py:9

**От кого зависит она:**
- `payments` вызывает: HTTP /api/payments, адрес payments, адрес из настройки PAYMENTS_URL — orders:src/clients/payments.ts:5
- `payments` слушает его событие: payments.completed — payments:app/api/payments.py:22 → orders:src/consumers/payments.ts:8

**Публикует события:**
- `orders.created` → notifications; поля: тип не найден — смотри место публикации

**Общая инфраструктура и данные:**
- orders db (ORDERS_DB_URL) — также notifications

**О системе в документах:**
- ../docs/architecture.md — Архитектура магазина

**Расхождения и вопросы:**
- orders → crm: «новый покупатель» (RECONCILE.md)
- orders db (ORDERS_DB_URL): notifications, orders (RECONCILE.md)
- Q-001 [блокирует] Можно ли notifications читать базу заказов напрямую, если ADR-0001 это запрещает?
<!-- sa:auto-end -->

## Заметки

- **Как с ней работать:** <!-- заполнить: для изменений в соседних системах — что важно знать (SLA, окна выкатки, кто согласует контракт), со ссылкой на источник; не знаешь — «не известно» и вопрос -->
