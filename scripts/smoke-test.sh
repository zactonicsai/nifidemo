#!/usr/bin/env bash
# =============================================================================
# FreshMart Demo — Smoke Test
# Runs through every workflow and asserts data ends up where it should.
# =============================================================================
set -e

API=http://localhost:8000/api          # via dashboard nginx proxy
echo "▸ Smoke testing FreshMart pipeline at $API"

step() { echo ""; echo "── $1 ───────────────────────────────"; }

step "1. Health"
curl -sf "$API/health" | jq .

step "2. POS sale (Workflow 1)"
curl -sf -X POST "$API/pos/sale" -H "Content-Type: application/json" \
  -d '{"store_id":"FM-042","sku":"BAN-CAVENDISH-1LB","qty":3,"price":0.99,"cashier_id":"EMP-1147"}' | jq .

step "3. Bulk POS"
curl -sf -X POST "$API/pos/sale/bulk" -H "Content-Type: application/json" \
  -d '{"count":15,"store_id":"FM-042"}' | jq '.fired'

step "4. Vendor delivery (Workflow 3)"
curl -sf -X POST "$API/vendor/delivery" -H "Content-Type: application/json" \
  -d '{"vendor_id":"DOLE","sku":"BAN-CAVENDISH-1LB","cases":240,"unit_cost":0.28}' | jq .

step "5. Inventory sweep (Workflow 2)"
curl -sf -X POST "$API/inventory/check" -H "Content-Type: application/json" -d '{}' | jq '.triggered | length'

step "6. Planogram broadcast (Workflow 4)"
curl -sf -X POST "$API/planogram/sync" -H "Content-Type: application/json" \
  -d '{"store_id":"FM-042","sku":"BAN-CAVENDISH-1LB","aisle":"A07","section":"PRODUCE-1","shelf_level":2}' | jq .

step "7. HR weekly notify (Workflow 5)"
curl -sf -X POST "$API/schedule/notify" -H "Content-Type: application/json" \
  -d "{\"week_start\":\"$(date +%F)\"}" | jq '.notified'

step "8. Customer feedback (Workflow 6) — fire 5 SAFETY to trigger recall"
for i in 1 2 3 4 5; do
  curl -sf -X POST "$API/feedback" -H "Content-Type: application/json" \
    -d "{\"store_id\":\"FM-042\",\"sku\":\"MILK-WHOLE-1G\",\"feedback_text\":\"Complaint #$i: milk was spoiled and sour\"}" > /dev/null
done
echo "5 feedback events submitted"

step "9. Final stats"
curl -sf "$API/stats" | jq .

step "10. Kafka topics"
curl -sf "$API/topics" | jq '.topics'

echo ""
echo "✓ Smoke test complete."
echo ""
echo "Open the dashboard:  http://localhost:8000"
echo "NiFi UI:             https://localhost:8443/nifi  (admin / FreshMart2024Secret!)"
echo "Kafka UI:            http://localhost:8081"
echo "pgAdmin:             http://localhost:8082  (admin@freshmart.local / FreshMart2024!)"
