from fastapi import FastAPI

from app.api import payments

app = FastAPI(title="Payments")
app.include_router(payments.router, prefix="/api/payments")
