<!-- собирает qa-scan (route.py index) — руками не правь -->
# Кейсы и автотесты

`ext:<id>` — автотест, привязанный в TMS (externalId); `путь:строка` — найден в коде (`map.py autotests`).

- [TC-0001](../oformlenie-zakaza/TC-0001-oformlenie-zakaza-iz-korziny.md) Оформление заказа из корзины · highest · ready · automated · cap: order-checkout · req: SHOP-12, SHOP-15 → `test/orders.test.ts:4`
- [TC-0002](../oformlenie-zakaza/TC-0002-pustoy-zakaz-ne-oformlyaetsya.md) Пустой заказ не оформляется · medium · ready · automated · cap: order-checkout · req: SHOP-12 → `test/orders.test.ts:6`
- [TC-0004](../otmena-zakaza/pokupatel/TC-0004-pokupatel-ne-mozhet-otmenit-oplachennyy.md) Покупатель не может отменить оплаченный заказ · high · ready · automated · cap: order-cancellation · req: SHOP-31 → `test/orders.test.ts:8`
