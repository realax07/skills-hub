---
id: TC-0008
title: "Передача заказа на склад"
priority: low
status: ready
type: manual
tags: []
requirements: []
capabilities: [order-shipping]
code: []
autotests: []
source:
  tms: testrail
  id: C131
  key: C131
  section: "Доставка"
  hash: 32e4df63c4ae
custom:
  type: Functional
---

# TC-0008 Передача заказа на склад

## Шаги

1. Менеджер запускает отгрузку оплаченного заказа
   - **Ожидается:** Заказ SHIPPING, склад получил задание
