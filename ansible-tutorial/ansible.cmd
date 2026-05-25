@echo off
REM ansible.cmd - Windows entry point for running Ansible commands.
REM
REM This wraps `docker compose run --rm controller ansible-playbook ...`
REM so you can type `ansible playbooks\01-health-check.yml` from PowerShell
REM or cmd.exe and have it run inside the controller container.
REM
REM Examples:
REM   ansible playbooks\01-health-check.yml
REM   ansible playbooks\05-config-deploy.yml --check --diff
REM   ansible playbooks\02-restart-service.yml -e target_service=kafka
REM
REM First-run: build the controller image
REM   docker compose -f docker\docker-compose.yml --profile controller build controller

setlocal
cd /d "%~dp0"
docker compose -f docker\docker-compose.yml --profile controller run --rm controller ansible-playbook %*
endlocal
