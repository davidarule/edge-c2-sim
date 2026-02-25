# Claude Code — Phase 5 Task Brief: Polish & Demo Preparation

## Context

Phases 0-4 built the complete system: simulation engine, COP dashboard, REST 
adapter, and TAK integration. Phase 5 is about making everything presentation-
ready for the April 2026 demo to senior Malaysian defense/security officials.

This phase is about the difference between "works" and "impresses."

**Demo environment:** Laptop connected to a large display (projector or wall 
screen) in a briefing room. Audience: senior military and security officials 
who will judge Edge C2's capability by what they see on screen.

---

## Task 1: COP Visual Polish

### 1a. Smooth Entity Animation

Current state: entities jump between positions on each WebSocket update.
Target: entities glide smoothly between updates.

```javascript
/**
 * Use Cesium SampledPositionProperty for position interpolation.
 * 
 * Instead of directly setting entity.position, add time-stamped samples.
 * Cesium interpolates between samples automatically, creating smooth movement.
 */

function updateEntityPosition(cesiumEntity, newPos, timestamp) {
  // If entity doesn't have sampled position yet, create one
  if (!(cesiumEntity.position instanceof Cesium.SampledPositionProperty)) {
    const sampled = new Cesium.SampledPositionProperty();
    sampled.setInterpolationOptions({
      interpolationDegree: 1,  // Linear interpolation
      interpolationAlgorithm: Cesium.LinearApproximation
    });
    cesiumEntity.position = sampled;
  }
  
  const time = Cesium.JulianDate.fromIso8601(timestamp);
  cesiumEntity.position.addSample(
    time,
    Cesium.Cartesian3.fromDegrees(newPos.longitude, newPos.latitude, newPos.altitude_m || 0)
  );
  
  // Keep sample buffer bounded (last 30 samples)
  // Note: Cesium doesn't have a built-in way to trim samples, 
  // so you may need to recreate the property periodically
}
```

**Important:** This requires the Cesium viewer clock to be synced with the 
simulation clock. Add clock sync logic:

```javascript
function syncCesiumClock(viewer, simTime, speed, running) {
  const julianTime = Cesium.JulianDate.fromIso8601(simTime);
  viewer.clock.currentTime = julianTime;
  viewer.clock.multiplier = speed;
  viewer.clock.shouldAnimate = running;
  viewer.clock.clockStep = Cesium.ClockStep.SYSTEM_CLOCK_MULTIPLIER;
}
```

### 1b. Track Trail Fade

Trails should fade from bright (newest point) to transparent (oldest):

```javascript
// Use Cesium PolylineGlowMaterialProperty or custom material
const trail = viewer.entities.add({
  polyline: {
    positions: trailPositions,
    width: 3,
    material: new Cesium.PolylineGlowMaterialProperty({
      glowPower: 0.2,
      color: agencyColor.withAlpha(0.6)
    })
  }
});
```

Or for per-segment fading, use a `ColorMaterialProperty` per segment with 
decreasing alpha.

### 1c. Event Toast Notifications

When a CRITICAL event fires, show a brief notification overlay in the viewport:

```javascript
function showToast(event) {
  const toast = document.createElement('div');
  toast.className = `toast toast-${event.severity.toLowerCase()}`;
  toast.innerHTML = `
    <span class="toast-agency">${event.alert_agencies?.[0] || 'ESSCOM'}</span>
    <span class="toast-text">${event.description}</span>
  `;
  document.getElementById('toast-container').appendChild(toast);
  
  // Auto-remove after 5 seconds
  setTimeout(() => toast.classList.add('toast-exit'), 4000);
  setTimeout(() => toast.remove(), 5000);
}
```

```css
#toast-container {
  position: absolute;
  top: 60px;
  right: 220px;
  z-index: 1000;
  display: flex;
  flex-direction: column;
  gap: 8px;
  pointer-events: none;
}

.toast {
  padding: 10px 16px;
  border-radius: 4px;
  background: rgba(13, 17, 23, 0.9);
  border-left: 3px solid;
  font-size: 13px;
  max-width: 400px;
  animation: slideIn 0.3s ease-out;
}
.toast-exit { animation: slideOut 0.3s ease-in forwards; }
.toast-critical { border-color: #F85149; background: rgba(61, 17, 23, 0.95); }
.toast-warning { border-color: #D29922; }
.toast-info { border-color: #58A6FF; }
.toast-agency {
  font-weight: 600;
  margin-right: 8px;
  font-size: 11px;
  text-transform: uppercase;
}
```

### 1d. Entity Clustering at Low Zoom

When the camera is above 500km altitude, cluster nearby entities into 
count badges to avoid visual clutter:

```javascript
// Simple approach: hide individual entities, show aggregate markers
function updateClustering(cameraAltitude) {
  if (cameraAltitude > 500000) {
    // Group entities by grid cell (e.g., 0.5° grid)
    const clusters = groupByGrid(getAllEntities(), 0.5);
    showClusterMarkers(clusters);
    hideIndividualEntities();
  } else {
    hideClusterMarkers();
    showIndividualEntities();
  }
}
```

Cluster marker: Circle with count and dominant agency color.

### 1e. Mini-map

Small overview map in bottom-left corner showing full ESSZONE with entity dots:

```javascript
// Use a second Cesium viewer in a small div (150x150px)
// Or use a simple Canvas/SVG rendering:
function renderMinimap(canvas, entities, esszoneBounds) {
  const ctx = canvas.getContext('2d');
  ctx.fillStyle = '#0D1117';
  ctx.fillRect(0, 0, 150, 150);
  
  // Draw ESSZONE outline
  // Draw entity dots (colored by agency)
  // Draw camera viewport rectangle
}
```

Avoid a second Cesium instance (too heavy). Use Canvas 2D for the minimap.

---

## Task 2: Scenario Polish

### 2a. Realistic Background Traffic

Current: background entities auto-generated with basic patrol/route movement.
Polish: add more varied and realistic behavior.

- **Fishing boats:** Drift at 2-4 kts for 20-30 min (nets out), then move 
  at 6-8 kts to new spot. Cluster in groups of 3-5 near fishing grounds.
- **Cargo ships:** Follow Sulu Sea transit corridor at steady 12-16 kts. 
  Some slow down near Sandakan port (approaching/departing).
- **Tankers:** Slower (10-12 kts), steady course.
- **Dive boats:** Short hops between Sipadan/Mabul/Kapalai islands, 
  15-20 kts, stop for 45-60 min at each.
- **Aircraft:** Commercial flights pass through at 35000 ft, 450 kts. 
  Light aircraft at 5000-10000 ft.

### 2b. Day/Night Cycle

Tie CesiumJS globe lighting to simulation time:

```javascript
// Simulation starts at 0800 local (UTC+8), so UTC 0000
// Sun position reflects this
viewer.scene.globe.enableLighting = true;
viewer.clock.currentTime = /* sim time as Julian */;
// CesiumJS automatically calculates sun position from clock time
```

When demo runs in real-time through morning hours, the lighting naturally shifts.

### 2c. Weather Overlay (Optional)

If time permits, add a cloud cover layer for visual richness:

```javascript
// Use Cesium's weather visualization or a semi-transparent cloud tile layer
// Simple approach: static semi-transparent cloud texture at 10000m altitude
```

This is nice-to-have only. Don't spend more than 2 hours on it.

---

## Task 3: Demo Automation

### 3a. Narrated Demo Mode Enhancements

Extend the Phase 3 demo mode with:

1. **Pre-scripted camera movements** tied to combined scenario events:
   ```yaml
   # demo_camera_script.yaml
   camera_moves:
     - time: "00:00"
       description: "Opening shot — ESSZONE overview"
       position: { lat: 5.00, lon: 118.50, alt: 300000 }
       pitch: -45
       duration: 0  # Instant
       
     - time: "00:02"
       description: "Zoom to radar detection area"
       position: { lat: 5.80, lon: 118.88, alt: 80000 }
       pitch: -60
       duration: 3.0
       
     - time: "00:25"
       description: "Follow the chase — fleet scattering"
       track_entity: "IFF-004"
       altitude: 15000
       duration: 2.0
       
     - time: "00:35"
       description: "Boarding close-up"
       position: { lat: 5.50, lon: 119.00, alt: 3000 }
       pitch: -75
       duration: 2.5
   ```

2. **Scenario title cards** — At transitions (Part 1 → Part 2), show a full-
   screen overlay with scenario name and brief description, fading after 5 seconds.

3. **Entity highlight** — When an event references a specific entity, pulse 
   its symbol larger for 3 seconds to draw attention.

### 3b. Presenter Controls

A discrete floating toolbar (only visible to the presenter) with:

- **Scenario selector** dropdown
- **Demo mode** on/off toggle
- **Jump to event** — skip to any event in the timeline
- **Reset** — restart from beginning
- **Speed** quick buttons
- **Fullscreen** toggle

Position: small floating panel at top-left, semi-transparent, auto-hides 
after 5 seconds of no hover.

### 3c. Keyboard Shortcuts

```
Space       — Play / Pause
1-5         — Speed (1x, 2x, 5x, 10x, 60x)
D           — Toggle demo mode
F           — Fullscreen
R           — Reset scenario
Escape      — Cancel follow mode / close detail panel
Arrow keys  — Pan camera
+ / -       — Zoom in / out
```

---

## Task 4: Performance Optimization

### 4a. Target: 100+ entities at 60 FPS

Profile and optimize:

1. **WebSocket message batching:**
   - Simulator: send `entity_batch` every 100ms with all entity states
   - Don't send individual `entity_update` when >10 entities
   - Client: process batch in single `requestAnimationFrame` callback

2. **Billboard pooling:**
   - Don't create/destroy Cesium entities frequently
   - Pre-allocate a pool of 150 billboard entities
   - Assign/unassign to simulation entities as needed
   - Unassigned pool entities: `show = false`

3. **Symbol caching:**
   - milsymbol generation is expensive (~5ms per symbol)
   - Cache generated DataURLs in a Map keyed by SIDC + size
   - Only regenerate on SIDC change (rare)

4. **Trail updates:**
   - Don't update trail polylines every frame
   - Update trails every 5th position sample
   - Use `CallbackProperty` to avoid entity recreation

5. **Throttle non-critical updates:**
   - Entity counts in sidebar: update every 1 second
   - Minimap: redraw every 2 seconds
   - Clock display: update every 100ms

### 4b. Test on target hardware

Create a performance test scenario:

```yaml
# config/scenarios/perf_test.yaml
scenario:
  name: "Performance Test — 150 Entities"
  background_entities:
    - type: CIVILIAN_FISHING
      count: 60
      area: "esszone_sector_2_sandakan"
    - type: CIVILIAN_CARGO
      count: 30
      route: "sulu_sea_transit_corridor"
    - type: CIVILIAN_TANKER
      count: 20
      route: "sandakan_export_route"
    - type: CIVILIAN_LIGHT
      count: 10
      route: "kk_sandakan_corridor"
  scenario_entities:
    # 30 named entities across all agencies
    # ... (generate variety of types)
  events: []  # No events, just traffic
```

Run this at 10x speed and verify:
- COP maintains 60 FPS
- WebSocket doesn't back up
- No memory leak over 10-minute run
- Browser tab memory stays under 500MB

---

## Task 5: Error Handling & Resilience

### 5a. Graceful degradation

| Failure | Behavior |
|---------|----------|
| Edge C2 API down | REST adapter logs warning, continues simulation. COP still works. |
| WebSocket disconnect | COP auto-reconnects, requests snapshot on reconnect |
| FreeTAKServer down | CoT adapter logs warning, continues simulation |
| Invalid scenario YAML | Clear error message, don't crash |
| Browser tab crash | COP recovers on refresh, reconnects to running sim |
| Simulator crash | COP shows "DISCONNECTED" status, pauses display |

### 5b. Health check endpoint

Add a health check HTTP endpoint on the simulator:

```python
# GET http://localhost:8766/health
# Returns:
{
  "status": "running",
  "scenario": "ESSZONE Multi-Domain Operations",
  "sim_time": "2026-04-15T08:14:32Z",
  "speed": 5.0,
  "entities": 47,
  "events_fired": 12,
  "events_total": 34,
  "uptime_seconds": 342,
  "transports": {
    "websocket": {"status": "ok", "clients": 1},
    "rest": {"status": "ok", "last_push": "2026-04-15T08:14:30Z"},
    "console": {"status": "ok"}
  }
}
```

### 5c. Logging

Structured logging throughout the simulator:

```python
import logging
import json

# JSON-formatted log lines
logging.basicConfig(
    format='{"time": "%(asctime)s", "level": "%(levelname)s", "module": "%(name)s", "message": "%(message)s"}',
    level=logging.INFO
)

# Key log events:
# - Scenario loaded (entity count, event count, duration)
# - Entity created/updated/removed (at DEBUG level)
# - Event fired (at INFO level)
# - Transport push success/failure
# - REST API response codes
# - WebSocket client connect/disconnect
# - Performance metrics every 30 seconds (entity count, update rate, latency)
```

---

## Task 6: Docker Packaging

### 6a. Final docker-compose.yml

```yaml
version: '3.8'

services:
  simulator:
    build:
      context: .
      dockerfile: Dockerfile
    ports:
      - "8765:8765"    # WebSocket
      - "8766:8766"    # Health check
    environment:
      - SCENARIO=${SCENARIO:-config/scenarios/demo_combined.yaml}
      - SIM_SPEED=${SIM_SPEED:-1}
      - EDGE_C2_URL=${EDGE_C2_URL:-}
      - EDGE_C2_API_KEY=${EDGE_C2_API_KEY:-}
      - REST_DRY_RUN=${REST_DRY_RUN:-true}
    volumes:
      - ./config:/app/config
      - ./geodata:/app/geodata
      - ./logs:/app/logs
    command: >
      edge-c2-sim 
        --scenario ${SCENARIO:-config/scenarios/demo_combined.yaml}
        --speed ${SIM_SPEED:-1}
        --transport ws,console${REST_TRANSPORT:-}
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8766/health"]
      interval: 10s
      timeout: 5s
      retries: 3

  cop:
    build:
      context: ./cop
      args:
        - VITE_CESIUM_ION_TOKEN=${CESIUM_ION_TOKEN}
        - VITE_WS_URL=${WS_URL:-ws://localhost:8765}
    ports:
      - "3000:3000"
    depends_on:
      simulator:
        condition: service_healthy

  # Optional TAK server
  freetakserver:
    image: freetakteam/freetakserver:latest
    ports:
      - "8087:8087"
      - "8443:8443"
      - "19023:19023"
    profiles:
      - tak

volumes:
  fts_data:
```

### 6b. Quick-start script

```bash
#!/bin/bash
# scripts/demo-start.sh
#
# Quick start for demo. Just run: ./scripts/demo-start.sh
#
# Prerequisites:
# 1. Docker Desktop installed
# 2. CESIUM_ION_TOKEN in .env file
# 3. That's it.

set -e

echo "╔══════════════════════════════════════════╗"
echo "║     Edge C2 Simulator — Demo Start       ║"
echo "╚══════════════════════════════════════════╝"

# Check .env
if [ ! -f .env ]; then
  echo "ERROR: .env file not found. Copy .env.example and add your Cesium token."
  exit 1
fi

# Check Cesium token
source .env
if [ -z "$CESIUM_ION_TOKEN" ]; then
  echo "ERROR: CESIUM_ION_TOKEN not set in .env"
  exit 1
fi

# Build and start
echo "Building containers..."
docker-compose build

echo "Starting simulator and COP..."
docker-compose up -d

echo ""
echo "✓ Simulator running on ws://localhost:8765"
echo "✓ Health check: http://localhost:8766/health"
echo "✓ COP Dashboard: http://localhost:3000"
echo ""
echo "Open http://localhost:3000 in Chrome (fullscreen recommended)"
echo ""
echo "Controls:"
echo "  Space = Play/Pause"
echo "  1-5   = Speed (1x/2x/5x/10x/60x)"
echo "  D     = Demo mode (auto-camera)"
echo "  F     = Fullscreen"
echo ""
echo "To stop: docker-compose down"
```

### 6c. .env.example

```bash
# Edge C2 Simulator Configuration
# Copy this to .env and fill in values

# REQUIRED: Cesium Ion token (free: https://ion.cesium.com/signup)
CESIUM_ION_TOKEN=

# Scenario to run (default: combined demo)
SCENARIO=config/scenarios/demo_combined.yaml

# Starting simulation speed
SIM_SPEED=1

# WebSocket URL for COP (change if running on different host)
WS_URL=ws://localhost:8765

# Edge C2 API (leave empty to skip REST integration)
EDGE_C2_URL=
EDGE_C2_API_KEY=
REST_DRY_RUN=true

# Optional: REST transport (add ,rest to enable)
REST_TRANSPORT=
```

---

## Task 7: README

Write the project README.md:

```markdown
# Edge C2 Simulator

Multi-domain C2 simulation demonstrating coordinated security operations 
across Malaysian agencies in the Eastern Sabah Security Zone (ESSZONE).

## Quick Start

1. Get a free Cesium Ion token: https://ion.cesium.com/signup
2. Copy `.env.example` to `.env`, add your token
3. Run: `./scripts/demo-start.sh`
4. Open: http://localhost:3000

## Scenarios

- **IUU Fishing Intercept** — Vietnamese illegal fishing fleet detected and 
  intercepted by MMEA, RMN, RMAF, RMP, and Customs
- **Kidnapping-for-Ransom Response** — Armed militant incursion near Semporna, 
  full ESSCOM multi-agency response
- **Combined Demo** — Both scenarios back-to-back (recommended for presentations)

## Architecture

[brief architecture description]

## Creating New Scenarios

See `docs/SCENARIO_AUTHORING.md`

## Edge C2 Integration

See `docs/API_INTEGRATION.md`
```

---

## Task 8: Pre-Demo Checklist

Create `docs/DEMO_CHECKLIST.md`:

```markdown
# Demo Day Checklist

## Day Before
- [ ] Docker images built and tested on demo laptop
- [ ] .env file configured with Cesium token
- [ ] Internet access verified (Cesium tile loading)
- [ ] OR: Cesium tile cache populated for offline use
- [ ] Scenario runs start-to-finish without errors
- [ ] External display tested (resolution, HDMI/USB-C)
- [ ] Browser: Chrome, fullscreen, bookmark to localhost:3000
- [ ] Backup: second laptop with same setup

## 1 Hour Before
- [ ] docker-compose up
- [ ] Open http://localhost:3000 in Chrome
- [ ] Verify entities appear on globe
- [ ] Run through first 2 minutes at 5x to verify
- [ ] Reset scenario
- [ ] Connect external display
- [ ] Set browser to fullscreen (F11)
- [ ] Test audio (if presenting with narration)

## During Demo
- [ ] Start with scenario paused — show the ESSZONE overview
- [ ] Press Play at 5x speed
- [ ] Enable demo mode (D key) for auto-camera
- [ ] Slow to 2x during action sequences
- [ ] 1x during boarding/resolution for dramatic effect
- [ ] Use agency filters to highlight specific forces
- [ ] Click entities to show detail panel when discussing

## Troubleshooting
- **COP blank/not loading:** Check Cesium token in .env, check internet
- **No entities:** Check simulator health: curl http://localhost:8766/health
- **Entities frozen:** Check WebSocket: browser console should show updates
- **Slow/laggy:** Close other browser tabs, reduce to 50x speed
- **Display issues:** Try Ctrl+F5 to force reload
```

---

## Definition of Done

Phase 5 is complete when:

1. Entities animate smoothly (no jumping between positions)
2. Track trails fade properly
3. Event toast notifications appear for CRITICAL events
4. Demo mode auto-flies camera through the combined scenario
5. Keyboard shortcuts work (Space, 1-5, D, F, R, Escape)
6. Performance: 60 FPS with 100+ entities on demo laptop
7. All error conditions handled gracefully (no crashes)
8. docker-compose up starts everything with one command
9. demo-start.sh works end-to-end from clean clone
10. README, DEMO_CHECKLIST, API_INTEGRATION docs complete
11. Combined scenario runs start-to-finish without errors at 5x
12. It looks impressive on a large display in a dark room
