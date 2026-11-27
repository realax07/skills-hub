import { Router } from "express";
import { stripe } from "../integrations/stripe";
import { prisma } from "../models/db";
import { sendReceipt } from "../integrations/mailer";

export const webhooksRouter = Router();

webhooksRouter.post("/stripe", async (req, res) => {
  let event;
  try {
    event = stripe.webhooks.constructEvent(req.body, req.headers["stripe-signature"] as string, process.env.STRIPE_WEBHOOK_SECRET!);
  } catch {
    return res.status(400).send("bad signature");
  }
  if (event.type === "payment_intent.succeeded") {
    const order = await prisma.order.findFirst({ where: { paymentId: event.data.object.id } });
    if (order && order.status === "NEW") {
      await prisma.order.update({ where: { id: order.id }, data: { status: "PAID" } });
      await sendReceipt(order.id);
    }
  }
  res.json({ received: true });
});
