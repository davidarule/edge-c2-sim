# Claude Code — Phase 3 Task Brief: CesiumJS COP Dashboard

## Context

Phases 0-2 built the simulation engine: entities move, events fire, AIS/ADS-B 
signals generate, and everything broadcasts via WebSocket. Phase 3 builds the 
visual frontend — the CesiumJS Common Operating Picture that demo audiences 
will actually see.

**Read first:**
- `docs/COP_DASHBOARD_DESIGN.md` — Complete visual specification
- `edge-c2-simulator-plan.md` — Architecture overview
- `config/scenarios/demo_combined.yaml` — What we're visualizing

After Phase 3, we should have a fully working browser-based 3D COP that 
connects to the running simulation and renders all entities in real-time with 
military symbology.

---

## Task 1: Project Setup (`cop/`)

### 1a. Initialize npm project

```bash
cd cop/
npm init -y
npm install cesium milsymbol reconnecting-websocket
npm install -D vite vite-plugin-cesium
```

### 1b. Vite configuration (`cop/vite.config.js`)

```javascript
import { defineConfig } from 'vite';
import cesium from 'vite-plugin-cesium';

export default defineConfig({
  plugins: [cesium()],
  server: {
    port: 3000,
    host: '0.0.0.0'  // Allow access from other machines (demo setup)
  },
  build: {
    outDir: 'dist',
    sourcemap: true
  }
});
```

### 1c. HTML shell (`cop/index.html`)

Single-page app shell. The layout is a CSS Grid with five regions:
- Header (top bar)
- Left sidebar (agency filters)
- Main viewport (CesiumJS)
- Right sidebar (entity detail — hidden until click)
- Bottom bar (playback controls + event timeline)

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Edge C2 — Common Operating Picture</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans:wght@400;500;600&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
</head>
<body>
  <div id="app">
    <header id="header"></header>
    <aside id="sidebar-left"></aside>
    <main id="cesium-container"></main>
    <aside id="sidebar-right"></aside>
    <div id="controls"></div>
    <div id="timeline"></div>
  </div>
  <script type="module" src="/src/main.js"></script>
</body>
</html>
```

CSS Grid layout:
```css
#app {
  display: grid;
  grid-template-columns: 200px 1fr 0px;  /* Right sidebar 0 until opened */
  grid-template-rows: 48px 1fr 40px 120px;
  grid-template-areas:
    "header   header    header"
    "sidebar  viewport  detail"
    "controls controls  controls"
    "timeline timeline  timeline";
  height: 100vh;
  width: 100vw;
  overflow: hidden;
  background: #0D1117;
  color: #C9D1D9;
}
```

When entity detail panel opens, transition `grid-template-columns` to 
`200px 1fr 280px`.

### 1d. Entry point (`cop/src/main.js`)

```javascript
// Initialization order matters:
// 1. Load config (agency colors, defaults)
// 2. Initialize CesiumJS viewer
// 3. Connect WebSocket to simulator
// 4. Initialize UI components (filters, controls, timeline, detail panel)
// 5. Start render loop

import { initConfig } from './config.js';
import { initCesium } from './cesium-setup.js';
import { connectWebSocket } from './websocket-client.js';
import { initEntityManager } from './entity-manager.js';
import { initAgencyFilter } from './agency-filter.js';
import { initPlaybackControls } from './playback-controls.js';
import { initTimeline } from './timeline.js';
import { initEntityPanel } from './entity-panel.js';
import { initOverlayManager } from './overlay-manager.js';

async function main() {
  const config = initConfig();
  const viewer = await initCesium('cesium-container', config);
  const entityManager = initEntityManager(viewer, config);
  
  const ws = connectWebSocket(config.wsUrl, {
    onSnapshot: (entities) => entityManager.loadSnapshot(entities),
    onEntityUpdate: (entity) => entityManager.updateEntity(entity),
    onEntityRemove: (id) => entityManager.removeEntity(id),
    onEvent: (event) => timeline.addEvent(event),
    onClock: (clockState) => controls.updateClock(clockState)
  });
  
  const filters = initAgencyFilter('sidebar-left', entityManager, config);
  const controls = initPlaybackControls('controls', ws, config);
  const timeline = initTimeline('timeline', viewer, config);
  const detail = initEntityPanel('sidebar-right', entityManager, viewer);
  const overlays = initOverlayManager(viewer, config);
  
  // Entity click handler
  entityManager.onEntityClick((entity) => detail.show(entity));
  entityManager.onEntityDoubleClick((entity) => {
    viewer.camera.flyTo({
      destination: Cesium.Cartesian3.fromDegrees(
        entity.position.longitude,
        entity.position.latitude,
        entity.domain === 'AIR' ? 20000 : 5000
      ),
      duration: 1.0
    });
  });
}

main().catch(console.error);
```

### Tests for Task 1:

- `npm run dev` starts Vite dev server on port 3000
- Page loads without errors
- CesiumJS globe renders (dark imagery, terrain)
- CSS grid layout matches design spec
- Console shows "Connecting to WebSocket..." message

---

## Task 2: CesiumJS Viewer Setup (`cop/src/cesium-setup.js`)

```javascript
/**
 * Initialize CesiumJS viewer with dark theme and ESSZONE camera.
 * 
 * IMPORTANT: Cesium Ion token must be set via environment variable
 * VITE_CESIUM_ION_TOKEN or in config. Free tier is sufficient.
 */

export async function initCesium(containerId, config) {
  // Set Cesium Ion token
  Cesium.Ion.defaultAccessToken = config.cesiumToken;
  
  const viewer = new Cesium.Viewer(containerId, {
    // Disable default UI widgets we're replacing
    animation: false,
    timeline: false,
    baseLayerPicker: false,
    geocoder: false,
    homeButton: false,
    sceneModePicker: false,
    navigationHelpButton: false,
    fullscreenButton: false,
    infoBox: false,        // We have our own entity panel
    selectionIndicator: false,
    
    // Enable terrain
    terrain: Cesium.Terrain.fromWorldTerrain(),
    
    // Dark imagery
    baseLayer: Cesium.ImageryLayer.fromProviderAsync(
      Cesium.IonImageryProvider.fromAssetId(3845)  // Cesium Dark
      // Fallback: Cesium.IonImageryProvider.fromAssetId(2)  // Bing Aerial
    ),
    
    // Scene settings
    skyBox: false,  // Clean dark background at high altitude
    skyAtmosphere: true,
    globe: {
      enableLighting: true,
      showGroundAtmosphere: true
    }
  });
  
  // Dark globe customization
  viewer.scene.globe.baseColor = Cesium.Color.fromCssColorString('#0a0e17');
  viewer.scene.backgroundColor = Cesium.Color.fromCssColorString('#0a0e17');
  
  // Remove Cesium branding (move to our footer)
  viewer.cesiumWidget.creditContainer.style.display = 'none';
  
  // Initial camera — ESSZONE overview
  viewer.camera.flyTo({
    destination: Cesium.Cartesian3.fromDegrees(
      config.initialCenter.lon,   // 118.50
      config.initialCenter.lat,   // 5.00
      config.initialAltitude      // 300000 (300km up)
    ),
    orientation: {
      heading: Cesium.Math.toRadians(0),
      pitch: Cesium.Math.toRadians(-60),
      roll: 0
    },
    duration: 0  // Instant on load
  });
  
  // Enable anti-aliasing
  viewer.scene.postProcessStages.fxaa.enabled = true;
  
  return viewer;
}
```

### Cesium token handling:

Create `cop/.env.example`:
```
VITE_CESIUM_ION_TOKEN=your_token_here
VITE_WS_URL=ws://localhost:8765
VITE_SIM_DEFAULT_SPEED=1
```

In `config.js`:
```javascript
export function initConfig() {
  return {
    cesiumToken: import.meta.env.VITE_CESIUM_ION_TOKEN || '',
    wsUrl: import.meta.env.VITE_WS_URL || 'ws://localhost:8765',
    initialCenter: { lat: 5.00, lon: 118.50 },
    initialAltitude: 300000,
    // ... agency colors, entity type configs from COP_DASHBOARD_DESIGN.md
  };
}
```

### Tests:

- Globe renders with dark imagery
- Camera starts positioned over ESSZONE
- Terrain visible when zoomed in
- No Cesium default UI widgets visible

---

## Task 3: WebSocket Client (`cop/src/websocket-client.js`)

```javascript
/**
 * WebSocket client with auto-reconnect.
 * 
 * Connects to simulation engine, dispatches messages to callbacks.
 * Sends commands (speed, pause, reset) back to simulator.
 */

import ReconnectingWebSocket from 'reconnecting-websocket';

export function connectWebSocket(url, handlers) {
  const ws = new ReconnectingWebSocket(url, [], {
    maxRetries: 50,
    reconnectionDelayGrowFactor: 1.3,
    maxReconnectionDelay: 10000,
    minReconnectionDelay: 1000
  });
  
  ws.addEventListener('open', () => {
    console.log('WebSocket connected to simulator');
    updateConnectionStatus('connected');
  });
  
  ws.addEventListener('close', () => {
    console.log('WebSocket disconnected');
    updateConnectionStatus('disconnected');
  });
  
  ws.addEventListener('message', (event) => {
    const msg = JSON.parse(event.data);
    
    switch (msg.type) {
      case 'snapshot':
        handlers.onSnapshot(msg.entities);
        break;
      case 'entity_update':
        handlers.onEntityUpdate(msg.entity);
        break;
      case 'entity_batch':
        // Bulk update — array of entities
        msg.entities.forEach(e => handlers.onEntityUpdate(e));
        break;
      case 'entity_remove':
        handlers.onEntityRemove(msg.entity_id);
        break;
      case 'event':
        handlers.onEvent(msg.event);
        break;
      case 'clock':
        handlers.onClock(msg);
        break;
    }
  });
  
  // Command API
  return {
    raw: ws,
    setSpeed: (speed) => ws.send(JSON.stringify({ cmd: 'set_speed', speed })),
    pause: () => ws.send(JSON.stringify({ cmd: 'pause' })),
    resume: () => ws.send(JSON.stringify({ cmd: 'resume' })),
    reset: () => ws.send(JSON.stringify({ cmd: 'reset' })),
    requestSnapshot: () => ws.send(JSON.stringify({ cmd: 'snapshot' }))
  };
}

function updateConnectionStatus(status) {
  const indicator = document.getElementById('connection-status');
  if (indicator) {
    indicator.className = `connection-${status}`;
    indicator.textContent = status === 'connected' ? '● LIVE' : '○ DISCONNECTED';
  }
}
```

### Message format (from simulator → COP):

```javascript
// Snapshot (sent on connect or request)
{
  "type": "snapshot",
  "entities": [
    {
      "entity_id": "MMEA-PV-101",
      "entity_type": "MMEA_PATROL",
      "domain": "MARITIME",
      "agency": "MMEA",
      "callsign": "KM Semporna",
      "position": { "latitude": 5.84, "longitude": 118.07, "altitude_m": 0 },
      "heading_deg": 45.2,
      "speed_knots": 18.5,
      "course_deg": 47.0,
      "status": "ACTIVE",
      "sidc": "10033000001211040000",
      "timestamp": "2026-04-15T08:14:32Z",
      "metadata": { "vessel_type": "Patrol vessel", "ais_active": true }
    }
  ]
}

// Entity update (individual, high-frequency)
{
  "type": "entity_update",
  "entity": { /* same structure as snapshot entry */ }
}

// Entity batch (bulk, every 100ms)
{
  "type": "entity_batch",
  "entities": [ /* array of entity objects */ ]
}

// Event
{
  "type": "event",
  "event": {
    "time": "2026-04-15T08:14:00Z",
    "event_type": "DETECTION",
    "description": "Coastal radar detects 5 unidentified contacts",
    "severity": "WARNING",
    "position": { "latitude": 5.80, "longitude": 118.88 },
    "alert_agencies": ["MMEA", "MIL"]
  }
}

// Clock sync
{
  "type": "clock",
  "sim_time": "2026-04-15T08:14:32Z",
  "speed": 5.0,
  "running": true,
  "scenario_progress": 0.28  // 0-1 fraction through scenario
}
```

### Tests:

- Connects to WebSocket server (integration test with running sim)
- Reconnects automatically after disconnect
- Parses all message types without error
- Sends speed/pause/resume commands

---

## Task 4: Entity Manager (`cop/src/entity-manager.js`)

The core module. Manages all Cesium entities, generates milsymbol icons, 
handles entity lifecycle (add, update, remove), filtering, and selection.

```javascript
/**
 * Entity lifecycle management for CesiumJS.
 * 
 * Each simulation entity maps to a Cesium Billboard (symbol) + Label (callsign)
 * + Polyline (track trail). Uses milsymbol.js to generate MIL-STD-2525D icons.
 */

import ms from 'milsymbol';

export function initEntityManager(viewer, config) {
  const entities = new Map();  // entity_id → { cesiumBillboard, cesiumLabel, cesiumTrail, data }
  const clickHandlers = [];
  const doubleClickHandlers = [];
  const filters = { agencies: new Set(), domains: new Set() };
  
  // Track trail storage
  const trailPositions = new Map();  // entity_id → array of {lat, lon, time}
  const MAX_TRAIL_POINTS = 15;
  
  // === MILSYMBOL ===
  function generateSymbolImage(entity) {
    const sidc = entity.sidc || guessSidc(entity);
    const symbol = new ms.Symbol(sidc, {
      size: 28,
      frame: true,
      fill: true,
      strokeWidth: 1.5,
      infoFields: false
    });
    return symbol.toDataURL();
  }
  
  // Fallback SIDC guesser based on entity_type and agency
  function guessSidc(entity) {
    // Map from COP_DASHBOARD_DESIGN.md SIDC table
    const sidcMap = {
      'MMEA_PATROL':        '10033000001211040000',
      'MMEA_FAST_INTERCEPT': '10033000001211040000',
      'MIL_NAVAL':          '10033000001211000000',
      'SUSPECT_VESSEL':     '10063000001211000000',
      'CIVILIAN_CARGO':     '10043000001213000000',
      'CIVILIAN_FISHING':   '10043000001215000000',
      'CIVILIAN_TANKER':    '10043000001214000000',
      'RMAF_FIGHTER':       '10031000001211040000',
      'RMAF_HELICOPTER':    '10031500001211000000',
      'RMAF_TRANSPORT':     '10031000001211050000',
      'RMP_HELICOPTER':     '10031500001211040000',
      'CIVILIAN_COMMERCIAL': '10041000001213000000',
      'RMP_PATROL_CAR':     '10031000001511040000',
      'RMP_TACTICAL_TEAM':  '10031000001511040000',
      'MIL_APC':            '10031000001512000000',
      'MIL_INFANTRY_SQUAD': '10031000001211000000',
      'CI_OFFICER':         '10031000001511050000',
      'CI_IMMIGRATION_TEAM': '10031000001511050000'
    };
    return sidcMap[entity.entity_type] || '10030000001200000000';  // Generic friendly
  }
  
  // === ENTITY CRUD ===
  function addOrUpdateEntity(entityData) {
    const id = entityData.entity_id;
    
    if (entities.has(id)) {
      updateExisting(id, entityData);
    } else {
      createNew(entityData);
    }
  }
  
  function createNew(entityData) {
    const id = entityData.entity_id;
    const pos = entityData.position;
    
    // Create Cesium billboard
    const billboard = viewer.entities.add({
      id: `entity-${id}`,
      position: Cesium.Cartesian3.fromDegrees(pos.longitude, pos.latitude, pos.altitude_m || 0),
      billboard: {
        image: generateSymbolImage(entityData),
        verticalOrigin: Cesium.VerticalOrigin.CENTER,
        horizontalOrigin: Cesium.HorizontalOrigin.CENTER,
        scale: 1.0,
        rotation: Cesium.Math.toRadians(-(entityData.heading_deg || 0)),
        disableDepthTestDistance: Number.POSITIVE_INFINITY  // Always render on top
      },
      label: {
        text: entityData.callsign || id,
        font: '12px IBM Plex Mono',
        fillColor: Cesium.Color.WHITE,
        outlineColor: Cesium.Color.BLACK,
        outlineWidth: 2,
        style: Cesium.LabelStyle.FILL_AND_OUTLINE,
        verticalOrigin: Cesium.VerticalOrigin.TOP,
        pixelOffset: new Cesium.Cartesian2(0, 20),
        distanceDisplayCondition: new Cesium.DistanceDisplayCondition(0, 200000),
        disableDepthTestDistance: Number.POSITIVE_INFINITY
      }
    });
    
    // Create track trail polyline (initially empty)
    const trail = viewer.entities.add({
      id: `trail-${id}`,
      polyline: {
        positions: new Cesium.CallbackProperty(() => {
          const points = trailPositions.get(id) || [];
          return points.map(p => Cesium.Cartesian3.fromDegrees(p.lon, p.lat, p.alt || 0));
        }, false),
        width: 2,
        material: new Cesium.PolylineFadeAppearance
          ? Cesium.Color.fromCssColorString(getAgencyColor(entityData.agency)).withAlpha(0.5)
          : Cesium.Color.fromCssColorString(getAgencyColor(entityData.agency)).withAlpha(0.5)
      }
    });
    
    // Initialize trail
    trailPositions.set(id, [{
      lat: pos.latitude,
      lon: pos.longitude,
      alt: pos.altitude_m || 0
    }]);
    
    // Store reference
    entities.set(id, {
      cesiumEntity: billboard,
      cesiumTrail: trail,
      data: entityData,
      visible: true
    });
    
    // Apply current filters
    applyVisibility(id);
  }
  
  function updateExisting(id, entityData) {
    const entry = entities.get(id);
    const pos = entityData.position;
    
    // Update position
    entry.cesiumEntity.position = Cesium.Cartesian3.fromDegrees(
      pos.longitude, pos.latitude, pos.altitude_m || 0
    );
    
    // Update heading rotation
    entry.cesiumEntity.billboard.rotation = Cesium.Math.toRadians(-(entityData.heading_deg || 0));
    
    // Update symbol if status changed (e.g., friendly → hostile)
    if (entityData.entity_type !== entry.data.entity_type || 
        entityData.status !== entry.data.status) {
      entry.cesiumEntity.billboard.image = generateSymbolImage(entityData);
    }
    
    // Update label
    entry.cesiumEntity.label.text = entityData.callsign || id;
    
    // Add to trail
    const trail = trailPositions.get(id) || [];
    trail.push({ lat: pos.latitude, lon: pos.longitude, alt: pos.altitude_m || 0 });
    if (trail.length > MAX_TRAIL_POINTS) trail.shift();
    trailPositions.set(id, trail);
    
    // Update stored data
    entry.data = entityData;
  }
  
  function removeEntity(id) {
    const entry = entities.get(id);
    if (entry) {
      viewer.entities.remove(entry.cesiumEntity);
      viewer.entities.remove(entry.cesiumTrail);
      entities.delete(id);
      trailPositions.delete(id);
    }
  }
  
  // === FILTERING ===
  function setAgencyFilter(agency, visible) {
    if (visible) filters.agencies.delete(agency);
    else filters.agencies.add(agency);
    entities.forEach((entry, id) => applyVisibility(id));
  }
  
  function setDomainFilter(domain, visible) {
    if (visible) filters.domains.delete(domain);
    else filters.domains.add(domain);
    entities.forEach((entry, id) => applyVisibility(id));
  }
  
  function applyVisibility(id) {
    const entry = entities.get(id);
    if (!entry) return;
    
    const hidden = filters.agencies.has(entry.data.agency) || 
                   filters.domains.has(entry.data.domain);
    
    entry.cesiumEntity.show = !hidden;
    entry.cesiumTrail.show = !hidden;
    entry.visible = !hidden;
  }
  
  // === SELECTION ===
  // Wire up Cesium click handler in main.js:
  // viewer.screenSpaceEventHandler.setInputAction((click) => { ... }, LEFT_CLICK);
  
  // === API ===
  return {
    loadSnapshot: (entityList) => {
      // Clear existing, add all from snapshot
      entities.forEach((_, id) => removeEntity(id));
      entityList.forEach(e => addOrUpdateEntity(e));
    },
    updateEntity: addOrUpdateEntity,
    removeEntity,
    setAgencyFilter,
    setDomainFilter,
    getEntity: (id) => entities.get(id)?.data,
    getAllEntities: () => [...entities.values()].map(e => e.data),
    getEntityCount: () => entities.size,
    getCountByAgency: () => {
      const counts = {};
      entities.forEach(e => {
        const a = e.data.agency || 'UNKNOWN';
        counts[a] = (counts[a] || 0) + 1;
      });
      return counts;
    },
    onEntityClick: (fn) => clickHandlers.push(fn),
    onEntityDoubleClick: (fn) => doubleClickHandlers.push(fn)
  };
}

function getAgencyColor(agency) {
  const colors = {
    RMP: '#1B3A8C',
    MMEA: '#FF6600',
    CI: '#2E7D32',
    RMAF: '#5C6BC0',
    MIL: '#4E342E',
    CIVILIAN: '#78909C'
  };
  return colors[agency] || '#78909C';
}
```

### Key implementation notes:

1. **Billboard rotation** — CesiumJS rotates counter-clockwise, heading is 
   clockwise. Negate: `rotation = -heading_deg`.

2. **Depth test disabled** — `disableDepthTestDistance: Number.POSITIVE_INFINITY` 
   ensures entity symbols are always visible, never hidden behind terrain.

3. **Trail polyline** — Use `CallbackProperty` so the trail updates dynamically 
   without recreating the entity. Limit to 15 points for performance.

4. **Label distance condition** — Labels only visible within 200km camera 
   distance. At strategic zoom, only symbols are visible (prevents label 
   clutter).

5. **Symbol regeneration** — Only regenerate the milsymbol image when entity 
   type or status changes, NOT on every position update. Symbol generation is 
   expensive.

### Tests:

- Create entity → billboard appears on globe at correct position
- Update entity → billboard moves to new position
- Remove entity → billboard removed from globe
- Agency filter → entities hidden/shown correctly
- Trail grows with position updates
- Trail limited to MAX_TRAIL_POINTS

---

## Task 5: UI Components

Build the remaining UI panels per `COP_DASHBOARD_DESIGN.md`. Each component 
is a separate module that manages a DOM region.

### 5a. Agency Filter (`cop/src/agency-filter.js`)

Renders toggle buttons for each agency and domain in the left sidebar.

- Each agency toggle: colored swatch + abbreviation + entity count
- Click toggles visibility via entity manager
- Domain toggles below agency toggles
- Entity count updates every second (use `setInterval`)
- Statistics section at bottom: total entities, active events

### 5b. Playback Controls (`cop/src/playback-controls.js`)

Bottom bar with play/pause/speed and clock display.

- Play/Pause toggle button — sends command via WebSocket
- Speed buttons: `1x` `2x` `5x` `10x` `60x` — radio button group
- Reset button — confirms before sending
- Clock: large simulation time (JetBrains Mono), smaller real time
- Progress bar: thin line showing scenario progress (from `clock.scenario_progress`)
- Status indicator: green bottom border when running, amber when paused

### 5c. Event Timeline (`cop/src/timeline.js`)

Bottom panel with scrollable event log.

- Auto-scrolls to newest event
- Each event: `[HH:MM] [AGENCY_BADGE] Description`
- Agency badge: small colored pill with 3-letter abbreviation
- Severity colors: INFO=blue, WARNING=amber, CRITICAL=red with red background
- Click event: camera flies to event position (if has coordinates)
- New critical events: brief flash animation on the timeline entry
- Expandable: drag handle to resize from 120px to 240px

### 5d. Entity Detail Panel (`cop/src/entity-panel.js`)

Right sidebar, slides in when entity is clicked.

Content per design spec:
- Entity milsymbol (large, 64px)
- Callsign and type
- Agency badge with color
- Status with color
- Position (lat/lon/alt, formatted)
- Movement (speed, heading, course)
- Domain-specific metadata section
- Action buttons: Fly To, Follow, Track History, Close

**Follow mode:** When "Follow" is active, camera tracks the entity each frame:
```javascript
viewer.trackedEntity = cesiumEntity;
// Or manual: each frame, update camera to entity position + offset
```

### 5e. Overlay Manager (`cop/src/overlay-manager.js`)

Small floating panel (gear icon, top-right of viewport) with toggle switches:

- ESSZONE boundary (dashed yellow polygon)
- Patrol sectors (semi-transparent fills with labels)
- Coastal radar coverage (250km radius circles, green, 10% opacity)
- Transit corridor (dashed line)
- Base locations (square icons)
- Sea curfew zone (red fill, activates during KFR scenario)

Load overlays from the geodata GeoJSON files. These should be loaded at startup 
via a static fetch (or bundled).

**Loading GeoJSON into Cesium:**
```javascript
async function loadGeoJsonOverlay(viewer, url, style) {
  const dataSource = await Cesium.GeoJsonDataSource.load(url, {
    stroke: style.strokeColor || Cesium.Color.YELLOW,
    strokeWidth: style.strokeWidth || 2,
    fill: style.fillColor || Cesium.Color.TRANSPARENT,
    markerSize: 0  // No default markers
  });
  viewer.dataSources.add(dataSource);
  dataSource.show = style.defaultVisible || false;
  return dataSource;
}
```

---

## Task 6: Cesium Click Handling

Wire up Cesium's screen space events to entity manager callbacks.

```javascript
// In main.js after entity manager init:

const handler = new Cesium.ScreenSpaceEventHandler(viewer.scene.canvas);

// Left click — select entity
handler.setInputAction((movement) => {
  const picked = viewer.scene.pick(movement.position);
  if (picked && picked.id && picked.id.id?.startsWith('entity-')) {
    const entityId = picked.id.id.replace('entity-', '');
    const entityData = entityManager.getEntity(entityId);
    if (entityData) {
      entityManager._fireClick(entityData);
    }
  } else {
    // Clicked empty space — deselect
    entityPanel.hide();
  }
}, Cesium.ScreenSpaceEventType.LEFT_CLICK);

// Double click — fly to entity
handler.setInputAction((movement) => {
  const picked = viewer.scene.pick(movement.position);
  if (picked && picked.id && picked.id.id?.startsWith('entity-')) {
    const entityId = picked.id.id.replace('entity-', '');
    const entityData = entityManager.getEntity(entityId);
    if (entityData) {
      entityManager._fireDoubleClick(entityData);
    }
  }
}, Cesium.ScreenSpaceEventType.LEFT_DOUBLE_CLICK);

// Hover — show tooltip
handler.setInputAction((movement) => {
  const picked = viewer.scene.pick(movement.endPosition);
  // Show/hide tooltip based on hover
}, Cesium.ScreenSpaceEventType.MOUSE_MOVE);
```

---

## Task 7: Demo Mode (`cop/src/demo-mode.js`)

Auto-narration mode that flies the camera to key events as they unfold.

```javascript
/**
 * Demo mode — automated camera for presentations.
 * 
 * When active, camera automatically repositions to focus on the action
 * as events fire. Operator can interrupt at any time by clicking the 
 * globe, and resume by pressing the demo mode button.
 */

const CAMERA_PRESETS = {
  DETECTION:  { altitude: 150000, pitch: -45, duration: 2.0 },
  ALERT:      { altitude: 100000, pitch: -50, duration: 1.5 },
  ORDER:      { altitude: 50000,  pitch: -60, duration: 1.5 },
  INTERCEPT:  { altitude: 10000,  pitch: -70, duration: 2.0 },
  BOARDING:   { altitude: 3000,   pitch: -80, duration: 2.5 },
  INCIDENT:   { altitude: 20000,  pitch: -65, duration: 2.0 },
  RESOLUTION: { altitude: 200000, pitch: -45, duration: 3.0 }
};

export function initDemoMode(viewer, entityManager) {
  let active = false;
  let interrupted = false;
  
  function handleEvent(event) {
    if (!active || interrupted) return;
    
    const preset = CAMERA_PRESETS[event.event_type] || CAMERA_PRESETS.ALERT;
    
    // Determine target position
    let targetLon, targetLat;
    if (event.position) {
      targetLon = event.position.longitude;
      targetLat = event.position.latitude;
    } else if (event.target) {
      const entity = entityManager.getEntity(event.target);
      if (entity) {
        targetLon = entity.position.longitude;
        targetLat = entity.position.latitude;
      }
    }
    
    if (targetLon && targetLat) {
      viewer.camera.flyTo({
        destination: Cesium.Cartesian3.fromDegrees(targetLon, targetLat, preset.altitude),
        orientation: {
          heading: 0,
          pitch: Cesium.Math.toRadians(preset.pitch),
          roll: 0
        },
        duration: preset.duration
      });
    }
    
    // Show event overlay text
    showEventOverlay(event.description, event.severity);
  }
  
  function showEventOverlay(text, severity) {
    // Large text overlay that fades in/out over the viewport
    const overlay = document.getElementById('event-overlay');
    overlay.textContent = text;
    overlay.className = `event-overlay severity-${severity.toLowerCase()} visible`;
    setTimeout(() => overlay.classList.remove('visible'), 4000);
  }
  
  return {
    toggle: () => { active = !active; interrupted = false; return active; },
    isActive: () => active,
    handleEvent,
    interrupt: () => { interrupted = true; },
    resume: () => { interrupted = false; }
  };
}
```

### Event overlay CSS:

```css
.event-overlay {
  position: absolute;
  bottom: 180px;
  left: 50%;
  transform: translateX(-50%);
  padding: 12px 24px;
  border-radius: 4px;
  font-family: 'IBM Plex Sans', sans-serif;
  font-size: 16px;
  font-weight: 500;
  color: white;
  background: rgba(13, 17, 23, 0.85);
  border-left: 3px solid;
  opacity: 0;
  transition: opacity 0.5s ease;
  pointer-events: none;
  max-width: 600px;
  text-align: center;
  z-index: 1000;
}
.event-overlay.visible { opacity: 1; }
.event-overlay.severity-info { border-color: #58A6FF; }
.event-overlay.severity-warning { border-color: #D29922; }
.event-overlay.severity-critical { border-color: #F85149; background: rgba(61, 17, 23, 0.9); }
```

---

## Task 8: Docker & Build

### Development:
```bash
cd cop/
npm run dev  # Starts Vite dev server on :3000
```

### Production build:
```bash
cd cop/
npm run build  # Outputs to cop/dist/
```

### Docker (`cop/Dockerfile`):
```dockerfile
FROM node:20-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
ARG VITE_CESIUM_ION_TOKEN
ARG VITE_WS_URL=ws://localhost:8765
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 3000
```

### Nginx config (`cop/nginx.conf`):
```nginx
server {
    listen 3000;
    root /usr/share/nginx/html;
    index index.html;
    
    location / {
        try_files $uri $uri/ /index.html;
    }
    
    # Cache static assets aggressively
    location ~* \.(js|css|png|jpg|svg|woff2)$ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
}
```

### Update `docker-compose.yml` to add COP service:
```yaml
services:
  simulator:
    build: .
    ports:
      - "8765:8765"
    command: edge-c2-sim --scenario config/scenarios/demo_combined.yaml --speed 1
    
  cop:
    build: ./cop
    ports:
      - "3000:3000"
    environment:
      - VITE_CESIUM_ION_TOKEN=${CESIUM_ION_TOKEN}
      - VITE_WS_URL=ws://simulator:8765
    depends_on:
      - simulator
```

---

## Definition of Done

Phase 3 is complete when:

1. `npm run dev` in `cop/` starts the COP on port 3000
2. Globe renders with dark theme, terrain, ESSZONE camera position
3. Connecting to running simulator via WebSocket shows entities on globe
4. Entities render with correct milsymbol icons (friendly blue, hostile red)
5. Entity labels show callsigns
6. Track trails follow entity movement
7. Agency filter toggles work (instant show/hide)
8. Domain filter toggles work
9. Click entity → detail panel slides in with full info
10. Double-click entity → camera flies to position
11. Playback controls send speed/pause/resume commands
12. Event timeline populates as events fire
13. Click timeline event → camera flies to event location
14. Demo mode auto-flies camera to events
15. `docker-compose up` runs both simulator and COP together
16. Performance: 60 FPS with 50+ entities on a modern laptop
