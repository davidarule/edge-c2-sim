"""
Random patrol within a GeoJSON polygon.

Generates random waypoints inside the polygon boundary. Entity moves
between waypoints at a speed within its type's range, with configurable
dwell time at each point. Creates natural-looking patrol behavior.
"""

import logging
import random
from datetime import datetime, timedelta

from shapely.geometry import Polygon, Point

from simulator.movement.waypoint import (
    MovementState, Waypoint, WaypointMovement, _initial_bearing,
)

logger = logging.getLogger(__name__)


class PatrolMovement:
    """Patrol randomly within a polygon boundary."""

    def __init__(
        self,
        polygon: Polygon,
        speed_range_knots: tuple[float, float],
        dwell_time_range_s: tuple[int, int] = (30, 120),
        seed: int | None = None,
        scenario_start: datetime | None = None,
        domain: str | None = None,
    ) -> None:
        self._polygon = polygon
        self._speed_range = speed_range_knots
        self._dwell_range = dwell_time_range_s
        self._rng = random.Random(seed)
        self._scenario_start = scenario_start or datetime.now()
        self._domain = domain  # Used for terrain validation
        self._waypoint_movement: WaypointMovement | None = None
        self._generate_waypoints(timedelta(0))

    def _random_point_in_polygon(self) -> tuple[float, float]:
        """Generate a random point inside the polygon using rejection sampling.
        Also validates terrain if domain is set (maritime -> water, ground -> land)."""
        from simulator.movement.terrain import validate_position

        minx, miny, maxx, maxy = self._polygon.bounds
        for _ in range(1000):
            lat = self._rng.uniform(miny, maxy)
            lon = self._rng.uniform(minx, maxx)
            if self._polygon.contains(Point(lon, lat)):
                # Terrain check: skip points on wrong terrain
                if self._domain and not validate_position(lat, lon, self._domain):
                    continue
                return lat, lon
        # Fallback: try without terrain check
        for _ in range(100):
            lat = self._rng.uniform(miny, maxy)
            lon = self._rng.uniform(minx, maxx)
            if self._polygon.contains(Point(lon, lat)):
                return lat, lon
        # Last resort: centroid
        c = self._polygon.centroid
        return c.y, c.x

    def _generate_waypoints(self, start_offset: timedelta) -> None:
        """Generate 5-8 random patrol waypoints within the polygon."""
        count = self._rng.randint(5, 8)
        waypoints: list[Waypoint] = []
        current_offset = start_offset

        prev_lat, prev_lon = None, None

        for i in range(count):
            lat, lon = self._random_point_in_polygon()

            # Reject sharp turns (>90 deg change)
            if prev_lat is not None and len(waypoints) >= 2:
                prev_wp = waypoints[-1]
                prev_bearing = _initial_bearing(
                    waypoints[-2].lat, waypoints[-2].lon,
                    prev_wp.lat, prev_wp.lon,
                )
                new_bearing = _initial_bearing(prev_wp.lat, prev_wp.lon, lat, lon)
                turn = abs(new_bearing - prev_bearing)
                if turn > 180:
                    turn = 360 - turn
                if turn > 90:
                    # Try again with a new random point (up to 5 times)
                    for _ in range(5):
                        lat, lon = self._random_point_in_polygon()
                        new_bearing = _initial_bearing(prev_wp.lat, prev_wp.lon, lat, lon)
                        turn = abs(new_bearing - prev_bearing)
                        if turn > 180:
                            turn = 360 - turn
                        if turn <= 90:
                            break

            speed = self._rng.uniform(*self._speed_range)

            # Add dwell waypoint (same position, speed 0) before moving
            if i > 0:
                dwell_s = self._rng.randint(*self._dwell_range)
                waypoints.append(Waypoint(
                    lat=waypoints[-1].lat,
                    lon=waypoints[-1].lon,
                    speed_knots=0.0,
                    time_offset=current_offset + timedelta(seconds=dwell_s),
                ))
                current_offset = waypoints[-1].time_offset

            # Estimate travel time from previous point
            if prev_lat is not None:
                from geopy.distance import geodesic as geo_dist
                dist_nm = geo_dist((prev_lat, prev_lon), (lat, lon)).nautical
                travel_s = (dist_nm / speed * 3600) if speed > 0 else 0
                current_offset = current_offset + timedelta(seconds=travel_s)
            else:
                current_offset = current_offset + timedelta(seconds=1)

            waypoints.append(Waypoint(
                lat=lat, lon=lon, speed_knots=speed,
                time_offset=current_offset,
            ))
            prev_lat, prev_lon = lat, lon

        self._waypoint_movement = WaypointMovement(waypoints, self._scenario_start)
        self._last_offset = current_offset

    def get_state(self, sim_time: datetime) -> MovementState:
        """Current position on patrol route."""
        if self._waypoint_movement.is_complete(sim_time):
            self._generate_waypoints(self._last_offset)
        return self._waypoint_movement.get_state(sim_time)

    def is_complete(self, sim_time: datetime) -> bool:
        """Patrol never completes — it regenerates waypoints."""
        return False
