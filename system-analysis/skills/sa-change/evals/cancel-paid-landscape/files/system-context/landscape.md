# Ландшафт: системы этого репозитория

Копия карточек из слоя архитектуры `../architecture` (собран 2026-11-27 12:00). Не правь здесь — пересобирается `landscape.py link`.

## orders (`orders`)

- Назначение: заказы: оформление, оплата через Stripe, отмена, отгрузка (docs/prd.md:1)
- Владелец: Команда «Заказы» (docs/prd.md:3)

**Кто зависит от неё** (меняешь её вход или событие — эти сломаются первыми, выкатываются отдельно):
- `support-desk` вызывает её: HTTP /api/orders — support-desk:src/api/orders.ts:14
- `mobile-app` вызывает её: HTTP /api/orders — mobile-app:lib/api/orders_api.dart:22, mobile-app:lib/screens/order_screen.dart:57

**От кого зависит она:**
- `stripe` вызывает: адрес api.stripe.com — orders:src/integrations/stripe.ts:9

**Общая инфраструктура и данные:**
- orders db (DATABASE_URL) — также warehouse-sync (раз в минуту выбирает заказы со статусом PAID и передаёт складу на сборку)
