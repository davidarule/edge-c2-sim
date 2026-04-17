# Edge C2 Scenario Specification v2.0

Formal specification for Edge C2 scenario YAML files. All scenario files MUST conform to this specification. A JSON Schema file (`config/scenario.schema.json`) provides machine-readable validation.

---

## 1. Document Structure

```yaml
scenario:                          # REQUIRED — root object
  name: string                     # REQUIRED — scenario identifier
  description: string              # REQUIRED — narrative overview
  duration_minutes: integer        # REQUIRED — scenario length
  center:                          # REQUIRED — map center
    lat: number                    #   latitude (-90 to 90)
    lon: number                    #   longitude (-180 to 180)
  zoom: integer                    # OPTIONAL — map zoom (1-18, default: 9)
  include_entities: [string]       # OPTIONAL — background entity files
  background_entities: [object]    # OPTIONAL — inline background entities
  scenario_entities: [Entity]      # REQUIRED — entity definitions
  events: [Event]                  # REQUIRED — timeline events
```

---

## 2. Entity Definition

### 2.1 Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `id` | string | YES | — | Unique entity identifier (e.g., `RMAF-HELI-001`) |
| `type` | EntityType | YES | — | Entity type (see 2.2) |
| `callsign` | string | NO | value of `id` | Display name |
| `agency` | Agency | NO | from type | Owning agency |
| `behavior` | Behavior | NO | `waypoint` | Initial movement behavior |
| `spawn_at` | TimeOffset | NO | — | Deferred spawn time (entity hidden until then) |
| `initial_position` | Position | YES | — | Starting location |
| `waypoints` | [Waypoint] | NO | — | Explicit movement path |
| `patrol_area` | string | NO | — | GeoJSON zone ID (for behavior: patrol) |
| `metadata` | object | NO | `{}` | Domain-specific data |

### 2.2 EntityType (enum)

**Maritime:**
`CIVILIAN_TANKER`, `CIVILIAN_TANKER_VLCC`, `CIVILIAN_CARGO`, `CIVILIAN_PASSENGER`, `CIVILIAN_FISHING`, `CIVILIAN_LIGHT_AIRCRAFT`, `SUSPECT_VESSEL`, `SUSPECT_FAST_BOAT`, `MMEA_PATROL`, `MMEA_FAST_INTERCEPT`, `RMP_PATROL_BOAT`, `MIL_NAVAL`, `MIL_NAVAL_FRIGATE`, `MIL_SUBMARINE`

**Air:**
`RMAF_HELICOPTER`, `RMAF_MPA`, `RMAF_FIGHTER`

**Ground:**
`RMP_PATROL_CAR`, `MIL_APC`

**Personnel:**
`RMP_TACTICAL_TEAM`, `MIL_INFANTRY`, `CI_OFFICER`

### 2.3 Agency (enum)

`RMP`, `MMEA`, `CI`, `RMAF`, `MIL`, `CIVILIAN`, `IDN`, `SGP`

### 2.4 Embarked Units

Units that are aboard a carrier (e.g., UTK team on a patrol vessel, infantry in an APC) use `embarked_on` instead of `spawn_at`:

```yaml
- id: RMP-UTK-001
  type: RMP_TACTICAL_TEAM
  callsign: UTK Team Alpha
  agency: RMP
  embarked_on: MMEA-PV-001        # Aboard KM Perantau
  initial_position:                # Position when deployed (or carrier position)
    lat: 3.416
    lon: 100.490
```

**Behavior:**
- Entity is hidden from the COP and not in the entity store while embarked
- Entity tracks the carrier's position (no independent movement)
- A `disembark` action event spawns the entity at the carrier's current position
- Only entity types with `can_embark: true` may use `embarked_on`
- Only entity types with `can_carry: true` may be referenced as carriers

```yaml
# Deploy the boarding team from KM Perantau
- time: "01:03"
  type: BOARDING
  description: UTK deploys via RHIB from KM Perantau.
  on_initiate: UTK Team Alpha RHIB alongside MT Labuan Palm.
  action: disembark
  target: RMP-UTK-001
  boarding_target: TANKER-001
  alert_agencies: [MMEA, MIL, RMP]
  severity: CRITICAL
```

### 2.5 Entity Type Constraints

Entity types are defined in `config/entity_types.json`. Each type specifies:

| Property | Type | Description |
|----------|------|-------------|
| `domain` | string | MARITIME, AIR, GROUND_VEHICLE, PERSONNEL |
| `surface` | string | `water`, `land`, `air`, or `any` — where the entity can be placed |
| `max_speed_kn` | number | Maximum speed in knots |
| `max_altitude_m` | number | Maximum altitude in metres (air entities only) |
| `action_speeds_kn` | object | Speed per action type (transit, patrol, intercept, etc.) |
| `action_altitudes_m` | object | Altitude per action type (air entities only) |
| `turn_params` | object | Turning circle: `loa_m`, `k_coef`, `c_coef` |
| `can_embark` | boolean | Can this entity be embarked on a carrier? |
| `can_carry` | boolean | Can this entity carry embarked units? |
| `carry_capacity` | integer | Max embarked personnel/teams |
| `default_sidc` | string | Default 20-char MIL-STD-2525D SIDC |

### 2.6 Action-Based Speeds and Altitudes

The simulator automatically selects speed and altitude based on the action being performed. Scenario authors do **not** need to specify speed or altitude unless overriding the default.

**Example: MMEA Patrol Vessel (max 28kn)**

| Action | Speed | Description |
|--------|-------|-------------|
| `patrol` | 12 kn | Routine surveillance |
| `transit` | 22 kn | Proceeding to location |
| `intercept` | 28 kn | Max speed pursuit |
| `approach` | 5 kn | Boarding approach |
| `escort` | 10 kn | Escorting detained vessel |
| `search` | 8 kn | Area search pattern |

**Example: RMAF Helicopter (max 140kn)**

| Action | Speed | Altitude | Description |
|--------|-------|----------|-------------|
| `transit` | 120 kn | 300m | Flying to scene |
| `patrol` | 60 kn | 300m | Area patrol |
| `orbit` | 40 kn | 150m | Overwatch orbit |
| `search` | 50 kn | 100m | Low-level search |
| `intercept` | 140 kn | 150m | Pursuit |

The `speed` and `altitude_m` fields on events override these defaults when specified.

**The validator checks:**
- Entity `initial_position` is on correct surface (water/land/any)
- Waypoint speeds do not exceed `max_speed_kn`
- `embarked_on` references a carrier with `can_carry: true`
- Embarked entity has `can_embark: true`

### 2.6 Behavior (DEPRECATED)

**Do not use in new scenarios.** Kept for backward compatibility only.

Entities without waypoints start stationary at `initial_position`. Entities with waypoints follow them. Use events with actions to drive all movement.

| Value | Legacy Effect |
|-------|--------------|
| `waypoint` | Follow explicit waypoints |
| `patrol` | Random patrol within `patrol_area` polygon |
| `standby` | No movement |

### 2.5 Position

```yaml
initial_position:
  lat: number                      # REQUIRED — latitude
  lon: number                      # REQUIRED — longitude
  alt_m: number                    # OPTIONAL — altitude in metres (default: 0)
```

### 2.6 Waypoint

```yaml
waypoints:
  - lat: number                    # REQUIRED
    lon: number                    # REQUIRED
    speed: number                  # OPTIONAL — speed in knots (default: 0)
    time: TimeOffset               # REQUIRED — scenario-relative time
    alt_m: number                  # OPTIONAL — altitude (default: 0)
    metadata: object               # OPTIONAL — property overrides (see 2.7)
```

### 2.7 Waypoint Metadata Overrides

Override entity-level properties at a specific waypoint:

| Key | Type | Effect |
|-----|------|--------|
| `sidc` | string (20 chars) | Change entity SIDC (identity/symbol) |
| `callsign` | string | Change display name |
| Any other key | any | Merged into `entity.metadata` |

### 2.8 TimeOffset Format

String in `HH:MM` or `HH:MM:SS` format, representing time from scenario start.

Examples: `"00:00"`, `"01:15"`, `"00:30:45"`

---

## 3. Event Definition

Events are the primary mechanism for driving the scenario. Each event has a **trigger** (when it fires), a **message** (what appears in the timeline), and optionally an **action** (what entities do).

### 3.1 Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `time` | TimeOffset | COND | — | When to fire (required if no `trigger`) |
| `trigger` | Trigger | COND | — | Condition-based firing (required if no `time`) |
| `type` | EventType | YES | — | Event category |
| `description` | string | YES | — | Author's intent — documents what this event represents (not displayed in timeline) |
| `on_initiate` | string | NO | — | Message shown in timeline when event fires |
| `on_complete` | string | NO | — | Message shown in timeline when action completes |
| `severity` | Severity | NO | `INFO` | Alert level |
| `target` | string | NO | — | Single entity ID to act on |
| `targets` | [string] | NO | — | Multiple entity IDs |
| `source` | string | NO | — | Originating entity ID (for inter-agency routing) |
| `alert_agencies` | [Agency] | NO | `[]` | Recipients of timeline messages |
| `action` | Action | NO | — | Movement command (see Section 4) |
| `on_complete_action` | Action | NO | — | What to do after action completes (see 3.4) |
| `position` | Position | NO | — | Event location (for click-to-fly) |
| Additional fields | varies | NO | — | Action-specific parameters (see Section 4) |

### 3.2 EventType (enum)

| Value | Purpose |
|-------|---------|
| `DETECTION` | Sensor contact, sighting, AIS track |
| `DISTRESS` | Emergency signal (SSAS, Mayday, EPIRB) |
| `ALERT` | Situation update, intelligence assessment |
| `ORDER` | Command to entity — usually has `action` |
| `AIS_LOSS` | Transponder disabled (marks entity dark) |
| `BOARDING` | Boarding operation begins |
| `INTERCEPT` | Auto-generated: intercept movement completed |
| `ARRIVAL` | Auto-generated: transit/deploy completed |
| `RESOLUTION` | Incident resolved, endstate |

### 3.3 Severity (enum)

| Value | COP Behavior |
|-------|-------------|
| `INFO` | Normal entry in timeline |
| `WARNING` | Yellow highlight, toast notification |
| `CRITICAL` | Red highlight, toast + timeline auto-expand |

### 3.4 On-Complete Action

When a movement action completes, the entity can automatically transition to a follow-on behavior:

| Value | Behavior |
|-------|----------|
| `hold_station` | Stay at current position (speed 0) — DEFAULT for surface entities |
| `orbit` | Circle at current position (uses `orbit_*` params if present) — DEFAULT for fixed-wing |
| `rtb` | Return to base |
| `barrier` | Back-and-forth patrol at current position |
| `escort` | Follow the intercept target at matching speed |

If `on_complete_action` is not specified:
- Fixed-wing aircraft (min_speed > 0): auto-orbit
- All others: hold station (speed 0)

---

## 4. Actions

Actions modify entity movement. They are set on events via the `action` field.

### 4.1 `transit`

Move to a destination at specified speed.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `destination` | Position | YES | — | Target location {lat, lon} |
| `speed` | number | NO | type max * 0.9 | Speed in knots |
| `altitude_m` | number | NO | current | For air entities |

**Completion:** Arrives at destination. Fires `on_complete` message.

```yaml
- time: "00:08"
  type: ORDER
  description: Scramble helicopter to tanker position for FLIR overwatch.
  on_initiate: >
    TUDM Caracal 1 scrambled from RMAF Subang. ETA ~27 minutes.
  on_complete: >
    TUDM Caracal 1 on scene. FLIR confirms tanker stationary,
    two fast boats alongside.
  target: RMAF-HELI-001
  action: transit
  destination: {lat: 3.416, lon: 100.490}
  speed: 150
  altitude_m: 150
  alert_agencies: [MMEA, MIL, RMP]
  on_complete_action: orbit
  orbit_radius_nm: 1.0
  orbit_speed: 40
```

### 4.2 `orbit`

Circular pattern around a point or entity.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `orbit_center` | string | NO | current pos | Entity ID to orbit around |
| `orbit_center_lat` | number | NO | current lat | Fixed orbit center |
| `orbit_center_lon` | number | NO | current lon | Fixed orbit center |
| `orbit_radius_nm` | number | NO | 1.0 | Radius in nautical miles |
| `orbit_speed` | number | NO | type min speed | Speed in knots |
| `orbit_direction` | `CW` or `CCW` | NO | `CW` | Orbit direction |
| `altitude_m` | number | NO | current | For air entities |

**Completion:** Never completes — orbits until replaced by next action.

```yaml
- time: "00:12"
  type: DETECTION
  description: Pirate lookout boat circling tanker as sentry.
  target: PIRATE-002
  action: orbit
  orbit_center: TANKER-001
  orbit_radius_nm: 0.18
  orbit_speed: 4
```

### 4.3 `hold_station`

Hold position (stationary or alongside target).

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `hold_target` | string | NO | — | Entity ID to track alongside |

**Completion:** Never completes — holds until replaced.

```yaml
# Static hold
- time: "00:15"
  type: ALERT
  description: Tanker dead in water after SSAS activation.
  on_initiate: MT Labuan Palm dead in water at 3.416N 100.490E.
  target: TANKER-001
  action: hold_station
  alert_agencies: [MMEA, MIL, RMP]
  severity: CRITICAL

# Hold alongside another entity
- time: "00:58"
  type: ORDER
  description: Patrol vessel stations alongside tanker for boarding support.
  on_initiate: KM Perantau alongside MT Labuan Palm.
  target: MMEA-PV-001
  action: hold_station
  hold_target: TANKER-001
```

### 4.4 `intercept`

Chase a moving target using lead pursuit.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `intercept_target` | string | YES | — | Entity ID to chase |

**Completion:** When within 500m of target. Fires `on_complete` message. Non-fixed-wing entities stop; fixed-wing entities orbit.

```yaml
- time: "01:06"
  type: ORDER
  description: KD Perak intercepts fleeing pirates before they reach Indonesian EEZ.
  on_initiate: KD Perak ordered to intercept fleeing fast boats.
  on_complete: >
    KD Perak alongside both fast boats. 11 perpetrators detained.
  target: RMN-OPV-001
  action: intercept
  intercept_target: PIRATE-001
  alert_agencies: [MMEA, MIL]
  on_complete_action: hold_station
```

### 4.5 `escape`

Flee on a constant bearing.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `bearing_deg` | number | YES | — | Escape heading (0-360) |
| `speed` | number | NO | type max | Speed in knots |
| `duration_min` | number | NO | — | Stop after N minutes |

**Completion:** When duration expires (if set), otherwise never.

```yaml
- time: "00:58"
  type: ALERT
  description: Pirate boat breaks away toward Indonesian waters.
  on_initiate: Fast Boat 1 fleeing heading 210 at 28kn.
  target: PIRATE-001
  action: escape
  bearing_deg: 210
  speed: 28
  alert_agencies: [MMEA, MIL, RMP]
  severity: CRITICAL
```

### 4.6 `approach`

Graduated deceleration toward a target or point.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `approach_target` | string | NO | — | Entity ID to approach |
| `destination` | Position | NO | — | Fixed point (if no approach_target) |
| `final_speed` | number | NO | 2 | Target speed in knots |
| `approach_distance_nm` | number | NO | 1.0 | Begin decelerating at this range |

**Completion:** Within ~100m at final speed. Fires `on_complete`.

```yaml
- time: "00:52"
  type: ORDER
  description: KM Perantau reduces speed for boarding approach.
  on_initiate: KM Perantau approaching tanker for boarding.
  on_complete: KM Perantau alongside MT Labuan Palm.
  target: MMEA-PV-001
  action: approach
  approach_target: TANKER-001
  final_speed: 2
  on_complete_action: hold_station
  hold_target: TANKER-001
```

### 4.7 `rtb`

Return to base.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| (none) | — | — | — | Uses `metadata.home_base` or `initial_position` |

**Completion:** Arrives at base. Entity transitions to standby.

```yaml
- time: "01:10"
  type: ORDER
  description: Helicopter returns to Subang after fuel state requires RTB.
  on_initiate: TUDM Caracal 1 RTB to RMAF Subang.
  target: RMAF-HELI-001
  action: rtb
```

---

## 5. Triggers (Condition-Based Events)

Events can fire based on conditions instead of fixed times. Use `trigger` instead of `time`.

### 5.1 Trigger Types

| Trigger | Fires When | Parameters |
|---------|-----------|------------|
| `arrival` | Entity reaches destination | `entity: string` |
| `intercept_complete` | InterceptMovement reaches target | `entity: string` |
| `proximity` | Two entities within range | `entity: string, target: string, range_nm: number` |
| `elapsed` | Duration since another event | `after_event: string, delay_min: number` |

### 5.2 Examples

```yaml
# Fire when helicopter arrives at tanker (instead of guessing T+37)
- trigger:
    type: arrival
    entity: RMAF-HELI-001
  type: ORDER
  description: Helicopter on scene, begin overwatch orbit.
  on_initiate: TUDM Caracal 1 commencing overwatch orbit.
  target: RMAF-HELI-001
  action: orbit
  orbit_center: TANKER-001
  orbit_radius_nm: 1.0
  orbit_speed: 40

# Fire when KD Perak gets within 1nm of pirates
- trigger:
    type: proximity
    entity: RMN-OPV-001
    target: PIRATE-001
    range_nm: 1.0
  type: DETECTION
  description: KD Perak visual contact with fleeing fast boats.
  on_initiate: >
    KD Perak: fast boats sighted bearing 030, speed 28kn.
    Closing to intercept.
  alert_agencies: [MMEA, MIL]

# Fire 5 minutes after boarding event
- trigger:
    type: elapsed
    after_event: boarding_start     # references event ID
    delay_min: 5
  type: ALERT
  description: Boarding team secures the bridge.
  on_initiate: UTK Team Alpha — BRIDGE SECURE.
  alert_agencies: [MMEA, MIL, RMP]
```

### 5.3 Event ID (for trigger references)

Events can have an optional `id` field for cross-referencing:

```yaml
- id: boarding_start
  time: "01:03"
  type: BOARDING
  description: UTK boards tanker via RHIB.
  on_initiate: UTK Team Alpha alongside MT Labuan Palm. Fast-rope ascent.
```

**Note:** Triggers are a future enhancement. For v2.0, `time` is the primary mechanism. `on_complete` on actions provides basic condition-based messaging.

---

## 6. Special Event Behaviors

### 6.1 AIS_LOSS

Marks an entity's transponder as dark. COP renders the entity greyed out.

```yaml
- time: "00:10"
  type: AIS_LOSS
  description: Suspect vessel disables AIS transponder.
  on_initiate: "AIS LOSS — MV Hai Long 7 transponder inactive."
  target: SUSPECT-001
  alert_agencies: [MMEA]
  severity: WARNING
```

### 6.2 SIDC/Identity Override via Event

Change an entity's symbol identity through an event:

```yaml
- time: "00:55"
  type: ALERT
  description: Pirates escalated to hostile after firing flares.
  on_initiate: Hostile intent confirmed — fast boats reclassified HOSTILE.
  targets: [PIRATE-001, PIRATE-002]
  sidc_override: "10063000001400000000"
  callsign_override: Hostile Boat
  alert_agencies: [MMEA, MIL, RMP]
  severity: CRITICAL
```

---

## 7. Metadata Fields

### 7.1 Common Metadata

| Key | Type | Used By | Purpose |
|-----|------|---------|---------|
| `home_base` | `{lat, lon}` | Air entities | RTB destination |
| `mmsi` | string | Maritime | AIS identification |
| `flag` | string | Maritime | Flag state |
| `vessel_type` | string | Maritime | Hull description |
| `aircraft_type` | string | Air | Aircraft model |
| `armed` | boolean | Any | Weapons capability |
| `estimated_crew` | integer | Any | Personnel count |

---

## 8. Background Entities

### 8.1 Include Files

Reference pre-built AIS traffic files:

```yaml
include_entities:
  - ais_background_malacca.yaml
  - ais_background_esszone.yaml
```

### 8.2 Available Background Files

| File | Coverage Area |
|------|--------------|
| `ais_background_malacca.yaml` | Strait of Malacca |
| `ais_background_south_malacca.yaml` | Southern Malacca approaches |
| `ais_background_esszone.yaml` | Eastern Sabah (ESSZONE) |
| `ais_background_singapore.yaml` | Singapore Strait |
| `ais_background_east_singapore.yaml` | East of Singapore |
| `ais_background_sg_west.yaml` | West of Singapore |
| `ais_background_all.yaml` | All regions combined |

---

## 9. Validation

### 9.1 Command-Line Validator

```bash
python3 scripts/validate_scenario.py config/scenarios/my_scenario.yaml
```

### 9.2 JSON Schema Validation

```bash
python3 -c "
import yaml, jsonschema, json
with open('config/scenario.schema.json') as f:
    schema = json.load(f)
with open('config/scenarios/my_scenario.yaml') as f:
    data = yaml.safe_load(f)
jsonschema.validate(data, schema)
print('VALID')
"
```

---

## Appendix A: Complete Field Reference

### Entity Fields (alphabetical)

| Field | Type | Req | Default | Section |
|-------|------|-----|---------|---------|
| `agency` | Agency | NO | from type | 2.1 |
| `behavior` | Behavior | NO | `waypoint` | 2.4 |
| `callsign` | string | NO | = id | 2.1 |
| `id` | string | YES | — | 2.1 |
| `initial_position` | Position | YES | — | 2.5 |
| `metadata` | object | NO | `{}` | 7.1 |
| `patrol_area` | string | NO | — | 2.1 |
| `spawn_at` | TimeOffset | NO | — | 2.1 |
| `type` | EntityType | YES | — | 2.2 |
| `waypoints` | [Waypoint] | NO | — | 2.6 |

### Event Fields (alphabetical)

| Field | Type | Req | Default | Section |
|-------|------|-----|---------|---------|
| `action` | Action | NO | — | 4 |
| `alert_agencies` | [Agency] | NO | `[]` | 3.1 |
| `approach_distance_nm` | number | NO | 1.0 | 4.6 |
| `approach_target` | string | NO | — | 4.6 |
| `bearing_deg` | number | NO | — | 4.5 |
| `description` | string | YES | — | 3.1 |
| `destination` | Position | NO | — | 4.1 |
| `duration_min` | number | NO | — | 4.5 |
| `final_speed` | number | NO | 2 | 4.6 |
| `hold_target` | string | NO | — | 4.3 |
| `id` | string | NO | — | 5.3 |
| `intercept_target` | string | NO | — | 4.4 |
| `on_complete` | string | NO | — | 3.1 |
| `on_complete_action` | Action | NO | — | 3.4 |
| `on_initiate` | string | NO | — | 3.1 |
| `orbit_center` | string | NO | — | 4.2 |
| `orbit_center_lat` | number | NO | — | 4.2 |
| `orbit_center_lon` | number | NO | — | 4.2 |
| `orbit_direction` | `CW`/`CCW` | NO | `CW` | 4.2 |
| `orbit_radius_nm` | number | NO | 1.0 | 4.2 |
| `orbit_speed` | number | NO | — | 4.2 |
| `position` | Position | NO | — | 3.1 |
| `severity` | Severity | NO | `INFO` | 3.3 |
| `sidc_override` | string | NO | — | 6.2 |
| `callsign_override` | string | NO | — | 6.2 |
| `source` | string | NO | — | 3.1 |
| `speed` | number | NO | — | 4.1 |
| `target` | string | NO | — | 3.1 |
| `targets` | [string] | NO | — | 3.1 |
| `time` | TimeOffset | COND | — | 3.1 |
| `trigger` | Trigger | COND | — | 5.1 |
| `type` | EventType | YES | — | 3.2 |
