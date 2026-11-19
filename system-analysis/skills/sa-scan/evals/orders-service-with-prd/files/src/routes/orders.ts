import { Router } from "express";
import { prisma } from "../models/db";
import { requireAuth, requireRole } from "../auth";
import { createPaymentIntent, refund } from "../integrations/stripe";
import { shipQueue } from "../jobs/queues";

export const ordersRouter = Router();
ordersRouter.use(requireAuth);

const MAX_ITEMS = 50;

// Создать заказ: считает сумму по ценам из запроса и создаёт платёж в Stripe
ordersRouter.post("/", async (req, res) => {
  const items = req.body.items || [];
  if (items.length === 0 || items.length > MAX_ITEMS) return res.status(422).json({ error: "items" });
  const totalCents = items.reduce((s: number, i: any) => s + i.priceCents * i.qty, 0);
  // TODO: брать цены из каталога, а не из запроса клиента
  const order = await prisma.order.create({
    data: { userId: req.user.id, totalCents, items: { create: items } },
  });
  const intent = await createPaymentIntent(order.id, totalCents);
  await prisma.order.update({ where: { id: order.id }, data: { paymentId: intent.id } });
  res.status(201).json({ id: order.id, clientSecret: intent.client_secret });
});

ordersRouter.get("/", async (req, res) => {
  const where = req.user.role === "CUSTOMER" ? { userId: req.user.id } : {};
  res.json(await prisma.order.findMany({ where, orderBy: { createdAt: "desc" }, take: 100 }));
});

ordersRouter.get("/:id", async (req, res) => {
  const order = await prisma.order.findUnique({ where: { id: req.params.id }, include: { items: true } });
  if (!order || (req.user.role === "CUSTOMER" && order.userId !== req.user.id)) return res.status(404).end();
  res.json(order);
});

// Отмена: клиент может отменить только NEW, менеджер — NEW и PAID (с возвратом)
ordersRouter.post("/:id/cancel", async (req, res) => {
  const order = await prisma.order.findUnique({ where: { id: req.params.id } });
  if (!order) return res.status(404).end();
  const isCustomer = req.user.role === "CUSTOMER";
  if (isCustomer && (order.userId !== req.user.id || order.status !== "NEW")) return res.status(409).json({ error: "state" });
  if (order.status === "PAID") {
    await refund(order.paymentId!, order.totalCents);
    await prisma.order.update({ where: { id: order.id }, data: { status: "REFUNDED" } });
    return res.json({ status: "REFUNDED" });
  }
  if (order.status !== "NEW") return res.status(409).json({ error: "state" });
  await prisma.order.update({ where: { id: order.id }, data: { status: "CANCELLED" } });
  res.json({ status: "CANCELLED" });
});

ordersRouter.post("/:id/ship", requireRole("MANAGER"), async (req, res) => {
  const order = await prisma.order.findUnique({ where: { id: req.params.id } });
  if (!order || order.status !== "PAID") return res.status(409).json({ error: "state" });
  await shipQueue.add("ship", { orderId: order.id });
  res.status(202).json({ queued: true });
});
