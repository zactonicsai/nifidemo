#!/usr/bin/env bash
# scripts/test-stack.sh — exercises every playbook and verifies idempotency.
#
# Usage:
#   ./scripts/test-stack.sh           # run, then tear down
#   ./scripts/test-stack.sh --keep    # leave the stack running afterward
#
# Exit codes:
#   0  all tests passed
#   1  a test failed
#   2  prerequisites missing
set -euo pipefail

KEEP=0
[[ "${1:-}" == "--keep" ]] && KEEP=1

cd "$(dirname "$0")/.."

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; NC='\033[0m'
pass() { echo -e "${GREEN}✓${NC} $1"; }
fail() { echo -e "${RED}✗${NC} $1"; exit 1; }
info() { echo -e "${YELLOW}→${NC} $1"; }

# ----- 0. Prereqs -----
command -v docker >/dev/null    || { echo "docker not found";    exit 2; }
command -v ansible-playbook >/dev/null || { echo "ansible-playbook not found"; exit 2; }
docker compose version >/dev/null 2>&1 || { echo "docker compose plugin missing"; exit 2; }
pass "Prerequisites present"

# ----- 1. Bootstrap -----
info "Bootstrap (00-bootstrap.yml)..."
ansible-playbook playbooks/00-bootstrap.yml >/tmp/bootstrap.log 2>&1 || { tail -30 /tmp/bootstrap.log; fail "Bootstrap failed"; }
pass "Stack bootstrapped"

# ----- 2. Health check -----
info "Health check (01-health-check.yml)..."
ansible-playbook playbooks/01-health-check.yml >/tmp/health.log 2>&1 || { tail -30 /tmp/health.log; fail "Health check failed"; }
pass "All services healthy"

# ----- 3. Backup logs -----
info "Backup logs (03-backup-logs.yml)..."
ansible-playbook playbooks/03-backup-logs.yml >/tmp/backup.log 2>&1 || { tail -30 /tmp/backup.log; fail "Backup failed"; }
# Verify archives exist
for svc in zookeeper kafka elasticsearch nifi; do
  count=$(find /tmp/ansible-tutorial-backups/$svc -name '*.tar.gz' 2>/dev/null | wc -l)
  [[ $count -ge 1 ]] || fail "No backup archive for $svc"
done
pass "Backup archives created for all services"

# ----- 4. Rotate + move logs -----
info "Rotate & move (04-rotate-and-move-logs.yml)..."
ansible-playbook playbooks/04-rotate-and-move-logs.yml >/tmp/rotate.log 2>&1 || { tail -30 /tmp/rotate.log; fail "Rotate failed"; }
pass "Rotate/move completed"

# ----- 5. Config deploy — FIRST run (may change) -----
info "Config deploy first run (05-config-deploy.yml)..."
ansible-playbook playbooks/05-config-deploy.yml >/tmp/deploy1.log 2>&1 || { tail -30 /tmp/deploy1.log; fail "First deploy failed"; }
pass "First config deploy succeeded"

# ----- 6. Config deploy — SECOND run MUST be no-op -----
info "Idempotency test — second run (must report changed=0)..."
ansible-playbook playbooks/05-config-deploy.yml 2>&1 | tee /tmp/deploy2.log | grep -E 'changed=[0-9]+' || true
CHANGED=$(grep -oE 'changed=[0-9]+' /tmp/deploy2.log | grep -oE '[0-9]+' | awk '{s+=$1} END {print s+0}')
if [[ $CHANGED -gt 0 ]]; then
  fail "Second run reported changed=$CHANGED (expected 0) — playbook is NOT idempotent"
fi
pass "Idempotent on second run (changed=0)"

# ----- 7. Force a change and re-run — handler MUST fire -----
info "Force a config change and re-run..."
mkdir -p docker/config/zookeeper
echo "# forced change $(date +%s)" >> docker/config/zookeeper/zoo.cfg.local
# Touch a value the template renders, by changing the var via -e
ansible-playbook playbooks/05-config-deploy.yml -e zk_max_client_cnxns=80 >/tmp/deploy3.log 2>&1 || { tail -30 /tmp/deploy3.log; fail "Forced-change run failed"; }
# Verify handler ran (zookeeper got restarted)
grep -q "Restart Zookeeper container" /tmp/deploy3.log || fail "Handler did not fire after forced change"
pass "Handler fired after forced config change"

# ----- 8. Disk usage report -----
info "Disk usage report (07-disk-usage-report.yml)..."
ansible-playbook playbooks/07-disk-usage-report.yml >/tmp/disk.log 2>&1 || { tail -30 /tmp/disk.log; fail "Disk report failed"; }
pass "Disk report passed"

# ----- 9. Cleanup dry run -----
info "Cleanup dry run (06-cleanup-old-data.yml)..."
ansible-playbook playbooks/06-cleanup-old-data.yml >/tmp/cleanup.log 2>&1 || { tail -30 /tmp/cleanup.log; fail "Cleanup dry run failed"; }
pass "Cleanup dry run completed"

# ----- Final teardown -----
if [[ $KEEP -eq 0 ]]; then
  info "Tearing down stack..."
  ( cd docker && docker compose down -v ) >/tmp/teardown.log 2>&1 || true
  pass "Stack torn down"
else
  info "Leaving stack running (use 'cd docker && docker compose down -v' to clean up)"
fi

echo
echo -e "${GREEN}====================================${NC}"
echo -e "${GREEN}  ALL TESTS PASSED                  ${NC}"
echo -e "${GREEN}====================================${NC}"
