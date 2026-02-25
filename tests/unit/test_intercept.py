"""Tests for intercept movement."""

from datetime import datetime, timedelta, timezone

import pytest

from simulator.core.entity import Agency, Domain, Entity, EntityStatus, Position
from simulator.core.entity_store import EntityStore
from simulator.movement.intercept import InterceptMovement


@pytest.fixture
def store():
    return EntityStore()


@pytest.fixture
def scenario_start():
    return datetime(2026, 4, 15, 8, 0, 0, tzinfo=timezone.utc)


def _make_entity(entity_id, lat, lon, speed=0, course=0):
    return Entity(
        entity_id=entity_id,
        entity_type="TEST",
        domain=Domain.MARITIME,
        agency=Agency.CIVILIAN,
        callsign=entity_id,
        position=Position(lat, lon),
        speed_knots=speed,
        course_deg=course,
    )


class TestInterceptMovement:
    def test_converge_on_stationary_target(self, store, scenario_start):
        """Pursuer should head toward a stationary target."""
        target = _make_entity("target", 6.0, 119.0)
        pursuer = _make_entity("pursuer", 5.0, 118.0)
        store.add_entity(target)
        store.add_entity(pursuer)

        im = InterceptMovement(
            entity_speed_knots=20,
            target_entity_id="target",
            entity_store=store,
            pursuer_entity_id="pursuer",
        )

        state = im.get_state(scenario_start)
        assert state.speed_knots == 20
        # Heading should be roughly NE toward target
        assert 20 < state.heading_deg < 70

    def test_converge_on_moving_target(self, store, scenario_start):
        """With lead pursuit, heading should lead the target."""
        target = _make_entity("target", 5.5, 119.0, speed=10, course=90)
        pursuer = _make_entity("pursuer", 5.0, 118.0)
        store.add_entity(target)
        store.add_entity(pursuer)

        im = InterceptMovement(
            entity_speed_knots=25,
            target_entity_id="target",
            entity_store=store,
            pursuer_entity_id="pursuer",
            lead_pursuit=True,
        )

        state = im.get_state(scenario_start)
        # Should aim ahead of direct bearing to target
        direct_bearing_approx = 70  # rough NE bearing
        assert state.heading_deg != 0
        assert state.speed_knots == 25

    def test_intercept_detected_within_radius(self, store, scenario_start):
        """Intercept detected when pursuer within radius of target."""
        target = _make_entity("target", 5.001, 118.001)
        pursuer = _make_entity("pursuer", 5.0, 118.0)
        store.add_entity(target)
        store.add_entity(pursuer)

        im = InterceptMovement(
            entity_speed_knots=20,
            target_entity_id="target",
            entity_store=store,
            intercept_radius_m=500,
            pursuer_entity_id="pursuer",
        )

        state = im.get_state(scenario_start)
        assert im.is_intercepted()
        assert state.speed_knots == 0

    def test_target_removed_holds_position(self, store, scenario_start):
        """If target removed, pursuer holds position."""
        pursuer = _make_entity("pursuer", 5.0, 118.0)
        store.add_entity(pursuer)

        im = InterceptMovement(
            entity_speed_knots=20,
            target_entity_id="nonexistent",
            entity_store=store,
            pursuer_entity_id="pursuer",
        )

        state = im.get_state(scenario_start)
        assert state.speed_knots == 0

    def test_heading_updates_each_tick(self, store, scenario_start):
        """Heading should change as target moves."""
        target = _make_entity("target", 6.0, 119.0, speed=8, course=90)
        pursuer = _make_entity("pursuer", 5.0, 118.0)
        store.add_entity(target)
        store.add_entity(pursuer)

        im = InterceptMovement(
            entity_speed_knots=20,
            target_entity_id="target",
            entity_store=store,
            pursuer_entity_id="pursuer",
        )

        state1 = im.get_state(scenario_start)
        # Move target
        target.update_position(6.0, 119.5, course_deg=90)
        store.update_entity(target)
        state2 = im.get_state(scenario_start + timedelta(minutes=10))

        # Heading should have changed
        assert abs(state1.heading_deg - state2.heading_deg) > 0.1
