"""Intercept lead-pursuit geometry tests.

Covers the SCN-MAL-02A regression: KD Perak (pursuer SSW of target) intercepts
PIRATE-002 which is fleeing SSW — target is closing on the pursuer, not fleeing
from it. The pursuer must head roughly north (toward target) rather than south
(away from target).
"""

import math
from datetime import datetime, timedelta, timezone

import pytest

from simulator.core.entity import Agency, Domain, Entity, EntityStatus, Position
from simulator.core.entity_store import EntityStore
from simulator.movement.intercept import InterceptMovement


@pytest.fixture
def sim_start():
    return datetime(2026, 4, 19, 0, 0, 0, tzinfo=timezone.utc)


def _make_surface(eid, lat, lon, agency, speed=0.0, course=0.0):
    return Entity(
        entity_id=eid, entity_type="MIL_NAVAL",
        domain=Domain.MARITIME, agency=agency,
        callsign=eid, position=Position(lat, lon),
        heading_deg=course, course_deg=course,
        speed_knots=speed,
        status=EntityStatus.ACTIVE,
    )


class TestInterceptLeadPursuit:
    def test_head_on_target_pursuer_heads_toward_target(self, sim_start):
        """SCN-MAL-02A: target fleeing SSW toward a pursuer positioned SSW of
        the target. Pursuer should head NE toward target, not SW away."""
        store = EntityStore()
        # KD Perak at blocking position (3.35 N, 100.45 E)
        perak = _make_surface("PERAK", 3.35, 100.45, Agency.MIL)
        # PIRATE-002 NNE of KD Perak, fleeing on SSW course (215°) at 28 kn
        pirate = _make_surface("PIRATE", 3.392, 100.466, Agency.MIL,
                               speed=28.0, course=215.0)
        store.add_entity(perak)
        store.add_entity(pirate)

        movement = InterceptMovement(
            entity_speed_knots=35.0,
            target_entity_id="PIRATE",
            entity_store=store,
            pursuer_entity_id="PERAK",
            lead_pursuit=True,
        )
        state = movement.get_state(sim_start + timedelta(seconds=1))

        # Target is NE of pursuer. Target fleeing SSW → converges with pursuer.
        # Correct lead pursuit aims between current target and pursuer's axis,
        # so heading should be in the northern semicircle (NW–N–NE). Anything
        # in the southern semicircle means the pursuer is running away.
        north_component = math.cos(math.radians(state.heading_deg))
        assert north_component > 0.3, (
            f"pursuer heading {state.heading_deg:.1f}° — should be northbound "
            f"(north component {north_component:.2f} > 0.3). Lead pursuit is "
            f"over-projecting the target past the pursuer due to broken "
            f"closing-speed formula."
        )

    def test_tail_chase_still_leads(self, sim_start):
        """Classic tail chase: target fleeing directly away at slower speed.
        Pursuer should head roughly toward the target (slight lead OK)."""
        store = EntityStore()
        # Pursuer south of target; target fleeing north at 15 kn
        pursuer = _make_surface("P", 3.0, 101.0, Agency.MIL)
        target = _make_surface("T", 3.1, 101.0, Agency.MIL, speed=15.0, course=0.0)
        store.add_entity(pursuer)
        store.add_entity(target)

        m = InterceptMovement(
            entity_speed_knots=30.0, target_entity_id="T",
            entity_store=store, pursuer_entity_id="P",
            lead_pursuit=True,
        )
        state = m.get_state(sim_start + timedelta(seconds=1))
        # Pursuer should head roughly north (0°). Lead extends further north.
        diff = abs((state.heading_deg - 0 + 180) % 360 - 180)
        assert diff < 20, f"tail chase heading should be ~north, got {state.heading_deg:.1f}°"
