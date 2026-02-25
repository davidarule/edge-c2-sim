# Scenario Authoring Guide

## Overview

Scenarios are YAML files that define a complete simulation — entities, their 
movements, and timed events. **No code changes are needed to create new scenarios.**

Place scenario files in `config/scenarios/`. Run them with:
```bash
edge-c2-sim --scenario config/scenarios/your_scenario.yaml
```

---

## Scenario File Structure

```yaml
scenario:
  name: "Human-readable scenario name"
  description: |
    Multi-line description of what happens.
  duration_minutes: 60
  center: { lat: 5.50, lon: 118.50 }   # Initial camera position
  zoom: 9                                # Initial zoom level

  background_entities:    # Ambient traffic (auto-generated)
    - ...

  scenario_entities:      # Named entities with scripted behavior
    - ...

  events:                 # Timed events driving the narrative
    - ...
```

---

## Background Entities

These are auto-generated entities that create realistic ambient traffic. 
They don't have specific scripts — the simulator generates routes and 
movements automatically.

```yaml
background_entities:
  - type: CIVILIAN_FISHING      # Entity type (see Entity Types below)
    count: 12                   # How many to generate
    area: "esszone_sector_2"    # GeoJSON polygon ID from geodata/areas/
    speed_variation: 0.15       # ±15% random speed variation
    metadata:                   # Applied to all generated entities
      ais_active: true
      flag: "MYS"

  - type: CIVILIAN_CARGO
    count: 5
    route: "sulu_sea_transit_corridor"  # GeoJSON LineString from geodata/routes/
    speed_variation: 0.1
```

**Key fields:**
- `type` — one of the Entity Types listed below
- `count` — number to generate
- `area` — entities patrol randomly within this GeoJSON polygon
- `route` — entities follow this GeoJSON LineString
- `speed_variation` — randomize speed ±X% for realism
- `metadata` — key-value pairs added to each entity

---

## Scenario Entities

Named entities with specific starting positions and scripted behaviors.

### Basic entity definition:
```yaml
scenario_entities:
  - id: "MMEA-PV-101"           # Unique ID (used in events to reference)
    type: MMEA_PATROL            # Entity type
    callsign: "KM Semporna"     # Display name
    agency: MMEA                 # Agency: RMP, MMEA, CI, RMAF, MIL
    initial_position:
      lat: 5.84
      lon: 118.07
    behavior: "patrol"           # Starting behavior
    patrol_area: "zone_bravo"    # Area for patrol behavior
    metadata:                    # Domain-specific data
      vessel_type: "Patrol vessel"
      speed_max_knots: 25
```

### Entity with waypoints (scripted route):
```yaml
  - id: "SUSPECT-001"
    type: SUSPECT_VESSEL
    callsign: "Unknown Trawler"
    initial_position: { lat: 5.80, lon: 118.90 }
    waypoints:
      - { lat: 5.75, lon: 118.85, speed: 4, time: "00:00" }
      - { lat: 5.70, lon: 118.80, speed: 3, time: "00:10" }
      - { lat: 5.65, lon: 118.75, speed: 3, time: "00:20" }
      # Entity stops here
      - { lat: 5.65, lon: 118.75, speed: 0, time: "00:25" }
    metadata:
      ais_active: false
      flag: "VNM"
```

### Behaviors

| Behavior | Description |
|----------|-------------|
| `patrol` | Move randomly within `patrol_area` polygon |
| `standby` | Stationary at `initial_position` until activated by event |
| `stationary` | Always stationary (checkpoints, fixed positions) |
| (waypoints) | If `waypoints` defined, follow them regardless of behavior |

When an event changes an entity's behavior (e.g., ORDER → intercept), 
the simulator overrides the current behavior.

---

## Events

Timed events drive the scenario narrative. They fire at specific times 
relative to scenario start.

### Event format:
```yaml
events:
  - time: "00:14"              # MM:SS from scenario start
    type: "ORDER"              # Event type (see below)
    description: "MMEA orders KM Sangitan to investigate contacts"
    target: "MMEA-PV-102"     # Entity this event affects
    action: "intercept"        # What the entity should now do
    intercept_target: "SUSPECT-001"  # Who to intercept
    severity: "WARNING"        # INFO, WARNING, CRITICAL
    alert_agencies: [MMEA, MIL]  # Agencies notified (for COP display)
```

### Event Types

| Type | Description | Typical Fields |
|------|-------------|----------------|
| `DETECTION` | Sensor/radar detects something | `position`, `alert_agencies` |
| `ALERT` | Intelligence assessment or warning | `description`, `alert_agencies`, `severity` |
| `ORDER` | Command to entity(s) to take action | `target`/`targets`, `action`, `destination` |
| `INCIDENT` | Something bad happens (attack, explosion) | `position`, `severity: CRITICAL` |
| `ARRIVAL` | Entity arrives at destination | `source` |
| `INTERCEPT` | Entity reaches and stops target | `source`, `target` |
| `BOARDING` | Law enforcement boards vessel | `source`, `target` |
| `RESOLUTION` | Scenario concludes | `description` |
| `AIS_LOSS` | Vessel AIS goes dark | `target` |

### Event Actions

When an ORDER event fires, the `action` field tells the simulator what 
the target entity should do:

| Action | Description | Required Fields |
|--------|-------------|-----------------|
| `intercept` | Chase and intercept a target | `intercept_target` |
| `deploy` | Move to a destination at best speed | `destination: {lat, lon}` |
| `search_area` | Fly/patrol a search pattern | `area` (polygon ID) |
| `patrol` | Resume patrol behavior | `patrol_area` (optional) |
| `respond` | Emergency response to location | `destination: {lat, lon}` |
| `lockdown` | Entity stays in place, blocks area | — |
| `escort_to_port` | Guide seized vessels to port | `escort: [entity_ids]` |
| `activate` | Wake up from standby | — |
| `process` | CI processing of detained persons | — |
| `secure` | Mark area as secured | — |
| `airlift` | Air transport to destination | `destination: {lat, lon}` |

### Targeting multiple entities:
```yaml
  - time: "00:18"
    type: "ORDER"
    targets: ["RMP-MP-101", "RMP-MP-102"]  # Note: "targets" plural
    action: "deploy"
    destination: { lat: 4.47, lon: 118.66 }
```

---

## Entity Types Reference

### Maritime
| Type | Agency | Speed (kts) | Description |
|------|--------|-------------|-------------|
| `CIVILIAN_CARGO` | CIVILIAN | 10-16 | Merchant cargo vessel |
| `CIVILIAN_TANKER` | CIVILIAN | 10-15 | Oil/chemical tanker |
| `CIVILIAN_FISHING` | CIVILIAN | 3-8 | Fishing boat |
| `CIVILIAN_PASSENGER` | CIVILIAN | 12-22 | Ferry/cruise |
| `MMEA_PATROL` | MMEA | 12-30 | MMEA patrol vessel |
| `MMEA_FAST_INTERCEPT` | MMEA | 25-45 | MMEA fast intercept craft |
| `MIL_NAVAL` | MIL | 15-30 | Navy warship/patrol vessel |
| `SUSPECT_VESSEL` | — | 8-40 | Unidentified/hostile vessel |

### Aviation
| Type | Agency | Speed (kts) | Alt (ft) | Description |
|------|--------|-------------|----------|-------------|
| `CIVILIAN_COMMERCIAL` | CIVILIAN | 140-500 | 0-41000 | Commercial airliner |
| `CIVILIAN_LIGHT` | CIVILIAN | 80-200 | 0-15000 | Small aircraft |
| `RMAF_FIGHTER` | RMAF | 200-600 | 0-50000 | Fighter jet |
| `RMAF_TRANSPORT` | RMAF | 150-300 | 0-30000 | C-130, CN-235, MPA |
| `RMAF_HELICOPTER` | RMAF | 0-150 | 0-10000 | EC725, Blackhawk |
| `RMP_HELICOPTER` | RMP | 0-140 | 0-8000 | Police helicopter |

### Ground Vehicles
| Type | Agency | Speed (km/h) | Description |
|------|--------|--------------|-------------|
| `RMP_PATROL_CAR` | RMP | 0-140 | Police patrol vehicle |
| `RMP_TACTICAL` | RMP | 0-100 | Tactical/armored vehicle |
| `CI_CHECKPOINT_VEHICLE` | CI | 0-120 | Customs vehicle |
| `CI_MOBILE_UNIT` | CI | 0-120 | Immigration mobile unit |
| `MIL_APC` | MIL | 0-80 | Armored personnel carrier |
| `MIL_TRANSPORT` | MIL | 0-90 | Military transport truck |
| `MIL_COMMAND` | MIL | 0-100 | Mobile command vehicle |

### Personnel
| Type | Agency | Speed (km/h) | Description |
|------|--------|--------------|-------------|
| `RMP_OFFICER` | RMP | 0-6 | Police officer |
| `RMP_TACTICAL_TEAM` | RMP | 0-6 | GOF/UTK tactical team |
| `CI_OFFICER` | CI | 0-5 | Customs/Immigration officer |
| `CI_IMMIGRATION_TEAM` | CI | 0-5 | Immigration team |
| `MIL_INFANTRY_SQUAD` | MIL | 0-6 | Infantry squad |
| `MIL_SPECIAL_FORCES` | MIL | 0-8 | GGK/special forces |

---

## GeoJSON References

Scenarios reference areas and routes by their `zone_id` or `route_id` from 
GeoJSON files in `geodata/`.

**Areas** (polygons — for `area` and `patrol_area`):
- `esszone_sector_1_kudat`
- `esszone_sector_2_sandakan`
- `esszone_sector_3_lahad_datu`
- `esszone_sector_4_semporna`
- `esszone_sector_5_tawau`
- `semporna_islands`
- `sulu_illegal_fishing_grounds`
- `padang_besar_border`

**Routes** (linestrings — for `route`):
- `sulu_sea_transit_corridor`
- `sibutu_passage`
- `strait_tss_westbound`
- `strait_tss_eastbound`

**Bases** (points — for reference):
- All bases in `geodata/bases/security_bases.geojson` and 
  `geodata/esszone_sulu_sea.geojson`

---

## Tips for Realistic Scenarios

1. **Vary speeds realistically.** Cargo ships don't suddenly go 30 knots. 
   Fishing boats drift at 2-4 knots while nets are out. Speedboats can 
   do 30+ knots. Navy interceptors max at 35 knots.

2. **Time distances correctly.** At 30 knots, a vessel covers ~56 km/hour.
   Semporna to Sandakan is ~200km by sea = ~3.5 hours at 30 kts. Don't 
   have a vessel travel that in 10 minutes.

3. **Layer the response.** Real multi-agency operations have delays:
   - Detection → alert: 1-3 minutes
   - Alert → first order: 2-5 minutes  
   - Standby unit → underway: 5-15 minutes
   - Transit to scene: depends on distance
   - Nearest unit always responds first

4. **Background traffic matters.** 12-20 fishing boats, 3-5 cargo ships, 
   and 2-3 aircraft make the simulation look alive. Without them, the 
   scenario feels empty.

5. **AIS behavior.** Civilian vessels have AIS on. Suspect vessels may 
   have AIS off (`ais_active: false`) — this is a key detection trigger. 
   Military vessels may or may not broadcast AIS depending on operations.

6. **Use real geography.** Check that waypoints are actually in the sea 
   (not on land) and that routes don't cross through islands.

---

## Validation

Run the validator before testing:
```bash
python scripts/validate_scenario.py config/scenarios/your_scenario.yaml
```

This checks:
- All entity types are valid
- All referenced zones/routes exist in geodata
- Event times are in chronological order
- Entity IDs referenced in events exist in scenario_entities
- Waypoint coordinates are in valid ranges
- Speeds are within entity type limits
- No duplicate entity IDs
