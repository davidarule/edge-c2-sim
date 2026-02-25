"""
YAML scenario file parser.

Reads a scenario YAML file, validates it against entity type definitions,
creates Entity objects with assigned MovementStrategy instances, and
returns a complete ScenarioState ready for the simulation engine.
"""

import json
import logging
import os
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml
from shapely.geometry import LineString, MultiPolygon, Polygon, shape

from simulator.core.entity import Agency, Domain, Entity, EntityStatus, Position
from simulator.movement.patrol import PatrolMovement
from simulator.movement.waypoint import Waypoint, WaypointMovement

logger = logging.getLogger(__name__)

# Default scenario start time (DSA 2026 demo)
DEFAULT_START = datetime(2026, 4, 15, 8, 0, 0, tzinfo=timezone.utc)

# Entity type definitions: type_name -> (domain, default_agency, speed_range, sidc_prefix)
ENTITY_TYPES: dict[str, dict[str, Any]] = {
    "SUSPECT_VESSEL": {
        "domain": Domain.MARITIME, "agency": Agency.CIVILIAN,
        "speed_range": (0, 35), "sidc": "SHSP------",
    },
    "CIVILIAN_FISHING": {
        "domain": Domain.MARITIME, "agency": Agency.CIVILIAN,
        "speed_range": (2, 8), "sidc": "SNSP------",
    },
    "CIVILIAN_CARGO": {
        "domain": Domain.MARITIME, "agency": Agency.CIVILIAN,
        "speed_range": (8, 16), "sidc": "SNSP------",
    },
    "CIVILIAN_TANKER": {
        "domain": Domain.MARITIME, "agency": Agency.CIVILIAN,
        "speed_range": (8, 14), "sidc": "SNSP------",
    },
    "CIVILIAN_LIGHT": {
        "domain": Domain.AIR, "agency": Agency.CIVILIAN,
        "speed_range": (80, 140), "sidc": "SNAP------",
    },
    "MMEA_PATROL": {
        "domain": Domain.MARITIME, "agency": Agency.MMEA,
        "speed_range": (8, 22), "sidc": "SFSP------",
    },
    "MMEA_FAST_INTERCEPT": {
        "domain": Domain.MARITIME, "agency": Agency.MMEA,
        "speed_range": (15, 35), "sidc": "SFSP------",
    },
    "MIL_NAVAL": {
        "domain": Domain.MARITIME, "agency": Agency.MIL,
        "speed_range": (10, 35), "sidc": "SFSP------",
    },
    "MIL_NAVAL_FIC": {
        "domain": Domain.MARITIME, "agency": Agency.MIL,
        "speed_range": (15, 35), "sidc": "SFSP------",
    },
    "RMAF_TRANSPORT": {
        "domain": Domain.AIR, "agency": Agency.RMAF,
        "speed_range": (120, 280), "sidc": "SFAP------",
    },
    "RMAF_MPA": {
        "domain": Domain.AIR, "agency": Agency.RMAF,
        "speed_range": (120, 280), "sidc": "SFAP------",
    },
    "RMAF_HELICOPTER": {
        "domain": Domain.AIR, "agency": Agency.RMAF,
        "speed_range": (0, 140), "sidc": "SFAP------",
    },
    "RMAF_FIGHTER": {
        "domain": Domain.AIR, "agency": Agency.RMAF,
        "speed_range": (200, 550), "sidc": "SFAP------",
    },
    "RMP_PATROL_CAR": {
        "domain": Domain.MARITIME, "agency": Agency.RMP,
        "speed_range": (10, 30), "sidc": "SFSP------",
    },
    "RMP_OFFICER": {
        "domain": Domain.PERSONNEL, "agency": Agency.RMP,
        "speed_range": (0, 4), "sidc": "SFGP------",
    },
    "CI_OFFICER": {
        "domain": Domain.PERSONNEL, "agency": Agency.CI,
        "speed_range": (0, 4), "sidc": "SFGP------",
    },
    "CI_IMMIGRATION_TEAM": {
        "domain": Domain.PERSONNEL, "agency": Agency.CI,
        "speed_range": (0, 4), "sidc": "SFGP------",
    },
    "MIL_VEHICLE": {
        "domain": Domain.GROUND_VEHICLE, "agency": Agency.MIL,
        "speed_range": (0, 50), "sidc": "SFGP------",
    },
    "MIL_APC": {
        "domain": Domain.GROUND_VEHICLE, "agency": Agency.MIL,
        "speed_range": (0, 40), "sidc": "SFGP------",
    },
    "MIL_INFANTRY": {
        "domain": Domain.PERSONNEL, "agency": Agency.MIL,
        "speed_range": (0, 4), "sidc": "SFGP------",
    },
    "HOSTILE_VESSEL": {
        "domain": Domain.MARITIME, "agency": Agency.CIVILIAN,
        "speed_range": (0, 35), "sidc": "SHSP------",
    },
    "HOSTILE_PERSONNEL": {
        "domain": Domain.PERSONNEL, "agency": Agency.CIVILIAN,
        "speed_range": (0, 6), "sidc": "SHGP------",
    },
    "CIVILIAN_TOURIST": {
        "domain": Domain.PERSONNEL, "agency": Agency.CIVILIAN,
        "speed_range": (0, 3), "sidc": "SNGP------",
    },
    "CIVILIAN_BOAT": {
        "domain": Domain.MARITIME, "agency": Agency.CIVILIAN,
        "speed_range": (3, 15), "sidc": "SNSP------",
    },
    "CIVILIAN_PASSENGER": {
        "domain": Domain.MARITIME, "agency": Agency.CIVILIAN,
        "speed_range": (5, 20), "sidc": "SNSP------",
    },
    "RMP_TACTICAL_TEAM": {
        "domain": Domain.PERSONNEL, "agency": Agency.RMP,
        "speed_range": (0, 6), "sidc": "SFGP------",
    },
    "MIL_INFANTRY_SQUAD": {
        "domain": Domain.PERSONNEL, "agency": Agency.MIL,
        "speed_range": (0, 6), "sidc": "SFGP------",
    },
}

# Callsign pools for background traffic
_CARGO_NAMES = [
    "Bintang Laut", "Seri Sabah", "Kota Makmur", "Lautan Mas",
    "Samudera Jaya", "Pelita Nusantara", "Borneo Star", "Mutiara Timur",
]
_FISHING_NAMES = ["Nelayan", "FB"]
_TANKER_NAMES = ["Miri Crude", "Kerteh", "Labuan Palm", "Bintulu Gas"]


def _parse_time_offset(time_str: str) -> timedelta:
    """Parse 'HH:MM' or 'HH:MM:SS' to timedelta."""
    parts = time_str.split(":")
    if len(parts) == 2:
        return timedelta(hours=int(parts[0]), minutes=int(parts[1]))
    elif len(parts) == 3:
        return timedelta(
            hours=int(parts[0]), minutes=int(parts[1]), seconds=int(parts[2])
        )
    raise ValueError(f"Invalid time format: {time_str}")


@dataclass
class ScenarioEvent:
    """A timed event in the scenario timeline."""
    time_offset: timedelta
    event_type: str
    description: str
    severity: str = "INFO"
    target: str | None = None
    targets: list[str] | None = None
    action: str | None = None
    intercept_target: str | None = None
    destination: dict | None = None
    area: str | None = None
    position: dict | None = None
    alert_agencies: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    source: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "time_offset_s": self.time_offset.total_seconds(),
            "event_type": self.event_type,
            "description": self.description,
            "severity": self.severity,
            "target": self.target,
            "targets": self.targets,
            "action": self.action,
            "intercept_target": self.intercept_target,
            "destination": self.destination,
            "area": self.area,
            "position": self.position,
            "alert_agencies": self.alert_agencies,
            "source": self.source,
        }


@dataclass
class ScenarioState:
    """Complete parsed scenario ready for simulation."""
    name: str
    description: str
    duration: timedelta
    center: tuple[float, float]
    zoom: int
    entities: dict[str, Entity]
    movements: dict[str, Any]  # entity_id -> movement strategy
    events: list[ScenarioEvent]
    start_time: datetime


class ScenarioLoader:
    """Loads and parses scenario YAML files."""

    def __init__(self, geodata_path: str = "geodata/") -> None:
        self._geodata_path = Path(geodata_path)
        self._zones: dict[str, Polygon | MultiPolygon] = {}
        self._routes: dict[str, LineString] = {}
        self._bases: dict[str, tuple[float, float]] = {}
        self._load_geodata()

    def _load_geodata(self) -> None:
        """Load all GeoJSON files and index by zone_id/route_id."""
        for geojson_file in self._geodata_path.rglob("*.geojson"):
            try:
                with open(geojson_file) as f:
                    data = json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(f"Failed to load {geojson_file}: {e}")
                continue

            features = data.get("features", [])
            for feat in features:
                props = feat.get("properties", {})
                geom = shape(feat["geometry"])

                zone_id = props.get("zone_id") or props.get("area_id")
                route_id = props.get("route_id")
                base_id = props.get("base_id")

                if zone_id and isinstance(geom, (Polygon, MultiPolygon)):
                    self._zones[zone_id] = geom
                elif route_id and isinstance(geom, LineString):
                    self._routes[route_id] = geom
                elif base_id and hasattr(geom, "x"):
                    self._bases[base_id] = (geom.y, geom.x)  # (lat, lon)

        logger.info(
            f"Loaded geodata: {len(self._zones)} zones, "
            f"{len(self._routes)} routes, {len(self._bases)} bases"
        )

    def load(
        self, scenario_path: str, start_time: datetime | None = None,
    ) -> ScenarioState:
        """Parse YAML file and return complete ScenarioState."""
        with open(scenario_path) as f:
            raw = yaml.safe_load(f)

        scenario = raw["scenario"]
        name = scenario["name"]
        description = scenario.get("description", "")
        duration_min = scenario["duration_minutes"]
        center = (scenario["center"]["lat"], scenario["center"]["lon"])
        zoom = scenario.get("zoom", 9)
        start = start_time or DEFAULT_START

        entities: dict[str, Entity] = {}
        movements: dict[str, Any] = {}

        # Parse scenario entities
        for entry in scenario.get("scenario_entities", []):
            entity, movement = self._parse_scenario_entity(entry, start)
            entities[entity.entity_id] = entity
            if movement:
                movements[entity.entity_id] = movement

        # Parse background entities
        for bg_config in scenario.get("background_entities", []):
            bg_pairs = self._create_background_entities(bg_config, start)
            for entity, movement in bg_pairs:
                entities[entity.entity_id] = entity
                if movement:
                    movements[entity.entity_id] = movement

        # Parse events
        events = self._parse_events(scenario.get("events", []))

        logger.info(
            f"Loaded scenario '{name}': {len(entities)} entities, "
            f"{len(events)} events over {duration_min} minutes"
        )

        return ScenarioState(
            name=name,
            description=description,
            duration=timedelta(minutes=duration_min),
            center=center,
            zoom=zoom,
            entities=entities,
            movements=movements,
            events=events,
            start_time=start,
        )

    def _parse_scenario_entity(
        self, entry: dict, start: datetime,
    ) -> tuple[Entity, Any]:
        """Parse a single scenario entity definition."""
        entity_id = entry["id"]
        entity_type = entry["type"]
        type_def = ENTITY_TYPES.get(entity_type, {})

        domain = type_def.get("domain", Domain.MARITIME)
        agency_str = entry.get("agency", type_def.get("agency", Agency.CIVILIAN))
        if isinstance(agency_str, str):
            agency = Agency(agency_str)
        else:
            agency = agency_str

        pos = entry.get("initial_position", {})
        position = Position(
            latitude=pos.get("lat", 0.0),
            longitude=pos.get("lon", 0.0),
            altitude_m=pos.get("alt_m", 0.0),
        )

        metadata = dict(entry.get("metadata", {}))
        metadata["entity_type_name"] = entity_type

        entity = Entity(
            entity_id=entity_id,
            entity_type=entity_type,
            domain=domain,
            agency=agency,
            callsign=entry.get("callsign", entity_id),
            position=position,
            status=EntityStatus.IDLE if entry.get("behavior") == "standby" else EntityStatus.ACTIVE,
            sidc=type_def.get("sidc", ""),
            metadata=metadata,
        )

        # Create movement strategy
        movement = None
        behavior = entry.get("behavior", "waypoint")

        if "waypoints" in entry and entry["waypoints"]:
            waypoints = []
            for wp in entry["waypoints"]:
                waypoints.append(Waypoint(
                    lat=wp["lat"],
                    lon=wp["lon"],
                    alt_m=wp.get("alt_m", 0.0),
                    speed_knots=wp.get("speed", 0.0),
                    time_offset=_parse_time_offset(wp["time"]),
                    metadata_overrides=wp.get("metadata"),
                ))
            movement = WaypointMovement(waypoints, start)
            if waypoints:
                entity.speed_knots = waypoints[0].speed_knots

        elif behavior == "patrol":
            patrol_area_id = entry.get("patrol_area")
            polygon = self._zones.get(patrol_area_id) if patrol_area_id else None
            if polygon:
                speed_range = type_def.get("speed_range", (5, 10))
                movement = PatrolMovement(
                    polygon=polygon if isinstance(polygon, Polygon)
                    else list(polygon.geoms)[0],
                    speed_range_knots=speed_range,
                    seed=hash(entity_id) & 0xFFFFFFFF,
                    scenario_start=start,
                )
                entity.speed_knots = sum(speed_range) / 2
            else:
                if patrol_area_id:
                    logger.warning(
                        f"Patrol area '{patrol_area_id}' not found for {entity_id}. "
                        f"Available: {list(self._zones.keys())}"
                    )
        # standby: no movement (entity stays in place)

        return entity, movement

    def _create_background_entities(
        self, config: dict, start: datetime,
    ) -> list[tuple[Entity, Any]]:
        """Generate background traffic entities."""
        entity_type = config["type"]
        count = config.get("count", 1)
        type_def = ENTITY_TYPES.get(entity_type, {})
        speed_range = type_def.get("speed_range", (5, 10))
        speed_var = config.get("speed_variation", 0.1)
        metadata = dict(config.get("metadata", {}))
        metadata["background"] = True
        metadata["entity_type_name"] = entity_type

        results = []
        rng = random.Random(hash(entity_type) & 0xFFFFFFFF)

        area_id = config.get("area")
        route_id = config.get("route")

        for i in range(count):
            eid = f"BG-{entity_type}-{i+1:03d}"
            callsign = self._generate_callsign(entity_type, i, rng)

            domain = type_def.get("domain", Domain.MARITIME)
            agency = type_def.get("agency", Agency.CIVILIAN)

            if area_id and area_id in self._zones:
                polygon = self._zones[area_id]
                if isinstance(polygon, MultiPolygon):
                    polygon = list(polygon.geoms)[0]

                speed = rng.uniform(*speed_range)
                speed *= 1 + rng.uniform(-speed_var, speed_var)

                entity = Entity(
                    entity_id=eid,
                    entity_type=entity_type,
                    domain=domain,
                    agency=agency,
                    callsign=callsign,
                    position=Position(0, 0),  # Will be set by patrol
                    speed_knots=speed,
                    sidc=type_def.get("sidc", ""),
                    metadata=dict(metadata),
                )

                movement = PatrolMovement(
                    polygon=polygon,
                    speed_range_knots=speed_range,
                    seed=(hash(eid) & 0xFFFFFFFF),
                    scenario_start=start,
                )

                # Set initial position from first patrol waypoint
                state = movement.get_state(start)
                entity.position = Position(state.lat, state.lon)

                results.append((entity, movement))

            elif route_id and route_id in self._routes:
                route = self._routes[route_id]
                coords = list(route.coords)
                if len(coords) < 2:
                    continue

                # Distribute entities along the route
                frac = i / max(count - 1, 1)
                point = route.interpolate(frac, normalized=True)

                speed = rng.uniform(*speed_range)
                speed *= 1 + rng.uniform(-speed_var, speed_var)

                # Build waypoints from route coords, starting from entity's position
                start_idx = int(frac * (len(coords) - 1))
                remaining_coords = coords[start_idx:]
                waypoints = []
                cumulative = timedelta(0)

                for j, (lon, lat) in enumerate(remaining_coords):
                    if j > 0:
                        prev_lon, prev_lat = remaining_coords[j - 1]
                        from geopy.distance import geodesic as geo_dist
                        dist_nm = geo_dist(
                            (prev_lat, prev_lon), (lat, lon)
                        ).nautical
                        travel_s = (dist_nm / speed * 3600) if speed > 0 else 0
                        cumulative += timedelta(seconds=travel_s)

                    waypoints.append(Waypoint(
                        lat=lat, lon=lon, speed_knots=speed,
                        time_offset=cumulative,
                    ))

                entity = Entity(
                    entity_id=eid,
                    entity_type=entity_type,
                    domain=domain,
                    agency=agency,
                    callsign=callsign,
                    position=Position(point.y, point.x),
                    speed_knots=speed,
                    sidc=type_def.get("sidc", ""),
                    metadata=dict(metadata),
                )

                if len(waypoints) >= 1:
                    movement = WaypointMovement(waypoints, start)
                    results.append((entity, movement))
                else:
                    results.append((entity, None))

            else:
                if area_id:
                    logger.warning(f"Area '{area_id}' not found for background {entity_type}")
                if route_id:
                    logger.warning(f"Route '{route_id}' not found for background {entity_type}")

        return results

    def _generate_callsign(
        self, entity_type: str, index: int, rng: random.Random,
    ) -> str:
        """Generate plausible callsign for background entities."""
        if "CARGO" in entity_type:
            name = rng.choice(_CARGO_NAMES)
            return f"MV {name}"
        elif "FISHING" in entity_type:
            return f"Nelayan {rng.randint(100, 999)}"
        elif "TANKER" in entity_type:
            name = rng.choice(_TANKER_NAMES)
            return f"MT {name}"
        elif "LIGHT" in entity_type:
            return f"9M-{rng.choice('ABCDEFG')}{rng.choice('ABCDEFG')}{rng.choice('ABCDEFG')}"
        return f"BG-{index+1:03d}"

    def _parse_events(self, events_raw: list[dict]) -> list[ScenarioEvent]:
        """Parse event definitions into ScenarioEvent objects."""
        events = []
        for entry in events_raw:
            time_offset = _parse_time_offset(entry["time"])
            event = ScenarioEvent(
                time_offset=time_offset,
                event_type=entry.get("type", "INFO"),
                description=entry.get("description", ""),
                severity=entry.get("severity", "INFO"),
                target=entry.get("target"),
                targets=entry.get("targets"),
                action=entry.get("action"),
                intercept_target=entry.get("intercept_target"),
                destination=entry.get("destination"),
                area=entry.get("area"),
                position=entry.get("position"),
                alert_agencies=entry.get("alert_agencies", []),
                source=entry.get("source"),
                metadata={
                    k: v for k, v in entry.items()
                    if k not in {
                        "time", "type", "description", "severity", "target",
                        "targets", "action", "intercept_target", "destination",
                        "area", "position", "alert_agencies", "source",
                    }
                },
            )
            events.append(event)

        # Sort by time
        events.sort(key=lambda e: e.time_offset)
        return events

    def validate(self, scenario_path: str) -> list[str]:
        """Validate scenario file without loading. Returns list of errors."""
        errors = []
        try:
            with open(scenario_path) as f:
                raw = yaml.safe_load(f)
        except yaml.YAMLError as e:
            return [f"YAML syntax error: {e}"]
        except FileNotFoundError:
            return [f"File not found: {scenario_path}"]

        if "scenario" not in raw:
            return ["Missing top-level 'scenario' key"]

        scenario = raw["scenario"]

        # Required fields
        for field_name in ["name", "duration_minutes", "center"]:
            if field_name not in scenario:
                errors.append(f"Missing required field: {field_name}")

        # Entity types
        entity_ids = set()
        for entry in scenario.get("scenario_entities", []):
            eid = entry.get("id")
            if not eid:
                errors.append("Scenario entity missing 'id'")
                continue
            if eid in entity_ids:
                errors.append(f"Duplicate entity ID: {eid}")
            entity_ids.add(eid)

            etype = entry.get("type")
            if etype and etype not in ENTITY_TYPES:
                errors.append(f"Unknown entity type '{etype}' for {eid}")

            # Check waypoint coords
            for j, wp in enumerate(entry.get("waypoints", [])):
                lat = wp.get("lat", 0)
                lon = wp.get("lon", 0)
                if not (-90 <= lat <= 90):
                    errors.append(f"Entity {eid} waypoint {j}: lat {lat} out of range")
                if not (-180 <= lon <= 180):
                    errors.append(f"Entity {eid} waypoint {j}: lon {lon} out of range")

            # Check patrol area exists
            patrol_area = entry.get("patrol_area")
            if patrol_area and patrol_area not in self._zones:
                errors.append(
                    f"Entity {eid}: area '{patrol_area}' not found. "
                    f"Available: {list(self._zones.keys())}"
                )

        # Background entities
        for bg in scenario.get("background_entities", []):
            etype = bg.get("type")
            if etype and etype not in ENTITY_TYPES:
                errors.append(f"Unknown background entity type: {etype}")
            area = bg.get("area")
            if area and area not in self._zones:
                errors.append(f"Background area '{area}' not found")
            route = bg.get("route")
            if route and route not in self._routes:
                errors.append(f"Background route '{route}' not found")

        # Events
        prev_time = timedelta(0)
        for i, evt in enumerate(scenario.get("events", [])):
            if "time" not in evt:
                errors.append(f"Event {i} missing 'time'")
                continue
            try:
                t = _parse_time_offset(evt["time"])
            except ValueError as e:
                errors.append(f"Event {i}: {e}")
                continue

            if t < prev_time:
                errors.append(
                    f"Event at {evt['time']} is out of chronological order"
                )
            prev_time = t

            # Check entity references
            target = evt.get("target")
            if target and target not in entity_ids:
                errors.append(
                    f"Event at {evt['time']} references entity '{target}' "
                    f"which is not in scenario_entities"
                )
            for t_id in evt.get("targets", []):
                if t_id not in entity_ids:
                    errors.append(
                        f"Event at {evt['time']} references entity '{t_id}' "
                        f"which is not in scenario_entities"
                    )

        return errors

    @property
    def zones(self) -> dict[str, Any]:
        return dict(self._zones)

    @property
    def routes(self) -> dict[str, Any]:
        return dict(self._routes)
