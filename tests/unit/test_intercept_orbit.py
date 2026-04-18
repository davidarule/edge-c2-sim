"""Tests for fixed-wing intercept → orbit transitions."""

import math
from datetime import datetime, timedelta, timezone

import pytest
from geopy.distance import geodesic

from simulator.core.entity import Agency, Domain, Entity, EntityStatus, Position
from simulator.core.entity_store import EntityStore
from simulator.movement.intercept import InterceptMovement


@pytest.fixture
def sim_start():
    return datetime(2026, 4, 19, 0, 0, 0, tzinfo=timezone.utc)


def _make_air(eid, lat, lon, heading=0.0):
    return Entity(
        entity_id=eid, entity_type="RMAF_MPA",
        domain=Domain.AIR, agency=Agency.RMAF,
        callsign=eid, position=Position(lat, lon, 3000.0),
        heading_deg=heading,
        status=EntityStatus.ACTIVE,
    )


def _make_surface(eid, lat, lon):
    return Entity(
        entity_id=eid, entity_type="TANKER_CARGO",
        domain=Domain.MARITIME, agency=Agency.MMEA,
        callsign=eid, position=Position(lat, lon),
        status=EntityStatus.ACTIVE,
    )


class TestInterceptOrbitTransition:
    def test_fixed_wing_target_reached_does_not_fly_north(self, sim_start):
        """When a fixed-wing aircraft reaches its target, it should begin orbiting
        from its current bearing relative to the target — not fly toward due north
        of the target as if orbit_heading started at 0°."""
        store = EntityStore()
        # Aircraft arriving at the target from the east — bearing ~90° from target
        target = _make_surface("TARGET", 3.0, 101.0)
        # 300 m east of target (inside 500 m intercept radius)
        aircraft_lat, aircraft_lon = 3.0, 101.00269
        aircraft = _make_air("MPA", aircraft_lat, aircraft_lon, heading=270.0)
        store.add_entity(target)
        store.add_entity(aircraft)

        movement = InterceptMovement(
            entity_speed_knots=180.0, target_entity_id="TARGET",
            entity_store=store, pursuer_entity_id="MPA",
            min_speed_knots=150.0,  # fixed-wing minimum
        )

        # Prime _last_sim_time so subsequent dt is real
        movement.get_state(sim_start)

        # Advance 10 s. Buggy code: aircraft heads toward due-north of target,
        # so its bearing-from-target drifts from 90° (east) toward 0° (north).
        for i in range(1, 11):
            store.upsert_entity(aircraft)  # keep aircraft at its last orbit sample
            state = movement.get_state(sim_start + timedelta(seconds=i))
            # Simulate the main loop writing the state back to the entity
            aircraft.position = Position(state.lat, state.lon, state.alt_m)

        bearing_from_target = math.degrees(
            math.atan2(
                (state.lon - 101.0) * math.cos(math.radians(3.0)),
                state.lat - 3.0,
            )
        ) % 360.0
        # Aircraft should still be east-ish (has had time to start orbiting
        # tangentially). If the bug is present, bearing will have drifted
        # sharply toward 0° (north).
        diff = abs((bearing_from_target - 90 + 180) % 360 - 180)
        assert diff < 30.0, (
            f"aircraft's bearing from target drifted to {bearing_from_target:.1f}° "
            f"(expected near 90°, diff {diff:.1f}°). Orbit heading initialised "
            f"from north instead of from aircraft's arrival bearing."
        )

    def test_fixed_wing_target_vanished_does_not_teleport(self, sim_start):
        """When the target disappears, aircraft orbits its last known position.
        Initial orbit sample must not teleport radius-metres away from where it is."""
        store = EntityStore()
        target = _make_surface("TARGET", 3.0, 101.0)
        # 300 m east of target
        aircraft_lat, aircraft_lon = 3.0, 101.00269
        aircraft = _make_air("MPA", aircraft_lat, aircraft_lon, heading=270.0)
        store.add_entity(target)
        store.add_entity(aircraft)

        movement = InterceptMovement(
            entity_speed_knots=180.0, target_entity_id="TARGET",
            entity_store=store, pursuer_entity_id="MPA",
            min_speed_knots=150.0,
        )
        # Prime _last_sim_time / _last_heading
        movement.get_state(sim_start)

        # Target vanishes
        store._entities.pop("TARGET", None)

        # Bug symptom: orbit center is set to pursuer's current position,
        # so on the first sample the aircraft flies toward due-north of itself.
        # After 10 s at 150 kt, that's ~770 m straight north.
        for i in range(1, 11):
            state = movement.get_state(sim_start + timedelta(seconds=i))
            aircraft.position = Position(state.lat, state.lon, state.alt_m)
            store.upsert_entity(aircraft)

        # Net displacement direction from starting position
        dy = (state.lat - aircraft_lat) * 111_111.0
        dx = (state.lon - aircraft_lon) * 111_111.0 * math.cos(math.radians(aircraft_lat))
        travel_bearing = math.degrees(math.atan2(dx, dy)) % 360.0

        # Aircraft was heading 270° (west). With a correct tangent-style orbit
        # handoff the net travel over a few seconds should stay roughly in that
        # direction (±90°). If the bug is present it drifts sharply northward.
        diff = abs((travel_bearing - 270 + 180) % 360 - 180)
        assert diff < 90.0, (
            f"aircraft travel direction after target loss: {travel_bearing:.1f}° "
            f"(expected ~270° westbound, diff {diff:.1f}°). Orbit center anchored "
            f"on aircraft's own position so it flew north instead of continuing west."
        )
