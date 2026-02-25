"""Tests for patrol movement."""

from datetime import datetime, timedelta, timezone

import pytest
from shapely.geometry import Polygon, Point

from simulator.movement.patrol import PatrolMovement


@pytest.fixture
def patrol_polygon():
    """A roughly 50km x 50km box in ESSZONE waters."""
    return Polygon([
        (118.0, 5.0),  # (lon, lat) — Shapely convention
        (118.5, 5.0),
        (118.5, 5.5),
        (118.0, 5.5),
        (118.0, 5.0),
    ])


@pytest.fixture
def scenario_start():
    return datetime(2026, 4, 15, 8, 0, 0, tzinfo=timezone.utc)


class TestPatrolMovement:
    def test_position_inside_polygon(self, patrol_polygon, scenario_start):
        """Entity position should always be inside the patrol polygon."""
        pm = PatrolMovement(
            polygon=patrol_polygon,
            speed_range_knots=(5, 10),
            seed=42,
            scenario_start=scenario_start,
        )
        for minutes in range(0, 120, 5):
            state = pm.get_state(scenario_start + timedelta(minutes=minutes))
            # Shapely uses (lon, lat) convention
            point = Point(state.lon, state.lat)
            # Allow small noise tolerance (point should be close to polygon)
            assert patrol_polygon.buffer(0.01).contains(point), \
                f"Position ({state.lat}, {state.lon}) outside polygon at t+{minutes}m"

    def test_speed_in_range(self, patrol_polygon, scenario_start):
        """Speed should be within specified range (or 0 during dwell)."""
        pm = PatrolMovement(
            polygon=patrol_polygon,
            speed_range_knots=(5, 10),
            seed=42,
            scenario_start=scenario_start,
        )
        for minutes in range(0, 60, 2):
            state = pm.get_state(scenario_start + timedelta(minutes=minutes))
            # Speed is either 0 (dwell) or within range (with interpolation tolerance)
            assert state.speed_knots >= 0
            assert state.speed_knots <= 12  # Allow some interpolation overshoot

    def test_never_completes(self, patrol_polygon, scenario_start):
        """Patrol movement should never report as complete."""
        pm = PatrolMovement(
            polygon=patrol_polygon,
            speed_range_knots=(5, 10),
            seed=42,
            scenario_start=scenario_start,
        )
        assert not pm.is_complete(scenario_start + timedelta(hours=10))

    def test_reproducible_with_seed(self, patrol_polygon, scenario_start):
        """Same seed should produce same patrol pattern."""
        pm1 = PatrolMovement(
            polygon=patrol_polygon, speed_range_knots=(5, 10),
            seed=123, scenario_start=scenario_start,
        )
        pm2 = PatrolMovement(
            polygon=patrol_polygon, speed_range_knots=(5, 10),
            seed=123, scenario_start=scenario_start,
        )
        t = scenario_start + timedelta(minutes=10)
        s1 = pm1.get_state(t)
        s2 = pm2.get_state(t)
        assert abs(s1.lat - s2.lat) < 1e-10
        assert abs(s1.lon - s2.lon) < 1e-10

    def test_dwell_time(self, patrol_polygon, scenario_start):
        """During dwell, speed should be 0."""
        pm = PatrolMovement(
            polygon=patrol_polygon,
            speed_range_knots=(5, 10),
            dwell_time_range_s=(60, 60),  # Fixed 60s dwell
            seed=42,
            scenario_start=scenario_start,
        )
        # Check many time points — some should have speed 0 (dwell)
        dwell_found = False
        for seconds in range(0, 3600, 10):
            state = pm.get_state(scenario_start + timedelta(seconds=seconds))
            if state.speed_knots == 0.0:
                dwell_found = True
                break
        assert dwell_found, "Expected at least one dwell period in first hour"
