import cron from "node-cron";
import { prisma } from "../models/db";

export function startJobs() {
  // каждые 15 минут отменяем неоплаченные заказы старше 30 минут
  cron.schedule("*/15 * * * *", async () => {
    const cutoff = new Date(Date.now() - 30 * 60 * 1000);
    await prisma.order.updateMany({ where: { status: "NEW", createdAt: { lt: cutoff } }, data: { status: "CANCELLED" } });
  });
}
