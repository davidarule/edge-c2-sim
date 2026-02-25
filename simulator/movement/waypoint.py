"""
Waypoint-based movement with great-circle interpolation.

Given a list of waypoints with (lat, lon, speed, time), interpolates
the entity's position at any simulation time. Uses great-circle
(geodesic) math for accurate lat/lon interpolation over distances
up to hundreds of kilometers.
"""

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from geopy.distance import geodesic


@dataclass
class MovementState:
    """Interpolated entity state at a point in time."""
    lat: float
    lon: float
    alt_m: float
    heading_deg: float  # True heading 0-360
    speed_knots: float
    course_deg: float   # Course over ground
    metadata_overrides: dict[str, Any] | None = None


@dataclass
class Waypoint:
    """A single waypoint in a movement plan."""
    lat: float
    lon: float
    alt_m: float = 0.0
    speed_knots: float = 0.0
    time_offset: timedelta = field(default_factory=timedelta)
    metadata_overrides: dict[str, Any] | None = None


def _initial_bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate initial bearing (forward azimuth) between two points.
    Returns bearing in degrees [0, 360)."""
    lat1_r = math.radians(lat1)
    lat2_r = math.radians(lat2)
    dlon_r = math.radians(lon2 - lon1)

    x = math.sin(dlon_r) * math.cos(lat2_r)
    y = (math.cos(lat1_r) * math.sin(lat2_r) -
         math.sin(lat1_r) * math.cos(lat2_r) * math.cos(dlon_r))

    bearing = math.degrees(math.atan2(x, y))
    return bearing % 360.0


def _interpolate_geodesic(
    lat1: float, lon1: float, lat2: float, lon2: float, fraction: float
) -> tuple[float, float]:
    """Interpolate along great circle between two points.
    fraction: 0.0 = start, 1.0 = end."""
    if fraction <= 0.0:
        return lat1, lon1
    if fraction >= 1.0:
        return lat2, lon2

    # Convert to radians
    lat1_r = math.radians(lat1)
    lon1_r = math.radians(lon1)
    lat2_r = math.radians(lat2)
    lon2_r = math.radians(lon2)

    # Angular distance
    d = 2 * math.asin(math.sqrt(
        math.sin((lat2_r - lat1_r) / 2) ** 2 +
        math.cos(lat1_r) * math.cos(lat2_r) *
        math.sin((lon2_r - lon1_r) / 2) ** 2
    ))

    if d < 1e-12:
        return lat1, lon1

    a = math.sin((1 - fraction) * d) / math.sin(d)
    b = math.sin(fraction * d) / math.sin(d)

    x = a * math.cos(lat1_r) * math.cos(lon1_r) + b * math.cos(lat2_r) * math.cos(lon2_r)
    y = a * math.cos(lat1_r) * math.sin(lon1_r) + b * math.cos(lat2_r) * math.sin(lon2_r)
    z = a * math.sin(lat1_r) + b * math.sin(lat2_r)

    lat = math.atan2(z, math.sqrt(x ** 2 + y ** 2))
    lon = math.atan2(y, x)

    return math.degrees(lat), math.degrees(lon)


class WaypointMovement:
    """Moves an entity along a series of time-stamped waypoints using
    great-circle interpolation."""

    def __init__(self, waypoints: list[Waypoint], scenario_start: datetime) -> None:
        if not waypoints:
            raise ValueError("At least one waypoint required")
        self._waypoints = sorted(waypoints, key=lambda w: w.time_offset)
        self._scenario_start = scenario_start

    def get_state(self, sim_time: datetime) -> MovementState:
        """Return interpolated position, heading, speed for given sim_time."""
        elapsed = sim_time - self._scenario_start
        wps = self._waypoints

        # Before first waypoint
        if elapsed <= wps[0].time_offset:
            wp = wps[0]
            heading = 0.0
            if len(wps) > 1:
                heading = _initial_bearing(wp.lat, wp.lon, wps[1].lat, wps[1].lon)
            return MovementState(
                lat=wp.lat, lon=wp.lon, alt_m=wp.alt_m,
                heading_deg=heading, speed_knots=0.0, course_deg=heading,
                metadata_overrides=wp.metadata_overrides,
            )

        # After last waypoint
        if elapsed >= wps[-1].time_offset:
            wp = wps[-1]
            heading = 0.0
            if len(wps) > 1:
                heading = _initial_bearing(wps[-2].lat, wps[-2].lon, wp.lat, wp.lon)
            return MovementState(
                lat=wp.lat, lon=wp.lon, alt_m=wp.alt_m,
                heading_deg=heading, speed_knots=0.0, course_deg=heading,
                metadata_overrides=wp.metadata_overrides,
            )

        # Find the segment we're on
        for i in range(len(wps) - 1):
            wp_a = wps[i]
            wp_b = wps[i + 1]
            if wp_a.time_offset <= elapsed <= wp_b.time_offset:
                seg_duration = (wp_b.time_offset - wp_a.time_offset).total_seconds()
                if seg_duration <= 0:
                    # Instant jump
                    return MovementState(
                        lat=wp_b.lat, lon=wp_b.lon, alt_m=wp_b.alt_m,
                        heading_deg=_initial_bearing(wp_a.lat, wp_a.lon, wp_b.lat, wp_b.lon),
                        speed_knots=wp_b.speed_knots,
                        course_deg=_initial_bearing(wp_a.lat, wp_a.lon, wp_b.lat, wp_b.lon),
                    )

                fraction = (elapsed - wp_a.time_offset).total_seconds() / seg_duration
                lat, lon = _interpolate_geodesic(
                    wp_a.lat, wp_a.lon, wp_b.lat, wp_b.lon, fraction
                )

                # Altitude interpolation (linear)
                alt = wp_a.alt_m + (wp_b.alt_m - wp_a.alt_m) * fraction

                # Speed interpolation (linear between waypoint speeds)
                speed = wp_a.speed_knots + (wp_b.speed_knots - wp_a.speed_knots) * fraction

                # Heading: bearing from current position to next waypoint
                heading = _initial_bearing(lat, lon, wp_b.lat, wp_b.lon)
                course = _initial_bearing(wp_a.lat, wp_a.lon, wp_b.lat, wp_b.lon)

                # Metadata overrides from the most recently passed waypoint
                meta = wp_a.metadata_overrides

                return MovementState(
                    lat=lat, lon=lon, alt_m=alt,
                    heading_deg=heading, speed_knots=speed, course_deg=course,
                    metadata_overrides=meta,
                )

        # Fallback (shouldn't reach here)
        wp = wps[-1]
        return MovementState(
            lat=wp.lat, lon=wp.lon, alt_m=wp.alt_m,
            heading_deg=0.0, speed_knots=0.0, course_deg=0.0,
        )

    def is_complete(self, sim_time: datetime) -> bool:
        """True if sim_time is past the last waypoint."""
        elapsed = sim_time - self._scenario_start
        return elapsed >= self._waypoints[-1].time_offset

    @property
    def total_duration(self) -> timedelta:
        """Time from first to last waypoint."""
        return self._waypoints[-1].time_offset - self._waypoints[0].time_offset

    @property
    def waypoints(self) -> list[Waypoint]:
        return list(self._waypoints)
