"""
Personnel domain simulator.

Manages troop/officer entities. Personnel move slowly (walking speed),
can form formations (patrol, checkpoint, cordon), and groups move as
a unit with slight position spread.
"""

import logging
import math
import random
from datetime import datetime

from simulator.core.entity import Domain, Entity
from simulator.core.entity_store import EntityStore

logger = logging.getLogger(__name__)

# Formation parameters: (spread_radius_m, description)
FORMATIONS = {
    "patrol": (5.0, "Moving patrol formation"),
    "checkpoint": (20.0, "Stationary checkpoint"),
    "cordon": (50.0, "Security cordon ring"),
    "standby": (5.0, "Standby/clustered"),
}


class PersonnelSimulator:
    """Personnel domain simulator — formations and group spread."""

    def __init__(self, entity_store: EntityStore) -> None:
        self._store = entity_store
        self._rng = random.Random(42)

    def tick(self, sim_time: datetime) -> None:
        """Update formation and member positions each tick."""
        for entity in self._store.get_entities_by_domain(Domain.PERSONNEL):
            formation = entity.metadata.get("formation", "standby")
            unit_size = entity.metadata.get("unit_size", 1)

            # Ensure formation metadata is set
            entity.metadata["formation"] = formation

            # Generate member positions if unit_size > 1
            if unit_size > 1:
                entity.metadata["member_positions"] = self._generate_member_positions(
                    entity, formation, unit_size,
                )

            # Speed limits: walking 3-5 km/h, running 6-8 km/h
            max_speed_kts = 4.3  # ~8 km/h in knots
            if entity.speed_knots > max_speed_kts:
                entity.speed_knots = max_speed_kts

            entity.metadata["speed_kmh"] = round(entity.speed_knots * 1.852, 1)

    def _generate_member_positions(
        self, entity: Entity, formation: str, unit_size: int,
    ) -> list[dict]:
        """Generate spread positions for individual members."""
        center_lat = entity.position.latitude
        center_lon = entity.position.longitude
        radius_m = FORMATIONS.get(formation, (10.0, ""))[0]

        positions = []
        for i in range(unit_size):
            if formation == "cordon":
                # Ring formation: evenly spaced on circle
                angle = (2 * math.pi * i) / unit_size
                offset_n = radius_m * math.cos(angle)
                offset_e = radius_m * math.sin(angle)
            elif formation == "patrol":
                # Single file along heading
                heading_rad = math.radians(entity.heading_deg)
                spacing = radius_m * i
                offset_n = -spacing * math.cos(heading_rad)  # Trail behind
                offset_e = -spacing * math.sin(heading_rad)
            else:
                # Random spread (checkpoint, standby)
                offset_n = self._rng.gauss(0, radius_m / 2)
                offset_e = self._rng.gauss(0, radius_m / 2)

            dlat = offset_n / 111_111.0
            dlon = offset_e / (111_111.0 * math.cos(math.radians(center_lat)))

            positions.append({
                "lat": round(center_lat + dlat, 7),
                "lon": round(center_lon + dlon, 7),
            })

        return positions
