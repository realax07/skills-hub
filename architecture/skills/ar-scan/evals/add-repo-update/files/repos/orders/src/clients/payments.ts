const PAYMENTS_URL = process.env.PAYMENTS_URL ?? "http://payments:8000";

// Синхронное списание: заказ ждёт ответа платёжного сервиса
export async function charge(orderId: string, amount: number): Promise<{ id: string; status: string }> {
  const r = await fetch(`${PAYMENTS_URL}/api/payments`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ orderId, amount }),
  });
  if (!r.ok) throw new Error(`payments ${r.status}`);
  return r.json();
}
