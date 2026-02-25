"""
WebSocket server that broadcasts entity updates to connected COP clients.

Runs a WebSocket server on a configurable port. All connected clients
(typically the CesiumJS COP dashboard) receive real-time entity updates,
events, and clock synchronization messages.
"""

import asyncio
import json
import logging
from typing import Any

import websockets
from websockets.server import ServerConnection

from simulator.core.entity import Entity
from simulator.core.entity_store import EntityStore
from simulator.core.clock import SimulationClock
from simulator.transport.base import TransportAdapter

logger = logging.getLogger(__name__)


class WebSocketAdapter(TransportAdapter):
    """
    WebSocket server broadcasting entity updates to COP clients.

    On client connect, sends a full snapshot of all current entities.
    Broadcasts entity updates, events, and clock sync to all clients.
    Accepts commands from clients (set_speed, pause, resume, reset).
    """

    def __init__(
        self,
        entity_store: EntityStore,
        clock: SimulationClock,
        host: str = "0.0.0.0",
        port: int = 8765,
        scenario_duration_s: float = 0,
    ) -> None:
        self._entity_store = entity_store
        self._clock = clock
        self._host = host
        self._port = port
        self._scenario_duration_s = scenario_duration_s
        self._clients: set[ServerConnection] = set()
        self._server: Any = None
        self._clock_task: asyncio.Task | None = None
        self._command_handlers: dict[str, Any] = {}

    @property
    def name(self) -> str:
        return "websocket"

    def set_command_handler(self, command: str, handler: Any) -> None:
        """Register a handler for incoming client commands."""
        self._command_handlers[command] = handler

    async def connect(self) -> None:
        """Start the WebSocket server."""
        self._server = await websockets.serve(
            self._handle_client,
            self._host,
            self._port,
        )
        self._clock_task = asyncio.create_task(self._broadcast_clock())
        logger.info(f"WebSocket server started on ws://{self._host}:{self._port}")

    async def disconnect(self) -> None:
        """Stop the WebSocket server."""
        if self._clock_task:
            self._clock_task.cancel()
            try:
                await self._clock_task
            except asyncio.CancelledError:
                pass
        if self._server:
            self._server.close()
            await self._server.wait_closed()
        logger.info("WebSocket server stopped")

    async def push_entity_update(self, entity: Entity) -> None:
        """Broadcast entity update to all connected clients."""
        msg = json.dumps({"type": "entity_update", "entity": entity.to_dict()})
        await self._broadcast(msg)

    async def push_event(self, event: dict) -> None:
        """Broadcast operational event to all connected clients."""
        msg = json.dumps({"type": "event", "event": event})
        await self._broadcast(msg)

    async def push_bulk_update(self, entities: list[Entity]) -> None:
        """Broadcast multiple entity updates as a batch."""
        if not entities:
            return
        msg = json.dumps({
            "type": "entity_batch",
            "entities": [e.to_dict() for e in entities],
        })
        await self._broadcast(msg)

    async def push_entity_remove(self, entity_id: str) -> None:
        """Broadcast entity removal."""
        msg = json.dumps({"type": "entity_remove", "entity_id": entity_id})
        await self._broadcast(msg)

    async def _handle_client(self, websocket: ServerConnection) -> None:
        """Handle a single client connection."""
        self._clients.add(websocket)
        logger.info(f"Client connected ({len(self._clients)} total)")

        try:
            # Send snapshot of all current entities
            entities = self._entity_store.get_all_entities()
            snapshot = json.dumps({
                "type": "snapshot",
                "entities": [e.to_dict() for e in entities],
            })
            await websocket.send(snapshot)

            # Listen for commands
            async for message in websocket:
                await self._handle_message(message)

        except websockets.ConnectionClosed:
            pass
        finally:
            self._clients.discard(websocket)
            logger.info(f"Client disconnected ({len(self._clients)} total)")

    async def _handle_message(self, raw: str) -> None:
        """Process an incoming message from a client."""
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning(f"Invalid JSON from client: {raw[:100]}")
            return

        # Support both { type: "..." } and { cmd: "..." } formats
        msg_type = msg.get("cmd") or msg.get("type")

        if msg_type == "set_speed":
            speed = msg.get("speed", 1.0)
            self._clock.set_speed(float(speed))
            logger.info(f"Clock speed set to {speed}x")
        elif msg_type == "pause":
            self._clock.pause()
            logger.info("Clock paused")
        elif msg_type == "resume":
            self._clock.start()
            logger.info("Clock resumed")
        elif msg_type == "snapshot":
            # Re-send full snapshot to requesting client
            pass  # Handled per-client; snapshot sent on connect
        elif msg_type == "reset":
            logger.info("Reset requested by client")
            if "reset" in self._command_handlers:
                await self._command_handlers["reset"](msg)
        elif msg_type in self._command_handlers:
            await self._command_handlers[msg_type](msg)
        else:
            logger.debug(f"Unknown message type: {msg_type}")

    async def _broadcast(self, message: str) -> None:
        """Send a message to all connected clients."""
        if not self._clients:
            return
        disconnected = set()
        for client in self._clients:
            try:
                await client.send(message)
            except websockets.ConnectionClosed:
                disconnected.add(client)
        self._clients -= disconnected

    async def _broadcast_clock(self) -> None:
        """Periodically broadcast clock state to all clients."""
        while True:
            try:
                elapsed = self._clock.get_elapsed().total_seconds()
                progress = 0.0
                if self._scenario_duration_s > 0:
                    progress = min(1.0, elapsed / self._scenario_duration_s)

                msg = json.dumps({
                    "type": "clock",
                    "sim_time": self._clock.get_sim_time().isoformat(),
                    "speed": self._clock.speed,
                    "running": self._clock.is_running,
                    "scenario_progress": round(progress, 3),
                })
                await self._broadcast(msg)
                await asyncio.sleep(1.0)
            except asyncio.CancelledError:
                break

    @property
    def client_count(self) -> int:
        """Number of connected clients."""
        return len(self._clients)
