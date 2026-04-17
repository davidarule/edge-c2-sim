#!/usr/bin/env bash
# Start the simulator + COP frontend for local development.
# Usage: ./scripts/start_local.sh [scenario] [speed]
#   scenario: path to YAML (default: config/scenarios/sulu_sea_fishing_intercept.yaml)
#   speed:    sim speed multiplier (default: 10)

set -e

SCENARIO="${1:-config/scenarios/sulu_sea_fishing_intercept.yaml}"
SPEED="${2:-10}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cleanup() {
    echo ""
    echo "Shutting down..."
    # Kill child processes
    [ -n "$SIM_PID" ] && kill "$SIM_PID" 2>/dev/null
    [ -n "$COP_PID" ] && kill "$COP_PID" 2>/dev/null
    wait 2>/dev/null
    echo "Done."
}
trap cleanup EXIT INT TERM

# Start simulator in background
echo "Starting simulator: $SCENARIO (${SPEED}x)"
python3 "$SCRIPT_DIR/run_simulator.py" -s "$SCENARIO" --speed "$SPEED" &
SIM_PID=$!

# Start COP dev server in background
echo "Starting COP frontend..."
cd "$PROJECT_DIR/cop"
npm run dev &
COP_PID=$!
cd "$PROJECT_DIR"

echo ""
echo "=== Edge C2 Local Dev ==="
echo "  Simulator: ws://localhost:8765"
echo "  COP:       http://localhost:5173"
echo "  Press Ctrl+C to stop both"
echo "========================="
echo ""

# Wait for either to exit
wait -n "$SIM_PID" "$COP_PID" 2>/dev/null
