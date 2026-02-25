"""
Ground vehicle domain simulator.

Manages vehicle entities. Vehicles follow waypoint routes. Emergency
vehicles travel at higher speeds. Convoys maintain spacing.
"""

import logging
from datetime import datetime

from simulator.core.entity import Domain, Entity, EntityStatus
from simulator.core.entity_store import EntityStore

logger = logging.getLogger(__name__)

# Knots to km/h conversion
KTS_TO_KMH = 1.852


class GroundVehicleSimulator:
    """Ground vehicle domain simulator — speed conversion and convoy spacing."""

    def __init__(self, entity_store: EntityStore) -> None:
        self._store = entity_store

    def tick(self, sim_time: datetime) -> None:
        """Update vehicle metadata each tick."""
        for entity in self._store.get_entities_by_domain(Domain.GROUND_VEHICLE):
            # Always update speed in km/h
            entity.metadata["speed_kmh"] = round(
                entity.speed_knots * KTS_TO_KMH, 1
            )

            # Ground altitude = 0
            if entity.position.altitude_m != 0:
                entity.position.altitude_m = 0

            # Emergency response speed boost
            if entity.status == EntityStatus.RESPONDING:
                entity.metadata["emergency_mode"] = True
            else:
                entity.metadata["emergency_mode"] = False
