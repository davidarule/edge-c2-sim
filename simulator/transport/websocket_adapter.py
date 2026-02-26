"""
WebSocket server that broadcasts entity updates to connected COP clients.

Runs a WebSocket server on a configurable port. All connected clients
(typically the CesiumJS COP dashboard) receive real-time entity updates,
events, and clock synchronization messages.

Authentication:
  When WS_AUTH=true (default in production), the server validates JWT tokens
  on WebSocket connection upgrade. Tokens are read from:
    1. The 'edge_c2_session' cookie in the upgrade request headers
    2. A 'token' query parameter in the connection URL
  The JWT_SECRET must match the auth service's secret.
  For development (WS_AUTH=false), auth is disabled.
"""

import asyncio
import json
import logging
import os
from typing import Any
from urllib.parse import urlparse, parse_qs

import websockets
from websockets.server import ServerConnection

from simulator.core.entity import Entity
from simulator.core.entity_store import EntityStore
from simulator.core.clock import SimulationClock
from simulator.transport.base import TransportAdapter

logger = logging.getLogger(__name__)

# JWT validation for WebSocket connections
_ws_auth_enabled = os.environ.get("WS_AUTH", "false").lower() == "true"
_jwt_secret = os.environ.get("JWT_SECRET", "")
_jwt_algorithm = os.environ.get("JWT_ALGORITHM", "HS256")
_cookie_name = os.environ.get("COOKIE_NAME", "edge_c2_session")


def _validate_ws_token(path: str, request_headers) -> bool:
    """Validate JWT token from cookie or query parameter.

    Returns True if auth is disabled or token is valid.
    """
    if not _ws_auth_enabled:
        return True

    if not _jwt_secret:
        logger.warning("WS_AUTH=true but JWT_SECRET not set, allowing all connections")
        return True

    try:
        from jose import jwt, JWTError
    except ImportError:
        logger.warning("python-jose not installed, skipping WS auth")
        return True

    token = None

    # Try cookie first
    cookie_header = request_headers.get("Cookie", "")
    if cookie_header:
        for part in cookie_header.split(";"):
            part = part.strip()
            if part.startswith(f"{_cookie_name}="):
                token = part[len(_cookie_name) + 1:]
                break

    # Try query parameter as fallback
    if not token:
        parsed = urlparse(path)
        params = parse_qs(parsed.query)
        tokens = params.get("token", [])
        if tokens:
            token = tokens[0]

    if not token:
        logger.info("WebSocket connection rejected: no auth token")
        return False

    try:
        jwt.decode(token, _jwt_secret, algorithms=[_jwt_algorithm])
        return True
    except JWTError as e:
        logger.info(f"WebSocket connection rejected: invalid token ({e})")
        return False


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
        self._route_data: dict[str, list[dict]] = {}
        # Trail history: entity_id -> list of {lat, lon, alt, ts}
        self._trail_history: dict[str, list[dict]] = {}
        self._max_trail_points = 2000  # Max points per entity
        # Event history: list of event dicts
        self._event_history: list[dict] = []

    @property
    def name(self) -> str:
        return "websocket"

    def set_command_handler(self, command: str, handler: Any) -> None:
        """Register a handler for incoming client commands."""
        self._command_handlers[command] = handler

    def set_route_data(self, routes: dict) -> None:
        """Store planned route data for COP display.

        Args:
            routes: Maps entity_id to list of waypoint dicts
                    [{"lat": ..., "lon": ..., "alt_m": ...}, ...]
        """
        self._route_data = routes

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
        self._event_history.append(event)
        msg = json.dumps({"type": "event", "event": event})
        await self._broadcast(msg)

    async def push_bulk_update(self, entities: list[Entity]) -> None:
        """Broadcast multiple entity updates as a batch."""
        if not entities:
            return

        # Accumulate trail history for each entity
        for entity in entities:
            eid = entity.entity_id
            pos = entity.position
            if not pos or (pos.latitude == 0 and pos.longitude == 0):
                continue
            ts = entity.timestamp.isoformat() if entity.timestamp else None
            ts_ms = int(entity.timestamp.timestamp() * 1000) if entity.timestamp else 0
            point = {
                "lat": pos.latitude,
                "lon": pos.longitude,
                "alt": pos.altitude_m,
                "ts": ts_ms,
            }
            if eid not in self._trail_history:
                self._trail_history[eid] = []
            trail = self._trail_history[eid]
            # Skip if entity hasn't moved
            if trail:
                last = trail[-1]
                dlat = abs(point["lat"] - last["lat"])
                dlon = abs(point["lon"] - last["lon"])
                if dlat < 0.0001 and dlon < 0.0001:
                    continue
            trail.append(point)
            if len(trail) > self._max_trail_points:
                trail.pop(0)

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
        # Validate JWT token on connection
        if not _validate_ws_token(websocket.request.path or "/", websocket.request.headers):
            await websocket.close(4001, "Unauthorized")
            return

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

            # Send trail history so new clients get full trails immediately
            if self._trail_history:
                trail_msg = json.dumps({
                    "type": "trail_history",
                    "trails": self._trail_history,
                })
                await websocket.send(trail_msg)

            # Send event history so timeline shows past events
            if self._event_history:
                for evt in self._event_history:
                    await websocket.send(json.dumps({"type": "event", "event": evt}))

            # Send planned routes if available
            if self._route_data:
                routes_msg = json.dumps({"type": "routes", "routes": self._route_data})
                await websocket.send(routes_msg)

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
            # Re-send full snapshot to requesting client - broadcast to all
            entities = self._entity_store.get_all_entities()
            snapshot = json.dumps({"type": "snapshot", "entities": [e.to_dict() for e in entities]})
            await self._broadcast(snapshot)
            if self._route_data:
                routes_msg = json.dumps({"type": "routes", "routes": self._route_data})
                await self._broadcast(routes_msg)
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
