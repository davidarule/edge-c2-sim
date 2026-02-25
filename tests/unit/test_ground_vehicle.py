"""Tests for ground vehicle simulator."""

from datetime import datetime, timezone

import pytest

from simulator.core.entity import Agency, Domain, Entity, EntityStatus, Position
from simulator.core.entity_store import EntityStore
from simulator.domains.ground_vehicle import GroundVehicleSimulator


@pytest.fixture
def store():
    return EntityStore()


@pytest.fixture
def sim_time():
    return datetime(2026, 4, 15, 8, 0, 0, tzinfo=timezone.utc)


def _make_vehicle(eid, speed_kts=10.0, status=EntityStatus.ACTIVE):
    return Entity(
        entity_id=eid, entity_type="MIL_VEHICLE",
        domain=Domain.GROUND_VEHICLE, agency=Agency.MIL,
        callsign=eid, position=Position(5.5, 118.5, 0),
        speed_knots=speed_kts, status=status,
    )


class TestGroundVehicleSimulator:
    def test_speed_kmh_metadata(self, store, sim_time):
        """Speed should be available in km/h."""
        v = _make_vehicle("V1", speed_kts=10.0)
        store.add_entity(v)

        sim = GroundVehicleSimulator(store)
        sim.tick(sim_time)

        updated = store.get_entity("V1")
        assert abs(updated.metadata["speed_kmh"] - 18.5) < 0.5  # 10kts * 1.852

    def test_emergency_mode(self, store, sim_time):
        """Responding vehicle should have emergency_mode flag."""
        v = _make_vehicle("V1", speed_kts=20.0, status=EntityStatus.RESPONDING)
        store.add_entity(v)

        sim = GroundVehicleSimulator(store)
        sim.tick(sim_time)

        assert store.get_entity("V1").metadata["emergency_mode"] is True

    def test_altitude_zero(self, store, sim_time):
        """Ground vehicles should have altitude=0."""
        v = _make_vehicle("V1")
        v.position.altitude_m = 100  # Erroneous altitude
        store.add_entity(v)

        sim = GroundVehicleSimulator(store)
        sim.tick(sim_time)

        assert store.get_entity("V1").position.altitude_m == 0
