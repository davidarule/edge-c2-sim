"""
Timed event processor.

Checks the scenario event timeline each simulation tick. When an event's
time arrives, it fires: broadcasting the event through transport adapters
and modifying entity behavior as specified.
"""

import logging
from datetime import datetime, timedelta
from typing import Any

from geopy.distance import geodesic

from simulator.core.entity import EntityStatus
from simulator.core.entity_store import EntityStore
from simulator.movement.intercept import InterceptMovement
from simulator.movement.waypoint import Waypoint, WaypointMovement
from simulator.scenario.loader import ENTITY_TYPES, ScenarioEvent

logger = logging.getLogger(__name__)


class EventEngine:
    """Processes timed scenario events and modifies entity behavior."""

    def __init__(
        self,
        events: list[ScenarioEvent],
        entity_store: EntityStore,
        movements: dict[str, Any],
        scenario_start: datetime,
    ) -> None:
        self._events = sorted(events, key=lambda e: e.time_offset)
        self._entity_store = entity_store
        self._movements = movements
        self._scenario_start = scenario_start
        self._fired: list[ScenarioEvent] = []
        self._fired_set: set[int] = set()  # indices of fired events

    def tick(self, sim_time: datetime) -> list[ScenarioEvent]:
        """Check and fire events whose time has arrived.
        Returns list of newly fired events."""
        elapsed = sim_time - self._scenario_start
        newly_fired = []

        for i, event in enumerate(self._events):
            if i in self._fired_set:
                continue
            if event.time_offset <= elapsed:
                self._fire_event(event, sim_time)
                self._fired.append(event)
                self._fired_set.add(i)
                newly_fired.append(event)
                logger.info(
                    f"[{event.event_type}] {event.description}"
                )

        return newly_fired

    def _fire_event(self, event: ScenarioEvent, sim_time: datetime) -> None:
        """Execute an event's action on its target entities."""
        if not event.action:
            return

        # Collect all target entity IDs
        target_ids = []
        if event.target:
            target_ids.append(event.target)
        if event.targets:
            target_ids.extend(event.targets)

        for target_id in target_ids:
            entity = self._entity_store.get_entity(target_id)
            if not entity:
                logger.warning(f"Event target '{target_id}' not found in store")
                continue

            self._apply_action(event, entity, target_id, sim_time)

    def _apply_action(
        self, event: ScenarioEvent, entity: Any,
        target_id: str, sim_time: datetime,
    ) -> None:
        """Apply an event action to a specific entity."""
        action = event.action

        if action == "intercept":
            if not event.intercept_target:
                logger.warning(f"Intercept event for {target_id} missing intercept_target")
                return

            type_def = ENTITY_TYPES.get(entity.entity_type, {})
            max_speed = type_def.get("speed_range", (10, 20))[1]

            new_movement = InterceptMovement(
                entity_speed_knots=max_speed,
                target_entity_id=event.intercept_target,
                entity_store=self._entity_store,
                pursuer_entity_id=target_id,
            )
            self._movements[target_id] = new_movement
            entity.status = EntityStatus.INTERCEPTING
            entity.speed_knots = max_speed

        elif action in ("deploy", "respond"):
            entity.status = EntityStatus.RESPONDING

            if event.destination:
                # Create waypoint movement from current position to destination
                current_pos = entity.position
                type_def = ENTITY_TYPES.get(entity.entity_type, {})
                max_speed = type_def.get("speed_range", (10, 20))[1]

                # Personnel/infantry are transported by vehicle — use realistic speed
                if max_speed <= 6:
                    deploy_speed = 25  # Transported by boat/vehicle
                else:
                    deploy_speed = max_speed * 0.9

                # Calculate travel time from distance
                dist_nm = geodesic(
                    (current_pos.latitude, current_pos.longitude),
                    (event.destination["lat"], event.destination["lon"]),
                ).nautical
                if deploy_speed > 0 and dist_nm > 0:
                    travel_hours = dist_nm / deploy_speed
                    travel_td = timedelta(hours=travel_hours)
                else:
                    travel_td = timedelta(minutes=30)

                origin_wp = Waypoint(
                    lat=current_pos.latitude,
                    lon=current_pos.longitude,
                    speed_knots=deploy_speed,
                    time_offset=timedelta(0),
                )
                dest_wp = Waypoint(
                    lat=event.destination["lat"],
                    lon=event.destination["lon"],
                    speed_knots=0,
                    time_offset=travel_td,
                )
                new_movement = WaypointMovement([origin_wp, dest_wp], sim_time)
                self._movements[target_id] = new_movement
                entity.speed_knots = deploy_speed

        elif action in ("search_area", "patrol"):
            # If no destination provided, just activate — entity keeps current movement
            entity.status = EntityStatus.ACTIVE

        elif action in ("lockdown", "secure"):
            entity.status = EntityStatus.ACTIVE
            entity.speed_knots = 0
            # Remove movement — entity stays in place
            if target_id in self._movements:
                del self._movements[target_id]

        elif action == "activate":
            entity.status = EntityStatus.ACTIVE

        elif action == "escort_to_port":
            entity.status = EntityStatus.ACTIVE
            # All escort entities head to Sandakan port
            sandakan = {"lat": 5.84, "lon": 118.105}
            current_pos = entity.position
            type_def = ENTITY_TYPES.get(entity.entity_type, {})
            max_speed = type_def.get("speed_range", (10, 20))[1]
            escort_speed = max_speed * 0.5  # Slow escort speed

            dist_nm = geodesic(
                (current_pos.latitude, current_pos.longitude),
                (sandakan["lat"], sandakan["lon"]),
            ).nautical
            travel_td = timedelta(hours=dist_nm / escort_speed) if escort_speed > 0 else timedelta(hours=1)

            origin_wp = Waypoint(
                lat=current_pos.latitude, lon=current_pos.longitude,
                speed_knots=escort_speed, time_offset=timedelta(0),
            )
            dest_wp = Waypoint(
                lat=sandakan["lat"], lon=sandakan["lon"],
                speed_knots=0, time_offset=travel_td,
            )
            new_movement = WaypointMovement([origin_wp, dest_wp], sim_time)
            self._movements[target_id] = new_movement
            entity.speed_knots = escort_speed

        else:
            logger.debug(f"Unhandled action '{action}' for {target_id}")
            entity.status = EntityStatus.ACTIVE

        self._entity_store.upsert_entity(entity)

    def reset(self) -> None:
        """Reset all fired events so they can fire again."""
        self._fired.clear()
        self._fired_set.clear()

    def get_fired_events(self) -> list[ScenarioEvent]:
        """All events that have fired so far."""
        return list(self._fired)

    def get_upcoming_events(
        self, window: timedelta | None = None,
    ) -> list[ScenarioEvent]:
        """Events not yet fired, optionally within a time window."""
        upcoming = [
            e for i, e in enumerate(self._events) if i not in self._fired_set
        ]
        if window and self._fired:
            last_time = self._fired[-1].time_offset
            upcoming = [e for e in upcoming if e.time_offset <= last_time + window]
        return upcoming

    @property
    def is_complete(self) -> bool:
        """True when all events have fired."""
        return len(self._fired_set) == len(self._events)

    @property
    def total_events(self) -> int:
        return len(self._events)
