"""
Debug transport adapter that prints entity updates to stdout.

Useful for development and testing without any external services.
Rate-limited to avoid flooding the console.
"""

import time

from simulator.core.entity import Entity
from simulator.transport.base import TransportAdapter


class ConsoleAdapter(TransportAdapter):
    """Prints entity updates and events to the console."""

    def __init__(self, min_interval: float = 5.0) -> None:
        """
        Args:
            min_interval: Minimum seconds between prints for the same entity.
        """
        self._min_interval = min_interval
        self._last_print: dict[str, float] = {}

    @property
    def name(self) -> str:
        return "console"

    async def connect(self) -> None:
        print("[CONSOLE] Transport adapter connected")

    async def disconnect(self) -> None:
        print("[CONSOLE] Transport adapter disconnected")

    async def push_entity_update(self, entity: Entity) -> None:
        """Print entity update if enough time has passed since last print for this entity."""
        now = time.monotonic()
        last = self._last_print.get(entity.entity_id, 0)
        if now - last < self._min_interval:
            return
        self._last_print[entity.entity_id] = now
        pos = entity.position
        print(
            f"[{entity.timestamp.strftime('%H:%M:%S')}] "
            f"[{entity.agency.value:>8}] "
            f"{entity.callsign:<20} "
            f"@ ({pos.latitude:8.4f}, {pos.longitude:9.4f}) "
            f"HDG {entity.heading_deg:5.1f}° "
            f"SPD {entity.speed_knots:5.1f}kn "
            f"{entity.status.value}"
        )

    async def push_event(self, event: dict) -> None:
        """Print operational event."""
        time_str = event.get("time", "??:??")
        desc = event.get("description", "Unknown event")
        event_type = event.get("event_type", event.get("type", "EVENT"))
        print(f"[{time_str}] {event_type}: {desc}")

    async def push_bulk_update(self, entities: list[Entity]) -> None:
        """Print each entity update (rate limiting still applies per entity)."""
        for entity in entities:
            await self.push_entity_update(entity)
