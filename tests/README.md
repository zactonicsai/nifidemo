# POS Simulator Test Harness

This is an **offline** test suite that exercises every endpoint of
`pos-simulator/app.py` without needing Docker, Kafka, or Postgres running.

It mocks Kafka (capturing all `producer.send()` calls) and swaps `psycopg2`
for a SQLite-backed shim that runs the project's real `sql/init.sql` and
`sql/seed.sql`. The Flask app is then driven via its `test_client()`.

## Running

```bash
pip install flask flask-cors
python3 tests/test_pos_simulator.py
```

Expected output ends with `RESULT: 64 passed, 0 failed`.

## What it covers

- All 10 REST endpoints (`/api/health`, `/api/pos/sale`, `/api/pos/sale/bulk`,
  `/api/vendor/delivery`, `/api/feedback`, `/api/inventory/check`,
  `/api/schedule/notify`, `/api/planogram/sync`, `/api/stats`,
  `/api/recent/<table>`, `/api/topics`).
- All 6 workflows from the FreshMart reference document.
- Input validation (missing fields, wrong types, out-of-range, empty body).
- Auto-recall trigger at 5+ SAFETY feedback rows.
- Bulk inventory + DW writes.
- Planogram fan-out to all stores when `store_id == 'ALL'`.
- HR notify uses the correct `hr-notifications` topic.
