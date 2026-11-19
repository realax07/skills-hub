---
type: llm
focus: trace
weight: 1
---

plan.json assigns the FastAPI routes POST /documents, GET /documents/{doc_id} and POST /admin/documents/{doc_id}/retry, the celery tasks and the reconvert CLI to capabilities, and excludes /healthz with a reason
