#!/bin/bash
# Deploy Edge C2 Simulator to EC2
#
# Usage: ./scripts/deploy.sh
#
# Prerequisites:
#   1. EC2 instance set up with ec2-setup.sh
#   2. SSH access to deploy@<ec2-ip>
#   3. .env file configured on the server
#   4. Cloudflare origin certs in nginx/ssl/

set -euo pipefail

# Configuration — update these
EC2_HOST="${EC2_HOST:-deploy@ec2sim.brumbiesoft.org}"
DEPLOY_DIR="/opt/edge-c2-sim"
COMPOSE_FILE="docker-compose.prod.yml"

echo "╔══════════════════════════════════════════╗"
echo "║  Deploying Edge C2 Simulator              ║"
echo "╚══════════════════════════════════════════╝"

echo "[1/4] Syncing files to server..."
rsync -avz --delete \
    --exclude '.git' \
    --exclude 'node_modules' \
    --exclude '__pycache__' \
    --exclude '.env' \
    --exclude 'nginx/ssl/*.pem' \
    --exclude 'logs/' \
    --exclude '.pytest_cache' \
    --exclude 'cop/dist' \
    ./ "${EC2_HOST}:${DEPLOY_DIR}/"

echo "[2/4] Building containers on server..."
ssh "${EC2_HOST}" "cd ${DEPLOY_DIR} && sudo docker compose -f ${COMPOSE_FILE} build"

echo "[3/4] Restarting services..."
ssh "${EC2_HOST}" "cd ${DEPLOY_DIR} && sudo docker compose -f ${COMPOSE_FILE} down --timeout 10"
ssh "${EC2_HOST}" "cd ${DEPLOY_DIR} && sudo docker compose -f ${COMPOSE_FILE} up -d"

echo "[4/4] Checking health..."
sleep 10
ssh "${EC2_HOST}" "curl -sf http://localhost/health | jq ."

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║  Deployment complete!                     ║"
echo "║  https://ec2sim.brumbiesoft.org            ║"
echo "╚══════════════════════════════════════════╝"
