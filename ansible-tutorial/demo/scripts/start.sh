#!/usr/bin/env bash
set -euo pipefail

echo ">> Building and starting containers..."
docker compose up -d --build

echo ">> Waiting for targets to report healthy..."
for c in target1 target2; do
  for i in {1..30}; do
    status=$(docker inspect --format '{{.State.Health.Status}}' "$c" 2>/dev/null || echo starting)
    if [ "$status" = "healthy" ]; then
      echo "   $c: healthy"
      break
    fi
    sleep 1
  done
done

echo ">> Verifying Ansible can control targets..."
docker exec ansible-controller bash -lc "ansible all -i inventory.ini -m ping"
docker exec ansible-controller bash -lc "ansible-playbook -i inventory.ini verify.yml"

echo ">> Running main playbook..."
docker exec ansible-controller bash -lc "ansible-playbook -i inventory.ini playbook.yml"

echo
echo "Open target1 at http://localhost:8081"
echo "Open target2 at http://localhost:8082"
