---
type: llm
focus: trace
weight: 1
---

По P-03 в tasks.md есть задача передать ключ идемпотентности в вызов возврата Stripe (src/integrations/stripe.ts, stripe.refunds.create), а повтор запроса отмены в design.md «Цепочка» разобран с опорой на этот ключ.
