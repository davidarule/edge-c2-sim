"""Tests for hold-station movement."""

from datetime import datetime, timezone

import pytest
from geopy.distance import geodesic

from simulator.core.entity import Agency, Domain, Entity, EntityStatus, Position
from simulator.core.entity_store import EntityStore
from simulator.movement.hold_station import HoldStationMovement


@pytest.fixture
def sim_time():
    return datetime(2026, 4, 19, 0, 0, 0, tzinfo=timezone.utc)


def _make_entity(eid, lat, lon, heading=0.0):
    return Entity(
        entity_id=eid, entity_type="TANKER_CARGO",
        domain=Domain.MARITIME, agency=Agency.MMEA,
        callsign=eid, position=Position(lat, lon),
        heading_deg=heading,
        status=EntityStatus.ACTIVE,
    )


class TestHoldStationAlongside:
    def test_no_target_stays_in_place(self, sim_time):
        m = HoldStationMovement(lat=3.0, lon=101.0)
        s = m.get_state(sim_time)
        assert s.lat == pytest.approx(3.0)
        assert s.lon == pytest.approx(101.0)

    def test_preserves_offset_to_stationary_target(self, sim_time):
        """Entity ~500m from the tanker when hold_station starts should stay
        ~500m from the tanker, not teleport onto the tanker's position."""
        store = EntityStore()
        tanker = _make_entity("TANKER", 3.0, 101.0)
        store.add_entity(tanker)

        # Pirate ~500m south of tanker at hold-station start
        pirate_lat, pirate_lon = 2.9955, 101.0
        initial_distance_m = geodesic(
            (tanker.position.latitude, tanker.position.longitude),
            (pirate_lat, pirate_lon),
        ).meters

        m = HoldStationMovement(
            lat=pirate_lat, lon=pirate_lon,
            target_entity_id="TANKER", entity_store=store,
        )
        s = m.get_state(sim_time)
        dist_now = geodesic(
            (tanker.position.latitude, tanker.position.longitude),
            (s.lat, s.lon),
        ).meters
        assert abs(dist_now - initial_distance_m) < 5.0, (
            f"expected ~{initial_distance_m:.0f} m from target, got {dist_now:.0f} m "
            f"(entity snapped onto target)"
        )

    def test_offset_follows_moving_target(self, sim_time):
        """When the tanker moves, the entity should move with it, keeping the same
        geographic offset."""
        store = EntityStore()
        tanker = _make_entity("TANKER", 3.0, 101.0)
        store.add_entity(tanker)

        pirate_lat, pirate_lon = 2.9955, 101.0  # 500 m south
        m = HoldStationMovement(
            lat=pirate_lat, lon=pirate_lon,
            target_entity_id="TANKER", entity_store=store,
        )
        m.get_state(sim_time)  # Lock in offset

        # Tanker drifts north by ~100m
        tanker.position = Position(3.001, 101.0)
        store.upsert_entity(tanker)

        s = m.get_state(sim_time)
        # Entity should also have moved north by ~100m, still ~500m south of tanker
        assert s.lat > pirate_lat, "entity should drift with target"
        dist_now = geodesic(
            (tanker.position.latitude, tanker.position.longitude),
            (s.lat, s.lon),
        ).meters
        assert abs(dist_now - 500.0) < 20.0, (
            f"offset not preserved: now {dist_now:.0f} m from target"
        )
