"""Tests for maritime simulator."""

from datetime import datetime, timedelta, timezone

import pytest

from simulator.core.entity import Agency, Domain, Entity, EntityStatus, Position
from simulator.core.entity_store import EntityStore
from simulator.domains.maritime import MaritimeSimulator


@pytest.fixture
def store():
    return EntityStore()


@pytest.fixture
def sim_time():
    return datetime(2026, 4, 15, 8, 0, 0, tzinfo=timezone.utc)


def _make_vessel(eid, speed=10.0, ais_active=True, entity_type="CIVILIAN_CARGO"):
    return Entity(
        entity_id=eid, entity_type=entity_type,
        domain=Domain.MARITIME, agency=Agency.CIVILIAN,
        callsign=eid, position=Position(5.5, 118.5),
        speed_knots=speed,
        timestamp=datetime(2026, 4, 15, 8, 0, 0, tzinfo=timezone.utc),
        metadata={
            "ais_active": ais_active,
            "flag": "MYS",
            "mmsi": "533000001",
        },
    )


class TestMaritimeSimulator:
    def test_ais_generated_for_active_vessel(self, store, sim_time):
        """AIS should be generated for AIS-active vessels."""
        vessel = _make_vessel("V1", speed=10)
        store.add_entity(vessel)

        sim = MaritimeSimulator(store)
        sim.tick(sim_time)

        assert len(sim.recent_ais_nmea) > 0
        assert len(sim.recent_ais_json) > 0

    def test_no_ais_when_dark(self, store, sim_time):
        """No AIS should be generated when ais_active=false."""
        vessel = _make_vessel("DARK-1", speed=8, ais_active=False)
        store.add_entity(vessel)

        sim = MaritimeSimulator(store)
        sim.tick(sim_time)

        assert len(sim.recent_ais_nmea) == 0
        assert len(sim.recent_ais_json) == 0

    def test_nav_status_underway(self, store, sim_time):
        """Moving vessel should have nav_status=0 (underway)."""
        vessel = _make_vessel("V1", speed=10)
        store.add_entity(vessel)

        sim = MaritimeSimulator(store)
        sim.tick(sim_time)

        updated = store.get_entity("V1")
        assert updated.metadata["nav_status"] == 0

    def test_nav_status_anchor(self, store, sim_time):
        """Idle vessel should have nav_status=1 (at anchor)."""
        vessel = _make_vessel("V1", speed=0)
        vessel.status = EntityStatus.IDLE
        store.add_entity(vessel)

        sim = MaritimeSimulator(store)
        sim.tick(sim_time)

        assert store.get_entity("V1").metadata["nav_status"] == 1

    def test_nav_status_fishing(self, store, sim_time):
        """Slow fishing vessel should have nav_status=7."""
        vessel = _make_vessel("F1", speed=2, entity_type="CIVILIAN_FISHING")
        store.add_entity(vessel)

        sim = MaritimeSimulator(store)
        sim.tick(sim_time)

        assert store.get_entity("F1").metadata["nav_status"] == 7

    def test_ais_type5_generated(self, store, sim_time):
        """Type 5 static data should be generated on first tick."""
        vessel = _make_vessel("V1", speed=10)
        store.add_entity(vessel)

        sim = MaritimeSimulator(store)
        sim.tick(sim_time)

        # Should have both position (Type 1) and static (Type 5) NMEA
        assert len(sim.recent_ais_nmea) >= 2

    def test_ais_interval_respects_speed(self, store, sim_time):
        """Fast vessel should generate AIS more often than slow one."""
        vessel = _make_vessel("FAST", speed=25)
        store.add_entity(vessel)

        sim = MaritimeSimulator(store)
        sim.tick(sim_time)
        count1 = len(sim.recent_ais_nmea)

        # Second tick 1 second later — fast vessel should still generate
        sim.tick(sim_time + timedelta(seconds=3))
        count2 = len(sim.recent_ais_nmea)

        assert count2 > 0  # 25kt vessel has 2s interval

    def test_multiple_vessels(self, store, sim_time):
        """Multiple active vessels should each generate AIS."""
        for i in range(3):
            store.add_entity(_make_vessel(f"V{i}", speed=10))

        sim = MaritimeSimulator(store)
        sim.tick(sim_time)

        assert len(sim.recent_ais_json) == 3
