---
type: llm
focus: contracts
weight: 1
---

the agent ran scripts/contracts.py scan, so system-context/contracts.md lists every HTTP route with the response codes found in the handler (for example 422 and 201 on order creation, 409 on cancel and ship) and the shipping queue with its publisher and consumer, and system-context/data.md lists the Prisma entities with their fields; no "<!-- заполнить" placeholders are left in either file, and the agent's own text in data.md says what is not protected against concurrent changes or not covered by a transaction (for example order creation and the Stripe payment intent are not one transaction, there is no row version); requirements in the specs name their entries by method and path, such as POST /api/orders/{id}/cancel
