"""
Transit movement — go to a destination at a given speed.

Thin wrapper around WaypointMovement that auto-calculates travel time
from distance and speed. The event engine creates this instead of
manually building 2-waypoint movements inline.
"""

from datetime import datetime, timedelta

from geopy.distance import geodesic

from simulator.movement.waypoint import MovementState, Waypoint, WaypointMovement


class TransitMovement:
    """Move from current position to destination at specified speed."""

    def __init__(
        self,
        origin_lat: float,
        origin_lon: float,
        dest_lat: float,
        dest_lon: float,
        speed_knots: float,
        start_time: datetime,
        origin_alt_m: float = 0.0,
        dest_alt_m: float = 0.0,
    ) -> None:
        self._speed = speed_knots
        self._start_time = start_time

        # Calculate travel time from distance
        dist_nm = geodesic(
            (origin_lat, origin_lon),
            (dest_lat, dest_lon),
        ).nautical

        if speed_knots > 0 and dist_nm > 0:
            travel_s = (dist_nm / speed_knots) * 3600
        else:
            travel_s = 0

        self._travel_time = timedelta(seconds=travel_s)
        self._eta = start_time + self._travel_time

        # Build 2-waypoint movement
        waypoints = [
            Waypoint(
                lat=origin_lat, lon=origin_lon, alt_m=origin_alt_m,
                speed_knots=speed_knots, time_offset=timedelta(0),
            ),
            Waypoint(
                lat=dest_lat, lon=dest_lon, alt_m=dest_alt_m,
                speed_knots=0, time_offset=self._travel_time,
            ),
        ]
        self._movement = WaypointMovement(waypoints, start_time)

    @property
    def eta(self) -> datetime:
        """Estimated time of arrival."""
        return self._eta

    @property
    def travel_time(self) -> timedelta:
        return self._travel_time

    def get_state(self, sim_time: datetime) -> MovementState:
        return self._movement.get_state(sim_time)

    def is_complete(self, sim_time: datetime) -> bool:
        return self._movement.is_complete(sim_time)
