"""
Orbit/loiter movement — circular pattern around a center point or entity.

Supports:
- Fixed center point or dynamic tracking of a target entity
- Configurable radius, speed, direction (CW/CCW)
- Speed-derived orbit rate (replaces hardcoded 3 deg/s)
"""

import math
from datetime import datetime

from simulator.movement.waypoint import MovementState


class OrbitMovement:
    """Fly/sail a circular orbit pattern."""

    def __init__(
        self,
        center_lat: float,
        center_lon: float,
        altitude_m: float,
        speed_knots: float,
        orbit_radius_m: float = 3000.0,
        initial_heading: float = 0.0,
        direction: str = "CW",
        target_entity_id: str | None = None,
        entity_store=None,
    ) -> None:
        self._center_lat = center_lat
        self._center_lon = center_lon
        self._alt = altitude_m
        self._speed = speed_knots
        self._radius = orbit_radius_m
        self._orbit_angle = initial_heading
        self._direction = 1.0 if direction == "CW" else -1.0
        self._target_id = target_entity_id
        self._entity_store = entity_store
        self._last_sim_time: datetime | None = None

        # Derive orbit rate from speed and radius
        # rate = (speed_m_s / circumference) * 360 degrees
        speed_ms = speed_knots * 0.51444
        circumference = 2 * math.pi * orbit_radius_m
        if circumference > 0 and speed_ms > 0:
            self._orbit_rate_deg_s = (speed_ms / circumference) * 360.0
        else:
            self._orbit_rate_deg_s = 3.0  # fallback

    def get_state(self, sim_time: datetime) -> MovementState:
        if self._last_sim_time is not None:
            dt_s = (sim_time - self._last_sim_time).total_seconds()
        else:
            dt_s = 0.0

        # Advance orbit angle
        self._orbit_angle = (
            self._orbit_angle + self._direction * self._orbit_rate_deg_s * dt_s
        ) % 360.0

        # Get center point (dynamic if tracking target)
        center_lat = self._center_lat
        center_lon = self._center_lon
        if self._target_id and self._entity_store:
            target = self._entity_store.get_entity(self._target_id)
            if target:
                center_lat = target.position.latitude
                center_lon = target.position.longitude

        # Position on the orbit circle
        angle_rad = math.radians(self._orbit_angle)
        lat = center_lat + (self._radius * math.cos(angle_rad)) / 111_111.0
        lon = center_lon + (self._radius * math.sin(angle_rad)) / (
            111_111.0 * math.cos(math.radians(center_lat))
        )

        # Course is tangent to orbit (perpendicular to radius vector)
        if self._direction > 0:
            course = (self._orbit_angle + 90.0) % 360.0
        else:
            course = (self._orbit_angle - 90.0) % 360.0

        self._last_sim_time = sim_time

        return MovementState(
            lat=lat, lon=lon, alt_m=self._alt,
            heading_deg=course, speed_knots=self._speed, course_deg=course,
        )

    def is_complete(self, sim_time: datetime) -> bool:
        """Orbit never completes — entity circles until replaced."""
        return False
