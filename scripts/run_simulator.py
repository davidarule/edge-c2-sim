"""
Main entry point for the Edge C2 Simulator.

Loads a scenario, initializes all components, and runs the simulation
loop. Each tick: advance clock, update all entity positions via their
movement strategies, fire events, push updates through transport adapters.
"""

import asyncio
import json
import logging
import math
import os
import signal
from datetime import datetime, timedelta, timezone
from pathlib import Path

import click
import yaml

from simulator.core.clock import SimulationClock
from simulator.core.entity import EntityStatus
from simulator.core.entity_store import EntityStore
from simulator.domains.aviation import AviationSimulator
from simulator.domains.ground_vehicle import GroundVehicleSimulator
from simulator.domains.maritime import MaritimeSimulator
from simulator.domains.personnel import PersonnelSimulator
from simulator.movement.noise import PositionNoise
from simulator.movement.orbit import OrbitMovement, tangent_orbit_params
from simulator.movement.terrain import validate_position, find_nearest_valid_point
from simulator.scenario.event_engine import EventEngine
from simulator.scenario.loader import ENTITY_TYPES, ScenarioLoader, ScenarioState
from simulator.transport.console_adapter import ConsoleAdapter
from simulator.transport.http_forward_adapter import HttpForwardAdapter
from simulator.transport.websocket_adapter import WebSocketAdapter
from scripts.health_server import HealthServer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

VERSION = "0.1.0"


async def simulation_loop(
    sim_context: dict,
    clock: SimulationClock,
    entity_store: EntityStore,
    adapters: list,
    tick_interval_s: float,
    stop_event: asyncio.Event,
    domain_simulators: list | None = None,
) -> None:
    """Core simulation loop — runs until scenario complete or user stops.

    sim_context is a mutable dict with keys 'scenario_state' and 'event_engine'.
    This ensures the loop always sees the current objects after a reset, since
    handle_restart replaces them in the same dict.

    Physics sub-stepping: at high sim-speeds the per-real-tick sim-time jump
    can get large (e.g. 60 s at 60x with a 1 Hz tick). That's too coarse for
    close-range interactions — fast-moving entities skip past each other and
    InterceptMovement may miss its 500 m radius check. We subdivide the
    sim-time advance into at most MAX_SUBSTEP_S-wide sub-ticks, running
    movement + event dispatch on each sub-tick. Adapter pushes only fire
    once per real tick (after the last sub-step) to avoid flooding the COP.
    """
    # Per-entity noise generators (each entity gets its own instance)
    noise_cache: dict[str, PositionNoise] = {}
    tick_count = 0
    domain_sims = domain_simulators or []
    last_sim_time: datetime | None = None
    MAX_SUBSTEP_S = 5.0

    while not stop_event.is_set():
        if not clock.is_running:
            await asyncio.sleep(0.1)
            last_sim_time = None  # resync on resume so the first tick doesn't replay catch-up
            continue

        tick_start = asyncio.get_event_loop().time()
        target_sim_time = clock.get_sim_time()
        if last_sim_time is None:
            last_sim_time = target_sim_time
        # Clamp the worst case: if something pauses the process (debugger,
        # long GC, etc.) don't suddenly run hundreds of sub-steps.
        sim_delta_s = (target_sim_time - last_sim_time).total_seconds()
        sim_delta_s = max(0.0, min(sim_delta_s, 300.0))
        n_substeps = max(1, int(math.ceil(sim_delta_s / MAX_SUBSTEP_S))) if sim_delta_s > 0 else 1
        substep_s = sim_delta_s / n_substeps if n_substeps > 0 else 0.0
        sub_sim_time = last_sim_time

        # Read current scenario_state and event_engine from shared context
        scenario_state = sim_context["scenario_state"]
        event_engine = sim_context["event_engine"]

        # Spawn deferred entities whose spawn_at time has been reached
        pending = sim_context.get("pending_spawns", {})
        elapsed = clock.get_elapsed()
        spawned = []
        for eid, (entity, spawn_at) in pending.items():
            if spawn_at is None:
                continue  # Embarked entity — spawned by disembark action
            if elapsed >= spawn_at:
                entity_store.add_entity(entity)
                spawned.append(eid)
                logger.info(f"Spawned deferred entity: {eid} at +{elapsed}")
        for eid in spawned:
            del pending[eid]

        # Substep loop: advance sim_time in MAX_SUBSTEP_S-wide increments so
        # high-speed physics (e.g. interceptors crossing each other's radius)
        # stays accurate. Adapter pushes happen once per real tick, after all
        # sub-ticks, to avoid flooding the COP.
        scenario_ended = False
        for _ in range(n_substeps):
            sub_sim_time = sub_sim_time + timedelta(seconds=substep_s)
            sim_time = sub_sim_time

            # Update all entity positions via movement strategies
            for entity_id, movement in list(scenario_state.movements.items()):
                entity = entity_store.get_entity(entity_id)
                if not entity:
                    continue

                state = movement.get_state(sim_time)

                # Per-entity noise instance
                domain_key = entity.domain.value
                if entity_id not in noise_cache:
                    noise_cache[entity_id] = PositionNoise.for_domain(domain_key)
                noisy_state = noise_cache[entity_id].apply(state)

                # Store clean (pre-noise) position for trail rendering
                entity.metadata["track_lat"] = state.lat
                entity.metadata["track_lon"] = state.lon

                # Terrain validation: ensure entity is on correct surface
                final_lat = noisy_state.lat
                final_lon = noisy_state.lon
                if domain_key in ("MARITIME", "GROUND_VEHICLE", "PERSONNEL"):
                    if not validate_position(final_lat, final_lon, domain_key):
                        fix = find_nearest_valid_point(final_lat, final_lon, domain_key)
                        if fix:
                            final_lat, final_lon = fix

                # Update entity position
                entity.update_position(
                    latitude=final_lat,
                    longitude=final_lon,
                    altitude_m=noisy_state.alt_m,
                    heading_deg=noisy_state.heading_deg,
                    speed_knots=noisy_state.speed_knots,
                    course_deg=noisy_state.course_deg,
                )

                # Apply metadata overrides from waypoints
                if noisy_state.metadata_overrides:
                    overrides = noisy_state.metadata_overrides
                    # Special keys update entity-level fields
                    if "sidc" in overrides:
                        entity.sidc = overrides["sidc"]
                    if "callsign" in overrides:
                        entity.callsign = overrides["callsign"]
                    # Rest goes to metadata dict
                    entity.metadata.update(
                        {k: v for k, v in overrides.items() if k not in ("sidc", "callsign")}
                    )

                entity_store.upsert_entity(entity)

                # Fixed-wing aircraft: swap to orbit when movement completes —
                # but ONLY when the aircraft is airborne AND the scenario
                # doesn't already have a scripted follow-on waiting for this
                # movement's completion. If a _PendingCompletion is queued for
                # this entity, the event engine is about to fire the next
                # scripted step (intercept, orbit, rtb, ...); auto-orbiting
                # here would yank the movement out from under it.
                pending_for_entity = any(
                    pc.entity_id == entity_id and not pc.fired
                    for pc in getattr(event_engine, "_pending_completions", [])
                )
                if (
                    domain_key == "AIR"
                    and movement.is_complete(sim_time)
                    and not isinstance(movement, OrbitMovement)
                    and not entity.metadata.get("on_ground", False)
                    and not pending_for_entity
                ):
                    type_def = ENTITY_TYPES.get(entity.entity_type, {})
                    min_speed = type_def.get("speed_range", (0, 100))[0]
                    if min_speed > 0:
                        orbit_radius_m = 3000.0
                        c_lat, c_lon, init_heading = tangent_orbit_params(
                            final_lat, final_lon, noisy_state.heading_deg,
                            orbit_radius_m, direction="CW",
                        )
                        scenario_state.movements[entity_id] = OrbitMovement(
                            center_lat=c_lat,
                            center_lon=c_lon,
                            altitude_m=noisy_state.alt_m,
                            speed_knots=min_speed,
                            orbit_radius_m=orbit_radius_m,
                            initial_heading=init_heading,
                            direction="CW",
                        )
                        logger.info(
                            f"Fixed-wing {entity_id} switching to orbit at "
                            f"{min_speed} kts"
                        )

            # Tick domain simulators
            for domain_sim in domain_sims:
                try:
                    domain_sim.tick(sim_time)
                except Exception as e:
                    logger.debug(f"Domain sim tick error: {e}")

            # Process events (at the sub-step's sim_time — accurate for timing)
            fired_events = event_engine.tick(sim_time)
            for event in fired_events:
                event_dict = event.to_dict()
                event_dict["time"] = sim_time.isoformat()
                for adapter in adapters:
                    try:
                        await adapter.push_event(event_dict)
                    except Exception as e:
                        logger.debug(f"Event push error: {e}")
                # Stop clock on RESOLUTION event (scenario endstate)
                if event.event_type == "RESOLUTION":
                    scenario_ended = True

            if scenario_ended:
                break

        last_sim_time = sub_sim_time

        if scenario_ended:
            clock.pause()
            logger.info("Scenario ENDSTATE — clock paused")

        # Push bulk entity updates
        all_entities = entity_store.get_all_entities()
        if all_entities:
            for adapter in adapters:
                try:
                    await adapter.push_bulk_update(all_entities)
                except Exception as e:
                    logger.debug(f"Bulk update error: {e}")

        tick_count += 1

        # Periodic status (every 30 ticks)
        if tick_count % 30 == 0:
            elapsed = clock.get_elapsed()
            elapsed_min = elapsed.total_seconds() / 60
            logger.info(
                f"Tick {tick_count} | Sim time: +{elapsed_min:.1f}m | "
                f"Entities: {entity_store.count} | "
                f"Events: {len(event_engine.get_fired_events())}/{event_engine.total_events}"
            )

        # Check scenario completion
        if event_engine.is_complete and tick_count > 10:
            # All events fired — check if all movements complete too
            all_done = all(
                hasattr(m, 'is_complete') and m.is_complete(sim_time)
                for m in scenario_state.movements.values()
                if hasattr(m, 'is_complete')
            )
            if all_done:
                logger.info("Scenario complete — all events fired and movements finished")
                break

        # Wait for next tick — subtract processing time to maintain consistent rate
        processing_time = asyncio.get_event_loop().time() - tick_start
        sleep_time = max(0, tick_interval_s - processing_time)
        await asyncio.sleep(sleep_time)


async def run(
    scenario: str | None, speed: float, port: int,
    tick_rate: float, transport: str,
) -> None:
    """Run the simulator."""
    print(f"\nEdge C2 Simulator v{VERSION}")
    print("=" * 40)

    # Parse transport options
    transport_names = [t.strip() for t in transport.split(",")]

    # Shared mutable context — simulation_loop and command handlers both
    # read from this dict, so reset/restart updates are immediately visible
    sim_context: dict = {"scenario_state": None, "event_engine": None, "pending_spawns": {}}

    if scenario:
        print(f"Loading scenario: {scenario}")
        loader = ScenarioLoader()
        sim_context["scenario_state"] = loader.load(scenario)
        scenario_state = sim_context["scenario_state"]

        scenario_count = sum(
            1 for e in scenario_state.entities.values()
            if not e.metadata.get("background")
        )
        bg_count = sum(
            1 for e in scenario_state.entities.values()
            if e.metadata.get("background")
        )
        print(f"Loaded {scenario_count} scenario entities, {bg_count} background entities")
        print(f"Loaded {len(scenario_state.events)} events over "
              f"{scenario_state.duration.total_seconds() / 60:.0f} minutes")

    # Initialize core components
    start_time = scenario_state.start_time if scenario_state else datetime.now(timezone.utc)
    clock = SimulationClock(start_time=start_time, speed=speed)
    store = EntityStore()

    # Populate entity store from scenario
    # - spawn_at entities: deferred until sim clock reaches time
    # - embarked_on entities: deferred until disembark action
    pending_spawns: dict[str, tuple] = {}  # entity_id -> (entity, timedelta)
    embarked_entities: dict[str, str] = {}  # entity_id -> carrier_id
    if scenario_state:
        for entity in scenario_state.entities.values():
            if entity.spawn_at is not None:
                pending_spawns[entity.entity_id] = (entity, entity.spawn_at)
                logger.info(f"Deferred spawn: {entity.entity_id} at +{entity.spawn_at}")
            elif entity.metadata.get("embarked_on"):
                carrier_id = entity.metadata["embarked_on"]
                embarked_entities[entity.entity_id] = carrier_id
                # Store the entity object for later disembark
                pending_spawns[entity.entity_id] = (entity, None)
                logger.info(f"Embarked: {entity.entity_id} on {carrier_id}")
            else:
                store.add_entity(entity)

        sim_context["event_engine"] = EventEngine(
            events=scenario_state.events,
            entity_store=store,
            movements=scenario_state.movements,
            scenario_start=scenario_state.start_time,
            pending_spawns=pending_spawns,
        )
        sim_context["pending_spawns"] = pending_spawns
        sim_context["embarked_entities"] = embarked_entities

    # Initialize domain simulators
    maritime_sim = MaritimeSimulator(store)
    aviation_sim = AviationSimulator(store)
    ground_sim = GroundVehicleSimulator(store)
    personnel_sim = PersonnelSimulator(store)
    domain_simulators = [maritime_sim, aviation_sim, ground_sim, personnel_sim]

    # Initialize transport adapters
    adapters = []
    if "console" in transport_names:
        console = ConsoleAdapter(min_interval=2.0)
        adapters.append(console)
    if "ws" in transport_names:
        duration_s = scenario_state.duration.total_seconds() if scenario_state else 0
        ws_adapter = WebSocketAdapter(
            entity_store=store, clock=clock, port=port,
            scenario_duration_s=duration_s,
        )
        if scenario_state:
            ws_adapter._scenario_center = scenario_state.center
            ws_adapter._scenario_zoom = scenario_state.zoom
            ws_adapter._scenario_file = scenario if scenario else None
            ws_adapter._scenario_meta = {
                "name": scenario_state.name,
                "description": scenario_state.description,
                "duration_min": int(scenario_state.duration.total_seconds() / 60),
                "center": {"lat": scenario_state.center[0], "lon": scenario_state.center[1]},
                "zoom": scenario_state.zoom,
            }
        adapters.append(ws_adapter)

        # Extract planned routes for COP display
        if scenario_state:
            from simulator.movement.waypoint import WaypointMovement
            from simulator.movement.patrol import PatrolMovement

            route_data = {}
            for eid, mov in scenario_state.movements.items():
                if isinstance(mov, WaypointMovement):
                    route_data[eid] = [
                        {"lat": wp.lat, "lon": wp.lon, "alt_m": wp.alt_m}
                        for wp in mov.waypoints
                    ]
                elif isinstance(mov, PatrolMovement):
                    # Extract patrol waypoints from internal movement
                    try:
                        if hasattr(mov, '_waypoint_movement') and mov._waypoint_movement:
                            route_data[eid] = [
                                {"lat": wp.lat, "lon": wp.lon, "alt_m": wp.alt_m}
                                for wp in mov._waypoint_movement.waypoints
                            ]
                    except Exception:
                        pass
            ws_adapter.set_route_data(route_data)

        # Load SIDC overrides from persistent file and attach to ws_adapter
        overrides_path = "config/sidc_overrides.json"
        if os.path.exists(overrides_path):
            try:
                with open(overrides_path) as f:
                    ws_adapter._sidc_overrides = json.load(f)
                logger.info(f"Loaded {len(ws_adapter._sidc_overrides)} SIDC overrides from {overrides_path}")
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(f"Failed to load SIDC overrides: {e}")

        # SIDC update handler: updates entity store + saves to config/sidc_overrides.json
        async def handle_sidc_update(msg):
            entity_type = msg.get("entity_type")
            new_sidc = msg.get("sidc")
            if not entity_type or not new_sidc or len(new_sidc) != 20:
                logger.warning(f"Invalid SIDC update: type={entity_type}, sidc={new_sidc}")
                return
            # Update all entities of this type in the store
            updated = 0
            for entity in store.get_all_entities():
                if entity.entity_type == entity_type:
                    entity.sidc = new_sidc
                    store.upsert_entity(entity)
                    updated += 1
            logger.info(f"SIDC update: {entity_type} -> {new_sidc} ({updated} entities)")
            # Persist to overrides file
            overrides_path = "config/sidc_overrides.json"
            overrides = {}
            if os.path.exists(overrides_path):
                try:
                    with open(overrides_path) as f:
                        overrides = json.load(f)
                except (json.JSONDecodeError, OSError):
                    pass
            overrides[entity_type] = new_sidc
            ws_adapter._sidc_overrides = overrides
            try:
                with open(overrides_path, "w") as f:
                    json.dump(overrides, f, indent=2)
                logger.info(f"SIDC overrides saved to {overrides_path}")
            except OSError as e:
                logger.error(f"Failed to save SIDC overrides: {e}")

        ws_adapter.set_command_handler("update_sidc", handle_sidc_update)

        # Mutable container so handle_load_scenario can swap the active path
        active_scenario = [scenario]

        async def _do_restart(scenario_path, *, switch=False):
            """Core restart logic — reload scenario_path and re-broadcast snapshot.

            On restart (same scenario): AIS replay entities are preserved.
            On switch (different scenario): ALL entities cleared, AIS replay
            feed stopped (background traffic comes from include_entities).
            """
            nonlocal ais_feed
            from simulator.ais.live_feed import AIS_ENTITY_PREFIX

            clock.pause()

            # Load the new scenario FIRST so we can rebase the clock to its
            # start_time before any movement code queries sim_time. Without
            # this rebase, clock._start_time stays at the previous scenario's
            # value and EscapeMovement.get_state() sees negative elapsed on
            # switch — entities dead-reckon on the reverse bearing.
            fresh = None
            if scenario_path:
                fresh = ScenarioLoader().load(scenario_path)
            clock.reset(start_time=fresh.start_time if fresh else None)

            # Always stop AIS feed on restart/switch — may restart below
            if ais_feed:
                ais_feed.stop()
                ais_feed = None
                logger.info("AIS replay feed stopped")

            if switch:
                ws_adapter._trail_history.clear()
            else:
                ais_trails = {
                    eid: trail for eid, trail in ws_adapter._trail_history.items()
                    if eid.startswith(AIS_ENTITY_PREFIX)
                }
                ws_adapter._trail_history.clear()
                ws_adapter._trail_history.update(ais_trails)

            ws_adapter._event_history.clear()
            if fresh is not None:
                sim_context["scenario_state"] = fresh
                with store._lock:
                    store._entities.clear()
                new_pending = {}
                for entity in fresh.entities.values():
                    if entity.spawn_at is not None:
                        new_pending[entity.entity_id] = (entity, entity.spawn_at)
                    else:
                        store.upsert_entity(entity)
                sim_context["pending_spawns"] = new_pending
                sim_context["event_engine"] = EventEngine(
                    events=fresh.events,
                    entity_store=store,
                    movements=fresh.movements,
                    scenario_start=fresh.start_time,
                )
                from simulator.movement.waypoint import WaypointMovement
                from simulator.movement.patrol import PatrolMovement
                route_data = {}
                for eid, mov in fresh.movements.items():
                    if isinstance(mov, WaypointMovement):
                        route_data[eid] = [
                            {"lat": wp.lat, "lon": wp.lon, "alt_m": wp.alt_m}
                            for wp in mov.waypoints
                        ]
                    elif isinstance(mov, PatrolMovement):
                        try:
                            if hasattr(mov, '_waypoint_movement') and mov._waypoint_movement:
                                route_data[eid] = [
                                    {"lat": wp.lat, "lon": wp.lon, "alt_m": wp.alt_m}
                                    for wp in mov._waypoint_movement.waypoints
                                ]
                        except Exception:
                            pass
                ws_adapter.set_route_data(route_data)
                ws_adapter._scenario_center = fresh.center
                ws_adapter._scenario_zoom = fresh.zoom
                ws_adapter._scenario_file = scenario_path if scenario_path else None
                ws_adapter._scenario_duration_s = fresh.duration.total_seconds()
                ws_adapter._scenario_meta = {
                    "name": fresh.name,
                    "description": fresh.description,
                    "duration_min": int(fresh.duration.total_seconds() / 60),
                    "center": {"lat": fresh.center[0], "lon": fresh.center[1]},
                    "zoom": fresh.zoom,
                }
            entities = store.get_all_entities()
            snap_msg = {
                "type": "snapshot",
                "entities": [e.to_dict() for e in entities],
            }
            if ws_adapter._scenario_center:
                snap_msg["center"] = {"lat": ws_adapter._scenario_center[0], "lon": ws_adapter._scenario_center[1]}
            if ws_adapter._scenario_zoom is not None:
                snap_msg["zoom"] = ws_adapter._scenario_zoom
            if ws_adapter._scenario_file is not None:
                snap_msg["scenario_file"] = ws_adapter._scenario_file
            if ws_adapter._scenario_meta is not None:
                snap_msg["scenario_meta"] = ws_adapter._scenario_meta
            if ws_adapter._sidc_overrides:
                snap_msg["sidc_overrides"] = ws_adapter._sidc_overrides
            snapshot = json.dumps(snap_msg)
            await ws_adapter._broadcast(snapshot)
            # Push an immediate clock message so the COP doesn't wait up to 1s
            # for the next periodic broadcast before its sim-time display updates.
            clock_msg = json.dumps({
                "type": "clock",
                "sim_time": clock.get_sim_time().isoformat(),
                "speed": clock.speed,
                "running": clock.is_running,
                "scenario_progress": 0.0,
            })
            await ws_adapter._broadcast(clock_msg)
            if ws_adapter._route_data:
                routes_msg = json.dumps({"type": "routes", "routes": ws_adapter._route_data})
                await ws_adapter._broadcast(routes_msg)

            # Restart AIS feed only if new scenario has no background includes
            if scenario_path:
                fresh_state = sim_context.get("scenario_state")
                if fresh_state and not fresh_state.has_background_includes:
                    _start_ais_feed()
                elif fresh_state and fresh_state.has_background_includes:
                    logger.info("Scenario has background includes — AIS feed not restarted")

        async def handle_restart(msg):
            logger.info("Restart requested by client")
            await _do_restart(active_scenario[0])
            logger.info("Scenario reset complete")

        async def handle_load_scenario(msg):
            """Load a different scenario file and restart the simulation."""
            new_path = msg.get("scenario", "")
            # Security: restrict to config/scenarios/*.yaml only
            if not (new_path.startswith("config/scenarios/") and new_path.endswith(".yaml")):
                logger.warning(f"load_scenario: rejected invalid path: {new_path!r}")
                await ws_adapter._broadcast(json.dumps({
                    "type": "scenario_error",
                    "scenario": new_path,
                    "error": "Invalid scenario path (must be config/scenarios/*.yaml).",
                }))
                return
            is_switch = new_path != active_scenario[0]
            logger.info(f"Loading scenario: {new_path} ({'switch' if is_switch else 'reload'})")
            prev_path = active_scenario[0]
            active_scenario[0] = new_path
            try:
                await _do_restart(new_path, switch=is_switch)
            except Exception as e:
                # Roll back so a subsequent reset targets the last known-good scenario.
                active_scenario[0] = prev_path
                logger.error(f"load_scenario failed: {e}")
                await ws_adapter._broadcast(json.dumps({
                    "type": "scenario_error",
                    "scenario": new_path,
                    "error": str(e),
                }))
                return
            logger.info(f"Scenario {'switched to' if is_switch else 'reloaded'}: {new_path}")

        async def handle_return_to_start(msg):
            """Send an entity back to its initial position."""
            entity_id = msg.get("entity_id")
            if not entity_id:
                logger.warning("return_to_start: missing entity_id")
                return
            entity = store.get_entity(entity_id)
            if not entity or not entity.initial_position:
                logger.warning(f"return_to_start: entity {entity_id} not found or no initial_position")
                return
            # Calculate cruise speed from entity type definition
            type_def = ENTITY_TYPES.get(entity.entity_type, {})
            speed_range = type_def.get("speed_range", (10, 20))
            cruise_speed = sum(speed_range) / 2
            # Build 2-waypoint movement: current position -> initial position
            from simulator.movement.waypoint import Waypoint, WaypointMovement
            from geopy.distance import geodesic as geo_dist
            dist_nm = geo_dist(
                (entity.position.latitude, entity.position.longitude),
                (entity.initial_position.latitude, entity.initial_position.longitude),
            ).nautical
            travel_s = (dist_nm / cruise_speed * 3600) if cruise_speed > 0 else 0
            sim_time = clock.get_sim_time()
            waypoints = [
                Waypoint(
                    lat=entity.position.latitude,
                    lon=entity.position.longitude,
                    alt_m=entity.position.altitude_m,
                    speed_knots=cruise_speed,
                    time_offset=timedelta(0),
                ),
                Waypoint(
                    lat=entity.initial_position.latitude,
                    lon=entity.initial_position.longitude,
                    alt_m=entity.initial_position.altitude_m,
                    speed_knots=cruise_speed,
                    time_offset=timedelta(seconds=travel_s),
                ),
            ]
            movement = WaypointMovement(waypoints, sim_time)
            sim_context["scenario_state"].movements[entity_id] = movement
            entity.status = EntityStatus.RTB
            store.upsert_entity(entity)
            logger.info(
                f"RTS: {entity_id} returning to start ({dist_nm:.1f} nm, "
                f"ETA {travel_s:.0f}s at {cruise_speed:.0f} kts)"
            )

        async def handle_list_scenarios(msg):
            """Scan config/scenarios/ and return available scenario files."""
            scenarios_dir = Path("config/scenarios")
            result = []
            for yaml_file in sorted(scenarios_dir.glob("*.yaml")):
                try:
                    with open(yaml_file) as f:
                        raw = yaml.safe_load(f)
                    # Skip include files (they are entity lists, not scenarios)
                    if not isinstance(raw, dict) or "scenario" not in raw:
                        continue
                    name = raw["scenario"].get("name", yaml_file.stem)
                    result.append({"file": f"config/scenarios/{yaml_file.name}", "name": name})
                except Exception as e:
                    logger.warning(f"list_scenarios: failed to read {yaml_file}: {e}")
            await ws_adapter._broadcast(json.dumps({
                "type": "scenarios_list", "scenarios": result,
            }))
            logger.info(f"list_scenarios: returned {len(result)} scenarios")

        ws_adapter.set_command_handler("return_to_start", handle_return_to_start)
        ws_adapter.set_command_handler("restart", handle_restart)
        ws_adapter.set_command_handler("reset", handle_restart)
        ws_adapter.set_command_handler("load_scenario", handle_load_scenario)
        ws_adapter.set_command_handler("list_scenarios", handle_list_scenarios)
        print(f"WebSocket server on ws://0.0.0.0:{port}")

    if "console" in transport_names:
        print("Console output enabled")

    # HTTP forwarding — enabled via FORWARD_URL env var or --forward-url CLI
    forward_url = os.environ.get("FORWARD_URL", "")
    if forward_url:
        fwd = HttpForwardAdapter(target_url=forward_url)
        adapters.append(fwd)
        print(f"HTTP forwarding -> {forward_url}")

    # Connect adapters
    for adapter in adapters:
        await adapter.connect()

    # Start AIS feed: live (AISStream.io) or replay (captured CSV)
    # Only when the scenario doesn't already provide background entities
    # via include_entities / background_entities YAML config.
    ais_feed = None
    ais_config = {
        "max": int(os.environ.get("AIS_MAX_ENTITIES", "300")),
        "interval": float(os.environ.get("AIS_UPDATE_INTERVAL", "30")),
        "stale": float(os.environ.get("AIS_STALE_SECONDS", "300")),
        "key": os.environ.get("AISSTREAM_API_KEY", ""),
        "replay_dir": os.environ.get("AIS_REPLAY_DIR", "scripts/ais_data"),
        "replay_speed": float(os.environ.get("AIS_REPLAY_SPEED", "1")),
    }

    def _start_ais_feed():
        """Start AIS replay/live feed. Returns the feed instance or None."""
        nonlocal ais_feed
        if "ws" not in transport_names:
            return None
        if os.environ.get("SKIP_BACKGROUND"):
            logger.info("SKIP_BACKGROUND=1 — AIS replay feed not started")
            return None
        replay_pos = None
        if os.path.isdir(ais_config["replay_dir"]):
            csvs = sorted(
                [f for f in os.listdir(ais_config["replay_dir"])
                 if f.startswith("positions_") and f.endswith(".csv")],
                reverse=True,
            )
            if csvs:
                replay_pos = os.path.join(ais_config["replay_dir"], csvs[0])
                replay_static = os.path.join(
                    ais_config["replay_dir"], csvs[0].replace("positions_", "statics_")
                )

        if replay_pos and os.path.exists(replay_pos):
            from simulator.ais.replay_feed import AISReplayFeed
            ais_feed = AISReplayFeed(
                positions_csv=replay_pos,
                statics_csv=replay_static,
                entity_store=store,
                ws_adapter=ws_adapter,
                max_entities=ais_config["max"],
                update_interval_s=ais_config["interval"],
                stale_seconds=ais_config["stale"],
                speed=ais_config["replay_speed"],
            )
            asyncio.create_task(ais_feed.run())
            logger.info(f"AIS replay feed started: {replay_pos} ({ais_config['replay_speed']}x)")
            return ais_feed
        elif ais_config["key"]:
            from simulator.ais.live_feed import AISLiveFeed
            ais_feed = AISLiveFeed(
                api_key=ais_config["key"],
                entity_store=store,
                ws_adapter=ws_adapter,
                max_entities=ais_config["max"],
                update_interval_s=ais_config["interval"],
                stale_seconds=ais_config["stale"],
            )
            asyncio.create_task(ais_feed.run())
            logger.info("AIS live feed started (AISStream.io)")
            return ais_feed
        return None

    has_bg = scenario_state.has_background_includes if scenario_state else False
    if not has_bg:
        _start_ais_feed()
    else:
        logger.info("Scenario has background includes — skipping AIS replay feed")

    # Start health server
    health = HealthServer(port=8766)
    health.scenario_name = scenario or "none"
    health.speed = speed
    health.entity_count = store.count
    await health.start()

    # Clock starts paused — user presses PLAY in COP to begin
    print(f"\nSimulation loaded at {start_time.isoformat()} (speed: {speed}x)")
    print("Paused — press PLAY in COP to start\n")

    # Setup stop signal
    stop = asyncio.Event()
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)

    # Run simulation loop
    if sim_context["scenario_state"] and sim_context["event_engine"]:
        tick_interval = 1.0 / tick_rate
        await simulation_loop(
            sim_context=sim_context,
            clock=clock,
            entity_store=store,
            adapters=adapters,
            tick_interval_s=tick_interval,
            stop_event=stop,
            domain_simulators=domain_simulators,
        )
    else:
        logger.info("No scenario specified — running in standby mode")
        await stop.wait()

    # Cleanup
    print("\nShutting down...")
    if ais_feed:
        ais_feed.stop()
    clock.pause()

    # Summary
    if sim_context["event_engine"]:
        elapsed = clock.get_elapsed()
        print(f"Simulation ran for {elapsed.total_seconds() / 60:.1f} simulated minutes")
        event_engine = sim_context["event_engine"]
        print(f"Events fired: {len(event_engine.get_fired_events())}/{event_engine.total_events}")
    print(f"Entities tracked: {store.count}")

    for adapter in adapters:
        await adapter.disconnect()
    await health.stop()
    print("Simulator stopped")


@click.command()
@click.option("--scenario", "-s", default=None, help="Path to scenario YAML file")
@click.option("--speed", default=1.0, help="Simulation speed multiplier (1, 2, 5, 10, 60)")
@click.option("--port", default=8765, help="WebSocket server port")
@click.option("--tick-rate", default=1.0, help="Ticks per second (real-time)")
@click.option("--transport", default="ws", help="Comma-separated transports (ws,console)")
def main(scenario: str | None, speed: float, port: int, tick_rate: float, transport: str) -> None:
    """Edge C2 Simulator — Multi-domain C2 simulation engine."""
    asyncio.run(run(scenario, speed, port, tick_rate, transport))


if __name__ == "__main__":
    main()
