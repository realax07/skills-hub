import json
import os

import httpx
from kafka import KafkaConsumer, KafkaProducer

ORDERS_URL = os.environ.get("ORDERS_URL", "http://orders:3000")
consumer = KafkaConsumer("payments.completed", bootstrap_servers=os.environ["KAFKA_BROKERS"].split(","), group_id="delivery")
producer = KafkaProducer(bootstrap_servers=os.environ["KAFKA_BROKERS"].split(","), value_serializer=lambda v: json.dumps(v).encode())


def main():
    for msg in consumer:
        e = json.loads(msg.value)
        if e.get("status") != "succeeded":
            continue
        order = httpx.get(f"{ORDERS_URL}/api/orders/{e['orderId']}", timeout=5).json()
        # курьерская служба пока вручную: просто фиксируем отгрузку
        producer.send("delivery.shipped", {"orderId": order["id"], "customerId": order["customerId"]})


if __name__ == "__main__":
    main()
