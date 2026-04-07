"""Tests for waypoint movement."""

import math
from datetime import datetime, timedelta, timezone

import pytest
from geopy.distance import geodesic

from simulator.movement.waypoint import (
    MovementState, TurnParams, Waypoint, WaypointMovement, _initial_bearing,
    _angle_diff, _smooth_heading,
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


class TestTurnPhysics:
    """Tests for vessel turn-rate smoothing."""

    def test_angle_diff_positive(self):
        """Turn from 350° to 10° is +20° (right turn)."""
        assert abs(_angle_diff(350.0, 10.0) - 20.0) < 0.01

    def test_angle_diff_negative(self):
        """Turn from 10° to 350° is -20° (left turn)."""
        assert abs(_angle_diff(10.0, 350.0) + 20.0) < 0.01

    def test_smooth_heading_at_zero_time_returns_incoming(self):
        """At t=0 the vessel is still on its original heading."""
        tp = TurnParams(loa_m=100.0, k_coef=3.5, c_coef=2.5)
        h = _smooth_heading(0.0, 90.0, 180.0, 12.0, tp)
        assert abs(h - 90.0) < 1.0

    def test_smooth_heading_fully_complete_returns_outgoing(self):
        """Well past turn duration the vessel is on the new heading."""
        tp = TurnParams(loa_m=100.0, k_coef=3.5, c_coef=2.5)
        # Turn duration ≈ 90 / omega; give 10× that time
        h = _smooth_heading(5000.0, 0.0, 90.0, 12.0, tp)
        assert abs(h - 90.0) < 0.1

    def test_smooth_heading_monotonically_approaches_outgoing(self):
        """Heading should move from incoming toward outgoing without overshoot."""
        tp = TurnParams(loa_m=60.0, k_coef=3.0, c_coef=2.0)
        prev = 0.0
        for t in range(0, 300, 5):
            h = _smooth_heading(float(t), 0.0, 90.0, 15.0, tp)
            assert h >= prev - 0.01, f"Heading went backwards at t={t}: {h} < {prev}"
            assert h <= 90.01, f"Heading overshot at t={t}: {h}"
            prev = h

    def test_arc_heading_at_start_of_turn(self, scenario_start):
        """At the start of the arc window, heading should be near the incoming bearing."""
        tp = TurnParams(loa_m=100.0, k_coef=3.5, c_coef=2.5)
        wps = [
            Waypoint(lat=5.0, lon=100.0, speed_knots=12, time_offset=timedelta(0)),
            Waypoint(lat=5.0, lon=101.0, speed_knots=12, time_offset=timedelta(hours=1)),
            Waypoint(lat=6.0, lon=101.0, speed_knots=12, time_offset=timedelta(hours=2)),
        ]
        wm = WaypointMovement(wps, scenario_start, turn_params=tp)

        # At the very start of the arc (arc begins before waypoint), heading ≈ incoming (~90° east)
        assert len(wm._turn_arcs) == 1
        arc = wm._turn_arcs[0]
        t_arc_start = scenario_start + arc.t_start + timedelta(seconds=0.1)
        state = wm.get_state(t_arc_start)
        assert state.heading_deg > 80.0, (
            f"Heading at arc start should be near 90°, got {state.heading_deg:.1f}°"
        )

    def test_arc_heading_at_end_of_turn(self, scenario_start):
        """At the end of the arc window, heading should be near the outgoing bearing."""
        tp = TurnParams(loa_m=100.0, k_coef=3.5, c_coef=2.5)
        wps = [
            Waypoint(lat=5.0, lon=100.0, speed_knots=12, time_offset=timedelta(0)),
            Waypoint(lat=5.0, lon=101.0, speed_knots=12, time_offset=timedelta(hours=1)),
            Waypoint(lat=6.0, lon=101.0, speed_knots=12, time_offset=timedelta(hours=2)),
        ]
        wm = WaypointMovement(wps, scenario_start, turn_params=tp)

        arc = wm._turn_arcs[0]
        t_arc_end = scenario_start + arc.t_end - timedelta(seconds=0.1)
        state = wm.get_state(t_arc_end)
        # heading_out ≈ 0° (north); accept 350°–10° range
        assert state.heading_deg < 10.0 or state.heading_deg > 350.0, (
            f"Heading at arc end should be near 0°, got {state.heading_deg:.1f}°"
        )

    def test_arc_position_is_curved(self, scenario_start):
        """During arc, position should deviate from the straight corner path."""
        tp = TurnParams(loa_m=100.0, k_coef=3.5, c_coef=2.5)
        wps = [
            Waypoint(lat=5.0, lon=100.0, speed_knots=12, time_offset=timedelta(0)),
            Waypoint(lat=5.0, lon=101.0, speed_knots=12, time_offset=timedelta(hours=1)),
            Waypoint(lat=6.0, lon=101.0, speed_knots=12, time_offset=timedelta(hours=2)),
        ]
        wm = WaypointMovement(wps, scenario_start, turn_params=tp)

        # At mid-arc, position should be "inside" the corner (SW of waypoint for right turn)
        arc = wm._turn_arcs[0]
        t_mid = scenario_start + arc.t_start + (arc.t_end - arc.t_start) / 2
        state = wm.get_state(t_mid)
        # For this east→north right turn, mid-arc position should be SW of the waypoint
        assert state.lat <= 5.0 + 0.001, "Mid-arc lat should be near/south of waypoint lat"
        assert state.lon <= 101.0 + 0.001, "Mid-arc lon should be near/west of waypoint lon"

    def test_without_turn_params_heading_snaps(self, scenario_start):
        """Without TurnParams, heading should snap immediately at waypoint."""
        wps = [
            Waypoint(lat=5.0, lon=100.0, speed_knots=12, time_offset=timedelta(0)),
            Waypoint(lat=5.0, lon=101.0, speed_knots=12, time_offset=timedelta(hours=1)),
            Waypoint(lat=6.0, lon=101.0, speed_knots=12, time_offset=timedelta(hours=2)),
        ]
        wm = WaypointMovement(wps, scenario_start, turn_params=None)
        assert wm._turn_arcs == []

        t_just_after = scenario_start + timedelta(hours=1, seconds=1)
        state = wm.get_state(t_just_after)
        # Without arcs, heading should be near 0° (north) immediately
        assert state.heading_deg < 45.0, (
            f"Expected snapped heading near 0°, got {state.heading_deg:.1f}°"
        )

    def test_turn_rate_formula_vlcc(self):
        """Sanity-check: VLCC at 8kn should have turn rate ~0.14 deg/s."""
        # ω = (4.1 × 57.3) / (5.0 × 330) ≈ 0.143 deg/s
        tp = TurnParams(loa_m=330.0, k_coef=5.0, c_coef=4.0)
        # 100° turn at 8 knots
        h = _smooth_heading(0.0, 0.0, 100.0, 8.0, tp)
        assert abs(h - 0.0) < 1.0  # barely moved at t=0
        # After 1 second: ~0.14° turn
        h1 = _smooth_heading(1.0, 0.0, 100.0, 8.0, tp)
        assert 0.0 < h1 < 2.0  # small fraction of total turn


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
