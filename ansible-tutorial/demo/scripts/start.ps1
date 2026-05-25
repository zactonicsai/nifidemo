docker compose up -d --build
docker exec -it ansible-controller bash -lc "ansible all -i inventory.ini -m ping && ansible-playbook -i inventory.ini playbook.yml"
Write-Host ""
Write-Host "Open target1 at http://localhost:8081"
Write-Host "Open target2 at http://localhost:8082"
