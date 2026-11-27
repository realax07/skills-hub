# Контракты между системами

Только то, у чего есть потребители в **других** системах: события, HTTP-входы, gRPC-сервисы. Меняешь такой контракт — потребитель
в другом репозитории сломается первым, а выкатывается он отдельно.

Поиск: `grep -n -A20 "### \`event:<Имя>" contracts.md` или `landscape.py show <arch> --event <часть имени>`.
Блоки `sa:auto` пересобирает `landscape.py build`.

## События между системами

### `event:payments.completed`
<!-- sa:auto id="event:payments.completed" -->
- Владелец (публикует): `payments`
  - payments:app/api/payments.py:22
- Подписаны: `orders`
  - orders:src/consumers/payments.ts:8 (kafka)
<!-- sa:auto-end -->

### `event:orders.created`
<!-- sa:auto id="event:orders.created" -->
- Владелец (публикует): `orders`
  - orders:src/routes/orders.ts:13
- Подписаны: `notifications`
  - notifications:notifications/worker.py:9 (kafka)
<!-- sa:auto-end -->

## HTTP-входы с потребителями в других системах

### `http:payments /api/payments`
<!-- sa:auto id="http:payments:api/payments" -->
- Владелец: `payments`
- Входы: `POST /api/payments`, `GET /api/payments/{payment_id}`
- Потребитель `orders`:
  - orders:src/clients/payments.ts:5 `const r = await fetch(${PAYMENTS_URL}/api/payments, {`
<!-- sa:auto-end -->

## gRPC-сервисы с потребителями в других системах

Не найдено.
