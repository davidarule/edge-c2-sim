# Scenario YAML Schema Reference

**Applies to:** active scenarios under `config/scenarios/*.yaml` (not `v1_archive/`).

This document describes the schema **as the code actually interprets it**. Where an
enumerated value silently no-ops, or behaves differently from its name, that is
called out as **⚠ quirk**. Those are not bugs being documented for future work —
they are the current behaviour.

The authoritative loader is [`simulator/scenario/loader.py`](../simulator/scenario/loader.py);
the action dispatcher is [`simulator/scenario/event_engine.py`](../simulator/scenario/event_engine.py).

---

## Top-level structure

```yaml
scenario:
  name:              str      # human-readable name
  description:       str      # long description, may be multi-line
  duration_minutes:  int      # when the simulator auto-stops
  center:            {lat, lon}   # initial camera centre
  zoom:              int      # initial camera altitude (see COP main.js)
  background:                 # optional — include background traffic files
    include:
      - ais_background_malacca.yaml
  scenario_entities: [ ... ]  # see "Entity" section
  events:            [ ... ]  # see "Event" section
  background_entities: [ ... ] # (legacy v1) — not used in active scenarios
```

## Entity

Each entry under `scenario_entities`:

```yaml
- id:                str       # unique ID — referenced by events
  type:              str       # see "Entity types" below
  callsign:          str       # optional; defaults to id
  agency:            str       # see "Agency enum"; optional, derived from type
  sidc:              str       # optional; overrides the type's default SIDC
  embarked_on:       str       # optional; entity hidden until a `disembark` event
  spawn_at:          "HH:MM"   # optional; entity hidden until this offset
  behavior:          str       # see "Behavior enum"
  initial_position:
    lat:             float
    lon:             float
    alt_m:           float     # optional, default 0
    speed_kn:        float     # initial speed; see "drift movement" note below
    heading_deg:     float     # initial heading (also used as drift bearing)
  waypoints:                   # optional; if present, entity runs WaypointMovement
    - { lat, lon, alt_m, speed, time: "HH:MM", metadata: {...} }
  patrol_area:       str       # zone_id from geodata — used with behavior: patrol
  metadata:          {}        # arbitrary key/value; some keys are domain-specific
```

### Entity types

See `ENTITY_TYPES` in `loader.py` for the canonical list and speed/turn parameters.
Current set (35 entries): `SUSPECT_VESSEL`, `SUSPECT_FAST_BOAT`, `CIVILIAN_FISHING`,
`CIVILIAN_CARGO`, `CIVILIAN_TANKER`, `CIVILIAN_TANKER_VLCC`, `CIVILIAN_LIGHT`,
`CIVILIAN_COMMERCIAL`, `MMEA_PATROL`, `MMEA_FAST_INTERCEPT`, `MIL_NAVAL`,
`MIL_NAVAL_FRIGATE`, `MIL_NAVAL_FIC`, `MIL_SUBMARINE`, `MIL_SUBMARINE_FRIENDLY`,
`RMAF_TRANSPORT`, `RMAF_MPA`, `RMAF_HELICOPTER`, `RMAF_FIGHTER`, `RMP_PATROL_CAR`,
`RMP_PATROL_BOAT`, `RMP_MARINE_PATROL`, `RMP_OFFICER`, `CI_OFFICER`,
`CI_IMMIGRATION_TEAM`, `MIL_VEHICLE`, `MIL_APC`, `MIL_INFANTRY`, `HOSTILE_VESSEL`,
`HOSTILE_PERSONNEL`, `CIVILIAN_TOURIST`, `CIVILIAN_BOAT`, `CIVILIAN_PASSENGER`,
`RMP_TACTICAL_TEAM`, `MIL_INFANTRY_SQUAD`.

### Behavior enum

| Value        | Actual behaviour |
|--------------|------------------|
| `standby`    | Status starts as `IDLE`. No movement is assigned — **unless** `initial_position.speed_kn > 0` (see drift movement below), in which case `EscapeMovement` still runs. |
| `waypoint`   | Default. If `waypoints:` is set, runs `WaypointMovement`; otherwise entity is static (again, drift movement may apply). |
| `patrol`     | Runs `PatrolMovement` within `patrol_area` polygon. Requires a valid `patrol_area` zone_id or the entity gets no movement. |

### Drift movement (all behaviors)

If an entity has `initial_position.speed_kn > 0` and no waypoints are set and it
is not `embarked_on` a carrier, the loader assigns an `EscapeMovement` that
dead-reckons from `initial_position` along `heading_deg`. This is used as a
cheap "entity is moving at cruise" fallback, not a true drift model.

---

## Event

Each entry under `events`:

```yaml
- id:                 str              # optional; required if other events depend on this one
  time:               "HH:MM[:SS]"     # optional; absolute offset from scenario start
  after:                               # optional; dependency trigger
    event:            str              #   id of the event this depends on
    phase:            initiate|complete
    offset:           "HH:MM:SS"       # optional extra delay once dep is satisfied
  type:               str              # see "event_type enum"
  description:        str              # short label (also used as fallback for on_initiate)
  severity:           INFO|WARNING|CRITICAL
  on_initiate:        str              # long message shown when event fires
  on_complete:        str              # long message shown when action finishes (arrival/intercept)
  actionee:           str              # entity performing / experiencing this event
  targets:            [str, ...]       # multiple entities (if more than one actionee)
  target:             str              # object of the action (intercept/approach/etc.)
  action:             str              # see "Action enum" — dispatches movement change
  on_complete_action: str              # action to fire when the movement completes
  destination:        {lat, lon}       # used by: transit, approach (when no approach_target)
  area:               str              # zone_id; used by legacy search_area / patrol
  position:           {lat, lon}       # purely informational (COP timeline fly-to)
  source:             str              # informational "who said this" — used by REST/HTTP forward
  alert_agencies:     [str, ...]       # which agencies receive the alert (names from Agency enum)
  # — everything else under the event maps into metadata{} —
  # common metadata keys:
  orbit_center:       str              # entity_id (dynamic tracking) used by action: orbit
  orbit_center_lat:   float            # if no orbit_center entity is given
  orbit_center_lon:   float
  orbit_radius_nm:    float
  orbit_speed:        float
  orbit_direction:    CW|CCW
  altitude_m:         float
  hold_target:        str              # used by action: hold_station
  bearing_deg:        float            # required by action: escape
  speed:              float            # default speed override
  duration_min:       float            # optional — action: escape
  approach_target:    str              # used by action: approach
  approach_distance_nm: float
  final_speed:        float
  sidc_override:      str              # 20-char SIDC applied to actionee/targets
  callsign_override:  str
  new_type:           str              # used by action: reclassify
  boarding_target:    str              # informational only — action: boarding is a no-op
  reclassify:                          # inline reclassify (bypasses action dispatch)
    targets: [str, ...]
    new_type: str
```

### event_type enum

Most values are **descriptive only** — they flow through to the COP timeline for
display/styling and to the REST/HTTP-forward adapters for routing. Only
`AIS_LOSS` triggers bespoke behaviour inside the simulator itself.

| Value       | Runtime effect |
|-------------|----------------|
| `ALERT`     | None (descriptive). |
| `ORDER`     | None (descriptive). |
| `DETECTION` | None (descriptive). |
| `DISTRESS`  | None (descriptive). |
| `INTERCEPT` | None (descriptive). Also generated by the engine when an `intercept` action completes. |
| `BOARDING`  | None (descriptive). See also `action: boarding` below — which is also almost a no-op. |
| `RESOLUTION`| None (descriptive). |
| `AIS_LOSS`  | Sets `actionee.metadata.ais_active = false`. |
| `ARRIVAL`   | Generated by the engine on movement completion when there's no `is_intercepted` method. Not valid in scenario files. |

### severity enum

`INFO`, `WARNING`, `CRITICAL`. Default `INFO`. Used only by the COP for styling
(timeline rows, event overlay) and HTTP-forward passthrough.

### after.phase enum

| Value      | Satisfied when |
|------------|----------------|
| `initiate` | The dependency event fires. |
| `complete` | The dependency event's `on_complete_action` movement signals completion (via `is_complete()` or `is_intercepted()`). |

### Action enum

Actions replace the actionee's movement strategy. Each action is dispatched in
`_fire_event` (primary path) and, when used as an `on_complete_action`, in
`_apply_complete_action`.

| Value              | Behaviour (from code) |
|--------------------|------------------------|
| `transit`          | Swaps to `TransitMovement` from current position → `destination`. Speed from `metadata.speed` or entity-type default. status=RESPONDING. Requires `destination`. |
| `orbit`            | Swaps to `OrbitMovement` around `orbit_center` entity (dynamic tracking) or fixed `orbit_center_lat/lon`. Radius from `orbit_radius_nm` (default 1.0nm). Speed from `orbit_speed`. Direction CW default. `initial_heading` computed from current bearing to centre so the entity stays where it is. status=ACTIVE. |
| `hold_station`     | Swaps to `HoldStationMovement` at current position. If `hold_target` is set, the entity rides alongside the target with a frozen initial offset. speed=0, status=ACTIVE. |
| `alongside`        | **Maritime only.** Equivalent to `hold_station` with a `hold_target` — `HoldStationMovement` locked to the target entity's position with the geographic offset at handoff preserved. `target` names the target; `hold_target` in metadata is an alternative. Use this when a vessel comes alongside another vessel (e.g. pirate skiff rafting up). For personnel transfer between vessels, use `disembark` with `onto:`. |
| `escape`           | Swaps to `EscapeMovement` dead-reckoning from current position along `bearing_deg` at `speed` (or entity max) for `duration_min` (or indefinitely). Requires `bearing_deg`. status=ACTIVE. |
| `approach`         | Swaps to `ApproachMovement`. Destination = `approach_target` entity position, or `destination`. Speed interpolates from `speed` → `final_speed` (default 2) over `approach_distance_nm` (default 1.0). status=RESPONDING. ⚠ On arrival the movement stops where it is (old code teleported to exact destination — fixed 2026-04-19). |
| `rtb`              | Swaps to `TransitMovement` back to `metadata.home_base{lat,lon}` or `entity.initial_position`. Speed = entity-type transit default. status=RTB. |
| `disembark`        | **Personnel only.** Teleports the actionee to the `embarked_on` carrier's position and sets heading to carrier's. If optional `onto:` metadata is set, teleports the actionee to *that* entity's position instead and assigns a `HoldStationMovement` with `hold_target: <onto>` so the actionee tracks the onto-entity. status=ACTIVE. |
| `intercept`        | Swaps to `InterceptMovement` toward `target` entity. Speed from `metadata.speed` or entity-type default. status=INTERCEPTING. Intercept radius resolution: (1) `intercept_radius_nm` metadata wins; (2) else, if `on_complete_action: orbit` with `orbit_radius_nm`, sync to that; (3) else 500 m default. Preserves an existing `WaypointMovement` with >2 waypoints instead of replacing it. Requires `target`. |
| `pursue`           | **Alias for `intercept`** — identical code path, kept for legacy scenarios. |
| `deploy`, `respond`| Same as `transit` but preserves an existing `WaypointMovement` with >2 waypoints. status=RESPONDING. |
| `lockdown`, `secure`| Sets status=ACTIVE, speed=0. Deletes any existing movement — entity freezes in place. |
| `activate`         | ⚠ **No-op.** Sets status=ACTIVE. |
| `escort_to_port`   | Swaps to `TransitMovement` to **Sandakan (5.84, 118.105)** at half max speed. ⚠ Destination is hard-coded — only meaningful for ESSZONE scenarios. |
| `reclassify`       | Changes `entity.entity_type` and `entity.sidc` to `metadata.new_type`'s values. Skips the normal upsert. |
| `search_area`, `patrol` | ⚠ **DEPRECATED + excluded from all domain whitelists.** Historically a near-no-op (only flipped status to ACTIVE). Use `behavior: patrol` at entity definition time for real patrol behaviour. The validator now rejects these as event actions. |
| `boarding`         | ⚠ **DEPRECATED + excluded from all domain whitelists.** Historically a no-op; would fail the new per-domain validator. Use `alongside` for vessels or `disembark onto: <target>` for personnel transfer. The action handler logs a warning and does nothing. |
| *(unknown)*        | Logs a debug message; sets status=ACTIVE. |

### Per-domain action whitelist

The validator rejects any event whose `action` or `on_complete_action` is not in the whitelist for the actionee entity's domain. Source: `DOMAIN_ACTIONS` in `simulator/scenario/loader.py`.

| Domain | Allowed actions |
|--------|-----------------|
| `MARITIME`       | transit, orbit, hold_station, escape, approach, alongside, intercept, pursue, deploy, respond, escort_to_port, reclassify, lockdown, secure, activate |
| `AIR`            | transit, orbit, hold_station, escape, approach, intercept, pursue, rtb, deploy, respond, reclassify, activate |
| `PERSONNEL`      | transit, embark, disembark, hold_station, approach, escape, reclassify, activate, lockdown, secure |
| `GROUND_VEHICLE` | transit, hold_station, escape, approach, rtb, deploy, respond, reclassify, activate |

### on_complete_action

Same valid values as `action`. Fires via `_apply_complete_action` when the
primary action's movement signals `is_complete()` (or `is_intercepted()` for
surface intercepts). Typical uses: `hold_station`, `orbit`.

### actionee / target / targets — which to use

| Field | Type | Meaning |
|-------|------|---------|
| `actionee` | str | **The entity performing or experiencing the event.** Use for single-entity events. |
| `targets`  | list[str] | Use when the event applies to more than one entity (they all receive the same action). |
| `target`   | str | **The object of the action** (e.g., the ship to intercept, the entity to approach). Only meaningful for actions that take a target (`intercept`, `pursue`, and those using `hold_target`/`approach_target` via metadata). |

The engine collects actionee IDs from `actionee` + `targets` when applying an
`action`. It uses `target` for the action's object.

---

## Agency enum

`RMP`, `MMEA`, `CI`, `RMAF`, `MIL`, `IDN`, `SGP`, `CIVILIAN`.

## Domain enum

`MARITIME`, `AIR`, `GROUND_VEHICLE`, `PERSONNEL`. Set by the entity type, not in
scenario files.

## EntityStatus enum (runtime only)

`ACTIVE`, `IDLE`, `RESPONDING`, `INTERCEPTING`, `RTB`. Set by the engine based
on actions; never authored in scenarios.

---

## Known behavioural gotchas to review

These are documented here because code behaviour matches them today. We have
not changed them; flag them for separate discussion if they need fixing:

1. **`boarding` action is DEPRECATED + no-op.** Retained in the enum for legacy
   compatibility but rejected by the per-domain validator. Use `alongside` for
   vessel-to-vessel rafting; use `disembark onto: <target>` for moving
   personnel onto a target entity.
2. **`search_area` / `patrol` actions are DEPRECATED + no-ops.** Rejected by
   the validator. The entity-level `behavior: patrol` (at entity definition
   time) runs `PatrolMovement` — that's the right way to get a patrol
   behaviour.
3. **`escort_to_port` destination is hard-coded to Sandakan (5.84 N, 118.105 E).**
   Inherited from the ESSZONE scenarios; unsuitable for Malacca operations.
4. **`disembark` produces no follow-on movement.** Disembarked entities are
   placed at the carrier's coordinates and then stop. Most scenarios follow up
   with a later `action: transit` or `action: approach` event to move them.
5. **Multiple `event_type` values are decorative only.** Only `AIS_LOSS`
   triggers engine-level behaviour; the rest are passed through to the COP and
   transport adapters for display/routing.
