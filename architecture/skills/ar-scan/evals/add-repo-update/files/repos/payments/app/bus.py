import json
import os

from kafka import KafkaProducer

producer = KafkaProducer(
    bootstrap_servers=os.environ.get("KAFKA_BROKERS", "localhost:9092").split(","),
    value_serializer=lambda v: json.dumps(v).encode(),
)
