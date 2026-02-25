"""
Cursor on Target (CoT) transport adapter.

Generates CoT XML messages and sends them via TCP to a TAK server
(FreeTAKServer or TAK Server). Allows ATAK/WinTAK clients to display
simulated entities alongside real operational data.

CoT is the standard messaging protocol for tactical awareness in the
TAK ecosystem used by US/NATO/partner militaries.
"""

import asyncio
import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from typing import Optional

from simulator.core.entity import Entity
from simulator.transport.base import TransportAdapter

logger = logging.getLogger(__name__)

# Entity type → CoT type mapping
COT_TYPE_MAP = {
    # Friendly maritime
    "MMEA_PATROL":          "a-f-S-X-N",
    "MMEA_FAST_INTERCEPT":  "a-f-S-X-N",
    "MIL_NAVAL":            "a-f-S-C",
    # Hostile maritime
    "SUSPECT_VESSEL":       "a-h-S-X",
    # Neutral maritime
    "CIVILIAN_CARGO":       "a-n-S-C-M",
    "CIVILIAN_FISHING":     "a-n-S-C-F",
    "CIVILIAN_TANKER":      "a-n-S-C-M",
    "CIVILIAN_PASSENGER":   "a-n-S-C-M",
    # Friendly air
    "RMAF_FIGHTER":         "a-f-A-M-F",
    "RMAF_HELICOPTER":      "a-f-A-M-H",
    "RMAF_TRANSPORT":       "a-f-A-M-C",
    "RMP_HELICOPTER":       "a-f-A-C-H",
    # Neutral air
    "CIVILIAN_COMMERCIAL":  "a-n-A-C",
    "CIVILIAN_LIGHT":       "a-n-A-C",
    # Friendly ground
    "RMP_PATROL_CAR":       "a-f-G-E-V-C-P",
    "RMP_TACTICAL_TEAM":    "a-f-G-U-C-I",
    "MIL_APC":              "a-f-G-E-V-A",
    "MIL_INFANTRY_SQUAD":   "a-f-G-U-C-I",
    # Friendly ground (CI)
    "CI_OFFICER":           "a-f-G-U-C-I",
    "CI_IMMIGRATION_TEAM":  "a-f-G-U-C-I",
}

KNOTS_TO_MS = 0.514444


class CoTAdapter(TransportAdapter):
    """
    Cursor on Target XML adapter for TAK ecosystem.

    Sends CoT XML events via TCP to a TAK server (FreeTAKServer default port 8087).
    """

    def __init__(
        self,
        tak_host: str = "localhost",
        tak_port: int = 8087,
        stale_seconds: int = 30,
        enabled: bool = False,
    ):
        self._host = tak_host
        self._port = tak_port
        self._stale_seconds = stale_seconds
        self._enabled = enabled
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._connected = False

    @property
    def name(self) -> str:
        return "cot"

    async def connect(self) -> None:
        """Open TCP connection to TAK server."""
        if not self._enabled:
            logger.info("CoT adapter disabled")
            return
        try:
            self._reader, self._writer = await asyncio.open_connection(
                self._host, self._port
            )
            self._connected = True
            logger.info(f"CoT adapter connected to {self._host}:{self._port}")
        except Exception as e:
            logger.warning(f"CoT connection failed: {e}")
            self._connected = False

    async def disconnect(self) -> None:
        """Close TCP connection."""
        if self._writer:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except Exception:
                pass
        self._connected = False
        logger.info("CoT adapter disconnected")

    async def push_entity_update(self, entity: Entity) -> None:
        """Convert entity to CoT XML and send."""
        if not self._enabled:
            return
        cot_xml = self.entity_to_cot(entity.to_dict())
        await self._send(cot_xml)

    async def push_event(self, event: dict) -> None:
        """Convert scenario event to CoT GeoChat alert."""
        if not self._enabled:
            return
        cot_xml = self.event_to_cot(event)
        await self._send(cot_xml)

    async def push_bulk_update(self, entities: list[Entity]) -> None:
        """Send CoT for each entity."""
        if not self._enabled:
            return
        for entity in entities:
            await self.push_entity_update(entity)

    # === CoT GENERATION ===

    def entity_to_cot(self, entity: dict) -> str:
        """Generate CoT XML event for an entity."""
        pos = entity.get("position", {})
        now = entity.get("timestamp", datetime.now(timezone.utc).isoformat())
        stale = self._stale_time(now)

        cot_type = self._entity_type_to_cot_type(entity)

        event = ET.Element("event")
        event.set("version", "2.0")
        event.set("uid", entity.get("entity_id", "unknown"))
        event.set("type", cot_type)
        event.set("time", self._format_cot_time(now))
        event.set("start", self._format_cot_time(now))
        event.set("stale", stale)
        event.set("how", "m-g")

        # Point
        point = ET.SubElement(event, "point")
        point.set("lat", str(pos.get("latitude", 0)))
        point.set("lon", str(pos.get("longitude", 0)))
        point.set("hae", str(pos.get("altitude_m", 0)))
        point.set("ce", "15.0")
        point.set("le", "15.0")

        # Detail
        detail = ET.SubElement(event, "detail")

        contact = ET.SubElement(detail, "contact")
        contact.set("callsign", entity.get("callsign", entity.get("entity_id", "")))

        track = ET.SubElement(detail, "track")
        speed_ms = (entity.get("speed_knots", 0) or 0) * KNOTS_TO_MS
        track.set("speed", f"{speed_ms:.2f}")
        track.set("course", str(entity.get("heading_deg", 0)))

        agency = entity.get("agency", "UNKNOWN")
        entity_type = entity.get("entity_type", "")
        status = entity.get("status", "ACTIVE")
        remarks = ET.SubElement(detail, "remarks")
        remarks.text = f"{agency}: {entity_type} — {status} | Speed: {entity.get('speed_knots', 0):.1f} kts"

        group = ET.SubElement(detail, "__group")
        group.set("name", agency)
        group.set("role", "Team Lead")

        status_el = ET.SubElement(detail, "status")
        status_el.set("readiness", "true")

        uid_el = ET.SubElement(detail, "uid")
        uid_el.set("Droid", entity.get("callsign", entity.get("entity_id", "")))

        precision = ET.SubElement(detail, "precisionlocation")
        precision.set("altsrc", "GPS")
        precision.set("geopointsrc", "GPS")

        return '<?xml version="1.0" encoding="UTF-8"?>' + ET.tostring(event, encoding="unicode")

    def event_to_cot(self, event: dict) -> str:
        """Convert scenario event to CoT GeoChat message."""
        now = event.get("time", event.get("timestamp", datetime.now(timezone.utc).isoformat()))
        stale = self._stale_time(now, seconds=300)
        event_id = event.get("event_id", f"event-{hash(event.get('description', ''))}")

        pos = event.get("position", {})
        lat = pos.get("latitude", 0)
        lon = pos.get("longitude", 0)

        cot_event = ET.Element("event")
        cot_event.set("version", "2.0")
        cot_event.set("uid", event_id)
        cot_event.set("type", "b-t-f")
        cot_event.set("time", self._format_cot_time(now))
        cot_event.set("start", self._format_cot_time(now))
        cot_event.set("stale", stale)

        point = ET.SubElement(cot_event, "point")
        point.set("lat", str(lat))
        point.set("lon", str(lon))
        point.set("hae", "0")
        point.set("ce", "999999")
        point.set("le", "999999")

        detail = ET.SubElement(cot_event, "detail")

        chat = ET.SubElement(detail, "__chat")
        chat.set("chatroom", "ESSCOM")
        chat.set("groupOwner", "ESSCOM")
        chatgrp = ET.SubElement(chat, "chatgrp")
        chatgrp.set("uid0", "simulator")
        chatgrp.set("uid1", "ESSCOM")

        remarks = ET.SubElement(detail, "remarks")
        remarks.set("source", "ESSCOM")
        remarks.text = event.get("description", "")

        link = ET.SubElement(detail, "link")
        link.set("uid", event_id)
        link.set("type", "a-f-G")
        link.set("relation", "p-p")

        return '<?xml version="1.0" encoding="UTF-8"?>' + ET.tostring(cot_event, encoding="unicode")

    def _entity_type_to_cot_type(self, entity: dict) -> str:
        """Map entity type + affiliation to CoT type string."""
        entity_type = entity.get("entity_type", "")
        return COT_TYPE_MAP.get(entity_type, "a-u-G")  # Default: unknown ground

    def _stale_time(self, timestamp: str, seconds: Optional[int] = None) -> str:
        """Calculate stale time as timestamp + stale_seconds."""
        stale_s = seconds or self._stale_seconds
        try:
            dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            dt = datetime.now(timezone.utc)
        stale_dt = dt + timedelta(seconds=stale_s)
        return stale_dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")

    def _format_cot_time(self, timestamp: str) -> str:
        """Format timestamp for CoT (ISO 8601 with milliseconds)."""
        try:
            dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            return dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")
        except (ValueError, AttributeError):
            return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")

    # === TCP ===

    async def _send(self, xml_str: str) -> None:
        """Send XML string via TCP."""
        if not self._connected or not self._writer:
            await self._reconnect()
            if not self._connected:
                return

        try:
            self._writer.write(xml_str.encode("utf-8"))
            await self._writer.drain()
        except Exception as e:
            logger.warning(f"CoT send error: {e}")
            self._connected = False
            await self._reconnect()

    async def _reconnect(self) -> None:
        """Attempt to reconnect to TAK server."""
        try:
            self._reader, self._writer = await asyncio.open_connection(
                self._host, self._port
            )
            self._connected = True
            logger.info(f"CoT reconnected to {self._host}:{self._port}")
        except Exception as e:
            logger.debug(f"CoT reconnect failed: {e}")
            self._connected = False
