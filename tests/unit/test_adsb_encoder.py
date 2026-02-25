"""Tests for ADS-B encoder."""

from datetime import datetime, timezone

import pytest

from simulator.core.entity import Agency, Domain, Entity, Position
from simulator.signals.adsb_encoder import ADSBEncoder


@pytest.fixture
def encoder():
    return ADSBEncoder()


@pytest.fixture
def aircraft():
    return Entity(
        entity_id="RMAF-MPA-101",
        entity_type="RMAF_TRANSPORT",
        domain=Domain.AIR,
        agency=Agency.RMAF,
        callsign="TUDM MPA 01",
        position=Position(5.5, 118.5, altitude_m=4572),  # ~15000 ft
        heading_deg=45.0,
        speed_knots=250.0,
        course_deg=46.0,
        timestamp=datetime(2026, 4, 15, 8, 30, 0, tzinfo=timezone.utc),
        metadata={
            "on_ground": False,
            "vertical_rate_fpm": 0,
        },
    )


class TestADSBEncoder:
    def test_position_message_format(self, encoder, aircraft):
        """Position message should be in SBS MSG,3 format."""
        result = encoder.encode_position(aircraft)
        assert result.startswith("MSG,3,")
        # Should contain lat/lon
        assert "5.500000" in result
        assert "118.500000" in result
        # Altitude ~15000 ft
        assert "15000" in result or "14999" in result or "15001" in result

    def test_velocity_message_format(self, encoder, aircraft):
        """Velocity message should be in SBS MSG,4 format."""
        result = encoder.encode_velocity(aircraft)
        assert result.startswith("MSG,4,")
        assert "250" in result  # speed
        assert "45.0" in result  # heading

    def test_identification_message(self, encoder, aircraft):
        """Identification message should include callsign."""
        result = encoder.encode_identification(aircraft)
        assert result.startswith("MSG,1,")
        assert "TUDM MPA" in result

    def test_icao_deterministic(self):
        """Same entity_id should always produce same ICAO hex."""
        hex1 = ADSBEncoder.generate_icao_hex("TEST-001", "MYS")
        hex2 = ADSBEncoder.generate_icao_hex("TEST-001", "MYS")
        assert hex1 == hex2
        assert len(hex1) == 6
        # Should be in Malaysian range
        icao_int = int(hex1, 16)
        assert 0x750000 <= icao_int <= 0x75FFFF

    def test_squawk_codes(self):
        """Squawk codes should be appropriate for entity type."""
        assert ADSBEncoder.generate_squawk("CIVILIAN_LIGHT") == "1200"
        assert ADSBEncoder.generate_squawk("RMAF_FIGHTER") == "0000"
        assert ADSBEncoder.generate_squawk("emergency_medevac") == "7700"

    def test_json_output(self, encoder, aircraft):
        """JSON output should contain all key fields."""
        result = encoder.encode_to_json(aircraft)
        assert result["callsign"] == "TUDM MPA 01"
        assert abs(result["altitude_ft"] - 15000) < 10
        assert result["speed_knots"] == 250.0
        assert result["on_ground"] is False

    def test_on_ground_flag(self, encoder):
        """On-ground flag should be in position message."""
        entity = Entity(
            entity_id="GROUND-1", entity_type="RMAF_TRANSPORT",
            domain=Domain.AIR, agency=Agency.RMAF,
            callsign="Test", position=Position(5.0, 118.0, 15.0),
            timestamp=datetime(2026, 4, 15, 8, 0, tzinfo=timezone.utc),
            metadata={"on_ground": True, "vertical_rate_fpm": 0},
        )
        result = encoder.encode_position(entity)
        assert result.endswith("-1")  # on_ground = -1 in SBS
