import Stripe from "stripe";

export const stripe = new Stripe(process.env.STRIPE_SECRET_KEY!, { apiVersion: "2023-10-16" });

export async function createPaymentIntent(orderId: string, amountCents: number) {
  return stripe.paymentIntents.create({ amount: amountCents, currency: "rub", metadata: { orderId } });
}

export async function refund(paymentIntentId: string, amountCents: number) {
  // FIXME: частичный возврат за флагом FEATURE_PARTIAL_REFUNDS ещё не сделан
  return stripe.refunds.create({ payment_intent: paymentIntentId, amount: amountCents });
}
