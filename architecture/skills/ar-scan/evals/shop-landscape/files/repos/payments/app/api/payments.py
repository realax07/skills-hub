from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.bus import producer
from app.stripe_client import create_intent

router = APIRouter()
PAYMENTS: dict = {}


class PaymentRequest(BaseModel):
    orderId: str
    amount: float


@router.post("", status_code=201)
def create_payment(req: PaymentRequest):
    # повторный POST с тем же orderId создаёт второй платёж
    intent = create_intent(req.amount, req.orderId)
    status = "succeeded" if intent.get("status") == "succeeded" else "failed"
    PAYMENTS[intent["id"]] = {"id": intent["id"], "orderId": req.orderId, "status": status}
    producer.send("payments.completed", {"orderId": req.orderId, "paymentId": intent["id"], "status": status})
    return PAYMENTS[intent["id"]]


@router.get("/{payment_id}")
def get_payment(payment_id: str):
    if payment_id not in PAYMENTS:
        raise HTTPException(status_code=404)
    return PAYMENTS[payment_id]
