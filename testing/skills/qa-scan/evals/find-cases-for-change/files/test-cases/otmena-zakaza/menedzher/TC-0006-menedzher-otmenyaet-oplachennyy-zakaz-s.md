---
id: TC-0006
title: "Менеджер отменяет оплаченный заказ с возвратом"
priority: highest
status: ready
type: manual
tags: []
requirements: []
capabilities: [order-cancellation]
code: []
autotests: []
source:
  tms: testrail
  id: C120
  key: C120
  section: "Отмена заказа / Менеджер"
  hash: 71c0db8261df
custom:
  type: Functional
---

# TC-0006 Менеджер отменяет оплаченный заказ с возвратом

## Предусловия

Вход менеджером: **manager** / пароль [скрыто: S-03]

Звонить в поддержку: +7 916 123-45-67

## Шаги

1. Открыть заказ в статусе PAID в админке
   - **Ожидается:** Доступна кнопка «Отменить с возвратом»
2. Нажать «Отменить с возвратом»
   - **Ожидается:** Заказ REFUNDED, в Stripe создан возврат на полную сумму ![](index.php?/attachments/get/77)
