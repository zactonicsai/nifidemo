# Ansible + Docker Compose Tutorial
## Zero-Install Controller — Run Everything from Windows via Docker Desktop

Everything in this tutorial runs in containers. **Nothing is installed on your Windows host** except Docker Desktop. The Ansible controller is itself a container that drives the other services through the Docker socket.

**Stack (current as of May 2026):**
- `controller` — Python 3.12 + ansible-core 2.20.4 + ansible 13.7.0 + collections + Docker CLI
- `zookeeper` — Confluent 7.7 (ZK 3.9)
- `kafka` — Confluent 7.7 (Kafka 3.8)
- `elasticsearch` — Elastic 8.15
- `nifi` — Apache 2.0

---

## How the Pieces Fit

```
+--------------------- Windows host -------------------------+
|                                                            |
|  Docker Desktop                                            |
|                                                            |
|  +-------------------+   docker.sock                       |
|  | ansible-controller| <--------------------+              |
|  | (Python + ansible)|                      |              |
|  +-------------------+                      |              |
|         |                                   |              |
|         | docker compose / docker exec      |              |
|         v                                   v              |
|  +-----------+  +-------+  +---------------+  +-------+    |
|  | zookeeper |  | kafka |  | elasticsearch |  | nifi  |    |
|  +-----------+  +-------+  +---------------+  +-------+    |
|         all share the `stack` bridge network               |
|                                                            |
|  Bind mounts (host -> container):                          |
|    docker\logs\<svc>   -> service log dir                  |
|    project root        -> /workspace inside controller     |
|                                                            |
+------------------------------------------------------------+
```

The controller container:
- Has the Docker CLI baked in
- Mounts the host's Docker socket → can drive the other containers
- Bind-mounts the whole project at `/workspace` → playbooks see the same paths regardless of where you cloned the project on Windows
- Joins the `stack` bridge network → reaches `zookeeper`, `kafka`, `elasticsearch`, `nifi` by name

---

## Prerequisites (Windows)

1. **Docker Desktop for Windows** — current version, with the Linux engine.
   - Settings → General → "Use the WSL 2 based engine" should be ticked.
   - Settings → Resources → enable WSL integration if you want to use WSL too (optional).
2. **PowerShell** or **cmd.exe** — both work.
3. **Git for Windows** (optional, only if cloning from a repo).

That's it. No Python, no Ansible, no WSL required.

---

## First Run (Windows PowerShell)

Open PowerShell in the project directory and run:

```powershell
# 1. Build the controller image (one-time, ~3 min)
docker compose -f docker\docker-compose.yml --profile controller build controller

# 2. Bring up the application stack (Zookeeper, Kafka, ES, NiFi)
docker compose -f docker\docker-compose.yml up -d

# 3. Wait ~90 seconds for all healthchecks to go green
docker compose -f docker\docker-compose.yml ps

# 4. Bootstrap: post-up sanity check + create backup dirs
.\ansible.ps1 playbooks\00-bootstrap.yml

# 5. Health check
.\ansible.ps1 playbooks\01-health-check.yml
```

If the `.ps1` form errors with "execution policy", run this once:
```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

Or use the `.cmd` form, which works without policy changes:
```powershell
.\ansible.cmd playbooks\01-health-check.yml
```

---

## Daily Use

### Run any playbook
```powershell
.\ansible.ps1 playbooks\03-backup-logs.yml
.\ansible.ps1 playbooks\05-config-deploy.yml --check --diff
.\ansible.ps1 playbooks\02-restart-service.yml -e target_service=kafka
```

### Drop into an interactive shell in the controller
```powershell
.\shell.cmd
```
Once inside, you can run `ansible-playbook ...`, `ansible all -m ping`, `docker ps`, etc. without spinning up a new container each time.

### Run the full test suite (idempotency proof, handler firing, etc.)
```powershell
.\ansible.ps1 ../scripts/test-stack.sh   # NO — that's a shell script, not a playbook
```

Use the shell wrapper instead:
```powershell
.\shell.cmd
# inside the controller:
bash scripts/test-stack.sh
```

---

## Project Layout

```
ansible-tutorial/
|
|-- ansible.cmd               Windows cmd entrypoint
|-- ansible.ps1               PowerShell entrypoint
|-- shell.cmd                 Drop into controller shell
|-- ansible.cfg               Ansible config
|-- README.md                 This file
|-- requirements.yml          Galaxy collections (baked into controller image)
|
|-- docker/
|   |-- docker-compose.yml    Full stack: controller + 4 services
|   |-- .env                  Pinned image versions
|   |-- controller/
|   |   `-- Dockerfile        Ansible controller image build
|   |-- logs/                 Created on first run (bind-mounted to services)
|   |-- config/               Rendered config overrides
|
|-- inventory/hosts.ini       Targets the controller (ansible_connection=local)
|-- group_vars/all.yml        Service catalog, paths, retention settings
|
|-- playbooks/
|   |-- 00-bootstrap.yml      Post-up checks, dir creation, wait-for-healthy
|   |-- 01-health-check.yml   Verify every service is alive
|   |-- 02-restart-service.yml  Safe restart with pre/post log snapshot
|   |-- 03-backup-logs.yml    Snapshot all logs into gzipped tars
|   |-- 04-rotate-and-move-logs.yml  Rotate huge logs, move old ones
|   |-- 05-config-deploy.yml  Template-driven config + handler-restart
|   |-- 06-cleanup-old-data.yml  Prune backups older than N days
|   |-- 07-disk-usage-report.yml  Disk usage, fails on >80%
|   |-- site.yml              Run everything in order
|
|-- roles/                    Service-specific templates
|-- scripts/test-stack.sh     End-to-end test driver
|-- backups/                  Created on first backup run
|-- archive/                  Created on first rotate run
```

---

## What Each Playbook Demonstrates

| # | Playbook | Patterns shown |
|---|---|---|
| 00 | bootstrap | Pre-flight checks, `retries`/`until` waits, idempotent directory creation |
| 01 | health-check | Three-layer probe: container state, app-level health, log activity |
| 02 | restart-service | Pre/post log snapshots, restart-count tracking, `assert` post-conditions |
| 03 | backup-logs | `stat` before action, `community.general.archive`, empty-archive detection, recent-backup guard |
| 04 | rotate-and-move-logs | `find` by `size`/`age`, in-place gzip, move to separate archive root |
| 05 | config-deploy | Template + `backup: yes`, handler chain via `listen:`, idempotent restart |
| 06 | cleanup-old-data | Dry-run by default, computed freed space, opt-in delete with `-e confirm_delete=true` |
| 07 | disk-usage-report | Mount-level scan, per-service log dir size, `fail_when` over threshold |

---

## Common Operations Cheat Sheet (Windows)

| Task | Command |
|---|---|
| Build controller image | `docker compose -f docker\docker-compose.yml --profile controller build controller` |
| Start stack | `docker compose -f docker\docker-compose.yml up -d` |
| Stop stack | `docker compose -f docker\docker-compose.yml down` |
| Stop + wipe data | `docker compose -f docker\docker-compose.yml down -v` |
| See service status | `docker compose -f docker\docker-compose.yml ps` |
| Tail a service log | `docker compose -f docker\docker-compose.yml logs -f kafka` |
| Run any playbook | `.\ansible.ps1 playbooks\<name>.yml` |
| Dry-run with diff | `.\ansible.ps1 playbooks\<name>.yml --check --diff` |
| Shell into controller | `.\shell.cmd` |
| Restart one service | `.\ansible.ps1 playbooks\02-restart-service.yml -e target_service=kafka` |
| Force a config change test | `.\ansible.ps1 playbooks\05-config-deploy.yml -e zk_max_client_cnxns=80` |
| Delete old backups | `.\ansible.ps1 playbooks\06-cleanup-old-data.yml -e confirm_delete=true` |

---

## Troubleshooting

**"docker: command not found" inside controller**
The controller image bakes in the Docker CLI. Rebuild: `docker compose -f docker\docker-compose.yml --profile controller build --no-cache controller`.

**"Cannot connect to the Docker daemon" from controller**
The host docker socket isn't mounted. Check the controller service in `docker\docker-compose.yml` — it must have `- /var/run/docker.sock:/var/run/docker.sock` under volumes. On Windows Docker Desktop, this path works as-is.

**Playbook says `host unreachable` for `kafka`/`elasticsearch`**
The controller must be on the same `stack` network. Verify with `docker network inspect docker_stack`.

**Logs directory empty**
The services need time to write logs. After `docker compose up -d`, wait 30-60s before running backup/rotate playbooks.

**Idempotency test fails (second run reports changed > 0)**
Check what changed: `.\ansible.ps1 playbooks\05-config-deploy.yml --diff`. The most common culprit is a template that includes a timestamp.

---

## Tearing Down

```powershell
# Stop everything but keep volumes (logs persist)
docker compose -f docker\docker-compose.yml down

# Stop and wipe ALL data
docker compose -f docker\docker-compose.yml down -v
Remove-Item -Recurse -Force docker\logs, docker\config, backups, archive -ErrorAction SilentlyContinue
```
