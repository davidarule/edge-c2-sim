"""
AIS NMEA sentence generator.

Converts entity state into properly formatted AIS NMEA sentences
using the pyais library. Generates both position reports (Type 1/2/3)
and static data (Type 5).
"""

import hashlib
from typing import Any

from pyais import encode_dict

from simulator.core.entity import Entity

# Country MID codes for MMSI generation
COUNTRY_MIDS = {
    "MYS": "533",
    "VNM": "574",
    "PHL": "548",
    "IDN": "525",
    "SGP": "563",
    "BRN": "508",
    "CHN": "412",
    "TWN": "416",
    "JPN": "431",
    "KOR": "440",
}

# AIS vessel type codes (subset)
VESSEL_TYPE_CODES = {
    "cargo": 70,
    "tanker": 80,
    "fishing": 30,
    "tug": 52,
    "passenger": 60,
    "military": 35,
    "patrol": 55,
    "sar": 51,
    "pilot": 50,
    "pleasure": 37,
}


class AISEncoder:
    """Generates AIS NMEA sentences from entity state."""

    def encode_position_report(self, entity: Entity) -> list[str]:
        """Generate AIS Type 1 position report NMEA sentence(s)."""
        mmsi = entity.metadata.get("mmsi") or self.generate_mmsi(
            entity.entity_id, entity.metadata.get("flag", "MYS")
        )

        nav_status = entity.metadata.get("nav_status", 0)

        data = {
            "type": 1,
            "mmsi": str(mmsi),
            "status": nav_status,
            "turn": 0.0,
            "speed": round(entity.speed_knots, 1),
            "accuracy": 0,
            "lon": round(entity.position.longitude, 6),
            "lat": round(entity.position.latitude, 6),
            "course": round(entity.course_deg, 1),
            "heading": int(entity.heading_deg) % 360,
            "second": entity.timestamp.second if entity.timestamp else 0,
            "maneuver": 0,
            "raim": False,
            "radio": 0,
        }

        return encode_dict(data, talker_id="AIVDM")

    def encode_static_data(self, entity: Entity) -> list[str]:
        """Generate AIS Type 5 static and voyage data NMEA sentence(s)."""
        mmsi = entity.metadata.get("mmsi") or self.generate_mmsi(
            entity.entity_id, entity.metadata.get("flag", "MYS")
        )

        vessel_name = entity.metadata.get("vessel_name", entity.callsign)
        callsign = entity.metadata.get("callsign_radio", entity.callsign[:7])

        # Determine vessel type code
        vessel_type_str = entity.metadata.get("vessel_type", "").lower()
        shiptype = 0
        for key, code in VESSEL_TYPE_CODES.items():
            if key in vessel_type_str:
                shiptype = code
                break
        if shiptype == 0 and "patrol" in entity.entity_type.lower():
            shiptype = 55
        elif shiptype == 0 and "fishing" in entity.entity_type.lower():
            shiptype = 30

        # Generate IMO from entity_id hash
        imo_hash = int(hashlib.md5(entity.entity_id.encode()).hexdigest()[:7], 16)
        imo = 1000000 + (imo_hash % 9000000)

        destination = entity.metadata.get("destination", "")

        data = {
            "type": 5,
            "mmsi": str(mmsi),
            "ais_version": 0,
            "imo": imo,
            "callsign": callsign[:7].ljust(7),
            "shipname": vessel_name[:20].ljust(20),
            "shiptype": shiptype,
            "to_bow": 30,
            "to_stern": 20,
            "to_port": 5,
            "to_starboard": 5,
            "epfd": 1,  # GPS
            "month": 4,  # April
            "day": 15,
            "hour": 8,
            "minute": 0,
            "draught": 5.0,
            "destination": destination[:20].ljust(20) if destination else "                    ",
        }

        return encode_dict(data, talker_id="AIVDM")

    @staticmethod
    def generate_mmsi(entity_id: str, flag: str = "MYS") -> str:
        """Generate a plausible MMSI for an entity.
        Deterministic: same entity_id always gets same MMSI."""
        mid = COUNTRY_MIDS.get(flag, "533")
        # Generate 6 digits from entity_id hash
        hash_int = int(hashlib.md5(entity_id.encode()).hexdigest()[:6], 16)
        suffix = str(hash_int % 1000000).zfill(6)
        return f"{mid}{suffix}"

    def encode_to_json(self, entity: Entity) -> dict[str, Any]:
        """Generate structured AIS data as JSON (fallback for non-NMEA consumers)."""
        mmsi = entity.metadata.get("mmsi") or self.generate_mmsi(
            entity.entity_id, entity.metadata.get("flag", "MYS")
        )
        return {
            "mmsi": mmsi,
            "msg_type": 1,
            "latitude": round(entity.position.latitude, 6),
            "longitude": round(entity.position.longitude, 6),
            "speed_knots": round(entity.speed_knots, 1),
            "course_deg": round(entity.course_deg, 1),
            "heading_deg": int(entity.heading_deg) % 360,
            "nav_status": entity.metadata.get("nav_status", 0),
            "vessel_name": entity.metadata.get("vessel_name", entity.callsign),
            "flag": entity.metadata.get("flag", "MYS"),
            "timestamp": entity.timestamp.isoformat() if entity.timestamp else None,
        }
