# ansible.ps1 - PowerShell entry point for running Ansible via the controller.
#
# Examples:
#   .\ansible.ps1 playbooks\01-health-check.yml
#   .\ansible.ps1 playbooks\05-config-deploy.yml --check --diff
#   .\ansible.ps1 playbooks\02-restart-service.yml -e target_service=kafka
#
# If you get an execution-policy error, run once:
#   Set-ExecutionPolicy -Scope CurrentUser RemoteSigned

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

docker compose -f docker\docker-compose.yml --profile controller run --rm controller ansible-playbook @args
