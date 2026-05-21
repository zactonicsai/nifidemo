# FreshMart Grocery — Apache NiFi Demo Stack

A complete, runnable demonstration of an enterprise grocery data pipeline built around **Apache NiFi 2.7**, **Apache Kafka 7.7** (KRaft mode, no ZooKeeper), **PostgreSQL 17**, and **LocalStack 3.8** for AWS SQS / SNS / S3 emulation — driven through an **IBM Carbon-style web dashboard** (HTML + Tailwind + JavaScript on a blue-on-white IBM palette).

The dashboard lets you fire every workflow described in the FreshMart reference document — POS sales, inventory reorder, vendor CSV ingestion, planogram broadcast, HR scheduling, and customer-feedback recall detection — and watch the pipeline come alive in real time.

---

## Table of Contents

1. [Architecture at a glance](#1-architecture-at-a-glance)
2. [Directory structure](#2-directory-structure)
3. [Service-by-service explanation](#3-service-by-service-explanation)
4. [Workflows / scenarios / roles](#4-workflows--scenarios--roles)
5. [Quick start](#5-quick-start)
6. [How to test — every workflow, every role](#6-how-to-test--every-workflow-every-role)
7. [Inspecting what happened](#7-inspecting-what-happened)
8. [`docker-compose.yml` — line by line](#8-docker-composeyml--line-by-line)
9. [Dashboard — line by line](#9-dashboard--line-by-line)
10. [POS simulator — endpoint by endpoint](#10-pos-simulator--endpoint-by-endpoint)
11. [Go validator — function by function](#11-go-validator--function-by-function)
12. [Database schema reference](#12-database-schema-reference)
13. [Static seed data](#13-static-seed-data)
14. [Troubleshooting](#14-troubleshooting)
15. [Tear-down](#15-tear-down)

---

## 1. Architecture at a glance

```
                ┌──────────────────────────────────────────────────────┐
                │            DASHBOARD  (HTML+Tailwind+JS)             │
                │   http://localhost:8000   IBM blue on white theme    │
                │   ↓ /api/* (proxied by nginx)                        │
                └──────────────────────────┬───────────────────────────┘
                                           │
                ┌──────────────────────────▼───────────────────────────┐
                │         POS SIMULATOR / EVENT GATEWAY                │
                │         Flask · port 9090                            │
                │   POST /api/pos/sale       → Kafka pos-sales         │
                │   POST /api/vendor/delivery→ Kafka vendor-deliveries │
                │   POST /api/feedback       → Kafka customer-feedback │
                │   POST /api/inventory/check→ Kafka reorder-alerts    │
                │   POST /api/planogram/sync → Kafka planogram-updates │
                │   POST /api/schedule/notify→ HR notifications        │
                └──┬──────────────────────┬──────────────────────┬─────┘
                   │                      │                      │
        ┌──────────▼──────────┐  ┌────────▼────────┐  ┌──────────▼──────────┐
        │   APACHE KAFKA 7.7  │  │  POSTGRESQL 17  │  │     LOCALSTACK      │
        │   (KRaft, port 9092)│  │  (port 5432)    │  │  SQS / SNS / S3     │
        │   8 topics          │  │  9 tables       │  │  (port 4566)        │
        └──────────┬──────────┘  └────────┬────────┘  └──────────┬──────────┘
                   │                      │                      │
                   └──────────────────────┼──────────────────────┘
                                          │
                              ┌───────────▼───────────┐
                              │     APACHE NIFI 2.7    │
                              │  https://localhost:8443│
                              │  6 process groups      │
                              │   1. POS Sales         │
                              │   2. Inventory Reorder │
                              │   3. Vendor CSV        │
                              │   4. Planogram SNS     │
                              │   5. HR Schedule       │
                              │   6. Feedback / Recall │
                              └───────────┬────────────┘
                                          │ InvokeHTTP
                                          ▼
                              ┌─────────────────────┐
                              │   GO VALIDATOR      │
                              │   port 8080         │
                              │   schema validation │
                              └─────────────────────┘
```

| Service        | Image                           | Host port | Role                                     |
| -------------- | ------------------------------- | --------- | ---------------------------------------- |
| `dashboard`    | `nginx:1.27-alpine`             | 8000      | Web UI · proxies `/api/*` to pos-simulator |
| `pos-simulator`| Python 3.12 + Flask             | 9090      | Event gateway, the only writer to Kafka  |
| `nifi`         | `apache/nifi:2.7.0`             | 8443      | Visual data pipelines                    |
| `kafka`        | `confluentinc/cp-kafka:7.7.1`   | 9092      | Event bus (KRaft, no ZK)                 |
| `kafka-init`   | same                            | —         | One-shot topic creator                   |
| `kafka-ui`     | `provectuslabs/kafka-ui:latest` | 8081      | Inspect topics                           |
| `postgres`     | `postgres:17-alpine`            | 5432      | Data warehouse                           |
| `pgadmin`      | `dpage/pgadmin4:latest`         | 8082      | Inspect/query the DB                     |
| `localstack`   | `localstack/localstack:3.8`     | 4566      | AWS SQS / SNS / S3 emulation             |
| `go-validator` | Go 1.23 multi-stage             | 8080      | Schema validation called by NiFi         |

---

## 2. Directory structure

```
freshmart-nifi/
├── docker-compose.yml              # all services, latest images
├── .env.example                    # per-env overrides
├── README.md                       # this file
│
├── sql/
│   ├── init.sql                    # schema: 9 tables + indexes
│   └── seed.sql                    # 5 stores, 10 products, 8 employees, 12 inventory rows
│
├── scripts/
│   ├── localstack-init.sh          # creates SQS queues, SNS topics, S3 buckets
│   ├── pgadmin-servers.json        # pre-wires pgAdmin to postgres
│   ├── smoke-test.sh               # end-to-end pipeline smoke test
│   └── dev.sh                      # up|down|reset|logs|psql|kafka-topics
│
├── dashboard/                      # IBM-style web UI
│   ├── index.html                  # 7 role tabs · 7 KPI tiles · live logs
│   ├── app.js                      # role switching · form handlers · 4-sec polling
│   └── nginx.conf                  # /api/* → pos-simulator
│
├── pos-simulator/                  # Flask event gateway
│   ├── app.py                      # 10 REST endpoints
│   ├── requirements.txt
│   └── Dockerfile
│
├── go-validator/                   # Go microservice
│   ├── main.go                     # /health · /validate · /metrics
│   ├── go.mod  go.sum
│   └── Dockerfile                  # multi-stage scratch image
│
├── flows/
│   └── freshmart-flows-reference.json  # blueprint for building NiFi process groups
│
├── static-data/                    # static JSON catalog data
│   ├── products/product_catalog.json
│   ├── stores/stores.json
│   └── employees/employees.json
│
├── test-data/                      # sample CSV/JSON events
│   ├── DOLE_20241101_delivery.csv
│   ├── NESTLE_20241101_delivery.csv
│   ├── pos_sales_batch.json
│   ├── customer_feedback.json
│   └── planogram_update.json
│
└── vendor-data/                    # SFTP drop folder watched by NiFi
```

---

## 3. Service-by-service explanation

### 3.1 `nifi` — Apache NiFi 2.7

Visual data pipeline platform. We expose the HTTPS UI on **8443**. On first boot the user is `admin` / `FreshMart2024Secret!`. Volumes persist data, logs, conf, and bind-mount your local `./flows`, `./vendor-data`, `./static-data`, and `./test-data` into the container so processors can read them.

### 3.2 `kafka` — Confluent Kafka 7.7 (KRaft mode)

Modern Kafka no longer needs ZooKeeper. We run a single broker that is also its own controller (`KAFKA_PROCESS_ROLES: broker,controller`). Two listeners:
- `PLAINTEXT://kafka:29092` — for other containers on the `freshmart-net` Docker network
- `EXTERNAL://localhost:9092` — for any client running on your host machine

### 3.3 `kafka-init` — One-shot topic bootstrapper

After `kafka` is healthy, this container creates 8 topics (`pos-sales`, `vendor-deliveries`, `customer-feedback`, `reorder-alerts`, `planogram-updates`, `product-recalls`, `inventory-updates`, `dead-letter-queue`), prints the list, and exits. Idempotent: rerun-safe.

### 3.4 `postgres` — FreshMart Data Warehouse

PostgreSQL 17 (Alpine). `sql/init.sql` defines the schema, `sql/seed.sql` populates stores/products/employees/inventory. Docker's `docker-entrypoint-initdb.d` mechanism runs both on first boot only — wipe with `docker compose down -v` to reseed.

### 3.5 `localstack` — AWS SQS, SNS, S3

Free, local emulation of AWS. The init script `scripts/localstack-init.sh` is mounted into `/etc/localstack/init/ready.d/` and runs once when LocalStack is ready, creating:
- 7 SQS queues (including 2 FIFO + a DLQ)
- 2 SNS topics (`freshmart-product-recalls`, `freshmart-planogram-updates`)
- SNS → SQS fan-out subscriptions
- 3 S3 buckets

### 3.6 `go-validator` — Schema validation microservice

Tiny Go service that NiFi calls with `InvokeHTTP` to validate a JSON payload. Cross-references SKU against `PRODUCT_CATALOG`. Exposes `/health` (used by Docker healthcheck), `/validate` (POST), `/metrics` (GET — counts for the dashboard).

### 3.7 `pos-simulator` — Event gateway

This is the heart of the demo's UX. The dashboard is a static SPA — every action it takes lands here, and we then publish to Kafka, write to PostgreSQL, and audit-log the event. Why two writes? So the dashboard reflects activity *even before* you've wired up the NiFi flows, then NiFi can additionally consume the same Kafka topics for full pipeline behaviour.

### 3.8 `dashboard` — Web UI

Nginx serves `index.html` + `app.js`. The Nginx config (`dashboard/nginx.conf`) proxies any `/api/*` request to `pos-simulator:9090` on the internal network — so the browser never needs to know about CORS or the simulator's port.

### 3.9 `kafka-ui` — Topic inspector

Provectus's web UI at **http://localhost:8081**. Shows brokers, topics, partitions, consumer groups, and lets you produce/consume.

### 3.10 `pgadmin` — Database UI

pgAdmin 4 at **http://localhost:8082**. Pre-configured (via `scripts/pgadmin-servers.json`) to connect to the `postgres` container. Login: `admin@freshmart.local` / `FreshMart2024!`.

---

## 4. Workflows / scenarios / roles

All six workflows from the FreshMart document are implemented and triggerable from the dashboard.

| # | Workflow                          | Role tab    | Endpoint                  | Kafka topic         | DB tables written           |
| - | --------------------------------- | ----------- | ------------------------- | ------------------- | --------------------------- |
| 1 | POS Sales: Register → DB → Kafka  | **Cashier** | `POST /api/pos/sale`      | `pos-sales`         | `DW_SALES_FACT`, `INVENTORY`|
| 2 | Inventory tracking & auto-reorder | **Manager** | `POST /api/inventory/check`| `reorder-alerts`   | `REORDER_LOG`               |
| 3 | Vendor CSV ingestion (SFTP)       | **Vendor**  | `POST /api/vendor/delivery`| `vendor-deliveries`| `VENDOR_DELIVERIES`         |
| 4 | Planogram sync (SNS fan-out)      | **Ops**     | `POST /api/planogram/sync`| `planogram-updates` | `PRODUCT_LOCATIONS`         |
| 5 | Staff scheduling & HR sync        | **HR**      | `POST /api/schedule/notify`| `planogram-updates`| (Kafka only by default)     |
| 6 | Customer feedback & recall        | **Customer**| `POST /api/feedback`      | `customer-feedback` + `product-recalls` on auto-trigger | `CUSTOMER_FEEDBACK` |

The **Kafka Inspector** tab lets you peek raw messages from any topic. The **Ops** tab also has a one-click "Run Full Pipeline Demo" button that fires every workflow in sequence.

### Roles modeled

| Role           | What they do in the demo                                                              |
| -------------- | ------------------------------------------------------------------------------------- |
| Cashier        | Scans items at the POS register — fires sale events into the pipeline.                |
| Store Manager  | Monitors stock levels, manually triggers reorder sweeps, sees the reorder log build up.|
| Vendor         | Submits delivery rows that NiFi maps from vendor SKU → FreshMart SKU.                 |
| Customer       | Submits feedback. Repeated SAFETY complaints auto-trigger a product recall.           |
| HR             | Pushes weekly shift notifications to all employees in the roster.                     |
| Operations / HQ| Broadcasts planogram updates to all stores via SNS fan-out. Runs the full demo.       |

---

## 5. Quick start

### Requirements

- Docker Desktop / Docker Engine 24+
- Docker Compose v2 (`docker compose` not `docker-compose`)
- ~8 GB of free RAM (NiFi gets 2 GB on its own)
- Free ports: 4566, 5432, 8000, 8080, 8081, 8082, 8443, 9090, 9092

### Steps

```bash
# 1. Extract this archive and enter the directory
cd freshmart-nifi

# 2. Make scripts executable (one-time)
chmod +x scripts/*.sh

# 3. Build and start everything (first run downloads ~2 GB of images)
docker compose up -d --build

# 4. Watch the slow starter — NiFi takes ~90 seconds to fully boot
docker compose logs -f nifi | grep -i "started"

# 5. Open the dashboard
open http://localhost:8000          # macOS
# OR  xdg-open http://localhost:8000  # Linux
# OR  start  http://localhost:8000    # Windows
```

You should see a dark IBM header, KPI tiles starting at `—` or `0`, and the **Cashier** tab pre-selected.

### One-line everything check

```bash
bash scripts/smoke-test.sh
```

This curls every endpoint, then prints `stats` and topic counts at the end. If all 10 steps print results without errors, the stack is healthy.

### Convenience commands

```bash
./scripts/dev.sh up            # build + start
./scripts/dev.sh down          # stop (keep volumes)
./scripts/dev.sh reset         # stop + wipe all data
./scripts/dev.sh logs nifi     # tail a service
./scripts/dev.sh psql          # open psql shell in postgres
./scripts/dev.sh kafka-topics  # list topics
./scripts/dev.sh kafka-peek pos-sales   # peek 10 messages from a topic
./scripts/dev.sh sqs-list      # list LocalStack SQS queues
./scripts/dev.sh smoke         # run the smoke test
```

---

## 6. How to test — every workflow, every role

### From the dashboard (recommended)

1. Open **http://localhost:8000**.
2. Click each role tab and use its form/buttons:

| Tab            | What to do                                                                                                              |
| -------------- | ----------------------------------------------------------------------------------------------------------------------- |
| **Cashier**    | Click **Scan & Send Event** (single sale) and **Fire 25 Random Sales** (burst).                                         |
| **Manager**    | Click **Run Inventory Sweep** — sees the low-stock SKUs (highlighted red in the table) get reorder rows.                |
| **Vendor**     | Submit a delivery — picks SKU, cases, unit cost. Lands in `VENDOR_DELIVERIES` and Kafka `vendor-deliveries`.            |
| **Customer**   | Type a complaint with words like *spoiled, sick, rotten* and submit. Then click **Fire 5 SAFETY → Trigger Recall** to auto-fire 5 SAFETY complaints on the same SKU and watch the recall banner appear. |
| **HR**         | Pick a Monday date, click **Push Weekly Notifications**.                                                                |
| **Operations** | Submit a planogram update. Then click **▶ Run Full Pipeline Demo** to fire all 6 workflows in sequence.                  |
| **Kafka Inspector** | Choose a topic, click **Peek** to see the last 10 messages.                                                       |

KPI tiles refresh every 4 seconds. Live log panels (right side of every tab) tail the corresponding table.

### From `curl`

```bash
# Single POS sale (Workflow 1)
curl -X POST http://localhost:8000/api/pos/sale \
  -H "Content-Type: application/json" \
  -d '{"store_id":"FM-042","sku":"BAN-CAVENDISH-1LB","qty":3,"price":0.99,"cashier_id":"EMP-1147"}'

# Vendor delivery (Workflow 3)
curl -X POST http://localhost:8000/api/vendor/delivery \
  -H "Content-Type: application/json" \
  -d '{"vendor_id":"DOLE","sku":"BAN-CAVENDISH-1LB","cases":240,"unit_cost":0.28}'

# Inventory sweep (Workflow 2)
curl -X POST http://localhost:8000/api/inventory/check -H "Content-Type: application/json" -d '{}'

# Customer feedback (Workflow 6)
curl -X POST http://localhost:8000/api/feedback \
  -H "Content-Type: application/json" \
  -d '{"store_id":"FM-042","sku":"MILK-WHOLE-1G","feedback_text":"The milk was spoiled and sour"}'
```

### From the NiFi UI

1. Open **https://localhost:8443/nifi** (accept the self-signed cert).
2. Login: `admin` / `FreshMart2024Secret!`.
3. Drag a `ConsumeKafka` processor onto the canvas; set Brokers `kafka:29092`, Topic `pos-sales`. Start it.
4. Drag a `LogAttribute` after it. You should see your sales arriving from the dashboard, live.
5. Use `flows/freshmart-flows-reference.json` as your processor blueprint for building out each of the six workflows.

### Dropping a CSV directly for NiFi to ingest (Workflow 3 SFTP-style)

```bash
cp test-data/DOLE_20241101_delivery.csv vendor-data/
```

If you've configured a NiFi `GetFile` processor on `/sftp/vendor/incoming` (the `vendor-data/` host folder is bind-mounted there), it'll pick the file up.

---

## 7. Inspecting what happened

### Kafka topics from the CLI

```bash
# List topics
docker exec freshmart-kafka kafka-topics --bootstrap-server localhost:29092 --list

# Tail a topic
docker exec freshmart-kafka kafka-console-consumer \
  --bootstrap-server localhost:29092 --topic pos-sales --from-beginning --max-messages 10
```

### Postgres from the CLI

```bash
docker exec -it freshmart-postgres psql -U nifi -d freshmart_dw

freshmart_dw=# SELECT store_id, sku, qty, unit_price FROM DW_SALES_FACT ORDER BY id DESC LIMIT 10;
freshmart_dw=# SELECT * FROM REORDER_LOG;
freshmart_dw=# SELECT event_type, count(*) FROM EVENT_LOG GROUP BY event_type;
```

### SQS from the CLI

```bash
docker exec freshmart-localstack awslocal sqs list-queues
docker exec freshmart-localstack awslocal sqs receive-message \
  --queue-url http://localhost:4566/000000000000/freshmart-reorder-alerts.fifo
```

### Web UIs

| URL                              | Use                                              |
| -------------------------------- | ------------------------------------------------ |
| http://localhost:8000            | The FreshMart dashboard                          |
| https://localhost:8443/nifi      | NiFi visual designer (admin / FreshMart2024Secret!) |
| http://localhost:8081            | Kafka UI — topics, partitions, messages          |
| http://localhost:8082            | pgAdmin — databases, tables, queries             |
| http://localhost:8080/health     | Go validator status                              |
| http://localhost:9090/api/health | POS simulator status                             |

---

## 8. `docker-compose.yml` — line by line

This is one of the longer files; every block matters. Here's what each section does.

### Service: `nifi`

```yaml
nifi:
  image: apache/nifi:2.7.0          # latest stable NiFi as of May 2026
  container_name: freshmart-nifi    # stable name for `docker exec`
  ports:
    - "8443:8443"                    # NiFi HTTPS UI exposed on host
  environment:
    SINGLE_USER_CREDENTIALS_USERNAME: admin              # single-user auth mode
    SINGLE_USER_CREDENTIALS_PASSWORD: FreshMart2024Secret!   # ≥ 12 chars required
    NIFI_WEB_HTTPS_PORT: 8443                            # inside-container port
    NIFI_WEB_PROXY_HOST: "localhost:8443,nifi:8443"      # allowed Host headers
    NIFI_JVM_HEAP_INIT: 1g
    NIFI_JVM_HEAP_MAX: 2g                                # heap ceiling
  volumes:
    - nifi-data:/opt/nifi/nifi-current/data              # FlowFile content repo
    - nifi-logs:/opt/nifi/nifi-current/logs              # nifi-app.log
    - nifi-conf:/opt/nifi/nifi-current/conf              # flow.json.gz
    - ./flows:/opt/nifi/nifi-current/flow-archive        # your flow exports
    - ./vendor-data:/sftp/vendor/incoming                # CSV drop folder
    - ./static-data:/opt/freshmart/static                # catalog lookups
    - ./test-data:/opt/freshmart/test-data               # sample events
  depends_on:
    kafka:    { condition: service_healthy }             # wait for Kafka
    postgres: { condition: service_healthy }             # wait for DB
    localstack: { condition: service_started }
  networks: [freshmart]
  healthcheck:
    test: ["CMD", "curl", "-f", "-k", "https://localhost:8443/nifi-api/system-diagnostics"]
    interval: 30s
    timeout: 10s
    retries: 10
    start_period: 90s                                    # NiFi is slow to start
```

### Service: `kafka` (KRaft mode)

```yaml
kafka:
  image: confluentinc/cp-kafka:7.7.1
  ports:
    - "9092:9092"                    # external client port
  environment:
    KAFKA_NODE_ID: 1                 # broker AND controller node id
    KAFKA_PROCESS_ROLES: "broker,controller"
    KAFKA_CONTROLLER_QUORUM_VOTERS: "1@kafka:9093"        # KRaft quorum
    KAFKA_LISTENERS: "PLAINTEXT://0.0.0.0:29092,CONTROLLER://0.0.0.0:9093,EXTERNAL://0.0.0.0:9092"
    KAFKA_ADVERTISED_LISTENERS: "PLAINTEXT://kafka:29092,EXTERNAL://localhost:9092"
    KAFKA_LISTENER_SECURITY_PROTOCOL_MAP: "PLAINTEXT:PLAINTEXT,CONTROLLER:PLAINTEXT,EXTERNAL:PLAINTEXT"
    KAFKA_CONTROLLER_LISTENER_NAMES: "CONTROLLER"
    KAFKA_INTER_BROKER_LISTENER_NAME: "PLAINTEXT"
    KAFKA_AUTO_CREATE_TOPICS_ENABLE: "true"               # let NiFi auto-create
    KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR: 1             # single-broker setup
    KAFKA_MESSAGE_MAX_BYTES: 10485760                     # 10 MB max payload
    CLUSTER_ID: "FreshMart-KRaft-Cluster-01"              # required in KRaft
```

The two listener names (`PLAINTEXT` internal, `EXTERNAL` for the host) is the trick that lets containers reach Kafka at `kafka:29092` while your laptop reaches it at `localhost:9092`.

### Service: `kafka-init`

A one-shot helper. It runs `kafka-topics --create --if-not-exists` for every topic, then exits. `depends_on: { kafka: condition: service_healthy }` guarantees it only fires after Kafka is healthy.

### Service: `postgres`

The init script runs in order: `01-init.sql` (schema) then `02-seed.sql` (data). `pg_isready` healthcheck makes other services wait on it.

### Service: `localstack`

`SERVICES: "sqs,sns,s3"` keeps the boot footprint small. Mounting our script as `/etc/localstack/init/ready.d/init.sh:ro` triggers LocalStack's "init hooks" — it runs the script once when the API is ready.

### Service: `go-validator`

Builds from `./go-validator/Dockerfile` (multi-stage). The `depends_on: { postgres: condition: service_healthy }` plus the in-app retry loop (30 attempts × 2 sec) handles the cold-start race against Postgres.

### Service: `pos-simulator`

Same pattern — builds from its own Dockerfile, depends on healthy Kafka and Postgres. Exposes port 9090 so you can hit it directly with curl if you bypass the dashboard.

### Service: `dashboard`

A pure nginx static-file server. Its only smart bit is the bind-mounted `nginx.conf` that proxies `/api/*` to `pos-simulator:9090`. This eliminates CORS issues entirely — the browser thinks both the UI and the API live at `localhost:8000`.

### Networks and Volumes

A single bridge network `freshmart-net` lets every container talk to every other container by name. Seven named volumes persist data across restarts (`docker compose down`) but are deleted by `docker compose down -v`.

---

## 9. Dashboard — line by line

### `dashboard/index.html`

The dashboard is **one HTML file with Tailwind via the Play CDN**. No build step. Reading it top to bottom:

**Lines 1–9 — Document head.** `<meta viewport>` for responsive scaling, then the Tailwind CDN script, then preconnects to Google Fonts to speed up the IBM Plex load.

**Lines 11–13 — IBM Plex font load.** IBM's official open-source typeface family. We pull three faces: Sans (300/400/500/600/700), Mono (400/500/600), and Serif (the IBM Carbon design system uses all three).

**Lines 15–47 — Tailwind config block.** Inline `tailwind.config = {...}` configures custom utility names:
- `font-sans`, `font-mono`, `font-serif` override Tailwind defaults with IBM Plex.
- The `colors.ibm.*` palette mirrors IBM Carbon Design v11: `blue: #0f62fe` is IBM's signature interactive blue, `gray10` through `gray90` is the standard neutral ramp, and `red: #da1e28` is the Carbon "danger" red used for the recall banner.

**Lines 49–73 — Custom CSS.** Five things worth noting:
- `.ibm-card { border: 1px solid #e0e0e0; }` — IBM uses sharp 1-pixel borders, never shadows.
- `.ibm-tile` adds a 4-pixel blue left bar — the Carbon "data tile" pattern.
- `.log-scroll::-webkit-scrollbar` is a slim 8-pixel scrollbar so the log panels feel monospace-clean.
- The `@keyframes ibm-pulse` powers the "live" status dots in the header.
- `.tab-active { box-shadow: inset 0 -3px 0 #0f62fe; }` is the Carbon active-tab indicator — a 3-pixel inset bottom border.

**Lines 79–115 — Top header.** Two layers:
- Dark `bg-ibm-black` shell with the "FM" logo block, breadcrumb, and right-aligned mono status indicators (KAFKA · POSTGRES · NIFI). The colored dot for each comes from `app.js`.
- White sub-header with page title and a one-line description.

**Lines 117–148 — KPI tile row.** Seven `.ibm-tile` cards in a CSS grid. Each card has a colored left bar (blue for default, red for recalls, yellow for low-stock, green for the all-events counter). The `id="stat-*"` divs are populated by `refreshStats()` in JS every 4 seconds.

**Lines 150–161 — Role tab nav.** Seven `<button>` elements with `data-role` attributes — JS reads that to switch panels.

**Lines 165 onward — Role panels.** Each role has a `<section data-panel="...">`. Only one is visible at a time (others get the Tailwind `hidden` class via JS). Common pattern per panel:
- Left column (2/3 width): the action form with sharp `border-ibm-gray30` inputs and an `bg-ibm-blue` submit button.
- Right column (1/3 width): a live log feed of recent items related to the workflow.

**Lines 425–428 — Toast stack.** Fixed-positioned `bottom-6 right-6` div where `toast()` in JS appends notifications. They auto-remove after 4.5 seconds.

**Lines 431–442 — Footer.** Quick links to the four backing UIs (NiFi / Kafka / pgAdmin / Validator).

### `dashboard/app.js`

**Lines 12–14 — Constants.** `API = '/api'` (proxied by nginx), `POLL_MS = 4000` (refresh cadence).

**Lines 19–32 — `toast(msg, kind)`.** Builds an IBM-style notification: a left-bar color (green/red/blue based on `kind`), uppercase mono label, then the message. Appends to `#toast-stack`, removes after 4.5 sec.

**Lines 37–48 — `postJSON` and `getJSON`.** Minimal `fetch()` wrappers that throw on non-2xx. Used everywhere instead of repeating header boilerplate.

**Lines 50–58 — `formToJson(form)`.** Walks a `FormData`, coerces number inputs (`type=number`) to JS numbers so the JSON sent to the backend has the right types.

**Lines 63–73 — `switchRole(role)`.** Toggles `.tab-active` on buttons and `.hidden` on `<section>` panels. Saves choice to `localStorage.fm-role` so a reload remembers the last tab.

**Lines 79–87 — Workflow 1 (single sale) form handler.** Submits the form → posts to `/api/pos/sale` → shows toast → calls `refreshAll()` to update the KPIs and recent-list.

**Lines 89–96 — Workflow 1 (bulk burst) button.** Sends `{ count: 25 }` for a 25-sale burst to the same store.

**Lines 99–105 — Workflow 2 (inventory sweep) button.** Calls `/api/inventory/check`. The response includes the array of triggered reorders; we just show the count in the toast.

**Lines 108–115 — Workflow 3 (vendor delivery) form.** Standard form submit → `/api/vendor/delivery`.

**Lines 118–125 — Workflow 6 (single feedback).** Important detail: the backend classifies the feedback as `SAFETY` or `GENERAL` and returns the category. We tint the toast red if it's SAFETY.

**Lines 127–136 — Workflow 6 (auto-recall test).** Sequentially fires 5 SAFETY feedbacks on `MILK-WHOLE-1G`. The backend counts SAFETY-category complaints in the last hour per SKU; on the 5th it sets `recall_triggered=true` and publishes to the `product-recalls` topic.

**Lines 139–148 — Workflow 5 (HR notify) form.** The date input defaults to today on page load (line 140). On submit it posts to `/api/schedule/notify`, which fires one Kafka message per employee in the roster.

**Lines 151–159 — Workflow 4 (planogram) form.** Builds the JSON from form fields, posts to `/api/planogram/sync`.

**Lines 162–175 — One-click full demo button.** Awaits 6 sequential POST calls — sales burst, vendor delivery, inventory sweep, planogram, HR notify, recall feedback. Useful for screen recordings.

**Lines 181–204 — Kafka inspector.** `loadTopics()` populates the dropdown from `/api/topics`; the **Peek** button calls `/api/topics/<topic>/peek` and renders the 10 most recent messages in a `<pre>` block.

**Lines 211–219 — `refreshStats()`.** Pulls `/api/stats` (a flat JSON object), then for each known key writes the count into the matching `#stat-*` element.

**Lines 226–293 — `refreshRecent()`.** The big render function. Fetches in parallel: sales, reorders, deliveries, feedback, events, inventory, employees. For each, it builds little IBM-style left-bordered log rows. Feedback rows that triggered a recall get a red border + ⚠ RECALL badge. Inventory rows below threshold get a light-red background tint.

**Lines 297–315 — `refreshHealth()`.** Pings `/api/health` and uses the returned Kafka/Postgres status to recolor the small dots in the header. NiFi is special: we attempt a `no-cors` fetch against `https://localhost:8443/nifi/`; if it doesn't throw we mark it green, otherwise yellow (the self-signed cert makes a precise check impossible from JS).

**Lines 321–326 — Boot.** Restores the last-used role tab, kicks off an initial refresh + health check + topic load, then schedules the two polling loops (4 sec for stats/recent, 10 sec for health).

### `dashboard/nginx.conf`

Two location blocks:
- `location /` — serve static files, fall back to `index.html` for SPA-style routing.
- `location /api/` — `proxy_pass http://pos-simulator:9090;` plus standard forwarding headers. This is the entire reason the dashboard doesn't need CORS configuration.

---

## 10. POS simulator — endpoint by endpoint

`pos-simulator/app.py` is a Flask service. Reading top to bottom:

**Imports + config (lines 23–40).** Standard Flask + flask-cors + kafka-python + psycopg2. Pulls Kafka brokers and Postgres connection info from env vars set by docker-compose.

**`producer()` (lines 47–67).** Lazy singleton: on first call, retries the Kafka connection up to 20 times (3 seconds between attempts) because Kafka may still be coming up when this container starts. After connect, the producer is held for the life of the process. We use `acks="all"` (durability) and `gzip` compression.

**`pg()` (lines 70–74).** Opens a fresh psycopg2 connection per request. For a demo this is fine; production would use a pool.

**`audit(event_type, source, payload)` (lines 77–85).** Writes a row to `EVENT_LOG` with the action type, who triggered it, and the full payload as JSONB. Every endpoint calls this so you have a single audit table to query.

**`/api/health` (lines 95–106).** Returns `{kafka, postgres, ts}` statuses. The dashboard hits this every 10 seconds to recolor its header dots.

**`/api/pos/sale` (lines 109–146) — Workflow 1.** Accepts `{ store_id, sku, qty, price, cashier_id, timestamp? }`. Publishes to Kafka topic `pos-sales` keyed by store_id (so all sales for one store land in the same partition, preserving order). Then directly inserts into `DW_SALES_FACT` and decrements `INVENTORY.qty`. The DB write is intentional duplication: it makes the dashboard show activity *before* NiFi has been wired up. Once you build a NiFi flow that consumes `pos-sales` and inserts to `DW_SALES_FACT`, you'll get two rows per sale — fine for demo, easy to disable.

**`/api/pos/sale/bulk` (lines 149–168).** Fires N random sales (default 25). Uses a hard-coded list of common SKUs and three cashier IDs so the data looks realistic.

**`/api/vendor/delivery` (lines 171–197) — Workflow 3.** Publishes to `vendor-deliveries` keyed by vendor_id, inserts to `VENDOR_DELIVERIES`.

**`/api/feedback` (lines 200–248) — Workflow 6.** This one has logic: it scans the feedback text for SAFETY keywords (`spoiled, sick, recall, rotten, mold, expired`). If it finds one, it sets `category=SAFETY`. After insert, if there are 5+ SAFETY rows on the same SKU in the last hour, it sets `recall_triggered=TRUE` on all of them and publishes to the `product-recalls` topic. This mirrors what the ExecuteGroovyScript processor in the document does — but in Python, so you can test the behavior without building NiFi flows first.

**`/api/inventory/check` (lines 251–286) — Workflow 2.** Queries `INVENTORY WHERE qty < reorder_threshold`, generates a reorder message for each row, publishes to `reorder-alerts` keyed by store_id, and inserts to `REORDER_LOG`. The reorder qty is `4 × threshold` (minimum 100).

**`/api/schedule/notify` (lines 289–311) — Workflow 5.** Iterates over EMPLOYEES where role is CASHIER/STOCKER/MANAGER, builds a per-employee notification message, publishes to Kafka.

**`/api/planogram/sync` (lines 314–339) — Workflow 4.** Single planogram update → Kafka + UPSERT into PRODUCT_LOCATIONS.

**`/api/stats` (lines 342–360).** Returns counts of every interesting table. The dashboard's KPI tiles read this.

**`/api/recent/<table>` (lines 363–387).** Whitelisted-table reader — returns the most recent 20–30 rows from `sales`, `feedback`, `reorders`, `deliveries`, `events`, `inventory`, or `employees`. Converts datetime fields to ISO strings so JSON.dumps works.

**`/api/topics` (lines 390–397) and `/api/topics/<topic>/peek` (lines 400–419).** Wraps `KafkaAdminClient.list_topics()` and a one-off `KafkaConsumer` (1.5-second timeout) to give the dashboard's Kafka Inspector tab its data.

---

## 11. Go validator — function by function

`go-validator/main.go`:

**`SaleEvent` struct (lines 25–32).** JSON tags match the field names in the documents — `unit_price`, `sale_ts`, `emp_id`. NiFi's JoltTransform should rename incoming fields to match before calling us.

**`main()` (lines 39–66).** Loops up to 30 times trying to connect to Postgres (the validator's container starts in parallel with Postgres, so the first few attempts may fail). Once connected, registers three handlers and starts listening on `:8080`.

**`healthHandler` (lines 69–77).** Returns 200 with `{status:"up", db:"connected"}` when the DB ping succeeds, otherwise 503. Docker Compose uses this for the `healthcheck` directive.

**`validateHandler` (lines 80–119).** Decodes the JSON body, runs six checks (required fields, qty > 0, unit_price > 0, RFC3339 timestamp), then cross-references the SKU against `PRODUCT_CATALOG`. Returns 200 if valid, 400 with a list of error strings if not. NiFi's `InvokeHTTP` processor can route the FlowFile based on the HTTP status code: 200 → success queue, 400 → DLQ.

**`metricsHandler` (lines 122–134).** Pure-read endpoint that returns `{sales, feedback, reorders}` counts. The CORS header lets the dashboard hit this directly if desired.

**`respond()` (lines 137–142).** Helper to set the right Content-Type and status, then JSON-encode the body.

---

## 12. Database schema reference

| Table              | Purpose                                          | Written by                              |
| ------------------ | ------------------------------------------------ | --------------------------------------- |
| `DW_SALES_FACT`    | Every POS scan (the fact table)                  | Workflow 1                              |
| `INVENTORY`        | Per-SKU per-store stock + reorder threshold      | Workflow 1 (decrement), seed.sql (init) |
| `REORDER_LOG`      | Audit of every reorder NiFi fired                | Workflow 2                              |
| `PRODUCT_CATALOG`  | Vendor item_code → FreshMart sku mapping         | seed.sql (init only)                    |
| `CUSTOMER_FEEDBACK`| Every complaint, classified                      | Workflow 6                              |
| `VENDOR_DELIVERIES`| Validated rows from vendor CSVs                  | Workflow 3                              |
| `PRODUCT_LOCATIONS`| Per-SKU aisle/section/shelf                      | Workflow 4                              |
| `PAYROLL_ATTENDANCE`| Synced from HR weekly                           | Workflow 5                              |
| `EMPLOYEES`        | All employees with roles                         | seed.sql (init only)                    |
| `STORES`           | Store directory                                  | seed.sql (init only)                    |
| `EVENT_LOG`        | Audit of every dashboard-triggered event         | Every endpoint in pos-simulator         |

Schema source: `sql/init.sql`. Seed data: `sql/seed.sql`.

---

## 13. Static seed data

The `static-data/` directory contains three JSON files that NiFi (or any other service) can read as lookup tables:

| File                                       | Rows | Purpose                                     |
| ------------------------------------------ | ---- | ------------------------------------------- |
| `static-data/products/product_catalog.json`| 10   | Master product list with vendor mapping     |
| `static-data/stores/stores.json`           | 5    | All FreshMart locations                     |
| `static-data/employees/employees.json`     | 8    | Roster covering all roles                   |

The `test-data/` directory has triggerable sample events:

| File                                  | Use case                                                     |
| ------------------------------------- | ------------------------------------------------------------ |
| `test-data/DOLE_20241101_delivery.csv`| Vendor CSV — drop into `vendor-data/` to trigger Workflow 3  |
| `test-data/NESTLE_20241101_delivery.csv`| Same — different vendor                                    |
| `test-data/pos_sales_batch.json`      | 7 sample sales — feed to Workflow 1                          |
| `test-data/customer_feedback.json`    | 7 feedback items (5 SAFETY → auto-recall)                    |
| `test-data/planogram_update.json`     | Multi-SKU planogram update                                   |

Both directories are bind-mounted into NiFi at `/opt/freshmart/static` and `/opt/freshmart/test-data` so NiFi's `GetFile`, `LookupRecord`, and `ListenHTTP` processors can read them directly.

---

## 13.5 Offline test harness

The project ships with a self-contained test suite at `tests/test_pos_simulator.py` that exercises **every endpoint** and **every workflow** of the POS simulator without Docker, Kafka, or Postgres running. It mocks Kafka and uses SQLite-as-Postgres against the real `sql/init.sql` + `sql/seed.sql`.

```bash
pip install flask flask-cors
python3 tests/test_pos_simulator.py
```

Expected: `RESULT: 64 passed, 0 failed`.

This is the test that caught the bugs documented below.

## 13.6 Bug fixes in v2 (POS simulator hardening)

Twelve issues were found by the test harness on v1 and fixed in v2:

| Fix | What was broken                                                                            | What v2 does                                                       |
| --- | ------------------------------------------------------------------------------------------ | ------------------------------------------------------------------ |
| A   | `/api/pos/sale` published malformed events to Kafka, then `KeyError`'d on the DB insert and returned 200. | Validates `store_id`, `sku`, `qty > 0`, `price > 0`, ISO8601 `timestamp`. Returns 400 with errors list. No Kafka publish on validation failure. |
| B   | "Fire 25 Random Sales" published to Kafka but **never** wrote to `DW_SALES_FACT` or decremented `INVENTORY`. KPI tile didn't move. | Bulk endpoint now writes every event to DW and inventory, exactly like single sales. |
| C   | HR weekly notifications were published to the `planogram-updates` topic (copy-paste bug). | New dedicated `hr-notifications` topic; kafka-init creates it. |
| D   | `datetime.utcnow()` used (deprecated in Python 3.12).                                      | Replaced with `datetime.now(timezone.utc)`. |
| F   | Empty request body crashed with `AttributeError: 'NoneType' has no attribute 'setdefault'`. | New `parse_body()` returns `{}` on missing body. |
| G   | First successful Kafka producer was cached forever — if brokers later went down, every request would hang on `send()`. | `producer()` now checks `bootstrap_connected()` on each call; rebuilds on stale. Send timeouts capped at 10 sec. |
| J   | Bulk sales used a hardcoded 5-SKU list regardless of selected store.                        | Bulk endpoint queries `INVENTORY WHERE store_id = ?` to pick realistic SKUs. |
| K   | Planogram form "ALL stores" option just inserted a literal `store_id='ALL'` row.           | When `store_id == 'ALL'`, fans out to every row in `STORES`. |
| L   | Dashboard toast referenced undefined CSS class `animate-pulse-once`.                       | New `@keyframes ibm-toast-in` + `.animate-toast-in` class. |
| —   | Dashboard `postJSON()` only threw a generic `HTTP 4xx` on errors.                          | Now extracts the structured `{errors: [...]}` from the response and surfaces each error string in the toast. |
| —   | `/api/topics/<topic>/peek` used `auto_offset_reset='latest'` so it returned nothing unless you happened to send a message between the request and the timeout. | Switched to `earliest` so the dashboard can actually inspect historical messages. |
| —   | All endpoints had inconsistent error handling — some returned 200 with logs, some 500.     | All endpoints now: validate first, return 400 on bad input, 502 on Kafka failure, 500 only on unexpected DB errors. |

Validated by `tests/test_pos_simulator.py` (22 test scenarios, 64 individual assertions).

---

## 14. Troubleshooting

**NiFi takes forever to come up.** Yes — 60–90 seconds is normal. Watch with `docker compose logs -f nifi | grep started`.

**Browser says certificate invalid for `https://localhost:8443`.** NiFi self-signs on first boot. In Chrome, type `thisisunsafe` while focused on the page. Or use Firefox and click through the warning.

**"port already in use" on startup.** Some other process owns one of the ports. Either kill it or override in `.env`. Then `docker compose down && docker compose up -d`.

**Dashboard KPIs all show `—`.** The pos-simulator container probably isn't healthy yet. `docker compose logs pos-simulator` will tell you. Most common cause: Kafka still starting — the simulator's `producer()` retry loop will get there.

**Kafka "no brokers available".** Check `docker compose ps`. If kafka isn't `healthy` yet, give it ~30 sec. If it's been more than 2 minutes, check `docker compose logs kafka` — disk full and bad volume permissions are the usual suspects.

**Postgres init didn't seed.** The init scripts only run on a *fresh* volume. `docker compose down -v` and `up -d` again to reseed.

**LocalStack queues empty.** Init runs once when LocalStack is ready. If it failed, `docker compose logs localstack | grep -i error`. Easiest recovery: `docker compose down -v && docker compose up -d`.

**"connection refused" hitting `/api` from the dashboard.** Check `docker compose ps`. If `freshmart-dashboard` (the nginx) is running but the simulator is down, nginx will return 502 — restart the simulator.

**I rebuilt go-validator and it still uses the old binary.** Docker layer caching. `docker compose build --no-cache go-validator`.

**I want to keep volumes but rebuild images.** `docker compose down && docker compose up -d --build`.

---

## 15. Tear-down

```bash
# Stop everything, keep volumes (data persists for next time)
docker compose down

# Stop and wipe all data (postgres, kafka, nifi, localstack, pgadmin)
docker compose down -v

# Stop, wipe, remove built images (start completely fresh)
docker compose down -v --rmi local
docker system prune -f
```

---

## License & attribution

This demo stack ships everything under permissive open-source licenses. Upstream:

- Apache NiFi · Apache License 2.0
- Apache Kafka / Confluent Community · Confluent Community License
- PostgreSQL · PostgreSQL License
- LocalStack Community · Apache License 2.0
- nginx · 2-clause BSD
- IBM Plex font family · SIL Open Font License 1.1
- Tailwind CSS · MIT
- kafka-python · Apache License 2.0
- Flask · BSD-3-Clause

Inspired by the *Apache NiFi Complete Reference — FreshMart Grocery Store Pipeline* document. All FreshMart names, store IDs, employee IDs, and SKUs are fictional and used purely for demonstration.
"# nifidemo" 
