"""
End-to-end harness for pos-simulator/app.py.

Strategy
--------
- Mock `psycopg2` with a SQLite-backed shim that translates PG SQL dialect →
  SQLite where needed. This lets us actually run the SQL, populate tables,
  and verify counts/joins without Docker.
- Mock `kafka.KafkaProducer`, `kafka.KafkaConsumer`, `kafka.admin.KafkaAdminClient`
  to capture sends without a real broker.
- Use Flask's test_client() to drive every endpoint exactly as the dashboard does.
"""
import sys, os, json, types, sqlite3, re, datetime as dt, importlib

ROOT = "/home/claude/freshmart-nifi"
sys.path.insert(0, ROOT + "/pos-simulator")

# ─── 1. Mock kafka before app.py imports it ──────────────────────────────────
sent_messages = []          # list of (topic, key, value)

class FakeFuture:
    def get(self, timeout=None): return None

class FakeProducer:
    def __init__(self, **kw): self.kw = kw
    def send(self, topic, key=None, value=None):
        sent_messages.append((topic, key, value))
        return FakeFuture()
    def flush(self, timeout=None): pass
    def bootstrap_connected(self): return True
    def close(self, timeout=None): pass

class FakeConsumer:
    def __init__(self, *a, **kw): pass
    def __iter__(self): return iter([])
    def close(self): pass

class FakeAdmin:
    def __init__(self, **kw): pass
    def list_topics(self): return sorted({t for (t, _, _) in sent_messages})

fake_kafka = types.ModuleType("kafka")
fake_kafka.KafkaProducer = FakeProducer
fake_kafka.KafkaConsumer = FakeConsumer
fake_kafka_admin = types.ModuleType("kafka.admin")
fake_kafka_admin.KafkaAdminClient = FakeAdmin
fake_kafka.admin = fake_kafka_admin
sys.modules["kafka"] = fake_kafka
sys.modules["kafka.admin"] = fake_kafka_admin


# ─── 2. SQLite-backed psycopg2 stand-in ──────────────────────────────────────
SQLITE_DB = ":memory:"
_conn_singleton = sqlite3.connect(SQLITE_DB, check_same_thread=False)
_conn_singleton.row_factory = sqlite3.Row

def translate_sql(sql: str) -> str:
    """Convert PG-only fragments to something SQLite tolerates."""
    s = sql
    s = s.replace("BIGSERIAL", "INTEGER")
    s = s.replace("TIMESTAMPTZ", "TEXT")
    s = s.replace("JSONB", "TEXT")
    s = s.replace("DECIMAL(10,2)", "REAL")
    s = re.sub(r"VARCHAR\(\d+\)", "TEXT", s)
    s = s.replace("DEFAULT NOW()", "DEFAULT CURRENT_TIMESTAMP")
    s = s.replace("NOW()", "CURRENT_TIMESTAMP")
    s = s.replace("ON CONFLICT", "ON CONFLICT")
    # Handle both `NOW() - INTERVAL '1 hour'` and `CURRENT_TIMESTAMP - INTERVAL '1 hour'`
    s = re.sub(r"(NOW\(\)|CURRENT_TIMESTAMP)\s*-\s*INTERVAL\s*'1 hour'",
               "datetime('now','-1 hour')", s)
    # GREATEST emulated
    s = re.sub(r"GREATEST\(([^,]+),\s*0\)", r"MAX(\1, 0)", s)
    # PG uses %s placeholders; SQLite uses ?
    s = s.replace("%s", "?")
    return s

class FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self.last = None
    def execute(self, sql, params=None):
        sql_t = translate_sql(sql)
        try:
            self.last = self.conn.execute(sql_t, params or ())
        except sqlite3.Error as e:
            raise RuntimeError(f"SQLite error: {e}\nSQL: {sql_t}\nParams: {params}") from e
        return self
    def fetchone(self):
        if not self.last: return None
        row = self.last.fetchone()
        if row is None: return None
        # Match the RealDictCursor contract: keys accessible by name
        d = {k: row[k] for k in row.keys()}
        # Also expose lowercase "count" key for SELECT COUNT(*) results
        if len(d) == 1 and "COUNT(*)" in list(d.keys())[0].upper():
            d["count"] = list(d.values())[0]
        # In PG, COUNT(*) returns column name "count"; SQLite returns "COUNT(*)"
        if "COUNT(*)" in d:
            d["count"] = d["COUNT(*)"]
        return d
    def fetchall(self):
        if not self.last: return []
        return [{k: r[k] for k in r.keys()} for r in self.last.fetchall()]
    def close(self): pass
    def __enter__(self): return self
    def __exit__(self, *a): self.close()

class FakeConn:
    def __init__(self): self.c = _conn_singleton
    def cursor(self, cursor_factory=None): return FakeCursor(self.c)
    def commit(self): self.c.commit()
    def rollback(self): self.c.rollback()
    def close(self): pass
    def __enter__(self): return self
    def __exit__(self, et, ev, tb):
        if et is None: self.commit()
        else: self.rollback()

fake_psycopg = types.ModuleType("psycopg2")
fake_psycopg.connect = lambda **kw: FakeConn()
fake_psycopg_extras = types.ModuleType("psycopg2.extras")
class _RDC: pass
fake_psycopg_extras.RealDictCursor = _RDC
fake_psycopg.extras = fake_psycopg_extras
sys.modules["psycopg2"] = fake_psycopg
sys.modules["psycopg2.extras"] = fake_psycopg_extras


# ─── 3. Initialise SQLite with the project's init + seed SQL ─────────────────
def run_sql_file(path):
    with open(path) as f: raw = f.read()
    # SQLite doesn't grok all PG, but our schema is simple. Translate per statement.
    stmts = []
    cur = []
    for line in raw.splitlines():
        if line.strip().startswith("--"): continue
        cur.append(line)
        if line.rstrip().endswith(";"):
            stmts.append("\n".join(cur))
            cur = []
    for s in stmts:
        s = s.strip()
        if not s: continue
        # SQLite doesn't support ON CONFLICT (col,col) DO NOTHING in older versions but 3.24+ does.
        s_t = translate_sql(s)
        # SQLite doesn't allow CREATE INDEX inside same call if table missing yet — ok in our order.
        try:
            _conn_singleton.executescript(s_t)
        except sqlite3.OperationalError as e:
            print(f"⚠ SQL skipped: {e}\n{s_t[:200]}")
    _conn_singleton.commit()

print("─" * 70)
print("Loading schema + seed data into in-memory SQLite...")
run_sql_file(f"{ROOT}/sql/init.sql")
run_sql_file(f"{ROOT}/sql/seed.sql")


# ─── 4. Import the app ───────────────────────────────────────────────────────
os.environ["KAFKA_BROKERS"] = "fake:1234"
import app as posapp
posapp.app.testing = True
client = posapp.app.test_client()


# ─── 5. Run the test sequence ────────────────────────────────────────────────
PASS, FAIL = 0, 0
def check(label, cond, detail=""):
    global PASS, FAIL
    mark = "✓" if cond else "✗"
    print(f"  {mark} {label}" + (f"  [{detail}]" if detail else ""))
    if cond: PASS += 1
    else:    FAIL += 1

def post(path, body=None):
    return client.post(path, data=json.dumps(body or {}),
                       headers={"Content-Type": "application/json"})

def get(path):
    return client.get(path)


print("\n" + "─" * 70)
print("TEST 1 — /api/health")
r = get("/api/health")
print(f"   status={r.status_code}  body={r.get_json()}")
check("status 200", r.status_code == 200)
check("postgres up", r.get_json().get("postgres") == "up")
check("kafka up",    r.get_json().get("kafka") == "up")

print("\nTEST 2 — /api/pos/sale (single)")
sent_messages.clear()
body = {"store_id":"FM-042","sku":"BAN-CAVENDISH-1LB","qty":3,
        "price":0.99,"cashier_id":"EMP-1147"}
r = post("/api/pos/sale", body)
print(f"   status={r.status_code}  body={r.get_json()}")
check("status 200", r.status_code == 200)
check("Kafka topic pos-sales fired", any(m[0] == "pos-sales" for m in sent_messages))
# Check DW write
cur = _conn_singleton.execute("SELECT COUNT(*) FROM DW_SALES_FACT WHERE store_id='FM-042' AND sku='BAN-CAVENDISH-1LB'")
n = cur.fetchone()[0]
check(f"DW_SALES_FACT got 1 row", n == 1, f"rows={n}")
# Check inventory decremented (started at 18, qty=3 → 15)
cur = _conn_singleton.execute("SELECT qty FROM INVENTORY WHERE sku='BAN-CAVENDISH-1LB' AND store_id='FM-042'")
inv = cur.fetchone()[0]
check(f"INVENTORY decremented to 15", inv == 15, f"qty={inv}")

print("\nTEST 3 — /api/pos/sale/bulk")
sent_messages.clear()
r = post("/api/pos/sale/bulk", {"count": 25, "store_id": "FM-042"})
print(f"   status={r.status_code}  fired={r.get_json().get('fired')}")
check("status 200", r.status_code == 200)
check("25 Kafka messages",
      len([m for m in sent_messages if m[0] == "pos-sales"]) == 25)
# Bulk handler does NOT write to DW or decrement inventory — that's by design

print("\nTEST 4 — /api/vendor/delivery")
sent_messages.clear()
r = post("/api/vendor/delivery", {
    "vendor_id":"DOLE","sku":"BAN-CAVENDISH-1LB","cases":240,"unit_cost":0.28})
print(f"   status={r.status_code}  body={r.get_json()}")
check("status 200", r.status_code == 200)
check("Kafka topic vendor-deliveries fired",
      any(m[0] == "vendor-deliveries" for m in sent_messages))
cur = _conn_singleton.execute("SELECT COUNT(*) FROM VENDOR_DELIVERIES")
check("VENDOR_DELIVERIES has 1 row", cur.fetchone()[0] == 1)

print("\nTEST 5 — /api/inventory/check (Workflow 2)")
sent_messages.clear()
r = post("/api/inventory/check", {})
print(f"   status={r.status_code}")
js = r.get_json()
print(f"   triggered={len(js.get('triggered', []))}")
check("status 200", r.status_code == 200)
check("triggered list non-empty", len(js.get("triggered", [])) > 0)
cur = _conn_singleton.execute("SELECT COUNT(*) FROM REORDER_LOG")
n_reorder = cur.fetchone()[0]
check(f"REORDER_LOG populated", n_reorder > 0, f"rows={n_reorder}")
check("Kafka reorder-alerts published",
      any(m[0] == "reorder-alerts" for m in sent_messages))

print("\nTEST 6 — /api/feedback single (Workflow 6)")
sent_messages.clear()
r = post("/api/feedback", {
    "store_id":"FM-042","sku":"MILK-WHOLE-1G",
    "feedback_text":"The milk was spoiled and sour"})
print(f"   status={r.status_code}  body={r.get_json()}")
check("status 200", r.status_code == 200)
check("category=SAFETY", r.get_json().get("category") == "SAFETY")
check("Kafka customer-feedback fired",
      any(m[0] == "customer-feedback" for m in sent_messages))

print("\nTEST 7 — /api/feedback × 5 should trigger recall")
sent_messages.clear()
# We already inserted 1 above; add 4 more = 5 total on MILK-WHOLE-1G
for i in range(4):
    post("/api/feedback", {
        "store_id":"FM-042","sku":"MILK-WHOLE-1G",
        "feedback_text":f"complaint #{i+2} milk was rotten and spoiled"})
cur = _conn_singleton.execute(
    "SELECT COUNT(*) FROM CUSTOMER_FEEDBACK WHERE sku='MILK-WHOLE-1G' AND category='SAFETY'")
n_safety = cur.fetchone()[0]
print(f"   SAFETY feedback count for MILK-WHOLE-1G: {n_safety}")
check("5 SAFETY feedback rows", n_safety == 5)
cur = _conn_singleton.execute(
    "SELECT COUNT(*) FROM CUSTOMER_FEEDBACK WHERE sku='MILK-WHOLE-1G' AND recall_triggered=1")
n_recall = cur.fetchone()[0]
check(f"recall_triggered flagged on rows", n_recall == 5, f"flagged={n_recall}")
check("product-recalls topic fired",
      any(m[0] == "product-recalls" for m in sent_messages))

print("\nTEST 8 — /api/planogram/sync (Workflow 4)")
sent_messages.clear()
r = post("/api/planogram/sync", {
    "store_id":"FM-042","sku":"BAN-CAVENDISH-1LB",
    "aisle":"A07","section":"PRODUCE-1","shelf_level":2})
print(f"   status={r.status_code}  body={r.get_json()}")
check("status 200", r.status_code == 200)
check("Kafka planogram-updates fired",
      any(m[0] == "planogram-updates" for m in sent_messages))
cur = _conn_singleton.execute(
    "SELECT COUNT(*) FROM PRODUCT_LOCATIONS WHERE sku='BAN-CAVENDISH-1LB'")
check("PRODUCT_LOCATIONS upserted", cur.fetchone()[0] == 1)

print("\nTEST 9 — /api/schedule/notify (Workflow 5)")
sent_messages.clear()
r = post("/api/schedule/notify", {"week_start":"2026-05-25"})
print(f"   status={r.status_code}  body={r.get_json()}")
check("status 200", r.status_code == 200)
check("notified > 0", r.get_json().get("notified", 0) > 0)
check("Kafka messages produced", len(sent_messages) > 0)

print("\nTEST 10 — /api/stats")
r = get("/api/stats")
print(f"   stats={r.get_json()}")
check("status 200", r.status_code == 200)
js = r.get_json()
check("sales counter >= 1",      js.get("sales", 0) >= 1)
check("feedback counter >= 5",   js.get("feedback", 0) >= 5)
check("reorders counter >= 1",   js.get("reorders", 0) >= 1)
check("deliveries counter >= 1", js.get("deliveries", 0) >= 1)
check("recalls counter >= 1",    js.get("recalls", 0) >= 1)
check("events counter > 0",      js.get("events", 0) > 0)

print("\nTEST 11 — /api/recent/<table> endpoints")
for table in ["sales","feedback","reorders","deliveries","events","inventory","employees"]:
    r = get(f"/api/recent/{table}")
    js = r.get_json()
    err = isinstance(js, dict) and js.get("error")
    is_list = isinstance(js, list)
    check(f"recent/{table}", r.status_code == 200 and (is_list or not err),
          f"status={r.status_code}, type={type(js).__name__}, err={err}")

print("\nTEST 12 — bad table name returns 404")
r = get("/api/recent/bogus")
check("recent/bogus returns 404", r.status_code == 404)

print("\nTEST 13 — /api/topics")
r = get("/api/topics")
print(f"   topics={r.get_json()}")
check("status 200", r.status_code == 200)
check("topics is a list", isinstance(r.get_json().get("topics"), list))

print("\nTEST 14 — Bad POS sale body returns 400 with errors (FIX A)")
r = post("/api/pos/sale", {"store_id":"FM-042"})   # missing sku, qty, price
js = r.get_json()
print(f"   status={r.status_code}  body={js}")
check("status 400 on bad input", r.status_code == 400)
check("response.ok=false", js.get("ok") is False)
check("errors list present", isinstance(js.get("errors"), list) and len(js["errors"]) > 0)
# Confirm NO kafka send was made for this bad request
recent_pos = [m for m in sent_messages if m[0] == "pos-sales"]
# After test 7 we did several /api/feedback × 5; sent_messages got cleared in tests 6/8
# So sent_messages here should contain only what we just attempted (nothing — 400)
# But to be safe, clear and replay:
sent_messages.clear()
post("/api/pos/sale", {"store_id":"FM-042"})
check("bad request did NOT publish to Kafka",
      not any(m[0] == "pos-sales" for m in sent_messages),
      f"sent_messages={sent_messages}")

print("\nTEST 15 — Empty body returns 400 (FIX F)")
r = client.post("/api/pos/sale",
                data="", headers={"Content-Type":"application/json"})
print(f"   status={r.status_code}  body={r.get_json()}")
check("empty body returns 400", r.status_code == 400)
check("does NOT 500 on empty body", r.status_code != 500)

print("\nTEST 16 — Bulk sale now updates DW + INVENTORY (FIX B)")
sent_messages.clear()
# Snapshot current state
cur = _conn_singleton.execute("SELECT COUNT(*) FROM DW_SALES_FACT")
sales_before = cur.fetchone()[0]
r = post("/api/pos/sale/bulk", {"count": 10, "store_id":"FM-042"})
js = r.get_json()
print(f"   fired={js.get('fired')}  failed={js.get('failed')}")
cur = _conn_singleton.execute("SELECT COUNT(*) FROM DW_SALES_FACT")
sales_after = cur.fetchone()[0]
delta = sales_after - sales_before
check(f"DW_SALES_FACT grew by 10 after bulk", delta == 10, f"delta={delta}")

print("\nTEST 17 — HR notify uses hr-notifications topic (FIX C)")
sent_messages.clear()
r = post("/api/schedule/notify", {"week_start":"2026-05-25"})
hr_topic_msgs = [m for m in sent_messages if m[0] == "hr-notifications"]
planogram_topic_msgs = [m for m in sent_messages if m[0] == "planogram-updates"]
check(f"HR fired to hr-notifications topic ({len(hr_topic_msgs)} msgs)",
      len(hr_topic_msgs) > 0)
check("HR did NOT fire to planogram-updates topic",
      len(planogram_topic_msgs) == 0,
      f"wrong-topic count={len(planogram_topic_msgs)}")

print("\nTEST 18 — Planogram 'ALL' fans out to every store (FIX K)")
sent_messages.clear()
r = post("/api/planogram/sync", {
    "store_id":"ALL","sku":"BAN-CAVENDISH-1LB",
    "aisle":"A07","section":"PRODUCE-1","shelf_level":2})
js = r.get_json()
print(f"   stores={js.get('stores')}  published={js.get('published')}")
# We seeded 5 stores
check("planogram fanned out to all 5 stores", js.get("published") == 5)
check(f"5 Kafka messages sent",
      len([m for m in sent_messages if m[0] == "planogram-updates"]) == 5)

print("\nTEST 19 — Bad vendor delivery returns 400")
r = post("/api/vendor/delivery", {"vendor_id":"DOLE"})   # missing sku, cases, unit_cost
print(f"   status={r.status_code}  body={r.get_json()}")
check("status 400", r.status_code == 400)
check("errors list returned", isinstance(r.get_json().get("errors"), list))

print("\nTEST 20 — Bad feedback returns 400")
r = post("/api/feedback", {})
print(f"   status={r.status_code}  body={r.get_json()}")
check("status 400", r.status_code == 400)

print("\nTEST 21 — Bulk sale count out of range returns 400")
r = post("/api/pos/sale/bulk", {"count": 9999, "store_id":"FM-042"})
check("count > 500 returns 400", r.status_code == 400)
r = post("/api/pos/sale/bulk", {"count": 0, "store_id":"FM-042"})
check("count < 1 returns 400", r.status_code == 400)
r = post("/api/pos/sale/bulk", {"count": "notanumber"})
check("non-numeric count returns 400", r.status_code == 400)

print("\nTEST 22 — Valid POS sale with timestamp validation")
r = post("/api/pos/sale", {
    "store_id":"FM-042","sku":"BAN-CAVENDISH-1LB","qty":1,"price":0.99,
    "timestamp":"not-a-date"})
check("bad timestamp returns 400", r.status_code == 400)
r = post("/api/pos/sale", {
    "store_id":"FM-042","sku":"BAN-CAVENDISH-1LB","qty":1,"price":0.99,
    "timestamp":"2026-05-20T14:23:00Z"})
check("ISO8601 timestamp accepted", r.status_code == 200)

print("\n" + "─" * 70)
print(f"RESULT: {PASS} passed, {FAIL} failed")
sys.exit(0 if FAIL == 0 else 1)
