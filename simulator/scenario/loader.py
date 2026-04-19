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
from simulator.movement.waypoint import TurnParams, Waypoint, WaypointMovement

logger = logging.getLogger(__name__)

# Default scenario start time (DSA 2026 demo)
DEFAULT_START = datetime(2026, 4, 15, 8, 0, 0, tzinfo=timezone.utc)


# 20-char 2525D SIDCs come from config/entity_types.json; they're the format
# the COP detail panel decodes. ENTITY_TYPES (below) carries legacy 10-char
# 2525B codes which the panel can't parse. Look up the 2525D code first.
_ENTITY_TYPE_DEFS_2525D: dict[str, dict] = {}
try:
    with open("config/entity_types.json") as _f:
        _ENTITY_TYPE_DEFS_2525D = json.load(_f).get("entity_types", {})
except (OSError, json.JSONDecodeError):
    pass


def get_default_sidc(entity_type: str) -> str:
    """Default SIDC for an entity type. Prefers 20-char 2525D from
    ``config/entity_types.json``; falls back to legacy 10-char 2525B in
    ``ENTITY_TYPES``."""
    td = _ENTITY_TYPE_DEFS_2525D.get(entity_type, {})
    sidc = td.get("default_sidc")
    if sidc:
        return sidc
    return ENTITY_TYPES.get(entity_type, {}).get("sidc", "")


# Per-domain action whitelist.
# An action/on_complete_action on an event whose actionee is in a given domain
# must be in this set; otherwise the validator emits an error. The `boarding`,
# `patrol`, and `search_area` actions are intentionally absent — see
# docs/scenario-schema.md (they're DEPRECATED and are no-ops at runtime).
DOMAIN_ACTIONS: dict[Any, frozenset[str]] = {
    "MARITIME": frozenset({
        "transit", "orbit", "hold_station", "escape", "approach",
        "alongside", "intercept", "pursue", "deploy", "respond",
        "escort_to_port", "reclassify", "lockdown", "secure", "activate",
    }),
    "AIR": frozenset({
        "transit", "orbit", "hold_station", "escape", "approach",
        "intercept", "pursue", "rtb", "deploy", "respond", "reclassify",
        "activate",
    }),
    "PERSONNEL": frozenset({
        "transit", "embark", "disembark", "hold_station", "approach",
        "escape", "reclassify", "activate", "lockdown", "secure",
    }),
    "GROUND_VEHICLE": frozenset({
        "transit", "hold_station", "escape", "approach", "rtb",
        "deploy", "respond", "reclassify", "activate",
    }),
}

# Entity type definitions. SIDC is 20-char MIL-STD-2525D throughout — we use
# 2525D as the platform's one-and-only symbol standard; 2525B/C are not
# supported. SIDCs are kept in sync with config/entity_types.json default_sidc.
ENTITY_TYPES: dict[str, dict[str, Any]] = {
    "SUSPECT_VESSEL": {
        "domain": Domain.MARITIME, "agency": Agency.CIVILIAN,
        "speed_range": (0, 35), "sidc": "10053000001400000000",
        "turn": (100.0, 3.5, 2.5),   # ~100m cargo/bulk carrier
    },
    "SUSPECT_FAST_BOAT": {
        "domain": Domain.MARITIME, "agency": Agency.CIVILIAN,
        "speed_range": (0, 45), "sidc": "10013000001400000000",
        "turn": (10.0, 1.5, 0.8),    # ~10m pirate skiff / fast attack boat
    },
    "CIVILIAN_FISHING": {
        "domain": Domain.MARITIME, "agency": Agency.CIVILIAN,
        "speed_range": (2, 8), "sidc": "10043000001402000000",
        "turn": (25.0, 2.5, 1.5),    # ~25m fishing vessel
    },
    "CIVILIAN_CARGO": {
        "domain": Domain.MARITIME, "agency": Agency.CIVILIAN,
        "speed_range": (8, 16), "sidc": "10043000001401010000",
        "turn": (130.0, 3.5, 2.5),   # ~130m general cargo
    },
    "CIVILIAN_TANKER": {
        "domain": Domain.MARITIME, "agency": Agency.CIVILIAN,
        "speed_range": (8, 14), "sidc": "10043000001401020000",
        "turn": (180.0, 4.0, 3.0),   # ~180m product tanker
    },
    "CIVILIAN_TANKER_VLCC": {
        "domain": Domain.MARITIME, "agency": Agency.CIVILIAN,
        "speed_range": (8, 14), "sidc": "10043000001401020000",
        "turn": (300.0, 4.5, 3.5),   # ~300m VLCC crude tanker (e.g. MT Labuan Palm)
    },
    "CIVILIAN_LIGHT": {
        "domain": Domain.AIR, "agency": Agency.CIVILIAN,
        "speed_range": (80, 140), "sidc": "10040100001201000000",
    },
    "CIVILIAN_COMMERCIAL": {
        "domain": Domain.AIR, "agency": Agency.CIVILIAN,
        "speed_range": (200, 400), "sidc": "10040100001200000000",
    },
    "MMEA_PATROL": {
        "domain": Domain.MARITIME, "agency": Agency.MMEA,
        "speed_range": (8, 28), "sidc": "10033000001205020000",
        "turn": (60.0, 3.0, 2.0),    # ~60m patrol vessel
    },
    "MMEA_FAST_INTERCEPT": {
        "domain": Domain.MARITIME, "agency": Agency.MMEA,
        "speed_range": (15, 50), "sidc": "10033000001205010000",
        "turn": (39.0, 2.0, 1.2),    # ~39m fast intercept craft
    },
    "MIL_NAVAL": {
        "domain": Domain.MARITIME, "agency": Agency.MIL,
        "speed_range": (10, 35), "sidc": "10033000001202060003",
        "turn": (80.0, 3.0, 2.5),    # ~80m corvette
    },
    "MIL_NAVAL_FRIGATE": {
        "domain": Domain.MARITIME, "agency": Agency.MIL,
        "speed_range": (15, 30), "sidc": "10033000001202040000",
        "turn": (105.0, 3.0, 2.5),   # ~105m frigate (KD Lekiu-class)
    },
    "MIL_NAVAL_FIC": {
        "domain": Domain.MARITIME, "agency": Agency.MIL,
        "speed_range": (15, 35), "sidc": "10033000001205010000",
        "turn": (50.0, 2.5, 1.5),    # ~50m fast intercept craft
    },
    "MIL_SUBMARINE": {
        "domain": Domain.MARITIME, "agency": Agency.MIL,
        "speed_range": (0, 20), "sidc": "10013500000000000000",  # Unknown until identified
        "turn": (60.0, 3.0, 2.0),    # ~60m submarine
    },
    "MIL_SUBMARINE_FRIENDLY": {
        "domain": Domain.MARITIME, "agency": Agency.MIL,
        "speed_range": (0, 20), "sidc": "10033500000000000000",  # Friendly — after identification
        "turn": (60.0, 3.0, 2.0),
    },
    "RMAF_TRANSPORT": {
        "domain": Domain.AIR, "agency": Agency.RMAF,
        "speed_range": (120, 280), "sidc": "10030100001101310000",
    },
    "RMAF_MPA": {
        "domain": Domain.AIR, "agency": Agency.RMAF,
        "speed_range": (120, 280), "sidc": "10030100001101000300",
    },
    "RMAF_HELICOPTER": {
        "domain": Domain.AIR, "agency": Agency.RMAF,
        "speed_range": (0, 140), "sidc": "10030100001102000000",
    },
    "RMAF_FIGHTER": {
        "domain": Domain.AIR, "agency": Agency.RMAF,
        "speed_range": (200, 550), "sidc": "10030100001101020000",
    },
    "RMP_PATROL_CAR": {
        "domain": Domain.GROUND_VEHICLE, "agency": Agency.RMP,
        "speed_range": (20, 80), "sidc": "10031500001700000000",
    },
    "RMP_PATROL_BOAT": {
        "domain": Domain.MARITIME, "agency": Agency.RMP,
        "speed_range": (10, 30), "sidc": "10033000001208010000",
        "turn": (8.0, 1.8, 1.0),     # ~8m patrol boat
    },
    "RMP_MARINE_PATROL": {
        "domain": Domain.MARITIME, "agency": Agency.RMP,
        "speed_range": (10, 30), "sidc": "10033000001208010000",
        "turn": (15.0, 2.0, 1.2),    # ~15m marine patrol vessel
    },
    "RMP_OFFICER": {
        "domain": Domain.PERSONNEL, "agency": Agency.RMP,
        "speed_range": (0, 4), "sidc": "10031000001401000000",
    },
    "CI_OFFICER": {
        "domain": Domain.PERSONNEL, "agency": Agency.CI,
        "speed_range": (0, 4), "sidc": "10031500001703000000",
    },
    "CI_IMMIGRATION_TEAM": {
        "domain": Domain.PERSONNEL, "agency": Agency.CI,
        "speed_range": (0, 4), "sidc": "10031500001703000000",
    },
    "MIL_VEHICLE": {
        "domain": Domain.GROUND_VEHICLE, "agency": Agency.MIL,
        "speed_range": (0, 50), "sidc": "10031500001202000000",
    },
    "MIL_APC": {
        "domain": Domain.GROUND_VEHICLE, "agency": Agency.MIL,
        "speed_range": (0, 40), "sidc": "10031500001201010000",
    },
    "MIL_INFANTRY": {
        "domain": Domain.PERSONNEL, "agency": Agency.MIL,
        "speed_range": (0, 4), "sidc": "10031000001201000000",
    },
    "HOSTILE_VESSEL": {
        "domain": Domain.MARITIME, "agency": Agency.CIVILIAN,
        "speed_range": (0, 35), "sidc": "10063000001400000000",
    },
    "HOSTILE_PERSONNEL": {
        "domain": Domain.PERSONNEL, "agency": Agency.CIVILIAN,
        "speed_range": (0, 6), "sidc": "10061000001201000000",
    },
    "CIVILIAN_TOURIST": {
        "domain": Domain.PERSONNEL, "agency": Agency.CIVILIAN,
        "speed_range": (0, 3), "sidc": "10041000001100000000",
    },
    "CIVILIAN_BOAT": {
        "domain": Domain.MARITIME, "agency": Agency.CIVILIAN,
        "speed_range": (3, 15), "sidc": "10043000001400000000",
    },
    "CIVILIAN_PASSENGER": {
        "domain": Domain.MARITIME, "agency": Agency.CIVILIAN,
        "speed_range": (5, 20), "sidc": "10043000001401030000",
    },
    "RMP_TACTICAL_TEAM": {
        "domain": Domain.PERSONNEL, "agency": Agency.RMP,
        "speed_range": (0, 25), "sidc": "10031000001211000000",  # up to 25kn for RHIB ops
    },
    "MIL_INFANTRY_SQUAD": {
        "domain": Domain.PERSONNEL, "agency": Agency.MIL,
        "speed_range": (0, 6), "sidc": "10031000001201000000",
    },
}

# Callsign pools for background traffic
_CARGO_NAMES = [
    "Bintang Laut", "Seri Sabah", "Kota Makmur", "Lautan Mas",
    "Samudera Jaya", "Pelita Nusantara", "Borneo Star", "Mutiara Timur",
]
_FISHING_NAMES = ["Nelayan", "FB"]
_TANKER_NAMES = ["Miri Crude", "Kerteh", "Labuan Palm", "Bintulu Gas"]


def _parse_start_time(value: Any) -> datetime:
    """Parse a scenario-level start_time into a UTC datetime.

    Accepts ISO 8601 strings ('2026-04-15T22:00:00Z', '2026-04-15T22:00:00+00:00',
    '2026-04-15 22:00') and the datetime instance PyYAML produces for timestamp
    scalars. Bare HH:MM strings are not supported here — start_time is an
    absolute instant, not an offset.
    """
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        s = value.strip().replace("Z", "+00:00")
        # `fromisoformat` handles both 'T' and space separators since 3.11.
        try:
            dt = datetime.fromisoformat(s)
        except ValueError as e:
            raise ValueError(
                f"start_time must be ISO 8601 UTC (e.g. 2026-04-15T22:00:00Z), got {value!r}"
            ) from e
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    raise ValueError(f"start_time must be a string or datetime, got {type(value).__name__}")


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
    """A timed or dependency-triggered event in the scenario timeline.

    Schema fields:
    - ``actionee``: the entity performing / experiencing the event.
    - ``target``:   the entity the action operates on (only set for
                    actions that have a target, e.g. intercept, approach).
    See ``docs/scenario-schema.md`` for the full reference.
    """
    time_offset: timedelta | None
    event_type: str
    description: str
    id: str | None = None
    after: str | dict | None = None
    severity: str = "INFO"
    actionee: str | None = None
    targets: list[str] | None = None
    action: str | None = None
    target: str | None = None
    destination: dict | None = None
    area: str | None = None
    position: dict | None = None
    alert_agencies: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    source: str | None = None
    on_initiate: str | None = None
    on_complete: str | None = None
    on_complete_action: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "time_offset_s": self.time_offset.total_seconds() if self.time_offset else None,
            "event_type": self.event_type,
            "description": self.on_initiate or self.description,
            "severity": self.severity,
            "actionee": self.actionee,
            "targets": self.targets,
            "action": self.action,
            "target": self.target,
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
    has_background_includes: bool = False


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
        # Resolution order for the scenario start clock:
        #   1. explicit start_time argument (programmatic override)
        #   2. top-level `start_time` field in the YAML (ISO 8601 UTC)
        #   3. DEFAULT_START (daytime placeholder)
        yaml_start = scenario.get("start_time")
        if start_time is not None:
            start = start_time
        elif yaml_start:
            start = _parse_start_time(yaml_start)
        else:
            start = DEFAULT_START
            logger.warning(
                f"Scenario {scenario_path} has no top-level `start_time` — "
                f"using default {DEFAULT_START.isoformat()}. "
                f"Night / specific-time scenarios should set start_time explicitly."
            )

        entities: dict[str, Entity] = {}
        movements: dict[str, Any] = {}

        # Parse scenario entities
        for entry in scenario.get("scenario_entities", []):
            entity, movement = self._parse_scenario_entity(entry, start)
            entities[entity.entity_id] = entity
            if movement:
                movements[entity.entity_id] = movement

        # Load included entity files (external YAML lists of scenario_entities)
        # Supports both v2 format (background.include) and legacy (include_entities)
        # Env var SKIP_BACKGROUND=1 disables background includes — useful when
        # you want to watch a scenario without 300 AIS vessels cluttering the
        # COP.
        scenario_dir = Path(scenario_path).parent
        bg = scenario.get("background", {})
        include_list = bg.get("include", []) if isinstance(bg, dict) else []
        if os.environ.get("SKIP_BACKGROUND"):
            if include_list:
                logger.info(
                    f"SKIP_BACKGROUND=1 — ignoring {len(include_list)} "
                    f"background include(s): {include_list}"
                )
            include_list = []
        if not include_list:
            include_list = scenario.get("include_entities", [])
        for include_path in include_list:
            inc_file = Path(include_path)
            if not inc_file.is_absolute():
                inc_file = scenario_dir / inc_file
            if not inc_file.exists():
                logger.warning(f"Include file not found: {inc_file}")
                continue
            with open(inc_file) as inc_f:
                inc_entries = yaml.safe_load(inc_f)
            if isinstance(inc_entries, list):
                for entry in inc_entries:
                    entity, movement = self._parse_scenario_entity(entry, start)
                    entities[entity.entity_id] = entity
                    if movement:
                        movements[entity.entity_id] = movement
                logger.info(
                    f"Included {len(inc_entries)} entities from {inc_file.name}"
                )

        # Parse background entities
        for bg_config in scenario.get("background_entities", []):
            bg_pairs = self._create_background_entities(bg_config, start)
            for entity, movement in bg_pairs:
                entities[entity.entity_id] = entity
                if movement:
                    movements[entity.entity_id] = movement

        # Validate terrain for waypoint-based movements
        self._validate_terrain(entities, movements, start)

        # Parse events
        events = self._parse_events(scenario.get("events", []))

        logger.info(
            f"Loaded scenario '{name}': {len(entities)} entities, "
            f"{len(events)} events over {duration_min} minutes"
        )

        has_bg = bool(include_list) or bool(scenario.get("background_entities")) or bool(bg.get("entities"))

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
            has_background_includes=has_bg,
        )

    def _validate_terrain(
        self, entities: dict, movements: dict, start: datetime,
    ) -> None:
        """Validate all maritime/ground entity starting positions and waypoints.

        If a maritime entity's authored starting position falls on land per the
        terrain dataset, auto-snap it to the nearest sea point *when* that point
        is within AUTO_SNAP_THRESHOLD_M. This covers the common case where
        authored dock coordinates sit at the waterfront edge and the Natural
        Earth 10m dataset treats that pixel as land — snap distance is typically
        10–30 m.

        Entities flagged as on land with NO nearby sea point, or with nearest
        sea further than the threshold, still raise (the scenario is
        genuinely pointing at the interior — an authoring error).
        """
        try:
            from scripts.terrain import get_nearest_sea_point, is_land
            from simulator.movement.terrain import find_nearest_valid_point, validate_position
        except ImportError:
            logger.debug("Terrain validation unavailable (scripts.terrain not installed)")
            return

        # Auto-snap radius for authored starting positions. The terrain
        # dataset (Natural Earth 10m raster) classifies piers, jetties, and
        # port infrastructure as "land" — authored dock coordinates routinely
        # sit 100 m to 3 km from the nearest raster-water pixel. 5 km is wide
        # enough to absorb that while still rejecting truly-inland authoring
        # errors (points that land dozens of km from any sea).
        AUTO_SNAP_THRESHOLD_M = 5000.0

        terrain_errors = []
        for eid, entity in entities.items():
            domain = entity.domain.value
            if domain != "MARITIME":
                continue
            if entity.metadata.get("skip_terrain_check"):
                continue
            movement = movements.get(eid)
            if isinstance(movement, PatrolMovement):
                # Patrol position is authoritative — YAML initial_position is a hint
                state = movement.get_state(start)
                lat, lon = state.lat, state.lon
                is_patrol = True
            else:
                lat = entity.position.latitude
                lon = entity.position.longitude
                is_patrol = False
            if not is_land(lat, lon):
                continue

            nearest = get_nearest_sea_point(lat, lon)
            if not nearest:
                msg = (
                    f"Maritime entity '{entity.callsign}' ({eid}) is on land: "
                    f"({lat:.4f}, {lon:.4f}) — no nearby sea point found"
                )
                logger.warning(msg)
                terrain_errors.append(msg)
                continue

            # Distance to nearest sea point (haversine-ish, adequate for < 1 km).
            import math
            dy_m = (nearest[0] - lat) * 111_111.0
            dx_m = (nearest[1] - lon) * 111_111.0 * math.cos(math.radians(lat))
            snap_dist_m = math.hypot(dx_m, dy_m)

            if snap_dist_m <= AUTO_SNAP_THRESHOLD_M and not is_patrol:
                entity.position = Position(
                    latitude=nearest[0],
                    longitude=nearest[1],
                    altitude_m=entity.position.altitude_m,
                )
                if entity.initial_position:
                    entity.initial_position = Position(
                        latitude=nearest[0],
                        longitude=nearest[1],
                        altitude_m=entity.initial_position.altitude_m,
                    )
                logger.info(
                    f"Auto-snapped '{entity.callsign}' ({eid}) from "
                    f"({lat:.6f}, {lon:.6f}) to nearest sea "
                    f"({nearest[0]:.6f}, {nearest[1]:.6f}) — shift {snap_dist_m:.1f} m"
                )
            else:
                msg = (
                    f"Maritime entity '{entity.callsign}' ({eid}) is on land: "
                    f"({lat:.4f}, {lon:.4f}) — nearest sea "
                    f"({nearest[0]:.4f}, {nearest[1]:.4f}) is {snap_dist_m:.0f} m away "
                    f"(> {AUTO_SNAP_THRESHOLD_M:.0f} m auto-snap limit)"
                )
                logger.warning(msg)
                terrain_errors.append(msg)

        if terrain_errors:
            raise ValueError(
                f"Scenario has {len(terrain_errors)} maritime entity/entities too far inland:\n"
                + "\n".join(f"  • {e}" for e in terrain_errors)
            )

        # Fix waypoints that are on wrong terrain (auto-correct rather than fail)
        fix_count = 0
        for eid, movement in movements.items():
            entity = entities.get(eid)
            if not entity:
                continue
            domain = entity.domain.value
            if domain == "AIR":
                continue

            if isinstance(movement, WaypointMovement):
                wps = movement.waypoints
                local_fixes = 0
                for i, wp in enumerate(wps):
                    if not validate_position(wp.lat, wp.lon, domain):
                        fix = find_nearest_valid_point(wp.lat, wp.lon, domain)
                        if fix:
                            logger.warning(
                                f"Terrain fix [{eid}] wp{i}: "
                                f"({wp.lat:.4f},{wp.lon:.4f})->({fix[0]:.4f},{fix[1]:.4f}) "
                                f"[{domain}]"
                            )
                            wps[i] = Waypoint(
                                lat=fix[0], lon=fix[1], alt_m=wp.alt_m,
                                speed_knots=wp.speed_knots,
                                time_offset=wp.time_offset,
                                metadata_overrides=wp.metadata_overrides,
                            )
                            local_fixes += 1
                        else:
                            logger.warning(
                                f"Terrain INVALID [{eid}] wp{i}: "
                                f"({wp.lat:.4f},{wp.lon:.4f}) — no fix found [{domain}]"
                            )
                if local_fixes > 0:
                    fix_count += local_fixes
                    # Rebuild movement with corrected waypoints (preserve turn_params)
                    movements[eid] = WaypointMovement(wps, start, turn_params=movement._turn_params)
                    # Update entity initial position
                    state = movements[eid].get_state(start)
                    entity.position = Position(state.lat, state.lon)

        if fix_count > 0:
            logger.info(f"Terrain validation: {fix_count} waypoints corrected")

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

        # Deferred spawn: entity hidden until sim clock reaches this offset
        spawn_at = None
        if "spawn_at" in entry:
            spawn_at = _parse_time_offset(entry["spawn_at"])

        # Embarked on carrier: entity hidden and tracks carrier position
        embarked_on = entry.get("embarked_on")
        if embarked_on:
            metadata["embarked_on"] = embarked_on

        # Read initial speed/heading from position (v2 format)
        initial_speed = pos.get("speed_kn", 0.0)
        initial_heading = pos.get("heading_deg", 0.0)

        # Soft precision check: maritime/port starting positions should be
        # authored at ~11 m resolution (4 decimal places) so entities are
        # placed at specific berths. Warn if either axis is exact at 3 dp or
        # coarser (i.e. lat*1000 is an integer within float tolerance).
        if type_def.get("domain") == Domain.MARITIME:
            raw_lat = pos.get("lat", 0.0)
            raw_lon = pos.get("lon", 0.0)
            coarse = []
            for label, val in (("lat", raw_lat), ("lon", raw_lon)):
                if val == 0.0:
                    continue
                scaled = val * 1000.0
                if abs(scaled - round(scaled)) < 1e-7:
                    coarse.append(label)
            if coarse:
                logger.warning(
                    f"Maritime entity '{entry.get('callsign', entity_id)}' ({entity_id}) "
                    f"initial_position {','.join(coarse)} has <4 decimal places "
                    f"(~110 m resolution). Use at least 4 dp for berth-specific placement."
                )

        entity = Entity(
            entity_id=entity_id,
            entity_type=entity_type,
            domain=domain,
            agency=agency,
            callsign=entry.get("callsign", entity_id),
            position=position,
            heading_deg=initial_heading,
            speed_knots=initial_speed,
            course_deg=initial_heading,
            status=EntityStatus.IDLE if entry.get("behavior") == "standby" else EntityStatus.ACTIVE,
            sidc=entry.get("sidc") or get_default_sidc(entity_type),
            metadata=metadata,
            initial_position=Position(
                latitude=pos.get("lat", 0.0),
                longitude=pos.get("lon", 0.0),
                altitude_m=pos.get("alt_m", 0.0),
            ),
            spawn_at=spawn_at,
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
            turn_tuple = type_def.get("turn")
            turn_params = TurnParams(*turn_tuple) if turn_tuple else None
            movement = WaypointMovement(waypoints, start, turn_params=turn_params)
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
                    domain=domain.value,
                )
                entity.speed_knots = sum(speed_range) / 2
            else:
                if patrol_area_id:
                    logger.warning(
                        f"Patrol area '{patrol_area_id}' not found for {entity_id}. "
                        f"Available: {list(self._zones.keys())}"
                    )
        # standby: no movement (entity stays in place)

        # v2: entity with initial speed/heading but no waypoints — create drift movement
        if not movement and initial_speed > 0 and not embarked_on:
            from simulator.movement.escape import EscapeMovement
            movement = EscapeMovement(
                start_lat=pos.get("lat", 0.0),
                start_lon=pos.get("lon", 0.0),
                bearing_deg=initial_heading,
                speed_knots=initial_speed,
                start_time=start,
                alt_m=pos.get("alt_m", 0.0),
            )

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
                    domain=domain.value,
                )

                # Set initial position from first patrol waypoint
                state = movement.get_state(start)
                entity.position = Position(state.lat, state.lon)
                entity.initial_position = Position(state.lat, state.lon)

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
                    initial_position=Position(point.y, point.x),
                )

                if len(waypoints) >= 1:
                    turn_tuple = type_def.get("turn")
                    turn_params = TurnParams(*turn_tuple) if turn_tuple else None
                    movement = WaypointMovement(waypoints, start, turn_params=turn_params)
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
            # time is optional for dependency-based events
            time_str = entry.get("time")
            time_offset = _parse_time_offset(time_str) if time_str else None

            event = ScenarioEvent(
                time_offset=time_offset,
                event_type=entry.get("type", "INFO"),
                description=entry.get("description", ""),
                id=entry.get("id"),
                after=entry.get("after"),
                severity=entry.get("severity", "INFO"),
                actionee=entry.get("actionee"),
                targets=entry.get("targets"),
                action=entry.get("action"),
                target=entry.get("target"),
                destination=entry.get("destination"),
                area=entry.get("area"),
                position=entry.get("position"),
                alert_agencies=entry.get("alert_agencies", []),
                source=entry.get("source"),
                on_initiate=entry.get("on_initiate"),
                on_complete=entry.get("on_complete"),
                on_complete_action=entry.get("on_complete_action"),
                metadata={
                    k: v for k, v in entry.items()
                    if k not in {
                        "time", "type", "description", "severity", "actionee",
                        "targets", "action", "target", "destination",
                        "area", "position", "alert_agencies", "source",
                        "on_initiate", "on_complete", "on_complete_action",
                        "id", "after",
                    }
                },
            )
            events.append(event)

        # Sort time-based events first (by time), dependency events after
        events.sort(key=lambda e: (
            e.time_offset if e.time_offset is not None else timedelta(days=999)
        ))
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
            for field_name in ("actionee", "target"):
                ref = evt.get(field_name)
                if ref and ref not in entity_ids:
                    errors.append(
                        f"Event at {evt['time']} references entity "
                        f"'{ref}' (via {field_name}) which is not in scenario_entities"
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
