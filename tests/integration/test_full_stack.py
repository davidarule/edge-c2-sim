"""
Full stack integration test.

Runs the simulator with REST adapter (dry run) and verifies:
1. REST adapter generates correct payloads for each endpoint
2. Events are pushed through all transports
3. Entity lifecycle: create -> update -> intercept -> stop
4. Scenario completes without errors
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
from simulator.transport.rest_adapter import RESTAdapter
from simulator.transport.cot_adapter import CoTAdapter
from simulator.transport.registry import TransportRegistry


@pytest.fixture
def start_time():
    return datetime(2026, 4, 15, 8, 0, 0, tzinfo=timezone.utc)


async def _run_with_transports(scenario_path, start_time):
    """Run a scenario with REST (dry run) and CoT (disabled) adapters."""
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

    # Transport registry with REST dry-run and disabled CoT
    registry = TransportRegistry()

    rest_adapter = RESTAdapter(
        api_spec_path="config/edge_c2_api.yaml",
        base_url="http://localhost:9999",
        dry_run=True,
        batch_mode=False,
    )
    await rest_adapter.connect()
    registry.register(rest_adapter)

    cot_adapter = CoTAdapter(enabled=False)
    registry.register(cot_adapter)

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

        # Domain sim ticks
        maritime_sim.tick(sim_time)
        aviation_sim.tick(sim_time)
        ground_sim.tick(sim_time)
        personnel_sim.tick(sim_time)

        # Push bulk updates through registry
        all_entities = store.get_all_entities()
        await registry.push_bulk_update(all_entities)

        # Event processing
        fired = event_engine.tick(sim_time)
        for event in fired:
            await registry.push_event(event.to_dict())

        sim_time += tick_interval
        tick_count += 1

    await rest_adapter.disconnect()

    return {
        "state": state,
        "store": store,
        "event_engine": event_engine,
        "rest_adapter": rest_adapter,
        "tick_count": tick_count,
        "registry": registry,
    }


class TestFullStackIntegration:
    @pytest.mark.asyncio
    async def test_rest_dry_run_generates_payloads(self, start_time):
        """REST adapter in dry-run mode generates payloads for all endpoints."""
        result = await _run_with_transports(
            "config/scenarios/sulu_sea_fishing_intercept.yaml", start_time
        )
        rest = result["rest_adapter"]
        log = rest.dry_run_log

        # Should have many entries (entity creates + position updates + events)
        assert len(log) > 100

        # Check entity creates were logged
        creates = [e for e in log if "entities" in e["path"] and e["method"] == "POST"
                   and "position" not in e["path"] and "bulk" not in e["path"]]
        assert len(creates) > 10  # At least 10 entities created

        # Check position updates were logged
        position_updates = [e for e in log if "position" in e["path"]]
        assert len(position_updates) > 50

        # Check events were logged
        event_posts = [e for e in log if "events" in e["path"]]
        assert len(event_posts) > 0

    @pytest.mark.asyncio
    async def test_payload_structure(self, start_time):
        """Verify payload structure matches API spec."""
        result = await _run_with_transports(
            "config/scenarios/sulu_sea_fishing_intercept.yaml", start_time
        )
        rest = result["rest_adapter"]
        log = rest.dry_run_log

        # Find a position update payload
        pos_entries = [e for e in log if "position" in e["path"]]
        assert len(pos_entries) > 0
        sample = pos_entries[0]["payload"]
        assert "position" in sample
        assert "latitude" in sample["position"]
        assert "longitude" in sample["position"]
        assert "heading_deg" in sample
        assert "speed_knots" in sample
        assert "timestamp" in sample

        # Find an entity create payload
        creates = [e for e in log if "entities" in e["path"] and e["method"] == "POST"
                   and "position" not in e["path"] and "bulk" not in e["path"]]
        if creates:
            create_payload = creates[0]["payload"]
            assert "entity_id" in create_payload
            assert "entity_type" in create_payload
            assert "domain" in create_payload
            assert "agency" in create_payload

    @pytest.mark.asyncio
    async def test_scenario_completes(self, start_time):
        """Scenario runs to completion with transports active."""
        result = await _run_with_transports(
            "config/scenarios/sulu_sea_fishing_intercept.yaml", start_time
        )
        assert result["event_engine"].is_complete
        assert result["tick_count"] > 100

    @pytest.mark.asyncio
    async def test_registry_has_multiple_transports(self, start_time):
        """Registry manages both REST and CoT transports."""
        result = await _run_with_transports(
            "config/scenarios/sulu_sea_fishing_intercept.yaml", start_time
        )
        registry = result["registry"]
        assert registry.count == 2
        assert "rest" in registry.transport_names
        assert "cot" in registry.transport_names
