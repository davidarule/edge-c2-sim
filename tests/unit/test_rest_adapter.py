"""Tests for REST API transport adapter."""

import asyncio
from datetime import datetime, timezone

import pytest

from simulator.core.entity import Agency, Domain, Entity, EntityStatus, Position
from simulator.transport.rest_adapter import RESTAdapter, BatchBuffer


@pytest.fixture
def rest_adapter():
    """Create REST adapter in dry-run mode."""
    adapter = RESTAdapter(
        api_spec_path="config/edge_c2_api.yaml",
        base_url="http://localhost:9000",
        dry_run=True,
        batch_mode=False,
    )
    return adapter


@pytest.fixture
def sample_entity():
    return Entity(
        entity_id="TEST-001",
        entity_type="MMEA_PATROL",
        domain=Domain.MARITIME,
        agency=Agency.MMEA,
        callsign="KM Test",
        position=Position(latitude=5.84, longitude=118.07, altitude_m=0),
        heading_deg=45.0,
        speed_knots=18.5,
        course_deg=47.0,
        timestamp=datetime(2026, 4, 15, 8, 14, 0, tzinfo=timezone.utc),
        status=EntityStatus.ACTIVE,
        sidc="10033000001211040000",
    )


class TestSpecParsing:
    def test_load_spec(self, rest_adapter):
        rest_adapter._load_spec()
        assert rest_adapter._spec.get("openapi") == "3.0.3"
        assert "paths" in rest_adapter._spec

    def test_build_endpoint_map(self, rest_adapter):
        rest_adapter._load_spec()
        rest_adapter._build_endpoint_map()
        assert "position_update" in rest_adapter.endpoints
        assert "bulk_update" in rest_adapter.endpoints
        assert "entity_create" in rest_adapter.endpoints
        assert "event_create" in rest_adapter.endpoints
        assert "health" in rest_adapter.endpoints
        assert "ais_signal" in rest_adapter.endpoints
        assert "adsb_signal" in rest_adapter.endpoints

    def test_endpoint_paths_include_base(self, rest_adapter):
        rest_adapter._load_spec()
        rest_adapter._build_endpoint_map()
        _, path = rest_adapter.endpoints["position_update"]
        assert "/api/v1/" in path

    def test_endpoint_methods(self, rest_adapter):
        rest_adapter._load_spec()
        rest_adapter._build_endpoint_map()
        method, _ = rest_adapter.endpoints["health"]
        assert method == "get"
        method, _ = rest_adapter.endpoints["position_update"]
        assert method == "post"


class TestPayloadGeneration:
    def test_position_payload(self, rest_adapter, sample_entity):
        entity_dict = sample_entity.to_dict()
        payload = rest_adapter._entity_to_position_payload(entity_dict)
        assert payload["position"]["latitude"] == pytest.approx(5.84)
        assert payload["position"]["longitude"] == pytest.approx(118.07)
        assert payload["heading_deg"] == pytest.approx(45.0)
        assert payload["speed_knots"] == pytest.approx(18.5)
        assert "timestamp" in payload

    def test_full_entity_payload(self, rest_adapter, sample_entity):
        entity_dict = sample_entity.to_dict()
        payload = rest_adapter._entity_to_full_payload(entity_dict)
        assert payload["entity_id"] == "TEST-001"
        assert payload["entity_type"] == "MMEA_PATROL"
        assert payload["domain"] == "MARITIME"
        assert payload["agency"] == "MMEA"
        assert payload["callsign"] == "KM Test"
        assert payload["sidc"] == "10033000001211040000"

    def test_event_payload(self, rest_adapter):
        event = {
            "event_type": "DETECTION",
            "description": "Radar contact detected",
            "time": "2026-04-15T08:00:00Z",
            "severity": "WARNING",
            "target": "IFF-001",
            "alert_agencies": ["MMEA", "MIL"],
            "position": {"latitude": 5.8, "longitude": 118.88},
        }
        payload = rest_adapter._event_to_payload(event)
        assert payload["event_type"] == "DETECTION"
        assert payload["severity"] == "WARNING"
        assert payload["target_entity_id"] == "IFF-001"
        assert payload["agencies_involved"] == ["MMEA", "MIL"]
        assert "position" in payload


class TestDryRun:
    @pytest.mark.asyncio
    async def test_dry_run_logs_payloads(self, rest_adapter, sample_entity):
        await rest_adapter.connect()
        await rest_adapter.push_entity_update(sample_entity)
        await rest_adapter.disconnect()

        assert len(rest_adapter.dry_run_log) > 0
        entry = rest_adapter.dry_run_log[0]
        assert "method" in entry
        assert "path" in entry
        assert "payload" in entry

    @pytest.mark.asyncio
    async def test_dry_run_health_check(self, rest_adapter):
        await rest_adapter.connect()
        result = await rest_adapter.health_check()
        assert result is True
        await rest_adapter.disconnect()


class TestBatchBuffer:
    @pytest.mark.asyncio
    async def test_batch_accumulates(self):
        flushed = []

        async def flush_cb(items):
            flushed.extend(items)

        buf = BatchBuffer(interval_s=0.1, flush_callback=flush_cb)
        buf.add({"a": 1})
        buf.add({"b": 2})
        await buf.flush_now()

        assert len(flushed) == 2
        assert flushed[0] == {"a": 1}

    @pytest.mark.asyncio
    async def test_batch_clears_after_flush(self):
        async def flush_cb(items):
            pass

        buf = BatchBuffer(interval_s=0.1, flush_callback=flush_cb)
        buf.add({"a": 1})
        await buf.flush_now()
        assert len(buf.buffer) == 0
