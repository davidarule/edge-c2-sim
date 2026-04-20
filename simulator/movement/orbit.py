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


def tangent_orbit_params(
    entity_lat: float,
    entity_lon: float,
    heading_deg: float,
    radius_m: float,
    direction: str = "CW",
) -> tuple[float, float, float]:
    """Compute orbit centre and initial angle so the entity begins on the circle
    with its current heading tangent to it.

    Prevents the teleport when a moving entity transitions into an orbit —
    instead of jumping radius-metres to an arbitrary arc, the entity stays
    where it is and the circle passes through its position with the correct
    tangent direction.

    Returns (centre_lat, centre_lon, initial_heading_deg).
    """
    if direction == "CW":
        bearing_to_centre = (heading_deg + 90.0) % 360.0
        position_angle = (heading_deg - 90.0) % 360.0
    else:  # CCW
        bearing_to_centre = (heading_deg - 90.0) % 360.0
        position_angle = (heading_deg + 90.0) % 360.0

    b_rad = math.radians(bearing_to_centre)
    d_lat = (radius_m * math.cos(b_rad)) / 111_111.0
    d_lon = (radius_m * math.sin(b_rad)) / (
        111_111.0 * max(math.cos(math.radians(entity_lat)), 0.01)
    )
    return entity_lat + d_lat, entity_lon + d_lon, position_angle


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
        target_offset_lat: float = 0.0,
        target_offset_lon: float = 0.0,
        capture_duration_s: float = 30.0,
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
        # Initial tangent-entry offset — used for a smooth transit->orbit
        # transition (no teleport, no heading snap). The offset decays
        # linearly to (0, 0) over capture_duration_s so that the orbit
        # converges onto the actual target centre within ~30 s.
        self._target_offset_lat = target_offset_lat
        self._target_offset_lon = target_offset_lon
        self._capture_duration_s = max(capture_duration_s, 0.001)
        self._capture_start: datetime | None = None
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

        # Capture-phase offset decay: start at 100% tangent offset so the
        # transition from transit is smooth, linearly decay to zero over
        # capture_duration_s so the orbit ends up centred on the target.
        if self._capture_start is None:
            self._capture_start = sim_time
        capture_elapsed = (sim_time - self._capture_start).total_seconds()
        offset_scale = max(0.0, 1.0 - (capture_elapsed / self._capture_duration_s))

        # Get center point (dynamic if tracking target)
        center_lat = self._center_lat
        center_lon = self._center_lon
        if self._target_id and self._entity_store:
            target = self._entity_store.get_entity(self._target_id)
            if target:
                # During the capture phase the offset eases from its
                # initial tangent value toward zero, so the orbit slides
                # onto the target's true centre over ~capture_duration_s.
                center_lat = (
                    target.position.latitude
                    + self._target_offset_lat * offset_scale
                )
                center_lon = (
                    target.position.longitude
                    + self._target_offset_lon * offset_scale
                )

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
