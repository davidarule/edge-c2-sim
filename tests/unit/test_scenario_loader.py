"""Tests for scenario loader."""

from datetime import datetime, timedelta, timezone

import pytest

from simulator.scenario.loader import ScenarioLoader, ENTITY_TYPES


@pytest.fixture
def loader():
    return ScenarioLoader(geodata_path="geodata/")


@pytest.fixture
def start_time():
    return datetime(2026, 4, 15, 8, 0, 0, tzinfo=timezone.utc)


class TestScenarioLoader:
    def test_load_fishing_scenario(self, loader, start_time):
        """Load the IUU fishing intercept scenario successfully."""
        state = loader.load(
            "config/scenarios/sulu_sea_fishing_intercept.yaml",
            start_time=start_time,
        )
        assert state.name == "Illegal Fishing Fleet Intercept — Sulu Sea"
        assert state.duration == timedelta(minutes=50)
        assert state.center == (5.5, 118.5)
        assert len(state.entities) > 0
        assert len(state.events) > 0

    def test_scenario_entities_created(self, loader, start_time):
        """All scenario entities should be created with valid IDs."""
        state = loader.load(
            "config/scenarios/sulu_sea_fishing_intercept.yaml",
            start_time=start_time,
        )
        # Check specific entities exist
        assert "IFF-001" in state.entities
        assert "MMEA-PV-101" in state.entities
        assert "RMN-FIC-101" in state.entities
        assert "RMAF-MPA-101" in state.entities

    def test_entity_positions_valid(self, loader, start_time):
        """All entity positions should be in reasonable ESSZONE range."""
        state = loader.load(
            "config/scenarios/sulu_sea_fishing_intercept.yaml",
            start_time=start_time,
        )
        for eid, entity in state.entities.items():
            if entity.metadata.get("background"):
                continue  # Background may be auto-generated
            assert 3.5 < entity.position.latitude < 8.0, \
                f"{eid} lat out of range: {entity.position.latitude}"
            assert 115 < entity.position.longitude < 120, \
                f"{eid} lon out of range: {entity.position.longitude}"

    def test_background_entities_generated(self, loader, start_time):
        """Background entities should be generated."""
        state = loader.load(
            "config/scenarios/sulu_sea_fishing_intercept.yaml",
            start_time=start_time,
        )
        bg_entities = [
            e for e in state.entities.values()
            if e.metadata.get("background")
        ]
        # Scenario has 12 fishing + 5 cargo + 3 tanker + 2 light = 22 background
        assert len(bg_entities) >= 10

    def test_events_sorted(self, loader, start_time):
        """Events should be in chronological order."""
        state = loader.load(
            "config/scenarios/sulu_sea_fishing_intercept.yaml",
            start_time=start_time,
        )
        for i in range(1, len(state.events)):
            assert state.events[i].time_offset >= state.events[i-1].time_offset

    def test_movements_assigned(self, loader, start_time):
        """Entities with waypoints/patrol should have movement strategies."""
        state = loader.load(
            "config/scenarios/sulu_sea_fishing_intercept.yaml",
            start_time=start_time,
        )
        # IFF-001 has waypoints
        assert "IFF-001" in state.movements
        # MMEA-PV-101 has patrol behavior
        assert "MMEA-PV-101" in state.movements

    def test_standby_entities_no_movement(self, loader, start_time):
        """Standby entities should have no movement."""
        state = loader.load(
            "config/scenarios/sulu_sea_fishing_intercept.yaml",
            start_time=start_time,
        )
        # MMEA-FI-101 is standby
        assert "MMEA-FI-101" not in state.movements

    def test_validate_valid_scenario(self, loader):
        """Valid scenario should return no critical errors (missing routes are warnings)."""
        errors = loader.validate(
            "config/scenarios/sulu_sea_fishing_intercept.yaml"
        )
        # Filter out missing route warnings — routes not yet in geodata
        critical = [e for e in errors if "route" not in e.lower()]
        assert len(critical) == 0, f"Unexpected critical errors: {critical}"

    def test_validate_missing_file(self, loader):
        """Missing file should return error."""
        errors = loader.validate("nonexistent.yaml")
        assert len(errors) == 1
        assert "not found" in errors[0].lower()

    def test_geodata_loaded(self, loader):
        """Geodata zones and routes should be loaded."""
        assert "esszone_sector_2_sandakan" in loader.zones
        # At least one route should be loaded (sibutu_passage exists)
        assert len(loader.routes) >= 1

    def test_event_parsing(self, loader, start_time):
        """Events should have correct fields parsed."""
        state = loader.load(
            "config/scenarios/sulu_sea_fishing_intercept.yaml",
            start_time=start_time,
        )
        first_event = state.events[0]
        assert first_event.event_type == "DETECTION"
        assert first_event.time_offset == timedelta(0)
        assert "MMEA" in first_event.alert_agencies

        # Find an ORDER event with intercept
        order_events = [e for e in state.events if e.action == "intercept"]
        assert len(order_events) > 0
        assert order_events[0].intercept_target is not None
