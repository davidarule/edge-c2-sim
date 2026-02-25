"""Tests for personnel simulator."""

import math
from datetime import datetime, timezone

import pytest

from simulator.core.entity import Agency, Domain, Entity, EntityStatus, Position
from simulator.core.entity_store import EntityStore
from simulator.domains.personnel import PersonnelSimulator


@pytest.fixture
def store():
    return EntityStore()


@pytest.fixture
def sim_time():
    return datetime(2026, 4, 15, 8, 0, 0, tzinfo=timezone.utc)


def _make_personnel(eid, unit_size=4, formation="standby", speed=0):
    return Entity(
        entity_id=eid, entity_type="RMP_OFFICER",
        domain=Domain.PERSONNEL, agency=Agency.RMP,
        callsign=eid, position=Position(5.5, 118.5),
        speed_knots=speed, heading_deg=0,
        metadata={"unit_size": unit_size, "formation": formation},
    )


class TestPersonnelSimulator:
    def test_member_positions_generated(self, store, sim_time):
        """Unit with size > 1 should have member_positions."""
        unit = _make_personnel("U1", unit_size=6, formation="standby")
        store.add_entity(unit)

        sim = PersonnelSimulator(store)
        sim.tick(sim_time)

        updated = store.get_entity("U1")
        assert "member_positions" in updated.metadata
        assert len(updated.metadata["member_positions"]) == 6

    def test_cordon_ring_formation(self, store, sim_time):
        """Cordon formation should create ring-shaped distribution."""
        unit = _make_personnel("U1", unit_size=8, formation="cordon")
        store.add_entity(unit)

        sim = PersonnelSimulator(store)
        sim.tick(sim_time)

        members = store.get_entity("U1").metadata["member_positions"]
        center_lat = 5.5
        center_lon = 118.5

        # All members should be roughly the same distance from center
        distances = []
        for m in members:
            dlat_m = (m["lat"] - center_lat) * 111_111
            dlon_m = (m["lon"] - center_lon) * 111_111 * math.cos(math.radians(center_lat))
            dist = math.sqrt(dlat_m ** 2 + dlon_m ** 2)
            distances.append(dist)

        # Distances should be similar (ring shape)
        assert max(distances) - min(distances) < 5  # Within 5m tolerance

    def test_speed_limited(self, store, sim_time):
        """Personnel speed should not exceed running speed."""
        unit = _make_personnel("U1", speed=10)  # Too fast
        store.add_entity(unit)

        sim = PersonnelSimulator(store)
        sim.tick(sim_time)

        updated = store.get_entity("U1")
        assert updated.speed_knots <= 4.5  # ~8 km/h

    def test_speed_kmh_metadata(self, store, sim_time):
        """Speed should be available in km/h."""
        unit = _make_personnel("U1", speed=2.0)
        store.add_entity(unit)

        sim = PersonnelSimulator(store)
        sim.tick(sim_time)

        updated = store.get_entity("U1")
        assert abs(updated.metadata["speed_kmh"] - 3.7) < 0.2

    def test_formation_metadata_set(self, store, sim_time):
        """Formation type should always be in metadata."""
        unit = _make_personnel("U1", formation="checkpoint")
        store.add_entity(unit)

        sim = PersonnelSimulator(store)
        sim.tick(sim_time)

        assert store.get_entity("U1").metadata["formation"] == "checkpoint"

    def test_single_person_no_member_positions(self, store, sim_time):
        """Unit size 1 should not generate member_positions."""
        unit = _make_personnel("U1", unit_size=1)
        store.add_entity(unit)

        sim = PersonnelSimulator(store)
        sim.tick(sim_time)

        assert "member_positions" not in store.get_entity("U1").metadata
