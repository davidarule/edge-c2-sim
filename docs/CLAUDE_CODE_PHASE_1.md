# Claude Code — Phase 1 Task Brief: Movement Engine

## Context

Phase 0 gave us the foundation: entity model, simulation clock, entity store, 
WebSocket adapter, and console adapter. Phase 1 builds the movement engine — 
the core logic that makes entities move realistically through the simulation.

After Phase 1, we should be able to:
1. Load a scenario YAML file
2. Spawn all entities at their initial positions
3. Move entities along waypoints, patrol areas, or intercept courses
4. Fire timed events that change entity behavior mid-scenario
5. See all of this in real-time via the console adapter and WebSocket

**Read the full plan:** `edge-c2-simulator-plan.md`  
**Read the scenarios:** `config/scenarios/sulu_sea_fishing_intercept.yaml` and 
`config/scenarios/semporna_kfr_response.yaml`  
**Geodata:** `geodata/esszone_sulu_sea.geojson`

---

## Task 1: Waypoint Movement (`simulator/movement/waypoint.py`)

The most important movement strategy. Entities follow a series of 
time-stamped waypoints with smooth interpolation between them.

```python
"""
Waypoint-based movement with great-circle interpolation.

Given a list of waypoints with (lat, lon, speed, time), interpolates
the entity's position at any simulation time. Uses great-circle 
(geodesic) math for accurate lat/lon interpolation over distances
up to hundreds of kilometers.
"""
```

### Interface:

```python
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

@dataclass
class Waypoint:
    lat: float
    lon: float
    alt_m: float = 0.0
    speed_knots: float = 0.0
    time_offset: timedelta = timedelta()  # Offset from scenario start
    metadata_overrides: dict = None  # e.g., {"ais_active": false} at this waypoint

class WaypointMovement:
    def __init__(self, waypoints: list[Waypoint], scenario_start: datetime):
        """
        waypoints: ordered list, must have at least 2 entries
        scenario_start: absolute datetime for time_offset reference
        """
    
    def get_state(self, sim_time: datetime) -> MovementState:
        """
        Returns interpolated position, heading, speed for given sim_time.
        
        - Before first waypoint: entity at first waypoint position, speed 0
        - Between waypoints: great-circle interpolation
        - After last waypoint: entity at last waypoint position, speed 0
        - Heading: calculated from bearing between interpolated position 
          and next waypoint
        - Speed: interpolated between waypoint speeds (smooth transition)
        """
    
    def is_complete(self, sim_time: datetime) -> bool:
        """True if sim_time is past the last waypoint."""
    
    @property
    def total_duration(self) -> timedelta:
        """Time from first to last waypoint."""

@dataclass
class MovementState:
    lat: float
    lon: float
    alt_m: float
    heading_deg: float  # True heading 0-360
    speed_knots: float
    course_deg: float   # Course over ground (may differ from heading)
    metadata_overrides: dict | None  # Waypoint-triggered metadata changes
```

### Implementation requirements:

1. **Great-circle interpolation** — Use `geopy.distance.geodesic` for distance 
   calculations and the geodesic inverse/direct problem for interpolation. 
   Do NOT use simple linear lat/lon interpolation — it's visibly wrong over 
   distances > 10km.

2. **Heading calculation** — Forward azimuth (initial bearing) from current 
   interpolated position to next waypoint. Use the geodesic inverse formula:
   ```
   bearing = atan2(sin(Δlon)·cos(lat2), cos(lat1)·sin(lat2) - sin(lat1)·cos(lat2)·cos(Δlon))
   ```

3. **Speed interpolation** — If waypoint A has speed 12 kts and waypoint B has 
   speed 20 kts, the entity should smoothly accelerate between them, not jump 
   instantly. Use linear interpolation based on time fraction between waypoints.

4. **Metadata overrides** — When a waypoint has metadata changes (like 
   `ais_active: false`), apply them when the entity reaches that waypoint. 
   The `MovementState` should carry these for the entity updater to apply.

5. **Edge cases:**
   - Single waypoint: entity is stationary at that position
   - Entity at final waypoint: speed 0, position fixed
   - Two waypoints with same time: instant teleport (shouldn't happen, but handle)

### Tests (`tests/unit/test_waypoint.py`):

- Two waypoints 100km apart, verify midpoint is on great circle
- Speed interpolation between slow and fast waypoints
- Heading calculation (north, east, south, west, and diagonal bearings)
- Before first waypoint: entity at start position
- After last waypoint: entity at end position, speed 0
- Metadata override applied at correct waypoint time
- Distance accuracy: known distance Sandakan→Semporna (~200km), verify 
  travel time matches expected at given speed

---

## Task 2: Patrol Movement (`simulator/movement/patrol.py`)

Entities patrol randomly within a polygon (e.g., MMEA patrol vessel in a 
designated zone).

```python
"""
Random patrol within a GeoJSON polygon.

Generates random waypoints inside the polygon boundary. Entity moves 
between waypoints at a speed within its type's range, with configurable 
dwell time at each point. Creates natural-looking patrol behavior.
"""

class PatrolMovement:
    def __init__(
        self,
        polygon: shapely.geometry.Polygon,
        speed_range_knots: tuple[float, float],  # (min, max)
        dwell_time_range_s: tuple[int, int] = (30, 120),  # Pause at each point
        seed: int = None  # For reproducibility
    ):
        """Generate initial set of random waypoints within polygon."""
    
    def get_state(self, sim_time: datetime) -> MovementState:
        """Current position on patrol route."""
    
    def regenerate_waypoints(self):
        """Generate new random waypoints (called when current set exhausted)."""
```

### Implementation requirements:

1. **Random point in polygon** — Use Shapely's `polygon.bounds` to get bounding 
   box, generate random points, reject those outside polygon. Generate 5-8 
   waypoints at a time, regenerate when exhausted.

2. **Smooth turns** — Don't create waypoints that require >90° turns. If a 
   randomly generated waypoint would cause a sharp reversal, regenerate it. 
   Check by computing bearing change from previous leg.

3. **Speed variation** — Each leg gets a random speed within the entity's range. 
   Vary by ±10% within the leg for micro-realism.

4. **Dwell time** — Entity pauses at each waypoint for a random duration within 
   `dwell_time_range_s`. During dwell, speed = 0, position fixed, heading 
   slowly drifts ±5° (simulating station-keeping).

### Tests (`tests/unit/test_patrol.py`):

- All generated waypoints are inside the polygon
- Speed within specified range
- No sharp turns (>90° heading change between consecutive legs)
- Entity position always inside polygon
- Dwell time works (speed = 0 during dwell)

---

## Task 3: Intercept Movement (`simulator/movement/intercept.py`)

Entity pursues a moving target. Used when an ORDER event commands a vessel 
or aircraft to intercept a suspect.

```python
"""
Pursuit intercept course calculation.

Calculates an intercept heading toward a moving target, optionally 
using lead pursuit (aim ahead of target) rather than tail chase 
(aim directly at current position). Updates heading each tick.
"""

class InterceptMovement:
    def __init__(
        self,
        entity_speed_knots: float,  # Pursuer max speed
        target_entity_id: str,      # ID of entity to chase
        entity_store: EntityStore,  # To look up target's current position
        intercept_radius_m: float = 500,  # "Caught" when within this radius
        lead_pursuit: bool = True   # Use lead pursuit vs tail chase
    ):
        pass
    
    def get_state(self, sim_time: datetime) -> MovementState:
        """
        Look up target's current position from entity_store.
        Calculate intercept heading. Return full speed toward target.
        """
    
    def is_intercepted(self) -> bool:
        """True when pursuer is within intercept_radius of target."""
```

### Implementation requirements:

1. **Target lookup** — Each tick, look up the target entity's current position 
   from the EntityStore. If target not found (removed), hold current heading.

2. **Lead pursuit** — For faster pursuers, calculate where the target WILL BE 
   rather than where it IS. Use target's current course and speed to project 
   ahead. This gives a realistic converging course rather than a long tail chase.
   
   Simple lead pursuit formula:
   - Estimate time to intercept: `distance / (pursuer_speed - target_speed_component)`
   - Project target position forward by that time
   - Set heading toward projected position
   - Recalculate each tick (the projection improves as distance closes)

3. **Tail chase fallback** — If lead pursuit calculation fails (e.g., target is 
   faster), fall back to tail chase (head directly at target's current position).

4. **Altitude convergence** (for aircraft) — If pursuer and target are at different 
   altitudes, climb/descend at a reasonable rate (1000 fpm for helicopters, 
   3000 fpm for fixed-wing) while also converging horizontally.

5. **Intercept detection** — Check distance each tick. When within 
   `intercept_radius_m`, set `is_intercepted()` = true. The event engine will 
   handle what happens next.

### Tests (`tests/unit/test_intercept.py`):

- Pursuer converges on stationary target
- Pursuer converges on moving target (lead pursuit)
- Intercept detected when within radius
- Faster target: pursuer follows in tail chase (never catches up unless 
  target slows)
- Heading updates each tick toward target

---

## Task 4: Position Noise (`simulator/movement/noise.py`)

Adds realistic GPS/sensor noise to make entities look real, not computer-generated.

```python
"""
Realistic position and movement noise.

Without noise, entities move on perfect mathematical curves that look 
artificial. This module adds sensor-appropriate jitter to positions, 
speeds, and headings.
"""

class PositionNoise:
    def __init__(
        self,
        position_noise_m: float = 15.0,   # Standard deviation in meters
        speed_noise_pct: float = 0.02,     # ±2% speed drift
        heading_noise_deg: float = 2.0,    # ±2° heading oscillation
        seed: int = None
    ):
        pass
    
    def apply(self, state: MovementState) -> MovementState:
        """
        Apply noise to a MovementState. Returns a new MovementState
        with jittered values. Original is not modified.
        """
    
    @staticmethod
    def for_domain(domain: str) -> 'PositionNoise':
        """
        Factory method returning domain-appropriate noise levels:
        - MARITIME: position ±15m, speed ±2%, heading ±2°
        - AIR: position ±50m, speed ±1%, heading ±1°
        - GROUND_VEHICLE: position ±5m, speed ±3%, heading ±1°
        - PERSONNEL: position ±3m, speed ±5%, heading ±5°
        """
```

### Implementation requirements:

1. **Gaussian noise** — Use normal distribution (not uniform) for position and 
   speed noise. Real sensor errors follow Gaussian distributions.

2. **Correlated noise** — Don't use independent random samples each tick. Real 
   GPS wander is correlated over time (Brownian-like). Maintain an internal 
   state that drifts slowly rather than jumping randomly each tick.
   
   Simple approach: keep a "noise offset" that does a random walk:
   ```
   offset_x += random.gauss(0, step_size)
   offset_x = clamp(offset_x, -3*sigma, 3*sigma)
   ```

3. **Position noise** — Apply as a random offset in meters (north and east), 
   then convert back to lat/lon. At Malaysian latitudes (~5°N), 
   1° latitude ≈ 111km, 1° longitude ≈ 110.5km.

4. **Speed noise** — Continuous drift within ±X%. Never negative speed.

5. **Heading noise** — Small oscillations. Should be smooth (correlated), 
   not jumpy.

### Tests (`tests/unit/test_noise.py`):

- Noisy position within expected sigma of true position (statistical test 
  over many samples)
- Speed stays within expected range
- Heading noise is bounded
- Domain-specific factory returns correct parameters
- Correlated noise: consecutive samples should be closer together than 
  independent samples would be

---

## Task 5: Scenario Loader (`simulator/core/scenario_loader.py`)

Parses scenario YAML files and creates all entities with their movement strategies.

```python
"""
YAML scenario file parser.

Reads a scenario YAML file, validates it against entity type definitions,
creates Entity objects with assigned MovementStrategy instances, and 
returns a complete ScenarioState ready for the simulation engine.
"""

@dataclass
class ScenarioState:
    name: str
    description: str
    duration: timedelta
    center: tuple[float, float]  # (lat, lon)
    zoom: int
    entities: dict[str, Entity]           # entity_id → Entity
    movements: dict[str, MovementBase]    # entity_id → movement strategy
    events: list[ScenarioEvent]           # time-sorted event list
    start_time: datetime                  # Scenario start timestamp

@dataclass
class ScenarioEvent:
    time_offset: timedelta
    event_type: str        # DETECTION, ALERT, ORDER, etc.
    description: str
    severity: str
    target: str | None           # Single entity ID
    targets: list[str] | None    # Multiple entity IDs
    action: str | None           # intercept, deploy, patrol, etc.
    intercept_target: str | None
    destination: dict | None     # {lat, lon}
    area: str | None             # GeoJSON polygon reference
    position: dict | None        # {lat, lon} for event location
    alert_agencies: list[str]
    metadata: dict               # Any extra fields from YAML

class ScenarioLoader:
    def __init__(self, geodata_path: str = "geodata/"):
        """Load GeoJSON polygon/route lookups from geodata directory."""
    
    def load(self, scenario_path: str, start_time: datetime = None) -> ScenarioState:
        """
        Parse YAML file and return complete ScenarioState.
        
        Steps:
        1. Read YAML
        2. Validate structure
        3. Load referenced GeoJSON areas/routes
        4. Create Entity objects for all scenario_entities
        5. Create background entities (with auto-generated positions/routes)
        6. Assign movement strategies:
           - Entities with waypoints → WaypointMovement
           - Entities with patrol behavior → PatrolMovement
           - Entities with standby behavior → StationaryMovement (speed=0)
        7. Parse events into sorted ScenarioEvent list
        8. Return ScenarioState
        """
    
    def _load_geojson_areas(self) -> dict[str, Polygon]:
        """Load all GeoJSON files, index by zone_id/area_id."""
    
    def _load_geojson_routes(self) -> dict[str, LineString]:
        """Load all GeoJSON route files, index by route_id."""
    
    def _create_background_entities(self, config: dict) -> list[tuple[Entity, MovementBase]]:
        """
        Auto-generate background traffic entities.
        For each background entry:
        - Generate `count` entities with unique IDs
        - Place them randomly within area or along route
        - Assign PatrolMovement (area) or WaypointMovement (route)
        - Randomize speed within type's range ± speed_variation
        """
    
    def validate(self, scenario_path: str) -> list[str]:
        """
        Validate scenario file without loading. Returns list of errors.
        Checks: entity types valid, referenced zones exist, events 
        chronological, entity IDs in events exist, coordinates valid.
        """
```

### Implementation requirements:

1. **GeoJSON loading** — Scan all `.geojson` files in `geodata/` (recursively). 
   Each Feature has a `zone_id`, `route_id`, or `area_id` property. Build 
   lookup dictionaries.

2. **Entity ID generation** for background traffic:
   ```
   BG-{type}-{sequence:03d}
   # e.g., BG-CIVILIAN_FISHING-001, BG-CIVILIAN_CARGO-014
   ```

3. **Callsign generation** for background traffic — Generate plausible callsigns:
   - Cargo: "MV {name}" where name is from a small pool of words
   - Fishing: "Nelayan {number}" or "FB-{registration}"
   - Tanker: "MT {name}"

4. **Route distribution** for background entities along a route — Don't place 
   all at the start. Distribute evenly along the route so at scenario start 
   they're already spread out and moving.

5. **Scenario start time** — If not provided, default to `2026-04-15T08:00:00Z` 
   (a plausible demo date/time).

6. **Error handling** — Clear error messages. If a referenced zone doesn't exist, 
   say `"Area 'esszone_sector_6' not found in geodata. Available: [list]"`.

### Tests (`tests/unit/test_scenario_loader.py`):

- Load `sulu_sea_fishing_intercept.yaml` successfully
- All entities have valid positions (within ESSZONE boundary)
- Background entities generated with correct count
- Events sorted by time
- Invalid scenario: missing entity type → clear error message
- Invalid scenario: nonexistent zone reference → clear error message
- Validate function catches problems without crashing

---

## Task 6: Event Engine (`simulator/core/event_engine.py`)

Processes timed events during simulation. Events can change entity behavior 
mid-scenario.

```python
"""
Timed event processor.

Checks the scenario event timeline each simulation tick. When an event's
time arrives, it fires: broadcasting the event through transport adapters
and modifying entity behavior as specified.
"""

class EventEngine:
    def __init__(
        self,
        events: list[ScenarioEvent],
        entity_store: EntityStore,
        movements: dict[str, MovementBase],
        scenario_start: datetime
    ):
        """
        events: sorted list from ScenarioLoader
        entity_store: for looking up / modifying entities
        movements: for swapping movement strategies on entities
        """
    
    def tick(self, sim_time: datetime) -> list[ScenarioEvent]:
        """
        Check if any events should fire at this sim_time.
        Returns list of newly fired events (may be empty).
        
        For each fired event:
        1. Mark event as fired (don't re-fire)
        2. If event has an action, modify target entity:
           - "intercept" → swap movement to InterceptMovement
           - "deploy" → swap movement to WaypointMovement toward destination
           - "patrol" → swap movement to PatrolMovement
           - "lockdown" → swap movement to StationaryMovement
           - "activate" → change entity status from IDLE to ACTIVE
        3. Update entity status based on action:
           - intercept → INTERCEPTING
           - deploy/respond → RESPONDING
           - patrol → ACTIVE
           - lockdown → ACTIVE (stationary)
        4. Return fired events for transport broadcast
        """
    
    def get_fired_events(self) -> list[ScenarioEvent]:
        """All events that have fired so far."""
    
    def get_upcoming_events(self, window: timedelta = None) -> list[ScenarioEvent]:
        """Events not yet fired, optionally within a time window."""
    
    @property
    def is_complete(self) -> bool:
        """True when all events have fired."""
```

### Implementation requirements:

1. **Tick processing** — On each tick, iterate through unfired events. Fire any 
   where `scenario_start + event.time_offset <= sim_time`. Support multiple 
   events at the same timestamp.

2. **Movement swapping** — When an ORDER event fires with an action:
   ```python
   if event.action == "intercept":
       new_movement = InterceptMovement(
           entity_speed_knots=entity.speed_knots or type_max_speed,
           target_entity_id=event.intercept_target,
           entity_store=self.entity_store
       )
       self.movements[event.target] = new_movement
   
   elif event.action == "deploy":
       destination_wp = Waypoint(
           lat=event.destination["lat"],
           lon=event.destination["lon"],
           speed_knots=type_max_speed * 0.9,  # 90% max speed for urgency
           time_offset=timedelta(0)  # Start immediately
       )
       current_pos = self.entity_store.get_entity(event.target).position
       origin_wp = Waypoint(
           lat=current_pos.latitude,
           lon=current_pos.longitude,
           speed_knots=0,
           time_offset=timedelta(0)
       )
       new_movement = WaypointMovement(
           [origin_wp, destination_wp], 
           sim_time  # Use current sim_time as new reference
       )
       self.movements[event.target] = new_movement
   ```

3. **Multi-target events** — If event has `targets` (plural), apply the action 
   to each entity in the list.

4. **Entity status updates** — Update the entity's `status` field in the store 
   when actions change behavior.

5. **Event broadcasting** — The tick method returns fired events. The main 
   simulation loop broadcasts them through all transport adapters.

### Tests (`tests/unit/test_event_engine.py`):

- Events fire at correct simulation time
- Events don't re-fire
- ORDER/intercept swaps movement strategy
- ORDER/deploy creates waypoint movement to destination
- Multi-target event applies to all targets
- Entity status updated on action
- is_complete true when all events fired

---

## Task 7: Main Simulation Loop (`scripts/run_simulator.py`)

Wire everything together into the main simulation loop.

```python
"""
Main simulation entry point.

Loads a scenario, initializes all components, and runs the simulation 
loop. Each tick: advance clock, update all entity positions via their
movement strategies, fire events, push updates through transport adapters.
"""

# CLI interface (Click):
# edge-c2-sim --scenario config/scenarios/sulu_sea_fishing_intercept.yaml
#              --speed 1
#              --port 8765
#              --transport ws,console

@click.command()
@click.option('--scenario', required=True, help='Path to scenario YAML file')
@click.option('--speed', default=1.0, help='Simulation speed multiplier')
@click.option('--port', default=8765, help='WebSocket server port')
@click.option('--transport', default='ws,console', help='Comma-separated transports')
@click.option('--tick-rate', default=1.0, help='Ticks per second (real-time)')
def main(scenario, speed, port, transport, tick_rate):
    pass
```

### Main loop pseudocode:

```python
async def simulation_loop(scenario_state, clock, entity_store, event_engine, 
                          transports, tick_interval_s):
    """
    Core simulation loop — runs until scenario complete or user stops.
    """
    while True:
        # 1. Get current simulation time
        sim_time = clock.get_sim_time()
        
        # 2. Update all entity positions
        for entity_id, movement in scenario_state.movements.items():
            state = movement.get_state(sim_time)
            entity = entity_store.get_entity(entity_id)
            if entity:
                # Apply noise
                noise = PositionNoise.for_domain(entity.domain)
                noisy_state = noise.apply(state)
                
                # Update entity
                entity.update_position(
                    lat=noisy_state.lat,
                    lon=noisy_state.lon, 
                    alt=noisy_state.alt_m,
                    heading=noisy_state.heading_deg,
                    speed=noisy_state.speed_knots,
                    course=noisy_state.course_deg
                )
                
                # Apply metadata overrides from waypoints
                if noisy_state.metadata_overrides:
                    entity.metadata.update(noisy_state.metadata_overrides)
                
                entity_store.upsert_entity(entity)
        
        # 3. Process events
        fired_events = event_engine.tick(sim_time)
        for event in fired_events:
            for transport in transports:
                await transport.push_event(event.to_dict())
        
        # 4. Push entity updates through transports
        all_entities = entity_store.get_all_entities()
        for transport in transports:
            await transport.push_bulk_update(all_entities)
        
        # 5. Check scenario completion
        if event_engine.is_complete:
            # Could keep running (entities still moving) or stop
            pass
        
        # 6. Wait for next tick
        await asyncio.sleep(tick_interval_s / clock.speed)
```

### Requirements:

1. **Graceful startup** — Print clear status messages:
   ```
   Edge C2 Simulator v0.1.0
   Loading scenario: Sulu Sea IUU Fishing Intercept
   Loaded 6 scenario entities, 20 background entities
   Loaded 17 events over 50 minutes
   Starting WebSocket server on ws://0.0.0.0:8765
   Console output enabled
   Simulation starting at 2026-04-15T08:00:00Z (speed: 1x)
   Press Ctrl+C to stop
   ```

2. **Graceful shutdown** — Handle SIGINT/SIGTERM. Close WebSocket connections, 
   print summary (entities processed, events fired, duration).

3. **Speed control via WebSocket** — The WebSocket adapter receives speed/pause 
   commands from COP clients. Wire these to the simulation clock.

4. **Tick rate** — Default 1 tick per second real-time. At 10x speed, simulation 
   advances 10 seconds per tick. At 60x, 60 seconds per tick. Adjust entity 
   update frequency accordingly.

5. **Bulk updates** — Don't push individual entity updates if >10 entities. Use 
   `push_bulk_update` for efficiency.

### Integration test (`tests/integration/test_scenario_execution.py`):

Write a test that:
1. Loads `sulu_sea_fishing_intercept.yaml`
2. Runs at 60x speed for the full 50-minute scenario duration (~50 seconds real)
3. Verifies:
   - All entities exist in the store
   - Suspect vessels moved from start to end positions
   - Events fired in chronological order
   - At least one intercept event has `is_intercepted` entities
   - Entity statuses changed (standby → responding → intercepting)
4. Captures all console adapter output and verifies key messages present

---

## Task 8: Scenario Validator (`scripts/validate_scenario.py`)

A quick CLI tool to validate scenario YAML without running the full simulation.

```python
"""
Validate a scenario YAML file.

Usage: python scripts/validate_scenario.py config/scenarios/my_scenario.yaml

Checks:
- YAML syntax valid
- Required top-level fields present
- All entity types are recognized
- All referenced GeoJSON zones/routes exist
- Event times are chronological
- Entity IDs in events match scenario_entities
- Waypoint coordinates are in valid lat/lon ranges
- Speeds are within entity type ranges
- No duplicate entity IDs
"""
```

Print clear pass/fail output:
```
Validating: config/scenarios/sulu_sea_fishing_intercept.yaml

✓ YAML syntax valid
✓ Required fields present (name, duration, center, scenario_entities, events)
✓ 11 scenario entities, all types valid
✓ 4 background entity groups
✓ 17 events in chronological order
✓ All entity references in events exist
✓ All GeoJSON zone references found
✓ Coordinates within valid ranges
✓ Speeds within entity type limits

PASS — Scenario is valid
```

Or on failure:
```
✗ Event at 00:28 references entity "RMN-PV-999" which is not in scenario_entities
✗ Area "esszone_sector_6" not found. Available: esszone_sector_1_kudat, ...
✗ Entity "IFF-001" waypoint 3: speed 45 exceeds SUSPECT_VESSEL max of 40 knots

FAIL — 3 errors found
```

---

## Dependency Notes

Phase 1 adds no new dependencies beyond what Phase 0 already has:
- `geopy` — geodesic distance/bearing calculations (already in pyproject.toml)
- `shapely` — polygon point-in-polygon tests (already in pyproject.toml)
- `pyyaml` — YAML parsing (already in pyproject.toml)

---

## Definition of Done

Phase 1 is complete when:

1. `python scripts/validate_scenario.py config/scenarios/sulu_sea_fishing_intercept.yaml` → PASS
2. `python scripts/validate_scenario.py config/scenarios/semporna_kfr_response.yaml` → PASS
3. `edge-c2-sim --scenario config/scenarios/sulu_sea_fishing_intercept.yaml --speed 10 --transport console` 
   runs and shows entities moving, events firing, intercepts happening
4. WebSocket adapter broadcasts updates that a COP client could consume
5. All unit tests pass with >80% coverage on movement modules
6. Integration test runs full scenario at 60x and verifies correctness
