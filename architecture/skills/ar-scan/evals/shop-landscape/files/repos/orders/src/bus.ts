import { Kafka } from "kafkajs";

const kafka = new Kafka({ clientId: "orders", brokers: (process.env.KAFKA_BROKERS ?? "localhost:9092").split(",") });
export const producer = kafka.producer();
export const consumer = kafka.consumer({ groupId: "orders" });
