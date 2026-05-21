-- =============================================================================
-- FreshMart Data Warehouse — Schema Initialization
-- Loaded automatically by PostgreSQL on first start via docker-entrypoint-initdb
-- =============================================================================

-- ── POS Sales Fact Table ─────────────────────────────────────────────────────
-- Every cashier scan inserts one row here. Loaded by NiFi Workflow 1.
CREATE TABLE IF NOT EXISTS DW_SALES_FACT (
  id            BIGSERIAL PRIMARY KEY,
  store_id      VARCHAR(20)   NOT NULL,
  sku           VARCHAR(50)   NOT NULL,
  qty           INTEGER       NOT NULL CHECK (qty > 0),
  unit_price    DECIMAL(10,2) NOT NULL,
  emp_id        VARCHAR(20),
  sale_ts       TIMESTAMPTZ   NOT NULL,
  ingest_time   TIMESTAMPTZ   DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sales_store_ts ON DW_SALES_FACT (store_id, sale_ts);
CREATE INDEX IF NOT EXISTS idx_sales_sku      ON DW_SALES_FACT (sku);

-- ── Inventory Levels ────────────────────────────────────────────────────────
-- Polled every 5 min by NiFi Workflow 2 to trigger re-orders.
CREATE TABLE IF NOT EXISTS INVENTORY (
  sku                 VARCHAR(50)  NOT NULL,
  store_id            VARCHAR(20)  NOT NULL,
  qty                 INTEGER      NOT NULL,
  reorder_threshold   INTEGER      DEFAULT 50,
  updated_at          TIMESTAMPTZ  DEFAULT NOW(),
  PRIMARY KEY (sku, store_id)
);

-- ── Reorder Audit Log ───────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS REORDER_LOG (
  id            BIGSERIAL PRIMARY KEY,
  sku           VARCHAR(50)   NOT NULL,
  store_id      VARCHAR(20)   NOT NULL,
  vendor_id     VARCHAR(20),
  qty_ordered   INTEGER       NOT NULL,
  ordered_at    TIMESTAMPTZ   DEFAULT NOW()
);

-- ── Product Catalog (vendor item_code → FreshMart sku mapping) ──────────────
-- Used by NiFi Workflow 3 (LookupRecord) to translate vendor barcodes.
CREATE TABLE IF NOT EXISTS PRODUCT_CATALOG (
  item_code   VARCHAR(50) PRIMARY KEY,    -- vendor's barcode
  sku         VARCHAR(50) NOT NULL,       -- FreshMart's SKU
  name        VARCHAR(200),
  category    VARCHAR(50),
  vendor_id   VARCHAR(20)
);

-- ── Customer Feedback ───────────────────────────────────────────────────────
-- NiFi Workflow 6 reads feedback and triggers recalls.
CREATE TABLE IF NOT EXISTS CUSTOMER_FEEDBACK (
  id                BIGSERIAL PRIMARY KEY,
  store_id          VARCHAR(20),
  sku               VARCHAR(50),
  feedback_text     TEXT,
  category          VARCHAR(30),        -- SAFETY | QUALITY | SERVICE | GENERAL
  recall_triggered  BOOLEAN     DEFAULT FALSE,
  received_at       TIMESTAMPTZ DEFAULT NOW()
);

-- ── Vendor Deliveries (post-validation, populated by Workflow 3) ────────────
CREATE TABLE IF NOT EXISTS VENDOR_DELIVERIES (
  id              BIGSERIAL PRIMARY KEY,
  vendor_id       VARCHAR(20)   NOT NULL,
  sku             VARCHAR(50)   NOT NULL,
  cases           INTEGER       NOT NULL,
  unit_cost       DECIMAL(10,2) NOT NULL,
  delivery_date   DATE          NOT NULL,
  received_at     TIMESTAMPTZ   DEFAULT NOW()
);

-- ── Product Locations (planogram, Workflow 4) ───────────────────────────────
CREATE TABLE IF NOT EXISTS PRODUCT_LOCATIONS (
  sku           VARCHAR(50)  NOT NULL,
  store_id      VARCHAR(20)  NOT NULL,
  aisle         VARCHAR(10),
  section       VARCHAR(20),
  shelf_level   INTEGER,
  updated_at    TIMESTAMPTZ  DEFAULT NOW(),
  PRIMARY KEY (sku, store_id)
);

-- ── Payroll Attendance (Workflow 5 — HR sync) ───────────────────────────────
CREATE TABLE IF NOT EXISTS PAYROLL_ATTENDANCE (
  emp_id        VARCHAR(20)  NOT NULL,
  shift_date    DATE         NOT NULL,
  hours         DECIMAL(5,2) NOT NULL,
  status        VARCHAR(20),
  department    VARCHAR(30),
  PRIMARY KEY (emp_id, shift_date)
);

-- ── Employees ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS EMPLOYEES (
  emp_id        VARCHAR(20)  PRIMARY KEY,
  emp_name      VARCHAR(100),
  emp_email     VARCHAR(150),
  role          VARCHAR(30),     -- CASHIER | MANAGER | STOCKER | VENDOR | HR
  department    VARCHAR(30),
  store_id      VARCHAR(20)
);

-- ── Stores ──────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS STORES (
  store_id   VARCHAR(20) PRIMARY KEY,
  name       VARCHAR(100),
  region     VARCHAR(20),
  address    VARCHAR(200)
);

-- ── Event Log (audit trail — every dashboard-triggered event lands here) ────
CREATE TABLE IF NOT EXISTS EVENT_LOG (
  id            BIGSERIAL PRIMARY KEY,
  event_type    VARCHAR(50)  NOT NULL,
  source        VARCHAR(50),
  payload       JSONB,
  created_at    TIMESTAMPTZ  DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_event_log_type ON EVENT_LOG (event_type);
CREATE INDEX IF NOT EXISTS idx_event_log_created ON EVENT_LOG (created_at DESC);
