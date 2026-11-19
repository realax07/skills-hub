import { Queue, Worker } from "bullmq";
import { prisma } from "../models/db";
import { createShipment } from "../integrations/warehouse";

const connection = { url: process.env.REDIS_URL };
export const shipQueue = new Queue("ship", { connection });

new Worker("ship", async (job) => {
  const order = await prisma.order.findUnique({ where: { id: job.data.orderId }, include: { items: true } });
  if (!order || order.status !== "PAID") return;
  await createShipment(order.id, order.items.map((i) => ({ sku: i.sku, qty: i.qty })));
  await prisma.order.update({ where: { id: order.id }, data: { status: "SHIPPED" } });
}, { connection, attempts: 5 } as any);
