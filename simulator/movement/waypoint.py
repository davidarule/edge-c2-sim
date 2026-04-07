"""
Waypoint-based movement with great-circle interpolation.

Given a list of waypoints with (lat, lon, speed, time), interpolates
the entity's position at any simulation time. Uses great-circle
(geodesic) math for accurate lat/lon interpolation over distances
up to hundreds of kilometers.

Turn physics (when TurnParams provided):
  Turning radius  R = K × LOA  (metres, speed-independent)
  Tangent distance d = R × tan(|δ|/2)
  The vessel leaves the straight segment d metres before each waypoint,
  follows a circular arc, and rejoins the next segment d metres after it.
  Both position AND heading are arc-derived during the turn window.
"""

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from geopy.distance import geodesic


@dataclass
class TurnParams:
    """Physical turning characteristics for a vessel class."""
    loa_m: float    # Length overall (metres)
    k_coef: float   # Turning radius coefficient (vessel class)
    c_coef: float   # Time-constant coefficient (unused now, kept for API compat)


def _angle_diff(a: float, b: float) -> float:
    """Signed shortest angular difference b − a, in (−180, 180]."""
    d = (b - a) % 360.0
    if d > 180.0:
        d -= 360.0
    return d


def _smooth_heading(
    t_since_wp: float,
    heading_in: float,
    heading_out: float,
    speed_knots: float,
    tp: TurnParams,
) -> float:
    """First-order lag heading smoother (kept for API compatibility / testing).
    The WaypointMovement class uses arc paths instead of this function.
    """
    delta = _angle_diff(heading_in, heading_out)
    if abs(delta) < 0.5:
        return heading_out

    speed_ms = speed_knots * 0.51444
    if speed_ms < 0.1:
        return heading_out

    omega = (speed_ms * 57.3) / (tp.k_coef * tp.loa_m)
    omega = max(0.05, min(omega, 45.0))
    turn_duration = abs(delta) / omega

    if t_since_wp >= turn_duration:
        return heading_out

    tau = max((tp.loa_m / speed_ms) * tp.c_coef, 0.1)
    denom = 1.0 - math.exp(-turn_duration / tau)
    if denom < 1e-6:
        progress = t_since_wp / turn_duration
    else:
        progress = (1.0 - math.exp(-t_since_wp / tau)) / denom

    return (heading_in + delta * max(0.0, min(progress, 1.0))) % 360.0


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


@dataclass
class _TurnArc:
    """Precomputed circular arc for a single waypoint turn."""
    wp_idx: int           # Index of the turn waypoint in self._waypoints
    t_start: timedelta    # Elapsed time when arc begins (before waypoint)
    t_end: timedelta      # Elapsed time when arc ends (after waypoint)
    center_e: float       # Arc center, metres east of waypoint
    center_n: float       # Arc center, metres north of waypoint
    radius: float         # Turning radius (metres)
    theta_start: float    # Start angle from centre (standard math radians)
    delta_rad: float      # Signed arc sweep: >0 right turn, <0 left turn
    speed_knots: float    # Speed during arc (from waypoint)
    alt_m: float          # Altitude during arc


def _initial_bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate initial bearing (forward azimuth) between two points.
    Returns bearing in degrees [0, 360)."""
    lat1_r = math.radians(lat1)
    lat2_r = math.radians(lat2)
    dlon_r = math.radians(lon2 - lon1)

    x = math.sin(dlon_r) * math.cos(lat2_r)
    y = (math.cos(lat1_r) * math.sin(lat2_r) -
         math.sin(lat1_r) * math.cos(lat2_r) * math.cos(dlon_r))

    return math.degrees(math.atan2(x, y)) % 360.0


def _interpolate_geodesic(
    lat1: float, lon1: float, lat2: float, lon2: float, fraction: float
) -> tuple[float, float]:
    """Interpolate along great circle between two points.
    fraction: 0.0 = start, 1.0 = end."""
    if fraction <= 0.0:
        return lat1, lon1
    if fraction >= 1.0:
        return lat2, lon2

    lat1_r = math.radians(lat1)
    lon1_r = math.radians(lon1)
    lat2_r = math.radians(lat2)
    lon2_r = math.radians(lon2)

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

    return math.degrees(math.atan2(z, math.sqrt(x**2 + y**2))), math.degrees(math.atan2(y, x))


class WaypointMovement:
    """Moves an entity along time-stamped waypoints using great-circle interpolation.

    When *turn_params* is provided, waypoint transitions follow circular arcs
    instead of snapping at corners.  Both the position trail and the heading
    reflect the arc geometry.  The arc radius is R = K × LOA (metres), which
    is speed-independent; only the timing of the arc window changes with speed.
    """

    def __init__(
        self,
        waypoints: list[Waypoint],
        scenario_start: datetime,
        turn_params: TurnParams | None = None,
    ) -> None:
        if not waypoints:
            raise ValueError("At least one waypoint required")
        self._waypoints = sorted(waypoints, key=lambda w: w.time_offset)
        self._scenario_start = scenario_start
        self._turn_params = turn_params
        self._turn_arcs: list[_TurnArc] = (
            self._precompute_arcs() if turn_params else []
        )

    # ── Arc precomputation ────────────────────────────────────────────────────

    def _precompute_arcs(self) -> list[_TurnArc]:
        """Build a _TurnArc for every meaningful course change."""
        tp = self._turn_params
        wps = self._waypoints
        R = tp.k_coef * tp.loa_m  # turning radius (m) — speed-independent

        arcs: list[_TurnArc] = []

        for i in range(1, len(wps) - 1):
            wp_prev = wps[i - 1]
            wp_curr = wps[i]
            wp_next = wps[i + 1]

            bearing_in  = _initial_bearing(wp_prev.lat, wp_prev.lon, wp_curr.lat, wp_curr.lon)
            bearing_out = _initial_bearing(wp_curr.lat, wp_curr.lon, wp_next.lat, wp_next.lon)
            delta_deg   = _angle_diff(bearing_in, bearing_out)

            # Skip trivial or near-180° turns (geometry degenerates)
            if abs(delta_deg) < 1.0 or abs(delta_deg) > 150.0:
                continue

            delta_rad = math.radians(delta_deg)
            d_tan = R * math.tan(abs(delta_rad) / 2)  # tangent length (m)

            speed_kn = wp_curr.speed_knots if wp_curr.speed_knots > 0.1 else 1.0
            speed_ms = speed_kn * 0.51444
            t_half_s = d_tan / speed_ms  # seconds from waypoint to arc start/end

            t_start = wp_curr.time_offset - timedelta(seconds=t_half_s)
            t_end   = wp_curr.time_offset + timedelta(seconds=t_half_s)

            # Clamp so arcs don't overlap adjacent waypoints
            t_start = max(t_start, wp_prev.time_offset + timedelta(seconds=0.5))
            t_end   = min(t_end,   wp_next.time_offset - timedelta(seconds=0.5))

            if t_end <= t_start:
                continue

            # ── Arc geometry (local East-North coords centred on wp_curr) ──
            alpha_rad = math.radians(bearing_in)
            sin_a, cos_a = math.sin(alpha_rad), math.cos(alpha_rad)

            # P1 = tangent point d_tan *before* waypoint on incoming bearing
            p1_e = -sin_a * d_tan
            p1_n = -cos_a * d_tan

            # Centre is R perpendicular to incoming direction at P1
            if delta_deg > 0:          # right turn → centre to the right
                perp_e, perp_n = cos_a, -sin_a
            else:                      # left turn  → centre to the left
                perp_e, perp_n = -cos_a, sin_a

            center_e = p1_e + R * perp_e
            center_n = p1_n + R * perp_n

            # Start angle: standard-math atan2 from centre to P1
            theta_start = math.atan2(p1_n - center_n, p1_e - center_e)

            arcs.append(_TurnArc(
                wp_idx=i,
                t_start=t_start,
                t_end=t_end,
                center_e=center_e,
                center_n=center_n,
                radius=R,
                theta_start=theta_start,
                delta_rad=delta_rad,
                speed_knots=speed_kn,
                alt_m=wp_curr.alt_m,
            ))

        return arcs

    # ── Arc state computation ─────────────────────────────────────────────────

    def _arc_state(self, elapsed: timedelta, arc: _TurnArc) -> MovementState:
        """Return MovementState interpolated along the circular arc."""
        arc_dur = (arc.t_end - arc.t_start).total_seconds()
        t_in   = (elapsed - arc.t_start).total_seconds()
        progress = max(0.0, min(1.0, t_in / arc_dur if arc_dur > 0 else 0.0))

        # Sweep angle: theta_end = theta_start − delta_rad
        # (right turn = CW bearing = decreasing standard-math angle)
        theta = arc.theta_start - arc.delta_rad * progress

        # Position in local (E, N) relative to waypoint
        arc_e = arc.center_e + arc.radius * math.cos(theta)
        arc_n = arc.center_n + arc.radius * math.sin(theta)

        # Convert to lat/lon (flat-earth OK for small arcs)
        wp = self._waypoints[arc.wp_idx]
        lat = wp.lat + arc_n / 111320.0
        lon = wp.lon + arc_e / (111320.0 * math.cos(math.radians(wp.lat)))

        # Tangent direction (unit vector in East-North) → bearing
        if arc.delta_rad > 0:   # right turn (CW): tangent = (sin θ, −cos θ)
            tang_e, tang_n = math.sin(theta), -math.cos(theta)
        else:                   # left turn (CCW): tangent = (−sin θ, cos θ)
            tang_e, tang_n = -math.sin(theta), math.cos(theta)

        heading = math.degrees(math.atan2(tang_e, tang_n)) % 360.0

        return MovementState(
            lat=lat, lon=lon, alt_m=arc.alt_m,
            heading_deg=heading, speed_knots=arc.speed_knots,
            course_deg=heading,
            metadata_overrides=self._waypoints[arc.wp_idx - 1].metadata_overrides,
        )

    # ── Public interface ──────────────────────────────────────────────────────

    def get_state(self, sim_time: datetime) -> MovementState:
        """Return interpolated position, heading, speed for given sim_time."""
        elapsed = sim_time - self._scenario_start
        wps = self._waypoints

        # Check turn arcs first — they override straight-segment interpolation
        for arc in self._turn_arcs:
            if arc.t_start <= elapsed <= arc.t_end:
                return self._arc_state(elapsed, arc)

        # Before first waypoint
        if elapsed <= wps[0].time_offset:
            wp = wps[0]
            heading = _initial_bearing(wp.lat, wp.lon, wps[1].lat, wps[1].lon) if len(wps) > 1 else 0.0
            return MovementState(
                lat=wp.lat, lon=wp.lon, alt_m=wp.alt_m,
                heading_deg=heading, speed_knots=0.0, course_deg=heading,
                metadata_overrides=wp.metadata_overrides,
            )

        # After last waypoint
        if elapsed >= wps[-1].time_offset:
            wp = wps[-1]
            heading = _initial_bearing(wps[-2].lat, wps[-2].lon, wp.lat, wp.lon) if len(wps) > 1 else 0.0
            return MovementState(
                lat=wp.lat, lon=wp.lon, alt_m=wp.alt_m,
                heading_deg=heading, speed_knots=0.0, course_deg=heading,
                metadata_overrides=wp.metadata_overrides,
            )

        # Straight-segment interpolation
        for i in range(len(wps) - 1):
            wp_a = wps[i]
            wp_b = wps[i + 1]
            if wp_a.time_offset <= elapsed <= wp_b.time_offset:
                seg_dur = (wp_b.time_offset - wp_a.time_offset).total_seconds()
                if seg_dur <= 0:
                    bearing = _initial_bearing(wp_a.lat, wp_a.lon, wp_b.lat, wp_b.lon)
                    return MovementState(
                        lat=wp_b.lat, lon=wp_b.lon, alt_m=wp_b.alt_m,
                        heading_deg=bearing, speed_knots=wp_b.speed_knots,
                        course_deg=bearing,
                    )

                fraction = (elapsed - wp_a.time_offset).total_seconds() / seg_dur
                lat, lon = _interpolate_geodesic(wp_a.lat, wp_a.lon, wp_b.lat, wp_b.lon, fraction)
                alt   = wp_a.alt_m + (wp_b.alt_m - wp_a.alt_m) * fraction
                speed = wp_a.speed_knots + (wp_b.speed_knots - wp_a.speed_knots) * fraction
                heading = _initial_bearing(lat, lon, wp_b.lat, wp_b.lon)
                course  = _initial_bearing(wp_a.lat, wp_a.lon, wp_b.lat, wp_b.lon)

                return MovementState(
                    lat=lat, lon=lon, alt_m=alt,
                    heading_deg=heading, speed_knots=speed, course_deg=course,
                    metadata_overrides=wp_a.metadata_overrides,
                )

        # Fallback (shouldn't reach here)
        wp = wps[-1]
        return MovementState(lat=wp.lat, lon=wp.lon, alt_m=wp.alt_m,
                             heading_deg=0.0, speed_knots=0.0, course_deg=0.0)

    def is_complete(self, sim_time: datetime) -> bool:
        """True if sim_time is past the last waypoint."""
        return (sim_time - self._scenario_start) >= self._waypoints[-1].time_offset

    @property
    def total_duration(self) -> timedelta:
        return self._waypoints[-1].time_offset - self._waypoints[0].time_offset

    @property
    def waypoints(self) -> list[Waypoint]:
        return list(self._waypoints)
