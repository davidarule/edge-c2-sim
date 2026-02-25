"""Tests for AIS encoder."""

from datetime import datetime, timezone

import pytest
from pyais import decode

from simulator.core.entity import Agency, Domain, Entity, EntityStatus, Position
from simulator.signals.ais_encoder import AISEncoder


@pytest.fixture
def encoder():
    return AISEncoder()


@pytest.fixture
def vessel():
    return Entity(
        entity_id="TEST-001",
        entity_type="CIVILIAN_CARGO",
        domain=Domain.MARITIME,
        agency=Agency.CIVILIAN,
        callsign="MV Bintang",
        position=Position(5.5, 118.5),
        heading_deg=90.0,
        speed_knots=12.0,
        course_deg=92.0,
        timestamp=datetime(2026, 4, 15, 8, 30, 15, tzinfo=timezone.utc),
        metadata={
            "mmsi": "533123456",
            "vessel_name": "MV Bintang Laut",
            "flag": "MYS",
            "nav_status": 0,
        },
    )


class TestAISEncoder:
    def test_position_report_encodes(self, encoder, vessel):
        """Position report should produce valid NMEA sentence."""
        result = encoder.encode_position_report(vessel)
        assert len(result) >= 1
        assert result[0].startswith("!AIVDM")

    def test_position_report_roundtrip(self, encoder, vessel):
        """Encode then decode should preserve key fields."""
        nmea = encoder.encode_position_report(vessel)
        decoded = decode(*nmea).asdict()
        assert str(decoded["mmsi"]) == "533123456"
        assert abs(decoded["lat"] - 5.5) < 0.001
        assert abs(decoded["lon"] - 118.5) < 0.001
        assert abs(decoded["speed"] - 12.0) < 0.2

    def test_static_data_encodes(self, encoder, vessel):
        """Type 5 static data should produce valid NMEA."""
        result = encoder.encode_static_data(vessel)
        assert len(result) >= 1
        assert any("AIVDM" in s for s in result)

    def test_mmsi_generation_valid(self):
        """Generated MMSI should be 9 digits with correct MID."""
        mmsi = AISEncoder.generate_mmsi("TEST-001", "MYS")
        assert len(mmsi) == 9
        assert mmsi.startswith("533")

        mmsi_vnm = AISEncoder.generate_mmsi("TEST-002", "VNM")
        assert mmsi_vnm.startswith("574")

    def test_mmsi_deterministic(self):
        """Same entity_id should always produce same MMSI."""
        m1 = AISEncoder.generate_mmsi("MY-SHIP", "MYS")
        m2 = AISEncoder.generate_mmsi("MY-SHIP", "MYS")
        assert m1 == m2

    def test_json_output(self, encoder, vessel):
        """JSON output should contain all key fields."""
        result = encoder.encode_to_json(vessel)
        assert result["mmsi"] == "533123456"
        assert result["latitude"] == 5.5
        assert result["longitude"] == 118.5
        assert result["speed_knots"] == 12.0
        assert result["nav_status"] == 0

    def test_no_mmsi_auto_generates(self, encoder):
        """Entity without MMSI should auto-generate one."""
        entity = Entity(
            entity_id="AUTO-001", entity_type="CIVILIAN_CARGO",
            domain=Domain.MARITIME, agency=Agency.CIVILIAN,
            callsign="Test", position=Position(5.0, 118.0),
            metadata={"flag": "MYS"},
        )
        result = encoder.encode_position_report(entity)
        assert len(result) >= 1
