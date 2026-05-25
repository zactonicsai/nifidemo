#!/usr/bin/env bash
# scripts/test-stack.sh — exercises every playbook from the controller container.
#
# Run this INSIDE the controller container:
#   docker compose run --rm controller bash scripts/test-stack.sh
#
# Or, if you've started the controller in the background:
#   docker exec -it ansible-controller bash scripts/test-stack.sh
set -euo pipefail

cd "$(dirname "$0")/.."

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; NC='\033[0m'
pass() { echo -e "${GREEN}OK${NC}  $1"; }
fail() { echo -e "${RED}FAIL${NC} $1"; exit 1; }
info() { echo -e "${YELLOW}>>${NC}  $1"; }

# ----- 0. Sanity: are we inside the controller? -----
[ -S /var/run/docker.sock ] || fail "Docker socket not mounted. Run inside the controller container."
command -v ansible-playbook >/dev/null || fail "ansible-playbook missing. Are you in the controller?"
command -v docker           >/dev/null || fail "docker CLI missing. Are you in the controller?"
pass "Running inside controller (ansible $(ansible --version | head -1 | awk '{print $2}' | tr -d '][') + docker $(docker --version | awk '{print $3}' | tr -d ','))"

# ----- 1. Health check (stack should already be up) -----
info "Health check (01-health-check.yml)..."
ansible-playbook playbooks/01-health-check.yml >/tmp/health.log 2>&1 || { tail -30 /tmp/health.log; fail "Health check failed"; }
pass "All services healthy"

# ----- 2. Backup logs -----
info "Backup logs (03-backup-logs.yml)..."
ansible-playbook playbooks/03-backup-logs.yml >/tmp/backup.log 2>&1 || { tail -30 /tmp/backup.log; fail "Backup failed"; }
for svc in zookeeper kafka elasticsearch nifi; do
  count=$(find /workspace/backups/$svc -name '*.tar.gz' 2>/dev/null | wc -l)
  [ "$count" -ge 1 ] || fail "No backup archive for $svc"
done
pass "Backup archives created for all services"

# ----- 3. Rotate + move logs -----
info "Rotate & move (04-rotate-and-move-logs.yml)..."
ansible-playbook playbooks/04-rotate-and-move-logs.yml >/tmp/rotate.log 2>&1 || { tail -30 /tmp/rotate.log; fail "Rotate failed"; }
pass "Rotate/move completed"

# ----- 4. Config deploy first run -----
info "Config deploy first run (05-config-deploy.yml)..."
ansible-playbook playbooks/05-config-deploy.yml >/tmp/deploy1.log 2>&1 || { tail -30 /tmp/deploy1.log; fail "First deploy failed"; }
pass "First config deploy succeeded"

# ----- 5. Idempotency proof — second run -----
info "Idempotency test — second run must report changed=0..."
ansible-playbook playbooks/05-config-deploy.yml 2>&1 | tee /tmp/deploy2.log | grep -E 'changed=[0-9]+' || true
CHANGED=$(grep -oE 'changed=[0-9]+' /tmp/deploy2.log | grep -oE '[0-9]+' | awk '{s+=$1} END {print s+0}')
[ "$CHANGED" -eq 0 ] || fail "Second run reported changed=$CHANGED (expected 0)"
pass "Idempotent on second run"

# ----- 6. Force a change → handler fires -----
info "Force a config change and verify handler fires..."
ansible-playbook playbooks/05-config-deploy.yml -e zk_max_client_cnxns=80 >/tmp/deploy3.log 2>&1 || { tail -30 /tmp/deploy3.log; fail "Forced-change run failed"; }
grep -q "Restart Zookeeper container" /tmp/deploy3.log || fail "Handler did not fire after forced change"
pass "Handler fired after forced config change"

# ----- 7. Disk usage report -----
info "Disk usage report (07-disk-usage-report.yml)..."
ansible-playbook playbooks/07-disk-usage-report.yml >/tmp/disk.log 2>&1 || { tail -30 /tmp/disk.log; fail "Disk report failed"; }
pass "Disk report passed"

# ----- 8. Cleanup dry run -----
info "Cleanup dry run (06-cleanup-old-data.yml)..."
ansible-playbook playbooks/06-cleanup-old-data.yml >/tmp/cleanup.log 2>&1 || { tail -30 /tmp/cleanup.log; fail "Cleanup dry run failed"; }
pass "Cleanup dry run completed"

echo
echo -e "${GREEN}===================================${NC}"
echo -e "${GREEN}  ALL TESTS PASSED                 ${NC}"
echo -e "${GREEN}===================================${NC}"
