#!/usr/bin/env bash
set -euo pipefail
docker exec -it ansible-controller bash -lc "ansible-playbook -i inventory.ini playbook.yml"
