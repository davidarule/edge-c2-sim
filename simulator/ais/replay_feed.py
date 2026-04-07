"""
AIS Replay Feed — replays captured AIS CSV data at real-time pace.

Reads positions and statics CSVs captured by scripts/ais_capture.py and
feeds them into the entity store and WebSocket adapter using the original
timestamps to pace delivery. The 2-hour capture loops continuously.

Same entity management as live_feed.py: AIS- prefix entities, throttled
broadcasts, stale cleanup, preserved across scenario reset.
"""

import asyncio
import csv
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from simulator.ais.live_feed import (
    AIS_ENTITY_PREFIX,
    DEFAULT_SIDC,
    _map_entity_type,
)
from simulator.core.entity import Agency, Domain, Entity, EntityStatus, Position
from simulator.core.entity_store import EntityStore
from simulator.transport.websocket_adapter import WebSocketAdapter

logger = logging.getLogger(__name__)


def _parse_ts(ts_str: str) -> float:
    """Parse AISStream timestamp to epoch seconds.

    Format: '2026-04-07 06:35:21.513409294 +0000 UTC'
    """
    # Trim nanoseconds to microseconds and drop ' UTC' suffix
    clean = ts_str.strip()
    if clean.endswith(" UTC"):
        clean = clean[:-4]
    # '2026-04-07 06:35:21.513409294 +0000' → trim fractional to 6 digits
    parts = clean.split(".")
    if len(parts) == 2:
        frac_and_tz = parts[1]
        # Split off timezone: '513409294 +0000'
        frac_parts = frac_and_tz.split(" ", 1)
        frac = frac_parts[0][:6]  # microseconds
        tz = frac_parts[1] if len(frac_parts) > 1 else "+0000"
        clean = f"{parts[0]}.{frac} {tz}"
    try:
        dt = datetime.strptime(clean, "%Y-%m-%d %H:%M:%S.%f %z")
    except ValueError:
        dt = datetime.strptime(clean, "%Y-%m-%d %H:%M:%S %z")
    return dt.timestamp()


class AISReplayFeed:
    """Replays captured AIS CSV data at real-time pace."""

    def __init__(
        self,
        positions_csv: str,
        statics_csv: str,
        entity_store: EntityStore,
        ws_adapter: WebSocketAdapter,
        max_entities: int = 300,
        update_interval_s: float = 30.0,
        stale_seconds: float = 300.0,
        position_threshold_deg: float = 0.0001,
        speed: float = 1.0,
    ):
        self._positions_path = Path(positions_csv)
        self._statics_path = Path(statics_csv)
        self._store = entity_store
        self._ws = ws_adapter
        self._max_entities = max_entities
        self._update_interval = update_interval_s
        self._stale_seconds = stale_seconds
        self._pos_threshold = position_threshold_deg
        self._speed = speed
        self._stop = asyncio.Event()

        # Per-MMSI tracking
        self._last_broadcast: dict[str, float] = {}
        self._last_position: dict[str, tuple[float, float]] = {}
        self._last_seen: dict[str, float] = {}
        self._active_count = 0

        # Statics lookup: mmsi -> {ship_name, ship_type_code, length_m, ...}
        self._statics: dict[str, dict] = {}

        # Counters
        self._position_count = 0
        self._broadcast_count = 0

    @property
    def entity_count(self) -> int:
        return self._active_count

    def stop(self) -> None:
        self._stop.set()

    def _load_statics(self) -> None:
        """Pre-load all static data into a lookup dict."""
        if not self._statics_path.exists():
            logger.warning(f"AIS replay: statics file not found: {self._statics_path}")
            return
        with open(self._statics_path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                mmsi = row.get("mmsi", "").strip()
                if not mmsi:
                    continue
                name = row.get("vessel_name", "").strip() or row.get("ship_name", "").strip()
                ship_type = int(row.get("ship_type_code") or 0)
                length = None
                try:
                    length = float(row["length_m"]) if row.get("length_m") else None
                except (ValueError, TypeError):
                    pass
                beam = None
                try:
                    beam = float(row["beam_m"]) if row.get("beam_m") else None
                except (ValueError, TypeError):
                    pass
                draught = None
                try:
                    draught = float(row["draught_m"]) if row.get("draught_m") else None
                except (ValueError, TypeError):
                    pass
                # Keep the most complete record per MMSI
                existing = self._statics.get(mmsi, {})
                if name:
                    existing["ship_name"] = name
                if ship_type:
                    existing["ship_type_code"] = ship_type
                if length:
                    existing["length_m"] = length
                if beam:
                    existing["beam_m"] = beam
                if draught:
                    existing["draught_m"] = draught
                dest = row.get("destination", "").strip()
                if dest:
                    existing["destination"] = dest
                callsign = row.get("call_sign", "").strip()
                if callsign:
                    existing["call_sign"] = callsign
                imo = row.get("imo_number", "").strip()
                if imo and imo != "0":
                    existing["imo_number"] = imo
                self._statics[mmsi] = existing

        logger.info(f"AIS replay: loaded statics for {len(self._statics)} vessels")

    def _load_positions(self) -> list[tuple[float, dict]]:
        """Load all position rows, sorted by timestamp. Returns [(epoch, row), ...]."""
        rows = []
        with open(self._positions_path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                ts_str = row.get("timestamp_utc", "")
                try:
                    epoch = _parse_ts(ts_str)
                except (ValueError, IndexError):
                    continue
                rows.append((epoch, row))
        rows.sort(key=lambda x: x[0])
        return rows

    def _handle_position(self, row: dict) -> None:
        """Process a single position row — mirrors live_feed._process_position."""
        mmsi = row.get("mmsi", "").strip()
        if not mmsi:
            return

        try:
            lat = float(row["latitude"])
            lon = float(row["longitude"])
        except (ValueError, KeyError, TypeError):
            return
        if abs(lat) < 0.001 and abs(lon) < 0.001:
            return

        sog = float(row.get("sog_knots") or 0)
        cog = float(row.get("cog_degrees") or 0)
        heading = row.get("true_heading", "")
        try:
            heading = float(heading) if heading else cog
            if heading == 511:
                heading = cog
        except (ValueError, TypeError):
            heading = cog

        now = time.monotonic()
        self._last_seen[mmsi] = now
        self._position_count += 1

        # Throttle
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

        entity_id = f"{AIS_ENTITY_PREFIX}{mmsi}"
        existing = self._store.get_entity(entity_id)
        if not existing and self._active_count >= self._max_entities:
            return

        # Enrich from statics
        static = self._statics.get(mmsi, {})
        ship_name = (
            row.get("ship_name", "").strip()
            or static.get("ship_name", "")
            or f"MMSI {mmsi}"
        )
        ship_type = static.get("ship_type_code", 0)
        length = static.get("length_m")
        entity_type = _map_entity_type(ship_type, length)

        if existing:
            existing.update_position(
                latitude=lat, longitude=lon,
                heading_deg=heading, speed_knots=sog, course_deg=cog,
            )
            if ship_name and existing.callsign.startswith("MMSI "):
                existing.callsign = ship_name
                existing.metadata["ship_name"] = ship_name
            self._store.upsert_entity(existing)
            entity = existing
        else:
            metadata = {
                "background": True,
                "source": "AIS_REPLAY",
                "mmsi": mmsi,
                "entity_type_name": entity_type,
            }
            # Add statics to metadata
            for key in ("ship_name", "call_sign", "imo_number", "length_m",
                        "beam_m", "draught_m", "destination"):
                if key in static:
                    metadata[key] = static[key]

            entity = Entity(
                entity_id=entity_id,
                entity_type=entity_type,
                domain=Domain.MARITIME,
                agency=Agency.CIVILIAN,
                callsign=ship_name,
                position=Position(latitude=lat, longitude=lon),
                heading_deg=heading,
                speed_knots=sog,
                course_deg=cog,
                status=EntityStatus.ACTIVE,
                sidc=DEFAULT_SIDC,
                metadata=metadata,
            )
            self._store.upsert_entity(entity)
            self._active_count += 1

        self._last_position[mmsi] = (lat, lon)
        self._last_broadcast[mmsi] = now
        self._broadcast_count += 1
        asyncio.ensure_future(self._ws.push_entity_update(entity))

    async def _cleanup_loop(self) -> None:
        """Remove vessels not seen recently."""
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
                    f"AIS replay cleanup: removed {len(stale)} stale, "
                    f"{self._active_count} active"
                )

    async def run(self) -> None:
        """Replay loop: pace positions by original timestamps, loop forever."""
        self._load_statics()
        positions = self._load_positions()
        if not positions:
            logger.error(f"AIS replay: no positions in {self._positions_path}")
            return

        first_epoch = positions[0][0]
        last_epoch = positions[-1][0]
        duration = last_epoch - first_epoch
        logger.info(
            f"AIS replay: {len(positions)} positions, "
            f"{len(self._statics)} statics, "
            f"duration {duration/60:.0f}min, "
            f"speed {self._speed}x"
        )

        cleanup_task = asyncio.create_task(self._cleanup_loop())
        loop_count = 0

        try:
            while not self._stop.is_set():
                loop_count += 1
                wall_start = time.monotonic()
                data_start = first_epoch

                for i, (epoch, row) in enumerate(positions):
                    if self._stop.is_set():
                        return

                    # Calculate how long to wait (wall-clock) for this position
                    data_elapsed = epoch - data_start
                    wall_target = wall_start + data_elapsed / self._speed
                    wall_now = time.monotonic()
                    delay = wall_target - wall_now

                    if delay > 0.5:
                        # Sleep in small chunks so we can check stop
                        while delay > 0 and not self._stop.is_set():
                            await asyncio.sleep(min(delay, 0.5))
                            delay = wall_target - time.monotonic()
                    elif delay < -5:
                        # Fallen behind by >5s — skip ahead
                        continue

                    self._handle_position(row)

                    # Periodic log
                    if (i + 1) % 2000 == 0:
                        logger.info(
                            f"AIS replay: {i+1}/{len(positions)} positions, "
                            f"{self._active_count} vessels, "
                            f"{self._broadcast_count} broadcasts "
                            f"(loop {loop_count})"
                        )

                logger.info(
                    f"AIS replay loop {loop_count} complete. "
                    f"Restarting from beginning..."
                )
                # Brief pause before looping
                await asyncio.sleep(2)

        finally:
            cleanup_task.cancel()
            try:
                await cleanup_task
            except asyncio.CancelledError:
                pass
            logger.info(
                f"AIS replay stopped. "
                f"Positions: {self._position_count}, "
                f"Broadcasts: {self._broadcast_count}, "
                f"Active: {self._active_count}"
            )
