# Claude Code — Scenario Builder & ORBAT Manager

## Context & Vision

The Edge C2 Simulator currently uses hand-authored YAML files for scenarios.
This works for developers but is unusable for anyone else — including the
Malaysian defense officials who will see the April demo. We need a **visual
scenario builder** integrated into the COP that lets a user:

1. **Manage an Order of Battle (ORBAT)** — define every organisation's
   available assets, personnel, and equipment with full MIL-STD-2525D
   symbology, then import/export them via CSV.
2. **Build scenarios visually** — place entities on the CesiumJS globe,
   draw routes and waypoints, define patrol areas, and script timed events
   — all through a GUI, outputting valid scenario YAML.
3. **Edit existing scenarios** — load any YAML scenario file back into
   the builder for modification.

**Read first:**
- `SCENARIO_AUTHORING.md` — The YAML format we must output
- `COP_DASHBOARD_DESIGN.md` — The existing COP visual spec
- `CLAUDE_CODE_REPLACE_MILSYMBOL.md` — SIDC structure and DISA SVG rendering
- `~/joint-military-symbology-xml/` — The working SIDC symbol builder

---

## Architecture Overview

The Scenario Builder is a **new mode** within the existing COP application
(`cop/`). It shares the CesiumJS globe, the JMSML symbol renderer, and the
dark UI theme, but adds an editing layer on top.

```
┌────────────────────────────────────────────────────────────────────┐
│                         COP Application                            │
│                                                                    │
│  ┌──────────────┐         ┌──────────────────────────────────────┐ │
│  │  PLAY MODE   │  ◄────► │  SCENARIO BUILDER MODE               │ │
│  │  (existing)  │ toggle  │                                      │ │
│  │              │         │  ┌────────────┐  ┌────────────────┐  │ │
│  │  - WebSocket │         │  │ ORBAT      │  │ Scenario       │  │ │
│  │  - Playback  │         │  │ Manager    │  │ Editor         │  │ │
│  │  - Timeline  │         │  │            │  │                │  │ │
│  │  - Filters   │         │  │ - Org tree │  │ - Entity place │  │ │
│  │              │         │  │ - Asset db │  │ - Route draw   │  │ │
│  │              │         │  │ - CSV I/O  │  │ - Event script │  │ │
│  │              │         │  │ - SIDC gui │  │ - Area define  │  │ │
│  │              │         │  └────────────┘  └────────────────┘  │ │
│  │              │         │                                      │ │
│  │              │         │  ┌────────────────────────────────┐  │ │
│  │              │         │  │ YAML Import / Export Engine    │  │ │
│  │              │         │  └────────────────────────────────┘  │ │
│  └──────────────┘         └──────────────────────────────────────┘ │
│                                                                    │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │          Shared: CesiumJS Globe + JMSML Symbols + Theme       │ │
│  └────────────────────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────────────────┘
```

The builder runs entirely client-side — no backend needed. Scenarios are
saved/loaded as YAML files through the browser File API.

---

## Research: What Makes Great Scenario Builders

After studying VR-Forces, ORBAT Mapper, Command: Modern Operations, and
Sandtable Mentat, here are the key UI/UX patterns that make scenario
builders effective:

### From VR-Forces (MAK Technologies)
- **Three-tier workflow**: Users → Modelers → Developers. We target Users.
- **ORBAT as pre-conditions**: Force structure (entities, equipment,
  personnel, resources) defined before scenario starts, reusable across
  scenarios.
- **Plans per entity**: Each entity gets a plan (task list with conditions).
  Plans can be saved and reused.
- **CSV import for external data**: MSDL, airspace control orders, and
  point/line/area objects all importable from CSV.
- **Force hierarchy**: entities grouped by force ID → echelon levels.
  Up to 255 forces. Perfect for multi-agency.
- **Simulation Object Editor**: Offline tool for managing entity type
  capabilities — speed, sensors, weapons parameters.

### From ORBAT Mapper (Open Source, Vue.js)
- **Map-based editing**: Click on map to place units, drag to move them.
- **Organizational chart view**: Collapsible tree showing side → group →
  unit hierarchy. Drag-and-drop to reorganize.
- **Tabular data manipulation**: Spreadsheet-like editing for bulk changes.
- **Time dimension**: Units have state at different times — positions change
  through scenario timeline. Animated playback.
- **Import/Export**: GeoJSON, spreadsheets (XLSX/CSV), MilX, Spatial
  Illusions format. Multi-format interop.
- **MSDL support**: Military Scenario Definition Language — XML standard
  for scenario interchange.
- **Symbology built-in**: MIL-STD-2525 symbol rendering integrated into
  every view.
- **Clone/duplicate**: Easily copy units, sides, groups with Ctrl+drag.
- **Breadcrumb navigation**: Click on unit → see its hierarchy path.
- **Lock feature**: Lock sides/groups/units to prevent accidental edits.

### From Command: Modern Operations
- **Right-click context menus**: Add unit at click position. Context-
  sensitive actions.
- **Reference points**: Named lat/lon points that missions, patrol areas,
  and events reference. Reusable anchor points.
- **Mission Editor with tabs**: Separate tabs for assigning units,
  configuring settings, and selecting targets — prevents cramped UI.
- **Waypoint per-point settings**: Each waypoint can have its own speed,
  altitude, and sensor config (F2/F9 keys on selected waypoint).
- **Ctrl+drag to clone waypoints**: Intuitive waypoint manipulation.
- **Strike Planner**: Auto-generates flight plans with ingress/egress
  routes, then lets you manually adjust any waypoint. Best of both worlds.
- **Event engine**: Triggers + conditions + actions system for scenario
  scripting. Visual event editor.
- **Filter-out contacts**: Ghost uninteresting entities to reduce clutter.

### From Sandtable Mentat (CesiumJS)
- **CesiumJS with military overlays**: Proves our tech stack choice works
  for professional military planning.
- **Layer management**: Toggle different data layers (soil, terrain, MCOO).
- **Tablet-friendly**: Tested on tablets in the field — touch-friendly UI.

### Key Design Principles We'll Apply

1. **Map is primary, panels are secondary** — Most work happens by
   interacting with the globe. Panels provide detail and configuration.
2. **Click-to-place, drag-to-move** — Entity placement should be as
   simple as clicking the map.
3. **Right-click context menus** — Context-sensitive actions everywhere.
4. **Property panel on selection** — Click entity → see/edit all its
   properties in right sidebar.
5. **Visual route editing** — Draw routes by clicking waypoints on map.
   Drag waypoints to adjust. Per-waypoint speed/altitude settings.
6. **Timeline scrubber** — Preview entity movements at any scenario time.
7. **Always-valid output** — The builder should never produce invalid YAML.
   Validate continuously.
8. **Import existing** — Load any valid scenario YAML back into the editor.

---

## Task 1: ORBAT Data Model & CSV Format

### 1a. ORBAT Data Model

The ORBAT represents all available assets across all organisations,
independent of any specific scenario. Think of it as "what do you have
in your toolkit?" — scenarios then draw from this toolkit.

Create `cop/src/orbat/orbat-model.js`:

```javascript
/**
 * ORBAT Data Model
 *
 * Structure:
 *   ORBAT
 *   └── Organisation (e.g., "Royal Malaysian Police", "MMEA")
 *       └── Unit/Asset
 *           ├── id (unique across ORBAT)
 *           ├── callsign / name
 *           ├── entity_type (from SCENARIO_AUTHORING.md types)
 *           ├── domain (MARITIME | AIR | GROUND_VEHICLE | PERSONNEL)
 *           ├── agency (RMP | MMEA | CI | RMAF | MIL | CIVILIAN)
 *           ├── sidc (20-digit MIL-STD-2525D code)
 *           ├── home_base { lat, lon, name }
 *           ├── speed_min (knots or km/h depending on domain)
 *           ├── speed_max
 *           ├── speed_cruise (default operational speed)
 *           ├── altitude_min (ft, for AIR domain)
 *           ├── altitude_max (ft, for AIR domain)
 *           ├── altitude_cruise (ft, for AIR domain)
 *           ├── sensors [] (e.g., "radar", "ais_receiver", "eo_ir")
 *           ├── weapons [] (future use)
 *           ├── personnel_count (for units)
 *           ├── status (OPERATIONAL | MAINTENANCE | RESERVE)
 *           ├── metadata {} (domain-specific key-value pairs)
 *           │   ├── ais_active (boolean, maritime)
 *           │   ├── adsb_active (boolean, air)
 *           │   ├── flag (string, maritime — e.g., "MYS")
 *           │   ├── vessel_type / aircraft_type (string)
 *           │   ├── mmsi (string, maritime)
 *           │   ├── icao_hex (string, air)
 *           │   └── ... (extensible)
 *           └── notes (free text)
 */

// Each Organisation:
//   id, name, abbreviation, color (hex), standard_identity (friend/
//   hostile/neutral), emblem_url (optional), units[]
//
// The ORBAT is saved/loaded as JSON. The CSV import/export is a
// flattened view for spreadsheet editing.
```

### 1b. CSV Format Definition

The CSV is a flat file with one row per asset. Organisations are
indicated by an `organisation` column. This means a single CSV can
contain multiple organisations, or separate CSVs per org.

**CSV Columns:**

```
id, callsign, organisation, agency, entity_type, domain, sidc,
home_base_name, home_base_lat, home_base_lon,
speed_min, speed_max, speed_cruise,
altitude_min, altitude_max, altitude_cruise,
sensors, personnel_count, status,
ais_active, adsb_active, flag, vessel_type, aircraft_type,
mmsi, icao_hex, notes
```

**Example rows:**

```csv
id,callsign,organisation,agency,entity_type,domain,sidc,home_base_name,home_base_lat,home_base_lon,speed_min,speed_max,speed_cruise,altitude_min,altitude_max,altitude_cruise,sensors,personnel_count,status,ais_active,adsb_active,flag,vessel_type,aircraft_type,mmsi,icao_hex,notes
MMEA-PV-101,KM Semporna,Malaysian Maritime Enforcement Agency,MMEA,MMEA_PATROL,MARITIME,10033000001204020000,Semporna Jetty,4.4837,118.6092,12,30,18,,,,radar;ais_receiver,15,OPERATIONAL,true,,MYS,Patrol Vessel,,533001234,,Zone Bravo primary patrol
MMEA-FI-201,KM Sangitan,Malaysian Maritime Enforcement Agency,MMEA,MMEA_FAST_INTERCEPT,MARITIME,10033000001204010000,Semporna Jetty,4.4837,118.6092,25,45,35,,,,radar;ais_receiver,8,OPERATIONAL,true,,MYS,Fast Intercept Craft,,533001235,,Rapid response craft
RMAF-MPA-01,TUDM Beechcraft 01,Royal Malaysian Air Force,RMAF,RMAF_MPA,AIR,10030100001101040000,Labuan Air Base,5.3007,115.2503,150,280,220,500,25000,15000,radar;eo_ir;ais_receiver,,OPERATIONAL,,true,MYS,,Maritime Patrol Aircraft,,750C01,,Primary MPA asset
RMP-GOF-01,GOF Alpha,Royal Malaysian Police,RMP,RMP_TACTICAL_TEAM,PERSONNEL,10031000001211000000,Semporna Police HQ,4.4820,118.6120,0,6,4,,,,,,8,OPERATIONAL,,,,,,,,GOF tactical response team
```

**Sensors** are semicolon-delimited within the column (e.g., `radar;ais_receiver;eo_ir`).

### 1c. CSV Import / Export

Create `cop/src/orbat/csv-io.js`:

```javascript
/**
 * CSV Import:
 * 1. Parse CSV using PapaParse (already available)
 * 2. Validate each row:
 *    - entity_type must be in the known types list
 *    - domain must be MARITIME|AIR|GROUND_VEHICLE|PERSONNEL
 *    - agency must be RMP|MMEA|CI|RMAF|MIL|CIVILIAN
 *    - sidc must be exactly 20 digits
 *    - lat/lon must be valid numbers
 *    - speeds must be non-negative numbers
 *    - status must be OPERATIONAL|MAINTENANCE|RESERVE
 * 3. Group rows by organisation column
 * 4. Build Organisation objects with their units
 * 5. Return { orbat: Orbat, errors: string[] }
 *
 * CSV Export:
 * 1. Flatten ORBAT into rows
 * 2. Generate CSV string
 * 3. Trigger browser download
 *
 * Also support: import from JSON, export to JSON (the native format).
 */
```

### 1d. ORBAT Persistence

ORBATs are saved in the browser using `localStorage` with the key
`edge_c2_orbats`. The data structure is:

```javascript
{
  version: 1,
  orbats: {
    "default": {
      name: "Malaysian ESSZONE Forces",
      created: "2026-03-01T...",
      modified: "2026-03-15T...",
      organisations: [ /* Organisation objects */ ]
    },
    "exercise_alpha": { ... }
  }
}
```

Multiple ORBATs can be stored. The user can also export/import the
full ORBAT as a JSON file for backup or sharing.

**Provide a built-in default ORBAT** that matches the entities used in
`demo_combined.yaml` so users can start immediately without importing
anything. Pre-populate it with all the Malaysian agencies and their
known assets from the existing scenarios.

---

## Task 2: SIDC Builder GUI

### 2a. The Problem

A 20-digit SIDC like `10033000001204020000` is inscrutable. Users need
a visual way to construct valid SIDCs for their ORBAT entries.

### 2b. Study the Existing Builder

The JMSML symbol builder at `~/joint-military-symbology-xml/` already
works. Study its code to understand:

1. How it parses SIDC positions (1-2: version, 3: context, 4: identity,
   5-6: symbol set, 7: status, 8: HQ/TF/dummy, 9-10: echelon,
   11-16: entity code, 17-18: modifier 1, 19-20: modifier 2)
2. How it maps positions to available SVG files
3. How it composites frame + icon + modifiers into a final symbol

### 2c. SIDC Builder Component

Create `cop/src/orbat/sidc-builder.js`:

A modal dialog that builds an SIDC interactively:

```
┌──────────────────────────────────────────────────────┐
│  SIDC Builder                                    [X] │
├──────────────────────────────────────────────────────┤
│                                                      │
│  ┌──────────────────┐  ┌──────────────────────────┐  │
│  │                  │  │                          │  │
│  │   [Live Symbol   │  │  SIDC: 10033000001204020 │  │
│  │    Preview]      │  │                          │  │
│  │                  │  │  Context:    [Reality ▼]  │  │
│  │   120×120px      │  │  Identity:   [Friend  ▼]  │  │
│  │   rendered from  │  │  Symbol Set: [Sea Sfc  ▼]  │  │
│  │   DISA SVGs      │  │  Status:     [Present ▼]  │  │
│  │                  │  │  HQ/TF:      [None    ▼]  │  │
│  └──────────────────┘  │  Echelon:    [None    ▼]  │  │
│                        │                          │  │
│                        │  Entity:  [search/browse] │  │
│                        │  ┌──────────────────────┐ │  │
│                        │  │ ▶ Combatant          │ │  │
│                        │  │   ▶ Line             │ │  │
│                        │  │   ▶ Patrol           │ │  │
│                        │  │     • Coastal         │ │  │
│                        │  │       • Station Ship ◄│ │  │
│                        │  │       • Patrol Craft  │ │  │
│                        │  │   ▶ Mine Warfare     │ │  │
│                        │  │ ▶ Non-combatant      │ │  │
│                        │  │ ▶ Merchant           │ │  │
│                        │  └──────────────────────┘ │  │
│                        │                          │  │
│                        │  Modifier 1: [None    ▼]  │  │
│                        │  Modifier 2: [None    ▼]  │  │
│                        └──────────────────────────┘  │
│                                                      │
│  [Cancel]                              [Apply SIDC]  │
└──────────────────────────────────────────────────────┘
```

**Key features:**
- **Live preview** updates instantly as user changes any dropdown.
  Uses the same DISA SVG compositor from the COP renderer.
- **Entity browser** is a collapsible tree matching the JMSML hierarchy
  for the selected symbol set. Clicking a leaf selects it.
- **Entity search** — type "patrol" to filter the tree to matching entries.
- **Dropdowns only show valid options** — changing Symbol Set updates
  available entities. Changing Context updates available identities.
- **Copy SIDC** button for pasting elsewhere.
- **Common presets** dropdown at the top: "MMEA Patrol Vessel", "RMAF
  Fighter", "Hostile Infantry" etc. — one click to get a known-good SIDC.

### 2d. Entity Code Data Source

The JMSML data files contain the full entity hierarchy for each symbol
set. You need to extract this data from the JMSML repo at
`~/joint-military-symbology-xml/`. Look for:

- XML/JSON files that map entity codes (positions 11-16) to human-readable
  names for each symbol set
- The modifier 1 and modifier 2 lookup tables per symbol set
- The frame selection rules

Build a JSON data file (`cop/src/data/jmsml-entities.json`) that the
SIDC builder can use at runtime. This is a build-time extraction — don't
ship the full JMSML repo to the browser.

---

## Task 3: ORBAT Manager Panel

### 3a. UI Layout

The ORBAT Manager is accessed from a tab in the left sidebar (alongside
the existing agency filter panel). It shows when in Builder mode.

```
┌─────────────────────────────┐
│  [Scenario] [ORBAT] [Layers]│  ◄── Tab bar at top of left sidebar
├─────────────────────────────┤
│  ORBAT: Malaysian ESSZONE ▼ │  ◄── ORBAT selector dropdown
│  [Import CSV] [Export] [+]  │  ◄── Action buttons
├─────────────────────────────┤
│                             │
│  ▼ 🟦 RMP (12 assets)      │  ◄── Org header (collapsible)
│    ├ RMP-GOF-01 GOF Alpha   │      with coloured agency badge
│    ├ RMP-GOF-02 GOF Bravo   │
│    ├ RMP-MP-101 Patrol 1    │
│    ├ 🚁 RMP-HELI-01 AW139  │
│    └ ... (+6 more)          │
│                             │
│  ▼ 🟩 MMEA (8 assets)      │
│    ├ 🚢 MMEA-PV-101 KM Sem │
│    ├ 🚢 MMEA-FI-201 KM San │
│    └ ... (+5 more)          │
│                             │
│  ▶ 🟨 CI (4 assets)        │  ◄── Collapsed
│  ▶ 🟧 RMAF (6 assets)      │
│  ▶ 🟥 MIL (10 assets)      │
│  ▶ ⬜ CIVILIAN (0 assets)  │
│                             │
│  [+ Add Organisation]       │
└─────────────────────────────┘
```

**Interactions:**
- **Click organisation header** → expand/collapse asset list
- **Click asset** → select it; if on map, fly camera to its home base;
  show asset detail in right panel
- **Right-click asset** → context menu: Edit, Duplicate, Delete, Add to
  Scenario, Show on Map
- **Right-click org header** → context menu: Add Asset, Import CSV for
  this org, Export this org CSV, Rename, Delete
- **Drag asset** from ORBAT panel onto the map → places it in the
  current scenario at the drop position (shortcut for "Add to Scenario")
- **[+] button** → opens the "Add Asset" dialog with the SIDC builder
- **[Import CSV]** → file picker, then runs CSV import with validation
  feedback
- **Search box** at the top (below tabs) → filters the tree in real-time

### 3b. Asset Detail / Edit Panel

When an asset is selected, the right sidebar shows an editable form:

```
┌─────────────────────────────┐
│  ◄ Back to list             │
├─────────────────────────────┤
│                             │
│  ┌────┐  MMEA-PV-101       │
│  │SYMB│  KM Semporna        │
│  │OL  │  MMEA Patrol Vessel │
│  └────┘  Agency: MMEA       │
│                             │
├─────────────────────────────┤
│  Callsign: [KM Semporna   ]│
│  Entity Type: [MMEA_PATROL▼]│
│  SIDC: [10033000001204020 ] │
│       [Open SIDC Builder 🔧]│
│                             │
│  ── Performance ──          │
│  Speed Min:     [12   ] kts │
│  Speed Max:     [30   ] kts │
│  Speed Cruise:  [18   ] kts │
│                             │
│  ── Home Base ──            │
│  Name: [Semporna Jetty    ] │
│  Lat:  [4.4837            ] │
│  Lon:  [118.6092          ] │
│  [📍 Pick from Map]         │
│                             │
│  ── Sensors ──              │
│  [x] Radar                  │
│  [x] AIS Receiver           │
│  [ ] EO/IR                  │
│  [ ] ESM                    │
│                             │
│  ── Metadata ──             │
│  AIS Active: [Yes ▼]       │
│  Flag: [MYS              ] │
│  Vessel Type: [Patrol Vsl] │
│  MMSI: [533001234        ] │
│                             │
│  ── Notes ──                │
│  [Zone Bravo primary patro] │
│                             │
│  [Save] [Delete] [Duplicate]│
└─────────────────────────────┘
```

**Key interactions:**
- **[Open SIDC Builder]** opens the modal from Task 2
- **[📍 Pick from Map]** enters a mode where next map click sets home base coords
- Fields auto-save on blur (debounced)
- Entity Type dropdown changes the domain and adjusts available fields
  (e.g., altitude fields only show for AIR domain)
- Invalid values show red border + tooltip with error message

---

## Task 4: Scenario Editor — Entity Placement

### 4a. Mode Switching

Add a mode toggle to the COP header bar:

```
[▶ PLAY] [🔧 BUILD]  ←  Two toggle buttons, mutually exclusive
```

- **PLAY mode** = current COP behavior (WebSocket, playback, timeline)
- **BUILD mode** = scenario editor (no WebSocket, map interaction for
  editing, property panels)

When entering BUILD mode:
- Disconnect WebSocket (if connected)
- Show builder-specific panels (ORBAT tab, scenario tab, layers tab)
- Enable map interaction handlers (click-to-place, drag, right-click menus)
- Show the builder toolbar on the map

When entering PLAY mode:
- Hide builder panels
- Reconnect WebSocket
- Resume normal COP operation

### 4b. Scenario Panel (Left Sidebar)

The Scenario tab shows the current scenario structure:

```
┌─────────────────────────────┐
│  [Scenario] [ORBAT] [Layers]│
├─────────────────────────────┤
│  Scenario: [New Scenario  ▼]│
│  [New] [Load YAML] [Save]   │
├─────────────────────────────┤
│  Name: [Sulu Sea Intercept ]│
│  Duration: [60] minutes     │
│  Description: [Multi-agency]│
├─────────────────────────────┤
│  ── Scenario Entities ──    │
│  ▼ 🟩 MMEA (3)             │
│    ├ MMEA-PV-101 KM Semp ● │  ◄── ● = placed on map
│    ├ MMEA-FI-201 KM Sang ● │
│    └ MMEA-PV-102 KM Mari ○ │  ◄── ○ = not placed yet
│  ▼ 🟧 RMAF (1)             │
│    └ RMAF-MPA-01 Beechcr ● │
│  ▼ ⚠ SUSPECTS (2)          │
│    ├ SUSPECT-001 Unknown ● │
│    └ SUSPECT-002 Dark Vs ● │
│  ▼ 👥 BACKGROUND (3 groups)│
│    ├ 12× CIVILIAN_FISHING   │
│    ├ 5× CIVILIAN_CARGO      │
│    └ 3× CIVILIAN_TANKER     │
│                             │
│  [+ From ORBAT] [+ Manual]  │
│  [+ Background Group]       │
├─────────────────────────────┤
│  ── Events (17) ──          │
│  [+ Add Event]              │
│  00:00 DETECTION Radar con  │
│  00:03 ALERT Intel warning  │
│  00:05 ORDER MMEA-PV-101 →  │
│  00:14 ORDER KM Sangitan →  │
│  ...                        │
└─────────────────────────────┘
```

**[+ From ORBAT]** — Opens a picker showing the ORBAT. Select one or
more assets → they're added to the scenario with their ORBAT properties
pre-filled (callsign, type, SIDC, speeds, metadata). User still needs
to place them on the map.

**[+ Manual]** — Creates a blank entity. User fills in all fields.

**[+ Background Group]** — Adds a background entity configuration
(type, count, area or route, speed variation).

### 4c. Entity Placement on Map

When an unplaced entity is selected in the Scenario panel (○ indicator):

1. A toast appears: "Click on the map to place KM Semporna"
2. Cursor changes to crosshair
3. Click on map → entity is placed at that position
4. Entity's 2525D symbol appears on the map at that position
5. Entity is now "placed" (● indicator)

When a placed entity is selected:
- Its symbol pulses/highlights on the map
- A drag handle appears — drag to reposition
- Right-click on the symbol → context menu:
  - Edit Properties
  - Set Behavior (patrol, standby, stationary)
  - Define Waypoints (enters route drawing mode)
  - Remove from Scenario
  - Fly to Home Base

### 4d. Map Interaction Handlers

Create `cop/src/builder/map-interaction.js`:

**Click modes** (selected from builder toolbar):

| Mode | Cursor | Action |
|------|--------|--------|
| SELECT | default | Click entity to select. Drag to pan. |
| PLACE | crosshair | Click to place the selected unplaced entity |
| WAYPOINT | crosshair+pin | Click to add waypoints to selected entity's route |
| AREA | crosshair+polygon | Click to add vertices to a polygon area |
| MEASURE | crosshair+ruler | Click two points to measure distance |

**Builder Toolbar** (floating, top-left of map, below header):

```
[🔍 Select] [📍 Place] [📐 Route] [⬡ Area] [📏 Measure]
```

Only one mode active at a time. SELECT is default.

### 4e. Right-Click Context Menu

Right-clicking on the map (not on an entity) shows:

```
┌──────────────────────────┐
│  Add Entity Here         │
│  Add Waypoint Here       │
│  Start New Area          │
│  Add Reference Point     │
│  ─────────────────────── │
│  Copy Coordinates        │
│  Center Map Here         │
│  Measure from Here       │
└──────────────────────────┘
```

Right-clicking on an entity shows:

```
┌──────────────────────────┐
│  Edit Properties         │
│  Set Behavior ►          │  ◄── Submenu: patrol, standby, stationary
│  Define Route            │
│  ─────────────────────── │
│  Duplicate Entity        │
│  Remove from Scenario    │
│  ─────────────────────── │
│  Add Event for Entity ►  │  ◄── Submenu: ORDER, DETECTION, etc.
│  Fly to Entity           │
│  Show in Scenario Panel  │
└──────────────────────────┘
```

---

## Task 5: Route & Waypoint Editor

This is the most interaction-heavy feature and must feel fluid.

### 5a. Route Drawing Mode

When user selects an entity and enters Route mode (via toolbar, context
menu, or the entity's "Define Waypoints" action):

1. Existing waypoints (if any) appear as numbered circles connected by
   lines on the map.
2. The route line is color-coded by speed (blue=slow, green=cruise,
   red=fast) with graduated coloring between waypoints.
3. Click on map → adds a new waypoint at that position, appended to the
   end of the route.
4. Each waypoint shows a small label: `WP1 4kts 00:00`
5. **ESC** or clicking the toolbar button exits route mode.

### 5b. Waypoint Manipulation

- **Drag a waypoint** → repositions it. Route lines update in real-time.
  Time offsets are automatically recalculated based on distance and speed.
- **Click a waypoint** → selects it. Shows waypoint properties in a
  floating popover near the waypoint:

```
┌─────────────────────────┐
│  Waypoint 3             │
│  Lat:  [5.750   ]      │
│  Lon:  [118.850 ]      │
│  Speed: [4     ] kts   │
│  Time:  [00:10 ] (auto)│  ◄── Auto-calculated from distance/speed
│  Alt:   [0     ] ft    │  ◄── Only for AIR domain
│  ─────────────────────  │
│  Metadata Overrides:    │
│  [x] AIS goes dark here │
│  ─────────────────────  │
│  [Insert Before] [Delete]│
└─────────────────────────┘
```

- **Right-click waypoint** → context menu:
  - Insert Waypoint Before
  - Insert Waypoint After
  - Delete Waypoint
  - Set as Loiter Point (speed=0, entity waits here)
  - Copy Coordinates
- **Double-click on route line between two waypoints** → inserts a new
  waypoint at that position on the line.
- **Ctrl+drag waypoint** → duplicates it (like CMANO).

### 5c. Time Calculation

Waypoint times can be:
- **Auto-calculated** (default): Time offset = distance from previous
  waypoint ÷ speed. Shown with "(auto)" label.
- **Manual override**: User types a specific time. Shown without "(auto)".
  If manually set, subsequent auto times cascade from this anchor.

Use geodesic distance calculation (great circle) for accuracy.

### 5d. Route Preview

A "Preview Route" button shows an animated entity moving along the route
at accelerated speed (like a scrubber). This helps the user verify the
route looks correct before running the full simulation.

### 5e. Patrol Area Definition

For entities with `behavior: "patrol"`, instead of waypoints they need a
patrol area (GeoJSON polygon). The area editor:

1. Switch to AREA mode from toolbar.
2. Click vertices on map to define polygon boundary.
3. Double-click to close the polygon.
4. Vertices can be dragged to reshape.
5. The polygon is semi-transparent, colored by agency.
6. Right-click vertex → Delete Vertex, Insert Vertex After.
7. Areas can reference existing GeoJSON zones by name instead of defining
   new geometry (dropdown: "Use existing zone → esszone_sector_2").

---

## Task 6: Event Scripting Editor

### 6a. Event List in Scenario Panel

Events are shown in the bottom section of the Scenario panel (left sidebar),
sorted by time. Each event is a compact row:

```
[00:14] [ORDER ▼] [⚠] MMEA orders intercept  [✏] [🗑]
```

- Time badge (monospace, amber background)
- Type dropdown (can change inline)
- Severity icon
- Description (truncated, full on hover)
- Edit pencil → opens event editor
- Delete trash → removes event (with confirmation)

### 6b. Event Editor Modal

```
┌──────────────────────────────────────────────────────┐
│  Event Editor                                    [X] │
├──────────────────────────────────────────────────────┤
│                                                      │
│  Time:     [00] : [14]  (MM:SS from scenario start)  │
│  Type:     [ORDER              ▼]                    │
│  Severity: [WARNING            ▼]                    │
│                                                      │
│  Description:                                        │
│  [MMEA orders KM Sangitan to investigate contacts  ] │
│                                                      │
│  ── Target(s) ──                                     │
│  [Single ▼]  [MMEA-FI-201 KM Sangitan ▼]           │
│  (or [Multiple ▼] → checkboxes for entity selection) │
│                                                      │
│  ── Action ──  (shown when Type = ORDER)             │
│  Action: [intercept           ▼]                     │
│                                                      │
│  ── Action Parameters ──                             │
│  Intercept Target: [SUSPECT-001 Unknown Trawler ▼]  │
│  (fields change based on selected action)            │
│                                                      │
│  ── Alert Agencies ──                                │
│  [x] RMP  [ ] MMEA  [ ] CI  [ ] RMAF  [x] MIL      │
│                                                      │
│  ── Position ──  (optional, for DETECTION/INCIDENT)  │
│  Lat: [5.70    ]  Lon: [118.80  ]                    │
│  [📍 Pick from Map]                                   │
│                                                      │
│  [Cancel]                                   [Save]   │
└──────────────────────────────────────────────────────┘
```

**Action-specific fields** (shown/hidden based on `action` dropdown):

| Action | Extra Fields |
|--------|-------------|
| `intercept` | Intercept Target (entity dropdown) |
| `deploy` | Destination lat/lon (with map picker) |
| `search_area` | Area (dropdown of defined areas + GeoJSON zones) |
| `patrol` | Patrol Area (optional area override) |
| `respond` | Destination lat/lon |
| `escort_to_port` | Escort entity IDs (multi-select) |
| `activate` | (none) |
| `lockdown` | (none) |

### 6c. Event Creation Shortcuts

- **Right-click entity → Add Event for Entity** → opens event editor
  with target pre-filled.
- **Click "+" on timeline** → opens event editor with time pre-filled
  based on timeline position.
- **Duplicate event** → creates a copy with time +1 minute (adjustable).

---

## Task 7: Background Entity Configuration

### 7a. Background Group Editor

Background entities (ambient traffic) are configured through a dedicated
editor, simpler than the full entity editor:

```
┌─────────────────────────────┐
│  Background Traffic Group   │
├─────────────────────────────┤
│  Type: [CIVILIAN_FISHING ▼] │
│  Count: [12              ]  │
│  Speed Variation: [0.15  ]  │
│                             │
│  ── Area / Route ──         │
│  [● Area  ○ Route]          │
│                             │
│  Area: [esszone_sector_2 ▼] │  ◄── Dropdown of available GeoJSON zones
│  (or)                       │
│  [Define New Area on Map]   │
│                             │
│  ── Metadata ──             │
│  AIS Active: [Yes ▼]       │
│  Flag: [MYS              ] │
│                             │
│  [Save] [Delete]            │
└─────────────────────────────┘
```

When an area is selected, its polygon is highlighted on the map in a
semi-transparent overlay.

---

## Task 8: YAML Import / Export Engine

### 8a. Export to YAML

Create `cop/src/builder/yaml-engine.js`:

The export engine converts the in-memory scenario state to valid YAML
matching the `SCENARIO_AUTHORING.md` format exactly.

```javascript
/**
 * Export workflow:
 * 1. Validate entire scenario (entity types, positions, event references)
 * 2. Build the YAML structure:
 *    scenario:
 *      name, description, duration_minutes, center, zoom
 *      background_entities: [...]
 *      scenario_entities: [...]
 *      events: [...]
 * 3. Serialize to YAML string (use js-yaml library)
 * 4. Trigger browser download as .yaml file
 *
 * Validation errors show in a modal before export:
 *   ✗ Entity SUSPECT-001 has no waypoints and no behavior set
 *   ✗ Event at 00:14 references entity "XXX" not in scenario
 *   ✓ 11 entities valid
 *   ✓ 17 events in chronological order
 */
```

### 8b. Import from YAML

```javascript
/**
 * Import workflow:
 * 1. Parse YAML file (js-yaml)
 * 2. Validate structure matches expected format
 * 3. For each scenario_entity:
 *    - Create entity in scenario state
 *    - Place on map at initial_position
 *    - If waypoints present, create route
 * 4. For each background_entity group:
 *    - Create background group config
 * 5. For each event:
 *    - Create event in scenario state
 * 6. Set scenario metadata (name, description, duration, center, zoom)
 * 7. Fly camera to scenario center position
 * 8. Report: "Loaded 11 entities, 3 background groups, 17 events"
 *
 * Handle gracefully:
 *   - Unknown entity types → import anyway with warning
 *   - Missing optional fields → use defaults
 *   - Invalid coordinates → flag error, skip entity
 */
```

### 8c. Round-trip Fidelity

Critical: **Loading a YAML file and immediately exporting it must produce
the same file** (modulo whitespace/comment differences). This means:

- All YAML fields must be preserved, including unknown/extra fields
- Field ordering should match the convention in SCENARIO_AUTHORING.md
- Numbers should not gain/lose precision
- Strings should not be unnecessarily quoted

Write tests that load `demo_combined.yaml`, export it, and diff the
result against the original.

---

## Task 9: Scenario Preview & Validation

### 9a. Timeline Scrubber

At the bottom of the BUILD mode UI, replace the event timeline with a
scenario preview scrubber:

```
┌─────────────────────────────────────────────────────────────┐
│  [▶ Preview]  ■■■■■■■■■■■■●──────────────  [00:14 / 01:00] │
│               ▲            ▲                                │
│               events       current time                      │
│  Speed: [1x] [2x] [5x] [10x]                               │
└─────────────────────────────────────────────────────────────┘
```

- **Preview button** → animates entities along their waypoints/routes on
  the map, without needing the simulation engine running.
- Event markers appear as ticks on the scrubber bar.
- Drag the scrubber to jump to any point in the scenario.
- Entities interpolate position based on their waypoints using the same
  great-circle math as the simulator.
- Events fire visually (flash on timeline) as the scrubber passes them.
- This is purely client-side — no WebSocket or simulator needed.

### 9b. Continuous Validation

Run validation in the background as the user edits. Show a status
indicator in the header:

```
[✓ Valid]     ← Green badge, all checks pass
[⚠ 2 Issues] ← Amber badge, click to see list
[✗ 5 Errors] ← Red badge, click to see list
```

Validation checks (run on every change, debounced):
1. All entities have valid positions (lat between -90/90, lon -180/180)
2. All entity types are recognized
3. All entity IDs are unique
4. All events are in chronological order
5. All entity references in events point to existing entities
6. Waypoint speeds are within entity type limits
7. At least one scenario entity exists
8. Scenario has a name and duration > 0
9. Waypoint coordinates are in water (maritime) or on land (ground) —
   use a rough bounding box check, not full geography

### 9c. Validation Results Modal

Clicking the status badge shows:

```
┌──────────────────────────────────────────────┐
│  Scenario Validation                     [X] │
├──────────────────────────────────────────────┤
│                                              │
│  ✓ 11 scenario entities, all types valid     │
│  ✓ 3 background entity groups                │
│  ✓ 17 events in chronological order          │
│  ✓ All entity IDs unique                     │
│                                              │
│  ⚠ Entity MMEA-PV-102 has behavior "patrol"  │
│    but no patrol_area defined                │
│    [Fix →]                                   │
│                                              │
│  ⚠ Waypoint 3 of SUSPECT-001: speed 45 kts  │
│    exceeds SUSPECT_VESSEL max of 40 kts      │
│    [Fix →]                                   │
│                                              │
│  ✓ No coordinate errors                      │
│                                              │
│  Overall: ⚠ 2 warnings                      │
│  [Export Anyway]  [Fix Issues]               │
└──────────────────────────────────────────────┘
```

**[Fix →]** links select the offending entity/event and scroll to it.

---

## Task 10: Visual Design & Theme

### 10a. Design Language

The Scenario Builder must match the COP's existing dark theme from
`COP_DASHBOARD_DESIGN.md`:

- **Background**: `#0D1117` (GitHub Dark)
- **Surface**: `#161B22` (panels, cards)
- **Border**: `#30363D`
- **Text primary**: `#C9D1D9`
- **Text secondary**: `#8B949E`
- **Accent**: `#58A6FF` (interactive elements)
- **Success**: `#3FB950`
- **Warning**: `#D29922`
- **Error**: `#F85149`
- **Fonts**: IBM Plex Sans (UI), JetBrains Mono (data, coordinates)

### 10b. Agency Colors (consistent with COP)

```
RMP:      #4A90D9 (blue)
MMEA:     #50C878 (green)
CI:       #FFB347 (amber)
RMAF:     #FF8C42 (orange)
MIL:      #FF6B6B (red)
CIVILIAN: #8B949E (grey)
HOSTILE:  #F85149 (bright red)
SUSPECT:  #D29922 (amber)
```

### 10c. Map Overlay Styling

- **Placed entities**: Full-opacity 2525D symbols, matching COP rendering
- **Unplaced entities**: Ghosted/dimmed symbol in the panel, no map marker
- **Selected entity**: Pulsing highlight ring around symbol
- **Waypoint markers**: Numbered circles (12px), white fill, colored border
  matching agency. Connected by dashed line colored by speed gradient.
- **Patrol areas**: Semi-transparent polygon fill (agency color at 15%
  opacity), dashed border (agency color at 60% opacity)
- **Route lines**: Solid 2px line, color interpolated by speed:
  - 0-25% of max speed: `#4A90D9` (blue, slow)
  - 25-75% of max speed: `#50C878` (green, cruise)
  - 75-100% of max speed: `#FF6B6B` (red, fast)
- **Background entity zones**: Very faint fill (5% opacity), dotted border
- **Reference points**: Small diamond markers with labels

### 10d. Responsive Panels

- Left sidebar: 240px wide in BUILD mode (wider than PLAY mode's 200px
  to accommodate editor controls)
- Right sidebar (property editor): 300px wide, slides in/out
- Panels are resizable by dragging their border (min 200px, max 400px)
- On smaller screens (<1400px): panels overlay the map instead of
  pushing it

---

## Implementation Order

Execute these tasks in order. Each builds on the previous.

### Phase A: Foundation (Tasks 1, 2)
1. ORBAT data model and CSV import/export
2. SIDC builder component (requires JMSML data extraction)
3. ORBAT persistence (localStorage + JSON file I/O)
4. Default ORBAT with Malaysian agency assets

### Phase B: ORBAT Manager UI (Task 3)
5. ORBAT panel (org tree with expand/collapse)
6. Asset detail/edit panel
7. Add/edit/delete asset flows
8. CSV import wizard with validation feedback

### Phase C: Scenario Editor Core (Tasks 4, 8)
9. Mode switching (PLAY ↔ BUILD)
10. Scenario panel (entity list, background groups)
11. Entity placement (click-to-place, drag-to-move)
12. Right-click context menus
13. YAML import/export engine
14. "Add from ORBAT" flow

### Phase D: Route & Area Editing (Task 5)
15. Waypoint route drawing mode
16. Waypoint manipulation (drag, insert, delete)
17. Per-waypoint property popover
18. Time auto-calculation
19. Patrol area polygon editor

### Phase E: Event Scripting (Task 6)
20. Event list in scenario panel
21. Event editor modal
22. Event creation shortcuts
23. Event-entity linking

### Phase F: Background & Preview (Tasks 7, 9)
24. Background entity group editor
25. Timeline scrubber with entity animation preview
26. Continuous validation engine
27. Validation results modal

### Phase G: Polish (Task 10)
28. Full visual design pass
29. Keyboard shortcuts (matching COP_DASHBOARD_DESIGN.md patterns)
30. Round-trip YAML fidelity tests
31. Edge case handling (empty scenarios, max entities, etc.)

---

## File Structure

```
cop/src/
├── builder/
│   ├── builder-mode.js          # Mode switching logic
│   ├── map-interaction.js       # Click/drag/right-click handlers
│   ├── context-menu.js          # Right-click menu component
│   ├── scenario-panel.js        # Left sidebar scenario tab
│   ├── entity-placer.js         # Entity placement on map
│   ├── route-editor.js          # Waypoint route drawing/editing
│   ├── area-editor.js           # Polygon area drawing/editing
│   ├── event-editor.js          # Event editor modal
│   ├── event-list.js            # Event list component
│   ├── background-editor.js     # Background entity group editor
│   ├── preview-scrubber.js      # Timeline scrubber for preview
│   ├── validation.js            # Continuous validation engine
│   ├── validation-modal.js      # Validation results display
│   └── yaml-engine.js           # YAML import/export
├── orbat/
│   ├── orbat-model.js           # Data model classes
│   ├── orbat-panel.js           # ORBAT tree panel component
│   ├── orbat-store.js           # ORBAT persistence (localStorage + file)
│   ├── asset-detail.js          # Asset detail/edit panel
│   ├── csv-io.js                # CSV import/export
│   ├── sidc-builder.js          # SIDC builder modal
│   └── sidc-data.js             # Extracted JMSML entity/modifier data
├── data/
│   └── jmsml-entities.json      # Build-time extracted JMSML hierarchy
│   └── default-orbat.json       # Pre-built Malaysian agencies ORBAT
└── shared/
    ├── map-utils.js             # Geodesic math, coordinate helpers
    └── interpolation.js         # Great-circle position interpolation
```

---

## Dependencies

Add to `cop/package.json`:

```json
{
  "js-yaml": "^4.1.0",      // YAML parsing/serialization
  "papaparse": "^5.4.1"     // CSV parsing (already available if using React artifacts)
}
```

No other new dependencies. The SIDC builder reuses the existing DISA SVG
rendering pipeline from `CLAUDE_CODE_REPLACE_MILSYMBOL.md`.

---

## Key UX Decisions

1. **ORBAT is separate from scenarios.** You build your ORBAT once (or
   import it), then pull assets from it into multiple scenarios. This
   matches how real military planning works — the ORBAT is the "inventory"
   and scenarios are the "plans."

2. **Click-to-place is king.** The most common action (placing an entity)
   should be the simplest possible interaction: click ORBAT asset → click
   map → done.

3. **Route editing must be fluid.** Drawing waypoints should feel like
   drawing in a graphics app — click to add, drag to adjust, double-click
   to insert. No modal dialogs needed for basic route editing.

4. **Validate early, validate often.** Don't let the user discover
   problems at export time. Show warnings inline as they edit.

5. **YAML round-trip is sacred.** Users will edit YAML by hand AND use
   the GUI. Both must work. Loading then saving must not corrupt data.

6. **No backend required.** Everything runs in the browser. Files are
   saved via download / loaded via file picker. ORBATs persist in
   localStorage. This keeps deployment simple for the demo.

---

## Testing Strategy

### Unit Tests
- ORBAT model: create, modify, serialize/deserialize
- CSV import: valid data, missing columns, invalid types, encoding
- CSV export: round-trip matches input
- SIDC builder: valid code generation for each symbol set
- YAML engine: round-trip fidelity with demo_combined.yaml
- Validation: each rule triggers correctly
- Geodesic math: known distances produce correct times
- Waypoint interpolation: position at time=midpoint is on great circle

### Integration Tests
- Load demo_combined.yaml → all entities appear on map → export → diff
- Create scenario from scratch → place entities → add routes → add events
  → export → load in simulator → entities move correctly
- Import CSV → assets appear in ORBAT → add to scenario → verify SIDC
  renders correctly

### Manual Testing Checklist
- [ ] Mode switch PLAY ↔ BUILD doesn't lose state
- [ ] ORBAT persists across browser refresh
- [ ] Entity drag-and-drop from ORBAT to map works
- [ ] Route drawing with 10+ waypoints is smooth (no lag)
- [ ] Right-click menus appear at correct position
- [ ] SIDC builder live preview updates instantly
- [ ] All agency colors render correctly
- [ ] YAML export matches SCENARIO_AUTHORING.md format exactly
- [ ] Can load both demo scenarios and re-export them

---

## Definition of Done

The Scenario Builder is complete when:

1. A user can create a new scenario entirely through the GUI:
   - Import an ORBAT from CSV
   - Add entities from the ORBAT to a scenario
   - Place them on the CesiumJS map
   - Draw routes with waypoints
   - Define patrol areas
   - Script events with the event editor
   - Preview the scenario with the timeline scrubber
   - Export valid YAML

2. A user can load `demo_combined.yaml` (or any existing scenario) and:
   - See all entities on the map
   - Modify routes, add/remove entities, change events
   - Export the modified scenario
   - The exported YAML validates and runs in the simulator

3. The SIDC builder produces valid 20-digit codes and renders correct
   2525D symbols for all symbol sets used in the project.

4. The ORBAT CSV import/export works with the defined format and handles
   edge cases gracefully.

5. Visual quality matches the COP dark theme and looks professional
   enough for the Malaysian defense demo.
