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
    """Adds GPS/sensor noise to movement states.

    Uses a correlated random walk with exponential decay so noise
    drifts smoothly rather than teleporting each tick. Each entity
    must have its OWN instance — do not share across entities.
    """

    def __init__(
        self,
        position_noise_m: float = 15.0,
        speed_noise_pct: float = 0.02,
        heading_noise_deg: float = 2.0,
        decay: float = 0.92,
        step_size: float = 2.0,
        seed: int | None = None,
    ) -> None:
        self._max_amplitude_m = position_noise_m
        self._speed_pct = speed_noise_pct
        self._heading_sigma = heading_noise_deg
        self._decay = decay
        self._step_size = step_size
        self._rng = random.Random(seed)

        # Correlated noise state (random walk offsets in meters)
        self._noise_north_m = 0.0
        self._noise_east_m = 0.0
        self._speed_offset = 0.0
        self._heading_offset = 0.0

    def apply(self, state: MovementState) -> MovementState:
        """Apply noise to a MovementState. Returns a new MovementState."""
        # Random walk with decay — smooth correlated drift
        self._noise_north_m += self._rng.gauss(0, self._step_size)
        self._noise_east_m += self._rng.gauss(0, self._step_size)

        # Clamp to max amplitude
        self._noise_north_m = max(-self._max_amplitude_m,
                                  min(self._max_amplitude_m, self._noise_north_m))
        self._noise_east_m = max(-self._max_amplitude_m,
                                 min(self._max_amplitude_m, self._noise_east_m))

        # Apply decay (noise drifts back toward zero over time)
        self._noise_north_m *= self._decay
        self._noise_east_m *= self._decay

        # Convert meter offsets to lat/lon
        dlat = self._noise_north_m / 111_111.0
        dlon = self._noise_east_m / (111_111.0 * math.cos(math.radians(state.lat)))

        # Random walk speed offset
        self._speed_offset += self._rng.gauss(0, self._speed_pct * 0.3)
        self._speed_offset = max(-3 * self._speed_pct, min(3 * self._speed_pct, self._speed_offset))
        self._speed_offset *= 0.95  # decay
        noisy_speed = state.speed_knots * (1 + self._speed_offset)
        noisy_speed = max(0.0, noisy_speed)

        # Random walk heading offset
        self._heading_offset += self._rng.gauss(0, self._heading_sigma * 0.3)
        self._heading_offset = max(
            -3 * self._heading_sigma,
            min(3 * self._heading_sigma, self._heading_offset),
        )
        self._heading_offset *= 0.95  # decay
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
        """Factory method returning domain-appropriate noise levels.

        Returns a NEW instance each call — do not share across entities.
        """
        # (max_amplitude_m, speed_pct, heading_deg, decay, step_size)
        configs = {
            "MARITIME": (15.0, 0.02, 2.0, 0.92, 2.0),
            "AIR": (50.0, 0.01, 1.0, 0.90, 5.0),
            "GROUND_VEHICLE": (5.0, 0.03, 1.0, 0.95, 0.5),
            "PERSONNEL": (3.0, 0.05, 5.0, 0.95, 0.3),
        }
        pos, spd, hdg, decay, step = configs.get(
            domain, (15.0, 0.02, 2.0, 0.92, 2.0)
        )
        return PositionNoise(
            position_noise_m=pos,
            speed_noise_pct=spd,
            heading_noise_deg=hdg,
            decay=decay,
            step_size=step,
            seed=seed,
        )
