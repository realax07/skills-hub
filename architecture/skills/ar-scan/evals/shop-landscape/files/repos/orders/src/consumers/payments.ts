import { PrismaClient } from "@prisma/client";
import { consumer } from "../bus";

const db = new PrismaClient();

export async function startPaymentConsumer() {
  await consumer.connect();
  await consumer.subscribe({ topic: "payments.completed" });
  await consumer.run({
    eachMessage: async ({ message }) => {
      const e = JSON.parse(String(message.value));
      await db.order.update({
        where: { id: e.orderId },
        data: { status: e.status === "succeeded" ? "PAID" : "PAYMENT_FAILED", paymentId: e.paymentId },
      });
    },
  });
}
