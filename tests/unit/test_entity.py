"""Tests for the Entity data model."""

from datetime import datetime, timezone

from simulator.core.entity import (
    Agency,
    Domain,
    Entity,
    EntityStatus,
    Position,
)


def _make_entity(**kwargs) -> Entity:
    """Helper to create a test entity with sensible defaults."""
    defaults = {
        "entity_id": "TEST-001",
        "entity_type": "MMEA_PATROL",
        "domain": Domain.MARITIME,
        "agency": Agency.MMEA,
        "callsign": "KM Marlin",
        "position": Position(latitude=2.5, longitude=102.0, altitude_m=0.0),
        "heading_deg": 90.0,
        "speed_knots": 15.0,
        "course_deg": 92.0,
        "status": EntityStatus.ACTIVE,
        "sidc": "SFSP------*****",
        "metadata": {"mmsi": "533000001"},
    }
    defaults.update(kwargs)
    return Entity(**defaults)


class TestPosition:
    def test_create(self):
        pos = Position(latitude=2.5, longitude=102.0, altitude_m=100.0)
        assert pos.latitude == 2.5
        assert pos.longitude == 102.0
        assert pos.altitude_m == 100.0

    def test_default_altitude(self):
        pos = Position(latitude=2.5, longitude=102.0)
        assert pos.altitude_m == 0.0

    def test_to_dict(self):
        pos = Position(latitude=2.5, longitude=102.0, altitude_m=50.0)
        d = pos.to_dict()
        assert d == {"latitude": 2.5, "longitude": 102.0, "altitude_m": 50.0}

    def test_from_dict(self):
        d = {"latitude": 2.5, "longitude": 102.0, "altitude_m": 50.0}
        pos = Position.from_dict(d)
        assert pos.latitude == 2.5
        assert pos.longitude == 102.0
        assert pos.altitude_m == 50.0

    def test_from_dict_default_altitude(self):
        d = {"latitude": 2.5, "longitude": 102.0}
        pos = Position.from_dict(d)
        assert pos.altitude_m == 0.0


class TestEnums:
    def test_agency_values(self):
        assert Agency.RMP.value == "RMP"
        assert Agency.MMEA.value == "MMEA"
        assert Agency.CI.value == "CI"
        assert Agency.RMAF.value == "RMAF"
        assert Agency.MIL.value == "MIL"
        assert Agency.CIVILIAN.value == "CIVILIAN"

    def test_domain_values(self):
        assert Domain.MARITIME.value == "MARITIME"
        assert Domain.AIR.value == "AIR"
        assert Domain.GROUND_VEHICLE.value == "GROUND_VEHICLE"
        assert Domain.PERSONNEL.value == "PERSONNEL"

    def test_status_values(self):
        assert EntityStatus.ACTIVE.value == "ACTIVE"
        assert EntityStatus.IDLE.value == "IDLE"
        assert EntityStatus.RESPONDING.value == "RESPONDING"
        assert EntityStatus.INTERCEPTING.value == "INTERCEPTING"
        assert EntityStatus.RTB.value == "RTB"


class TestEntity:
    def test_create(self):
        entity = _make_entity()
        assert entity.entity_id == "TEST-001"
        assert entity.entity_type == "MMEA_PATROL"
        assert entity.domain == Domain.MARITIME
        assert entity.agency == Agency.MMEA
        assert entity.callsign == "KM Marlin"
        assert entity.position.latitude == 2.5
        assert entity.heading_deg == 90.0
        assert entity.speed_knots == 15.0
        assert entity.status == EntityStatus.ACTIVE
        assert entity.metadata["mmsi"] == "533000001"

    def test_to_dict(self):
        entity = _make_entity()
        d = entity.to_dict()
        assert d["entity_id"] == "TEST-001"
        assert d["domain"] == "MARITIME"
        assert d["agency"] == "MMEA"
        assert d["position"]["latitude"] == 2.5
        assert d["status"] == "ACTIVE"
        assert isinstance(d["timestamp"], str)

    def test_from_dict_roundtrip(self):
        entity = _make_entity()
        d = entity.to_dict()
        restored = Entity.from_dict(d)
        assert restored.entity_id == entity.entity_id
        assert restored.entity_type == entity.entity_type
        assert restored.domain == entity.domain
        assert restored.agency == entity.agency
        assert restored.callsign == entity.callsign
        assert restored.position.latitude == entity.position.latitude
        assert restored.position.longitude == entity.position.longitude
        assert restored.heading_deg == entity.heading_deg
        assert restored.speed_knots == entity.speed_knots
        assert restored.status == entity.status
        assert restored.sidc == entity.sidc
        assert restored.metadata == entity.metadata

    def test_update_position(self):
        entity = _make_entity()
        old_ts = entity.timestamp
        entity.update_position(
            latitude=3.0,
            longitude=103.0,
            altitude_m=0.0,
            heading_deg=180.0,
            speed_knots=20.0,
            course_deg=182.0,
        )
        assert entity.position.latitude == 3.0
        assert entity.position.longitude == 103.0
        assert entity.heading_deg == 180.0
        assert entity.speed_knots == 20.0
        assert entity.course_deg == 182.0
        assert entity.timestamp >= old_ts

    def test_update_position_partial(self):
        entity = _make_entity()
        original_heading = entity.heading_deg
        original_speed = entity.speed_knots
        entity.update_position(latitude=3.0, longitude=103.0)
        assert entity.position.latitude == 3.0
        assert entity.heading_deg == original_heading
        assert entity.speed_knots == original_speed

    def test_default_status(self):
        entity = Entity(
            entity_id="X",
            entity_type="TEST",
            domain=Domain.MARITIME,
            agency=Agency.CIVILIAN,
            callsign="Test",
            position=Position(0, 0),
        )
        assert entity.status == EntityStatus.ACTIVE

    def test_from_dict_defaults(self):
        d = {
            "entity_id": "X",
            "entity_type": "TEST",
            "domain": "MARITIME",
            "agency": "CIVILIAN",
            "callsign": "Test",
            "position": {"latitude": 0, "longitude": 0},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        entity = Entity.from_dict(d)
        assert entity.heading_deg == 0.0
        assert entity.speed_knots == 0.0
        assert entity.status == EntityStatus.ACTIVE
        assert entity.sidc == ""
        assert entity.metadata == {}
