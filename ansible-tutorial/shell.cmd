@echo off
REM shell.cmd - drop into an interactive shell inside the controller container.
REM Use this when you want to run multiple ansible/ansible-playbook commands
REM without the overhead of starting a new container each time.

setlocal
cd /d "%~dp0"
docker compose -f docker\docker-compose.yml --profile controller run --rm -it controller bash
endlocal
