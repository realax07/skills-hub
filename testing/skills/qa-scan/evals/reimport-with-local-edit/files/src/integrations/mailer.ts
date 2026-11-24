import nodemailer from "nodemailer";
import { prisma } from "../models/db";

const transport = nodemailer.createTransport({ host: process.env.SMTP_HOST, port: 587 });

export async function sendReceipt(orderId: string) {
  const order = await prisma.order.findUnique({ where: { id: orderId }, include: { user: true } });
  if (!order) return;
  await transport.sendMail({ to: order.user.email, from: "shop@orders.example.ru", subject: `Заказ ${order.id} оплачен`, text: `Сумма: ${order.totalCents / 100} ₽` });
}
