-- =============================================================================
-- FreshMart Data Warehouse — Seed Data
-- =============================================================================

-- ── Stores ──────────────────────────────────────────────────────────────────
INSERT INTO STORES (store_id, name, region, address) VALUES
  ('FM-042', 'FreshMart Downtown',      'EAST',    '101 Market St, New York, NY'),
  ('FM-118', 'FreshMart Westside',      'WEST',    '500 Sunset Blvd, Los Angeles, CA'),
  ('FM-077', 'FreshMart Lakeview',      'CENTRAL', '88 Lake Shore Dr, Chicago, IL'),
  ('FM-201', 'FreshMart Southpoint',    'SOUTH',   '12 Peachtree, Atlanta, GA'),
  ('FM-309', 'FreshMart Northgate',     'NORTH',   '700 Pine Ave, Seattle, WA')
ON CONFLICT (store_id) DO NOTHING;

-- ── Product Catalog (vendor barcode → FreshMart SKU) ────────────────────────
INSERT INTO PRODUCT_CATALOG (item_code, sku, name, category, vendor_id) VALUES
  ('DOLE-BAN-001',   'BAN-CAVENDISH-1LB', 'Bananas 1lb Cavendish',  'PRODUCE',  'DOLE'),
  ('DOLE-BAN-002',   'BAN-PLANTAIN-1LB',  'Plantain 1lb',           'PRODUCE',  'DOLE'),
  ('DOLE-PINE-001',  'PINE-WHOLE-EACH',   'Pineapple Whole',        'PRODUCE',  'DOLE'),
  ('NESTLE-MLK-1G',  'MILK-WHOLE-1G',     'Whole Milk 1 Gallon',    'DAIRY',    'NESTLE'),
  ('NESTLE-CHO-12',  'CHOC-BAR-12CT',     'Chocolate Bar 12ct',     'CANDY',    'NESTLE'),
  ('KRAFT-CHE-8OZ',  'CHEESE-CHED-8OZ',   'Cheddar Cheese 8oz',     'DAIRY',    'KRAFT'),
  ('TYSON-CHI-2LB',  'CHICKEN-BRST-2LB',  'Chicken Breast 2lb',     'MEAT',     'TYSON'),
  ('PEPSI-COKE-12',  'SODA-COKE-12PK',    'Coke 12-pack',           'BEVERAGE', 'PEPSI'),
  ('GENERAL-CER-1',  'CEREAL-OAT-18OZ',   'Oat Cereal 18oz',        'GROCERY',  'GENERAL-MILLS'),
  ('OCEAN-FSH-1LB',  'SALMON-FILLET-1LB', 'Salmon Fillet 1lb',      'SEAFOOD',  'OCEAN-FRESH')
ON CONFLICT (item_code) DO NOTHING;

-- ── Inventory (starts low for some items to trigger reorder workflow) ───────
INSERT INTO INVENTORY (sku, store_id, qty, reorder_threshold) VALUES
  ('BAN-CAVENDISH-1LB', 'FM-042', 18,  50),    -- LOW → triggers reorder
  ('BAN-PLANTAIN-1LB',  'FM-042', 62,  30),
  ('PINE-WHOLE-EACH',   'FM-042', 8,   25),    -- LOW
  ('MILK-WHOLE-1G',     'FM-042', 110, 80),
  ('CHEESE-CHED-8OZ',   'FM-042', 22,  40),    -- LOW
  ('CHICKEN-BRST-2LB',  'FM-042', 95,  60),
  ('SODA-COKE-12PK',    'FM-042', 14,  35),    -- LOW
  ('CEREAL-OAT-18OZ',   'FM-042', 88,  50),
  ('SALMON-FILLET-1LB', 'FM-042', 45,  30),
  ('BAN-CAVENDISH-1LB', 'FM-118', 75,  50),
  ('CHEESE-CHED-8OZ',   'FM-118', 12,  40),    -- LOW
  ('MILK-WHOLE-1G',     'FM-077', 200, 80)
ON CONFLICT (sku, store_id) DO NOTHING;

-- ── Employees (all roles for demo) ──────────────────────────────────────────
INSERT INTO EMPLOYEES (emp_id, emp_name, emp_email, role, department, store_id) VALUES
  ('EMP-1147', 'Alice Chen',     'alice.chen@freshmart.local',   'CASHIER',  'CHECKOUT', 'FM-042'),
  ('EMP-2210', 'Bob Martinez',   'bob.m@freshmart.local',        'MANAGER',  'STORE',    'FM-042'),
  ('EMP-3340', 'Carla Singh',    'carla.s@freshmart.local',      'STOCKER',  'STOCKING', 'FM-042'),
  ('EMP-4521', 'Dan Okafor',     'dan.o@freshmart.local',        'CASHIER',  'CHECKOUT', 'FM-118'),
  ('EMP-5099', 'Eva Petrov',     'eva.p@freshmart.local',        'MANAGER',  'STORE',    'FM-118'),
  ('EMP-6611', 'Frank Liu',      'frank.l@freshmart.local',      'HR',       'HR',       'HQ'),
  ('EMP-7720', 'Grace Adeyemi',  'grace.a@freshmart.local',      'STOCKER',  'PRODUCE',  'FM-077'),
  ('EMP-8801', 'Henry Park',     'henry.p@freshmart.local',      'CASHIER',  'CHECKOUT', 'FM-201')
ON CONFLICT (emp_id) DO NOTHING;
