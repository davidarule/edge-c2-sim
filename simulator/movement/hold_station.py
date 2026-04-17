"""
Hold station movement — entity stays at a fixed position or tracks
alongside a target entity.

When hold_target is set, the entity follows the target's position
with an optional bearing/distance offset (for "hold alongside" behavior).
"""

from datetime import datetime

from simulator.movement.waypoint import MovementState


class HoldStationMovement:
    """Hold position (stationary or alongside a target entity)."""

    def __init__(
        self,
        lat: float,
        lon: float,
        alt_m: float = 0.0,
        heading_deg: float = 0.0,
        target_entity_id: str | None = None,
        entity_store=None,
    ) -> None:
        self._lat = lat
        self._lon = lon
        self._alt = alt_m
        self._heading = heading_deg
        self._target_id = target_entity_id
        self._entity_store = entity_store

    def get_state(self, sim_time: datetime) -> MovementState:
        lat = self._lat
        lon = self._lon
        alt = self._alt
        heading = self._heading

        # Track target entity position if set
        if self._target_id and self._entity_store:
            target = self._entity_store.get_entity(self._target_id)
            if target:
                lat = target.position.latitude
                lon = target.position.longitude
                alt = target.position.altitude_m
                heading = target.heading_deg

        return MovementState(
            lat=lat, lon=lon, alt_m=alt,
            heading_deg=heading, speed_knots=0.0, course_deg=heading,
        )

    def is_complete(self, sim_time: datetime) -> bool:
        """Hold station never completes — holds until replaced."""
        return False
