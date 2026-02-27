"""Tests for event engine."""

from datetime import datetime, timedelta, timezone

import pytest

from simulator.core.entity import Agency, Domain, Entity, EntityStatus, Position
from simulator.core.entity_store import EntityStore
from simulator.movement.waypoint import Waypoint, WaypointMovement
from simulator.scenario.event_engine import EventEngine
from simulator.scenario.loader import ScenarioEvent


@pytest.fixture
def start_time():
    return datetime(2026, 4, 15, 8, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def store():
    return EntityStore()


def _make_entity(eid, lat=5.0, lon=118.0, etype="MMEA_PATROL"):
    return Entity(
        entity_id=eid, entity_type=etype,
        domain=Domain.MARITIME, agency=Agency.MMEA,
        callsign=eid, position=Position(lat, lon),
        status=EntityStatus.IDLE,
    )


class TestEventEngine:
    def test_events_fire_at_correct_time(self, store, start_time):
        """Events should fire when sim_time reaches their offset."""
        store.add_entity(_make_entity("E1"))
        events = [
            ScenarioEvent(
                time_offset=timedelta(minutes=5),
                event_type="ALERT", description="Test alert",
            ),
            ScenarioEvent(
                time_offset=timedelta(minutes=10),
                event_type="ORDER", description="Test order",
            ),
        ]
        engine = EventEngine(events, store, {}, start_time)

        # At t+3min, nothing fires
        fired = engine.tick(start_time + timedelta(minutes=3))
        assert len(fired) == 0

        # At t+5min, first event fires
        fired = engine.tick(start_time + timedelta(minutes=5))
        assert len(fired) == 1
        assert fired[0].event_type == "ALERT"

        # At t+10min, second event fires
        fired = engine.tick(start_time + timedelta(minutes=10))
        assert len(fired) == 1
        assert fired[0].event_type == "ORDER"

    def test_events_dont_refire(self, store, start_time):
        """Events should only fire once."""
        events = [
            ScenarioEvent(
                time_offset=timedelta(minutes=5),
                event_type="ALERT", description="Test",
            ),
        ]
        engine = EventEngine(events, store, {}, start_time)

        fired1 = engine.tick(start_time + timedelta(minutes=5))
        assert len(fired1) == 1

        fired2 = engine.tick(start_time + timedelta(minutes=6))
        assert len(fired2) == 0

    def test_intercept_swaps_movement(self, store, start_time):
        """ORDER/intercept should swap movement to InterceptMovement."""
        pursuer = _make_entity("MMEA-1", 5.0, 118.0)
        target = _make_entity("TARGET-1", 6.0, 119.0, etype="SUSPECT_VESSEL")
        store.add_entity(pursuer)
        store.add_entity(target)

        movements = {}
        events = [
            ScenarioEvent(
                time_offset=timedelta(minutes=5),
                event_type="ORDER",
                description="Intercept",
                target="MMEA-1",
                action="intercept",
                intercept_target="TARGET-1",
            ),
        ]
        engine = EventEngine(events, store, movements, start_time)
        engine.tick(start_time + timedelta(minutes=5))

        assert "MMEA-1" in movements
        from simulator.movement.intercept import InterceptMovement
        assert isinstance(movements["MMEA-1"], InterceptMovement)

        # Entity status should be INTERCEPTING
        updated = store.get_entity("MMEA-1")
        assert updated.status == EntityStatus.INTERCEPTING

    def test_deploy_creates_waypoint(self, store, start_time):
        """ORDER/deploy with destination should create waypoint movement."""
        entity = _make_entity("UNIT-1", 5.0, 118.0)
        store.add_entity(entity)

        movements = {}
        events = [
            ScenarioEvent(
                time_offset=timedelta(minutes=5),
                event_type="ORDER",
                description="Deploy",
                target="UNIT-1",
                action="deploy",
                destination={"lat": 5.5, "lon": 118.5},
            ),
        ]
        engine = EventEngine(events, store, movements, start_time)
        engine.tick(start_time + timedelta(minutes=5))

        assert "UNIT-1" in movements
        assert isinstance(movements["UNIT-1"], WaypointMovement)

        updated = store.get_entity("UNIT-1")
        assert updated.status == EntityStatus.RESPONDING

    def test_multi_target_event(self, store, start_time):
        """Event with targets list should apply to all."""
        store.add_entity(_make_entity("A"))
        store.add_entity(_make_entity("B"))

        events = [
            ScenarioEvent(
                time_offset=timedelta(minutes=5),
                event_type="ORDER",
                description="Activate all",
                targets=["A", "B"],
                action="activate",
            ),
        ]
        engine = EventEngine(events, store, {}, start_time)
        engine.tick(start_time + timedelta(minutes=5))

        assert store.get_entity("A").status == EntityStatus.ACTIVE
        assert store.get_entity("B").status == EntityStatus.ACTIVE

    def test_is_complete(self, store, start_time):
        """is_complete should be true when all events fired."""
        events = [
            ScenarioEvent(
                time_offset=timedelta(minutes=1),
                event_type="ALERT", description="A",
            ),
            ScenarioEvent(
                time_offset=timedelta(minutes=2),
                event_type="ALERT", description="B",
            ),
        ]
        engine = EventEngine(events, store, {}, start_time)

        assert not engine.is_complete
        engine.tick(start_time + timedelta(minutes=1))
        assert not engine.is_complete
        engine.tick(start_time + timedelta(minutes=2))
        assert engine.is_complete

    def test_get_fired_events(self, store, start_time):
        events = [
            ScenarioEvent(
                time_offset=timedelta(minutes=1),
                event_type="ALERT", description="A",
            ),
        ]
        engine = EventEngine(events, store, {}, start_time)
        engine.tick(start_time + timedelta(minutes=1))
        assert len(engine.get_fired_events()) == 1

    def test_get_upcoming_events(self, store, start_time):
        events = [
            ScenarioEvent(
                time_offset=timedelta(minutes=1),
                event_type="A", description="A",
            ),
            ScenarioEvent(
                time_offset=timedelta(minutes=5),
                event_type="B", description="B",
            ),
        ]
        engine = EventEngine(events, store, {}, start_time)
        engine.tick(start_time + timedelta(minutes=1))
        upcoming = engine.get_upcoming_events()
        assert len(upcoming) == 1
        assert upcoming[0].event_type == "B"

    def test_reclassify_changes_entity_type(self, store, start_time):
        """Reclassify event should change entity type and SIDC."""
        suspect = Entity(
            entity_id="HOSTILE-001", entity_type="SUSPECT_VESSEL",
            domain=Domain.MARITIME, agency=Agency.CIVILIAN,
            callsign="Suspect 1", position=Position(4.9, 119.2),
            status=EntityStatus.ACTIVE, sidc="SHSP------",
        )
        store.add_entity(suspect)

        events = [
            ScenarioEvent(
                time_offset=timedelta(minutes=10),
                event_type="INCIDENT",
                description="Armed attack — reclassify",
                metadata={
                    "reclassify": {
                        "targets": ["HOSTILE-001"],
                        "new_type": "HOSTILE_VESSEL",
                    }
                },
            ),
        ]
        engine = EventEngine(events, store, {}, start_time)
        engine.tick(start_time + timedelta(minutes=10))

        updated = store.get_entity("HOSTILE-001")
        assert updated.entity_type == "HOSTILE_VESSEL"
        assert updated.sidc == "SHSP------"  # HOSTILE_VESSEL SIDC

    def test_pursue_creates_intercept_movement(self, store, start_time):
        """Pursue action should create InterceptMovement like intercept."""
        pursuer = _make_entity("HELI-1", 5.0, 118.0)
        target = Entity(
            entity_id="BAD-1", entity_type="HOSTILE_VESSEL",
            domain=Domain.MARITIME, agency=Agency.CIVILIAN,
            callsign="Bad 1", position=Position(4.5, 118.5),
            status=EntityStatus.ACTIVE,
        )
        store.add_entity(pursuer)
        store.add_entity(target)

        movements = {}
        events = [
            ScenarioEvent(
                time_offset=timedelta(minutes=5),
                event_type="ORDER",
                description="Pursue",
                target="HELI-1",
                action="pursue",
                intercept_target="BAD-1",
            ),
        ]
        engine = EventEngine(events, store, movements, start_time)
        engine.tick(start_time + timedelta(minutes=5))

        from simulator.movement.intercept import InterceptMovement
        assert isinstance(movements["HELI-1"], InterceptMovement)
        assert store.get_entity("HELI-1").status == EntityStatus.INTERCEPTING


class TestEntityTypes:
    """Verify new entity types are properly defined."""

    def test_rmp_marine_patrol_exists(self):
        """RMP_MARINE_PATROL should be a valid entity type."""
        from simulator.scenario.loader import ENTITY_TYPES
        assert "RMP_MARINE_PATROL" in ENTITY_TYPES
        typedef = ENTITY_TYPES["RMP_MARINE_PATROL"]
        assert typedef["domain"] == Domain.MARITIME
        assert typedef["agency"] == Agency.RMP

    def test_all_scenario_entity_types_valid(self):
        """All entity types used in scenario files should exist in ENTITY_TYPES."""
        import yaml
        from simulator.scenario.loader import ENTITY_TYPES

        scenario_files = [
            "config/scenarios/demo_combined.yaml",
            "config/scenarios/sulu_sea_fishing_intercept.yaml",
            "config/scenarios/semporna_kfr_response.yaml",
        ]
        for path in scenario_files:
            with open(path) as f:
                raw = yaml.safe_load(f)
            scenario = raw.get("scenario", {})
            for entity in scenario.get("scenario_entities", []):
                etype = entity["type"]
                assert etype in ENTITY_TYPES, f"{etype} not in ENTITY_TYPES ({path})"
            for bg in scenario.get("background_entities", []):
                etype = bg["type"]
                assert etype in ENTITY_TYPES, f"{etype} not in ENTITY_TYPES ({path})"
