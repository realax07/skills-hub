---
type: llm
focus: trace
weight: 1
---

В VIOLATIONS.md найдены вызов payments из orders без таймаута и таймауты 10 с у Stripe и SendGrid; у каждого нарушения заполнена «Проверка» со ссылкой на код и решение, а исключения (если есть) заведены rules.py except с источником, не «по здравому смыслу».
