#!/bin/bash
# Server management quick commands
# Source this file: source scripts/server-commands.sh
# Then run commands like: sim-logs, sim-restart, etc.

COMPOSE="sudo docker compose -f /opt/edge-c2-sim/docker-compose.prod.yml"
PROJECT_DIR="/opt/edge-c2-sim"

# View logs
alias sim-logs="cd $PROJECT_DIR && $COMPOSE logs -f"
alias sim-logs-sim="cd $PROJECT_DIR && $COMPOSE logs -f simulator"
alias sim-logs-cop="cd $PROJECT_DIR && $COMPOSE logs -f cop"
alias sim-logs-auth="cd $PROJECT_DIR && $COMPOSE logs -f auth-service"
alias sim-logs-nginx="cd $PROJECT_DIR && $COMPOSE logs -f nginx"

# Service management
alias sim-restart="cd $PROJECT_DIR && $COMPOSE restart"
alias sim-stop="cd $PROJECT_DIR && $COMPOSE down"
alias sim-start="cd $PROJECT_DIR && $COMPOSE up -d"
alias sim-rebuild="cd $PROJECT_DIR && $COMPOSE up -d --build"
alias sim-status="cd $PROJECT_DIR && $COMPOSE ps"

# Health check
alias sim-health="curl -sf http://localhost/health | jq ."

# User management (via auth service API)
sim-add-user() {
    local username=$1
    local password=$2
    local role=${3:-viewer}
    curl -sf -X POST http://localhost:8080/auth/api/users \
        -H "Content-Type: application/json" \
        -d "{\"username\":\"$username\",\"password\":\"$password\",\"role\":\"$role\"}" | jq .
}

sim-list-users() {
    curl -sf http://localhost:8080/auth/api/users | jq .
}

# Scenario management
sim-change-scenario() {
    local scenario=$1
    echo "Changing scenario to: $scenario"
    cd $PROJECT_DIR
    SCENARIO="$scenario" $COMPOSE up -d simulator
}
