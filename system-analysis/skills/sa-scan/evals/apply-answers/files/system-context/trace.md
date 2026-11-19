# Трассировка: требование → код

Для каждой возможности (`## <id>` — папка в `openspec/specs/`) — по строке на требование:
`- <имя требования, как в spec.md> → путь:строка, путь | тесты: путь, путь` (нет тестов — `| тесты: —`).
Нужна агенту, который меняет поведение: где трогать код и какие тесты обновить.

## order-checkout
- Оформление только для вошедших → src/auth.ts:4, src/routes/orders.ts:8 | тесты: —
- Проверка состава заказа → src/routes/orders.ts:10-15 | тесты: test/orders.test.ts
- Расчёт суммы заказа → src/routes/orders.ts:16 | тесты: —
- Создание платежа → src/routes/orders.ts:18-23, src/integrations/stripe.ts:5 | тесты: test/orders.test.ts

## order-payment
- Проверка подписи вебхука → src/routes/webhooks.ts:9-13, src/server.ts:7 | тесты: —
- Подтверждение оплаты → src/routes/webhooks.ts:14-19 | тесты: —
- Чек на почту → src/integrations/mailer.ts:6, src/routes/webhooks.ts:18 | тесты: —

## order-viewing
- Список заказов → src/routes/orders.ts:26-29 | тесты: —
- Карточка заказа → src/routes/orders.ts:31-35 | тесты: —

## order-cancellation
- Отмена заказа покупателем → src/routes/orders.ts:38-51 | тесты: test/orders.test.ts
- Отмена оплаченного заказа с возвратом → src/routes/orders.ts:43-47, src/integrations/stripe.ts:9 | тесты: —
- Автоотмена неоплаченного заказа → src/jobs/scheduler.ts:4-10 | тесты: —

## order-shipping
- Запуск отгрузки менеджером → src/routes/orders.ts:53-58, src/auth.ts:16 | тесты: —
- Передача заказа на склад → src/jobs/queues.ts:8-14, src/integrations/warehouse.ts:3 | тесты: —
