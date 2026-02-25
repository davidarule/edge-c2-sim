"""
Thread-safe in-memory entity state store.

Central registry of all simulated entities. Transport adapters subscribe
to update callbacks to receive entity changes in real-time.
"""

import threading
from typing import Callable

from simulator.core.entity import Agency, Domain, Entity


class EntityStore:
    """
    In-memory store for all simulated entities.

    Thread-safe via threading.Lock. Supports listener callbacks
    for entity updates and operational events.
    """

    def __init__(self) -> None:
        self._entities: dict[str, Entity] = {}
        self._lock = threading.Lock()
        self._update_callbacks: list[Callable[[Entity], None]] = []
        self._event_callbacks: list[Callable[[dict], None]] = []

    def add_entity(self, entity: Entity) -> None:
        """Add a new entity. Raises ValueError if entity_id already exists."""
        with self._lock:
            if entity.entity_id in self._entities:
                raise ValueError(f"Entity {entity.entity_id} already exists")
            self._entities[entity.entity_id] = entity
        self._notify_update(entity)

    def update_entity(self, entity: Entity) -> None:
        """Update an existing entity. Raises KeyError if not found."""
        with self._lock:
            if entity.entity_id not in self._entities:
                raise KeyError(f"Entity {entity.entity_id} not found")
            self._entities[entity.entity_id] = entity
        self._notify_update(entity)

    def upsert_entity(self, entity: Entity) -> None:
        """Add or update an entity."""
        with self._lock:
            self._entities[entity.entity_id] = entity
        self._notify_update(entity)

    def get_entity(self, entity_id: str) -> Entity | None:
        """Get entity by ID, or None if not found."""
        with self._lock:
            return self._entities.get(entity_id)

    def get_all_entities(self) -> list[Entity]:
        """Get all entities."""
        with self._lock:
            return list(self._entities.values())

    def get_entities_by_agency(self, agency: Agency) -> list[Entity]:
        """Get all entities belonging to an agency."""
        with self._lock:
            return [e for e in self._entities.values() if e.agency == agency]

    def get_entities_by_domain(self, domain: Domain) -> list[Entity]:
        """Get all entities in a domain."""
        with self._lock:
            return [e for e in self._entities.values() if e.domain == domain]

    def remove_entity(self, entity_id: str) -> None:
        """Remove an entity by ID. Raises KeyError if not found."""
        with self._lock:
            if entity_id not in self._entities:
                raise KeyError(f"Entity {entity_id} not found")
            del self._entities[entity_id]

    def on_update(self, callback: Callable[[Entity], None]) -> None:
        """Register a listener for entity updates."""
        self._update_callbacks.append(callback)

    def on_event(self, callback: Callable[[dict], None]) -> None:
        """Register a listener for operational events."""
        self._event_callbacks.append(callback)

    def emit_event(self, event: dict) -> None:
        """Push an operational event to all event listeners."""
        for cb in self._event_callbacks:
            cb(event)

    def _notify_update(self, entity: Entity) -> None:
        """Notify all update listeners of an entity change."""
        for cb in self._update_callbacks:
            cb(entity)

    @property
    def count(self) -> int:
        """Number of entities in the store."""
        with self._lock:
            return len(self._entities)
