"""
AIS Live Feed — streams real-time vessel positions from AISStream.io
into the simulator's entity store and WebSocket adapter.

Entities created here use the AIS- prefix and are treated as live data:
they must NOT be cleared by scenario reset/restart/load operations.

Prerequisites:
  - websockets package (already a project dependency)
  - AISSTREAM_API_KEY environment variable or constructor argument

Author: David Rule / BrumbieSoft
"""

import asyncio
import json
import logging
import time
from datetime import datetime, timezone

import websockets

from simulator.core.entity import Agency, Domain, Entity, EntityStatus, Position
from simulator.core.entity_store import EntityStore
from simulator.transport.websocket_adapter import WebSocketAdapter

logger = logging.getLogger(__name__)

AIS_ENTITY_PREFIX = "AIS-"

# ── AIS ship_type_code → Edge C2 entity type ─────────────────────────────────
# Mirrors scripts/ais_to_scenario.py AIS_TYPE_MAP

AIS_TYPE_MAP: dict[int, str] = {
    **{code: "CIVILIAN_FISHING" for code in range(30, 40)},
    **{code: "CIVILIAN_BOAT" for code in range(40, 50)},
    50: "CIVILIAN_BOAT", 51: "CIVILIAN_BOAT", 52: "CIVILIAN_BOAT",
    53: "CIVILIAN_BOAT", 54: "CIVILIAN_BOAT", 56: "CIVILIAN_BOAT",
    57: "CIVILIAN_BOAT", 58: "CIVILIAN_BOAT", 59: "CIVILIAN_BOAT",
    **{code: "CIVILIAN_PASSENGER" for code in range(60, 70)},
    **{code: "CIVILIAN_CARGO" for code in range(70, 80)},
    **{code: "CIVILIAN_TANKER" for code in range(80, 90)},
    **{code: "CIVILIAN_BOAT" for code in range(90, 100)},
}

# Bounding boxes: SE Asian waters (same as ais_capture.py)
BOUNDING_BOXES = [
    [[-2.0, 95.0], [8.0, 106.0]],     # Malacca + West Malaysia + Singapore
    [[-1.0, 106.0], [8.0, 120.0]],     # SCS + East Malaysia + Brunei
    [[-11.0, 106.0], [-1.0, 142.0]],   # Java Sea + Southern Borneo
    [[-1.0, 120.0], [8.0, 142.0]],     # Celebes Sea + Eastern Borneo
    [[-8.0, 93.0], [-2.0, 106.0]],     # Western Sumatra / Indian Ocean
]

POSITION_MSG_TYPES = [
    "PositionReport",
    "StandardClassBPositionReport",
    "ExtendedClassBPositionReport",
]
STATIC_MSG_TYPES = ["ShipStaticData", "StaticDataReport"]
ALL_MSG_TYPES = POSITION_MSG_TYPES + STATIC_MSG_TYPES

# SIDC for neutral surface (civilian vessel)
DEFAULT_SIDC = "SNSP------"


def _map_entity_type(ship_type_code: int, length_m: float | None = None) -> str:
    base = AIS_TYPE_MAP.get(ship_type_code, "CIVILIAN_CARGO")
    if base == "CIVILIAN_TANKER" and length_m and length_m >= 250:
        return "CIVILIAN_TANKER_VLCC"
    return base


class AISLiveFeed:
    """Streams live AIS data into the simulator entity store."""

    def __init__(
        self,
        api_key: str,
        entity_store: EntityStore,
        ws_adapter: WebSocketAdapter,
        max_entities: int = 300,
        update_interval_s: float = 30.0,
        stale_seconds: float = 300.0,
        position_threshold_deg: float = 0.0001,
    ):
        self._api_key = api_key
        self._store = entity_store
        self._ws = ws_adapter
        self._max_entities = max_entities
        self._update_interval = update_interval_s
        self._stale_seconds = stale_seconds
        self._pos_threshold = position_threshold_deg
        self._stop = asyncio.Event()

        # Per-MMSI tracking
        self._last_broadcast: dict[int, float] = {}   # mmsi -> monotonic time
        self._last_position: dict[int, tuple[float, float]] = {}  # mmsi -> (lat, lon)
        self._last_seen: dict[int, float] = {}         # mmsi -> monotonic time

        # Counters
        self._position_count = 0
        self._static_count = 0
        self._active_count = 0

    @property
    def entity_count(self) -> int:
        return self._active_count

    def stop(self) -> None:
        self._stop.set()

    # ── Message processing ────────────────────────────────────────────────

    def _process_position(self, msg: dict, msg_type: str, metadata: dict) -> None:
        body = msg.get(msg_type, {})
        mmsi = body.get("UserID", metadata.get("MMSI"))
        if not mmsi:
            return

        lat = body.get("Latitude", metadata.get("latitude"))
        lon = body.get("Longitude", metadata.get("longitude"))
        if lat is None or lon is None:
            return
        if abs(lat) < 0.001 and abs(lon) < 0.001:
            return

        sog = body.get("Sog", 0.0) or 0.0
        cog = body.get("Cog", 0.0) or 0.0
        heading = body.get("TrueHeading", 0)
        if heading == 511:
            heading = cog
        ship_name = metadata.get("ShipName", "").strip()

        now = time.monotonic()
        self._last_seen[mmsi] = now
        self._position_count += 1

        # Throttle: only broadcast if position changed or interval elapsed
        prev_pos = self._last_position.get(mmsi)
        prev_time = self._last_broadcast.get(mmsi, 0)
        time_since = now - prev_time

        pos_changed = True
        if prev_pos:
            dlat = abs(lat - prev_pos[0])
            dlon = abs(lon - prev_pos[1])
            pos_changed = dlat > self._pos_threshold or dlon > self._pos_threshold

        if not pos_changed and time_since < self._update_interval:
            return

        # Check entity limit
        entity_id = f"{AIS_ENTITY_PREFIX}{mmsi}"
        existing = self._store.get_entity(entity_id)
        if not existing and self._active_count >= self._max_entities:
            return  # at limit, drop silently

        # Create or update entity
        if existing:
            existing.update_position(
                latitude=lat, longitude=lon,
                heading_deg=heading, speed_knots=sog, course_deg=cog,
            )
            if ship_name and not existing.metadata.get("ship_name"):
                existing.metadata["ship_name"] = ship_name
                existing.callsign = ship_name or existing.callsign
            self._store.upsert_entity(existing)
            entity = existing
        else:
            entity_type = _map_entity_type(0)  # default until static msg arrives
            entity = Entity(
                entity_id=entity_id,
                entity_type=entity_type,
                domain=Domain.MARITIME,
                agency=Agency.CIVILIAN,
                callsign=ship_name or f"MMSI {mmsi}",
                position=Position(latitude=lat, longitude=lon),
                heading_deg=heading,
                speed_knots=sog,
                course_deg=cog,
                status=EntityStatus.ACTIVE,
                sidc=DEFAULT_SIDC,
                metadata={
                    "background": True,
                    "source": "AIS_LIVE",
                    "mmsi": str(mmsi),
                    "entity_type_name": entity_type,
                },
            )
            self._store.upsert_entity(entity)
            self._active_count += 1

        self._last_position[mmsi] = (lat, lon)
        self._last_broadcast[mmsi] = now

        # Push to WebSocket clients
        asyncio.ensure_future(self._ws.push_entity_update(entity))

    def _process_static(self, msg: dict, msg_type: str, metadata: dict) -> None:
        mmsi = metadata.get("MMSI")
        if not mmsi:
            body = msg.get(msg_type, {})
            mmsi = body.get("UserID")
        if not mmsi:
            return

        entity_id = f"{AIS_ENTITY_PREFIX}{mmsi}"
        entity = self._store.get_entity(entity_id)
        if not entity:
            return  # static for vessel we haven't seen a position for yet

        self._static_count += 1
        self._last_seen[mmsi] = time.monotonic()
        body = msg.get(msg_type, {})

        if msg_type == "ShipStaticData":
            name = body.get("Name", "").strip()
            if name:
                entity.callsign = name
                entity.metadata["ship_name"] = name
            callsign = body.get("CallSign", "").strip()
            if callsign:
                entity.metadata["call_sign"] = callsign
            imo = body.get("ImoNumber")
            if imo:
                entity.metadata["imo_number"] = str(imo)
            ship_type = body.get("Type", 0)
            if ship_type:
                entity.metadata["ship_type_code"] = ship_type
                dim = body.get("Dimension", {})
                dim_a = dim.get("A", 0) or 0
                dim_b = dim.get("B", 0) or 0
                length = dim_a + dim_b if dim_a and dim_b else None
                new_type = _map_entity_type(ship_type, length)
                entity.entity_type = new_type
                entity.metadata["entity_type_name"] = new_type
                if length:
                    entity.metadata["length_m"] = length
                dim_c = dim.get("C", 0) or 0
                dim_d = dim.get("D", 0) or 0
                beam = dim_c + dim_d if dim_c and dim_d else None
                if beam:
                    entity.metadata["beam_m"] = beam
            draught = body.get("MaximumStaticDraught")
            if draught:
                entity.metadata["draught_m"] = draught
            dest = body.get("Destination", "").strip()
            if dest:
                entity.metadata["destination"] = dest

        elif msg_type == "StaticDataReport":
            report_a = body.get("ReportA", {})
            report_b = body.get("ReportB", {})
            if report_a.get("Valid"):
                name = report_a.get("Name", "").strip()
                if name:
                    entity.callsign = name
                    entity.metadata["ship_name"] = name
            if report_b.get("Valid"):
                callsign = report_b.get("CallSign", "").strip()
                if callsign:
                    entity.metadata["call_sign"] = callsign
                ship_type = report_b.get("ShipType", 0)
                if ship_type:
                    entity.metadata["ship_type_code"] = ship_type
                    dim = report_b.get("Dimension", {})
                    dim_a = dim.get("A", 0) or 0
                    dim_b = dim.get("B", 0) or 0
                    length = dim_a + dim_b if dim_a and dim_b else None
                    entity.entity_type = _map_entity_type(ship_type, length)
                    entity.metadata["entity_type_name"] = entity.entity_type

        self._store.upsert_entity(entity)

    def _process_message(self, raw: str) -> None:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return

        if "error" in data:
            logger.warning(f"AISStream error: {data['error']}")
            return

        msg_type = data.get("MessageType", "")
        metadata = data.get("MetaData", {})
        message = data.get("Message", {})

        if msg_type in POSITION_MSG_TYPES:
            self._process_position(message, msg_type, metadata)
        elif msg_type in STATIC_MSG_TYPES:
            self._process_static(message, msg_type, metadata)

    # ── Stale entity cleanup ──────────────────────────────────────────────

    async def _cleanup_loop(self) -> None:
        while not self._stop.is_set():
            await asyncio.sleep(60)
            now = time.monotonic()
            stale = [
                mmsi for mmsi, seen in self._last_seen.items()
                if now - seen > self._stale_seconds
            ]
            for mmsi in stale:
                entity_id = f"{AIS_ENTITY_PREFIX}{mmsi}"
                try:
                    self._store.remove_entity(entity_id)
                except KeyError:
                    pass
                await self._ws.push_entity_remove(entity_id)
                self._last_seen.pop(mmsi, None)
                self._last_position.pop(mmsi, None)
                self._last_broadcast.pop(mmsi, None)
                self._active_count = max(0, self._active_count - 1)

            if stale:
                logger.info(
                    f"AIS cleanup: removed {len(stale)} stale vessels "
                    f"({self._active_count} active)"
                )

    # ── WebSocket connection with reconnect ───────────────────────────────

    async def _connect_and_stream(self) -> None:
        subscription = {
            "APIKey": self._api_key,
            "BoundingBoxes": BOUNDING_BOXES,
            "FilterMessageTypes": ALL_MSG_TYPES,
        }

        logger.info("AIS feed: connecting to AISStream.io...")

        async with websockets.connect(
            "wss://stream.aisstream.io/v0/stream",
            ping_interval=20,
            ping_timeout=30,
            close_timeout=5,
            max_size=2**20,
        ) as ws:
            await ws.send(json.dumps(subscription))
            logger.info("AIS feed: subscription active, receiving data")

            async for raw_msg in ws:
                if self._stop.is_set():
                    return
                self._process_message(raw_msg)

    async def run(self) -> None:
        """Main loop: connect, stream, reconnect on failure."""
        cleanup_task = asyncio.create_task(self._cleanup_loop())
        reconnect_count = 0

        try:
            while not self._stop.is_set():
                try:
                    await self._connect_and_stream()
                except (
                    websockets.exceptions.ConnectionClosed,
                    websockets.exceptions.ConnectionClosedError,
                    websockets.exceptions.ConnectionClosedOK,
                    ConnectionRefusedError,
                    OSError,
                ) as e:
                    reconnect_count += 1
                    delay = min(2 * (2 ** (reconnect_count - 1)), 60)
                    logger.warning(
                        f"AIS feed lost ({e.__class__.__name__}). "
                        f"Reconnecting in {delay}s (attempt {reconnect_count})..."
                    )
                    await asyncio.sleep(delay)
                    # Reset backoff after successful reconnection
                except asyncio.CancelledError:
                    break
                else:
                    reconnect_count = 0  # reset on clean disconnect
        finally:
            cleanup_task.cancel()
            try:
                await cleanup_task
            except asyncio.CancelledError:
                pass
            logger.info(
                f"AIS feed stopped. "
                f"Positions: {self._position_count}, "
                f"Statics: {self._static_count}, "
                f"Active vessels: {self._active_count}"
            )
