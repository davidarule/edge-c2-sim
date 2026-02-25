"""
Simulation clock with configurable speed multiplier.

The clock drives all simulators. It can run at 1x (real-time), 2x, 5x,
10x, or 60x speed. Supports pause/resume. All domain simulators query
this clock for the current simulation time rather than using wall-clock time.
"""

import time
from datetime import datetime, timedelta, timezone
from typing import Callable


class SimulationClock:
    """
    Simulation clock that maps wall-clock time to simulated time.

    Not async — simply calculates sim time from wall clock when queried.
    No background thread needed.
    """

    def __init__(self, start_time: datetime | None = None, speed: float = 1.0) -> None:
        self._start_time = start_time or datetime.now(timezone.utc)
        self._speed = speed
        self._running = False
        self._wall_start: float | None = None
        self._accumulated_sim: timedelta = timedelta()
        self._tick_callbacks: list[Callable] = []

    @property
    def speed(self) -> float:
        """Current speed multiplier."""
        return self._speed

    @property
    def is_running(self) -> bool:
        """Whether the clock is currently running."""
        return self._running

    @property
    def start_time(self) -> datetime:
        """The simulation start time."""
        return self._start_time

    def start(self) -> None:
        """Begin advancing time."""
        if self._running:
            return
        self._running = True
        self._wall_start = time.monotonic()

    def pause(self) -> None:
        """Pause time advancement. Accumulates elapsed sim time."""
        if not self._running:
            return
        self._accumulated_sim = self.get_elapsed()
        self._running = False
        self._wall_start = None

    def resume(self) -> None:
        """Resume from paused state."""
        if self._running:
            return
        self._running = True
        self._wall_start = time.monotonic()

    def reset(self) -> None:
        """Reset clock to the beginning (elapsed = 0). Clock is left paused."""
        self._running = False
        self._wall_start = None
        self._accumulated_sim = timedelta()

    def set_speed(self, multiplier: float) -> None:
        """Change speed multiplier. Accumulates elapsed time at old speed first."""
        if self._running:
            self._accumulated_sim = self.get_elapsed()
            self._wall_start = time.monotonic()
        self._speed = multiplier

    def get_elapsed(self) -> timedelta:
        """Get elapsed simulation time since start."""
        if not self._running or self._wall_start is None:
            return self._accumulated_sim
        wall_elapsed = time.monotonic() - self._wall_start
        sim_elapsed = timedelta(seconds=wall_elapsed * self._speed)
        return self._accumulated_sim + sim_elapsed

    def get_sim_time(self) -> datetime:
        """Get current simulation datetime."""
        return self._start_time + self.get_elapsed()

    def add_tick_callback(self, callback: Callable) -> None:
        """Register a function to be called on each tick."""
        self._tick_callbacks.append(callback)

    def tick(self) -> None:
        """Process one tick — calls all registered callbacks."""
        for cb in self._tick_callbacks:
            cb(self.get_sim_time())
