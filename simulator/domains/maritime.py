"""
Maritime domain simulator.

Manages all maritime entities (ships, boats, vessels). Adds maritime-specific
behavior on top of the base movement engine: AIS message generation, TSS lane
following, vessel traffic patterns, and suspect vessel dark-running behavior.
"""

import logging
from datetime import datetime, timedelta

from simulator.core.entity import Domain, Entity, EntityStatus
from simulator.core.entity_store import EntityStore
from simulator.signals.ais_encoder import AISEncoder

logger = logging.getLogger(__name__)


# AIS reporting intervals per IMO requirements (in seconds)
def _ais_interval(speed_knots: float, nav_status: int, course_changing: bool) -> float:
    """Return AIS reporting interval in seconds based on vessel state."""
    if nav_status in (1, 5):  # At anchor or moored
        return 180.0  # 3 minutes
    if course_changing:
        return 3.3
    if speed_knots > 23:
        return 2.0
    if speed_knots > 14:
        return 6.0
    if speed_knots > 0:
        return 10.0
    return 180.0  # Stationary


def _calculate_nav_status(entity: Entity) -> int:
    """Determine AIS navigation status from entity state."""
    if entity.status == EntityStatus.IDLE:
        return 1  # At anchor
    if entity.speed_knots < 0.5:
        # Check if at a port/base
        if entity.metadata.get("at_port", False):
            return 5  # Moored
        return 1  # At anchor
    if "fishing" in entity.entity_type.lower() and entity.speed_knots < 3:
        return 7  # Engaged in fishing
    if not entity.metadata.get("ais_active", True):
        return 15  # Not defined (dark targets)
    return 0  # Under way using engine


class MaritimeSimulator:
    """Maritime domain simulator — AIS generation and maritime metadata."""

    def __init__(self, entity_store: EntityStore) -> None:
        self._store = entity_store
        self._encoder = AISEncoder()
        self._last_ais_time: dict[str, datetime] = {}
        self._last_ais_type5_time: dict[str, datetime] = {}
        self._last_heading: dict[str, float] = {}
        self._ais_messages: list[str] = []  # Recent AIS NMEA output
        self._ais_json: list[dict] = []  # Recent AIS JSON output

    def tick(self, sim_time: datetime) -> None:
        """Called each simulation tick for all maritime entities."""
        self._ais_messages.clear()
        self._ais_json.clear()

        for entity in self._store.get_entities_by_domain(Domain.MARITIME):
            # Update nav status
            nav_status = _calculate_nav_status(entity)
            entity.metadata["nav_status"] = nav_status

            # AIS generation
            ais_active = entity.metadata.get("ais_active", True)

            if ais_active:
                self._maybe_generate_ais(entity, sim_time, nav_status)
                entity.metadata["last_ais_time"] = sim_time.isoformat()
            else:
                entity.metadata["last_ais_time"] = None

            # Track heading for course-change detection
            self._last_heading[entity.entity_id] = entity.heading_deg

    def _maybe_generate_ais(
        self, entity: Entity, sim_time: datetime, nav_status: int,
    ) -> None:
        """Generate AIS if enough time has elapsed since last transmission."""
        eid = entity.entity_id

        # Detect course change
        prev_heading = self._last_heading.get(eid, entity.heading_deg)
        heading_change = abs(entity.heading_deg - prev_heading)
        if heading_change > 180:
            heading_change = 360 - heading_change
        course_changing = heading_change > 2.0

        interval = _ais_interval(entity.speed_knots, nav_status, course_changing)

        # Check position report interval
        last_time = self._last_ais_time.get(eid)
        if last_time is None or (sim_time - last_time).total_seconds() >= interval:
            try:
                nmea = self._encoder.encode_position_report(entity)
                self._ais_messages.extend(nmea)
                self._ais_json.append(self._encoder.encode_to_json(entity))
            except Exception as e:
                logger.debug(f"AIS encode error for {eid}: {e}")
            self._last_ais_time[eid] = sim_time

        # Check Type 5 static data interval (every 6 minutes)
        last_type5 = self._last_ais_type5_time.get(eid)
        if last_type5 is None or (sim_time - last_type5).total_seconds() >= 360:
            try:
                nmea5 = self._encoder.encode_static_data(entity)
                self._ais_messages.extend(nmea5)
            except Exception as e:
                logger.debug(f"AIS Type 5 encode error for {eid}: {e}")
            self._last_ais_type5_time[eid] = sim_time

    @property
    def recent_ais_nmea(self) -> list[str]:
        """NMEA sentences generated in the last tick."""
        return list(self._ais_messages)

    @property
    def recent_ais_json(self) -> list[dict]:
        """JSON AIS data generated in the last tick."""
        return list(self._ais_json)
