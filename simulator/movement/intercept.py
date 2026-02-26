"""
Pursuit intercept course calculation.

Calculates an intercept heading toward a moving target, optionally
using lead pursuit (aim ahead of target) rather than tail chase
(aim directly at current position). Updates heading each tick.

Fixed-wing aircraft orbit at min_speed when intercepted rather than
stopping (which would be a crash).
"""

import math
from datetime import datetime

from geopy.distance import geodesic

from simulator.core.entity_store import EntityStore
from simulator.movement.waypoint import MovementState, _initial_bearing

# Orbit radius in meters for fixed-wing loiter pattern
_ORBIT_RADIUS_M = 3000.0  # ~3km orbit radius
# Degrees per second of heading change for orbit (~2 min for full circle)
_ORBIT_RATE_DEG_S = 3.0


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
        min_speed_knots: float = 0.0,
    ) -> None:
        self._speed = entity_speed_knots
        self._target_id = target_entity_id
        self._store = entity_store
        self._intercept_radius = intercept_radius_m
        self._lead_pursuit = lead_pursuit
        self._pursuer_id = pursuer_entity_id
        self._min_speed = min_speed_knots
        self._intercepted = False
        self._last_heading = 0.0
        self._last_lat: float | None = None
        self._last_lon: float | None = None
        self._last_alt: float = 0.0
        self._last_sim_time: datetime | None = None
        # Orbit state
        self._orbit_center_lat: float | None = None
        self._orbit_center_lon: float | None = None
        self._orbit_heading: float = 0.0

    def _orbit_state(
        self, p_lat: float, p_lon: float, p_alt: float,
        center_lat: float, center_lon: float,
        sim_time: datetime,
    ) -> MovementState:
        """Fly a circular orbit pattern around a center point."""
        orbit_speed = self._min_speed

        if self._last_sim_time is not None:
            dt_s = (sim_time - self._last_sim_time).total_seconds()
        else:
            dt_s = 0.0

        # Advance orbit heading (clockwise)
        self._orbit_heading = (self._orbit_heading + _ORBIT_RATE_DEG_S * dt_s) % 360.0

        # Calculate desired position on the orbit circle
        orbit_rad = math.radians(self._orbit_heading)
        target_lat = center_lat + (_ORBIT_RADIUS_M * math.cos(orbit_rad)) / 111_111.0
        target_lon = center_lon + (_ORBIT_RADIUS_M * math.sin(orbit_rad)) / (
            111_111.0 * math.cos(math.radians(center_lat))
        )

        # Move toward the orbit point
        heading = _initial_bearing(p_lat, p_lon, target_lat, target_lon)

        if dt_s > 0:
            speed_ms = orbit_speed * 0.514444
            move_m = speed_ms * dt_s
            heading_rad = math.radians(heading)
            dlat = (move_m * math.cos(heading_rad)) / 111_111.0
            dlon = (move_m * math.sin(heading_rad)) / (
                111_111.0 * math.cos(math.radians(p_lat))
            )
            p_lat += dlat
            p_lon += dlon

        # Course is tangent to orbit (perpendicular to radius = orbit_heading + 90)
        course = (self._orbit_heading + 90.0) % 360.0

        self._last_lat = p_lat
        self._last_lon = p_lon
        self._last_alt = p_alt
        self._last_heading = course
        self._last_sim_time = sim_time

        return MovementState(
            lat=p_lat, lon=p_lon, alt_m=p_alt,
            heading_deg=course, speed_knots=orbit_speed, course_deg=course,
        )

    def get_state(self, sim_time: datetime) -> MovementState:
        """Calculate intercept course and advance pursuer position toward target."""
        target = self._store.get_entity(self._target_id)
        pursuer = self._store.get_entity(self._pursuer_id) if self._pursuer_id else None

        if pursuer:
            p_lat = pursuer.position.latitude
            p_lon = pursuer.position.longitude
            p_alt = pursuer.position.altitude_m
        elif self._last_lat is not None:
            p_lat = self._last_lat
            p_lon = self._last_lon
            p_alt = self._last_alt
        else:
            # No position info yet — return zero state
            return MovementState(
                lat=0.0, lon=0.0, alt_m=0.0,
                heading_deg=0.0, speed_knots=0.0, course_deg=0.0,
            )

        if target is None:
            # Target removed
            if self._min_speed > 0:
                # Fixed-wing: orbit last known position
                if self._orbit_center_lat is None:
                    self._orbit_center_lat = p_lat
                    self._orbit_center_lon = p_lon
                    self._orbit_heading = self._last_heading
                return self._orbit_state(
                    p_lat, p_lon, p_alt,
                    self._orbit_center_lat, self._orbit_center_lon,
                    sim_time,
                )
            # Non-fixed-wing: hold position
            self._last_lat = p_lat
            self._last_lon = p_lon
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

            if self._min_speed > 0:
                # Fixed-wing: orbit around the target
                return self._orbit_state(
                    p_lat, p_lon, p_alt,
                    t_lat, t_lon,
                    sim_time,
                )

            # Non-fixed-wing: stop at intercept point
            self._last_lat = p_lat
            self._last_lon = p_lon
            heading = _initial_bearing(p_lat, p_lon, t_lat, t_lon)
            self._last_heading = heading
            self._last_sim_time = sim_time
            return MovementState(
                lat=p_lat, lon=p_lon, alt_m=p_alt,
                heading_deg=heading, speed_knots=0.0, course_deg=heading,
            )

        # Lead pursuit: project target position forward
        aim_lat, aim_lon = t_lat, t_lon
        if self._lead_pursuit and target.speed_knots > 0:
            closing_speed_knots = max(self._speed - target.speed_knots * 0.5, 1.0)
            dist_nm = dist_m / 1852.0
            time_to_intercept_h = dist_nm / closing_speed_knots
            time_to_intercept_s = time_to_intercept_h * 3600

            target_speed_ms = target.speed_knots * 0.514444
            target_course_rad = math.radians(target.course_deg)
            dx = target_speed_ms * time_to_intercept_s * math.sin(target_course_rad)
            dy = target_speed_ms * time_to_intercept_s * math.cos(target_course_rad)

            aim_lat = t_lat + dy / 111_111.0
            aim_lon = t_lon + dx / (111_111.0 * math.cos(math.radians(t_lat)))

        heading = _initial_bearing(p_lat, p_lon, aim_lat, aim_lon)
        self._last_heading = heading

        # Calculate time delta and advance pursuer position
        if self._last_sim_time is not None:
            dt_s = (sim_time - self._last_sim_time).total_seconds()
        else:
            dt_s = 0.0

        if dt_s > 0:
            speed_ms = self._speed * 0.514444  # knots to m/s
            move_m = speed_ms * dt_s

            # Don't overshoot the target
            if move_m > dist_m:
                move_m = dist_m

            heading_rad = math.radians(heading)
            dlat = (move_m * math.cos(heading_rad)) / 111_111.0
            dlon = (move_m * math.sin(heading_rad)) / (
                111_111.0 * math.cos(math.radians(p_lat))
            )
            p_lat += dlat
            p_lon += dlon

        self._last_lat = p_lat
        self._last_lon = p_lon
        self._last_alt = p_alt
        self._last_sim_time = sim_time

        return MovementState(
            lat=p_lat, lon=p_lon, alt_m=p_alt,
            heading_deg=heading, speed_knots=self._speed, course_deg=heading,
        )

    def is_intercepted(self) -> bool:
        """True when pursuer is within intercept_radius of target."""
        return self._intercepted

    def is_complete(self, sim_time: datetime) -> bool:
        """Intercept is complete when target is reached (non-fixed-wing only)."""
        # Fixed-wing intercepts never "complete" — they orbit indefinitely
        if self._min_speed > 0:
            return False
        return self._intercepted
