# CesiumJS COP Dashboard — Design Specification

## Overview

The Common Operating Picture (COP) is a browser-based 3D command center display 
built on CesiumJS. It receives real-time entity updates via WebSocket from the 
simulation engine and renders all entities on a 3D globe with MIL-STD-2525D 
military symbology.

**Target audience:** Senior Malaysian defense/security officials viewing on a 
large display (projector or wall screen) in a briefing room.

**Aesthetic:** Dark-themed command center. Think military operations center, not 
consumer web app. De-saturated map backgrounds with bright, high-contrast entity 
symbology. No playful colors or rounded corners.

---

## Layout

```
┌─────────────────────────────────────────────────────────────────────┐
│  [EDGE C2 LOGO]  EDGE C2 — COMMON OPERATING PICTURE    [CLOCK]    │
│                   Scenario: Sulu Sea IUU Intercept   SIM: 08:14:32 │
├────────┬────────────────────────────────────────────────┬───────────┤
│        │                                                │           │
│ AGENCY │                                                │  ENTITY   │
│ FILTER │                                                │  DETAIL   │
│ PANEL  │            CESIUM 3D GLOBE                     │  PANEL    │
│        │            (Main viewport)                     │           │
│ [■] RMP│                                                │ (Shows    │
│ [■]MMEA│                                                │  on click)│
│ [■] CI │                                                │           │
│ [■]RMAF│                                                │           │
│ [■] MIL│                                                │           │
│ [■] CIV│                                                │           │
│        │                                                │           │
│ DOMAIN │                                                │           │
│ [■] Sea│                                                │           │
│ [■] Air│                                                │           │
│ [■] Gnd│                                                │           │
│ [■] Per│                                                │           │
│        │                                                │           │
│ STATS  │                                                │           │
│ 47 ent │                                                │           │
│ 12 evt │                                                │           │
├────────┴────────────────────────────────────────────────┴───────────┤
│ ▶ PLAY  ⏸ PAUSE  [1x] [2x] [5x] [10x] [60x]  ⟲ RESET            │
├─────────────────────────────────────────────────────────────────────┤
│ EVENT TIMELINE                                                      │
│ 08:00 [MMEA] Coastal radar detects 5 unidentified contacts in EEZ  │
│ 08:02 [ESSCOM] Fusion Centre correlates with IUU intel report      │
│ 08:04 [MMEA] KM Sangitan ordered to investigate                    │
│ 08:06 [RMAF] Maritime patrol aircraft dispatched from Labuan       │
│ ► 08:08 [RMN] G2000 FIC scrambled from MAWILLA 2 Sandakan         │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Component Specifications

### 1. Top Bar (Header)

- **Height:** 48px
- **Background:** `#0D1117` (near-black)
- **Left:** Edge C2 logo (placeholder SVG if no logo provided) + product name
- **Center:** Active scenario name
- **Right:** Simulation clock (large, monospace font) + real/sim time indicator
- **Font:** `JetBrains Mono` or `IBM Plex Mono` for clock, `IBM Plex Sans` for labels
- **Border bottom:** 1px `#30363D`

### 2. Agency Filter Panel (Left Sidebar)

- **Width:** 200px, collapsible
- **Background:** `#161B22`
- **Sections:**
  - **Agencies** — toggle each on/off:
    - RMP — `#1B3A8C` (dark blue) — police badge icon
    - MMEA — `#FF6600` (orange) — anchor icon  
    - CI — `#2E7D32` (green) — customs shield icon
    - RMAF — `#5C6BC0` (indigo) — wings icon
    - MIL — `#4E342E` (brown) — star icon
    - CIVILIAN — `#78909C` (grey) — neutral icon
  - **Domains** — toggle each on/off:
    - Maritime — ship icon
    - Air — aircraft icon
    - Ground — vehicle icon
    - Personnel — person icon
  - **Statistics:**
    - Total entities (live count)
    - Active events (count)
    - Entities by agency (mini bar chart)

- **Toggle behavior:** Click = toggle visibility. Agency color swatch shows 
  filled when active, outline when hidden. Should feel instant — no animation 
  delay on filter changes.

### 3. Main Viewport (CesiumJS Globe)

- **Map style:** Dark/satellite hybrid. Use Cesium's default dark imagery or 
  Mapbox Dark if available. Terrain ON (Cesium World Terrain).
- **Initial camera:**
  - Scenario 1 (IUU): `lat: 5.50, lon: 118.50, height: 200000m` (200km up, 
    looking at ESSZONE sector 2-3)
  - Scenario 2 (KFR): `lat: 4.45, lon: 118.65, height: 80000m` (80km up, 
    Semporna area)
- **Globe settings:**
  - Enable terrain
  - Enable water effects (ocean rendering)
  - Enable atmosphere
  - Enable lighting (sun position based on sim time)
  - Disable default credits display (move to footer)

#### Entity Rendering

Each entity is a **Cesium Billboard** with these layers:

1. **Military symbol** (milsymbol.js generated):
   - Generate MIL-STD-2525D symbol from entity SIDC
   - Size: 32x32px at default zoom, scale with distance
   - milsymbol options: `{ size: 32, frame: true, fill: true }`
   - Color follows affiliation (friendly=blue, hostile=red, neutral=green, 
     unknown=yellow)

2. **Callsign label** (Cesium Label):
   - Position: below symbol, offset 20px
   - Font: `12px IBM Plex Mono`
   - Color: white with black outline (ensure readability on any background)
   - Show: always at close zoom, hide at strategic zoom (>200km)

3. **Heading indicator** (velocity vector):
   - Thin line from entity position in heading direction
   - Length proportional to speed (faster = longer line)
   - Color: same as agency color, 70% opacity
   - Hide when speed = 0

4. **Track trail** (Cesium Polyline):
   - Last 15 positions as fading polyline
   - Color: agency color, opacity fading from 80% (newest) to 10% (oldest)
   - Width: 2px
   - Toggle on/off per entity via detail panel

5. **Selection ring** (on click):
   - Pulsing circle around selected entity
   - Agency color, 2px width, animated radius pulse

#### Entity Interaction

- **Hover:** Tooltip appears showing:
  ```
  KM Semporna [MMEA]
  MMEA_PATROL | ACTIVE
  Speed: 18.5 kts | HDG: 045°
  ```
- **Click:** 
  - Entity selected (pulsing ring)
  - Right panel populated with full details
  - Camera does NOT auto-fly (user controls camera)
- **Double-click:**
  - Fly camera to entity position, 5km altitude
  - 1-second smooth flight animation

#### Map Overlays

These are toggle-able from a small overlay menu (gear icon in viewport corner):

- **ESSZONE boundary** — dashed yellow polygon outline
- **Patrol zones** — semi-transparent fill polygons with sector labels
- **Coastal radar coverage** — 250km radius circles at each radar station 
  (semi-transparent green fill, 10% opacity)
- **Sulu Sea transit corridor** — dashed line
- **Base locations** — small square icons with labels (only at close zoom)
- **Sea curfew zone** — red-tinted area (activates during scenarios)

### 4. Entity Detail Panel (Right Sidebar)

- **Width:** 280px, slides in on entity click, close button to dismiss
- **Background:** `#161B22`

Content layout:
```
┌─────────────────────────┐
│  [MILSYMBOL]  KM Penggalang 7    │
│              MMEA Fast Intercept  │
│              ████████ MMEA        │
├─────────────────────────┤
│  STATUS: INTERCEPTING            │
│  ─────────────────────────       │
│  Position                        │
│    LAT:  5.6234° N               │
│    LON:  118.7821° E             │
│    ALT:  0.0 m                   │
│                                  │
│  Movement                        │
│    SPEED: 35.0 kts               │
│    HDG:   072°                   │
│    CRS:   074°                   │
│                                  │
│  Maritime Data                   │
│    MMSI:  533100247              │
│    Type:  Fast Intercept Craft   │
│    AIS:   ACTIVE                 │
│                                  │
│  Agency: MMEA                    │
│  Domain: MARITIME                │
│  Updated: 08:14:32               │
├─────────────────────────┤
│  [📍 FLY TO] [📌 FOLLOW]        │
│  [📡 TRACK]  [❌ CLOSE]          │
└─────────────────────────┘
```

- **FLY TO:** Camera flies to entity position (5km alt for maritime, 
  20km for air, 2km for ground)
- **FOLLOW:** Camera locks to entity, follows its movement. Press again 
  or ESC to unlock.
- **TRACK:** Toggle track trail visibility for this entity

### 5. Playback Controls (Bottom Bar)

- **Height:** 40px
- **Background:** `#0D1117`
- **Controls:**
  - ▶ Play / ⏸ Pause — toggle button
  - Speed buttons: `1x` `2x` `5x` `10x` `60x` — radio group, highlight active
  - ⟲ Reset — restart scenario from beginning
  - Progress bar showing position in scenario timeline (clickable to seek)
- **Clock display:** Large `HH:MM:SS` simulation time, smaller real time below
- **Visual:** Green border-top when running, amber when paused

### 6. Event Timeline (Bottom Panel)

- **Height:** 120px, expandable to 240px by dragging handle
- **Background:** `#0D1117`
- **Layout:** Scrollable list, newest events at bottom (auto-scroll)
- **Each event row:**
  ```
  [TIME]  [AGENCY_BADGE]  Description text
  ```
  - Time: monospace, `08:14` format
  - Agency badge: small colored pill with agency abbreviation
  - Description: event text from scenario
  - Severity colors:
    - INFO: default text color (`#C9D1D9`)
    - WARNING: amber text (`#D29922`)  
    - CRITICAL: red text with subtle background (`#F85149`, bg `#3D1117`)

- **Click event:** Camera flies to event position (if event has coordinates)
- **Hover event:** Highlight related entities on the map (pulse their symbols)

---

## Technical Implementation Notes

### WebSocket Message Handling

```javascript
// Message types from simulator
switch (message.type) {
  case 'snapshot':
    // Full entity list — initial load or reconnect
    clearAllEntities();
    message.entities.forEach(e => addOrUpdateEntity(e));
    break;
    
  case 'entity_update':
    // Single entity position/state change
    addOrUpdateEntity(message.entity);
    break;
    
  case 'entity_remove':
    // Entity left simulation
    removeEntity(message.entity_id);
    break;
    
  case 'event':
    // Scenario event fired
    addTimelineEvent(message.event);
    handleEventEffects(message.event);  // Flash, fly-to, etc.
    break;
    
  case 'clock':
    // Simulation time sync
    updateClock(message.sim_time, message.speed, message.running);
    break;
}
```

### milsymbol Integration

```javascript
import ms from 'milsymbol';

function generateSymbol(entity) {
  const symbol = new ms.Symbol(entity.sidc, {
    size: 32,
    frame: true,
    fill: true,
    // Override affiliation color with agency color if desired
    // colorMode: { Friendly: agencyColors[entity.agency] }
  });
  
  // Convert to canvas for Cesium Billboard
  const canvas = symbol.asCanvas();
  return canvas.toDataURL();
}
```

### SIDC Codes for Entity Types

Use MIL-STD-2525D 20-character SIDCs:

```yaml
# Friendly maritime
MMEA_PATROL:        "10033000001211040000"  # Friendly, surface, law enforcement
MMEA_FAST_INTERCEPT: "10033000001211040000"
MIL_NAVAL:          "10033000001211000000"  # Friendly, surface, combatant

# Hostile/Suspect maritime
SUSPECT_VESSEL:     "10063000001211000000"  # Hostile, surface, unknown

# Neutral maritime
CIVILIAN_CARGO:     "10043000001213000000"  # Neutral, surface, merchant
CIVILIAN_FISHING:   "10043000001215000000"  # Neutral, surface, fishing
CIVILIAN_TANKER:    "10043000001214000000"  # Neutral, surface, tanker

# Friendly air
RMAF_FIGHTER:       "10031000001211040000"  # Friendly, air, military, fighter
RMAF_HELICOPTER:    "10031500001211000000"  # Friendly, air, rotary wing
RMAF_TRANSPORT:     "10031000001211050000"  # Friendly, air, military, cargo
RMP_HELICOPTER:     "10031500001211040000"  # Friendly, air, rotary wing, law enforcement

# Neutral air
CIVILIAN_COMMERCIAL: "10041000001213000000"  # Neutral, air, civilian

# Friendly ground
RMP_PATROL_CAR:     "10031000001511040000"  # Friendly, ground, law enforcement
RMP_TACTICAL:       "10031000001511040000"
MIL_APC:            "10031000001512000000"  # Friendly, ground, armored
MIL_INFANTRY_SQUAD: "10031000001211000000"  # Friendly, ground, infantry

# Friendly ground (CI)
CI_CHECKPOINT_VEHICLE: "10031000001513000000"  # Friendly, ground, administrative
CI_OFFICER:            "10031000001511050000"
```

NOTE: These SIDCs are approximations. The exact 20-character codes should be 
validated against the MIL-STD-2525D specification. milsymbol.js is forgiving 
and will render a reasonable symbol even with imperfect codes.

### Smooth Entity Animation

Use CesiumJS `SampledPositionProperty` for interpolation between updates:

```javascript
function updateEntityPosition(entity, newPosition, timestamp) {
  const cesiumEntity = entityMap.get(entity.entity_id);
  if (!cesiumEntity) return;
  
  // Add position sample — Cesium interpolates between samples
  const time = Cesium.JulianDate.fromIso8601(timestamp);
  cesiumEntity.position.addSample(time, Cesium.Cartesian3.fromDegrees(
    newPosition.longitude,
    newPosition.latitude,
    newPosition.altitude_m
  ));
  
  // Heading — update billboard rotation
  cesiumEntity.billboard.rotation = Cesium.Math.toRadians(-entity.heading_deg);
}
```

### Performance Targets

- **60 FPS** with up to 100 entities on screen
- **WebSocket latency:** <50ms from simulator to rendered update
- **Entity add/remove:** <16ms (one frame budget)
- **Filter toggle:** <16ms (instant visual response)
- **Camera fly-to:** 1-second smooth animation

For 100+ entities, implement:
- Billboard pooling (reuse Cesium entities, just update properties)
- Batch WebSocket messages (simulator sends bulk every 100ms)
- LOD: at strategic zoom (>200km), cluster nearby entities into count badges
- Throttle track trail updates to every 5th position sample

---

## Demo Mode

A special "demo mode" button in the header activates auto-narration:

1. Camera automatically flies to key locations as events unfold
2. On each major event, camera smoothly repositions:
   - Detection → fly to radar station / contact area (wide view)
   - Intercept order → zoom to intercepting vessel
   - Pursuit → follow the fast-moving pursuer
   - Boarding → close zoom on target vessel
   - Resolution → pull back to strategic view
3. Event descriptions appear as large overlay text (fade in/out)
4. Operator can interrupt at any time by clicking the globe
5. Press demo mode button again to resume auto-narration

Camera flight presets per event type:
```yaml
DETECTION:  { altitude: 150000, pitch: -45 }  # Wide area view
ORDER:      { altitude: 50000, pitch: -60 }   # Operational view
INTERCEPT:  { altitude: 10000, pitch: -70 }   # Tactical view  
BOARDING:   { altitude: 3000, pitch: -80 }    # Close-up
RESOLUTION: { altitude: 200000, pitch: -45 }  # Strategic pull-back
```

---

## Color Palette

```css
:root {
  /* Backgrounds */
  --bg-primary:     #0D1117;
  --bg-secondary:   #161B22;
  --bg-tertiary:    #21262D;
  --border:         #30363D;
  
  /* Text */
  --text-primary:   #C9D1D9;
  --text-secondary: #8B949E;
  --text-emphasis:  #FFFFFF;
  
  /* Agency colors */
  --agency-rmp:     #1B3A8C;
  --agency-mmea:    #FF6600;
  --agency-ci:      #2E7D32;
  --agency-rmaf:    #5C6BC0;
  --agency-mil:     #4E342E;
  --agency-civilian: #78909C;
  
  /* Severity */
  --severity-info:     #58A6FF;
  --severity-warning:  #D29922;
  --severity-critical: #F85149;
  
  /* Status */
  --status-active:       #3FB950;
  --status-intercepting: #F85149;
  --status-responding:   #D29922;
  --status-idle:         #8B949E;
  --status-rtb:          #58A6FF;
}
```

---

## Typography

```css
/* Clock and data displays */
font-family: 'JetBrains Mono', 'IBM Plex Mono', 'Fira Code', monospace;

/* UI labels and body text */
font-family: 'IBM Plex Sans', 'Inter', -apple-system, sans-serif;

/* Load via CDN */
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans:wght@400;500;600&family=JetBrains+Mono:wght@400;600&display=swap');
```

---

## Dependencies (npm)

```json
{
  "dependencies": {
    "cesium": "^1.124",
    "milsymbol": "^2.2",
    "reconnecting-websocket": "^4.4"
  },
  "devDependencies": {
    "vite": "^6.0",
    "vite-plugin-cesium": "^1.2"
  }
}
```

---

## File Structure

```
cop/
├── package.json
├── vite.config.js
├── index.html                    # Single page app shell
├── public/
│   ├── favicon.ico
│   └── assets/
│       ├── logo-edge-c2.svg      # Placeholder logo
│       └── icons/                 # Agency icons (SVG)
└── src/
    ├── main.js                   # Entry point — init Cesium, connect WS
    ├── config.js                 # Agency colors, SIDC mappings, defaults
    ├── cesium-setup.js           # Cesium viewer initialization
    ├── websocket-client.js       # WS connection + message handling
    ├── entity-manager.js         # Entity CRUD + Cesium billboard management
    ├── symbol-generator.js       # milsymbol wrapper — SIDC to Canvas
    ├── agency-filter.js          # Left panel filter logic
    ├── entity-panel.js           # Right panel detail display
    ├── timeline.js               # Bottom event timeline
    ├── playback-controls.js      # Play/pause/speed controls
    ├── overlay-manager.js        # Map overlay toggles (zones, radar, etc.)
    ├── demo-mode.js              # Auto-narration camera controller
    ├── utils/
    │   ├── geo-math.js           # Bearing, distance calculations
    │   └── formatting.js         # Time, coordinate formatters
    └── styles/
        ├── main.css              # Global styles + CSS variables
        ├── header.css
        ├── sidebar.css
        ├── timeline.css
        └── controls.css
```
