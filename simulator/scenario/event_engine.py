"""
Reactive event engine with action-based movement and dependency chains.

Events fire based on:
- Absolute time (time: "00:05")
- Dependencies on other events (after: "ssas_alert:complete + 00:05")
- Both (time acts as minimum guard)

Supports v2 actions (transit, orbit, hold_station, escape, approach, rtb)
with automatic completion detection and on_complete message generation.
"""

import json
import logging
import math
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from geopy.distance import geodesic

from simulator.core.entity import Agency, Domain, Entity, EntityStatus, Position
from simulator.core.entity_store import EntityStore
from simulator.movement.approach import ApproachMovement
from simulator.movement.escape import EscapeMovement
from simulator.movement.hold_station import HoldStationMovement
from simulator.movement.intercept import InterceptMovement
from simulator.movement.orbit import OrbitMovement
from simulator.movement.transit import TransitMovement
from simulator.movement.waypoint import Waypoint, WaypointMovement
from simulator.scenario.loader import ENTITY_TYPES, ScenarioEvent

logger = logging.getLogger(__name__)

# Load entity type definitions for action speeds/altitudes
_ENTITY_TYPE_DEFS: dict[str, dict] = {}
_et_path = os.path.join(os.path.dirname(__file__), "../../config/entity_types.json")
if os.path.exists(_et_path):
    try:
        with open(_et_path) as _f:
            _ENTITY_TYPE_DEFS = json.load(_f).get("entity_types", {})
    except (json.JSONDecodeError, OSError):
        pass


def _get_action_speed(entity_type: str, action: str) -> float | None:
    """Get default speed for an entity type performing an action."""
    td = _ENTITY_TYPE_DEFS.get(entity_type, {})
    speeds = td.get("action_speeds_kn", {})
    if action in speeds:
        return speeds[action]
    # Fallback to max speed for unknown actions
    return td.get("max_speed_kn")


def _get_action_altitude(entity_type: str, action: str) -> float | None:
    """Get default altitude for an air entity performing an action."""
    td = _ENTITY_TYPE_DEFS.get(entity_type, {})
    altitudes = td.get("action_altitudes_m", {})
    return altitudes.get(action)


def _get_max_speed(entity_type: str) -> float:
    """Get max speed from entity_types.json, fall back to ENTITY_TYPES dict."""
    td = _ENTITY_TYPE_DEFS.get(entity_type, {})
    if "max_speed_kn" in td:
        return td["max_speed_kn"]
    # Legacy fallback
    legacy = ENTITY_TYPES.get(entity_type, {})
    return legacy.get("speed_range", (10, 20))[1]


def _bearing_from_center(c_lat: float, c_lon: float, p_lat: float, p_lon: float) -> float:
    """Bearing in degrees (0=N, 90=E) from (c_lat, c_lon) to (p_lat, p_lon).

    Matches OrbitMovement's angle convention so the orbit begins at the
    entity's current angular position around the centre, not at due north.
    """
    dy = p_lat - c_lat
    dx = (p_lon - c_lon) * math.cos(math.radians(c_lat))
    if dx == 0 and dy == 0:
        return 0.0
    return math.degrees(math.atan2(dx, dy)) % 360.0


def _build_search_pattern(
    metadata: dict, entity: Any, sim_time: datetime, entity_store: Any,
) -> "WaypointMovement":
    """Build an ASW expanding-square localisation pattern around a datum.

    Real-world ASW MAD-trap / localisation pattern (NATOPS): after initial
    overfly and MAD detection, the aircraft spirals outward in right-angle
    legs of increasing length. Each pair of legs grows by one step, so the
    spiral naturally re-crosses the datum datum-area from multiple bearings —
    exactly what a submarine hunter does once it has a fix.

    Metadata keys (all optional):
        search_center            entity_id OR {lat, lon} — datum centre
        search_step_nm           leg growth step (default 0.5 nm)
        search_iterations        number of outward expansions (default 20)
        search_speed             knots (default from entity type / 140)
        altitude_m               cruise altitude (default from entity type)
    """
    import math as _math
    from simulator.movement.waypoint import TurnParams, Waypoint, WaypointMovement
    from simulator.scenario.loader import ENTITY_TYPES

    center = metadata.get("search_center")
    step_nm = float(metadata.get("search_step_nm", 0.5))
    iterations = int(metadata.get("search_iterations", 20))
    speed = float(metadata.get(
        "search_speed",
        _get_action_speed(entity.entity_type, "orbit") or 140,
    ))
    altitude = float(metadata.get(
        "altitude_m",
        _get_action_altitude(entity.entity_type, "orbit")
        or entity.position.altitude_m,
    ))

    # Resolve datum centre.
    datum_lat = entity.position.latitude
    datum_lon = entity.position.longitude
    if isinstance(center, str):
        ce = entity_store.get_entity(center)
        if ce:
            datum_lat, datum_lon = ce.position.latitude, ce.position.longitude
    elif isinstance(center, dict):
        datum_lat = float(center.get("lat", datum_lat))
        datum_lon = float(center.get("lon", datum_lon))

    cos_lat = max(_math.cos(_math.radians(datum_lat)), 0.01)
    step_lat = step_nm / 60.0
    step_lon = step_nm / (60.0 * cos_lat)
    speed_mps = max(speed * 0.514444, 0.1)

    # Waypoint 0 — entity's current position.
    waypoints = [Waypoint(
        lat=entity.position.latitude, lon=entity.position.longitude,
        alt_m=altitude, speed_knots=speed,
        time_offset=timedelta(seconds=0),
    )]
    cur_lat, cur_lon = entity.position.latitude, entity.position.longitude
    cur_t = 0.0

    # Procedure turn entering the search — discretised 270° left arc so
    # the aircraft rolls smoothly from its current heading back over the
    # datum on a perpendicular bearing (classic MAD re-attack turn).
    # Without this the WaypointMovement has no arc at waypoint 0 (no prev
    # segment) and the aircraft snaps to the datum-bearing instantly.
    start_heading = float(entity.heading_deg)
    # R is the ATR's natural turning radius from entity type; fall back to
    # a sensible ASW circle if the entity has no turn params.
    turn_tuple_head = ENTITY_TYPES.get(entity.entity_type, {}).get("turn")
    R_m = (turn_tuple_head[0] * turn_tuple_head[1]) if turn_tuple_head else 1000.0
    # Lead 500 m straight before starting the arc — gives the arc math
    # a clean "previous segment" to anchor on.
    lead_m = 500.0
    theta_rad = _math.radians(start_heading)
    lead_dlat = (lead_m / 111320.0) * _math.cos(theta_rad)
    lead_dlon = (lead_m / (111320.0 * cos_lat)) * _math.sin(theta_rad)
    lead_lat = cur_lat + lead_dlat
    lead_lon = cur_lon + lead_dlon
    cur_t += lead_m / speed_mps
    waypoints.append(Waypoint(
        lat=lead_lat, lon=lead_lon, alt_m=altitude, speed_knots=speed,
        time_offset=timedelta(seconds=cur_t),
    ))
    cur_lat, cur_lon = lead_lat, lead_lon

    # 270° left turn discretised as 6 chords of 45°. Centre is 90° left
    # of the current heading, at distance R.
    n_arc_chords = 6
    chord_deg = 270.0 / n_arc_chords
    # Arc centre (east, north) offsets in metres from the lead waypoint.
    ctr_bearing = start_heading - 90.0
    ctr_rad = _math.radians(ctr_bearing)
    ce_m = R_m * _math.sin(ctr_rad)
    cn_m = R_m * _math.cos(ctr_rad)
    # Aircraft's starting angle around the centre, measured CCW from east:
    # for compass heading θ, math-angle of the aircraft from the centre is
    # (360° − θ). Worked derivation: heading direction in math coords is
    # (90°−θ); centre of a LEFT turn is 90° CCW of that; aircraft lies on
    # the opposite side so its angle from centre is (90°−θ) + 90° + 180°.
    a0_deg = 360.0 - start_heading
    for i in range(1, n_arc_chords + 1):
        a_deg = a0_deg + i * chord_deg   # left turn → angle increases CCW
        a_rad = _math.radians(a_deg)
        e_offset = ce_m + R_m * _math.cos(a_rad)
        n_offset = cn_m + R_m * _math.sin(a_rad)
        arc_lat = lead_lat + n_offset / 111320.0
        arc_lon = lead_lon + e_offset / (111320.0 * cos_lat)
        # Chord length ≈ 2R·sin(chord/2).
        chord_m = 2 * R_m * _math.sin(_math.radians(chord_deg / 2))
        cur_t += chord_m / speed_mps
        waypoints.append(Waypoint(
            lat=arc_lat, lon=arc_lon, alt_m=altitude, speed_knots=speed,
            time_offset=timedelta(seconds=cur_t),
        ))
        cur_lat, cur_lon = arc_lat, arc_lon

    # After the 270° procedure turn, the aircraft is heading ~perpendicular
    # to its original track. Fly to the datum from this position — a gentle
    # crossing rather than a snap reversal.
    d_lat_m = (datum_lat - cur_lat) * 111320.0
    d_lon_m = (datum_lon - cur_lon) * 111320.0 * cos_lat
    seg_m = _math.sqrt(d_lat_m * d_lat_m + d_lon_m * d_lon_m)
    if seg_m > 50:
        cur_t += seg_m / speed_mps
        waypoints.append(Waypoint(
            lat=datum_lat, lon=datum_lon, alt_m=altitude, speed_knots=speed,
            time_offset=timedelta(seconds=cur_t),
        ))
        cur_lat, cur_lon = datum_lat, datum_lon

    # Expanding square: legs (1,1,2,2,3,3,...,N,N), directions rotating
    # N→E→S→W. Each pair of legs steps 1 longer; the spiral grows outward.
    #
    # Leg k (1-indexed): length_steps = ceil(k/2), direction = (k-1) mod 4
    dir_dlat = [+1, 0, -1, 0]   # N E S W
    dir_dlon = [0, +1, 0, -1]
    total_legs = 2 * iterations
    for k in range(1, total_legs + 1):
        length_steps = (k + 1) // 2
        dir_idx = (k - 1) % 4
        d_lat = dir_dlat[dir_idx] * length_steps * step_lat
        d_lon = dir_dlon[dir_idx] * length_steps * step_lon
        new_lat = cur_lat + d_lat
        new_lon = cur_lon + d_lon
        seg_m = _math.sqrt(
            (d_lat * 111320.0) ** 2 +
            (d_lon * 111320.0 * cos_lat) ** 2
        )
        cur_t += seg_m / speed_mps
        waypoints.append(Waypoint(
            lat=new_lat, lon=new_lon, alt_m=altitude, speed_knots=speed,
            time_offset=timedelta(seconds=cur_t),
        ))
        cur_lat, cur_lon = new_lat, new_lon

    # Sentinel waypoint far in the future so is_complete() never fires and
    # the main-loop auto-orbit does not replace the search pattern.
    waypoints.append(Waypoint(
        lat=cur_lat, lon=cur_lon, alt_m=altitude, speed_knots=speed,
        time_offset=timedelta(hours=24),
    ))

    # Give fixed-wing aircraft a real turn radius so the expanding square
    # has rounded corners instead of physics-defying 90° snaps.
    turn_tuple = ENTITY_TYPES.get(entity.entity_type, {}).get("turn")
    turn_params = TurnParams(*turn_tuple) if turn_tuple else None
    return WaypointMovement(
        waypoints=waypoints, scenario_start=sim_time,
        turn_params=turn_params,
    )


@dataclass
class EventDependency:
    """Parsed 'after' field: event_id, phase, and time offset."""
    event_id: str
    phase: str       # "initiate" or "complete"
    offset: timedelta


def parse_after(after) -> EventDependency:
    """Parse an 'after' dependency (object with event, phase, offset)."""
    if isinstance(after, str):
        # Legacy string format: "event_id" or "event_id:phase"
        return EventDependency(event_id=after, phase="initiate", offset=timedelta(0))

    if not isinstance(after, dict):
        raise ValueError(f"Invalid after: expected object, got {type(after)}")

    event_id = after.get("event")
    if not event_id:
        raise ValueError("after.event is required")

    phase = after.get("phase", "initiate")
    offset = timedelta(0)

    offset_str = after.get("offset")
    if offset_str:
        parts = str(offset_str).split(":")
        if len(parts) == 2:
            offset = timedelta(hours=int(parts[0]), minutes=int(parts[1]))
        elif len(parts) == 3:
            offset = timedelta(
                hours=int(parts[0]), minutes=int(parts[1]), seconds=int(parts[2]),
            )

    return EventDependency(event_id=event_id, phase=phase, offset=offset)


@dataclass
class _PendingCompletion:
    """Tracks an in-progress action awaiting movement completion."""
    entity_id: str
    on_complete: str
    on_complete_action: str | None
    source_event: ScenarioEvent
    fired: bool = False


class EventEngine:
    """Processes scenario events with dependency chain resolution."""

    def __init__(
        self,
        events: list[ScenarioEvent],
        entity_store: EntityStore,
        movements: dict[str, Any],
        scenario_start: datetime,
        pending_spawns: dict[str, tuple] | None = None,
    ) -> None:
        self._events = list(events)
        self._entity_store = entity_store
        self._movements = movements
        self._scenario_start = scenario_start
        self._pending_spawns = pending_spawns or {}
        self._fired: list[ScenarioEvent] = []
        self._fired_set: set[int] = set()
        self._pending_completions: list[_PendingCompletion] = []

        # Dependency tracking
        self._initiated_at: dict[str, datetime] = {}   # event_id -> sim_time
        self._completed_at: dict[str, datetime] = {}   # event_id -> sim_time
        self._event_index: dict[str, int] = {}          # event_id -> index

        # Pre-parse dependencies
        self._parsed_deps: dict[int, EventDependency] = {}
        for i, event in enumerate(self._events):
            if event.id:
                self._event_index[event.id] = i
            if event.after:
                self._parsed_deps[i] = parse_after(event.after)

    def tick(self, sim_time: datetime) -> list[ScenarioEvent]:
        """Fire events whose time/dependencies are satisfied.
        Uses cascading resolution so zero-offset chains fire in one tick."""
        elapsed = sim_time - self._scenario_start
        newly_fired = []

        # Cascading loop — re-scan until no new events fire
        changed = True
        while changed:
            changed = False
            for i, event in enumerate(self._events):
                if i in self._fired_set:
                    continue

                ready = self._is_ready(event, i, elapsed, sim_time)
                if ready:
                    self._fire_event(event, sim_time)
                    self._fired.append(event)
                    self._fired_set.add(i)
                    newly_fired.append(event)
                    changed = True

                    # Record initiation time
                    if event.id:
                        self._initiated_at[event.id] = sim_time
                    logger.info(f"[{event.event_type}] {event.description[:80]}")

                    # Register completion tracking
                    if event.on_complete or event.on_complete_action:
                        self._register_completion(event)

        # Check pending completions
        completion_events = self._check_completions(sim_time)
        newly_fired.extend(completion_events)

        return newly_fired

    def _is_ready(
        self, event: ScenarioEvent, index: int,
        elapsed: timedelta, sim_time: datetime,
    ) -> bool:
        """Check if an event's firing conditions are met."""
        has_time = event.time_offset is not None
        has_after = index in self._parsed_deps

        if not has_time and not has_after:
            # No trigger at all — fire immediately (shouldn't happen)
            return True

        if has_after:
            dep = self._parsed_deps[index]
            dep_satisfied, dep_time = self._check_dependency(dep)
            if not dep_satisfied or dep_time is None:
                return False
            fire_at = dep_time + dep.offset
            if sim_time < fire_at:
                return False
            # If also has time, use it as minimum guard
            if has_time and event.time_offset > elapsed:
                return False
            return True

        # Time-only event
        return has_time and event.time_offset <= elapsed

    def _check_dependency(self, dep: EventDependency) -> tuple[bool, datetime | None]:
        """Check if a dependency is satisfied. Returns (satisfied, timestamp)."""
        if dep.phase == "initiate":
            ts = self._initiated_at.get(dep.event_id)
            return (ts is not None, ts)
        elif dep.phase == "complete":
            ts = self._completed_at.get(dep.event_id)
            return (ts is not None, ts)
        return False, None

    def _register_completion(self, event: ScenarioEvent) -> None:
        """Register an event for completion tracking."""
        target_ids = []
        if event.actionee:
            target_ids.append(event.actionee)
        if event.targets:
            target_ids.extend(event.targets)
        # Track the first target — for multi-target events, the primary
        # entity's arrival is what matters
        if target_ids:
            self._pending_completions.append(_PendingCompletion(
                entity_id=target_ids[0],
                on_complete=event.on_complete,
                on_complete_action=event.on_complete_action,
                source_event=event,
            ))

    def _check_completions(self, sim_time: datetime) -> list[ScenarioEvent]:
        """Check if any tracked movements have completed."""
        completed = []
        for pc in self._pending_completions:
            if pc.fired:
                continue
            movement = self._movements.get(pc.entity_id)
            if not movement:
                continue

            is_done = False
            if hasattr(movement, 'is_complete'):
                is_done = movement.is_complete(sim_time)
            if hasattr(movement, 'is_intercepted') and not is_done:
                is_done = movement.is_intercepted()

            if is_done:
                pc.fired = True
                entity = self._entity_store.get_entity(pc.entity_id)
                elapsed = sim_time - self._scenario_start

                # Record completion time for dependency chain
                source_id = pc.source_event.id
                if source_id:
                    self._completed_at[source_id] = sim_time

                # Generate completion event (if on_complete message provided)
                if pc.on_complete:
                    completion_event = ScenarioEvent(
                        time_offset=elapsed,
                        event_type="ARRIVAL" if not hasattr(movement, 'is_intercepted')
                                   else "INTERCEPT",
                        description=pc.on_complete,
                        on_initiate=pc.on_complete,
                        severity=pc.source_event.severity,
                        target=pc.entity_id,
                        source=pc.entity_id,
                        alert_agencies=list(pc.source_event.alert_agencies),
                        position={
                            "lat": entity.position.latitude,
                            "lon": entity.position.longitude,
                        } if entity else None,
                    )
                    completed.append(completion_event)
                    self._fired.append(completion_event)
                    logger.info(f"[COMPLETION] {pc.entity_id}: {pc.on_complete[:80]}")
                else:
                    logger.info(f"[COMPLETION] {pc.entity_id} action complete (no message)")

                # Apply on_complete_action if set
                if pc.on_complete_action and entity:
                    self._apply_complete_action(
                        pc.on_complete_action, entity, pc.entity_id,
                        pc.source_event, sim_time,
                    )

        return completed

    def _apply_complete_action(
        self, action: str, entity: Any, entity_id: str,
        source_event: ScenarioEvent, sim_time: datetime,
    ) -> None:
        """Apply a follow-on action after movement completion."""
        # The follow-on now drives the entity; nothing comes after it.
        entity.current_action = action
        entity.next_action = None

        if action == "hold_station" or action == "alongside":
            # alongside == hold_station with a hold_target; same movement class.
            # For on_complete_action, hold_target may be the source event's target
            # (intercept-complete → stay alongside that target) or an explicit
            # hold_target override in metadata.
            hold_target = (
                source_event.metadata.get("hold_target")
                or (source_event.target if action == "alongside" else None)
            )
            self._movements[entity_id] = HoldStationMovement(
                lat=entity.position.latitude,
                lon=entity.position.longitude,
                alt_m=entity.position.altitude_m,
                heading_deg=entity.heading_deg,
                target_entity_id=hold_target,
                entity_store=self._entity_store,
            )
            entity.speed_knots = 0
            entity.status = EntityStatus.ACTIVE

        elif action == "orbit":
            from simulator.movement.orbit import tangent_orbit_params
            orbit_center = source_event.metadata.get("orbit_center")
            radius_nm = source_event.metadata.get("orbit_radius_nm", 1.0)
            if not source_event.metadata.get("orbit_radius_nm"):
                logger.debug(f"on_complete orbit for {entity_id}: using default radius/speed (not specified in source event)")
            orbit_speed = source_event.metadata.get(
                "orbit_speed",
                _get_action_speed(entity.entity_type, "orbit") or 40,
            )
            direction = source_event.metadata.get("orbit_direction", "CW")
            altitude = source_event.metadata.get(
                "altitude_m",
                _get_action_altitude(entity.entity_type, "orbit") or entity.position.altitude_m,
            )

            # Tangent-entry fix — see docs/scenario-schema.md for the history.
            # Without this, an aircraft finishing a transit and snapping to
            # orbit teleports onto the orbit circle and instantly changes
            # heading by ~90°. tangent_orbit_params keeps the aircraft at
            # its current position and heading and derives the orbit centre
            # so the current heading is tangent to the circle. We keep
            # target tracking so the orbit follows a moving target — the
            # centre is stored as an OFFSET from target (target_offset_lat
            # / _lon below), recomputed each tick in OrbitMovement.
            target_lat = entity.position.latitude
            target_lon = entity.position.longitude
            target_id = None
            if orbit_center:
                center_entity = self._entity_store.get_entity(orbit_center)
                if center_entity:
                    target_lat = center_entity.position.latitude
                    target_lon = center_entity.position.longitude
                    target_id = orbit_center

            radius_m = radius_nm * 1852
            c_lat, c_lon, init_angle = tangent_orbit_params(
                entity.position.latitude, entity.position.longitude,
                entity.heading_deg,
                radius_m,
                direction=direction,
            )
            # Offset of tangent centre from the nominal target — applied
            # every tick so a moving target drags the orbit with it.
            target_offset_lat = c_lat - target_lat
            target_offset_lon = c_lon - target_lon

            self._movements[entity_id] = OrbitMovement(
                center_lat=c_lat,
                center_lon=c_lon,
                altitude_m=altitude,
                speed_knots=orbit_speed,
                orbit_radius_m=radius_m,
                initial_heading=init_angle,
                direction=direction,
                target_entity_id=target_id,
                entity_store=self._entity_store,
                target_offset_lat=target_offset_lat,
                target_offset_lon=target_offset_lon,
            )
            entity.speed_knots = orbit_speed
            entity.status = EntityStatus.ACTIVE

        elif action == "rtb":
            home = entity.metadata.get("home_base")
            if isinstance(home, dict):
                dest_lat, dest_lon = home["lat"], home["lon"]
            elif entity.initial_position:
                dest_lat = entity.initial_position.latitude
                dest_lon = entity.initial_position.longitude
            else:
                return
            cruise = _get_action_speed(entity.entity_type, "transit") or 20
            self._movements[entity_id] = TransitMovement(
                origin_lat=entity.position.latitude,
                origin_lon=entity.position.longitude,
                dest_lat=dest_lat, dest_lon=dest_lon,
                speed_knots=cruise, start_time=sim_time,
                origin_alt_m=entity.position.altitude_m,
            )
            entity.speed_knots = cruise
            entity.status = EntityStatus.RTB

        elif action == "search_pattern":
            self._movements[entity_id] = _build_search_pattern(
                source_event.metadata, entity, sim_time, self._entity_store,
            )
            entity.speed_knots = float(source_event.metadata.get(
                "search_speed",
                _get_action_speed(entity.entity_type, "orbit") or 140,
            ))
            entity.status = EntityStatus.ACTIVE

        self._entity_store.upsert_entity(entity)

    def _fire_event(self, event: ScenarioEvent, sim_time: datetime) -> None:
        """Execute an event's action on its target entities."""
        # Handle reclassification
        reclassify = event.metadata.get("reclassify")
        if reclassify:
            self._apply_reclassify(reclassify)

        # Handle SIDC/callsign overrides on events
        sidc_override = event.metadata.get("sidc_override")
        callsign_override = event.metadata.get("callsign_override")
        if sidc_override or callsign_override:
            target_ids = []
            if event.actionee:
                target_ids.append(event.actionee)
            if event.targets:
                target_ids.extend(event.targets)
            for tid in target_ids:
                e = self._entity_store.get_entity(tid)
                if e:
                    if sidc_override:
                        e.sidc = sidc_override
                    if callsign_override:
                        e.callsign = callsign_override
                    self._entity_store.upsert_entity(e)

        # Handle AIS_LOSS
        if event.event_type == "AIS_LOSS" and event.actionee:
            entity = self._entity_store.get_entity(event.actionee)
            if entity:
                entity.metadata["ais_active"] = False
                self._entity_store.upsert_entity(entity)

        if not event.action:
            return

        # Collect target IDs
        target_ids = []
        if event.actionee:
            target_ids.append(event.actionee)
        if event.targets:
            target_ids.extend(event.targets)

        for target_id in target_ids:
            entity = self._entity_store.get_entity(target_id)
            if not entity:
                # Check pending spawns (embarked or deferred entities)
                if target_id in self._pending_spawns:
                    entity, _ = self._pending_spawns.pop(target_id)
                    self._entity_store.add_entity(entity)
                    logger.info(f"Spawned pending entity: {target_id}")
                else:
                    logger.warning(f"Event actionee '{target_id}' not found in store")
                    continue
            self._apply_action(event, entity, target_id, sim_time)

    def _apply_action(
        self, event: ScenarioEvent, entity: Any,
        target_id: str, sim_time: datetime,
    ) -> None:
        """Apply an event action to a specific entity."""
        action = event.action
        # Record the action chain for the detail-panel display. The status
        # enum is still set by each branch below.
        entity.current_action = action
        entity.next_action = event.on_complete_action
        # Snapshot the driving event so the COP detail panel can show
        # who/what/why (e.g. "intercept → IFF-005, on_complete hold_station").
        # `after` is normalised to a human-readable string.
        after_str = None
        if isinstance(event.after, dict):
            src = event.after.get("event")
            phase = event.after.get("phase", "initiate")
            offset = event.after.get("offset")
            after_str = f"{src}:{phase}" if src else None
            if after_str and offset:
                after_str = f"{after_str} +{offset}"
        elif isinstance(event.after, str):
            after_str = event.after
        # Resolve the target's callsign so the detail panel can show
        # "Target Name: Unknown Mothership" alongside "Target ID: IFF-005".
        target_name = None
        if event.target:
            t_ent = self._entity_store.get_entity(event.target)
            if t_ent:
                target_name = t_ent.callsign
        entity.current_event = {
            "id": event.id,
            "description": event.description,
            "after": after_str,
            "type": event.event_type,
            "action": action,
            "target": event.target,
            "target_name": target_name,
            "on_complete_action": event.on_complete_action,
        }

        # === NEW V2 ACTIONS ===

        if action == "transit":
            if not event.destination:
                logger.warning(f"Transit action for {target_id} missing destination")
                return
            speed = event.metadata.get(
                "speed",
                _get_action_speed(entity.entity_type, "transit") or 20,
            )
            altitude = event.metadata.get(
                "altitude_m",
                _get_action_altitude(entity.entity_type, "transit") or entity.position.altitude_m,
            )
            self._movements[target_id] = TransitMovement(
                origin_lat=entity.position.latitude,
                origin_lon=entity.position.longitude,
                dest_lat=event.destination["lat"],
                dest_lon=event.destination["lon"],
                speed_knots=speed, start_time=sim_time,
                origin_alt_m=entity.position.altitude_m,
                dest_alt_m=altitude,
            )
            entity.status = EntityStatus.RESPONDING
            entity.speed_knots = speed

        elif action == "orbit":
            orbit_center_id = event.metadata.get("orbit_center")
            center_lat = entity.position.latitude
            center_lon = entity.position.longitude
            if orbit_center_id:
                center_entity = self._entity_store.get_entity(orbit_center_id)
                if center_entity:
                    center_lat = center_entity.position.latitude
                    center_lon = center_entity.position.longitude
            else:
                center_lat = event.metadata.get("orbit_center_lat", center_lat)
                center_lon = event.metadata.get("orbit_center_lon", center_lon)

            radius_nm = event.metadata.get("orbit_radius_nm", 1.0)
            orbit_speed = event.metadata.get(
                "orbit_speed",
                _get_action_speed(entity.entity_type, "orbit") or 40,
            )
            direction = event.metadata.get("orbit_direction", "CW")
            altitude = event.metadata.get(
                "altitude_m",
                _get_action_altitude(entity.entity_type, "orbit") or entity.position.altitude_m,
            )
            initial_heading = _bearing_from_center(
                center_lat, center_lon,
                entity.position.latitude, entity.position.longitude,
            )
            self._movements[target_id] = OrbitMovement(
                center_lat=center_lat, center_lon=center_lon,
                altitude_m=altitude, speed_knots=orbit_speed,
                orbit_radius_m=radius_nm * 1852,
                initial_heading=initial_heading,
                direction=direction,
                target_entity_id=orbit_center_id,
                entity_store=self._entity_store,
            )
            entity.status = EntityStatus.ACTIVE
            entity.speed_knots = orbit_speed

        elif action == "hold_station":
            hold_target = event.metadata.get("hold_target")
            self._movements[target_id] = HoldStationMovement(
                lat=entity.position.latitude,
                lon=entity.position.longitude,
                alt_m=entity.position.altitude_m,
                heading_deg=entity.heading_deg,
                target_entity_id=hold_target,
                entity_store=self._entity_store,
            )
            entity.status = EntityStatus.ACTIVE
            entity.speed_knots = 0

        elif action == "escape":
            bearing = event.metadata.get("bearing_deg")
            if bearing is None:
                logger.warning(f"Escape action for {target_id} missing bearing_deg")
                return
            speed = event.metadata.get(
                "speed", _get_max_speed(entity.entity_type),
            )
            duration = event.metadata.get("duration_min")
            self._movements[target_id] = EscapeMovement(
                start_lat=entity.position.latitude,
                start_lon=entity.position.longitude,
                bearing_deg=bearing, speed_knots=speed,
                start_time=sim_time,
                alt_m=entity.position.altitude_m,
                duration_min=duration,
            )
            entity.status = EntityStatus.ACTIVE
            entity.speed_knots = speed

        elif action == "approach":
            approach_target_id = event.metadata.get("approach_target")
            dest_lat = entity.position.latitude
            dest_lon = entity.position.longitude
            if approach_target_id:
                target_entity = self._entity_store.get_entity(approach_target_id)
                if target_entity:
                    dest_lat = target_entity.position.latitude
                    dest_lon = target_entity.position.longitude
            elif event.destination:
                dest_lat = event.destination["lat"]
                dest_lon = event.destination["lon"]

            initial_speed = event.metadata.get(
                "speed",
                _get_action_speed(entity.entity_type, "transit") or 20,
            )
            final_speed = event.metadata.get("final_speed", 2)
            approach_dist = event.metadata.get("approach_distance_nm", 1.0)

            self._movements[target_id] = ApproachMovement(
                start_lat=entity.position.latitude,
                start_lon=entity.position.longitude,
                dest_lat=dest_lat, dest_lon=dest_lon,
                initial_speed_knots=initial_speed,
                final_speed_knots=final_speed,
                approach_distance_nm=approach_dist,
                start_time=sim_time,
                alt_m=entity.position.altitude_m,
                target_entity_id=approach_target_id,
                entity_store=self._entity_store,
            )
            entity.status = EntityStatus.RESPONDING
            entity.speed_knots = initial_speed

        elif action == "rtb":
            home = entity.metadata.get("home_base")
            if isinstance(home, dict):
                dest_lat, dest_lon = home["lat"], home["lon"]
            elif entity.initial_position:
                dest_lat = entity.initial_position.latitude
                dest_lon = entity.initial_position.longitude
            else:
                logger.warning(f"RTB for {target_id}: no home_base or initial_position")
                return
            cruise = _get_action_speed(entity.entity_type, "transit") or 20
            self._movements[target_id] = TransitMovement(
                origin_lat=entity.position.latitude,
                origin_lon=entity.position.longitude,
                dest_lat=dest_lat, dest_lon=dest_lon,
                speed_knots=cruise, start_time=sim_time,
                origin_alt_m=entity.position.altitude_m,
            )
            entity.status = EntityStatus.RTB
            entity.speed_knots = cruise

        elif action == "disembark":
            # Personnel-only. The disembarked entity is teleported to its
            # carrier's current position and given a HoldStationMovement that
            # tracks that carrier — so it rides the carrier as it moves.
            #
            # Carrier resolution order:
            #   1. event.metadata.onto — named transfer target (e.g. boarders
            #      stepping from their skiff onto the tanker)
            #   2. entity.metadata.embarked_on — the original carrier
            onto_id = event.metadata.get("onto")
            carrier_id = onto_id or entity.metadata.get("embarked_on")
            if carrier_id:
                carrier = self._entity_store.get_entity(carrier_id)
                if carrier:
                    entity.position = Position(
                        latitude=carrier.position.latitude,
                        longitude=carrier.position.longitude,
                        altitude_m=carrier.position.altitude_m,
                    )
                    entity.heading_deg = carrier.heading_deg
                    # Always attach a HoldStationMovement so the disembarked
                    # entity follows its carrier.
                    self._movements[target_id] = HoldStationMovement(
                        lat=entity.position.latitude,
                        lon=entity.position.longitude,
                        alt_m=entity.position.altitude_m,
                        heading_deg=entity.heading_deg,
                        target_entity_id=carrier_id,
                        entity_store=self._entity_store,
                    )
                    # Record the new carrier so subsequent events / re-embarks
                    # see the right entity.
                    entity.metadata["embarked_on"] = carrier_id
            entity.status = EntityStatus.ACTIVE

        # === LEGACY ACTIONS (backward compatible) ===

        elif action == "intercept":
            if not event.target:
                logger.warning(f"Intercept event for {target_id} missing target")
                return
            entity.status = EntityStatus.INTERCEPTING

            existing = self._movements.get(target_id)
            if existing and isinstance(existing, WaypointMovement) and len(existing._waypoints) > 2:
                logger.info(f"[intercept] {target_id} has explicit waypoints — movement preserved")
            else:
                speed = event.metadata.get(
                    "speed",
                    _get_action_speed(entity.entity_type, "intercept") or _get_max_speed(entity.entity_type),
                )
                # Resolve intercept radius. Explicit intercept_radius_nm on
                # the event wins; otherwise, if on_complete_action is an
                # orbit with orbit_radius_nm set, sync to that to avoid a
                # radial snap at handoff.
                intercept_kwargs = {}
                if event.metadata.get("intercept_radius_nm") is not None:
                    intercept_kwargs["intercept_radius_m"] = (
                        event.metadata["intercept_radius_nm"] * 1852
                    )
                elif (event.on_complete_action == "orbit"
                        and event.metadata.get("orbit_radius_nm") is not None):
                    orbit_radius_m = event.metadata["orbit_radius_nm"] * 1852
                    intercept_kwargs["intercept_radius_m"] = orbit_radius_m
                # Fixed-wing aircraft can't come to a full stop — force a
                # min_speed so the intercept movement orbits the target at
                # that speed instead of stalling at 0 kn when it arrives.
                if entity.domain.value == "AIR":
                    legacy = ENTITY_TYPES.get(entity.entity_type, {})
                    min_speed = legacy.get("speed_range", (0, 0))[0]
                else:
                    min_speed = 0
                self._movements[target_id] = InterceptMovement(
                    entity_speed_knots=speed,
                    target_entity_id=event.target,
                    entity_store=self._entity_store,
                    pursuer_entity_id=target_id,
                    min_speed_knots=min_speed,
                    **intercept_kwargs,
                )
                entity.speed_knots = speed

        elif action == "pursue":
            # Legacy alias — redirect to intercept
            event_copy = event
            event_copy_action = "intercept"
            entity.status = EntityStatus.INTERCEPTING
            if event.target:
                speed = event.metadata.get(
                    "speed",
                    _get_action_speed(entity.entity_type, "intercept") or _get_max_speed(entity.entity_type),
                )
                self._movements[target_id] = InterceptMovement(
                    entity_speed_knots=speed,
                    target_entity_id=event.target,
                    entity_store=self._entity_store,
                    pursuer_entity_id=target_id,
                    min_speed_knots=0,
                )
                entity.speed_knots = speed

        elif action in ("deploy", "respond"):
            entity.status = EntityStatus.RESPONDING
            if event.destination:
                existing = self._movements.get(target_id)
                if existing and isinstance(existing, WaypointMovement) and len(existing._waypoints) > 2:
                    logger.info(f"[{action}] {target_id} has explicit waypoints — movement preserved")
                else:
                    speed = event.metadata.get(
                        "speed",
                        _get_action_speed(entity.entity_type, "transit") or 20,
                    )
                    self._movements[target_id] = TransitMovement(
                        origin_lat=entity.position.latitude,
                        origin_lon=entity.position.longitude,
                        dest_lat=event.destination["lat"],
                        dest_lon=event.destination["lon"],
                        speed_knots=speed, start_time=sim_time,
                        origin_alt_m=entity.position.altitude_m,
                    )
                    entity.speed_knots = speed

        elif action in ("search_area", "patrol"):
            entity.status = EntityStatus.ACTIVE

        elif action == "search_pattern":
            self._movements[target_id] = _build_search_pattern(
                event.metadata, entity, sim_time, self._entity_store,
            )
            entity.speed_knots = float(event.metadata.get(
                "search_speed",
                _get_action_speed(entity.entity_type, "orbit") or 140,
            ))
            entity.status = EntityStatus.ACTIVE

        elif action == "drop_sonobuoy":
            # Drop a stationary SONOBUOY entity at the actionee's current
            # position. Auto-incrementing IDs as SONOBUOY-001, 002, ...
            # Metadata: sonobuoy_id (optional override), channel (sonobuoy
            # radio channel, optional for display).
            from simulator.scenario.loader import ENTITY_TYPES
            sb_id = event.metadata.get("sonobuoy_id")
            if not sb_id:
                n = 1 + sum(
                    1 for e in self._entity_store.get_all_entities()
                    if e.entity_id.startswith("SONOBUOY-")
                )
                sb_id = f"SONOBUOY-{n:03d}"
            td = ENTITY_TYPES.get("SONOBUOY", {})
            sb = Entity(
                entity_id=sb_id,
                entity_type="SONOBUOY",
                domain=td.get("domain", Domain.MARITIME),
                agency=td.get("agency", Agency.RMAF),
                callsign=event.metadata.get("callsign", sb_id),
                position=Position(
                    latitude=entity.position.latitude,
                    longitude=entity.position.longitude,
                    altitude_m=0.0,
                ),
                heading_deg=0.0,
                speed_knots=0.0,
                status=EntityStatus.ACTIVE,
                sidc=td.get("sidc", "10033500001302000000"),
                metadata={
                    "dropped_by": entity.entity_id,
                    "channel": event.metadata.get("channel"),
                    "drop_time": sim_time.isoformat(),
                },
            )
            self._entity_store.upsert_entity(sb)
            logger.info(f"Sonobuoy dropped: {sb_id} at "
                        f"({sb.position.latitude:.4f}, {sb.position.longitude:.4f}) "
                        f"by {entity.entity_id}")

        elif action in ("lockdown", "secure"):
            entity.status = EntityStatus.ACTIVE
            entity.speed_knots = 0
            if target_id in self._movements:
                del self._movements[target_id]

        elif action == "activate":
            entity.status = EntityStatus.ACTIVE

        elif action == "escort_to_port":
            entity.status = EntityStatus.ACTIVE
            sandakan = {"lat": 5.84, "lon": 118.105}
            escort_speed = (_get_action_speed(entity.entity_type, "escort")
                           or _get_max_speed(entity.entity_type) * 0.5)
            self._movements[target_id] = TransitMovement(
                origin_lat=entity.position.latitude,
                origin_lon=entity.position.longitude,
                dest_lat=sandakan["lat"], dest_lon=sandakan["lon"],
                speed_knots=escort_speed, start_time=sim_time,
                origin_alt_m=entity.position.altitude_m,
            )
            entity.speed_knots = escort_speed

        elif action == "reclassify":
            new_type = event.metadata.get("new_type")
            if new_type:
                self._apply_reclassify({"targets": [target_id], "new_type": new_type})
            return

        elif action == "alongside":
            # Maritime-only: come alongside target, locking in the current
            # geographic offset so the entity rides the target as it moves.
            hold_target = event.target or event.metadata.get("hold_target")
            self._movements[target_id] = HoldStationMovement(
                lat=entity.position.latitude,
                lon=entity.position.longitude,
                alt_m=entity.position.altitude_m,
                heading_deg=entity.heading_deg,
                target_entity_id=hold_target,
                entity_store=self._entity_store,
            )
            entity.speed_knots = 0
            entity.status = EntityStatus.ACTIVE

        elif action == "boarding":
            # DEPRECATED — use `alongside` for vessel-to-vessel approach, or
            # `disembark` (with optional `onto:`) for personnel transfer.
            logger.warning(
                f"Event action 'boarding' is deprecated (entity {target_id}). "
                f"Use 'alongside' for vessels or 'disembark onto' for personnel."
            )
            entity.status = EntityStatus.ACTIVE

        else:
            logger.debug(f"Unhandled action '{action}' for {target_id}")
            entity.status = EntityStatus.ACTIVE

        self._entity_store.upsert_entity(entity)

    def _apply_reclassify(self, reclassify: dict) -> None:
        """Change entity type for specified targets."""
        target_ids = reclassify.get("targets", [])
        new_type = reclassify.get("new_type")
        if not new_type or not target_ids:
            return

        type_def = ENTITY_TYPES.get(new_type)
        if not type_def:
            logger.warning(f"Reclassify: unknown entity type '{new_type}'")
            return

        from simulator.scenario.loader import get_default_sidc
        for target_id in target_ids:
            entity = self._entity_store.get_entity(target_id)
            if not entity:
                continue
            old_type = entity.entity_type
            entity.entity_type = new_type
            # Prefer the 20-char 2525D SIDC so the COP can decode it.
            new_sidc = get_default_sidc(new_type)
            if new_sidc:
                entity.sidc = new_sidc
            self._entity_store.upsert_entity(entity)
            logger.info(f"Reclassified {target_id}: {old_type} -> {new_type}")

    def reset(self) -> None:
        """Reset all fired events, pending completions, and dependency state."""
        self._fired.clear()
        self._fired_set.clear()
        self._pending_completions.clear()
        self._initiated_at.clear()
        self._completed_at.clear()

    def get_fired_events(self) -> list[ScenarioEvent]:
        return list(self._fired)

    def get_upcoming_events(
        self, window: timedelta | None = None,
    ) -> list[ScenarioEvent]:
        upcoming = [
            e for i, e in enumerate(self._events) if i not in self._fired_set
        ]
        if window and self._fired:
            last_time = self._fired[-1].time_offset
            if last_time is not None:
                upcoming = [e for e in upcoming
                           if e.time_offset is not None and e.time_offset <= last_time + window]
        return upcoming

    @property
    def is_complete(self) -> bool:
        return len(self._fired_set) == len(self._events)

    @property
    def total_events(self) -> int:
        return len(self._events)
