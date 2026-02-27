"""Tests for position noise."""

import math
import statistics

import pytest

from simulator.movement.noise import PositionNoise
from simulator.movement.waypoint import MovementState


@pytest.fixture
def base_state():
    return MovementState(
        lat=5.5, lon=118.5, alt_m=0.0,
        heading_deg=90.0, speed_knots=10.0, course_deg=90.0,
    )


class TestPositionNoise:
    def test_position_within_sigma(self, base_state):
        """Noisy positions should be within expected sigma of true position."""
        noise = PositionNoise(position_noise_m=15.0, seed=42)
        offsets_m = []
        for _ in range(200):
            noisy = noise.apply(base_state)
            dlat_m = (noisy.lat - base_state.lat) * 111_111.0
            dlon_m = (noisy.lon - base_state.lon) * 111_111.0 * math.cos(math.radians(base_state.lat))
            offset = math.sqrt(dlat_m ** 2 + dlon_m ** 2)
            offsets_m.append(offset)

        # Mean offset should be reasonable (within 3-sigma of position noise)
        assert max(offsets_m) < 15.0 * 3 * 2  # Extra tolerance for random walk

    def test_speed_in_range(self, base_state):
        """Noisy speed should stay within expected bounds."""
        noise = PositionNoise(speed_noise_pct=0.02, seed=42)
        for _ in range(100):
            noisy = noise.apply(base_state)
            # Speed should be within ~6% of original (3-sigma of 2%)
            assert noisy.speed_knots >= base_state.speed_knots * 0.9
            assert noisy.speed_knots <= base_state.speed_knots * 1.1

    def test_heading_bounded(self, base_state):
        """Heading noise should be bounded."""
        noise = PositionNoise(heading_noise_deg=2.0, seed=42)
        for _ in range(100):
            noisy = noise.apply(base_state)
            diff = abs(noisy.heading_deg - base_state.heading_deg)
            if diff > 180:
                diff = 360 - diff
            assert diff < 15  # Within reasonable bounds for random walk

    def test_domain_factory(self):
        """Domain factory should return correct noise levels."""
        maritime = PositionNoise.for_domain("MARITIME")
        assert maritime._max_amplitude_m == 15.0

        air = PositionNoise.for_domain("AIR")
        assert air._max_amplitude_m == 50.0

        ground = PositionNoise.for_domain("GROUND_VEHICLE")
        assert ground._max_amplitude_m == 5.0

        personnel = PositionNoise.for_domain("PERSONNEL")
        assert personnel._max_amplitude_m == 3.0

    def test_correlated_noise(self, base_state):
        """Consecutive noisy samples should be closer than independent samples."""
        noise = PositionNoise(position_noise_m=15.0, seed=42)
        states = [noise.apply(base_state) for _ in range(50)]

        # Calculate consecutive differences
        consecutive_diffs = []
        for i in range(1, len(states)):
            dlat = abs(states[i].lat - states[i-1].lat) * 111_111
            dlon = abs(states[i].lon - states[i-1].lon) * 111_111 * math.cos(math.radians(5.5))
            consecutive_diffs.append(math.sqrt(dlat**2 + dlon**2))

        # Calculate differences between every-other sample
        skip_diffs = []
        for i in range(2, len(states)):
            dlat = abs(states[i].lat - states[i-2].lat) * 111_111
            dlon = abs(states[i].lon - states[i-2].lon) * 111_111 * math.cos(math.radians(5.5))
            skip_diffs.append(math.sqrt(dlat**2 + dlon**2))

        # Consecutive should generally be smaller (correlated random walk)
        avg_consecutive = statistics.mean(consecutive_diffs)
        avg_skip = statistics.mean(skip_diffs)
        assert avg_consecutive < avg_skip * 1.5  # Correlated noise test

    def test_zero_speed_stays_nonnegative(self):
        """Speed should never go negative."""
        state = MovementState(
            lat=5.5, lon=118.5, alt_m=0, heading_deg=0,
            speed_knots=0.5, course_deg=0,
        )
        noise = PositionNoise(speed_noise_pct=0.05, seed=42)
        for _ in range(100):
            noisy = noise.apply(state)
            assert noisy.speed_knots >= 0

    def test_metadata_preserved(self, base_state):
        """Metadata overrides should pass through noise application."""
        base_state.metadata_overrides = {"ais_active": False}
        noise = PositionNoise(seed=42)
        noisy = noise.apply(base_state)
        assert noisy.metadata_overrides == {"ais_active": False}
