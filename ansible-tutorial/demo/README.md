# Ansible Docker Lab (fixed)

A small local Ansible practice environment built with Docker Compose.

## What's in this lab

- `ansible-controller` — Ubuntu 24.04 + latest Ansible (installed via pipx from PyPI)
- `target1`, `target2` — Ubuntu 24.04 + sshd + pre-installed nginx + `python3-apt`
- `ansible/playbook.yml` — configures nginx with a custom config and a hello-world page
- `ansible/verify.yml` — proves the controller can actually control the targets
- `ansible/check.yml` — operational sanity check (process, HTTP, logs)
- Helper scripts in `scripts/`

> SSH-into-containers is **not** how you'd run Docker in production. This is a
> learning lab where the targets simulate Linux servers managed over SSH.

## What changed vs. the original

| Issue | Fix |
|---|---|
| Ubuntu 22.04 base | Bumped to **24.04 LTS (Noble)** |
| `ppa:ansible/ansible` has no `noble` release → build fails | Install Ansible via **pipx** from PyPI |
| Target missing `python3-apt` → slow/warning on `apt` module | Pre-installed `python3-apt` |
| Nginx installed every playbook run → slow, breaks offline | Pre-installed `nginx` on the target image |
| No SSH host keys generated → sshd can fail to start | Added `ssh-keygen -A` |
| sshd sed config fragile across Ubuntu versions | Use a drop-in `/etc/ssh/sshd_config.d/00-lab.conf` |
| Controller starts before sshd is ready → first ping flaky | Added healthchecks + `depends_on: condition: service_healthy` |
| `service` module status unreliable without systemd | Use `pgrep` + `nginx -s reload` directly |
| No way to verify controller→target control plane works | New `verify.yml` playbook + `scripts/verify.sh` |

The playbooks pass `ansible-lint` at the **production** profile.

## Folder structure

```text
.
├── docker-compose.yml
├── Dockerfile.controller
├── Dockerfile.target
├── README.md
├── ansible/
│   ├── inventory.ini
│   ├── playbook.yml
│   ├── verify.yml
│   ├── check.yml
│   └── custom_nginx.conf
└── scripts/
    ├── start.sh
    ├── start.ps1
    ├── run-playbook.sh
    ├── verify.sh
    ├── check.sh
    └── stop.sh
```

## Requirements

- Docker Desktop (Windows/macOS) or Docker Engine + Compose plugin (Linux)

```bash
docker --version
docker compose version
```

## Start the lab

```bash
docker compose up -d --build
```

Or use the helper script which also runs verification automatically:

```bash
chmod +x scripts/*.sh
./scripts/start.sh
```

On Windows PowerShell:

```powershell
.\scripts\start.ps1
```

## Verify Ansible can control the targets

This is the key answer to "verify I can use the ansible docker controller to
control other services". Run:

```bash
./scripts/verify.sh
```

or, equivalently:

```bash
docker exec -it ansible-controller bash -lc "ansible-playbook -i inventory.ini verify.yml"
```

`verify.yml` walks every layer of the control plane and fails loudly on any
problem:

1. SSH + Python (the `ping` module)
2. Fact gathering (distribution, kernel)
3. Privilege escalation (`whoami` must be `root` after `become: true`)
4. File write (`copy` module)
5. File read-back (`slurp` module)
6. Package manager (`dpkg-query` for the nginx version)
7. HTTP reachability of the managed service (`uri` module, expects 200)
8. Cleanup

If every task is green on both `target1` and `target2`, the controller is
fully wired up.

## Quick one-liner connectivity test

```bash
docker exec -it ansible-controller bash -lc "ansible all -i inventory.ini -m ping"
```

Expected:

```
target1 | SUCCESS => { "changed": false, "ping": "pong" }
target2 | SUCCESS => { "changed": false, "ping": "pong" }
```

## Run the main playbook

```bash
docker exec -it ansible-controller bash -lc "ansible-playbook -i inventory.ini playbook.yml"
```

This deploys the custom nginx config, drops in a hello-world page, and
ensures nginx is running.

## View the web servers

- target1: <http://localhost:8081>
- target2: <http://localhost:8082>

Check the `X-Deployed-By: Ansible` header:

```bash
curl -I http://localhost:8081
curl -I http://localhost:8082
```

## Operational check

```bash
./scripts/check.sh
```

Runs `check.yml`, which inspects the nginx process, hits the local endpoint,
and tails the custom access log.

## Test the restart handler

Edit `ansible/custom_nginx.conf` — for example, change:

```nginx
add_header X-Deployed-By "Ansible";
```

to:

```nginx
add_header X-Deployed-By "Ansible Lab Updated";
```

Then re-run the playbook. The `Restart Nginx` handler should fire because
the config file changed.

## Stop the lab

```bash
docker compose down
```

## Clean rebuild

```bash
docker compose down -v
docker compose up -d --build
```

## Troubleshooting

**Container names already exist** — `docker compose down`, then start again.

**Ansible can't SSH** — confirm containers are up and target health is green:

```bash
docker ps
docker inspect --format '{{.State.Health.Status}}' target1
```

Then from inside the controller:

```bash
docker exec -it ansible-controller bash
ssh root@target1   # password: root
```

**Nginx page not showing** — run the check playbook and inspect logs:

```bash
./scripts/check.sh
docker logs target1
docker logs target2
```

## Key files

- `inventory.ini` — host list + connection settings
- `playbook.yml` — main configuration playbook
- `verify.yml` — control-plane verification playbook
- `check.yml` — operational sanity check
- `custom_nginx.conf` — nginx server block deployed to the targets
