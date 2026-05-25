# Ansible + Docker Compose Tutorial
## Managing Zookeeper, Kafka, Elasticsearch, and NiFi with Real Admin Scenarios

This tutorial uses **Docker Compose** to spin up a realistic multi-service stack, then drives all admin work through **Ansible playbooks**. You'll learn how to check service health, restart services safely, back up and rotate logs, move logs to archive locations, and run other common operational tasks — all idempotently.

**Versions used (current as of May 2026):**
- Ansible community package 13.7.0 / ansible-core 2.20.4
- Docker Engine 27.x with Compose v2
- Confluent Platform 7.7 (Kafka 3.8 / Zookeeper 3.9)
- Elasticsearch 8.15
- Apache NiFi 2.0

---

## Project Layout

```
ansible-tutorial/
├── docker/
│   ├── docker-compose.yml          # The full stack
│   └── .env                        # Image versions, ports, etc.
├── inventory/
│   └── hosts.ini                   # Inventory (uses Docker socket as connection)
├── group_vars/
│   └── all.yml                     # Vars shared by every play
├── playbooks/
│   ├── 00-bootstrap.yml            # Bring stack up, create volumes/dirs
│   ├── 01-health-check.yml         # Check every service is healthy
│   ├── 02-restart-service.yml      # Safely restart with pre-flight checks
│   ├── 03-backup-logs.yml          # Snapshot logs, gzip, store under /var/backups
│   ├── 04-rotate-and-move-logs.yml # Rotate active logs, move old ones to archive
│   ├── 05-config-deploy.yml        # Deploy config + restart only on change
│   ├── 06-cleanup-old-data.yml     # Prune backups older than N days
│   ├── 07-disk-usage-report.yml    # Check disk, alert if over threshold
│   └── site.yml                    # Master playbook (runs everything in order)
├── roles/
│   ├── common/                     # Bootstrap dirs, packages, common tasks
│   ├── zookeeper/                  # Zookeeper-specific tasks/templates
│   ├── kafka/                      # Kafka-specific tasks/templates
│   ├── elasticsearch/              # ES-specific tasks
│   ├── nifi/                       # NiFi-specific tasks
│   └── admin_tasks/                # Reusable admin operations
├── scripts/
│   └── test-stack.sh               # End-to-end test driver
├── ansible.cfg                     # Ansible config
└── README.md                       # This file
```

---

## The Stack at a Glance

| Service | Purpose | Port(s) | Log Location (in container) |
|---------|---------|---------|------------------------------|
| zookeeper | Coordination service for Kafka | 2181 | `/var/log/zookeeper` |
| kafka | Message broker | 9092, 29092 | `/var/log/kafka` |
| elasticsearch | Search/analytics engine | 9200, 9300 | `/usr/share/elasticsearch/logs` |
| nifi | Data flow orchestration | 8080 | `/opt/nifi/nifi-current/logs` |

All log directories are bind-mounted to the host at `./docker/logs/<service>/`, so Ansible can manage them directly on the host filesystem (no `docker exec` gymnastics for log work).

---

## Quick Start

```bash
# 1. Install requirements
pip install "ansible-core>=2.20,<2.21" "ansible>=13.7,<14"
ansible-galaxy collection install community.docker community.general ansible.posix

# 2. Bring the stack up
cd ansible-tutorial
ansible-playbook playbooks/00-bootstrap.yml

# 3. Verify everything is healthy
ansible-playbook playbooks/01-health-check.yml

# 4. Try the operational playbooks
ansible-playbook playbooks/03-backup-logs.yml
ansible-playbook playbooks/04-rotate-and-move-logs.yml
ansible-playbook playbooks/07-disk-usage-report.yml

# 5. Test a config-driven restart
ansible-playbook playbooks/05-config-deploy.yml --check --diff
ansible-playbook playbooks/05-config-deploy.yml

# 6. Run the idempotency test (second run should show changed=0)
ansible-playbook playbooks/05-config-deploy.yml
```

---

## The Eight Scenarios Covered

### 1. Bootstrap — bring up the stack
**Playbook:** `00-bootstrap.yml`
Creates host directories, sets permissions, runs `docker compose up -d`, waits for each service's healthcheck to pass.

### 2. Health check — verify every service
**Playbook:** `01-health-check.yml`
Per service: check container is running, port answers, HTTP endpoint returns 200 (where applicable). Fails loudly if any check fails.

### 3. Safe restart — pre-flight then restart
**Playbook:** `02-restart-service.yml`
Pre-flight: stat the container's log file, capture pre-restart line count. Restart via Docker module. Post-flight: wait for healthy, confirm log activity has resumed.

### 4. Backup logs — snapshot before any change
**Playbook:** `03-backup-logs.yml`
For each service: stat the log dir, gzip a timestamped copy into `/var/backups/<service>/`, verify the archive is non-zero size.

### 5. Rotate & move logs — keep disks happy
**Playbook:** `04-rotate-and-move-logs.yml`
Find log files over a size or age threshold, gzip them in place, move to an archive directory on a different mount, truncate the live log if the service is running.

### 6. Config-driven restart — change → restart, no change → no restart
**Playbook:** `05-config-deploy.yml`
Render configs from templates with `backup: yes` and `validate:`. Only the handler restarts the container, and only when the template task reports `changed`.

### 7. Cleanup — prune old archives
**Playbook:** `06-cleanup-old-data.yml`
Find backups older than `retention_days` (default 14), remove them, report freed space.

### 8. Disk usage report — alert when filling up
**Playbook:** `07-disk-usage-report.yml`
Walk the host's relevant mounts, compute usage, fail the play if any are over `disk_warn_pct` (default 80).

---

## Why Docker Compose for an Ansible Tutorial?

In real ops, you rarely have the luxury of fresh VMs to practice on. Docker Compose gives you:

- **Reproducibility.** Tear down with `docker compose down -v` and start clean.
- **Isolation.** Nothing on your laptop changes.
- **Realistic targets.** These are the real Confluent/Elastic/NiFi images, not mocks — every Ansible technique here works the same way against EC2, bare metal, or k8s nodes.
- **Cross-service scenarios.** Zookeeper → Kafka dependency, Elasticsearch heap tuning, NiFi log volume — covers patterns you'll meet in production.

Ansible treats the host running Compose as its target. All log directories are bind-mounted from the host, so Ansible's `file`, `find`, `copy`, and `archive` modules work directly on real paths.

---

## Best Practices Demonstrated

- ✅ **FQCN module names** everywhere (`ansible.builtin.copy`, `community.docker.docker_compose_v2`)
- ✅ **Idempotency** — every playbook reports `changed=0` on the second consecutive run
- ✅ **Handlers** for service restarts, never `state: restarted` in regular tasks
- ✅ **`backup: yes` + `validate:`** on config templates
- ✅ **`when` guards** on every destructive operation
- ✅ **`stat` before file action** — never assume a file exists
- ✅ **`changed_when: false`** on read-only shell/command tasks
- ✅ **`--check --diff`** support — every playbook works in dry-run mode
- ✅ **Tags** for selective execution

---

## Testing Everything

The `scripts/test-stack.sh` script runs the full lifecycle:

```bash
./scripts/test-stack.sh
```

What it does:
1. Bootstraps stack
2. Runs health check
3. Runs each operational playbook
4. Runs config deploy twice — second run MUST report `changed=0`
5. Forces a config change, runs again — handler MUST fire
6. Verifies backups exist on disk
7. Tears down (optional with `--keep`)
