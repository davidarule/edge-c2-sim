"""
Transport registry — manages all active transport adapters.

Supports multiple simultaneous transports (e.g., WebSocket + REST + CoT).
Each transport implements the same TransportAdapter interface.
"""

import logging
from typing import Any

from simulator.core.entity import Entity
from simulator.transport.base import TransportAdapter

logger = logging.getLogger(__name__)


class TransportRegistry:
    """Manages multiple transport adapters, fans out updates to all."""

    def __init__(self):
        self._transports: list[TransportAdapter] = []

    def register(self, adapter: TransportAdapter) -> None:
        """Add a transport adapter to the registry."""
        self._transports.append(adapter)
        logger.info(f"Registered transport: {adapter.name}")

    async def connect_all(self) -> None:
        """Connect all registered transports."""
        for t in self._transports:
            try:
                await t.connect()
            except Exception as e:
                logger.warning(f"Transport {t.name} connect failed: {e}")

    async def disconnect_all(self) -> None:
        """Disconnect all registered transports."""
        for t in self._transports:
            try:
                await t.disconnect()
            except Exception as e:
                logger.warning(f"Transport {t.name} disconnect failed: {e}")

    async def push_entity_update(self, entity: Entity) -> None:
        """Push entity update to all transports."""
        for t in self._transports:
            try:
                await t.push_entity_update(entity)
            except Exception as e:
                logger.warning(f"Transport {t.name} entity update failed: {e}")

    async def push_bulk_update(self, entities: list[Entity]) -> None:
        """Push bulk entity update to all transports."""
        for t in self._transports:
            try:
                await t.push_bulk_update(entities)
            except Exception as e:
                logger.warning(f"Transport {t.name} bulk update failed: {e}")

    async def push_event(self, event: dict) -> None:
        """Push event to all transports."""
        for t in self._transports:
            try:
                await t.push_event(event)
            except Exception as e:
                logger.warning(f"Transport {t.name} event push failed: {e}")

    @property
    def transport_names(self) -> list[str]:
        """List of registered transport names."""
        return [t.name for t in self._transports]

    @property
    def count(self) -> int:
        return len(self._transports)
