---
id: TC-0004
title: "Покупатель не может отменить оплаченный заказ"
priority: high
status: ready
type: automated
tags: []
requirements: [SHOP-31]
capabilities: [order-cancellation]
code: []
autotests: [test/orders.test.ts:8]
source:
  tms: testrail
  id: C110
  key: C110
  section: "Отмена заказа / Покупатель"
  hash: e99408f9e760
custom:
  type: Functional
  automation_type: Automated
---

# TC-0004 Покупатель не может отменить оплаченный заказ

## Шаги

1. Открыть свой заказ в статусе PAID
   - **Ожидается:** Кнопки «Отменить» нет
2. Вызвать PUT /api/orders/{id}/cancel с токеном покупателя: token=[скрыто: S-02]
   - **Ожидается:** Ответ 409 и сообщение «Оплаченный заказ отменяет менеджер»
