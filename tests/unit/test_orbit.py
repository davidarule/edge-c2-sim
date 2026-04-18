"""Tests for orbit movement."""

import math
from datetime import datetime, timedelta, timezone

import pytest

from simulator.movement.orbit import OrbitMovement, tangent_orbit_params


@pytest.fixture
def sim_start():
    return datetime(2026, 4, 19, 0, 0, 0, tzinfo=timezone.utc)


def _bearing_deg(center_lat, center_lon, lat, lon):
    dy = lat - center_lat
    dx = (lon - center_lon) * math.cos(math.radians(center_lat))
    return math.degrees(math.atan2(dx, dy)) % 360.0


class TestOrbitStartPosition:
    def test_starts_on_orbit_at_initial_heading(self, sim_start):
        """When initial_heading is supplied, the first sample must be at that bearing from center."""
        radius_m = 500.0
        orbit = OrbitMovement(
            center_lat=3.0, center_lon=101.0,
            altitude_m=0, speed_knots=4,
            orbit_radius_m=radius_m,
            initial_heading=180.0,  # due south of centre
        )
        state = orbit.get_state(sim_start)
        bearing = _bearing_deg(3.0, 101.0, state.lat, state.lon)
        assert abs(bearing - 180.0) < 1.0, f"expected bearing ~180°, got {bearing:.2f}°"

    def test_default_jumps_to_north_bug(self, sim_start):
        """Regression: without initial_heading the orbit starts due north (the bug we're documenting)."""
        orbit = OrbitMovement(
            center_lat=3.0, center_lon=101.0,
            altitude_m=0, speed_knots=4,
            orbit_radius_m=500.0,
            # initial_heading omitted -> defaults to 0 -> due north
        )
        state = orbit.get_state(sim_start)
        bearing = _bearing_deg(3.0, 101.0, state.lat, state.lon)
        assert abs(bearing - 0.0) < 1.0 or abs(bearing - 360.0) < 1.0, (
            f"default orbit should currently start at bearing 0° (north); got {bearing:.2f}°"
        )

    def test_from_entity_position_starts_near_entity(self, sim_start):
        """If initial_heading is derived from the entity's current position, orbit should
        begin at the entity's bearing from centre, not jump to north."""
        # Entity currently south-east of centre (bearing ~135°)
        center_lat, center_lon = 3.0, 101.0
        entity_lat, entity_lon = 2.9960, 101.0053  # roughly 135° at ~0.6km
        initial_bearing = _bearing_deg(center_lat, center_lon, entity_lat, entity_lon)

        orbit = OrbitMovement(
            center_lat=center_lat, center_lon=center_lon,
            altitude_m=0, speed_knots=4,
            orbit_radius_m=500.0,
            initial_heading=initial_bearing,
        )
        state = orbit.get_state(sim_start)
        bearing = _bearing_deg(center_lat, center_lon, state.lat, state.lon)
        assert abs(bearing - initial_bearing) < 1.0, (
            f"orbit should begin at entity's bearing {initial_bearing:.2f}°, got {bearing:.2f}°"
        )


class TestEventEngineOrbitStart:
    """Event-engine-level: an ORDER/orbit should not teleport the entity to due north."""

    def test_orbit_action_begins_at_entity_bearing(self, sim_start):
        """When event engine fires an orbit action, the resulting OrbitMovement should start
        from the entity's current bearing relative to the orbit centre — not default to north."""
        from simulator.core.entity import Agency, Domain, Entity, EntityStatus, Position
        from simulator.core.entity_store import EntityStore
        from simulator.scenario.event_engine import EventEngine
        from simulator.scenario.loader import ScenarioEvent

        # Orbit center entity (tanker) at (3.0, 101.0)
        # Pirate currently south-east of tanker at bearing ~135°
        center = Entity(
            entity_id="TANKER", entity_type="TANKER_CARGO",
            domain=Domain.MARITIME, agency=Agency.MMEA,
            callsign="TANKER", position=Position(3.0, 101.0),
            status=EntityStatus.ACTIVE,
        )
        pirate = Entity(
            entity_id="PIRATE", entity_type="SUSPECT_VESSEL",
            domain=Domain.MARITIME, agency=Agency.MMEA,
            callsign="PIRATE", position=Position(2.9960, 101.0053),
            status=EntityStatus.ACTIVE,
        )
        store = EntityStore()
        store.add_entity(center)
        store.add_entity(pirate)

        expected_bearing = _bearing_deg(3.0, 101.0, 2.9960, 101.0053)

        movements: dict = {}
        event = ScenarioEvent(
            time_offset=timedelta(minutes=1),
            event_type="ORDER", description="Orbit tanker",
            actionee="PIRATE", action="orbit",
            metadata={
                "orbit_center": "TANKER",
                "orbit_radius_nm": 0.18,
                "orbit_speed": 4,
            },
        )
        engine = EventEngine([event], store, movements, sim_start)
        engine.tick(sim_start + timedelta(minutes=1))

        assert "PIRATE" in movements
        state = movements["PIRATE"].get_state(sim_start + timedelta(minutes=1))
        actual_bearing = _bearing_deg(3.0, 101.0, state.lat, state.lon)

        diff = abs((actual_bearing - expected_bearing + 180) % 360 - 180)
        assert diff < 5.0, (
            f"orbit should start near entity's bearing {expected_bearing:.1f}°, "
            f"but started at {actual_bearing:.1f}° (diff {diff:.1f}°)"
        )


class TestTangentOrbit:
    """tangent_orbit_params should place the entity ON the orbit circle at a tangent
    to its current heading — so a fixed-wing aircraft entering a loiter pattern
    does not teleport radius-metres away from where it just arrived."""

    def test_entity_on_circle_after_handoff(self, sim_start):
        """First get_state after a tangent-orbit handoff must place the entity near
        its current position, not `radius_m` metres away."""
        aircraft_lat, aircraft_lon, heading = 3.0, 101.0, 90.0  # heading east
        radius_m = 3000.0
        center_lat, center_lon, initial_heading = tangent_orbit_params(
            aircraft_lat, aircraft_lon, heading, radius_m, direction="CW",
        )
        orbit = OrbitMovement(
            center_lat=center_lat, center_lon=center_lon,
            altitude_m=1000.0, speed_knots=150.0,
            orbit_radius_m=radius_m,
            initial_heading=initial_heading,
            direction="CW",
        )
        state = orbit.get_state(sim_start)
        # Distance from entity's arrival point to orbit's first sample
        dy_m = (state.lat - aircraft_lat) * 111_111.0
        dx_m = (state.lon - aircraft_lon) * 111_111.0 * math.cos(math.radians(aircraft_lat))
        jump_m = math.hypot(dx_m, dy_m)
        assert jump_m < 50.0, (
            f"tangent orbit jumped {jump_m:.0f} m on first sample (expected ~0)"
        )

    def test_initial_course_matches_heading(self, sim_start):
        """The course on first sample should match the aircraft's incoming heading
        so the handoff is visually seamless."""
        heading = 45.0  # NE
        center_lat, center_lon, initial_heading = tangent_orbit_params(
            3.0, 101.0, heading, 3000.0, direction="CW",
        )
        orbit = OrbitMovement(
            center_lat=center_lat, center_lon=center_lon,
            altitude_m=1000.0, speed_knots=150.0,
            orbit_radius_m=3000.0,
            initial_heading=initial_heading,
            direction="CW",
        )
        state = orbit.get_state(sim_start)
        diff = abs((state.course_deg - heading + 180) % 360 - 180)
        assert diff < 2.0, f"course {state.course_deg:.1f}° does not match heading {heading}°"
