---
id: TC-0002
title: "Пустой заказ не оформляется"
priority: medium
status: ready
type: automated
tags: []
requirements: [SHOP-12]
capabilities: [order-checkout]
code: []
autotests: [test/orders.test.ts:6]
source:
  tms: testrail
  id: C102
  key: C102
  section: "Оформление заказа"
  hash: 57338a03c5b5
custom:
  type: Functional
  automation_type: Automated
---

# TC-0002 Пустой заказ не оформляется

## Шаги

1. Отправить POST /api/orders с пустым списком товаров
   - **Ожидается:** Ответ 422
