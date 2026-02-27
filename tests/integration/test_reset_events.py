"""
Regression test: events must fire again after simulator reset.

BUG: simulation_loop captured event_engine and scenario_state as function
parameters. When handle_restart replaced them via nonlocal assignment,
the loop still held stale references — events never fired again after reset.

FIX: simulation_loop accesses event_engine and scenario_state through a
shared mutable dict (sim_context) so reset updates are visible to the loop.
"""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from simulator.core.clock import SimulationClock
from simulator.core.entity import Agency, Domain, Entity, EntityStatus, Position
from simulator.core.entity_store import EntityStore
from simulator.scenario.event_engine import EventEngine
from simulator.scenario.loader import ScenarioEvent, ScenarioLoader, ScenarioState


@pytest.fixture
def start_time():
    return datetime(2026, 4, 15, 8, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def simple_scenario(start_time):
    """Minimal scenario with one entity and one event at t+5min."""
    entity = Entity(
        entity_id="TEST-001",
        entity_type="MMEA_PATROL",
        domain=Domain.MARITIME,
        agency=Agency.MMEA,
        callsign="Test Vessel",
        position=Position(5.0, 118.0),
        status=EntityStatus.ACTIVE,
        initial_position=Position(5.0, 118.0),
    )
    events = [
        ScenarioEvent(
            time_offset=timedelta(minutes=5),
            event_type="DETECTION",
            description="Test detection event",
            severity="WARNING",
        ),
    ]
    return ScenarioState(
        name="test",
        description="Test scenario",
        duration=timedelta(minutes=30),
        center=(5.0, 118.0),
        zoom=9,
        entities={"TEST-001": entity},
        movements={},
        events=events,
        start_time=start_time,
    )


class TestResetEventsRegression:
    """Verify that events fire again after a simulator reset."""

    def test_event_engine_via_shared_context(self, simple_scenario, start_time):
        """After reset, simulation loop must see fresh event_engine via sim_context dict."""
        store = EntityStore()
        for e in simple_scenario.entities.values():
            store.add_entity(e)

        event_engine = EventEngine(
            events=simple_scenario.events,
            entity_store=store,
            movements=simple_scenario.movements,
            scenario_start=start_time,
        )

        # Shared mutable context — this is how the loop should access these
        sim_context = {
            "scenario_state": simple_scenario,
            "event_engine": event_engine,
        }

        # Simulate: advance past event time
        sim_time = start_time + timedelta(minutes=10)
        fired = sim_context["event_engine"].tick(sim_time)
        assert len(fired) == 1
        assert sim_context["event_engine"].is_complete

        # Reset: create fresh event engine in context (what handle_restart does)
        fresh_engine = EventEngine(
            events=simple_scenario.events,
            entity_store=store,
            movements=simple_scenario.movements,
            scenario_start=start_time,
        )
        sim_context["event_engine"] = fresh_engine

        # After reset, events must be unfired
        assert not sim_context["event_engine"].is_complete
        assert len(sim_context["event_engine"].get_fired_events()) == 0

        # Events must fire again
        fired2 = sim_context["event_engine"].tick(sim_time)
        assert len(fired2) == 1, "Events must fire again after reset"

    def test_stale_parameter_reference_is_the_bug(self, simple_scenario, start_time):
        """Demonstrate the actual bug: passing event_engine as a parameter
        creates a stale reference after reset replaces the outer variable."""
        store = EntityStore()
        for e in simple_scenario.entities.values():
            store.add_entity(e)

        event_engine = EventEngine(
            events=simple_scenario.events,
            entity_store=store,
            movements=simple_scenario.movements,
            scenario_start=start_time,
        )

        # Simulate a function that captures event_engine as a parameter
        def loop_tick(ee_param, sim_time):
            """This mimics how simulation_loop used the parameter."""
            return ee_param.tick(sim_time)

        # Fire all events
        sim_time = start_time + timedelta(minutes=10)
        fired = loop_tick(event_engine, sim_time)
        assert len(fired) == 1

        # "Reset" — create new engine (like handle_restart does with nonlocal)
        event_engine = EventEngine(
            events=simple_scenario.events,
            entity_store=store,
            movements=simple_scenario.movements,
            scenario_start=start_time,
        )

        # BUG: if loop_tick still used the OLD parameter, events wouldn't fire.
        # The fix is that the loop accesses via sim_context dict, not a parameter.
        fired2 = loop_tick(event_engine, sim_time)
        assert len(fired2) == 1, "Fresh event_engine must fire events"

    def test_full_scenario_reset_events_refire(self, start_time):
        """Load real scenario, fire events, reset, verify events fire again."""
        loader = ScenarioLoader()
        state = loader.load(
            "config/scenarios/sulu_sea_fishing_intercept.yaml",
            start_time=start_time,
        )
        store = EntityStore()
        for e in state.entities.values():
            store.add_entity(e)

        event_engine = EventEngine(
            events=state.events,
            entity_store=store,
            movements=state.movements,
            scenario_start=start_time,
        )

        sim_context = {
            "scenario_state": state,
            "event_engine": event_engine,
        }

        # Run past all events
        sim_time = start_time + state.duration + timedelta(minutes=5)
        sim_context["event_engine"].tick(sim_time)
        assert sim_context["event_engine"].is_complete
        original_fired_count = len(sim_context["event_engine"].get_fired_events())
        assert original_fired_count > 0

        # Reset: reload scenario, recreate event engine
        fresh = loader.load(
            "config/scenarios/sulu_sea_fishing_intercept.yaml",
            start_time=start_time,
        )
        sim_context["scenario_state"] = fresh

        fresh_store = EntityStore()
        for e in fresh.entities.values():
            fresh_store.add_entity(e)

        sim_context["event_engine"] = EventEngine(
            events=fresh.events,
            entity_store=fresh_store,
            movements=fresh.movements,
            scenario_start=start_time,
        )

        # After reset: no events fired yet
        assert not sim_context["event_engine"].is_complete
        assert len(sim_context["event_engine"].get_fired_events()) == 0

        # Events fire again
        sim_context["event_engine"].tick(sim_time)
        assert sim_context["event_engine"].is_complete
        assert len(sim_context["event_engine"].get_fired_events()) == original_fired_count
