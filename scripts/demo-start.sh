#!/bin/bash
#
# Edge C2 Simulator — Quick Demo Start
#
# Prerequisites:
# 1. Docker Desktop installed
# 2. CESIUM_ION_TOKEN in .env file
# 3. That's it.

set -e

echo ""
echo "  Edge C2 Simulator - Demo Start"
echo "  ==============================="
echo ""

# Check .env
if [ ! -f .env ]; then
  if [ -f .env.example ]; then
    echo "WARNING: .env not found. Copying from .env.example"
    echo "         Edit .env and add your Cesium Ion token."
    cp .env.example .env
  else
    echo "ERROR: .env file not found. Copy .env.example and add your Cesium token."
    exit 1
  fi
fi

# Check Cesium token
source .env
if [ -z "$CESIUM_ION_TOKEN" ]; then
  echo "WARNING: CESIUM_ION_TOKEN not set in .env"
  echo "         COP will load but map tiles may not render."
  echo "         Get a free token at: https://ion.cesium.com/signup"
  echo ""
fi

# Build and start
echo "Building containers..."
docker-compose build --quiet

echo "Starting simulator and COP..."
docker-compose up -d

echo ""
echo "  Simulator:  ws://localhost:8765"
echo "  Health:     http://localhost:8766/health"
echo "  COP:        http://localhost:3000"
echo ""
echo "  Open http://localhost:3000 in Chrome (fullscreen recommended)"
echo ""
echo "  Controls:"
echo "    Space = Play/Pause"
echo "    1-5   = Speed (1x/2x/5x/10x/60x)"
echo "    D     = Demo mode (auto-camera)"
echo "    F     = Fullscreen"
echo ""
echo "  To stop: docker-compose down"
echo ""
