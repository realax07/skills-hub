# Опись репозитория `t1`

Собрано `inventory.py scan` эвристиками: пропуски возможны, лишнее тоже. Полные данные — `inventory.json`,
выборка — `inventory.py show <repo> --kind <вид> --grep <текст>`.

## Сводка

- файлов кода: 11; входов: http 7, schedule 1, consumer 1
- исходящих вызовов: 3; внешних хостов: 1; переменных окружения: 10
- сущностей: 3; перечислений статусов и ролей: 2; файлов тестов: 1; документов: 3; TODO/FIXME: 2

## Стек и пакеты

| Папка | Имя | Фреймворки | Внешние сервисы по зависимостям |
|---|---|---|---|
| `.` | orders-service | Express | базы данных: @prisma/client, prisma; очереди задач: bullmq; почта: nodemailer; платежи: stripe |

## Точки входа

### HTTP (7)

| id | где | как найдено | метки |
|---|---|---|---|
| `http:GET /health` | `src/server.ts:10` | Express-подобный роутер | служебное |
| `http:POST /api/orders` | `src/routes/orders.ts:13` | Express-подобный роутер |  |
| `http:GET /api/orders` | `src/routes/orders.ts:26` | Express-подобный роутер |  |
| `http:GET /api/orders/{id}` | `src/routes/orders.ts:31` | Express-подобный роутер |  |
| `http:POST /api/orders/{id}/cancel` | `src/routes/orders.ts:38` | Express-подобный роутер |  |
| `http:POST /api/orders/{id}/ship` | `src/routes/orders.ts:53` | Express-подобный роутер |  |
| `http:POST /webhooks/stripe` | `src/routes/webhooks.ts:8` | Express-подобный роутер | webhook |

### Очереди, события, фоновые задачи (1)

| id | где | как найдено | метки |
|---|---|---|---|
| `consumer:bullmq-queue ship` | `src/jobs/queues.ts:8` | bullmq-queue |  |

### Расписания (1)

| id | где | как найдено | метки |
|---|---|---|---|
| `schedule:scheduler.ts [*/15 * * * *] (node-cron)` | `src/jobs/scheduler.ts:6` | node-cron |  |

## Внешние хосты

| Хост | Упоминаний | Где |
|---|---|---|
| `api.warehouse-partner.ru` | 1 | `src/integrations/warehouse.ts:1` |

## SDK внешних сервисов в коде

| Категория | Пакет | Где импортируется |
|---|---|---|
| базы данных | `@prisma/client` | `src/models/db.ts:1` |
| очереди задач | `bullmq` | `src/jobs/queues.ts:1` |
| платежи | `stripe` | `src/integrations/stripe.ts:1` |
| почта | `nodemailer` | `src/integrations/mailer.ts:1` |

## Исходящие вызовы (3)

Строки с HTTP-клиентами и SDK. Полный список — `show --section outbound`.

- `src/integrations/mailer.ts` — 1: строки 4; SMTP_HOST
- `src/integrations/warehouse.ts` — 1: строки 4
- `src/models/db.ts` — 1: строки 2

## Переменные окружения

Только имена — значения скилл не читает.

| Имя | Метки | Где |
|---|---|---|
| `DATABASE_URL` | адрес | `.env.example:1` |
| `FEATURE_PARTIAL_REFUNDS` | флаг | `.env.example:7` |
| `JWT_SECRET` | секрет | `.env.example:6`, `src/auth.ts:7` |
| `PORT` |  | `src/server.ts:13` |
| `REDIS_URL` | адрес | `.env.example:2`, `src/jobs/queues.ts:5` |
| `SMTP_HOST` | адрес | `.env.example:5`, `src/integrations/mailer.ts:4` |
| `STRIPE_SECRET_KEY` | секрет | `.env.example:3`, `src/integrations/stripe.ts:3` |
| `STRIPE_WEBHOOK_SECRET` | секрет | `.env.example:4`, `src/routes/webhooks.ts:11` |
| `WAREHOUSE_API_URL` | адрес | `.env.example:8`, `src/integrations/warehouse.ts:1` |
| `WAREHOUSE_TOKEN` | секрет | `src/integrations/warehouse.ts:6` |

## Данные

| Сущность | Как найдено | Где |
|---|---|---|
| `User` | Prisma | `prisma/schema.prisma:3` |
| `Order` | Prisma | `prisma/schema.prisma:10` |
| `OrderItem` | Prisma | `prisma/schema.prisma:21` |

Статусы, роли, типы:

- `OrderStatus` (`prisma/schema.prisma:30`): NEW, PAID, SHIPPED, CANCELLED, REFUNDED
- `Role` (`prisma/schema.prisma:38`): CUSTOMER, MANAGER, ADMIN

## Проверки прав (6)

- `src/auth.ts`: строки 14, 17
- `src/routes/orders.ts`: строки 27, 33, 41, 53

## Тесты (1 файлов)

- `test/orders.test.ts` (unit/integration, 4): orders; creates an order and returns client secret; rejects empty order with 422; customer cannot cancel paid order

## Документация

- `AGENTS.md` —  (15 строк)
- `README.md` — orders-service (8 строк)
- `docs/prd.md` — PRD: Сервис заказов (v1) (17 строк)

## TODO / FIXME (2)

Подсказки о известных проблемах и недоделках — проверь, не попадают ли в спеку как «так задумано».

- `src/integrations/stripe.ts:10` FIXME: частичный возврат за флагом FEATURE_PARTIAL_REFUNDS ещё не сделан
- `src/routes/orders.ts:17` TODO: брать цены из каталога, а не из запроса клиента
