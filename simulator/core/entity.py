"""
Entity data model for Edge C2 Simulator.

Every simulated entity (ship, aircraft, vehicle, person) shares a common
base model. Domain-specific data lives in the metadata dict.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class Agency(Enum):
    """Malaysian security agencies and civilian designation."""
    RMP = "RMP"        # Royal Malaysia Police
    MMEA = "MMEA"      # Malaysian Maritime Enforcement Agency
    CI = "CI"          # Royal Malaysian Customs and Immigration
    RMAF = "RMAF"      # Royal Malaysian Air Force
    MIL = "MIL"        # Malaysian Armed Forces
    CIVILIAN = "CIVILIAN"


class Domain(Enum):
    """Operational domains."""
    MARITIME = "MARITIME"
    AIR = "AIR"
    GROUND_VEHICLE = "GROUND_VEHICLE"
    PERSONNEL = "PERSONNEL"


class EntityStatus(Enum):
    """Entity operational status."""
    ACTIVE = "ACTIVE"
    IDLE = "IDLE"
    RESPONDING = "RESPONDING"
    INTERCEPTING = "INTERCEPTING"
    RTB = "RTB"  # Return to base


@dataclass
class Position:
    """WGS84 geographic position."""
    latitude: float
    longitude: float
    altitude_m: float = 0.0

    def to_dict(self) -> dict[str, float]:
        return {
            "latitude": self.latitude,
            "longitude": self.longitude,
            "altitude_m": self.altitude_m,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Position":
        return cls(
            latitude=d["latitude"],
            longitude=d["longitude"],
            altitude_m=d.get("altitude_m", 0.0),
        )


@dataclass
class Entity:
    """
    Base entity model for all simulated objects.

    Covers maritime vessels, aircraft, ground vehicles, and personnel.
    Domain-specific fields extend via the metadata dict.
    """
    entity_id: str
    entity_type: str
    domain: Domain
    agency: Agency
    callsign: str
    position: Position
    heading_deg: float = 0.0
    speed_knots: float = 0.0
    course_deg: float = 0.0
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    status: EntityStatus = EntityStatus.ACTIVE
    sidc: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def update_position(
        self,
        latitude: float,
        longitude: float,
        altitude_m: float = 0.0,
        heading_deg: float | None = None,
        speed_knots: float | None = None,
        course_deg: float | None = None,
    ) -> None:
        """Update entity position and optionally heading/speed/course. Timestamps automatically."""
        self.position = Position(latitude, longitude, altitude_m)
        if heading_deg is not None:
            self.heading_deg = heading_deg
        if speed_knots is not None:
            self.speed_knots = speed_knots
        if course_deg is not None:
            self.course_deg = course_deg
        self.timestamp = datetime.now(timezone.utc)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to JSON-compatible dictionary."""
        return {
            "entity_id": self.entity_id,
            "entity_type": self.entity_type,
            "domain": self.domain.value,
            "agency": self.agency.value,
            "callsign": self.callsign,
            "position": self.position.to_dict(),
            "heading_deg": self.heading_deg,
            "speed_knots": self.speed_knots,
            "course_deg": self.course_deg,
            "timestamp": self.timestamp.isoformat(),
            "status": self.status.value,
            "sidc": self.sidc,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Entity":
        """Deserialize from dictionary."""
        return cls(
            entity_id=d["entity_id"],
            entity_type=d["entity_type"],
            domain=Domain(d["domain"]),
            agency=Agency(d["agency"]),
            callsign=d["callsign"],
            position=Position.from_dict(d["position"]),
            heading_deg=d.get("heading_deg", 0.0),
            speed_knots=d.get("speed_knots", 0.0),
            course_deg=d.get("course_deg", 0.0),
            timestamp=datetime.fromisoformat(d["timestamp"]),
            status=EntityStatus(d.get("status", "ACTIVE")),
            sidc=d.get("sidc", ""),
            metadata=d.get("metadata", {}),
        )
