"""
Abstract base class for transport adapters.

Each adapter implements the same interface. The simulator core pushes
entity updates through all registered adapters. Adapters handle the
protocol-specific serialization and delivery.
"""

from abc import ABC, abstractmethod

from simulator.core.entity import Entity


class TransportAdapter(ABC):
    """Abstract transport adapter interface."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable adapter name."""
        ...

    @abstractmethod
    async def connect(self) -> None:
        """Establish connection / start server."""
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        """Close connection / stop server."""
        ...

    @abstractmethod
    async def push_entity_update(self, entity: Entity) -> None:
        """Send a single entity update."""
        ...

    @abstractmethod
    async def push_event(self, event: dict) -> None:
        """Send an operational event."""
        ...

    @abstractmethod
    async def push_bulk_update(self, entities: list[Entity]) -> None:
        """Send multiple entity updates at once."""
        ...
