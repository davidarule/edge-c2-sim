#!/usr/bin/env python3
"""
ais_to_scenario.py — Convert real AIS data to Edge C2 simulator background entities.

Reads sim_seed CSV (position reports) and vessel_catalogue CSV (static metadata),
groups tracks by MMSI, simplifies waypoints using heading/speed change detection,
maps AIS ship_type_code to Edge C2 entity types, and outputs YAML in the exact
scenario_entities format used by the simulator's ScenarioLoader.

Usage:
    python scripts/ais_to_scenario.py \\
        --seed    scripts/ais_data/sim_seed_20260407_112735.csv \\
        --catalog scripts/ais_data/vessel_catalogue_20260407_112735.csv \\
        --output  config/scenarios/ais_background_malacca.yaml \\
        --bbox    "1.0,98.0,7.0,105.0" \\
        --min-positions 3 \\
        --max-vessels 200 \\
        --scenario-duration 60

Bounding box format: "lat_min,lon_min,lat_max,lon_max"

Geographic presets (pass --preset instead of --bbox):
    malacca      1.0,98.5,7.0,103.0
    singapore    1.0,103.0,2.0,105.0
    scs_west     1.0,103.0,10.0,115.0
    java_sea    -9.0,105.0,1.0,116.0
    celebes      1.0,116.0,8.0,127.0
    all         -10.0,95.0,22.0,130.0

Output format:
    The script outputs a standalone YAML fragment containing a list of
    scenario_entities ready to be pasted into or included by an existing
    scenario file. Each entity follows the exact schema from loader.py:

        - id: "AIS-<mmsi>"
          type: CIVILIAN_CARGO          # mapped from ship_type_code
          callsign: "MV VESSEL NAME"
          initial_position: { lat: X.XXX, lon: Y.YYY }
          waypoints:
            - { lat: X.XXX, lon: Y.YYY, speed: 12.3, time: "00:00" }
            ...
          metadata:
            skip_terrain_check: false   # terrain validator uses Natural Earth 10m
            ais_active: true
            mmsi: "123456789"
            imo_number: "1234567"
            call_sign: "ABCD1"
            flag: "MYS"
            vessel_type: "Cargo"
            length_m: 185
            beam_m: 28
            draught_m: 9.5
            nav_status: "Under Way Using Engine"
            destination_declared: "Port Klang"
            source: "AIS_REAL"
"""

import argparse
import csv
import math
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import yaml

# ── AIS ship_type_code → Edge C2 entity type ─────────────────────────────────
# Based on ITU-R M.1371 Table 50 (AIS ship type codes) mapped to
# ENTITY_TYPES in simulator/scenario/loader.py
#
# Key references:
#   20–29: Wing in Ground
#   30–39: Fishing
#   40–49: High speed craft
#   50:    Pilot vessel
#   51:    SAR vessel
#   52:    Tug
#   53:    Port tender
#   55:    Law enforcement
#   60–69: Passenger
#   70–79: Cargo
#   80–89: Tanker
#   90–99: Other

AIS_TYPE_MAP: dict[int, str] = {
    # Fishing (30-39)
    **{code: "CIVILIAN_FISHING" for code in range(30, 40)},

    # High speed craft (40-49) → civilian boat
    **{code: "CIVILIAN_BOAT" for code in range(40, 50)},

    # Pilot, SAR, Tug, Port Tender (50-54, 56-57) → civilian boat
    50: "CIVILIAN_BOAT",   # Pilot vessel
    51: "CIVILIAN_BOAT",   # SAR
    52: "CIVILIAN_BOAT",   # Tug
    53: "CIVILIAN_BOAT",   # Port tender
    54: "CIVILIAN_BOAT",   # Anti-pollution
    56: "CIVILIAN_BOAT",   # Spare
    57: "CIVILIAN_BOAT",   # Spare
    58: "CIVILIAN_BOAT",   # Medical transport
    59: "CIVILIAN_BOAT",   # Resolution 18

    # Passenger (60-69)
    **{code: "CIVILIAN_PASSENGER" for code in range(60, 70)},

    # Cargo (70-79)
    **{code: "CIVILIAN_CARGO" for code in range(70, 80)},

    # Tanker (80-89) — subdivided by size in _map_entity_type()
    **{code: "CIVILIAN_TANKER" for code in range(80, 90)},

    # Other (90-99) → civilian boat
    **{code: "CIVILIAN_BOAT" for code in range(90, 100)},
}

# Nav status codes → human-readable
NAV_STATUS_TEXT: dict[int, str] = {
    0: "Under Way Using Engine",
    1: "At Anchor",
    2: "Not Under Command",
    3: "Restricted Manoeuvrability",
    4: "Constrained by Draught",
    5: "Moored",
    6: "Aground",
    7: "Engaged in Fishing",
    8: "Under Way Sailing",
    15: "Not Defined",
}

# Geographic bounding box presets
BBOX_PRESETS: dict[str, tuple[float, float, float, float]] = {
    "malacca":   (1.0,  98.5,  7.0,  103.0),
    "singapore": (1.0,  103.0, 2.0,  105.0),
    "scs_west":  (1.0,  103.0, 10.0, 115.0),
    "java_sea":  (-9.0, 105.0, 1.0,  116.0),
    "celebes":   (1.0,  116.0, 8.0,  127.0),
    "all":       (-10.0, 95.0, 22.0, 130.0),
}


# ── Vessel track record ───────────────────────────────────────────────────────

class PositionReport:
    __slots__ = ("ts", "lat", "lon", "sog", "cog", "nav_status")

    def __init__(self, ts: datetime, lat: float, lon: float,
                 sog: float, cog: float, nav_status: int):
        self.ts = ts
        self.lat = lat
        self.lon = lon
        self.sog = sog
        self.cog = cog
        self.nav_status = nav_status


class VesselTrack:
    def __init__(self, mmsi: str):
        self.mmsi = mmsi
        self.positions: list[PositionReport] = []
        # Static data from catalogue or seed
        self.ship_name: str = ""
        self.imo_number: str = ""
        self.call_sign: str = ""
        self.ship_type_code: int = 0
        self.ship_category: str = ""
        self.length_m: Optional[float] = None
        self.beam_m: Optional[float] = None
        self.draught_m: Optional[float] = None
        self.destination: str = ""
        self.flag: str = ""


# ── Geometry helpers ──────────────────────────────────────────────────────────

def haversine_nm(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in nautical miles."""
    R = 3440.065  # Earth radius in nm
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Initial bearing in degrees (0-360)."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dlam = math.radians(lon2 - lon1)
    x = math.sin(dlam) * math.cos(phi2)
    y = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(dlam)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def angle_diff(a: float, b: float) -> float:
    """Smallest absolute difference between two bearings (0-180)."""
    diff = abs(a - b) % 360
    return diff if diff <= 180 else 360 - diff


# ── Track simplification ──────────────────────────────────────────────────────

def simplify_track(
    positions: list[PositionReport],
    heading_threshold_deg: float = 15.0,
    speed_threshold_kn: float = 2.0,
    min_interval_sec: float = 60.0,
    max_waypoints: int = 30,
) -> list[PositionReport]:
    """
    Reduce AIS position reports to key waypoints using course/speed change detection.

    Keeps a position if:
    - It is the first or last point
    - The heading has changed by more than heading_threshold_deg since the last kept point
    - The speed has changed by more than speed_threshold_kn since the last kept point
    - More than max_interval_sec has passed since the last kept point (sparse data guard)

    Falls back to uniform resampling if result still exceeds max_waypoints.
    """
    if len(positions) <= 2:
        return list(positions)

    kept = [positions[0]]
    last_cog = positions[0].cog
    last_sog = positions[0].sog

    for pos in positions[1:-1]:
        dt = (pos.ts - kept[-1].ts).total_seconds()
        if dt < min_interval_sec:
            continue

        cog_change = angle_diff(pos.cog, last_cog)
        sog_change = abs(pos.sog - last_sog)
        time_gap = (pos.ts - kept[-1].ts).total_seconds() > 1800  # 30min gap

        if cog_change >= heading_threshold_deg or sog_change >= speed_threshold_kn or time_gap:
            kept.append(pos)
            last_cog = pos.cog
            last_sog = pos.sog

    kept.append(positions[-1])

    # Uniform resample if still too many
    if len(kept) > max_waypoints:
        step = len(kept) / max_waypoints
        kept = [kept[int(i * step)] for i in range(max_waypoints - 1)] + [kept[-1]]

    return kept


# ── Entity type mapping ───────────────────────────────────────────────────────

def map_entity_type(ship_type_code: int, length_m: Optional[float]) -> str:
    """
    Map AIS ship_type_code + vessel dimensions to Edge C2 entity type.

    Tanker subdivision:
      CIVILIAN_TANKER_VLCC  — length_m >= 250 (VLCC/ULCC)
      CIVILIAN_TANKER       — smaller tankers, product carriers
    """
    base = AIS_TYPE_MAP.get(ship_type_code, "CIVILIAN_CARGO")

    if base == "CIVILIAN_TANKER" and length_m and length_m >= 250:
        return "CIVILIAN_TANKER_VLCC"

    return base


# ── Flag inference from MMSI ──────────────────────────────────────────────────

# MID (Maritime Identification Digits) prefix → flag state
# Subset covering Southeast Asia and major maritime nations
MID_TO_FLAG: dict[str, str] = {
    "525": "IDN", "533": "MYS", "563": "SGP", "567": "THA",
    "574": "VNM", "477": "HKG", "412": "CHN", "413": "CHN",
    "414": "CHN", "338": "USA", "235": "GBR", "636": "LBR",
    "255": "PRT", "229": "MLT", "341": "ATG", "370": "PAN",
    "440": "KOR", "441": "KOR", "431": "JPN", "432": "JPN",
    "548": "PHL", "578": "VNM", "503": "AUS",
}


def mmsi_to_flag(mmsi: str) -> str:
    """Infer flag state from MMSI MID prefix (first 3 digits)."""
    for length in [3]:
        prefix = mmsi[:length]
        if prefix in MID_TO_FLAG:
            return MID_TO_FLAG[prefix]
    return ""


# ── CSV readers ───────────────────────────────────────────────────────────────

def parse_timestamp(ts_str: str) -> Optional[datetime]:
    """Parse ISO timestamp — handle multiple formats."""
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ",
                "%Y-%m-%d %H:%M:%S+00:00", "%Y-%m-%d %H:%M:%S"):
        try:
            dt = datetime.strptime(ts_str.strip(), fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    return None


def load_seed_csv(path: Path) -> dict[str, VesselTrack]:
    """Load position reports from sim_seed CSV."""
    tracks: dict[str, VesselTrack] = {}

    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            mmsi = row.get("mmsi", "").strip()
            if not mmsi:
                continue

            ts = parse_timestamp(row.get("timestamp_utc", ""))
            if ts is None:
                continue

            try:
                lat = float(row["latitude"])
                lon = float(row["longitude"])
            except (ValueError, KeyError):
                continue

            # Skip obviously bad positions
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                continue
            if lat == 0.0 and lon == 0.0:
                continue

            sog = _safe_float(row.get("sog_knots", "0"), 0.0)
            cog = _safe_float(row.get("cog_degrees", "0"), 0.0)
            nav_status = _safe_int(row.get("nav_status_code", "0"), 0)

            if mmsi not in tracks:
                track = VesselTrack(mmsi)
                track.ship_name = row.get("ship_name", "").strip()
                track.imo_number = row.get("imo_number", "").strip()
                track.call_sign = row.get("call_sign", "").strip()
                track.ship_type_code = _safe_int(row.get("ship_type_code", "0"), 0)
                track.ship_category = row.get("ship_category", "").strip()
                track.length_m = _safe_float(row.get("length_m"), None)
                track.beam_m = _safe_float(row.get("beam_m"), None)
                track.draught_m = _safe_float(row.get("draught_m"), None)
                track.destination = row.get("destination", "").strip()
                track.flag = mmsi_to_flag(mmsi)
                tracks[mmsi] = track

            tracks[mmsi].positions.append(
                PositionReport(ts, lat, lon, sog, cog, nav_status)
            )

    # Sort positions by timestamp
    for track in tracks.values():
        track.positions.sort(key=lambda p: p.ts)

    return tracks


def load_catalogue_csv(path: Path, tracks: dict[str, VesselTrack]) -> None:
    """Merge static vessel data from catalogue CSV into tracks."""
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            mmsi = row.get("mmsi", "").strip()
            if mmsi not in tracks:
                continue
            track = tracks[mmsi]
            # Catalogue overrides seed static data where present
            if row.get("ship_name", "").strip():
                track.ship_name = row["ship_name"].strip()
            if row.get("imo_number", "").strip():
                track.imo_number = row["imo_number"].strip()
            if row.get("call_sign", "").strip():
                track.call_sign = row["call_sign"].strip()
            if row.get("ship_type_code", "").strip():
                track.ship_type_code = _safe_int(row["ship_type_code"], track.ship_type_code)
            if row.get("length_m", "").strip():
                v = _safe_float(row["length_m"], None)
                if v:
                    track.length_m = v
            if row.get("beam_m", "").strip():
                v = _safe_float(row["beam_m"], None)
                if v:
                    track.beam_m = v
            if row.get("draught_m", "").strip():
                v = _safe_float(row["draught_m"], None)
                if v:
                    track.draught_m = v
            if row.get("destination", "").strip():
                track.destination = row["destination"].strip()


def _safe_float(val, default):
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _safe_int(val, default):
    try:
        return int(float(val))
    except (TypeError, ValueError):
        return default


# ── Bounding box filter ───────────────────────────────────────────────────────

def in_bbox(lat: float, lon: float,
            lat_min: float, lon_min: float,
            lat_max: float, lon_max: float) -> bool:
    return lat_min <= lat <= lat_max and lon_min <= lon <= lon_max


def filter_track_to_bbox(
    positions: list[PositionReport],
    lat_min: float, lon_min: float,
    lat_max: float, lon_max: float,
) -> list[PositionReport]:
    """Keep positions inside bbox, but include one point before/after for entry/exit."""
    inside = []
    for i, pos in enumerate(positions):
        if in_bbox(pos.lat, pos.lon, lat_min, lon_min, lat_max, lon_max):
            # Include predecessor if not already included (track entry)
            if i > 0 and (not inside or inside[-1] is not positions[i - 1]):
                inside.append(positions[i - 1])
            inside.append(pos)
        elif inside and inside[-1] is positions[i - 1]:
            # One point after exit for smooth track departure
            inside.append(pos)
            break
    return inside


# ── YAML entity builder ───────────────────────────────────────────────────────

def build_entity(
    track: VesselTrack,
    simplified: list[PositionReport],
    scenario_start: datetime,
    entity_index: int,
) -> dict:
    """Build a scenario_entity dict matching loader.py's _parse_scenario_entity()."""

    entity_type = map_entity_type(track.ship_type_code, track.length_m)

    # Build callsign: prefer real name, fall back to MMSI
    raw_name = track.ship_name.strip()
    if raw_name and raw_name not in ("", "0", "UNKNOWN", "N/A"):
        # Prefix by vessel category if not already prefixed
        if entity_type in ("CIVILIAN_TANKER", "CIVILIAN_TANKER_VLCC"):
            prefix = "MT" if not raw_name.upper().startswith("MT") else ""
        elif entity_type == "CIVILIAN_PASSENGER":
            prefix = "MV" if not raw_name.upper().startswith(("MV", "RV", "MS")) else ""
        elif entity_type == "CIVILIAN_FISHING":
            prefix = "FB" if not raw_name.upper().startswith(("FB", "KM", "KT")) else ""
        else:
            prefix = "MV" if not raw_name.upper().startswith(("MV", "MT", "MS")) else ""
        callsign = f"{prefix} {raw_name}".strip() if prefix else raw_name
    else:
        callsign = f"AIS-{track.mmsi}"

    # Waypoints — time offset from scenario start
    first_ts = simplified[0].ts
    waypoints = []
    for pos in simplified:
        elapsed = pos.ts - first_ts
        total_minutes = int(elapsed.total_seconds() // 60)
        hours = total_minutes // 60
        minutes = total_minutes % 60
        time_str = f"{hours:02d}:{minutes:02d}"

        waypoints.append({
            "lat": round(pos.lat, 5),
            "lon": round(pos.lon, 5),
            "speed": round(max(0.0, pos.sog), 1),
            "time": time_str,
        })

    # Nav status
    first_nav = simplified[0].nav_status
    nav_text = NAV_STATUS_TEXT.get(first_nav, "Under Way Using Engine")

    # Metadata — use per-vessel AIS dimensions as ground truth
    metadata: dict = {
        "skip_terrain_check": False,   # terrain validator uses Natural Earth 10m
        "ais_active": True,
        "mmsi": track.mmsi,
        "source": "AIS_REAL",
        "nav_status": nav_text,
        "nav_status_code": first_nav,
    }

    if track.ship_name:
        metadata["vessel_name"] = track.ship_name

    if track.imo_number and track.imo_number not in ("0", ""):
        metadata["imo_number"] = track.imo_number

    if track.call_sign and track.call_sign not in ("0", ""):
        metadata["call_sign"] = track.call_sign

    if track.flag:
        metadata["flag"] = track.flag

    if track.ship_category:
        metadata["vessel_type"] = track.ship_category
    elif track.ship_type_code:
        metadata["ship_type_code"] = track.ship_type_code

    # Per-vessel dimensions from AIS data (ground truth — NOT type defaults)
    if track.length_m and track.length_m > 0:
        metadata["length_m"] = round(track.length_m, 1)
    if track.beam_m and track.beam_m > 0:
        metadata["beam_m"] = round(track.beam_m, 1)
    if track.draught_m and track.draught_m > 0:
        metadata["draught_m"] = round(track.draught_m, 1)

    if track.destination and track.destination not in ("0", ""):
        metadata["destination_declared"] = track.destination

    return {
        "id": f"AIS-{track.mmsi}",
        "type": entity_type,
        "callsign": callsign,
        "initial_position": {
            "lat": round(simplified[0].lat, 5),
            "lon": round(simplified[0].lon, 5),
        },
        "waypoints": waypoints,
        "metadata": metadata,
    }


# ── YAML serializer (clean output matching scenario files) ────────────────────

class _Literal(str):
    pass


def _literal_representer(dumper, data):
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")


def _float_representer(dumper, data):
    # Avoid scientific notation for small floats
    return dumper.represent_scalar("tag:yaml.org,2002:float", f"{data:.5g}")


def build_yaml_output(
    entities: list[dict],
    bbox: tuple,
    seed_path: str,
    catalogue_path: str,
    generated_at: str,
) -> str:
    """Build the complete YAML output as a string."""
    lat_min, lon_min, lat_max, lon_max = bbox

    header = f"""# Edge C2 Simulator — AIS Background Traffic
# Generated: {generated_at}
# Source: {Path(seed_path).name}
# Catalogue: {Path(catalogue_path).name}
# Bounding box: {lat_min}°N–{lat_max}°N, {lon_min}°E–{lon_max}°E
# Entities: {len(entities)}
#
# Usage — paste into scenario file under scenario_entities:
#   scenario_entities:
#     - !include ais_background_malacca.yaml   # if loader supports includes
#   OR copy the list directly into scenario_entities.
#
# All entities:
#   - type mapped from AIS ship_type_code (ITU-R M.1371 Table 50)
#   - waypoints simplified (heading/speed change detection, max 30 points)
#   - dimensions from per-vessel AIS data (not type defaults)
#   - skip_terrain_check: false (Natural Earth 10m validator)
#   - source: AIS_REAL tagged in metadata

"""

    # Dump entities list
    entities_yaml = yaml.dump(
        entities,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
        width=120,
    )

    return header + entities_yaml


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Convert AIS data to Edge C2 background traffic entities"
    )
    parser.add_argument("--seed", required=True,
                        help="Path to sim_seed CSV (position reports)")
    parser.add_argument("--catalog", required=True,
                        help="Path to vessel_catalogue CSV (static metadata)")
    parser.add_argument("--output", required=True,
                        help="Output YAML file path")
    parser.add_argument("--bbox",
                        help="Bounding box: lat_min,lon_min,lat_max,lon_max")
    parser.add_argument("--preset",
                        choices=list(BBOX_PRESETS.keys()),
                        help="Named geographic preset (overrides --bbox)")
    parser.add_argument("--min-positions", type=int, default=3,
                        help="Minimum AIS reports to include a vessel (default: 3)")
    parser.add_argument("--max-vessels", type=int, default=500,
                        help="Maximum vessels to output (default: 500)")
    parser.add_argument("--scenario-duration", type=int, default=60,
                        help="Scenario duration in minutes for time offset calculation (default: 60)")
    parser.add_argument("--heading-threshold", type=float, default=15.0,
                        help="Heading change threshold in degrees for waypoint inclusion (default: 15)")
    parser.add_argument("--speed-threshold", type=float, default=2.0,
                        help="Speed change threshold in knots for waypoint inclusion (default: 2)")
    parser.add_argument("--max-waypoints", type=int, default=30,
                        help="Maximum waypoints per vessel track (default: 30)")
    parser.add_argument("--exclude-anchored", action="store_true",
                        help="Exclude vessels with nav_status 1 (At Anchor) or 5 (Moored)")
    parser.add_argument("--exclude-fishing", action="store_true",
                        help="Exclude fishing vessels (ship_type_code 30-39)")
    parser.add_argument("--types", nargs="+",
                        help="Only include these entity types (e.g. CIVILIAN_CARGO CIVILIAN_TANKER)")

    args = parser.parse_args()

    # Resolve bounding box
    if args.preset:
        bbox = BBOX_PRESETS[args.preset]
    elif args.bbox:
        try:
            parts = [float(x) for x in args.bbox.split(",")]
            if len(parts) != 4:
                raise ValueError
            bbox = tuple(parts)
        except ValueError:
            print("ERROR: --bbox must be lat_min,lon_min,lat_max,lon_max", file=sys.stderr)
            sys.exit(1)
    else:
        bbox = BBOX_PRESETS["all"]

    lat_min, lon_min, lat_max, lon_max = bbox
    print(f"Bounding box: {lat_min}°–{lat_max}°N, {lon_min}°–{lon_max}°E")

    # Load data
    seed_path = Path(args.seed)
    catalog_path = Path(args.catalog)

    print(f"Loading seed: {seed_path}")
    tracks = load_seed_csv(seed_path)
    print(f"  Loaded {len(tracks)} unique vessels from seed")

    print(f"Loading catalogue: {catalog_path}")
    load_catalogue_csv(catalog_path, tracks)

    # Filter, simplify, build entities
    entities = []
    stats = defaultdict(int)

    for mmsi, track in tracks.items():
        # Filter to bbox
        bbox_positions = filter_track_to_bbox(
            track.positions, lat_min, lon_min, lat_max, lon_max
        )
        if len(bbox_positions) < args.min_positions:
            stats["too_few_positions"] += 1
            continue

        # Exclude anchored/moored if requested
        if args.exclude_anchored:
            first_nav = bbox_positions[0].nav_status
            if first_nav in (1, 5):
                stats["excluded_stationary"] += 1
                continue

        # Exclude fishing if requested
        if args.exclude_fishing and 30 <= track.ship_type_code <= 39:
            stats["excluded_fishing"] += 1
            continue

        # Map entity type
        entity_type = map_entity_type(track.ship_type_code, track.length_m)

        # Filter by type if requested
        if args.types and entity_type not in args.types:
            stats["excluded_type"] += 1
            continue

        # Simplify track
        simplified = simplify_track(
            bbox_positions,
            heading_threshold_deg=args.heading_threshold,
            speed_threshold_kn=args.speed_threshold,
            max_waypoints=args.max_waypoints,
        )

        if len(simplified) < 2:
            stats["too_few_simplified"] += 1
            continue

        # Build entity dict
        entity = build_entity(
            track, simplified,
            scenario_start=datetime(2026, 4, 15, 8, 0, 0, tzinfo=timezone.utc),
            entity_index=len(entities),
        )
        entities.append(entity)
        stats[entity_type] += 1

        if len(entities) >= args.max_vessels:
            print(f"  Reached max-vessels limit ({args.max_vessels})")
            break

    print(f"\n=== Entity type breakdown ===")
    for key in sorted(stats):
        print(f"  {key}: {stats[key]}")
    print(f"  TOTAL OUTPUT: {len(entities)} entities\n")

    # Build output YAML
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    output_yaml = build_yaml_output(
        entities, bbox,
        str(seed_path), str(catalog_path), generated_at
    )

    # Write output
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(output_yaml)

    print(f"Written: {out_path}")
    print(f"  {len(entities)} entities")

    # Quick validation summary
    type_counts = defaultdict(int)
    for e in entities:
        type_counts[e["type"]] += 1
    print("\nEntity types in output:")
    for t, c in sorted(type_counts.items(), key=lambda x: -x[1]):
        print(f"  {t}: {c}")


if __name__ == "__main__":
    main()
