"""Tests for waypoint movement."""

import math
from datetime import datetime, timedelta, timezone

import pytest
from geopy.distance import geodesic

from simulator.movement.waypoint import (
    MovementState, Waypoint, WaypointMovement, _initial_bearing,
)


@pytest.fixture
def scenario_start():
    return datetime(2026, 4, 15, 8, 0, 0, tzinfo=timezone.utc)


class TestWaypointMovement:
    def test_two_waypoints_midpoint_on_great_circle(self, scenario_start):
        """Midpoint between two waypoints should be on the great circle."""
        wp_a = Waypoint(lat=5.0, lon=118.0, speed_knots=10, time_offset=timedelta(minutes=0))
        wp_b = Waypoint(lat=6.0, lon=119.0, speed_knots=10, time_offset=timedelta(minutes=60))
        wm = WaypointMovement([wp_a, wp_b], scenario_start)

        mid_time = scenario_start + timedelta(minutes=30)
        state = wm.get_state(mid_time)

        # Midpoint should be roughly halfway
        assert 5.4 < state.lat < 5.6
        assert 118.4 < state.lon < 118.6

    def test_speed_interpolation(self, scenario_start):
        """Speed should interpolate linearly between waypoints."""
        wp_a = Waypoint(lat=5.0, lon=118.0, speed_knots=5, time_offset=timedelta(minutes=0))
        wp_b = Waypoint(lat=5.5, lon=118.5, speed_knots=15, time_offset=timedelta(minutes=60))
        wm = WaypointMovement([wp_a, wp_b], scenario_start)

        mid_time = scenario_start + timedelta(minutes=30)
        state = wm.get_state(mid_time)
        assert abs(state.speed_knots - 10.0) < 0.5

    def test_heading_north(self, scenario_start):
        """Heading should be ~0° when moving north."""
        wp_a = Waypoint(lat=5.0, lon=118.0, speed_knots=10, time_offset=timedelta(minutes=0))
        wp_b = Waypoint(lat=6.0, lon=118.0, speed_knots=10, time_offset=timedelta(minutes=60))
        wm = WaypointMovement([wp_a, wp_b], scenario_start)

        state = wm.get_state(scenario_start + timedelta(minutes=30))
        assert state.heading_deg < 5 or state.heading_deg > 355

    def test_heading_east(self, scenario_start):
        """Heading should be ~90° when moving east."""
        wp_a = Waypoint(lat=5.0, lon=118.0, speed_knots=10, time_offset=timedelta(minutes=0))
        wp_b = Waypoint(lat=5.0, lon=119.0, speed_knots=10, time_offset=timedelta(minutes=60))
        wm = WaypointMovement([wp_a, wp_b], scenario_start)

        state = wm.get_state(scenario_start + timedelta(minutes=30))
        assert 85 < state.heading_deg < 95

    def test_heading_south(self, scenario_start):
        """Heading should be ~180° when moving south."""
        wp_a = Waypoint(lat=6.0, lon=118.0, speed_knots=10, time_offset=timedelta(minutes=0))
        wp_b = Waypoint(lat=5.0, lon=118.0, speed_knots=10, time_offset=timedelta(minutes=60))
        wm = WaypointMovement([wp_a, wp_b], scenario_start)

        state = wm.get_state(scenario_start + timedelta(minutes=30))
        assert 175 < state.heading_deg < 185

    def test_before_first_waypoint(self, scenario_start):
        """Before first waypoint: entity at start, speed 0."""
        wp_a = Waypoint(lat=5.0, lon=118.0, speed_knots=10, time_offset=timedelta(minutes=5))
        wp_b = Waypoint(lat=6.0, lon=119.0, speed_knots=10, time_offset=timedelta(minutes=60))
        wm = WaypointMovement([wp_a, wp_b], scenario_start)

        state = wm.get_state(scenario_start)
        assert state.lat == 5.0
        assert state.lon == 118.0
        assert state.speed_knots == 0.0

    def test_after_last_waypoint(self, scenario_start):
        """After last waypoint: entity at end, speed 0."""
        wp_a = Waypoint(lat=5.0, lon=118.0, speed_knots=10, time_offset=timedelta(minutes=0))
        wp_b = Waypoint(lat=6.0, lon=119.0, speed_knots=10, time_offset=timedelta(minutes=60))
        wm = WaypointMovement([wp_a, wp_b], scenario_start)

        state = wm.get_state(scenario_start + timedelta(minutes=90))
        assert state.lat == 6.0
        assert state.lon == 119.0
        assert state.speed_knots == 0.0

    def test_metadata_override(self, scenario_start):
        """Metadata overrides should be returned when passing a waypoint."""
        wp_a = Waypoint(
            lat=5.0, lon=118.0, speed_knots=10,
            time_offset=timedelta(minutes=0),
            metadata_overrides={"ais_active": False},
        )
        wp_b = Waypoint(lat=6.0, lon=119.0, speed_knots=10, time_offset=timedelta(minutes=60))
        wm = WaypointMovement([wp_a, wp_b], scenario_start)

        state = wm.get_state(scenario_start + timedelta(minutes=30))
        assert state.metadata_overrides == {"ais_active": False}

    def test_is_complete(self, scenario_start):
        wp_a = Waypoint(lat=5.0, lon=118.0, speed_knots=10, time_offset=timedelta(minutes=0))
        wp_b = Waypoint(lat=6.0, lon=119.0, speed_knots=10, time_offset=timedelta(minutes=60))
        wm = WaypointMovement([wp_a, wp_b], scenario_start)

        assert not wm.is_complete(scenario_start + timedelta(minutes=30))
        assert wm.is_complete(scenario_start + timedelta(minutes=60))

    def test_total_duration(self, scenario_start):
        wp_a = Waypoint(lat=5.0, lon=118.0, speed_knots=10, time_offset=timedelta(minutes=0))
        wp_b = Waypoint(lat=6.0, lon=119.0, speed_knots=10, time_offset=timedelta(minutes=60))
        wm = WaypointMovement([wp_a, wp_b], scenario_start)

        assert wm.total_duration == timedelta(minutes=60)

    def test_single_waypoint(self, scenario_start):
        """Single waypoint: entity stationary."""
        wp = Waypoint(lat=5.0, lon=118.0, speed_knots=0, time_offset=timedelta(0))
        wm = WaypointMovement([wp], scenario_start)

        state = wm.get_state(scenario_start + timedelta(minutes=30))
        assert state.lat == 5.0
        assert state.lon == 118.0
        assert state.speed_knots == 0.0

    def test_sandakan_semporna_distance(self, scenario_start):
        """Known distance: Sandakan to Semporna ~200km. Verify travel time."""
        # Sandakan: 5.84, 118.07
        # Semporna: 4.48, 118.61
        dist = geodesic((5.84, 118.07), (4.48, 118.61)).nautical
        speed = 20  # knots
        travel_hours = dist / speed
        travel_min = travel_hours * 60

        wp_a = Waypoint(lat=5.84, lon=118.07, speed_knots=speed, time_offset=timedelta(0))
        wp_b = Waypoint(lat=4.48, lon=118.61, speed_knots=speed, time_offset=timedelta(minutes=travel_min))
        wm = WaypointMovement([wp_a, wp_b], scenario_start)

        # At 50% time, should be roughly 50% of distance
        mid = scenario_start + timedelta(minutes=travel_min / 2)
        state = wm.get_state(mid)

        dist_from_start = geodesic((5.84, 118.07), (state.lat, state.lon)).nautical
        dist_to_end = geodesic((state.lat, state.lon), (4.48, 118.61)).nautical

        # Should be roughly equidistant from start and end
        assert abs(dist_from_start - dist_to_end) < dist * 0.1

    def test_empty_waypoints_raises(self, scenario_start):
        with pytest.raises(ValueError):
            WaypointMovement([], scenario_start)


class TestInitialBearing:
    def test_bearing_north(self):
        b = _initial_bearing(0.0, 0.0, 1.0, 0.0)
        assert abs(b - 0.0) < 1.0

    def test_bearing_east(self):
        b = _initial_bearing(0.0, 0.0, 0.0, 1.0)
        assert abs(b - 90.0) < 1.0

    def test_bearing_south(self):
        b = _initial_bearing(1.0, 0.0, 0.0, 0.0)
        assert abs(b - 180.0) < 1.0

    def test_bearing_west(self):
        b = _initial_bearing(0.0, 1.0, 0.0, 0.0)
        assert abs(b - 270.0) < 1.0
