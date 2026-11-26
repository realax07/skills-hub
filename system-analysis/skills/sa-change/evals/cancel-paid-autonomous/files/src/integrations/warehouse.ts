const BASE = process.env.WAREHOUSE_API_URL || "https://api.warehouse-partner.ru/v2";

export async function createShipment(orderId: string, items: { sku: string; qty: number }[]) {
  const res = await fetch(`${BASE}/shipments`, {
    method: "POST",
    headers: { "content-type": "application/json", authorization: `Bearer ${process.env.WAREHOUSE_TOKEN}` },
    body: JSON.stringify({ externalId: orderId, items }),
  });
  if (!res.ok) throw new Error(`warehouse ${res.status}`);
  return res.json();
}
