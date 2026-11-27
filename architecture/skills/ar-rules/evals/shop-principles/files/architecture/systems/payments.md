# payments (`payments`)

Карточка системы в ландшафте: кто от неё зависит и от кого зависит она. Блок `sa:auto` пересобирает `landscape.py build`; заметки пиши под ним.

<!-- sa:auto id="card" -->
- Репозиторий: `payments` (../repos/payments)
- Стек: FastAPI
- Слой sa-scan: нет
- Назначение: Списание денег за заказ через Stripe (docs/architecture.md:8)
- Владелец: Команда Billing (канал #billing) (docs/confluence/payments-service.html:5)

**Кто зависит от неё** (меняешь её вход или событие — эти сломаются первыми, выкатываются отдельно):
- `orders` вызывает её: HTTP /api/payments, адрес payments, адрес из настройки PAYMENTS_URL — orders:src/clients/payments.ts:5
- `orders` слушает её событие: payments.completed — payments:app/api/payments.py:22 → orders:src/consumers/payments.ts:8

**От кого зависит она:**
- `stripe` вызывает: адрес api.stripe.com — payments:app/stripe_client.py:5

**Публикует события:**
- `payments.completed` → orders; поля: тип не найден — смотри место публикации

**О системе в документах:**
- ../docs/architecture.md — Архитектура магазина
- ../docs/confluence/payments-service.html — Payments Service

**Расхождения и вопросы:**
- payments → notifications: «payments.completed» (RECONCILE.md)
- событие `payments.refunded` (payments) (RECONCILE.md)
- Q-002 [уточняет] Должны ли уведомления писать покупателю об успешной оплате?
<!-- sa:auto-end -->

## Заметки

- **Как с ней работать:** <!-- заполнить: для изменений в соседних системах — что важно знать (SLA, окна выкатки, кто согласует контракт), со ссылкой на источник; не знаешь — «не известно» и вопрос -->
