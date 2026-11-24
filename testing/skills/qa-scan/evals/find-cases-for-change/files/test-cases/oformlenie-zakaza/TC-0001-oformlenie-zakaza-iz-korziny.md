---
id: TC-0001
title: "Оформление заказа из корзины"
priority: highest
status: ready
type: automated
tags: []
requirements: [SHOP-12, SHOP-15]
capabilities: [order-checkout]
code: []
autotests: [test/orders.test.ts:4]
source:
  tms: testrail
  id: C101
  key: C101
  section: "Оформление заказа"
  hash: 7aad5890fcdb
custom:
  type: Functional
  estimate: 5m
  automation_type: Automated
---

# TC-0001 Оформление заказа из корзины

## Предусловия

Покупатель вошёл: логин buyer@example.com, пароль: [скрыто: S-01]

## Шаги

1. Добавить в корзину 2 товара
   - **Ожидается:** В корзине 2 позиции, сумма пересчитана
2. Нажать «Оформить заказ»
   - **Ожидается:** Открыта страница оплаты, заказ в статусе **NEW**
3. Ввести карту 4242 4242 4242 4242 и оплатить
   - **Ожидается:** Заказ PAID, на почту пришёл чек
