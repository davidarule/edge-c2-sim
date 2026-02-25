"""Tests for the EntityStore."""

import pytest

from simulator.core.entity import Agency, Domain, Entity, EntityStatus, Position
from simulator.core.entity_store import EntityStore


def _make_entity(entity_id: str = "TEST-001", **kwargs) -> Entity:
    defaults = {
        "entity_id": entity_id,
        "entity_type": "MMEA_PATROL",
        "domain": Domain.MARITIME,
        "agency": Agency.MMEA,
        "callsign": f"Test {entity_id}",
        "position": Position(latitude=2.5, longitude=102.0),
    }
    defaults.update(kwargs)
    return Entity(**defaults)


class TestEntityStore:
    def test_add_and_get(self):
        store = EntityStore()
        entity = _make_entity()
        store.add_entity(entity)
        assert store.get_entity("TEST-001") is entity

    def test_add_duplicate_raises(self):
        store = EntityStore()
        store.add_entity(_make_entity())
        with pytest.raises(ValueError, match="already exists"):
            store.add_entity(_make_entity())

    def test_update(self):
        store = EntityStore()
        entity = _make_entity()
        store.add_entity(entity)
        entity.speed_knots = 20.0
        store.update_entity(entity)
        assert store.get_entity("TEST-001").speed_knots == 20.0

    def test_update_nonexistent_raises(self):
        store = EntityStore()
        with pytest.raises(KeyError, match="not found"):
            store.update_entity(_make_entity())

    def test_upsert_create(self):
        store = EntityStore()
        store.upsert_entity(_make_entity())
        assert store.get_entity("TEST-001") is not None

    def test_upsert_update(self):
        store = EntityStore()
        store.upsert_entity(_make_entity(speed_knots=10.0))
        store.upsert_entity(_make_entity(speed_knots=20.0))
        assert store.get_entity("TEST-001").speed_knots == 20.0
        assert store.count == 1

    def test_get_nonexistent(self):
        store = EntityStore()
        assert store.get_entity("NOPE") is None

    def test_get_all(self):
        store = EntityStore()
        store.add_entity(_make_entity("A"))
        store.add_entity(_make_entity("B"))
        store.add_entity(_make_entity("C"))
        assert len(store.get_all_entities()) == 3

    def test_filter_by_agency(self):
        store = EntityStore()
        store.add_entity(_make_entity("A", agency=Agency.MMEA))
        store.add_entity(_make_entity("B", agency=Agency.RMP))
        store.add_entity(_make_entity("C", agency=Agency.MMEA))
        mmea = store.get_entities_by_agency(Agency.MMEA)
        assert len(mmea) == 2
        assert all(e.agency == Agency.MMEA for e in mmea)

    def test_filter_by_domain(self):
        store = EntityStore()
        store.add_entity(_make_entity("A", domain=Domain.MARITIME))
        store.add_entity(_make_entity("B", domain=Domain.AIR))
        store.add_entity(_make_entity("C", domain=Domain.MARITIME))
        maritime = store.get_entities_by_domain(Domain.MARITIME)
        assert len(maritime) == 2

    def test_remove(self):
        store = EntityStore()
        store.add_entity(_make_entity())
        store.remove_entity("TEST-001")
        assert store.get_entity("TEST-001") is None
        assert store.count == 0

    def test_remove_nonexistent_raises(self):
        store = EntityStore()
        with pytest.raises(KeyError, match="not found"):
            store.remove_entity("NOPE")

    def test_on_update_callback(self):
        store = EntityStore()
        received = []
        store.on_update(lambda e: received.append(e))
        entity = _make_entity()
        store.add_entity(entity)
        assert len(received) == 1
        assert received[0] is entity

    def test_update_triggers_callback(self):
        store = EntityStore()
        received = []
        store.on_update(lambda e: received.append(e))
        entity = _make_entity()
        store.add_entity(entity)
        entity.speed_knots = 25.0
        store.update_entity(entity)
        assert len(received) == 2

    def test_multiple_callbacks(self):
        store = EntityStore()
        a, b = [], []
        store.on_update(lambda e: a.append(e))
        store.on_update(lambda e: b.append(e))
        store.add_entity(_make_entity())
        assert len(a) == 1
        assert len(b) == 1

    def test_event_callback(self):
        store = EntityStore()
        events = []
        store.on_event(lambda e: events.append(e))
        store.emit_event({"type": "ALERT", "description": "Test alert"})
        assert len(events) == 1
        assert events[0]["type"] == "ALERT"

    def test_count(self):
        store = EntityStore()
        assert store.count == 0
        store.add_entity(_make_entity("A"))
        assert store.count == 1
        store.add_entity(_make_entity("B"))
        assert store.count == 2
        store.remove_entity("A")
        assert store.count == 1
