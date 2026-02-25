"""
Aviation domain simulator.

Manages aircraft entities with realistic flight profiles: takeoff,
climb, cruise, descent, and landing phases. Military aircraft can
scramble (rapid departure) and fly tactical profiles.
"""

import logging
from datetime import datetime

from simulator.core.entity import Domain, Entity, EntityStatus
from simulator.core.entity_store import EntityStore
from simulator.signals.adsb_encoder import ADSBEncoder

logger = logging.getLogger(__name__)

# Climb rates by aircraft type (feet per minute)
CLIMB_RATES = {
    "RMAF_TRANSPORT": (1500, 2500),
    "RMAF_HELICOPTER": (500, 1500),
    "RMAF_FIGHTER": (5000, 15000),
    "CIVILIAN_LIGHT": (500, 1000),
    "MIL_TRANSPORT": (1000, 2000),
}

# Cruise altitudes by type (feet)
CRUISE_ALTITUDES = {
    "RMAF_TRANSPORT": 15000,
    "RMAF_HELICOPTER": 3000,
    "RMAF_FIGHTER": 25000,
    "CIVILIAN_LIGHT": 5000,
    "MIL_TRANSPORT": 20000,
}

# Field elevation for ESSZONE bases (feet)
FIELD_ELEVATION = 50  # Approximate for Sabah coastal bases


class AviationSimulator:
    """Aviation domain simulator — flight profiles and ADS-B generation."""

    def __init__(self, entity_store: EntityStore) -> None:
        self._store = entity_store
        self._encoder = ADSBEncoder()
        self._adsb_messages: list[str] = []
        self._adsb_json: list[dict] = []
        self._last_tick_time: datetime | None = None

    def tick(self, sim_time: datetime) -> None:
        """Called each tick for aviation entities."""
        self._adsb_messages.clear()
        self._adsb_json.clear()

        dt_s = 0.0
        if self._last_tick_time:
            dt_s = (sim_time - self._last_tick_time).total_seconds()
        self._last_tick_time = sim_time

        for entity in self._store.get_entities_by_domain(Domain.AIR):
            self._update_flight_profile(entity, dt_s)

            # Generate ADS-B if active
            if entity.metadata.get("adsb_active", True):
                self._generate_adsb(entity)

    def _update_flight_profile(self, entity: Entity, dt_s: float) -> None:
        """Update altitude, vertical rate, and flight phase."""
        if dt_s <= 0:
            # Still set flight phase on first tick
            if entity.status == EntityStatus.IDLE and entity.metadata.get("on_ground", True):
                entity.metadata["flight_phase"] = "parked"
                entity.metadata["vertical_rate_fpm"] = 0
            return

        etype = entity.entity_type
        cruise_alt_ft = CRUISE_ALTITUDES.get(etype, 10000)
        climb_range = CLIMB_RATES.get(etype, (1000, 2000))

        current_alt_ft = entity.position.altitude_m * 3.28084
        target_alt_ft = entity.metadata.get("target_altitude_ft", cruise_alt_ft)
        on_ground = entity.metadata.get("on_ground", True)

        # Determine flight phase
        if entity.status == EntityStatus.IDLE and on_ground:
            # Parked — no changes
            entity.metadata["flight_phase"] = "parked"
            entity.metadata["vertical_rate_fpm"] = 0
            return

        if entity.status in (EntityStatus.ACTIVE, EntityStatus.RESPONDING,
                             EntityStatus.INTERCEPTING):
            if on_ground and entity.speed_knots > 0:
                # Taking off
                entity.metadata["on_ground"] = False
                entity.metadata["flight_phase"] = "takeoff"
                on_ground = False

            if not on_ground:
                alt_diff = target_alt_ft - current_alt_ft

                if abs(alt_diff) < 100:
                    # At cruise altitude
                    entity.metadata["flight_phase"] = "cruise"
                    entity.metadata["vertical_rate_fpm"] = 0
                elif alt_diff > 0:
                    # Climbing
                    climb_fpm = climb_range[1] if entity.status == EntityStatus.RESPONDING else climb_range[0]
                    # Scramble gets max climb
                    if entity.metadata.get("scramble"):
                        climb_fpm = climb_range[1] * 1.3

                    alt_change_ft = climb_fpm * (dt_s / 60.0)
                    alt_change_ft = min(alt_change_ft, alt_diff)
                    new_alt_ft = current_alt_ft + alt_change_ft
                    entity.position.altitude_m = new_alt_ft / 3.28084

                    entity.metadata["flight_phase"] = "climb"
                    entity.metadata["vertical_rate_fpm"] = climb_fpm
                else:
                    # Descending
                    descent_fpm = climb_range[0]  # Descend slower than climb
                    alt_change_ft = descent_fpm * (dt_s / 60.0)
                    alt_change_ft = min(alt_change_ft, abs(alt_diff))
                    new_alt_ft = current_alt_ft - alt_change_ft

                    if new_alt_ft <= FIELD_ELEVATION:
                        new_alt_ft = FIELD_ELEVATION
                        entity.metadata["on_ground"] = True
                        entity.metadata["flight_phase"] = "landed"
                    else:
                        entity.metadata["flight_phase"] = "descent"

                    entity.position.altitude_m = new_alt_ft / 3.28084
                    entity.metadata["vertical_rate_fpm"] = -descent_fpm

        # Helicopter hover detection
        if "HELICOPTER" in etype.upper() or "HELI" in etype.upper():
            if entity.speed_knots < 5 and not on_ground:
                entity.metadata["flight_phase"] = "hover"
                entity.metadata["vertical_rate_fpm"] = 0

    def _generate_adsb(self, entity: Entity) -> None:
        """Generate ADS-B messages for this entity."""
        try:
            # Position message
            self._adsb_messages.append(self._encoder.encode_position(entity))
            # Velocity message
            self._adsb_messages.append(self._encoder.encode_velocity(entity))
            # Identification (less frequent, but include)
            self._adsb_messages.append(self._encoder.encode_identification(entity))
            # JSON
            self._adsb_json.append(self._encoder.encode_to_json(entity))
        except Exception as e:
            logger.debug(f"ADS-B encode error for {entity.entity_id}: {e}")

    @property
    def recent_adsb_sbs(self) -> list[str]:
        """SBS messages from last tick."""
        return list(self._adsb_messages)

    @property
    def recent_adsb_json(self) -> list[dict]:
        """JSON ADS-B data from last tick."""
        return list(self._adsb_json)
