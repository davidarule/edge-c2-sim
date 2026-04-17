"""
Escape movement — flee on a constant bearing at speed.

Dead-reckoning: advances position along bearing_deg at speed_knots.
Optionally stops after duration_min expires.
"""

import math
from datetime import datetime, timedelta

from simulator.movement.waypoint import MovementState


class EscapeMovement:
    """Flee on a constant bearing at speed."""

    def __init__(
        self,
        start_lat: float,
        start_lon: float,
        bearing_deg: float,
        speed_knots: float,
        start_time: datetime,
        alt_m: float = 0.0,
        duration_min: float | None = None,
    ) -> None:
        self._start_lat = start_lat
        self._start_lon = start_lon
        self._bearing = bearing_deg
        self._speed = speed_knots
        self._start_time = start_time
        self._alt = alt_m
        self._duration = timedelta(minutes=duration_min) if duration_min else None

        # Pre-compute bearing components for dead reckoning
        self._bearing_rad = math.radians(bearing_deg)

    def get_state(self, sim_time: datetime) -> MovementState:
        elapsed = (sim_time - self._start_time).total_seconds()

        # If duration expired, hold at final position
        if self._duration and elapsed > self._duration.total_seconds():
            elapsed = self._duration.total_seconds()
            speed = 0.0
        else:
            speed = self._speed

        # Dead reckoning: distance in nautical miles
        dist_nm = (self._speed * elapsed) / 3600.0

        # Convert to lat/lon offset
        # 1 degree latitude ≈ 60 nm, 1 degree longitude ≈ 60 nm * cos(lat)
        dlat = (dist_nm / 60.0) * math.cos(self._bearing_rad)
        cos_lat = math.cos(math.radians(self._start_lat))
        dlon = (dist_nm / 60.0) * math.sin(self._bearing_rad) / max(cos_lat, 0.01)

        lat = self._start_lat + dlat
        lon = self._start_lon + dlon

        return MovementState(
            lat=lat, lon=lon, alt_m=self._alt,
            heading_deg=self._bearing, speed_knots=speed,
            course_deg=self._bearing,
        )

    def is_complete(self, sim_time: datetime) -> bool:
        if not self._duration:
            return False
        elapsed = (sim_time - self._start_time).total_seconds()
        return elapsed >= self._duration.total_seconds()
