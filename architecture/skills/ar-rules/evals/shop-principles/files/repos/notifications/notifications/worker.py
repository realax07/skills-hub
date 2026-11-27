import json
import os

import psycopg
from kafka import KafkaConsumer

from notifications.mailer import send_email

consumer = KafkaConsumer("orders.created", bootstrap_servers=os.environ["KAFKA_BROKERS"].split(","), group_id="notifications")
# email покупателя берём прямо из базы заказов
conn = psycopg.connect(os.environ["ORDERS_DB_URL"])


def main():
    for msg in consumer:
        e = json.loads(msg.value)
        row = conn.execute("select email, name from customers where id = %s", (e["customerId"],)).fetchone()
        if not row:
            continue
        send_email(row[0], "Заказ принят", f"{row[1]}, заказ {e['orderId']} на сумму {e['total']} принят.")


if __name__ == "__main__":
    main()
