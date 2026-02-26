"""
Main entry point for the Edge C2 Simulator.

Loads a scenario, initializes all components, and runs the simulation
loop. Each tick: advance clock, update all entity positions via their
movement strategies, fire events, push updates through transport adapters.
"""

import asyncio
import json
import logging
import os
import signal
from datetime import datetime, timezone

import click
import yaml

from simulator.core.clock import SimulationClock
from simulator.core.entity_store import EntityStore
from simulator.domains.aviation import AviationSimulator
from simulator.domains.ground_vehicle import GroundVehicleSimulator
from simulator.domains.maritime import MaritimeSimulator
from simulator.domains.personnel import PersonnelSimulator
from simulator.movement.noise import PositionNoise
from simulator.movement.terrain import validate_position, find_nearest_valid_point
from simulator.scenario.event_engine import EventEngine
from simulator.scenario.loader import ScenarioLoader, ScenarioState
from simulator.transport.console_adapter import ConsoleAdapter
from simulator.transport.websocket_adapter import WebSocketAdapter
from scripts.health_server import HealthServer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

VERSION = "0.1.0"


async def simulation_loop(
    scenario_state: ScenarioState,
    clock: SimulationClock,
    entity_store: EntityStore,
    event_engine: EventEngine,
    adapters: list,
    tick_interval_s: float,
    stop_event: asyncio.Event,
    domain_simulators: list | None = None,
) -> None:
    """Core simulation loop — runs until scenario complete or user stops."""
    # Noise generators per entity (keyed by domain)
    noise_cache: dict[str, PositionNoise] = {}
    tick_count = 0
    domain_sims = domain_simulators or []

    while not stop_event.is_set():
        if not clock.is_running:
            await asyncio.sleep(0.1)
            continue

        sim_time = clock.get_sim_time()

        # Update all entity positions via movement strategies
        for entity_id, movement in list(scenario_state.movements.items()):
            entity = entity_store.get_entity(entity_id)
            if not entity:
                continue

            state = movement.get_state(sim_time)

            # Apply noise
            domain_key = entity.domain.value
            if domain_key not in noise_cache:
                noise_cache[domain_key] = PositionNoise.for_domain(domain_key)
            noisy_state = noise_cache[domain_key].apply(state)

            # Terrain validation: ensure entity is on correct surface
            final_lat = noisy_state.lat
            final_lon = noisy_state.lon
            skip_terrain = entity.metadata.get("skip_terrain_check", False)
            if not skip_terrain and domain_key in ("MARITIME", "GROUND_VEHICLE", "PERSONNEL"):
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
                entity.metadata.update(noisy_state.metadata_overrides)

            entity_store.upsert_entity(entity)

        # Tick domain simulators
        for domain_sim in domain_sims:
            try:
                domain_sim.tick(sim_time)
            except Exception as e:
                logger.debug(f"Domain sim tick error: {e}")

        # Process events
        fired_events = event_engine.tick(sim_time)
        for event in fired_events:
            for adapter in adapters:
                try:
                    await adapter.push_event(event.to_dict())
                except Exception as e:
                    logger.debug(f"Event push error: {e}")

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

        # Wait for next tick
        await asyncio.sleep(tick_interval_s)


async def run(
    scenario: str | None, speed: float, port: int,
    tick_rate: float, transport: str,
) -> None:
    """Run the simulator."""
    print(f"\nEdge C2 Simulator v{VERSION}")
    print("=" * 40)

    # Parse transport options
    transport_names = [t.strip() for t in transport.split(",")]

    # Load scenario if specified
    scenario_state = None
    event_engine = None

    if scenario:
        print(f"Loading scenario: {scenario}")
        loader = ScenarioLoader()
        scenario_state = loader.load(scenario)

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
    if scenario_state:
        for entity in scenario_state.entities.values():
            store.add_entity(entity)

        event_engine = EventEngine(
            events=scenario_state.events,
            entity_store=store,
            movements=scenario_state.movements,
            scenario_start=scenario_state.start_time,
        )

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
            try:
                with open(overrides_path, "w") as f:
                    json.dump(overrides, f, indent=2)
                logger.info(f"SIDC overrides saved to {overrides_path}")
            except OSError as e:
                logger.error(f"Failed to save SIDC overrides: {e}")

        ws_adapter.set_command_handler("update_sidc", handle_sidc_update)

        async def handle_restart(msg):
            """Reset clock to beginning and re-broadcast snapshot."""
            logger.info("Restart requested by client")
            clock.pause()
            clock.reset()
            # Clear trail and event history
            ws_adapter._trail_history.clear()
            ws_adapter._event_history.clear()
            # Reset all entities to initial positions
            if scenario_state:
                for eid, entity in scenario_state.entities.items():
                    store.upsert_entity(entity)
            # Reset event engine
            if event_engine:
                event_engine.reset()
            clock.start()

        ws_adapter.set_command_handler("restart", handle_restart)
        print(f"WebSocket server on ws://0.0.0.0:{port}")

    if "console" in transport_names:
        print("Console output enabled")

    # Connect adapters
    for adapter in adapters:
        await adapter.connect()

    # Start health server
    health = HealthServer(port=8766)
    health.scenario_name = scenario or "none"
    health.speed = speed
    health.entity_count = store.count
    await health.start()

    # Start clock
    clock.start()
    print(f"\nSimulation starting at {start_time.isoformat()} (speed: {speed}x)")
    print("Press Ctrl+C to stop\n")

    # Setup stop signal
    stop = asyncio.Event()
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)

    # Run simulation loop
    if scenario_state and event_engine:
        tick_interval = 1.0 / tick_rate
        await simulation_loop(
            scenario_state=scenario_state,
            clock=clock,
            entity_store=store,
            event_engine=event_engine,
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
    clock.pause()

    # Summary
    if event_engine:
        elapsed = clock.get_elapsed()
        print(f"Simulation ran for {elapsed.total_seconds() / 60:.1f} simulated minutes")
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
@click.option("--transport", default="ws,console", help="Comma-separated transports (ws,console)")
def main(scenario: str | None, speed: float, port: int, tick_rate: float, transport: str) -> None:
    """Edge C2 Simulator — Multi-domain C2 simulation engine."""
    asyncio.run(run(scenario, speed, port, tick_rate, transport))


if __name__ == "__main__":
    main()
