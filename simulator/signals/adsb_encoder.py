"""
ADS-B message generator in SBS (BaseStation) format.

Generates SBS-format messages that match what a real ADS-B receiver
would output. This is the standard format for FlightRadar24, dump1090,
and most aviation tracking software.
"""

import hashlib
from datetime import datetime

from simulator.core.entity import Entity

# ICAO address ranges by country
ICAO_RANGES = {
    "MYS": (0x750000, 0x75FFFF),
    "VNM": (0x888000, 0x88FFFF),
    "PHL": (0x758000, 0x75FFFF),
    "IDN": (0x8A0000, 0x8AFFFF),
    "SGP": (0x768000, 0x76FFFF),
}


class ADSBEncoder:
    """Generates SBS-format ADS-B messages from entity state."""

    def encode_identification(self, entity: Entity) -> str:
        """SBS MSG Type 1 — Aircraft identification."""
        icao = entity.metadata.get("icao_hex") or self.generate_icao_hex(
            entity.entity_id, entity.metadata.get("country", "MYS")
        )
        callsign = entity.callsign[:8]
        now = entity.timestamp or datetime.utcnow()
        date_str = now.strftime("%Y/%m/%d")
        time_str = now.strftime("%H:%M:%S.000")

        return (
            f"MSG,1,1,1,{icao},1,"
            f"{date_str},{time_str},{date_str},{time_str},"
            f"{callsign},,,,,,,,,,"
        )

    def encode_position(self, entity: Entity) -> str:
        """SBS MSG Type 3 — Airborne position."""
        icao = entity.metadata.get("icao_hex") or self.generate_icao_hex(
            entity.entity_id, entity.metadata.get("country", "MYS")
        )
        now = entity.timestamp or datetime.utcnow()
        date_str = now.strftime("%Y/%m/%d")
        time_str = now.strftime("%H:%M:%S.000")

        alt_ft = entity.position.altitude_m * 3.28084
        lat = entity.position.latitude
        lon = entity.position.longitude
        on_ground = -1 if entity.metadata.get("on_ground", False) else 0

        return (
            f"MSG,3,1,1,{icao},1,"
            f"{date_str},{time_str},{date_str},{time_str},"
            f",{alt_ft:.0f},,,"
            f"{lat:.6f},{lon:.6f},,,,,,{on_ground}"
        )

    def encode_velocity(self, entity: Entity) -> str:
        """SBS MSG Type 4 — Airborne velocity."""
        icao = entity.metadata.get("icao_hex") or self.generate_icao_hex(
            entity.entity_id, entity.metadata.get("country", "MYS")
        )
        now = entity.timestamp or datetime.utcnow()
        date_str = now.strftime("%Y/%m/%d")
        time_str = now.strftime("%H:%M:%S.000")

        speed = entity.speed_knots
        heading = entity.heading_deg
        vrate = entity.metadata.get("vertical_rate_fpm", 0)

        return (
            f"MSG,4,1,1,{icao},1,"
            f"{date_str},{time_str},{date_str},{time_str},"
            f",{speed:.0f},,{heading:.1f},,,"
            f"{vrate:.0f},,,,"
        )

    @staticmethod
    def generate_icao_hex(entity_id: str, country: str = "MYS") -> str:
        """Generate plausible ICAO 24-bit hex address.
        Deterministic from entity_id."""
        base, top = ICAO_RANGES.get(country, (0x750000, 0x75FFFF))
        range_size = top - base
        hash_int = int(hashlib.md5(entity_id.encode()).hexdigest()[:6], 16)
        icao_int = base + (hash_int % range_size)
        return f"{icao_int:06X}"

    @staticmethod
    def generate_squawk(entity_type: str) -> str:
        """Generate appropriate transponder squawk code."""
        et = entity_type.lower()
        if "civilian" in et or "commercial" in et:
            return "1200"  # VFR
        if "military" in et or "fighter" in et or "rmaf" in et:
            return "0000"
        if "emergency" in et:
            return "7700"
        return "1200"

    def encode_to_json(self, entity: Entity) -> dict:
        """Generate structured ADS-B data as JSON."""
        icao = entity.metadata.get("icao_hex") or self.generate_icao_hex(
            entity.entity_id, entity.metadata.get("country", "MYS")
        )
        return {
            "icao_hex": icao,
            "callsign": entity.callsign,
            "latitude": round(entity.position.latitude, 6),
            "longitude": round(entity.position.longitude, 6),
            "altitude_ft": round(entity.position.altitude_m * 3.28084),
            "speed_knots": round(entity.speed_knots, 1),
            "heading_deg": round(entity.heading_deg, 1),
            "vertical_rate_fpm": entity.metadata.get("vertical_rate_fpm", 0),
            "on_ground": entity.metadata.get("on_ground", False),
            "squawk": self.generate_squawk(entity.entity_type),
            "timestamp": entity.timestamp.isoformat() if entity.timestamp else None,
        }
