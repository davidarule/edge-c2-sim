"""Tests for aviation simulator."""

from datetime import datetime, timedelta, timezone

import pytest

from simulator.core.entity import Agency, Domain, Entity, EntityStatus, Position
from simulator.core.entity_store import EntityStore
from simulator.domains.aviation import AviationSimulator


@pytest.fixture
def store():
    return EntityStore()


@pytest.fixture
def sim_time():
    return datetime(2026, 4, 15, 8, 0, 0, tzinfo=timezone.utc)


def _make_aircraft(
    eid, etype="RMAF_TRANSPORT", speed=0, alt_m=15.0,
    status=EntityStatus.IDLE, adsb=True, on_ground=True,
):
    return Entity(
        entity_id=eid, entity_type=etype,
        domain=Domain.AIR, agency=Agency.RMAF,
        callsign=eid, position=Position(5.5, 118.5, alt_m),
        speed_knots=speed,
        timestamp=datetime(2026, 4, 15, 8, 0, 0, tzinfo=timezone.utc),
        status=status,
        metadata={
            "adsb_active": adsb,
            "on_ground": on_ground,
        },
    )


class TestAviationSimulator:
    def test_parked_aircraft(self, store, sim_time):
        """Parked aircraft should stay on ground."""
        ac = _make_aircraft("AC1")
        store.add_entity(ac)

        sim = AviationSimulator(store)
        sim.tick(sim_time)

        updated = store.get_entity("AC1")
        assert updated.metadata["flight_phase"] == "parked"
        assert updated.metadata["on_ground"] is True

    def test_takeoff_transitions(self, store, sim_time):
        """Aircraft with speed on ground should transition to airborne."""
        ac = _make_aircraft("AC1", speed=120, status=EntityStatus.ACTIVE, on_ground=True)
        store.add_entity(ac)

        sim = AviationSimulator(store)
        sim.tick(sim_time)
        sim.tick(sim_time + timedelta(seconds=30))

        updated = store.get_entity("AC1")
        assert updated.metadata["on_ground"] is False

    def test_climb_increases_altitude(self, store, sim_time):
        """Active aircraft should climb toward cruise altitude."""
        ac = _make_aircraft(
            "AC1", speed=200, alt_m=300,  # ~1000ft
            status=EntityStatus.ACTIVE, on_ground=False,
        )
        store.add_entity(ac)

        sim = AviationSimulator(store)
        sim.tick(sim_time)
        # Second tick with time delta
        sim.tick(sim_time + timedelta(minutes=5))

        updated = store.get_entity("AC1")
        assert updated.position.altitude_m > 300
        assert updated.metadata["flight_phase"] == "climb"

    def test_helicopter_hover(self, store, sim_time):
        """Slow helicopter should be in hover."""
        helo = _make_aircraft(
            "H1", etype="RMAF_HELICOPTER", speed=2,
            alt_m=300, status=EntityStatus.ACTIVE, on_ground=False,
        )
        store.add_entity(helo)

        sim = AviationSimulator(store)
        sim.tick(sim_time)
        sim.tick(sim_time + timedelta(seconds=10))

        updated = store.get_entity("H1")
        assert updated.metadata["flight_phase"] == "hover"

    def test_adsb_generated(self, store, sim_time):
        """ADS-B should be generated for active aircraft."""
        ac = _make_aircraft("AC1", speed=200, status=EntityStatus.ACTIVE,
                           on_ground=False, adsb=True)
        store.add_entity(ac)

        sim = AviationSimulator(store)
        sim.tick(sim_time)

        assert len(sim.recent_adsb_sbs) > 0
        assert len(sim.recent_adsb_json) > 0

    def test_no_adsb_when_inactive(self, store, sim_time):
        """No ADS-B when adsb_active=false."""
        ac = _make_aircraft("AC1", speed=200, status=EntityStatus.ACTIVE,
                           on_ground=False, adsb=False)
        store.add_entity(ac)

        sim = AviationSimulator(store)
        sim.tick(sim_time)

        assert len(sim.recent_adsb_sbs) == 0

    def test_scramble_faster_climb(self, store, sim_time):
        """Scramble aircraft should climb faster."""
        ac = _make_aircraft(
            "F1", etype="RMAF_FIGHTER", speed=400, alt_m=300,
            status=EntityStatus.RESPONDING, on_ground=False,
        )
        ac.metadata["scramble"] = True
        store.add_entity(ac)

        sim = AviationSimulator(store)
        sim.tick(sim_time)
        sim.tick(sim_time + timedelta(minutes=2))

        updated = store.get_entity("F1")
        # Should have gained significant altitude with scramble
        assert updated.position.altitude_m > 500
        assert updated.metadata["vertical_rate_fpm"] > 0
