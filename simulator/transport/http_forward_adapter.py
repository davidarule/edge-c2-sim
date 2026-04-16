"""
HTTP forwarding adapter — fire-and-forget POST of all entity data.

Posts every entity update as JSON to a target URL. No spec required,
no field mapping — just raw entity dicts. Batches updates for efficiency.
"""

import asyncio
import logging
import time
from typing import Optional

from simulator.core.entity import Entity
from simulator.transport.base import TransportAdapter

logger = logging.getLogger(__name__)

try:
    import aiohttp
except ImportError:
    aiohttp = None  # type: ignore[assignment]


class HttpForwardAdapter(TransportAdapter):
    """Forward all entity data to an HTTP endpoint via POST."""

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
        self._buffer: list[dict] = []
        self._flush_task: Optional[asyncio.Task] = None
        self._stats = {"sent": 0, "errors": 0}

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
        # Final flush
        await self._flush_now()
        if self._session:
            await self._session.close()
        logger.info(
            f"HTTP forward adapter stopped "
            f"(sent={self._stats['sent']}, errors={self._stats['errors']})"
        )

    async def push_entity_update(self, entity: Entity) -> None:
        self._buffer.append(entity.to_dict())

    async def push_bulk_update(self, entities: list[Entity]) -> None:
        self._buffer.extend(e.to_dict() for e in entities)

    async def push_event(self, event: dict) -> None:
        payload = {"type": "event", **event}
        self._buffer.append(payload)

    async def _flush_loop(self) -> None:
        while True:
            await asyncio.sleep(self._batch_interval_s)
            await self._flush_now()

    async def _flush_now(self) -> None:
        if not self._buffer or not self._session:
            return
        batch = self._buffer.copy()
        self._buffer.clear()
        try:
            async with self._session.post(
                self._target_url,
                json={"entities": batch, "count": len(batch), "timestamp": time.time()},
            ) as resp:
                if resp.status < 400:
                    self._stats["sent"] += len(batch)
                else:
                    self._stats["errors"] += 1
                    if self._stats["errors"] <= 5:
                        body = await resp.text()
                        logger.warning(
                            f"Forward POST {resp.status}: {body[:200]}"
                        )
        except Exception as e:
            self._stats["errors"] += 1
            if self._stats["errors"] <= 5:
                logger.warning(f"Forward POST error: {e}")
