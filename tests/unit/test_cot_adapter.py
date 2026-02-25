"""Tests for CoT/TAK transport adapter."""

import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import pytest

from simulator.transport.cot_adapter import CoTAdapter, COT_TYPE_MAP, KNOTS_TO_MS


@pytest.fixture
def cot_adapter():
    return CoTAdapter(enabled=False)


@pytest.fixture
def sample_entity_dict():
    return {
        "entity_id": "MMEA-PV-101",
        "entity_type": "MMEA_PATROL",
        "domain": "MARITIME",
        "agency": "MMEA",
        "callsign": "KM Semporna",
        "position": {"latitude": 5.84, "longitude": 118.07, "altitude_m": 0},
        "heading_deg": 45.2,
        "speed_knots": 18.5,
        "course_deg": 47.0,
        "timestamp": "2026-04-15T08:14:32Z",
        "status": "ACTIVE",
    }


class TestCoTGeneration:
    def test_entity_to_cot_valid_xml(self, cot_adapter, sample_entity_dict):
        xml_str = cot_adapter.entity_to_cot(sample_entity_dict)
        # Parse should not raise
        root = ET.fromstring(xml_str.replace('<?xml version="1.0" encoding="UTF-8"?>', ''))
        assert root.tag == "event"
        assert root.get("version") == "2.0"

    def test_entity_uid_matches(self, cot_adapter, sample_entity_dict):
        xml_str = cot_adapter.entity_to_cot(sample_entity_dict)
        root = ET.fromstring(xml_str.replace('<?xml version="1.0" encoding="UTF-8"?>', ''))
        assert root.get("uid") == "MMEA-PV-101"

    def test_cot_type_friendly_maritime(self, cot_adapter, sample_entity_dict):
        xml_str = cot_adapter.entity_to_cot(sample_entity_dict)
        root = ET.fromstring(xml_str.replace('<?xml version="1.0" encoding="UTF-8"?>', ''))
        assert root.get("type") == "a-f-S-X-N"

    def test_cot_point_coordinates(self, cot_adapter, sample_entity_dict):
        xml_str = cot_adapter.entity_to_cot(sample_entity_dict)
        root = ET.fromstring(xml_str.replace('<?xml version="1.0" encoding="UTF-8"?>', ''))
        point = root.find("point")
        assert float(point.get("lat")) == pytest.approx(5.84)
        assert float(point.get("lon")) == pytest.approx(118.07)

    def test_speed_converted_to_ms(self, cot_adapter, sample_entity_dict):
        xml_str = cot_adapter.entity_to_cot(sample_entity_dict)
        root = ET.fromstring(xml_str.replace('<?xml version="1.0" encoding="UTF-8"?>', ''))
        track = root.find(".//track")
        speed_ms = float(track.get("speed"))
        expected = 18.5 * KNOTS_TO_MS
        assert speed_ms == pytest.approx(expected, rel=0.01)

    def test_stale_time_after_timestamp(self, cot_adapter, sample_entity_dict):
        xml_str = cot_adapter.entity_to_cot(sample_entity_dict)
        root = ET.fromstring(xml_str.replace('<?xml version="1.0" encoding="UTF-8"?>', ''))
        stale_str = root.get("stale")
        start_str = root.get("start")
        stale = datetime.strptime(stale_str, "%Y-%m-%dT%H:%M:%S.000Z")
        start = datetime.strptime(start_str, "%Y-%m-%dT%H:%M:%S.000Z")
        assert stale > start

    def test_contact_callsign(self, cot_adapter, sample_entity_dict):
        xml_str = cot_adapter.entity_to_cot(sample_entity_dict)
        root = ET.fromstring(xml_str.replace('<?xml version="1.0" encoding="UTF-8"?>', ''))
        contact = root.find(".//contact")
        assert contact.get("callsign") == "KM Semporna"

    def test_detail_remarks(self, cot_adapter, sample_entity_dict):
        xml_str = cot_adapter.entity_to_cot(sample_entity_dict)
        root = ET.fromstring(xml_str.replace('<?xml version="1.0" encoding="UTF-8"?>', ''))
        remarks = root.find(".//remarks")
        assert "MMEA" in remarks.text
        assert "ACTIVE" in remarks.text


class TestCoTTypeMapping:
    def test_all_entity_types_mapped(self):
        expected_types = [
            "MMEA_PATROL", "MMEA_FAST_INTERCEPT", "MIL_NAVAL",
            "SUSPECT_VESSEL", "CIVILIAN_CARGO", "CIVILIAN_FISHING",
            "RMAF_FIGHTER", "RMAF_HELICOPTER", "RMAF_TRANSPORT",
            "RMP_PATROL_CAR", "RMP_TACTICAL_TEAM", "MIL_APC",
            "MIL_INFANTRY_SQUAD", "CI_OFFICER",
        ]
        for et in expected_types:
            assert et in COT_TYPE_MAP, f"Missing CoT mapping for {et}"

    def test_hostile_vessel_type(self):
        assert COT_TYPE_MAP["SUSPECT_VESSEL"].startswith("a-h")

    def test_friendly_types_start_with_af(self):
        for et in ["MMEA_PATROL", "RMAF_FIGHTER", "RMP_PATROL_CAR"]:
            assert COT_TYPE_MAP[et].startswith("a-f")

    def test_neutral_civilian_types(self):
        for et in ["CIVILIAN_CARGO", "CIVILIAN_FISHING"]:
            assert COT_TYPE_MAP[et].startswith("a-n")


class TestEventToCoT:
    def test_event_geochat_format(self, cot_adapter):
        event = {
            "description": "Radar contact detected",
            "time": "2026-04-15T08:00:00Z",
            "position": {"latitude": 5.8, "longitude": 118.88},
        }
        xml_str = cot_adapter.event_to_cot(event)
        root = ET.fromstring(xml_str.replace('<?xml version="1.0" encoding="UTF-8"?>', ''))
        assert root.get("type") == "b-t-f"
        remarks = root.find(".//remarks")
        assert "Radar contact detected" in remarks.text
