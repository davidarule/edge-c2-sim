"""
Pursuit intercept course calculation.

Calculates an intercept heading toward a moving target, optionally
using lead pursuit (aim ahead of target) rather than tail chase
(aim directly at current position). Updates heading each tick.
"""

import math
from datetime import datetime

from geopy.distance import geodesic

from simulator.core.entity_store import EntityStore
from simulator.movement.waypoint import MovementState, _initial_bearing


class InterceptMovement:
    """Pursue and intercept a moving target entity."""

    def __init__(
        self,
        entity_speed_knots: float,
        target_entity_id: str,
        entity_store: EntityStore,
        intercept_radius_m: float = 500.0,
        lead_pursuit: bool = True,
        pursuer_entity_id: str | None = None,
    ) -> None:
        self._speed = entity_speed_knots
        self._target_id = target_entity_id
        self._store = entity_store
        self._intercept_radius = intercept_radius_m
        self._lead_pursuit = lead_pursuit
        self._pursuer_id = pursuer_entity_id
        self._intercepted = False
        self._last_heading = 0.0
        self._last_lat: float | None = None
        self._last_lon: float | None = None

    def get_state(self, sim_time: datetime) -> MovementState:
        """Calculate intercept heading toward target. Returns full speed toward target."""
        target = self._store.get_entity(self._target_id)
        pursuer = self._store.get_entity(self._pursuer_id) if self._pursuer_id else None

        if pursuer:
            p_lat = pursuer.position.latitude
            p_lon = pursuer.position.longitude
            p_alt = pursuer.position.altitude_m
        elif self._last_lat is not None:
            p_lat = self._last_lat
            p_lon = self._last_lon
            p_alt = 0.0
        else:
            # No position info yet — return zero state
            return MovementState(
                lat=0.0, lon=0.0, alt_m=0.0,
                heading_deg=0.0, speed_knots=0.0, course_deg=0.0,
            )

        if target is None:
            # Target removed — hold current heading and position
            return MovementState(
                lat=p_lat, lon=p_lon, alt_m=p_alt,
                heading_deg=self._last_heading,
                speed_knots=0.0,
                course_deg=self._last_heading,
            )

        t_lat = target.position.latitude
        t_lon = target.position.longitude

        # Check if already intercepted
        dist_m = geodesic((p_lat, p_lon), (t_lat, t_lon)).meters
        if dist_m <= self._intercept_radius:
            self._intercepted = True
            self._last_lat = p_lat
            self._last_lon = p_lon
            heading = _initial_bearing(p_lat, p_lon, t_lat, t_lon)
            self._last_heading = heading
            return MovementState(
                lat=p_lat, lon=p_lon, alt_m=p_alt,
                heading_deg=heading, speed_knots=0.0, course_deg=heading,
            )

        # Lead pursuit: project target position forward
        aim_lat, aim_lon = t_lat, t_lon
        if self._lead_pursuit and target.speed_knots > 0:
            # Estimate time to intercept
            closing_speed_knots = max(self._speed - target.speed_knots * 0.5, 1.0)
            dist_nm = dist_m / 1852.0
            time_to_intercept_h = dist_nm / closing_speed_knots
            time_to_intercept_s = time_to_intercept_h * 3600

            # Project target forward
            target_speed_ms = target.speed_knots * 0.514444
            target_course_rad = math.radians(target.course_deg)
            dx = target_speed_ms * time_to_intercept_s * math.sin(target_course_rad)
            dy = target_speed_ms * time_to_intercept_s * math.cos(target_course_rad)

            # Convert meters offset to lat/lon
            aim_lat = t_lat + dy / 111_111.0
            aim_lon = t_lon + dx / (111_111.0 * math.cos(math.radians(t_lat)))

        heading = _initial_bearing(p_lat, p_lon, aim_lat, aim_lon)
        self._last_heading = heading

        # Move pursuer toward target
        speed_ms = self._speed * 0.514444  # knots to m/s
        # We don't move position here — the main loop handles it via
        # the returned heading/speed. But for entities using this directly:
        self._last_lat = p_lat
        self._last_lon = p_lon

        return MovementState(
            lat=p_lat, lon=p_lon, alt_m=p_alt,
            heading_deg=heading, speed_knots=self._speed, course_deg=heading,
        )

    def is_intercepted(self) -> bool:
        """True when pursuer is within intercept_radius of target."""
        return self._intercepted

    def is_complete(self, sim_time: datetime) -> bool:
        """Intercept is complete when target is reached."""
        return self._intercepted
