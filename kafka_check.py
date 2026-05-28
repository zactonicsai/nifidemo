#!/usr/bin/env python3
"""
Simple Kafka health check: verify the broker is up, send a message, receive it.

Configuration via environment variables:
    KAFKA_BOOTSTRAP_SERVERS   Broker address(es)        default: localhost:9092
    KAFKA_TOPIC               Topic to use              default: healthcheck
    KAFKA_MESSAGE             Message to send           default: "ping"
    KAFKA_GROUP_ID            Consumer group id         default: healthcheck-group
    KAFKA_TIMEOUT             Seconds to wait for msg   default: 10
    KAFKA_SECURITY_PROTOCOL   e.g. SASL_SSL (optional)
    KAFKA_SASL_MECHANISM      e.g. PLAIN (optional)
    KAFKA_SASL_USERNAME       (optional)
    KAFKA_SASL_PASSWORD       (optional)

Requires:  pip install kafka-python
"""

import os
import sys
import json
import time
import uuid

from kafka import KafkaProducer, KafkaConsumer
from kafka.admin import KafkaAdminClient
from kafka.errors import KafkaError


def get_conn_config():
    """Build connection kwargs shared by all clients from env vars."""
    cfg = {
        "bootstrap_servers": os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092").split(","),
    }
    sec = os.getenv("KAFKA_SECURITY_PROTOCOL")
    if sec:
        cfg["security_protocol"] = sec
    mech = os.getenv("KAFKA_SASL_MECHANISM")
    if mech:
        cfg["sasl_mechanism"] = mech
        cfg["sasl_plain_username"] = os.getenv("KAFKA_SASL_USERNAME")
        cfg["sasl_plain_password"] = os.getenv("KAFKA_SASL_PASSWORD")
    return cfg


def check_broker(conn):
    """Return True if the broker responds to an admin metadata request."""
    try:
        admin = KafkaAdminClient(**conn, request_timeout_ms=5000)
        topics = admin.list_topics()
        admin.close()
        print(f"[OK] Broker is up. {len(topics)} topic(s) visible.")
        return True
    except KafkaError as e:
        print(f"[FAIL] Could not reach broker: {e}")
        return False


def send_and_receive(conn, topic, message, group_id, timeout):
    """Send one message and try to read it back. Returns True on success."""
    token = f"{message}-{uuid.uuid4().hex[:8]}"

    # Consumer first so we don't miss the message.
    consumer = KafkaConsumer(
        topic,
        **conn,
        group_id=group_id,
        auto_offset_reset="latest",
        consumer_timeout_ms=timeout * 1000,
        value_deserializer=lambda v: v.decode("utf-8"),
    )
    # Force partition assignment before producing.
    consumer.poll(timeout_ms=2000)

    producer = KafkaProducer(
        **conn,
        value_serializer=lambda v: v.encode("utf-8"),
    )
    producer.send(topic, token).get(timeout=10)
    producer.flush()
    print(f"[OK] Sent message: {token!r}")

    deadline = time.time() + timeout
    for msg in consumer:
        if msg.value == token:
            print(f"[OK] Received message: {msg.value!r}")
            consumer.close()
            producer.close()
            return True
        if time.time() > deadline:
            break

    print("[FAIL] Did not receive the sent message within timeout.")
    consumer.close()
    producer.close()
    return False


def main():
    conn = get_conn_config()
    topic = os.getenv("KAFKA_TOPIC", "healthcheck")
    message = os.getenv("KAFKA_MESSAGE", "ping")
    group_id = os.getenv("KAFKA_GROUP_ID", "healthcheck-group")
    timeout = int(os.getenv("KAFKA_TIMEOUT", "10"))

    print(f"Connecting to {conn['bootstrap_servers']} (topic={topic})")

    if not check_broker(conn):
        sys.exit(1)

    ok = send_and_receive(conn, topic, message, group_id, timeout)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
