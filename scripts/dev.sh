#!/usr/bin/env bash
# =============================================================================
# FreshMart — Convenience commands
# Usage:  ./scripts/dev.sh up | down | reset | logs | psql | kafka-topics
# =============================================================================
set -e
cd "$(dirname "$0")/.."

case "${1:-help}" in
  up)            docker compose up -d --build && echo "✓ Stack up. Dashboard: http://localhost:8000" ;;
  down)          docker compose down ;;
  reset)         docker compose down -v && echo "✓ Everything wiped." ;;
  logs)          docker compose logs -f ${2:-} ;;
  psql)          docker exec -it freshmart-postgres psql -U nifi -d freshmart_dw ;;
  kafka-topics)  docker exec freshmart-kafka kafka-topics --bootstrap-server localhost:29092 --list ;;
  kafka-peek)    docker exec freshmart-kafka kafka-console-consumer \
                   --bootstrap-server localhost:29092 --topic "${2:-pos-sales}" --from-beginning --max-messages 10 ;;
  sqs-list)      docker exec freshmart-localstack awslocal sqs list-queues ;;
  smoke)         bash scripts/smoke-test.sh ;;
  *)
    echo "Usage:  ./scripts/dev.sh {up|down|reset|logs <svc>|psql|kafka-topics|kafka-peek <topic>|sqs-list|smoke}"
    exit 1
    ;;
esac
