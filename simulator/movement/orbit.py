"""
Orbit/loiter movement for fixed-wing aircraft.

Flies a clockwise circular pattern around a center point at a given
speed and radius. Used when fixed-wing aircraft reach their destination
or intercept target and need to maintain flight.
"""

import math
from datetime import datetime

from simulator.movement.waypoint import MovementState, _initial_bearing

# Default orbit parameters
_DEFAULT_ORBIT_RADIUS_M = 3000.0  # ~3km
_ORBIT_RATE_DEG_S = 3.0  # ~2 min per full circle


class OrbitMovement:
    """Fly a circular orbit pattern around a fixed point."""

    def __init__(
        self,
        center_lat: float,
        center_lon: float,
        altitude_m: float,
        speed_knots: float,
        orbit_radius_m: float = _DEFAULT_ORBIT_RADIUS_M,
        initial_heading: float = 0.0,
    ) -> None:
        self._center_lat = center_lat
        self._center_lon = center_lon
        self._alt = altitude_m
        self._speed = speed_knots
        self._radius = orbit_radius_m
        self._orbit_angle = initial_heading  # position angle on the circle
        self._last_sim_time: datetime | None = None

    def get_state(self, sim_time: datetime) -> MovementState:
        """Advance position along circular orbit."""
        if self._last_sim_time is not None:
            dt_s = (sim_time - self._last_sim_time).total_seconds()
        else:
            dt_s = 0.0

        # Advance orbit angle (clockwise)
        self._orbit_angle = (self._orbit_angle + _ORBIT_RATE_DEG_S * dt_s) % 360.0

        # Position on the orbit circle
        angle_rad = math.radians(self._orbit_angle)
        lat = self._center_lat + (self._radius * math.cos(angle_rad)) / 111_111.0
        lon = self._center_lon + (self._radius * math.sin(angle_rad)) / (
            111_111.0 * math.cos(math.radians(self._center_lat))
        )

        # Course is tangent to orbit (perpendicular to radius vector)
        course = (self._orbit_angle + 90.0) % 360.0

        self._last_sim_time = sim_time

        return MovementState(
            lat=lat, lon=lon, alt_m=self._alt,
            heading_deg=course, speed_knots=self._speed, course_deg=course,
        )

    def is_complete(self, sim_time: datetime) -> bool:
        """Orbit never completes — aircraft circles indefinitely."""
        return False
