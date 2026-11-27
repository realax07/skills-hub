---
type: llm
focus: trace
weight: 1
---

В ландшафте есть система delivery со связями из кода: подписка на payments.completed от payments и вызов orders (GET /api/orders/{id} по ORDERS_URL); у новых связей в landscape.md заполнено «Зачем и как» со ссылкой на repos/delivery/delivery/worker.py.
