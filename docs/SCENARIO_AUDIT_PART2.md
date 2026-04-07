# Scenario Audit — Part 2: Trail Jitter & Ships on Land

These are two critical visual bugs identified on the live deployment at
ec2sim.brumbiesoft.org. Both are demo-blocking — they make the COP look
unprofessional and undermine credibility with the audience.

**Read the Part 1 audit first** — it covers entity type/SIDC corrections,
event-simulation alignment, and missing deploy destinations.

---

## Part F: Trail Jitter / "Squiggle" Bug — Critical Visual Defect

### Symptom

Entity trails look like thick fuzzy worms or seismograph readings instead
of clean lines. Worst on slow-moving vessels (fishing boats, patrol vessels).
At operational zoom levels the trails are visually unusable.

### Evidence (captured from live site at sim time 10:05:38)

Trail point analysis for IFF-001 (fishing trawler at 3-4 knots):
- Trail has **3,527 points** stored
- Consecutive point distances: 45m, 49m, 62m, 26m, 46m, 14m, 20m, 46m, 54m...
- **Actual movement per tick at 4 kts: ~2 meters**
- **Noise per tick: 14-62 meters (7-30x the actual movement)**

Trail point analysis for BG-CIVILIAN_FISHING-001:
- Trail has **3,460 points** stored
- Consecutive point distances: 53m, 30m, 12m, 25m, 23m, 27m, 38m, 51m...
- Same problem: noise dominates the signal completely

### Root Causes (3 compounding issues)

**1. Backend — Noise amplitude wrong for slow entities**

The `PositionNoise` spec says ±15m for maritime. But this is applied as
independent random offsets per tick. For a fishing boat at 4 kts (~2 m/s):

```
Signal (actual movement per tick): ~2 meters
Noise (random offset per tick):    ±15 meters (so up to 30m swing)
Signal-to-noise ratio:             0.07 to 0.13

Result: Random walk, not a realistic track
```

For faster entities (naval vessels at 30 kts = ~15 m/s), the ratio is
better (~1:1) but still produces visible jitter.

**2. Backend — No temporal correlation (white noise)**

The noise module generates independent random offsets each tick. Real GPS
noise is temporally correlated — the error drifts smoothly over seconds,
it doesn't teleport randomly every tick.

Current implementation (pseudocode):
```python
# WRONG: Independent random each tick
offset_lat = random.gauss(0, noise_amplitude)
offset_lon = random.gauss(0, noise_amplitude)
```

Correct approach — smoothed random walk:
```python
# RIGHT: Correlated noise using exponential smoothing
self._noise_lat += random.gauss(0, step_size)
self._noise_lat *= decay_factor  # e.g., 0.95 per tick
self._noise_lon += random.gauss(0, step_size)
self._noise_lon *= decay_factor
```

**3. Frontend — Trail stores every noisy position, no thinning**

The trail polyline stores the position from every WebSocket update
(every tick). This means:
- 3,500+ points per entity for a 1-hour scenario at 1x speed
- Every point has full noise applied
- The polyline renders all points, amplifying the visual jitter
- At operational zoom, the line width makes each deviation visible

### Required Fixes

#### Fix F1: Backend — Correlated noise (simulator/movement/noise.py)

Replace the current per-tick independent random noise with a smoothed
random walk. Each `PositionNoise` instance must be **stateful** — it
holds its current noise offset and drifts it smoothly.

```python
class PositionNoise:
    def __init__(self, domain):
        self._noise_lat = 0.0
        self._noise_lon = 0.0
        self._heading_noise = 0.0

        # Config per domain
        if domain == Domain.MARITIME:
            self._max_amplitude_m = 15.0
            self._step_size = 2.0      # Small random step per tick
            self._decay = 0.92         # Smooth decay → correlated drift
        elif domain == Domain.AIR:
            self._max_amplitude_m = 50.0
            self._step_size = 5.0
            self._decay = 0.90
        else:  # ground
            self._max_amplitude_m = 5.0
            self._step_size = 0.5
            self._decay = 0.95

    def apply(self, state: MovementState) -> MovementState:
        # Random walk with decay → smooth correlated drift
        self._noise_lat += random.gauss(0, self._step_size)
        self._noise_lon += random.gauss(0, self._step_size)

        # Clamp to max amplitude
        self._noise_lat = max(-self._max_amplitude_m,
                              min(self._max_amplitude_m, self._noise_lat))
        self._noise_lon = max(-self._max_amplitude_m,
                              min(self._max_amplitude_m, self._noise_lon))

        # Apply decay (noise drifts back toward zero over time)
        self._noise_lat *= self._decay
        self._noise_lon *= self._decay

        # Convert meters to lat/lon offset
        dlat = self._noise_lat / 111000.0
        dlon = self._noise_lon / (111000.0 * cos(radians(state.lat)))

        return MovementState(
            lat=state.lat + dlat,
            lon=state.lon + dlon,
            alt_m=state.alt_m,
            heading_deg=state.heading_deg + self._heading_noise,
            speed_knots=state.speed_knots,
            course_deg=state.course_deg,
        )
```

**Critical:** Each entity must get its OWN `PositionNoise` instance so the
state is per-entity. Don't share one noise object across entities. Check
the current code — if noise is applied via a class method or a shared
singleton, that needs to change to per-entity instances stored alongside
the movement strategy in the simulation loop.

#### Fix F2: Backend — Send clean position for trails

Add a `track_position` field to the WebSocket entity update message that
contains the PRE-NOISE position. The frontend uses this for trails and
the noisy `position` for the icon only.

In the simulation loop (scripts/run_simulator.py or equivalent), after
computing the movement state but before applying noise:

```python
# Get clean position from movement strategy
clean_state = movement.get_state(sim_time)

# Apply noise for display
noisy_state = noise.apply(clean_state)

# Send both
entity_update = {
    "entity_id": entity.entity_id,
    "position": {"lat": noisy_state.lat, "lon": noisy_state.lon},
    "track_position": {"lat": clean_state.lat, "lon": clean_state.lon},
    # ... other fields use noisy values
}
```

#### Fix F3: Frontend — Trail thinning and capping

In the entity manager (cop/src/entity-manager.js or equivalent), change
the trail update logic:

1. **Use `track_position` if available** for trail points, fall back to
   `position` if not.

2. **Distance-based thinning** — only add a trail point when the entity
   has moved more than a minimum distance from the last stored point:

```javascript
const MIN_TRAIL_DISTANCE_M = 100;  // No points closer than this

function maybeAddTrailPoint(entityId, newCartesian) {
    const trail = trailHistory[entityId];
    if (!trail || trail.length === 0) {
        addTrailPoint(entityId, newCartesian);
        return;
    }
    const lastPoint = trail[trail.length - 1];
    const distance = Cesium.Cartesian3.distance(lastPoint, newCartesian);
    if (distance > MIN_TRAIL_DISTANCE_M) {
        addTrailPoint(entityId, newCartesian);
    }
}
```

3. **Cap max trail points** at 300 per entity. Drop oldest when full
   (ring buffer or shift).

4. **Reduce trail line width** — currently appears to be 3-4px. Set to
   1.5px for operational zoom levels. Consider making it zoom-adaptive.

---

## Part G: Ships on Land — No Geographic Constraint

### Symptom

Maritime entities (naval vessels, patrol craft, fishing boats) frequently
end up positioned on land. Observed on the live site at sim time 10:14:11:

| Entity | Type | Position | Problem |
|--------|------|----------|---------|
| RMN-FIC-202 (KD G2000 Charlie) | MIL_NAVAL_FIC | 5.53°N, 118.35°E | Deep inland, middle of Borneo |
| IFF-002 (Unknown Trawler 2) | SUSPECT_VESSEL | 5.73°N, 118.35°E | On land, west of coast |
| RMN-FIC-101 (KD G2000 Alpha) | MIL_NAVAL_FIC | 5.83°N, 118.11°E | On shore at Sandakan |

### Root Cause

There is **zero geographic awareness** in the movement engine. No part of
the system checks whether a maritime entity's calculated position is in
water or on land:

- `WaypointMovement` interpolates great-circle between waypoints — if a
  waypoint is on land, or the great-circle arc crosses land, the entity
  sails inland.
- `InterceptMovement` calculates a direct bearing from interceptor to
  target. If that bearing crosses a coastline, the ship cuts straight
  across the peninsula.
- `PatrolMovement` generates random waypoints inside a polygon. If the
  polygon includes land areas, patrol points may be on land.
- The entity store accepts any position update without validation.
- The frontend renders whatever position the backend sends.

The Sabah coastline is complex — Sandakan Bay, the islands around
Semporna, the peninsula between the Sulu and South China seas. Any
movement strategy that uses straight-line bearings WILL cross land here.

### Required Fixes

#### Fix G1: Water validation utility (simulator/geo/water_check.py) — NEW FILE

Create a utility that checks whether a (lat, lon) point is in water.
The geodata directory already contains ESSZONE GeoJSON files. Use Shapely:

```python
from shapely.geometry import Point, shape
from functools import lru_cache
import json

class WaterValidator:
    """Validates that maritime positions are in water, not on land."""

    def __init__(self, land_polygons_path: str = "geodata/"):
        """
        Load coastline/land polygons from GeoJSON files.

        The existing esszone_sulu_sea.geojson and any other GeoJSON files
        in geodata/ contain zone polygons. We need LAND polygons.

        If no land polygon GeoJSON exists yet, create one:
        - Use a simplified Borneo coastline polygon covering the ESSZONE
          area (lat 4.0-7.0, lon 115.0-120.0)
        - This doesn't need to be meter-accurate — even a rough polygon
          will catch the gross violations (ships 50km inland)
        - Save as geodata/land/sabah_coastline.geojson
        """
        self._land_polygons = []
        self._load_land_polygons(land_polygons_path)

    def is_water(self, lat: float, lon: float) -> bool:
        """Returns True if the point is NOT inside any land polygon."""
        point = Point(lon, lat)  # Shapely uses (x, y) = (lon, lat)
        for poly in self._land_polygons:
            if poly.contains(point):
                return False
        return True

    def nearest_water_point(self, lat: float, lon: float) -> tuple[float, float]:
        """
        If a point is on land, find the nearest point on the coastline.
        Uses the polygon boundary to find the closest point.
        """
        point = Point(lon, lat)
        for poly in self._land_polygons:
            if poly.contains(point):
                nearest = poly.boundary.interpolate(
                    poly.boundary.project(point)
                )
                return (nearest.y, nearest.x)  # back to (lat, lon)
        return (lat, lon)  # already in water
```

#### Fix G2: Create Sabah land polygon (geodata/land/sabah_coastline.geojson)

If no land polygon exists, create a simplified one. This is a one-time
data task. The polygon needs to cover the Sabah/Borneo coastline in the
ESSZONE operational area (roughly lat 4.0-7.0, lon 115.0-120.0).

Sources for coordinates:
- Trace from the existing CesiumJS globe (the terrain is already loaded)
- Use a simplified polygon with ~50-100 points along the coastline
- Include major islands (Pulau Bum Bum, Sipadan area) as exclusion
  zones (holes in the land polygon, since those are surrounded by water)

The polygon doesn't need to be survey-grade. A 500m accuracy coastline
will prevent the gross "ship 50km inland" violations.

#### Fix G3: Validate positions in the simulation loop

In the main simulation loop, after computing each entity's new position,
validate maritime entities against the water check:

```python
# In the simulation loop, after movement.get_state() and noise.apply():

if entity.domain == Domain.MARITIME:
    if not water_validator.is_water(new_lat, new_lon):
        # Option A: Snap to nearest water point
        new_lat, new_lon = water_validator.nearest_water_point(new_lat, new_lon)

        # Option B (better for intercept): Adjust heading to follow coast
        # Keep the entity at its last known water position and rotate
        # its heading 15° away from land until it finds open water
```

#### Fix G4: Validate waypoints at scenario load time

In `scenario_loader.py`, when parsing scenario entities, validate that:
- All maritime entity `initial_position` values are in water
- All maritime entity `waypoints` are in water
- The great-circle path between consecutive waypoints doesn't cross land
  (check a few interpolated points along each segment)

Log warnings for any violations so the scenario author can fix them.

#### Fix G5: InterceptMovement coastal avoidance

This is the hardest fix but the most important, since InterceptMovement
is the primary cause of ships crossing land. Two approaches:

**Simple (recommended for demo):** Before applying the intercept bearing,
check if the next position would be on land. If so, rotate the heading
±15° in the direction that keeps the entity in water, and recheck. This
creates a crude "follow the coast" behavior.

```python
def get_state(self, sim_time):
    # Calculate direct bearing to target
    bearing = self._bearing_to_target(sim_time)

    # Check if next position at this bearing is in water
    next_lat, next_lon = self._project_position(bearing, self._speed, dt)

    if not self._water_validator.is_water(next_lat, next_lon):
        # Try rotating away from land
        for offset in [15, 30, 45, 60, 90, -15, -30, -45, -60, -90]:
            alt_lat, alt_lon = self._project_position(
                bearing + offset, self._speed, dt
            )
            if self._water_validator.is_water(alt_lat, alt_lon):
                bearing = bearing + offset
                next_lat, next_lon = alt_lat, alt_lon
                break

    return MovementState(lat=next_lat, lon=next_lon, ...)
```

**Proper (post-demo):** Use A* pathfinding on a water grid to compute a
route around coastlines. This is a larger effort and not needed for April.

---

## Implementation Order

For Claude Code, implement these fixes in this order:

1. **Fix F1** — Correlated noise (backend, self-contained, high impact)
2. **Fix F3** — Trail thinning and capping (frontend, self-contained, high impact)
3. **Fix G2** — Create Sabah land polygon GeoJSON
4. **Fix G1** — Water validation utility
5. **Fix G3** — Position validation in simulation loop
6. **Fix G4** — Waypoint validation at load time
7. **Fix F2** — Send clean track_position in WebSocket messages
8. **Fix G5** — InterceptMovement coastal avoidance

Fixes 1-3 are the highest visual impact for least effort. Fix G5 is the
hardest but addresses the root cause of ships on land during intercepts.

---

## Testing

After each fix, verify visually on the COP:

- **F1/F2/F3:** Trails should be smooth thin lines, not fuzzy worms.
  Zoom in on a slow fishing boat — trail should be a clean line with
  gentle drift, not a sawtooth zigzag.
- **G1-G5:** No maritime entity icons should appear over land at any
  point during the scenario. Run the full demo_combined scenario at 10x
  speed and watch the entire thing.
- **Regression:** Entity positions should still update smoothly. Noise
  should be subtle but visible (proving the data isn't "too clean").
  Intercept movements should still converge on targets, just routing
  around land instead of through it.
