import os

import httpx

STRIPE = "https://api.stripe.com/v1"


def create_intent(amount: float, order_id: str) -> dict:
    r = httpx.post(
        f"{STRIPE}/payment_intents",
        auth=(os.environ["STRIPE_API_KEY"], ""),
        data={"amount": int(amount * 100), "currency": "rub", "metadata[order_id]": order_id, "confirm": "true"},
        timeout=10,
    )
    r.raise_for_status()
    return r.json()
