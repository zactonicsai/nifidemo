# Ansible Docker Lab

Project ID: `6f80779d-7811-4e0d-950a-ef8d188a5170`

This lab creates a small local Ansible practice environment using Docker Compose.

You get:

- `ansible-controller`: the machine where Ansible runs
- `target1`: a simulated Linux server reachable over SSH
- `target2`: another simulated Linux server reachable over SSH
- An Ansible playbook that installs and configures Nginx
- A custom Nginx config with custom access and error logs
- Helper scripts for starting, checking, and stopping the lab

> Note: SSH into containers is not the normal way to run Docker in production. This is a learning lab that simulates managing Linux servers with Ansible.

## Folder Structure

```text
ansible-docker-lab-6f80779d-7811-4e0d-950a-ef8d188a5170/
├── docker-compose.yml
├── Dockerfile.controller
├── Dockerfile.target
├── README.md
├── ansible/
│   ├── inventory.ini
│   ├── playbook.yml
│   ├── check.yml
│   └── custom_nginx.conf
└── scripts/
    ├── start.sh
    ├── run-playbook.sh
    ├── check.sh
    ├── stop.sh
    └── start.ps1
```

## Requirements

Install Docker Desktop:

- Windows: Docker Desktop with WSL2 enabled
- macOS: Docker Desktop
- Linux: Docker Engine and Docker Compose plugin

Check Docker:

```bash
docker --version
docker compose version
```

## Start the Lab

From this folder, run:

```bash
docker compose up -d --build
```

Or use the helper script on Mac/Linux:

```bash
chmod +x scripts/*.sh
./scripts/start.sh
```

On Windows PowerShell:

```powershell
.\scripts\start.ps1
```

## Open the Ansible Controller

```bash
docker exec -it ansible-controller bash
```

Inside the controller container, you will be in:

```text
/ansible
```

## Test Ansible Connectivity

Inside the controller:

```bash
ansible all -i inventory.ini -m ping
```

You should see a successful response from `target1` and `target2`.

## Run the Main Playbook

Inside the controller:

```bash
ansible-playbook -i inventory.ini playbook.yml
```

This installs Nginx, copies the custom config, creates a simple web page, and starts Nginx.

## View the Web Servers

From your host machine:

- target1: http://localhost:8081
- target2: http://localhost:8082

## Check Headers

Inside the controller:

```bash
curl -I http://target1
curl -I http://target2
```

Look for this header:

```text
X-Deployed-By: Ansible
```

## Check Logs

Inside the controller:

```bash
ansible webservers -i inventory.ini -m command -a "tail -n 20 /var/log/nginx/ansible_access.log"
ansible webservers -i inventory.ini -m command -a "tail -n 20 /var/log/nginx/ansible_error.log"
```

Or run the check playbook:

```bash
ansible-playbook -i inventory.ini check.yml
```

From your host:

```bash
./scripts/check.sh
```

## Test the Restart Handler

Edit:

```text
ansible/custom_nginx.conf
```

Change this line:

```nginx
add_header X-Deployed-By "Ansible";
```

Example:

```nginx
add_header X-Deployed-By "Ansible Lab Updated";
```

Run the playbook again:

```bash
docker exec -it ansible-controller bash -lc "ansible-playbook -i inventory.ini playbook.yml"
```

Ansible should report the config file as changed and run the `Restart Nginx` handler.

## Stop the Lab

```bash
docker compose down
```

Or:

```bash
./scripts/stop.sh
```

## Clean Rebuild

```bash
docker compose down -v
docker compose up -d --build
```

## Common Troubleshooting

### Container names already exist

Run:

```bash
docker compose down
```

Then start again.

### Ansible cannot connect by SSH

Check containers:

```bash
docker ps
```

Then test from the controller:

```bash
docker exec -it ansible-controller bash
ping target1
ssh root@target1
```

The lab password is:

```text
root
```

### Nginx page not showing

Run:

```bash
docker exec -it ansible-controller bash -lc "ansible-playbook -i inventory.ini check.yml"
```

Also check:

```bash
docker logs target1
docker logs target2
```

## Learning Notes

Important Ansible files:

- `inventory.ini`: server list and connection settings
- `playbook.yml`: tasks that configure the target servers
- `custom_nginx.conf`: config file copied to the web servers
- `check.yml`: troubleshooting and verification playbook

Important Ansible commands:

```bash
ansible all -i inventory.ini -m ping
ansible webservers -i inventory.ini -m command -a "hostname"
ansible-playbook -i inventory.ini playbook.yml
ansible-playbook -i inventory.ini check.yml
```
