import express from "express";
import { ordersRouter } from "./routes/orders";
import { startPaymentConsumer } from "./consumers/payments";

const app = express();
app.use(express.json());
app.use("/api/orders", ordersRouter);

startPaymentConsumer().catch((e) => console.error("payment consumer failed", e));
app.listen(Number(process.env.PORT ?? 3000));
