"""
==============================================================================
FreshMart POS Simulator / Event Gateway   (v2 — hardened)
==============================================================================
A Flask HTTP service that the dashboard calls.
Acts as the "POS register" + bridge to Kafka + PostgreSQL:

  Dashboard ─► POS Simulator ─► Kafka topics  ─► (NiFi consumes)
                              └► PostgreSQL    (audit log + direct writes)

Endpoints
---------
  POST /api/pos/sale              — fire a single POS sale event
  POST /api/pos/sale/bulk         — fire N sale events in one shot
  POST /api/vendor/delivery       — drop a vendor CSV row → Kafka
  POST /api/feedback              — submit customer feedback (recall workflow)
  POST /api/inventory/check       — manually trigger low-stock scan
  POST /api/schedule/notify       — HR push of weekly shift notifications
  POST /api/planogram/sync        — broadcast a planogram update via Kafka
  GET  /api/stats                 — dashboard counters
  GET  /api/recent/<table>        — recent rows from a given table
  GET  /api/topics                — list Kafka topics
  GET  /api/health                — readiness

Validation contract for /api/pos/sale
-------------------------------------
Required:  store_id (str), sku (str), qty (int > 0), price (number > 0)
Optional:  cashier_id (str), timestamp (ISO8601; default = now UTC)
On error:  HTTP 400 with {ok: false, errors: ["...", ...]}
==============================================================================
"""
import os
import json
import time
import random
import logging
from datetime import datetime, timezone
from typing import Any

from flask import Flask, request, jsonify
from flask_cors import CORS
from kafka import KafkaProducer, KafkaConsumer
from kafka.admin import KafkaAdminClient
import psycopg2
from psycopg2.extras import RealDictCursor

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
log = logging.getLogger("pos-simulator")

KAFKA_BROKERS = os.getenv("KAFKA_BROKERS", "kafka:29092")
PG_HOST       = os.getenv("POSTGRES_HOST", "postgres")
PG_USER       = os.getenv("POSTGRES_USER", "nifi")
PG_PASS       = os.getenv("POSTGRES_PASS", "nifi_secret")
PG_DB         = os.getenv("POSTGRES_DB",   "freshmart_dw")

# Topic names — centralised so the names line up with kafka-init and the dashboard
TOPIC_POS_SALES         = "pos-sales"
TOPIC_VENDOR_DELIVERIES = "vendor-deliveries"
TOPIC_CUSTOMER_FEEDBACK = "customer-feedback"
TOPIC_REORDER_ALERTS    = "reorder-alerts"
TOPIC_PLANOGRAM_UPDATES = "planogram-updates"
TOPIC_PRODUCT_RECALLS   = "product-recalls"
TOPIC_HR_NOTIFICATIONS  = "hr-notifications"          # FIX C: was wrongly "planogram-updates"
TOPIC_DLQ               = "dead-letter-queue"

app = Flask(__name__)
CORS(app)                  # allow the dashboard (different port) to call us


# ─── Lazy singletons ─────────────────────────────────────────────────────────
_producer: KafkaProducer | None = None

def producer() -> KafkaProducer:
    """Build (once) and return a Kafka producer. Retries on first connection.

    FIX G: if the producer was previously created but is no longer
    `bootstrap_connected()`, we tear it down and rebuild — preventing a
    permanently-stuck producer from blocking every subsequent request.
    """
    global _producer
    if _producer is not None:
        try:
            if _producer.bootstrap_connected():
                return _producer
        except Exception:
            pass
        try: _producer.close(timeout=2)
        except Exception: pass
        _producer = None

    for attempt in range(20):
        try:
            _producer = KafkaProducer(
                bootstrap_servers=KAFKA_BROKERS.split(","),
                value_serializer=lambda v: json.dumps(v, default=str).encode("utf-8"),
                key_serializer=lambda k: (k or "").encode("utf-8"),
                acks="all",
                retries=3,
                compression_type="gzip",
                request_timeout_ms=10000,
                max_block_ms=10000,
            )
            log.info("✓ Kafka producer connected to %s", KAFKA_BROKERS)
            return _producer
        except Exception as e:
            log.warning("Kafka not ready (attempt %d): %s", attempt + 1, e)
            time.sleep(3)
    raise RuntimeError("Kafka producer could not connect")


def pg() -> Any:
    """Open a fresh connection to PostgreSQL."""
    return psycopg2.connect(
        host=PG_HOST, user=PG_USER, password=PG_PASS, dbname=PG_DB,
        cursor_factory=RealDictCursor,
    )


def audit(event_type: str, source: str, payload: dict) -> None:
    """Insert a row into EVENT_LOG so every action is traceable in the DB."""
    try:
        with pg() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO EVENT_LOG (event_type, source, payload) VALUES (%s, %s, %s)",
                (event_type, source, json.dumps(payload, default=str)),
            )
    except Exception as e:
        log.error("audit failed: %s", e)


def now_iso() -> str:
    # FIX D: utcnow() is deprecated in Python 3.12; use timezone-aware now()
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def today_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def parse_body() -> dict:
    """FIX F: returns {} when there is no body, never None."""
    body = request.get_json(silent=True) or {}
    if not isinstance(body, dict):
        return {}
    return body


def fail(errors, code=400):
    """Standard error response."""
    return jsonify({"ok": False, "errors": errors}), code


def validate_sale(p: dict):
    """FIX A: explicit validation for POS sale payloads. Returns list of errors."""
    errs = []
    if not isinstance(p.get("store_id"), str) or not p.get("store_id"):
        errs.append("store_id is required (string)")
    if not isinstance(p.get("sku"), str) or not p.get("sku"):
        errs.append("sku is required (string)")
    try:
        if int(p.get("qty", 0)) <= 0:
            errs.append("qty must be a positive integer")
    except (TypeError, ValueError):
        errs.append("qty must be a positive integer")
    try:
        if float(p.get("price", 0)) <= 0:
            errs.append("price must be a positive number")
    except (TypeError, ValueError):
        errs.append("price must be a positive number")
    ts = p.get("timestamp")
    if ts:
        try:
            datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except Exception:
            errs.append("timestamp must be ISO8601")
    return errs


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/api/health")
def health():
    """Liveness + dependency status for the dashboard's banner."""
    status = {"service": "pos-simulator", "ts": now_iso()}
    try:
        with pg() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1")
        status["postgres"] = "up"
    except Exception as e:
        status["postgres"] = f"down: {e}"
    try:
        if producer().bootstrap_connected():
            status["kafka"] = "up"
        else:
            status["kafka"] = "down: not connected"
    except Exception as e:
        status["kafka"] = f"down: {e}"
    return jsonify(status)


def _record_sale(payload: dict) -> None:
    """
    Insert one sale into DW_SALES_FACT and decrement INVENTORY.
    Used by both single and bulk POS endpoints.
    FIX B: bulk endpoint now also writes to DW + decrements INVENTORY.
    """
    with pg() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO DW_SALES_FACT (store_id, sku, qty, unit_price, emp_id, sale_ts)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                payload["store_id"], payload["sku"], int(payload["qty"]),
                float(payload["price"]),
                payload.get("cashier_id"), payload["timestamp"],
            ),
        )
        cur.execute(
            """
            UPDATE INVENTORY
               SET qty = GREATEST(qty - %s, 0), updated_at = NOW()
             WHERE sku = %s AND store_id = %s
            """,
            (int(payload["qty"]), payload["sku"], payload["store_id"]),
        )


@app.route("/api/pos/sale", methods=["POST"])
def pos_sale():
    """
    Workflow 1 trigger: a single POS scan.
    Body: { store_id, sku, qty, price, cashier_id?, timestamp? }
    """
    payload = parse_body()
    errs = validate_sale(payload)
    if errs:
        return fail(errs, 400)

    payload.setdefault("timestamp", now_iso())

    try:
        producer().send(TOPIC_POS_SALES, key=payload.get("store_id", ""), value=payload)
        producer().flush(timeout=5)
    except Exception as e:
        log.error("Kafka publish failed: %s", e)
        return fail([f"kafka publish failed: {e}"], 502)

    try:
        _record_sale(payload)
    except Exception as e:
        log.error("DW insert failed: %s", e)
        return fail([f"db write failed: {e}"], 500)

    audit("POS_SALE", "dashboard", payload)
    return jsonify({"ok": True, "kafka_topic": TOPIC_POS_SALES, "payload": payload})


@app.route("/api/pos/sale/bulk", methods=["POST"])
def pos_sale_bulk():
    """
    Bulk-fire N sale events. Body: { count, store_id? }
    Each event also writes to DW_SALES_FACT and decrements INVENTORY (FIX B).
    """
    body = parse_body()
    try:
        count = int(body.get("count", 10))
    except (TypeError, ValueError):
        return fail(["count must be an integer"])
    if count < 1 or count > 500:
        return fail(["count must be between 1 and 500"])

    store = body.get("store_id", "FM-042")

    # FIX J: pull SKUs from INVENTORY so bulk events match real data for this store
    try:
        with pg() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT sku FROM INVENTORY WHERE store_id = %s AND qty > 0 LIMIT 20",
                (store,))
            skus = [r["sku"] for r in cur.fetchall()]
    except Exception as e:
        log.error("failed to read inventory for bulk: %s", e)
        skus = []
    if not skus:
        skus = ["BAN-CAVENDISH-1LB", "MILK-WHOLE-1G", "CHEESE-CHED-8OZ",
                "SODA-COKE-12PK", "CHICKEN-BRST-2LB"]

    employees = ["EMP-1147", "EMP-4521", "EMP-8801"]
    fired, failed = [], 0
    for _ in range(count):
        ev = {
            "store_id":   store,
            "sku":        random.choice(skus),
            "qty":        random.randint(1, 5),
            "price":      round(random.uniform(0.99, 12.99), 2),
            "cashier_id": random.choice(employees),
            "timestamp":  now_iso(),
        }
        try:
            producer().send(TOPIC_POS_SALES, key=ev["store_id"], value=ev)
            _record_sale(ev)           # FIX B
            fired.append(ev)
        except Exception as e:
            log.warning("bulk send/insert failed: %s", e)
            failed += 1

    try: producer().flush(timeout=5)
    except Exception: pass

    audit("POS_SALE_BULK", "dashboard",
          {"count": count, "store_id": store, "fired": len(fired), "failed": failed})
    return jsonify({"ok": True, "fired": len(fired), "failed": failed,
                    "topic": TOPIC_POS_SALES, "sample": fired[:3]})


@app.route("/api/vendor/delivery", methods=["POST"])
def vendor_delivery():
    """Workflow 3: vendor CSV row delivery."""
    payload = parse_body()
    errs = []
    for k in ("vendor_id", "sku"):
        if not payload.get(k):
            errs.append(f"{k} is required")
    try:
        if int(payload.get("cases", 0)) <= 0:
            errs.append("cases must be a positive integer")
    except (TypeError, ValueError):
        errs.append("cases must be a positive integer")
    try:
        if float(payload.get("unit_cost", 0)) <= 0:
            errs.append("unit_cost must be a positive number")
    except (TypeError, ValueError):
        errs.append("unit_cost must be a positive number")
    if errs:
        return fail(errs)

    payload.setdefault("delivery_date", today_iso())   # FIX D

    try:
        producer().send(TOPIC_VENDOR_DELIVERIES,
                        key=payload.get("vendor_id", ""), value=payload)
        producer().flush(timeout=5)
    except Exception as e:
        return fail([f"kafka publish failed: {e}"], 502)

    try:
        with pg() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO VENDOR_DELIVERIES (vendor_id, sku, cases, unit_cost, delivery_date)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    payload["vendor_id"], payload["sku"],
                    int(payload["cases"]), float(payload["unit_cost"]),
                    payload["delivery_date"],
                ),
            )
    except Exception as e:
        log.error("vendor insert failed: %s", e)
        return fail([f"db write failed: {e}"], 500)

    audit("VENDOR_DELIVERY", "dashboard", payload)
    return jsonify({"ok": True, "topic": TOPIC_VENDOR_DELIVERIES, "payload": payload})


@app.route("/api/feedback", methods=["POST"])
def feedback():
    """
    Workflow 6: customer feedback. Auto-classifies SAFETY keywords and
    publishes to `customer-feedback` topic for NiFi to consume and possibly
    trigger a product recall.
    """
    payload = parse_body()
    if not payload.get("sku"):
        return fail(["sku is required"])
    if not payload.get("feedback_text"):
        return fail(["feedback_text is required"])

    text = (payload.get("feedback_text") or "").lower()
    keywords = ["spoiled", "sick", "recall", "rotten", "mold", "expired"]
    category = "SAFETY" if any(k in text for k in keywords) else "GENERAL"
    payload["category"] = category
    payload.setdefault("received_at", now_iso())

    try:
        producer().send(TOPIC_CUSTOMER_FEEDBACK,
                        key=payload.get("sku", ""), value=payload)
        producer().flush(timeout=5)
    except Exception as e:
        return fail([f"kafka publish failed: {e}"], 502)

    try:
        with pg() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO CUSTOMER_FEEDBACK (store_id, sku, feedback_text, category)
                VALUES (%s, %s, %s, %s)
                """,
                (
                    payload.get("store_id"), payload.get("sku"),
                    payload.get("feedback_text"), category,
                ),
            )
            if category == "SAFETY":
                cur.execute(
                    """
                    SELECT COUNT(*) AS count FROM CUSTOMER_FEEDBACK
                     WHERE sku=%s AND category='SAFETY'
                       AND received_at > NOW() - INTERVAL '1 hour'
                    """,
                    (payload.get("sku"),),
                )
                row = cur.fetchone()
                count = row["count"] if row else 0
                if count >= 5:
                    cur.execute(
                        "UPDATE CUSTOMER_FEEDBACK SET recall_triggered=TRUE WHERE sku=%s",
                        (payload.get("sku"),),
                    )
                    try:
                        producer().send(TOPIC_PRODUCT_RECALLS,
                                        key=payload.get("sku", ""),
                                        value={"sku": payload.get("sku"),
                                               "severity": "CRITICAL",
                                               "complaint_count": count,
                                               "triggered_at": now_iso()})
                        producer().flush(timeout=5)
                    except Exception as e:
                        log.error("recall publish failed: %s", e)
                    payload["recall_triggered"] = True
    except Exception as e:
        log.error("feedback insert failed: %s", e)
        return fail([f"db write failed: {e}"], 500)

    audit("FEEDBACK", "dashboard", payload)
    return jsonify({"ok": True, "topic": TOPIC_CUSTOMER_FEEDBACK,
                    "category": category, "payload": payload})


@app.route("/api/inventory/check", methods=["POST"])
def inventory_check():
    """Workflow 2: scan inventory for items below threshold and emit reorder alerts."""
    triggered = []
    try:
        with pg() as conn, conn.cursor() as cur:
            cur.execute("""
                SELECT i.sku, i.store_id, i.qty, i.reorder_threshold,
                       p.name, p.vendor_id
                  FROM INVENTORY i
             LEFT JOIN PRODUCT_CATALOG p ON p.sku = i.sku
                 WHERE i.qty < i.reorder_threshold
            """)
            rows = cur.fetchall()
            for r in rows:
                reorder_qty = max(r["reorder_threshold"] * 4, 100)
                msg = {
                    "store_id":          r["store_id"],
                    "sku":               r["sku"],
                    "product_name":      r["name"],
                    "vendor_id":         r["vendor_id"],
                    "current_qty":       r["qty"],
                    "reorder_threshold": r["reorder_threshold"],
                    "reorder_qty":       reorder_qty,
                    "alert_time":        now_iso(),
                }
                try:
                    producer().send(TOPIC_REORDER_ALERTS,
                                    key=r["store_id"], value=msg)
                except Exception as e:
                    log.warning("reorder publish failed: %s", e)
                cur.execute(
                    """
                    INSERT INTO REORDER_LOG (sku, store_id, vendor_id, qty_ordered)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (r["sku"], r["store_id"], r["vendor_id"], reorder_qty),
                )
                triggered.append(msg)
        try: producer().flush(timeout=5)
        except Exception: pass
    except Exception as e:
        log.error("inventory check failed: %s", e)
        return fail([f"inventory check failed: {e}"], 500)

    audit("INVENTORY_CHECK", "dashboard", {"triggered_count": len(triggered)})
    return jsonify({"ok": True, "triggered": triggered, "topic": TOPIC_REORDER_ALERTS})


@app.route("/api/schedule/notify", methods=["POST"])
def schedule_notify():
    """Workflow 5: HR sync — push weekly shift events into Kafka.

    FIX C: now publishes to TOPIC_HR_NOTIFICATIONS (was wrongly planogram-updates).
    """
    body = parse_body()
    week = body.get("week_start", today_iso())

    notifications = []
    try:
        with pg() as conn, conn.cursor() as cur:
            cur.execute("""
                SELECT emp_id, emp_name, emp_email, department, store_id
                  FROM EMPLOYEES
                 WHERE role IN ('CASHIER','STOCKER','MANAGER')
            """)
            for emp in cur.fetchall():
                msg = {
                    "emp_id":     emp["emp_id"],
                    "emp_name":   emp["emp_name"],
                    "emp_email":  emp["emp_email"],
                    "department": emp["department"],
                    "store_id":   emp["store_id"],
                    "week_start": week,
                    "subject":    f"Your FreshMart Schedule — Week of {week}",
                    "sent_at":    now_iso(),
                }
                try:
                    producer().send(TOPIC_HR_NOTIFICATIONS,    # ← FIX C
                                    key=emp["emp_id"], value=msg)
                    notifications.append(msg)
                except Exception as e:
                    log.warning("hr publish failed for %s: %s", emp["emp_id"], e)
        try: producer().flush(timeout=5)
        except Exception: pass
    except Exception as e:
        return fail([f"hr sync failed: {e}"], 500)

    audit("HR_NOTIFY", "dashboard", {"count": len(notifications), "week_start": week})
    return jsonify({"ok": True, "notified": len(notifications),
                    "topic": TOPIC_HR_NOTIFICATIONS, "sample": notifications[:3]})


@app.route("/api/planogram/sync", methods=["POST"])
def planogram_sync():
    """
    Workflow 4: broadcast a planogram update via Kafka (mirrors SNS fan-out).

    FIX K: store_id == 'ALL' fans out to every known store.
    """
    payload = parse_body()
    if not payload.get("sku"):
        return fail(["sku is required"])
    payload.setdefault("updated_at", now_iso())

    target_stores = []
    try:
        with pg() as conn, conn.cursor() as cur:
            if str(payload.get("store_id", "")).upper() == "ALL":
                cur.execute("SELECT store_id FROM STORES")
                target_stores = [r["store_id"] for r in cur.fetchall()]
            else:
                target_stores = [payload.get("store_id")]
    except Exception as e:
        log.error("planogram store resolve failed: %s", e)
        target_stores = [payload.get("store_id")]

    target_stores = [s for s in target_stores if s]
    if not target_stores:
        return fail(["store_id is required"])

    published = []
    try:
        with pg() as conn, conn.cursor() as cur:
            for store_id in target_stores:
                msg = dict(payload, store_id=store_id)
                try:
                    producer().send(TOPIC_PLANOGRAM_UPDATES,
                                    key=store_id, value=msg)
                except Exception as e:
                    log.warning("planogram publish failed: %s", e)
                cur.execute(
                    """
                    INSERT INTO PRODUCT_LOCATIONS (sku, store_id, aisle, section, shelf_level)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (sku, store_id) DO UPDATE
                       SET aisle=EXCLUDED.aisle,
                           section=EXCLUDED.section,
                           shelf_level=EXCLUDED.shelf_level,
                           updated_at=NOW()
                    """,
                    (
                        msg["sku"], store_id, msg.get("aisle"),
                        msg.get("section"), int(msg.get("shelf_level") or 1),
                    ),
                )
                published.append(msg)
        try: producer().flush(timeout=5)
        except Exception: pass
    except Exception as e:
        log.error("planogram db failed: %s", e)
        return fail([f"db write failed: {e}"], 500)

    audit("PLANOGRAM", "dashboard", {"stores": target_stores, "sku": payload.get("sku")})
    return jsonify({"ok": True, "topic": TOPIC_PLANOGRAM_UPDATES,
                    "published": len(published), "stores": target_stores,
                    "payload": payload})


@app.route("/api/stats")
def stats():
    """Counters powering the dashboard's top KPI cards."""
    out = {}
    try:
        with pg() as conn, conn.cursor() as cur:
            for label, sql_ in [
                ("sales",      "SELECT COUNT(*) AS count FROM DW_SALES_FACT"),
                ("feedback",   "SELECT COUNT(*) AS count FROM CUSTOMER_FEEDBACK"),
                ("reorders",   "SELECT COUNT(*) AS count FROM REORDER_LOG"),
                ("deliveries", "SELECT COUNT(*) AS count FROM VENDOR_DELIVERIES"),
                ("recalls",    "SELECT COUNT(*) AS count FROM CUSTOMER_FEEDBACK WHERE recall_triggered=TRUE"),
                ("events",     "SELECT COUNT(*) AS count FROM EVENT_LOG"),
                ("low_stock",  "SELECT COUNT(*) AS count FROM INVENTORY WHERE qty < reorder_threshold"),
            ]:
                cur.execute(sql_)
                row = cur.fetchone()
                out[label] = row["count"] if row else 0
    except Exception as e:
        out["error"] = str(e)
    return jsonify(out)


@app.route("/api/recent/<table>")
def recent(table):
    """Last N rows of one of the whitelisted tables."""
    safe = {
        "sales":      "SELECT * FROM DW_SALES_FACT     ORDER BY id DESC LIMIT 20",
        "feedback":   "SELECT * FROM CUSTOMER_FEEDBACK ORDER BY id DESC LIMIT 20",
        "reorders":   "SELECT * FROM REORDER_LOG      ORDER BY id DESC LIMIT 20",
        "deliveries": "SELECT * FROM VENDOR_DELIVERIES ORDER BY id DESC LIMIT 20",
        "events":     "SELECT * FROM EVENT_LOG        ORDER BY id DESC LIMIT 20",
        "inventory":  "SELECT * FROM INVENTORY        ORDER BY updated_at DESC LIMIT 30",
        "employees":  "SELECT * FROM EMPLOYEES        ORDER BY emp_id ASC LIMIT 30",
    }
    if table not in safe:
        return jsonify({"error": "unknown table"}), 404
    try:
        with pg() as conn, conn.cursor() as cur:
            cur.execute(safe[table])
            rows = [dict(r) for r in cur.fetchall()]
            for row in rows:
                for k, v in list(row.items()):
                    if isinstance(v, datetime):
                        row[k] = v.isoformat()
            return jsonify(rows)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/topics")
def topics():
    """List Kafka topics (drives the dashboard's Kafka panel)."""
    try:
        admin = KafkaAdminClient(bootstrap_servers=KAFKA_BROKERS.split(","),
                                 request_timeout_ms=5000)
        topics_list = sorted(admin.list_topics())
        try: admin.close()
        except Exception: pass
        return jsonify({"topics": topics_list})
    except Exception as e:
        return jsonify({"error": str(e), "topics": []}), 200


@app.route("/api/topics/<topic>/peek")
def topic_peek(topic):
    """Read up to 10 most recent messages from a topic for inspection."""
    try:
        consumer = KafkaConsumer(
            topic,
            bootstrap_servers=KAFKA_BROKERS.split(","),
            auto_offset_reset="earliest",
            enable_auto_commit=False,
            consumer_timeout_ms=1500,
            value_deserializer=lambda v: v.decode("utf-8", errors="replace"),
        )
        msgs = []
        for m in consumer:
            msgs.append({"offset": m.offset, "partition": m.partition, "value": m.value})
            if len(msgs) >= 30: break
        consumer.close()
        return jsonify({"topic": topic, "messages": msgs[-10:]})
    except Exception as e:
        return jsonify({"error": str(e), "messages": []}), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=9090, debug=False)
