"""Tests for the SimulationClock."""

import time
from datetime import datetime, timedelta, timezone

from simulator.core.clock import SimulationClock


class TestSimulationClock:
    def test_initial_state(self):
        start = datetime(2026, 4, 15, 8, 0, 0, tzinfo=timezone.utc)
        clock = SimulationClock(start_time=start, speed=1.0)
        assert clock.speed == 1.0
        assert not clock.is_running
        assert clock.start_time == start
        assert clock.get_sim_time() == start

    def test_start_advances_time(self):
        start = datetime(2026, 4, 15, 8, 0, 0, tzinfo=timezone.utc)
        clock = SimulationClock(start_time=start, speed=1.0)
        clock.start()
        time.sleep(0.1)
        sim_time = clock.get_sim_time()
        assert sim_time > start
        elapsed = clock.get_elapsed()
        assert elapsed.total_seconds() > 0.05

    def test_speed_multiplier(self):
        start = datetime(2026, 4, 15, 8, 0, 0, tzinfo=timezone.utc)
        clock = SimulationClock(start_time=start, speed=10.0)
        clock.start()
        time.sleep(0.1)
        elapsed = clock.get_elapsed().total_seconds()
        # At 10x, 0.1s wall time = ~1.0s sim time (with tolerance)
        assert elapsed > 0.5
        assert elapsed < 3.0

    def test_pause_stops_time(self):
        clock = SimulationClock(speed=1.0)
        clock.start()
        time.sleep(0.05)
        clock.pause()
        paused_time = clock.get_sim_time()
        time.sleep(0.1)
        assert clock.get_sim_time() == paused_time
        assert not clock.is_running

    def test_resume_continues(self):
        clock = SimulationClock(speed=1.0)
        clock.start()
        time.sleep(0.05)
        clock.pause()
        paused_elapsed = clock.get_elapsed()
        clock.resume()
        time.sleep(0.05)
        resumed_elapsed = clock.get_elapsed()
        assert resumed_elapsed > paused_elapsed

    def test_set_speed(self):
        clock = SimulationClock(speed=1.0)
        clock.start()
        time.sleep(0.05)
        clock.set_speed(10.0)
        assert clock.speed == 10.0
        time.sleep(0.05)
        # Should have accumulated time at both speeds
        elapsed = clock.get_elapsed().total_seconds()
        assert elapsed > 0.3  # more than 0.1s at pure 1x

    def test_set_speed_while_paused(self):
        clock = SimulationClock(speed=1.0)
        clock.start()
        time.sleep(0.05)
        clock.pause()
        paused_elapsed = clock.get_elapsed()
        clock.set_speed(5.0)
        assert clock.speed == 5.0
        # Elapsed shouldn't change while paused
        assert clock.get_elapsed() == paused_elapsed

    def test_elapsed_when_not_started(self):
        clock = SimulationClock(speed=1.0)
        assert clock.get_elapsed() == timedelta()

    def test_tick_callback(self):
        clock = SimulationClock(speed=1.0)
        clock.start()
        received = []
        clock.add_tick_callback(lambda t: received.append(t))
        clock.tick()
        assert len(received) == 1
        assert isinstance(received[0], datetime)

    def test_multiple_tick_callbacks(self):
        clock = SimulationClock(speed=1.0)
        clock.start()
        a, b = [], []
        clock.add_tick_callback(lambda t: a.append(t))
        clock.add_tick_callback(lambda t: b.append(t))
        clock.tick()
        assert len(a) == 1
        assert len(b) == 1

    def test_default_start_time(self):
        before = datetime.now(timezone.utc)
        clock = SimulationClock()
        after = datetime.now(timezone.utc)
        assert before <= clock.start_time <= after

    def test_start_idempotent(self):
        clock = SimulationClock(speed=1.0)
        clock.start()
        time.sleep(0.05)
        elapsed_before = clock.get_elapsed()
        clock.start()  # should be no-op
        elapsed_after = clock.get_elapsed()
        # Time should still be advancing, not reset
        assert elapsed_after >= elapsed_before
