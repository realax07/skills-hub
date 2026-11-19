import express from "express";
import { ordersRouter } from "./routes/orders";
import { webhooksRouter } from "./routes/webhooks";
import { startJobs } from "./jobs/scheduler";

const app = express();
app.use("/webhooks", express.raw({ type: "application/json" }), webhooksRouter);
app.use(express.json());
app.use("/api/orders", ordersRouter);
app.get("/health", (_req, res) => res.json({ ok: true }));

startJobs();
app.listen(Number(process.env.PORT || 3000));
