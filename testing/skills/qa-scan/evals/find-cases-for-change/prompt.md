---
tags: [skills-hub, qa-scan]
max_turns: 60
timeout_seconds: 1200
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

меняем правило: покупатель теперь может отменить оплаченный заказ сам, деньги возвращаются автоматически. какие тест-кейсы надо поправить и каких не хватает? пока ничего не меняй, просто скажи

Input files: AGENTS.md, README.md, openspec/changes/.gitkeep, openspec/config.yaml, openspec/specs/.gitkeep, openspec/specs/order-cancellation/spec.md, openspec/specs/order-checkout/spec.md, openspec/specs/order-payment/spec.md, openspec/specs/order-shipping/spec.md, openspec/specs/order-viewing/spec.md, package.json, src/auth.ts, src/integrations/mailer.ts, src/integrations/stripe.ts, src/integrations/warehouse.ts, src/jobs/queues.ts, src/jobs/scheduler.ts, src/models/db.ts, src/routes/orders.ts, src/routes/webhooks.ts, src/server.ts, system-context/trace.md, test/orders.test.ts, test-cases/ (перенесённые кейсы с индексами)
