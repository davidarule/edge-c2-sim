"""Tests for transport registry."""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from simulator.core.entity import Agency, Domain, Entity, EntityStatus, Position
from simulator.transport.registry import TransportRegistry


@pytest.fixture
def sample_entity():
    return Entity(
        entity_id="TEST-001",
        entity_type="MMEA_PATROL",
        domain=Domain.MARITIME,
        agency=Agency.MMEA,
        callsign="KM Test",
        position=Position(latitude=5.0, longitude=118.0),
        timestamp=datetime(2026, 4, 15, tzinfo=timezone.utc),
    )


def make_mock_adapter(name="mock"):
    adapter = MagicMock()
    adapter.name = name
    adapter.connect = AsyncMock()
    adapter.disconnect = AsyncMock()
    adapter.push_entity_update = AsyncMock()
    adapter.push_bulk_update = AsyncMock()
    adapter.push_event = AsyncMock()
    return adapter


class TestTransportRegistry:
    def test_register(self):
        registry = TransportRegistry()
        adapter = make_mock_adapter("ws")
        registry.register(adapter)
        assert registry.count == 1
        assert "ws" in registry.transport_names

    @pytest.mark.asyncio
    async def test_push_to_multiple(self, sample_entity):
        registry = TransportRegistry()
        a1 = make_mock_adapter("ws")
        a2 = make_mock_adapter("rest")
        registry.register(a1)
        registry.register(a2)

        await registry.push_entity_update(sample_entity)

        a1.push_entity_update.assert_awaited_once()
        a2.push_entity_update.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_one_failure_doesnt_stop_others(self, sample_entity):
        registry = TransportRegistry()
        a1 = make_mock_adapter("failing")
        a1.push_entity_update = AsyncMock(side_effect=Exception("boom"))
        a2 = make_mock_adapter("working")
        registry.register(a1)
        registry.register(a2)

        await registry.push_entity_update(sample_entity)

        # a2 should still have been called despite a1 failure
        a2.push_entity_update.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_push_event(self):
        registry = TransportRegistry()
        a1 = make_mock_adapter("ws")
        registry.register(a1)

        event = {"event_type": "DETECTION", "description": "test"}
        await registry.push_event(event)

        a1.push_event.assert_awaited_once_with(event)

    @pytest.mark.asyncio
    async def test_bulk_update(self, sample_entity):
        registry = TransportRegistry()
        a1 = make_mock_adapter("ws")
        registry.register(a1)

        await registry.push_bulk_update([sample_entity])

        a1.push_bulk_update.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_connect_all(self):
        registry = TransportRegistry()
        a1 = make_mock_adapter("ws")
        a2 = make_mock_adapter("rest")
        registry.register(a1)
        registry.register(a2)

        await registry.connect_all()

        a1.connect.assert_awaited_once()
        a2.connect.assert_awaited_once()
