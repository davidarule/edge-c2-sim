"""Tests for approach movement — focusing on the arrival transition."""

import math
from datetime import datetime, timedelta, timezone

import pytest
from geopy.distance import geodesic

from simulator.movement.approach import ApproachMovement


@pytest.fixture
def start_time():
    return datetime(2026, 4, 19, 0, 0, 0, tzinfo=timezone.utc)


class TestApproachArrival:
    def test_arrival_does_not_teleport_to_destination(self, start_time):
        """On arrival, the entity should stop at its current position — not teleport
        the ~100m remaining to the exact destination."""
        # Start very close to destination so the first tick triggers arrival
        start_lat, start_lon = 3.0, 101.0
        dest_lat, dest_lon = 3.0005, 101.0  # ~55 m north (inside 100 m threshold)

        approach = ApproachMovement(
            start_lat=start_lat, start_lon=start_lon,
            dest_lat=dest_lat, dest_lon=dest_lon,
            initial_speed_knots=20.0, final_speed_knots=2.0,
            approach_distance_nm=1.0, start_time=start_time,
        )
        state = approach.get_state(start_time + timedelta(seconds=1))

        assert approach.is_complete(state_time := start_time + timedelta(seconds=1))

        # Arrival position should be near start_lat/start_lon, NOT exactly at dest
        jump_m = geodesic((state.lat, state.lon), (start_lat, start_lon)).meters
        dist_to_dest = geodesic((state.lat, state.lon), (dest_lat, dest_lon)).meters
        assert jump_m < 20.0, (
            f"entity jumped {jump_m:.0f} m from its position on arrival — "
            f"should have stopped where it was"
        )
        assert dist_to_dest > 0.1, (
            "entity teleported exactly onto destination — that's the bug"
        )
