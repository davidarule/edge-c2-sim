"""
HTTP forwarding adapter — POST entity data and inter-agency messages.

Entity updates go to {target_url}/entities as batched JSON.
Scenario events go to {target_url}/events as inter-agency messages,
formatted per the Edge C2 API Event schema.
"""

import asyncio
import logging
import time
import uuid
from typing import Optional

from simulator.core.entity import Entity
from simulator.transport.base import TransportAdapter

logger = logging.getLogger(__name__)

try:
    import aiohttp
except ImportError:
    aiohttp = None  # type: ignore[assignment]


class HttpForwardAdapter(TransportAdapter):
    """Forward entity data and inter-agency messages to Edge C2 via HTTP."""

    def __init__(
        self,
        target_url: str,
        batch_interval_s: float = 1.0,
        timeout_s: float = 5.0,
    ):
        self._target_url = target_url.rstrip("/")
        self._batch_interval_s = batch_interval_s
        self._timeout_s = timeout_s
        self._session: Optional[aiohttp.ClientSession] = None
        self._entity_buffer: list[dict] = []
        self._event_buffer: list[dict] = []
        self._flush_task: Optional[asyncio.Task] = None
        self._stats = {"entities_sent": 0, "events_sent": 0, "errors": 0}

    @property
    def name(self) -> str:
        return "http_forward"

    async def connect(self) -> None:
        if aiohttp is None:
            raise RuntimeError("aiohttp required for HTTP forward adapter")
        timeout = aiohttp.ClientTimeout(total=self._timeout_s)
        self._session = aiohttp.ClientSession(
            headers={"Content-Type": "application/json"},
            timeout=timeout,
        )
        self._flush_task = asyncio.create_task(self._flush_loop())
        logger.info(f"HTTP forward adapter -> {self._target_url}")

    async def disconnect(self) -> None:
        if self._flush_task:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass
        await self._flush_now()
        if self._session:
            await self._session.close()
        logger.info(
            f"HTTP forward adapter stopped "
            f"(entities={self._stats['entities_sent']}, "
            f"events={self._stats['events_sent']}, "
            f"errors={self._stats['errors']})"
        )

    async def push_entity_update(self, entity: Entity) -> None:
        self._entity_buffer.append(entity.to_dict())

    async def push_bulk_update(self, entities: list[Entity]) -> None:
        self._entity_buffer.extend(e.to_dict() for e in entities)

    async def push_event(self, event: dict) -> None:
        self._event_buffer.append(self._format_interagency_message(event))

    def _format_interagency_message(self, event: dict) -> dict:
        """Format a scenario event as an Edge C2 inter-agency message.

        Determines the originating agency from the event source entity
        or defaults based on event type. Recipients are all alerted agencies.
        """
        # Determine originating agency
        source_agency = None
        if event.get("source"):
            # Infer agency from source entity ID prefix
            source_id = event["source"]
            for prefix, agency in [
                ("MMEA", "MMEA"), ("RMN", "MIL"), ("RMAF", "RMAF"),
                ("RMP", "RMP"), ("CI", "CI"), ("MIL", "MIL"),
            ]:
                if source_id.startswith(prefix):
                    source_agency = agency
                    break
        if not source_agency:
            # Default based on event type
            source_agency = {
                "BOARDING": "RMP",
                "INTERCEPT": "MIL",
                "DETECTION": "MMEA",
            }.get(event.get("event_type", ""), "MMEA")

        # Recipients: all alerted agencies minus the sender
        alert_agencies = event.get("alert_agencies") or []
        recipients = [a for a in alert_agencies if a != source_agency]
        if not recipients:
            # Default: broadcast to all agencies
            recipients = ["RMP", "MMEA", "RMAF", "MIL", "CI"]
            recipients = [a for a in recipients if a != source_agency]

        return {
            "event_id": str(uuid.uuid4()),
            "event_type": event.get("event_type", "ALERT"),
            "description": event.get("description", ""),
            "timestamp": event.get("time", ""),
            "severity": event.get("severity", "INFO"),
            "source_agency": source_agency,
            "source_entity_id": event.get("source") or event.get("actionee"),
            "target_entity_id": event.get("target") or event.get("actionee"),
            "recipient_agencies": recipients,
            "agencies_involved": alert_agencies or [source_agency],
            "position": event.get("position"),
            "action": event.get("action"),
            "metadata": {
                k: v for k, v in event.items()
                if k not in (
                    "type", "event_type", "description", "time",
                    "severity", "source", "actionee", "targets", "target",
                    "alert_agencies", "position", "action",
                    "time_offset_s", "destination", "area",
                )
                and v is not None
            },
        }

    async def _flush_loop(self) -> None:
        flush_count = 0
        while True:
            await asyncio.sleep(self._batch_interval_s)
            await self._flush_now()
            flush_count += 1
            if flush_count % 30 == 0:
                logger.info(
                    f"Forward stats: entities={self._stats['entities_sent']}, "
                    f"events={self._stats['events_sent']}, "
                    f"errors={self._stats['errors']} -> {self._target_url}"
                )

    async def _flush_now(self) -> None:
        if not self._session:
            return

        # Flush entities
        if self._entity_buffer:
            entities = self._entity_buffer.copy()
            self._entity_buffer.clear()
            await self._post(
                f"{self._target_url}/entities",
                {"entities": entities, "count": len(entities), "timestamp": time.time()},
                "entities",
                len(entities),
            )

        # Flush events as inter-agency messages
        if self._event_buffer:
            events = self._event_buffer.copy()
            self._event_buffer.clear()
            for event_msg in events:
                await self._post(
                    f"{self._target_url}/events",
                    event_msg,
                    "events",
                    1,
                )

    async def _post(self, url: str, payload: dict, stat_key: str, count: int) -> None:
        try:
            async with self._session.post(url, json=payload) as resp:
                if resp.status < 400:
                    self._stats[f"{stat_key}_sent"] += count
                else:
                    self._stats["errors"] += 1
                    if self._stats["errors"] <= 5:
                        body = await resp.text()
                        logger.warning(f"Forward POST {url} {resp.status}: {body[:200]}")
        except Exception as e:
            self._stats["errors"] += 1
            if self._stats["errors"] <= 5:
                logger.warning(f"Forward POST {url} error: {e}")
