# Контракты

То, по чему доработка не должна сломаться: что принимают входы и что отдают, какие события ходят между частями системы
и кто ещё в репозитории опирается на эти контракты. Поведение — в `openspec/specs/`, здесь — форма данных и связи.

Блоки `sa:auto` собирает `contracts.py scan` (эвристики — сверяй с кодом), пересканирование их переписывает.
Свои уточнения пиши **вне** блоков, строкой под блоком («Заметки: …»). Места с комментарием «заполнить» заполняет агент.

## HTTP

### `http:POST /api/orders`
<!-- sa:auto id="http:POST /api/orders" -->
- Возможность: order-checkout
- Вход: src/routes/orders.ts:13
- Обработчик: встроенный (лямбда) (src/routes/orders.ts:13)
- Сигнатура: `ordersRouter.post("/", async (req, res) =>`
- Ответы из кода обработчика (исключения из глубины вызовов сюда не попадают):
  - 422 тело `{ error: "items" }`
  - 201 тело `{ id: order.id, clientSecret: intent.client_secret }`
<!-- sa:auto-end -->

### `http:GET /api/orders`
<!-- sa:auto id="http:GET /api/orders" -->
- Возможность: order-viewing
- Вход: src/routes/orders.ts:26
- Обработчик: встроенный (лямбда) (src/routes/orders.ts:26)
- Сигнатура: `ordersRouter.get("/", async (req, res) =>`
- Ответы из кода обработчика: явных нет — по умолчанию 200; ошибки — исключения и общий обработчик
<!-- sa:auto-end -->

### `http:GET /api/orders/{id}`
<!-- sa:auto id="http:GET /api/orders/{id}" -->
- Возможность: order-viewing
- Вход: src/routes/orders.ts:31
- Обработчик: встроенный (лямбда) (src/routes/orders.ts:31)
- Сигнатура: `ordersRouter.get("/:id", async (req, res) =>`
- Ответы из кода обработчика (исключения из глубины вызовов сюда не попадают):
  - 404
<!-- sa:auto-end -->

### `http:POST /api/orders/{id}/cancel`
<!-- sa:auto id="http:POST /api/orders/{id}/cancel" -->
- Возможность: order-cancellation
- Вход: src/routes/orders.ts:38
- Обработчик: встроенный (лямбда) (src/routes/orders.ts:38)
- Сигнатура: `ordersRouter.post("/:id/cancel", async (req, res) =>`
- Ответы из кода обработчика (исключения из глубины вызовов сюда не попадают):
  - 404
  - 409 тело `{ error: "state" }`
<!-- sa:auto-end -->

### `http:POST /api/orders/{id}/ship`
<!-- sa:auto id="http:POST /api/orders/{id}/ship" -->
- Возможность: order-shipping
- Вход: src/routes/orders.ts:53
- Обработчик: встроенный (лямбда) (src/routes/orders.ts:53)
- Сигнатура: `ordersRouter.post("/:id/ship", requireRole("MANAGER"), async (req, res) =>`
- Ответы из кода обработчика (исключения из глубины вызовов сюда не попадают):
  - 409 тело `{ error: "state" }`
  - 202 тело `{ queued: true }`
<!-- sa:auto-end -->

### `http:POST /webhooks/stripe`
<!-- sa:auto id="http:POST /webhooks/stripe" -->
- Возможность: order-payment
- Вход: src/routes/webhooks.ts:8
- Обработчик: встроенный (лямбда) (src/routes/webhooks.ts:8)
- Сигнатура: `webhooksRouter.post("/stripe", async (req, res) =>`
- Заголовки: `stripe-signature`
- Ответы из кода обработчика (исключения из глубины вызовов сюда не попадают):
  - 400 «bad signature»
<!-- sa:auto-end -->

## Расписания

### `schedule:scheduler.ts [*/15 * * * *] (node-cron)`
<!-- sa:auto id="schedule:scheduler.ts [*/15 * * * *] (node-cron)" -->
- Возможность: order-cancellation
- Вход: src/jobs/scheduler.ts:6
<!-- sa:auto-end -->

## События между сервисами

### `ship`
<!-- sa:auto id="event:ship" -->
- Поля: тип не найден (событие по имени или теме) — смотри место публикации
- Публикует:
  - src/routes/orders.ts:56
- Подписаны:
  - src/jobs/queues.ts:8 (bullmq-queue)
- Возможности подписчиков: order-shipping
<!-- sa:auto-end -->

## Внутренние (доменные) события

Не найдено.

## Кто вызывает входы (в репозитории)

Не найдено.
