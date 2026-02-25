"""
Realistic position and movement noise.

Without noise, entities move on perfect mathematical curves that look
artificial. This module adds sensor-appropriate jitter to positions,
speeds, and headings. Uses correlated (random-walk) noise for realism.
"""

import math
import random

from simulator.movement.waypoint import MovementState


class PositionNoise:
    """Adds GPS/sensor noise to movement states."""

    def __init__(
        self,
        position_noise_m: float = 15.0,
        speed_noise_pct: float = 0.02,
        heading_noise_deg: float = 2.0,
        seed: int | None = None,
    ) -> None:
        self._pos_sigma = position_noise_m
        self._speed_pct = speed_noise_pct
        self._heading_sigma = heading_noise_deg
        self._rng = random.Random(seed)

        # Correlated noise state (random walk offsets)
        self._offset_north_m = 0.0
        self._offset_east_m = 0.0
        self._speed_offset = 0.0
        self._heading_offset = 0.0

        # Step size for random walk (smaller = smoother)
        self._walk_step = 0.3

    def apply(self, state: MovementState) -> MovementState:
        """Apply noise to a MovementState. Returns a new MovementState."""
        # Random walk position offset
        self._offset_north_m += self._rng.gauss(0, self._pos_sigma * self._walk_step)
        self._offset_east_m += self._rng.gauss(0, self._pos_sigma * self._walk_step)

        # Clamp to 3-sigma
        max_offset = 3 * self._pos_sigma
        self._offset_north_m = max(-max_offset, min(max_offset, self._offset_north_m))
        self._offset_east_m = max(-max_offset, min(max_offset, self._offset_east_m))

        # Convert meter offsets to lat/lon
        # At ~5°N (Malaysian latitude): 1° lat ≈ 111km, 1° lon ≈ 110.5km
        dlat = self._offset_north_m / 111_111.0
        dlon = self._offset_east_m / (111_111.0 * math.cos(math.radians(state.lat)))

        # Random walk speed offset
        self._speed_offset += self._rng.gauss(0, self._speed_pct * self._walk_step)
        self._speed_offset = max(-3 * self._speed_pct, min(3 * self._speed_pct, self._speed_offset))
        noisy_speed = state.speed_knots * (1 + self._speed_offset)
        noisy_speed = max(0.0, noisy_speed)

        # Random walk heading offset
        self._heading_offset += self._rng.gauss(0, self._heading_sigma * self._walk_step)
        self._heading_offset = max(
            -3 * self._heading_sigma,
            min(3 * self._heading_sigma, self._heading_offset),
        )
        noisy_heading = (state.heading_deg + self._heading_offset) % 360.0
        noisy_course = (state.course_deg + self._heading_offset * 0.5) % 360.0

        return MovementState(
            lat=state.lat + dlat,
            lon=state.lon + dlon,
            alt_m=state.alt_m,
            heading_deg=noisy_heading,
            speed_knots=noisy_speed,
            course_deg=noisy_course,
            metadata_overrides=state.metadata_overrides,
        )

    @staticmethod
    def for_domain(domain: str, seed: int | None = None) -> "PositionNoise":
        """Factory method returning domain-appropriate noise levels."""
        configs = {
            "MARITIME": (15.0, 0.02, 2.0),
            "AIR": (50.0, 0.01, 1.0),
            "GROUND_VEHICLE": (5.0, 0.03, 1.0),
            "PERSONNEL": (3.0, 0.05, 5.0),
        }
        pos, spd, hdg = configs.get(domain, (15.0, 0.02, 2.0))
        return PositionNoise(
            position_noise_m=pos,
            speed_noise_pct=spd,
            heading_noise_deg=hdg,
            seed=seed,
        )
