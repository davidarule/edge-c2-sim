"""
Approach movement — graduated deceleration toward a target or point.

Speed interpolates linearly from initial_speed to final_speed as the
entity closes from approach_distance to 0. If tracking a target entity,
the destination updates each tick.
"""

import math
from datetime import datetime

from geopy.distance import geodesic

from simulator.movement.waypoint import MovementState, _initial_bearing


class ApproachMovement:
    """Decelerate toward a target or fixed point."""

    # Within this distance (nm) we consider arrival
    _ARRIVAL_THRESHOLD_NM = 0.05  # ~100m

    def __init__(
        self,
        start_lat: float,
        start_lon: float,
        dest_lat: float,
        dest_lon: float,
        initial_speed_knots: float,
        final_speed_knots: float = 2.0,
        approach_distance_nm: float = 1.0,
        start_time: datetime | None = None,
        alt_m: float = 0.0,
        target_entity_id: str | None = None,
        entity_store=None,
    ) -> None:
        self._lat = start_lat
        self._lon = start_lon
        self._dest_lat = dest_lat
        self._dest_lon = dest_lon
        self._initial_speed = initial_speed_knots
        self._final_speed = final_speed_knots
        self._approach_dist = approach_distance_nm
        self._alt = alt_m
        self._target_id = target_entity_id
        self._entity_store = entity_store
        self._last_time: datetime | None = start_time
        self._arrived = False

    def get_state(self, sim_time: datetime) -> MovementState:
        # Update destination from target if tracking
        dest_lat = self._dest_lat
        dest_lon = self._dest_lon
        if self._target_id and self._entity_store:
            target = self._entity_store.get_entity(self._target_id)
            if target:
                dest_lat = target.position.latitude
                dest_lon = target.position.longitude

        # Current distance to destination
        dist_nm = geodesic(
            (self._lat, self._lon), (dest_lat, dest_lon)
        ).nautical

        # Check arrival — hold at current position, don't snap to destination
        if dist_nm <= self._ARRIVAL_THRESHOLD_NM:
            self._arrived = True
            heading = _initial_bearing(self._lat, self._lon, dest_lat, dest_lon)
            return MovementState(
                lat=self._lat, lon=self._lon, alt_m=self._alt,
                heading_deg=heading,
                speed_knots=self._final_speed, course_deg=heading,
            )

        # Interpolate speed: linear from initial at approach_dist to final at 0
        if dist_nm >= self._approach_dist:
            speed = self._initial_speed
        else:
            fraction = dist_nm / self._approach_dist
            speed = self._final_speed + (self._initial_speed - self._final_speed) * fraction

        # Advance position
        if self._last_time is not None:
            dt_s = (sim_time - self._last_time).total_seconds()
        else:
            dt_s = 0.0
        self._last_time = sim_time

        if speed > 0 and dt_s > 0:
            # Distance to move this tick (nautical miles)
            move_nm = (speed * dt_s) / 3600.0

            # Don't overshoot
            move_nm = min(move_nm, dist_nm)

            # Bearing to destination
            bearing = _initial_bearing(self._lat, self._lon, dest_lat, dest_lon)
            bearing_rad = math.radians(bearing)

            # Advance position
            dlat = (move_nm / 60.0) * math.cos(bearing_rad)
            cos_lat = math.cos(math.radians(self._lat))
            dlon = (move_nm / 60.0) * math.sin(bearing_rad) / max(cos_lat, 0.01)

            self._lat += dlat
            self._lon += dlon

            heading = bearing
        else:
            heading = _initial_bearing(self._lat, self._lon, dest_lat, dest_lon)

        return MovementState(
            lat=self._lat, lon=self._lon, alt_m=self._alt,
            heading_deg=heading, speed_knots=speed, course_deg=heading,
        )

    def is_complete(self, sim_time: datetime) -> bool:
        return self._arrived
