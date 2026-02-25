"""Tests for the WebSocket transport adapter."""

import asyncio
import json

import pytest
import websockets

from simulator.core.clock import SimulationClock
from simulator.core.entity import Agency, Domain, Entity, EntityStatus, Position
from simulator.core.entity_store import EntityStore
from simulator.transport.websocket_adapter import WebSocketAdapter


def _make_entity(entity_id: str = "TEST-001") -> Entity:
    return Entity(
        entity_id=entity_id,
        entity_type="MMEA_PATROL",
        domain=Domain.MARITIME,
        agency=Agency.MMEA,
        callsign=f"Test {entity_id}",
        position=Position(latitude=2.5, longitude=102.0),
        heading_deg=90.0,
        speed_knots=15.0,
        status=EntityStatus.ACTIVE,
    )


@pytest.fixture
async def ws_server():
    """Start a WebSocket adapter server and yield it, then clean up."""
    store = EntityStore()
    clock = SimulationClock(speed=1.0)
    clock.start()
    adapter = WebSocketAdapter(entity_store=store, clock=clock, port=0)
    await adapter.connect()
    # Get the actual port assigned
    port = adapter._server.sockets[0].getsockname()[1]
    yield adapter, store, clock, port
    await adapter.disconnect()


@pytest.mark.asyncio
async def test_client_receives_snapshot(ws_server):
    adapter, store, clock, port = ws_server
    # Add an entity before client connects
    entity = _make_entity()
    store.add_entity(entity)

    async with websockets.connect(f"ws://localhost:{port}") as ws:
        msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=2.0))
        assert msg["type"] == "snapshot"
        assert len(msg["entities"]) == 1
        assert msg["entities"][0]["entity_id"] == "TEST-001"


@pytest.mark.asyncio
async def test_entity_update_broadcast(ws_server):
    adapter, store, clock, port = ws_server

    async with websockets.connect(f"ws://localhost:{port}") as ws:
        # Consume snapshot
        await asyncio.wait_for(ws.recv(), timeout=2.0)

        # Push an entity update
        entity = _make_entity()
        await adapter.push_entity_update(entity)

        msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=2.0))
        assert msg["type"] == "entity_update"
        assert msg["entity"]["entity_id"] == "TEST-001"


@pytest.mark.asyncio
async def test_event_broadcast(ws_server):
    adapter, store, clock, port = ws_server

    async with websockets.connect(f"ws://localhost:{port}") as ws:
        # Consume snapshot
        await asyncio.wait_for(ws.recv(), timeout=2.0)

        await adapter.push_event({"event_type": "ALERT", "description": "Test"})

        msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=2.0))
        assert msg["type"] == "event"
        assert msg["event"]["event_type"] == "ALERT"


@pytest.mark.asyncio
async def test_clock_broadcast(ws_server):
    adapter, store, clock, port = ws_server

    async with websockets.connect(f"ws://localhost:{port}") as ws:
        # Consume snapshot
        await asyncio.wait_for(ws.recv(), timeout=2.0)

        # Wait for a clock message (broadcasts every 1 second)
        msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=3.0))
        assert msg["type"] == "clock"
        assert "sim_time" in msg
        assert "speed" in msg
        assert "running" in msg


@pytest.mark.asyncio
async def test_multiple_clients(ws_server):
    adapter, store, clock, port = ws_server

    async with websockets.connect(f"ws://localhost:{port}") as ws1:
        async with websockets.connect(f"ws://localhost:{port}") as ws2:
            # Both get snapshots
            await asyncio.wait_for(ws1.recv(), timeout=2.0)
            await asyncio.wait_for(ws2.recv(), timeout=2.0)

            assert adapter.client_count == 2

            # Both receive update
            entity = _make_entity()
            await adapter.push_entity_update(entity)

            msg1 = json.loads(await asyncio.wait_for(ws1.recv(), timeout=2.0))
            msg2 = json.loads(await asyncio.wait_for(ws2.recv(), timeout=2.0))
            assert msg1["type"] == "entity_update"
            assert msg2["type"] == "entity_update"


@pytest.mark.asyncio
async def test_client_speed_command(ws_server):
    adapter, store, clock, port = ws_server

    async with websockets.connect(f"ws://localhost:{port}") as ws:
        await asyncio.wait_for(ws.recv(), timeout=2.0)

        await ws.send(json.dumps({"type": "set_speed", "speed": 10}))
        await asyncio.sleep(0.1)
        assert clock.speed == 10.0


@pytest.mark.asyncio
async def test_client_pause_resume(ws_server):
    adapter, store, clock, port = ws_server

    async with websockets.connect(f"ws://localhost:{port}") as ws:
        await asyncio.wait_for(ws.recv(), timeout=2.0)

        await ws.send(json.dumps({"type": "pause"}))
        await asyncio.sleep(0.1)
        assert not clock.is_running

        await ws.send(json.dumps({"type": "resume"}))
        await asyncio.sleep(0.1)
        assert clock.is_running


@pytest.mark.asyncio
async def test_client_disconnect_doesnt_crash(ws_server):
    adapter, store, clock, port = ws_server

    ws = await websockets.connect(f"ws://localhost:{port}")
    await asyncio.wait_for(ws.recv(), timeout=2.0)
    assert adapter.client_count == 1

    await ws.close()
    await asyncio.sleep(0.1)

    # Server should still work
    entity = _make_entity()
    await adapter.push_entity_update(entity)  # Should not raise
