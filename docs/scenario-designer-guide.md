# Scenario Designer Guide

A scenario YAML file defines **entities** (who's in the scenario), **events** (what happens), and **actions** (how entities move). The simulator handles the physics — you describe intent.

---

## File Structure

```yaml
scenario:
  name: "SCN-MAL-XX: Short Title"
  description: >
    Multi-paragraph description of the scenario.
  duration_minutes: 75
  center:
    lat: 3.41
    lon: 100.49
  zoom: 9

  include_entities:
    - ais_background_malacca.yaml    # Background AIS traffic

  background_entities: []            # Inline background entities (or empty)

  scenario_entities:
    # ... entity definitions ...

  events:
    # ... timeline events ...
```

---

## Entities

Each entity needs an ID, type, callsign, agency, and starting position.

### Minimal Entity (action-driven, no waypoints)

```yaml
- id: RMAF-HELI-001
  type: RMAF_HELICOPTER
  callsign: TUDM Caracal 1
  agency: RMAF
  behavior: standby
  initial_position:
    lat: 3.131
    lon: 101.549
  metadata:
    aircraft_type: Airbus H225M Caracal
    home_base: {lat: 3.131, lon: 101.549}
```

The entity starts at Subang and does nothing until an event gives it an action.

### Entity with Initial Waypoints

Use waypoints when you need precise physics (deceleration curves, SIDC identity changes at specific points).

```yaml
- id: TANKER-001
  type: CIVILIAN_TANKER
  callsign: MT Labuan Palm
  initial_position:
    lat: 3.392
    lon: 100.514
  waypoints:
    - lat: 3.392
      lon: 100.514
      speed: 14
      time: "00:00"
    - lat: 3.406
      lon: 100.501
      speed: 14
      time: "00:05"
    - lat: 3.412
      lon: 100.495
      speed: 8
      time: "00:08"
    - lat: 3.415
      lon: 100.491
      speed: 3
      time: "00:12"
    - lat: 3.416
      lon: 100.490
      speed: 0
      time: "00:15"
  metadata:
    mmsi: '533000777'
    flag: MYS
```

After the last waypoint, the entity holds position at speed 0.

### Entity with Deferred Spawn

```yaml
- id: RMP-UTK-001
  type: RMP_TACTICAL_TEAM
  callsign: UTK Team Alpha
  agency: RMP
  spawn_at: "01:03"              # Hidden until T+63 minutes
  initial_position:
    lat: 3.416
    lon: 100.490
```

The entity doesn't appear on the COP until `spawn_at` time.

### Waypoint Metadata Overrides

Change entity properties (SIDC, callsign) at specific waypoints:

```yaml
waypoints:
  - lat: 3.389
    lon: 100.491
    speed: 3
    time: "00:00"
    metadata:
      sidc: "10013000001400000000"     # Unknown identity
  - lat: 3.406
    lon: 100.501
    speed: 25
    time: "00:05"
    metadata:
      sidc: "10053000001400000000"     # Suspect identity
      callsign: Suspect Boat 1
  - lat: 3.416
    lon: 100.490
    speed: 0
    time: "00:55"
    metadata:
      sidc: "10063000001400000000"     # Hostile identity
      callsign: Hostile Boat 1
```

---

## Entity Types

| Type | Domain | Speed Range | Use For |
|------|--------|-------------|---------|
| `CIVILIAN_TANKER` | MARITIME | 8-14 kn | Cargo/oil tankers |
| `CIVILIAN_CARGO` | MARITIME | 8-16 kn | Container ships, bulk carriers |
| `CIVILIAN_FISHING` | MARITIME | 2-8 kn | Fishing vessels |
| `SUSPECT_VESSEL` | MARITIME | 0-35 kn | Unidentified/suspect ships |
| `SUSPECT_FAST_BOAT` | MARITIME | 0-45 kn | Pirate skiffs, smuggling boats |
| `MMEA_PATROL` | MARITIME | 8-28 kn | MMEA patrol vessels |
| `MMEA_FAST_INTERCEPT` | MARITIME | 15-50 kn | MMEA fast intercept craft |
| `MIL_NAVAL` | MARITIME | 10-35 kn | Navy corvettes/OPVs |
| `MIL_NAVAL_FRIGATE` | MARITIME | 15-30 kn | Navy frigates |
| `MIL_SUBMARINE` | MARITIME | 0-20 kn | Submarines |
| `RMAF_HELICOPTER` | AIR | 0-140 kn | EC725, AW139 |
| `RMAF_MPA` | AIR | 120-280 kn | Maritime patrol aircraft |
| `RMP_TACTICAL_TEAM` | PERSONNEL | 0-25 kn | Police tactical teams (RHIB capable) |
| `RMP_PATROL_CAR` | GROUND | 20-80 kn | Police vehicles |
| `MIL_INFANTRY` | PERSONNEL | 0-4 kn | Ground troops |

---

## Events

Events are the heart of the scenario. Each event has a **time**, **type**, **description**, and optionally an **action** that changes entity behavior.

### Event Types

| Type | Purpose | Example |
|------|---------|---------|
| `DETECTION` | Sensor contact or sighting | "AIS contact detected" |
| `DISTRESS` | Emergency signal received | "SSAS alert activated" |
| `ALERT` | Situation update or warning | "Tanker dead in water" |
| `ORDER` | Command to an entity | "KM Perantau proceed to intercept" |
| `AIS_LOSS` | Transponder goes dark | "MV Hai Long 7 AIS lost" |
| `BOARDING` | Boarding operation begins | "UTK alongside, fast-rope ascent" |
| `INTERCEPT` | Entity reaches intercept target | "KD Perak alongside suspect" |
| `ARRIVAL` | Entity arrives at destination | Auto-generated on transit completion |
| `RESOLUTION` | Incident resolved | "Bridge secure, crew safe" |

### Event Fields

```yaml
- time: "00:08"                    # When event fires (HH:MM or HH:MM:SS)
  type: ORDER                      # Event type (see table above)
  description: >                   # Start message — shown in timeline
    MMEA requests RMAF helicopter support. TUDM Caracal 1
    scrambled from Subang.
  target: RMAF-HELI-001            # Entity affected (single)
  # targets: [ENTITY-1, ENTITY-2] # Or multiple entities
  action: transit                   # Movement action (see Actions below)
  destination: {lat: 3.416, lon: 100.490}  # For transit/deploy
  speed: 150                       # Override speed (knots)
  altitude_m: 150                  # For air entities
  alert_agencies: [MMEA, MIL, RMP] # Who receives this message
  severity: INFO                   # INFO, WARNING, or CRITICAL
  source: MMEA-PV-001              # Originating entity (for inter-agency routing)
  on_complete: >                   # Completion message — shown when action finishes
    TUDM Caracal 1 on scene. FLIR confirms two fast boats
    alongside stationary tanker.
```

### Pure Informational Event (no action)

```yaml
- time: "00:15"
  type: ALERT
  description: >
    SSAS secondary pulse. MT Labuan Palm stationary at 3.416N 100.490E.
    Dead in water. Hostage situation assessed HIGH RISK.
  alert_agencies: [MMEA, MIL, RMP]
  severity: CRITICAL
```

No `action` field — this is a timeline message only. No entity behavior changes.

---

## Actions

Actions tell entities how to move. They are triggered by events.

### `transit` — Go to a point

```yaml
- time: "00:08"
  type: ORDER
  action: transit
  target: RMAF-HELI-001
  destination: {lat: 3.416, lon: 100.490}
  speed: 150                       # Knots (default: entity type max * 0.9)
  altitude_m: 150                  # For air entities
  description: Helicopter scrambled to incident.
  on_complete: Helicopter on scene.
  alert_agencies: [MMEA, MIL]
```

Entity moves in a straight line to destination. ETA is auto-calculated. On arrival, fixed-wing aircraft auto-orbit; others hold position.

### `orbit` — Circle around a point or entity

```yaml
- time: "00:37"
  type: ORDER
  action: orbit
  target: RMAF-HELI-001
  orbit_center: TANKER-001        # Orbit around this entity (tracks if it moves)
  # OR: orbit_center_lat/orbit_center_lon for fixed point
  orbit_radius_nm: 1.0            # Radius in nautical miles
  orbit_speed: 40                  # Knots
  orbit_direction: CW              # CW or CCW (default: CW)
  altitude_m: 150
  description: Helicopter begins overwatch orbit.
```

Entity circles indefinitely until the next event gives it a new action.

### `hold_station` — Stay in place

```yaml
- time: "00:15"
  type: ALERT
  action: hold_station
  target: TANKER-001
  description: Tanker dead in water.
```

Entity stays at its current position (speed 0). Holds indefinitely until next action.

**Hold alongside another entity:**

```yaml
- time: "00:58"
  type: ORDER
  action: hold_station
  target: MMEA-PV-001
  hold_target: TANKER-001         # Track this entity's position
  description: KM Perantau holding station alongside tanker.
```

### `escape` — Flee on a bearing

```yaml
- time: "00:58"
  type: ALERT
  action: escape
  target: PIRATE-001
  bearing_deg: 210                 # Heading (degrees true)
  speed: 28                        # Knots
  duration_min: 15                 # Optional: stop after 15 minutes
  description: Fast Boat 1 fleeing SSW toward Indonesia.
  alert_agencies: [MMEA, MIL, RMP]
  severity: CRITICAL
```

Entity dead-reckons on the bearing at speed. If `duration_min` is set, stops after that time.

### `intercept` — Chase a moving target

```yaml
- time: "01:06"
  type: ORDER
  action: intercept
  target: RMN-OPV-001
  intercept_target: PIRATE-001    # Chase this entity
  description: KD Perak ordered to intercept fleeing fast boats.
  on_complete: >
    KD Perak alongside both fast boats. 11 perpetrators detained.
  alert_agencies: [MMEA, MIL]
```

Uses lead pursuit — aims ahead of the target based on speed and heading. Non-fixed-wing entities stop when they reach the target. Fixed-wing entities orbit around the target.

### `pursue` — Same as intercept

```yaml
action: pursue                     # Alias for intercept
```

### `approach` — Slow down toward a target

```yaml
- time: "00:52"
  type: ORDER
  action: approach
  target: MMEA-PV-001
  approach_target: TANKER-001     # Approach this entity
  final_speed: 2                   # Decelerate to 2 knots
  approach_distance_nm: 1.5        # Begin slowing at 1.5nm out
  description: KM Perantau approaching tanker for boarding.
  on_complete: KM Perantau alongside MT Labuan Palm.
```

Graduated deceleration — mimics realistic approach to boarding.

### `rtb` — Return to base

```yaml
- time: "01:10"
  type: ORDER
  action: rtb
  target: RMAF-HELI-001
  description: Helicopter RTB to Subang.
```

Transits to entity's `home_base` (from metadata) or `initial_position`. Uses cruise speed.

### `deploy` / `respond` — Legacy transit actions

```yaml
action: deploy                     # Same as transit, sets status RESPONDING
action: respond                    # Same as deploy
```

These still work for backward compatibility. Prefer `transit` for new scenarios.

---

## Completion Messages (`on_complete`)

When an event has `on_complete`, the simulator tracks the entity's movement and generates a timeline message when it arrives or intercepts its target.

```yaml
- time: "00:12"
  type: ORDER
  action: transit
  target: RMN-OPV-001
  destination: {lat: 3.350, lon: 100.450}
  speed: 22
  description: >
    KD Perak ordered to blocking position 3.35N 100.45E.
  on_complete: >
    KD Perak in blocking position. SW escape routes covered.
  alert_agencies: [MMEA, MIL]
```

**Timeline result:**
- T+12:00 `[MIL]` KD Perak ordered to blocking position...
- T+49:12 `[MIL]` KD Perak in blocking position. SW escape routes covered.

The completion time (T+49:12) is calculated by the simulator from distance and speed — the scenario author doesn't need to know it.

**Rules:**
- Completion inherits `alert_agencies` and `severity` from the parent event
- Completion position is the entity's actual position at arrival (click-to-fly works)
- Only one completion fires per event, even if multiple targets

---

## SIDC Identity Codes

MIL-STD-2525D 20-character numeric SIDC. Position 4 (index 3) is identity:

| Code | Identity | Symbol Shape |
|------|----------|-------------|
| `1` | Unknown | Yellow diamond |
| `3` | Friend | Blue rectangle |
| `4` | Neutral | Green square |
| `5` | Suspect | Yellow diamond |
| `6` | Hostile | Red diamond |

To change identity mid-scenario, use waypoint metadata overrides (see above) or `reclassify` events.

---

## Behaviors

Set on entities to define initial movement before any events fire:

| Behavior | Effect |
|----------|--------|
| `waypoint` (default) | Follow explicit waypoints |
| `patrol` | Random patrol within `patrol_area` polygon |
| `standby` | No movement, entity waits for action event |

---

## Tips for Scenario Authors

1. **Use actions for movement, waypoints for physics.** If you need a precise deceleration curve (tanker slowing after SSAS), use waypoints. If you just need "go there," use `action: transit`.

2. **Let completion messages tell the story.** Write the `description` as the order, write `on_complete` as the result. The simulator fills in the timing.

3. **Identity escalation via waypoints.** For contacts that change from Unknown → Suspect → Hostile, put SIDC overrides on waypoints at the moments of escalation.

4. **`spawn_at` for embarked units.** If a unit is conceptually aboard another vessel (UTK on KM Perantau), use `spawn_at` to make it appear only when it deploys.

5. **Don't over-specify.** A helicopter doesn't need 32 waypoints. `transit` → `orbit` → `pursue` → `rtb` is 4 events.

6. **Background traffic.** Use `include_entities` to add AIS replay traffic. Available files:
   - `ais_background_malacca.yaml` — Strait of Malacca
   - `ais_background_esszone.yaml` — Eastern Sabah
   - `ais_background_singapore.yaml` — Singapore Strait

---

## Complete Example: SCN-MAL-02A

```yaml
scenario:
  name: "SCN-MAL-02A: Tanker Armed Robbery — Action-Driven"
  description: >
    Same scenario as SCN-MAL-02 but using action-driven movement
    instead of explicit waypoints. 78% fewer waypoints.
  duration_minutes: 75
  center:
    lat: 3.41
    lon: 100.49
  zoom: 9
  include_entities:
    - ais_background_malacca.yaml
  background_entities: []

  scenario_entities:

    # Tanker — waypoints for deceleration physics
    - id: TANKER-001
      type: CIVILIAN_TANKER
      callsign: MT Labuan Palm
      initial_position: {lat: 3.392, lon: 100.514}
      waypoints:
        - {lat: 3.392, lon: 100.514, speed: 14, time: "00:00"}
        - {lat: 3.406, lon: 100.501, speed: 14, time: "00:05"}
        - {lat: 3.412, lon: 100.495, speed: 8,  time: "00:08"}
        - {lat: 3.415, lon: 100.491, speed: 3,  time: "00:12"}
        - {lat: 3.416, lon: 100.490, speed: 0,  time: "00:15"}

    # Pirate 1 — waypoints for sprint + SIDC changes
    - id: PIRATE-001
      type: SUSPECT_VESSEL
      callsign: Unknown Boat 1
      initial_position: {lat: 3.389, lon: 100.491}
      waypoints:
        - {lat: 3.389, lon: 100.491, speed: 3, time: "00:00",
           metadata: {sidc: "10013000001400000000"}}
        - {lat: 3.390, lon: 100.492, speed: 25, time: "00:02"}
        - {lat: 3.406, lon: 100.501, speed: 25, time: "00:05",
           metadata: {sidc: "10053000001400000000", callsign: "Suspect Boat 1"}}
        - {lat: 3.412, lon: 100.495, speed: 8,  time: "00:08"}
        - {lat: 3.415, lon: 100.491, speed: 3,  time: "00:12"}
        - {lat: 3.416, lon: 100.490, speed: 0,  time: "00:15"}

    # Pirate 2 — waypoints for sprint + SIDC, orbit via action
    - id: PIRATE-002
      type: SUSPECT_VESSEL
      callsign: Unknown Boat 2
      initial_position: {lat: 3.392, lon: 100.484}
      waypoints:
        - {lat: 3.392, lon: 100.484, speed: 3, time: "00:00",
           metadata: {sidc: "10013000001400000000"}}
        - {lat: 3.393, lon: 100.485, speed: 25, time: "00:02"}
        - {lat: 3.408, lon: 100.498, speed: 25, time: "00:06",
           metadata: {sidc: "10053000001400000000", callsign: "Suspect Boat 2"}}
        - {lat: 3.416, lon: 100.493, speed: 4,  time: "00:12"}

    # KM Perantau — initial patrol waypoints only
    - id: MMEA-PV-001
      type: MMEA_PATROL
      callsign: KM Perantau
      agency: MMEA
      initial_position: {lat: 3.200, lon: 100.700}
      waypoints:
        - {lat: 3.200, lon: 100.700, speed: 12, time: "00:00"}
        - {lat: 3.210, lon: 100.690, speed: 12, time: "00:05"}
        - {lat: 3.220, lon: 100.680, speed: 12, time: "00:10"}

    # UTK — spawns at boarding time, no waypoints
    - id: RMP-UTK-001
      type: RMP_TACTICAL_TEAM
      callsign: UTK Team Alpha
      agency: RMP
      spawn_at: "01:03"
      initial_position: {lat: 3.416, lon: 100.490}

    # KD Perak — initial patrol waypoints only
    - id: RMN-OPV-001
      type: MIL_NAVAL
      callsign: KD Perak
      agency: MIL
      initial_position: {lat: 3.120, lon: 100.550}
      waypoints:
        - {lat: 3.120, lon: 100.550, speed: 10, time: "00:00"}
        - {lat: 3.130, lon: 100.540, speed: 10, time: "00:06"}
        - {lat: 3.140, lon: 100.530, speed: 10, time: "00:12"}

    # Helicopter — standby at base, fully action-driven
    - id: RMAF-HELI-001
      type: RMAF_HELICOPTER
      callsign: TUDM Caracal 1
      agency: RMAF
      behavior: standby
      initial_position: {lat: 3.131, lon: 101.549}
      metadata:
        aircraft_type: Airbus H225M Caracal
        home_base: {lat: 3.131, lon: 101.549}

  events:

    # === PHASE 1: DETECTION & ALERT ===

    - time: "00:00"
      type: DETECTION
      description: >
        MRCC Lumut: MT Labuan Palm tracking normally on AIS.
        14 knots, heading 315 NW through southern Strait of Malacca.
      alert_agencies: [MMEA]
      severity: INFO

    - time: "00:05"
      type: DISTRESS
      description: >
        SSAS COVERT ALERT — MT Labuan Palm. Ship Security Alert System
        activated. Two fast boats approaching from Indonesian side.
      target: TANKER-001
      alert_agencies: [MMEA, MIL, RMP]
      severity: CRITICAL

    - time: "00:07"
      type: ALERT
      description: >
        MMEA ARAS response protocol activated. Radio silence imposed.
      alert_agencies: [MMEA, MIL, RMP]

    # === PHASE 2: RESPONSE ORDERS ===

    - time: "00:08"
      type: ORDER
      description: >
        TUDM Caracal 1 scrambled from RMAF Subang. FLIR priority.
        ETA on scene ~27 minutes.
      target: RMAF-HELI-001
      action: transit
      destination: {lat: 3.416, lon: 100.490}
      speed: 150
      altitude_m: 150
      alert_agencies: [MMEA, MIL, RMP]
      on_complete: >
        TUDM Caracal 1 on scene. FLIR confirms MT Labuan Palm
        stationary. Two fast boats — one alongside, one circling.

    - time: "00:10"
      type: ORDER
      description: >
        KM Perantau ordered to proceed at best speed. RMP UTK
        Team Alpha (12 operators) embarked — boarding team activated.
      target: MMEA-PV-001
      action: transit
      destination: {lat: 3.416, lon: 100.490}
      speed: 22
      alert_agencies: [MMEA, MIL, RMP]
      on_complete: >
        KM Perantau approaching tanker. UTK preparing RHIB.

    - time: "00:12"
      type: ORDER
      description: >
        KD Perak ordered to blocking position 3.35N 100.45E.
        Cut off pirate escape toward Indonesian EEZ.
      target: RMN-OPV-001
      action: transit
      destination: {lat: 3.350, lon: 100.450}
      speed: 22
      alert_agencies: [MMEA, MIL]
      on_complete: >
        KD Perak in blocking position. All SW escape routes covered.

    # Pirate 2 begins lookout orbit
    - time: "00:12"
      type: DETECTION
      action: orbit
      target: PIRATE-002
      orbit_center: TANKER-001
      orbit_radius_nm: 0.18
      orbit_speed: 4

    # Tanker dead in water
    - time: "00:15"
      type: ALERT
      action: hold_station
      target: TANKER-001
      description: >
        MT Labuan Palm dead in water at 3.416N 100.490E.
        Hostage situation assessed HIGH RISK.
      alert_agencies: [MMEA, MIL, RMP]
      severity: CRITICAL

    # Pirate 1 holds alongside
    - time: "00:15"
      type: DETECTION
      action: hold_station
      target: PIRATE-001
      hold_target: TANKER-001

    # === PHASE 3: ON SCENE ===

    # Helicopter arrives (auto via on_complete above), starts orbit
    - time: "00:37"
      type: ORDER
      action: orbit
      target: RMAF-HELI-001
      orbit_center: TANKER-001
      orbit_radius_nm: 1.0
      orbit_speed: 40
      altitude_m: 150

    - time: "00:50"
      type: ALERT
      description: >
        Helicopter illuminates tanker. Loudhailer: "This is MMEA.
        You are surrounded. Release the crew."
      alert_agencies: [MMEA, MIL, RMP]
      severity: WARNING

    # === PHASE 4: ESCALATION ===

    - time: "00:55"
      type: ALERT
      description: >
        Pirates fire flares — no weapons discharge. KD Perak in
        blocking position. KM Perantau 3 minutes out.
      alert_agencies: [MMEA, MIL, RMP]
      severity: WARNING

    # Pirate escape
    - time: "00:56"
      type: ALERT
      action: escape
      target: PIRATE-002
      bearing_deg: 215
      speed: 28
      description: Fast Boat 2 breaking away heading 215 at 28kn.
      alert_agencies: [MMEA, MIL, RMP]
      severity: CRITICAL
      # SIDC escalation to hostile
      sidc_override: "10063000001400000000"
      callsign_override: Hostile Boat 2

    - time: "00:58"
      type: ALERT
      action: escape
      target: PIRATE-001
      bearing_deg: 210
      speed: 28
      description: Fast Boat 1 breaking away heading 210 at 28kn.
      alert_agencies: [MMEA, MIL, RMP]
      severity: CRITICAL
      sidc_override: "10063000001400000000"
      callsign_override: Hostile Boat 1

    # Helicopter pursues
    - time: "00:59"
      type: ORDER
      action: pursue
      target: RMAF-HELI-001
      intercept_target: PIRATE-001
      description: TUDM Caracal 1 in pursuit of fleeing fast boats.
      alert_agencies: [MMEA, MIL]

    # === PHASE 5: BOARDING & RESOLUTION ===

    - time: "01:03"
      type: BOARDING
      action: hold_station
      target: RMP-UTK-001
      hold_target: TANKER-001
      description: >
        UTK Team Alpha RHIB alongside MT Labuan Palm. Fast-rope
        ascent — two teams, port and starboard.
      alert_agencies: [MMEA, MIL, RMP]
      severity: CRITICAL

    - time: "01:05"
      type: ALERT
      description: >
        UTK Team Alpha: BRIDGE SECURE. 4 perpetrators detained.
        Master and officers released. Crew of 28 safe.
      alert_agencies: [MMEA, MIL, RMP]

    - time: "01:06"
      type: ORDER
      action: intercept
      target: RMN-OPV-001
      intercept_target: PIRATE-001
      description: KD Perak ordered to intercept fleeing fast boats.
      on_complete: >
        KD Perak alongside both fast boats. 11 perpetrators
        detained. All weapons secured.
      alert_agencies: [MMEA, MIL]

    - time: "01:15"
      type: ALERT
      description: >
        ENDSTATE — 15 perpetrators in custody. Crew of 28 safe.
        Vessel proceeding to Port Klang under escort.
      alert_agencies: [MMEA, MIL, RMP]
```

---

## Checklist Before Submitting a Scenario

- [ ] All entity IDs are unique
- [ ] All entity types exist in the entity type table
- [ ] Events are in chronological order
- [ ] Every event `target` references an existing entity ID
- [ ] Every `intercept_target` references an existing entity ID
- [ ] `include_entities` files exist in `config/scenarios/`
- [ ] `spawn_at` entities have appropriate initial positions
- [ ] Run `python3 scripts/validate_scenario.py <path>` — should show PASS
