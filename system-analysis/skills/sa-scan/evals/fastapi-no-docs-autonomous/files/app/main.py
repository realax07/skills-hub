from fastapi import FastAPI
from app.api import documents, admin

app = FastAPI(title="docs-converter")
app.include_router(documents.router)
app.include_router(admin.router)


@app.get("/healthz")
def health():
    return {"ok": True}
