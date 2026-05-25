# Start the Ansible Docker lab on Windows.
$ErrorActionPreference = "Stop"

Write-Host ">> Building and starting containers..."
docker compose up -d --build

Write-Host ">> Waiting for targets to report healthy..."
foreach ($c in @("target1", "target2")) {
    for ($i = 0; $i -lt 30; $i++) {
        $status = docker inspect --format '{{.State.Health.Status}}' $c 2>$null
        if ($status -eq "healthy") {
            Write-Host "   $c: healthy"
            break
        }
        Start-Sleep -Seconds 1
    }
}

Write-Host ">> Verifying Ansible can control targets..."
docker exec ansible-controller bash -lc "ansible all -i inventory.ini -m ping"
docker exec ansible-controller bash -lc "ansible-playbook -i inventory.ini verify.yml"

Write-Host ">> Running main playbook..."
docker exec ansible-controller bash -lc "ansible-playbook -i inventory.ini playbook.yml"

Write-Host ""
Write-Host "Open target1 at http://localhost:8081"
Write-Host "Open target2 at http://localhost:8082"
