import { Router } from "express";
import { PrismaClient } from "@prisma/client";
import { producer } from "../bus";
import { charge } from "../clients/payments";

const db = new PrismaClient();
export const ordersRouter = Router();

ordersRouter.post("/", async (req, res) => {
  const { customerId, total } = req.body;
  if (!customerId || !(total > 0)) return res.status(400).json({ error: "customerId and total are required" });
  const order = await db.order.create({ data: { customerId, total, status: "NEW" } });
  await producer.send({
    topic: "orders.created",
    messages: [{ key: order.id, value: JSON.stringify({ orderId: order.id, customerId, total }) }],
  });
  try {
    const payment = await charge(order.id, Number(total));
    await db.order.update({ where: { id: order.id }, data: { paymentId: payment.id, status: "PAYMENT_PENDING" } });
    res.status(201).json({ id: order.id, status: "PAYMENT_PENDING", paymentId: payment.id });
  } catch (e) {
    res.status(502).json({ id: order.id, status: "NEW", error: "payment failed" });
  }
});

ordersRouter.get("/:id", async (req, res) => {
  const order = await db.order.findUnique({ where: { id: req.params.id } });
  if (!order) return res.status(404).end();
  res.json(order);
});

ordersRouter.post("/:id/cancel", async (req, res) => {
  const order = await db.order.findUnique({ where: { id: req.params.id } });
  if (!order) return res.status(404).end();
  if (order.status === "PAID") return res.status(409).json({ error: "already paid" });
  await db.order.update({ where: { id: order.id }, data: { status: "CANCELLED" } });
  res.json({ id: order.id, status: "CANCELLED" });
});
