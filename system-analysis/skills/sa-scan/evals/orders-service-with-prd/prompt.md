---
tags: [skills-hub, sa-scan]
max_turns: 80
timeout_seconds: 1800
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

переводим наш orders-service на агентную разработку, хотим openspec и SDD. сними мастер-спеку как сервис работает сейчас — по коду, плюс есть PRD в docs/prd.md (он мог устареть). все что непонятно из кода собери вопросами, я потом отвечу. главные покажи тут

Input files: .env.example, README.md, docs/prd.md, package.json, prisma/schema.prisma, src/auth.ts, src/integrations/mailer.ts, src/integrations/stripe.ts, src/integrations/warehouse.ts, src/jobs/queues.ts, src/jobs/scheduler.ts, src/models/db.ts, src/routes/orders.ts, src/routes/webhooks.ts, src/server.ts, test/orders.test.ts
