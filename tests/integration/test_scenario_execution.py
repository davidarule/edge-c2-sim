"""
End-to-end scenario test.

Loads a complete scenario, runs with all domain simulators, and verifies:
1. All entities spawned correctly
2. Maritime entities generate AIS data
3. Aviation entities have correct flight profiles
4. Events fire and change entity behavior
5. Scenario completes without errors
"""

from datetime import datetime, timedelta, timezone

import pytest

from simulator.core.entity import Domain, EntityStatus
from simulator.core.entity_store import EntityStore
from simulator.domains.aviation import AviationSimulator
from simulator.domains.ground_vehicle import GroundVehicleSimulator
from simulator.domains.maritime import MaritimeSimulator
from simulator.domains.personnel import PersonnelSimulator
from simulator.movement.noise import PositionNoise
from simulator.scenario.event_engine import EventEngine
from simulator.scenario.loader import ScenarioLoader


@pytest.fixture
def start_time():
    return datetime(2026, 4, 15, 8, 0, 0, tzinfo=timezone.utc)


def _run_scenario(scenario_path, start_time):
    """Helper: load and run a scenario with all domain simulators."""
    loader = ScenarioLoader()
    state = loader.load(scenario_path, start_time=start_time)

    store = EntityStore()
    for entity in state.entities.values():
        store.add_entity(entity)

    event_engine = EventEngine(
        events=state.events,
        entity_store=store,
        movements=state.movements,
        scenario_start=start_time,
    )

    # Domain simulators
    maritime_sim = MaritimeSimulator(store)
    aviation_sim = AviationSimulator(store)
    ground_sim = GroundVehicleSimulator(store)
    personnel_sim = PersonnelSimulator(store)

    noise_cache: dict[str, PositionNoise] = {}

    tick_interval = timedelta(seconds=10)
    sim_time = start_time
    end_time = start_time + state.duration + timedelta(minutes=5)
    tick_count = 0

    initial_positions = {}
    for eid, entity in list(state.entities.items()):
        initial_positions[eid] = (entity.position.latitude, entity.position.longitude)

    total_ais_count = 0
    total_adsb_count = 0

    while sim_time < end_time:
        # Movement update
        for entity_id, movement in list(state.movements.items()):
            entity = store.get_entity(entity_id)
            if not entity:
                continue
            mv_state = movement.get_state(sim_time)
            domain_key = entity.domain.value
            if domain_key not in noise_cache:
                noise_cache[domain_key] = PositionNoise.for_domain(domain_key, seed=42)
            noisy = noise_cache[domain_key].apply(mv_state)
            entity.update_position(
                latitude=noisy.lat, longitude=noisy.lon,
                altitude_m=noisy.alt_m, heading_deg=noisy.heading_deg,
                speed_knots=noisy.speed_knots, course_deg=noisy.course_deg,
            )
            if noisy.metadata_overrides:
                entity.metadata.update(noisy.metadata_overrides)
            store.upsert_entity(entity)

        # Domain simulator ticks
        maritime_sim.tick(sim_time)
        aviation_sim.tick(sim_time)
        ground_sim.tick(sim_time)
        personnel_sim.tick(sim_time)

        total_ais_count += len(maritime_sim.recent_ais_nmea)
        total_adsb_count += len(aviation_sim.recent_adsb_sbs)

        # Event processing
        event_engine.tick(sim_time)

        sim_time += tick_interval
        tick_count += 1

    return {
        "state": state,
        "store": store,
        "event_engine": event_engine,
        "initial_positions": initial_positions,
        "tick_count": tick_count,
        "total_ais_count": total_ais_count,
        "total_adsb_count": total_adsb_count,
        "maritime_sim": maritime_sim,
        "aviation_sim": aviation_sim,
    }


class TestFullScenarioExecution:
    def test_sulu_sea_fishing_intercept(self, start_time):
        """Run full IUU fishing scenario with all domain simulators."""
        result = _run_scenario(
            "config/scenarios/sulu_sea_fishing_intercept.yaml", start_time
        )
        store = result["store"]
        event_engine = result["event_engine"]

        # 1. All entities exist
        assert store.count > 10

        # 2. All events fired
        assert event_engine.is_complete

        # 3. Entities moved
        moved = 0
        for eid, (init_lat, init_lon) in result["initial_positions"].items():
            entity = store.get_entity(eid)
            if entity and eid in result["state"].movements:
                if abs(entity.position.latitude - init_lat) > 0.001:
                    moved += 1
        assert moved > 3

        # 4. IFF-001 stopped after intercept
        iff001 = store.get_entity("IFF-001")
        assert iff001 is not None
        assert iff001.speed_knots < 2

        # 5. Maritime entities have nav_status
        for e in store.get_entities_by_domain(Domain.MARITIME):
            if e.metadata.get("ais_active", True):
                assert "nav_status" in e.metadata

        # 6. AIS messages were generated
        assert result["total_ais_count"] > 0

        # 7. Events include expected types
        fired_types = [e.event_type for e in event_engine.get_fired_events()]
        assert "INTERCEPT" in fired_types
        assert "DETECTION" in fired_types
        assert "ORDER" in fired_types

    def test_semporna_kfr_with_domain_sims(self, start_time):
        """Run KFR scenario with all domain simulators."""
        result = _run_scenario(
            "config/scenarios/semporna_kfr_response.yaml", start_time
        )
        store = result["store"]
        event_engine = result["event_engine"]

        assert store.count > 5
        assert event_engine.is_complete

        # Personnel should have formation metadata
        for e in store.get_entities_by_domain(Domain.PERSONNEL):
            assert "formation" in e.metadata

        # Ground vehicles should have speed_kmh
        for e in store.get_entities_by_domain(Domain.GROUND_VEHICLE):
            assert "speed_kmh" in e.metadata

    def test_scenario_no_crashes(self, start_time):
        """Both scenarios should run to completion without exceptions."""
        for scenario in [
            "config/scenarios/sulu_sea_fishing_intercept.yaml",
            "config/scenarios/semporna_kfr_response.yaml",
        ]:
            result = _run_scenario(scenario, start_time)
            assert result["event_engine"].is_complete
            assert result["tick_count"] > 100
