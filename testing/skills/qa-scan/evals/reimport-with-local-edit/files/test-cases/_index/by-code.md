<!-- собирает qa-scan (route.py index) — руками не правь -->
# Кейсы по коду

Файл или папка кода → возможность → кейсы. Ищи: `grep -n "src/orders" test-cases/_index/by-code.md`.

## По трассировке sa-scan (`system-context/trace.md`)

- `src/auth.ts` → order-checkout (3), order-shipping (2)
- `src/integrations/mailer.ts` → order-payment (0)
- `src/integrations/stripe.ts` → order-cancellation (3), order-checkout (3)
- `src/integrations/warehouse.ts` → order-shipping (2)
- `src/jobs/queues.ts` → order-shipping (2)
- `src/jobs/scheduler.ts` → order-cancellation (3)
- `src/routes/orders.ts` → order-cancellation (3), order-checkout (3), order-shipping (2), order-viewing (0)
- `src/routes/webhooks.ts` → order-payment (0)
- `src/server.ts` → order-payment (0)

## Указаны в кейсах (`code:`, `autotests:`)

- `test/orders.test.ts (автотест)` → TC-0001, TC-0002, TC-0004

