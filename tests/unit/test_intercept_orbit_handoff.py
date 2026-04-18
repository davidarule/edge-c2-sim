"""Intercept→orbit handoff: pirate should stay on the side it arrived from."""

import math
from datetime import datetime, timedelta, timezone

import pytest
from geopy.distance import geodesic

from simulator.core.entity import Agency, Domain, Entity, EntityStatus, Position
from simulator.core.entity_store import EntityStore
from simulator.movement.intercept import InterceptMovement
from simulator.scenario.event_engine import EventEngine
from simulator.scenario.loader import ScenarioEvent


@pytest.fixture
def sim_start():
    return datetime(2026, 4, 19, 0, 0, 0, tzinfo=timezone.utc)


def _surface(eid, lat, lon, etype="SUSPECT_VESSEL", heading=0.0, speed=0.0):
    return Entity(
        entity_id=eid, entity_type=etype,
        domain=Domain.MARITIME, agency=Agency.MMEA,
        callsign=eid, position=Position(lat, lon),
        heading_deg=heading, course_deg=heading,
        speed_knots=speed, status=EntityStatus.ACTIVE,
    )


class TestInterceptOrbitHandoff:
    def test_pirate_intercepts_from_south_stays_south_after_orbit(self, sim_start):
        """PIRATE-002 approaches tanker from the south and hits the 500m intercept
        radius. on_complete_action: orbit. The orbit circle should place the
        pirate on the south side of the tanker — not teleport it to north."""
        store = EntityStore()
        # Tanker heading NW but momentarily stationary at this instant
        tanker = _surface("TANKER", 3.392, 100.484, etype="CIVILIAN_TANKER",
                          heading=315.0, speed=0.0)
        # Pirate 300m south of tanker (inside 500m intercept radius)
        pirate_lat = 3.392 - 300 / 111_111.0
        pirate = _surface("PIRATE", pirate_lat, 100.484, heading=0.0, speed=25.0)
        store.add_entity(tanker)
        store.add_entity(pirate)

        # Construct an intercept movement that is about to complete
        movements: dict = {}
        movements["PIRATE"] = InterceptMovement(
            entity_speed_knots=25.0, target_entity_id="TANKER",
            entity_store=store, pursuer_entity_id="PIRATE",
        )

        # pirate_sprint: the intercept event with on_complete_action orbit
        pirate_sprint = ScenarioEvent(
            id="pirate2_sprint",
            time_offset=timedelta(0),
            event_type="DETECTION", description="pirate sprint",
            target="PIRATE", action="intercept",
            intercept_target="TANKER",
            on_complete_action="orbit",
            metadata={
                "orbit_center": "TANKER",
                "orbit_radius_nm": 0.18,
                "orbit_speed": 4.0,
                "orbit_direction": "CCW",
            },
        )
        engine = EventEngine([pirate_sprint], store, movements, sim_start)
        engine._register_completion(pirate_sprint)

        # Drive one tick through the movement — this triggers _intercepted=True
        state = movements["PIRATE"].get_state(sim_start + timedelta(seconds=1))
        pirate.position = Position(state.lat, state.lon)
        store.upsert_entity(pirate)

        # Process completions → swaps in OrbitMovement
        engine._check_completions(sim_start + timedelta(seconds=1))

        # Sample the new orbit movement
        orbit = movements["PIRATE"]
        from simulator.movement.orbit import OrbitMovement
        assert isinstance(orbit, OrbitMovement), f"expected OrbitMovement, got {type(orbit)}"

        orbit_state = orbit.get_state(sim_start + timedelta(seconds=2))

        # Pirate should still be SOUTH of the tanker (lat < tanker.lat)
        dlat_m = (orbit_state.lat - tanker.position.latitude) * 111_111.0
        assert dlat_m < 0, (
            f"pirate jumped to the NORTH side of the tanker after intercept→orbit "
            f"handoff: Δlat = {dlat_m:.0f} m (positive = north). Should be negative "
            f"because pirate arrived from the south."
        )

    def test_no_radial_snap_at_intercept_orbit_handoff(self, sim_start):
        """Intercept fires at 500m by default but orbit places the entity on a
        fixed radius (here ~334m). Between the last intercept position and the
        first orbit position the entity should not jump more than a tick's
        worth of travel — if intercept_radius is synced to orbit_radius, there
        is no radial snap."""
        store = EntityStore()
        tanker = _surface("TANKER", 3.392, 100.484, etype="CIVILIAN_TANKER", speed=0.0)
        # Pirate 600 m south of tanker, moving north at 25 kn — will cross
        # both the intercept radius and orbit radius.
        pirate_lat = 3.392 - 600 / 111_111.0
        pirate = _surface("PIRATE", pirate_lat, 100.484, heading=0.0, speed=25.0)
        store.add_entity(tanker)
        store.add_entity(pirate)

        movements: dict = {}
        pirate_sprint = ScenarioEvent(
            id="pirate2_sprint",
            time_offset=timedelta(0),
            event_type="DETECTION", description="pirate sprint",
            target="PIRATE", action="intercept",
            intercept_target="TANKER",
            on_complete_action="orbit",
            metadata={
                "orbit_center": "TANKER",
                "orbit_radius_nm": 0.18,  # ~334 m
                "orbit_speed": 4.0,
                "orbit_direction": "CCW",
            },
        )
        engine = EventEngine([pirate_sprint], store, movements, sim_start)
        engine._register_completion(pirate_sprint)
        engine._fire_event(pirate_sprint, sim_start)

        # Drive the intercept forward until it completes. Each iteration does
        # one sim tick. We need enough to close the 600 m gap.
        t = sim_start
        last_pos = (pirate.position.latitude, pirate.position.longitude)
        for _ in range(120):  # up to 120 sim seconds
            t += timedelta(seconds=1)
            movement = movements.get("PIRATE")
            state = movement.get_state(t)
            # Capture last intercept position BEFORE possibly swapping to orbit
            was_intercept = isinstance(movement, InterceptMovement)
            pirate.position = Position(state.lat, state.lon)
            store.upsert_entity(pirate)
            engine.tick(t)
            now_movement = movements.get("PIRATE")
            if was_intercept and not isinstance(now_movement, InterceptMovement):
                # Handoff just happened. Next tick will call orbit.get_state
                # for the first time — measure any jump from the last intercept
                # position to the first orbit sample.
                t += timedelta(seconds=1)
                orbit_state = now_movement.get_state(t)
                jump_m = geodesic(
                    (state.lat, state.lon), (orbit_state.lat, orbit_state.lon),
                ).meters
                assert jump_m < 50.0, (
                    f"radial snap at intercept→orbit handoff: {jump_m:.0f} m "
                    f"(intercept completed at {(state.lat, state.lon)}, orbit "
                    f"started at {(orbit_state.lat, orbit_state.lon)})."
                )
                return
            last_pos = (state.lat, state.lon)
        pytest.fail("intercept never completed within 120 s")
