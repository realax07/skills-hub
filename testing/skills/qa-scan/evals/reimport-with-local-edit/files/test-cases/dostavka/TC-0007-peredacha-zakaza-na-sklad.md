---
id: TC-0007
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
  id: C130
  key: C130
  section: "Доставка"
  hash: ad17197c8a86
custom:
  type: Functional
  component: "Склад"
---

# TC-0007 Передача заказа на склад

## Шаги

1. Менеджер запускает отгрузку оплаченного заказа
   - **Ожидается:** Заказ SHIPPING, склад получил задание
