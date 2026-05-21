#!/bin/bash
# =============================================================================
# LocalStack Initialization — runs once after LocalStack is ready
# Creates all SQS queues, SNS topics, and S3 buckets for FreshMart
# =============================================================================

set -e

export AWS_DEFAULT_REGION=us-east-1
export AWS_ACCESS_KEY_ID=test
export AWS_SECRET_ACCESS_KEY=test
ENDPOINT=http://localhost:4566

echo "═══════════════════════════════════════════════════════════════"
echo "  FreshMart — LocalStack Init"
echo "═══════════════════════════════════════════════════════════════"

# ── SQS Queues ──────────────────────────────────────────────────────────────
echo "▸ Creating SQS queues..."

awslocal sqs create-queue \
  --queue-name freshmart-inventory-updates \
  --attributes VisibilityTimeout=30,MessageRetentionPeriod=86400

awslocal sqs create-queue \
  --queue-name freshmart-urgent-alerts.fifo \
  --attributes FifoQueue=true,ContentBasedDeduplication=true

awslocal sqs create-queue \
  --queue-name freshmart-reorder-alerts.fifo \
  --attributes FifoQueue=true,ContentBasedDeduplication=true

awslocal sqs create-queue \
  --queue-name freshmart-pos-system-queue

awslocal sqs create-queue \
  --queue-name freshmart-mobile-app-queue

awslocal sqs create-queue \
  --queue-name freshmart-esl-labels-queue

awslocal sqs create-queue \
  --queue-name freshmart-dlq

# ── SNS Topics ──────────────────────────────────────────────────────────────
echo "▸ Creating SNS topics..."

awslocal sns create-topic --name freshmart-product-recalls
awslocal sns create-topic --name freshmart-planogram-updates

# ── SNS → SQS subscriptions (fan-out) ───────────────────────────────────────
echo "▸ Wiring SNS → SQS fan-out..."

RECALL_ARN=$(awslocal sns list-topics \
  --query "Topics[?contains(TopicArn,'recalls')].TopicArn" --output text)
PLAN_ARN=$(awslocal sns list-topics \
  --query "Topics[?contains(TopicArn,'planogram')].TopicArn" --output text)

ALERTS_URL=$(awslocal sqs get-queue-url \
  --queue-name freshmart-urgent-alerts.fifo --query QueueUrl --output text)
POS_URL=$(awslocal sqs get-queue-url \
  --queue-name freshmart-pos-system-queue --query QueueUrl --output text)
MOBILE_URL=$(awslocal sqs get-queue-url \
  --queue-name freshmart-mobile-app-queue --query QueueUrl --output text)
ESL_URL=$(awslocal sqs get-queue-url \
  --queue-name freshmart-esl-labels-queue --query QueueUrl --output text)

awslocal sns subscribe --topic-arn "$RECALL_ARN" --protocol sqs --notification-endpoint "$ALERTS_URL"
awslocal sns subscribe --topic-arn "$PLAN_ARN"   --protocol sqs --notification-endpoint "$POS_URL"
awslocal sns subscribe --topic-arn "$PLAN_ARN"   --protocol sqs --notification-endpoint "$MOBILE_URL"
awslocal sns subscribe --topic-arn "$PLAN_ARN"   --protocol sqs --notification-endpoint "$ESL_URL"

# ── S3 Buckets ──────────────────────────────────────────────────────────────
echo "▸ Creating S3 buckets..."
awslocal s3 mb s3://freshmart-data-lake
awslocal s3 mb s3://freshmart-archive
awslocal s3 mb s3://freshmart-errors

echo ""
echo "✓ LocalStack init complete."
echo ""
echo "Queues:"
awslocal sqs list-queues
echo ""
echo "Topics:"
awslocal sns list-topics
echo ""
echo "Buckets:"
awslocal s3 ls
