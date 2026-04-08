#!/usr/bin/env python3
"""
ais_db_to_scenario.py — Convert Datalastic AIS database to Edge C2 background entities.

Reads from the SQLite database (ais_capture.db) produced by the Datalastic API capture
pipeline, groups positions by MMSI, simplifies tracks, maps vessel types, resolves
destination ports, and outputs YAML in the exact scenario_entities format.

Usage:
    python scripts/ais_db_to_scenario.py \
        --db      scripts/ais_data/ais_capture.db \
        --output  config/scenarios/ais_background_malacca.yaml \
        --preset  malacca \
        --max-vessels 300

    python scripts/ais_db_to_scenario.py \
        --db      scripts/ais_data/ais_capture.db \
        --output  config/scenarios/ais_background_singapore.yaml \
        --bbox    "1.1,103.5,1.5,104.2" \
        --max-vessels 200

Bounding box format: "lat_min,lon_min,lat_max,lon_max"

Geographic presets (--preset):
    malacca      1.0,98.5,7.0,103.0
    singapore    1.1,103.5,1.5,104.2
    scs_west     1.0,103.0,10.0,115.0
    java_sea    -9.0,105.0,1.0,116.0
    celebes      1.0,116.0,8.0,127.0
    sulu_sea     4.5,117.0,8.0,123.0
    all         -12.0,95.0,25.0,141.0
"""

import argparse
import math
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import yaml


# ── Datalastic type/type_specific → Edge C2 entity type ─────────────────────
# Maps the Datalastic vessel classification to ENTITY_TYPES in loader.py

DATALASTIC_TYPE_MAP: dict[str, str] = {
    # Cargo variants
    "Cargo": "CIVILIAN_CARGO",
    "Cargo - Hazard A (Major)": "CIVILIAN_CARGO",
    "Cargo - Hazard B": "CIVILIAN_CARGO",
    "Cargo - Hazard C (Minor)": "CIVILIAN_CARGO",
    "Cargo - Hazard D (Recognizable)": "CIVILIAN_CARGO",
    # Tanker variants
    "Tanker": "CIVILIAN_TANKER",
    "Tanker - Hazard A (Major)": "CIVILIAN_TANKER",
    "Tanker - Hazard B": "CIVILIAN_TANKER",
    "Tanker - Hazard C (Minor)": "CIVILIAN_TANKER",
    "Tanker - Hazard D (Recognizable)": "CIVILIAN_TANKER",
    # Passenger
    "Passenger": "CIVILIAN_PASSENGER",
    # Fishing
    "Fishing": "CIVILIAN_FISHING",
    # Everything else → CIVILIAN_BOAT
    "Tug": "CIVILIAN_BOAT",
    "Pilot Vessel": "CIVILIAN_BOAT",
    "Pleasure Craft": "CIVILIAN_BOAT",
    "Sailing Vessel": "CIVILIAN_BOAT",
    "High Speed Craft": "CIVILIAN_BOAT",
    "Port Tender": "CIVILIAN_BOAT",
    "Dredger": "CIVILIAN_BOAT",
    "Dive Vessel": "CIVILIAN_BOAT",
    "Special Craft": "CIVILIAN_BOAT",
    "Other": "CIVILIAN_BOAT",
    "Law Enforce": "CIVILIAN_BOAT",
    "Military Ops": "CIVILIAN_BOAT",
    "Search and Rescue": "CIVILIAN_BOAT",
    "Anti-pollution": "CIVILIAN_BOAT",
    "Spare": "CIVILIAN_BOAT",
}

# Types to exclude (not real vessels)
EXCLUDE_TYPES = {
    "Manned VTS", "Navigation Aid",
}
EXCLUDE_PREFIXES = ("Beacon", "Light")

# Datalastic navigational_status text → nav status for metadata
NAV_STATUS_NORMALIZE: dict[str, str] = {
    "Under way using engine": "Under Way Using Engine",
    "At anchor": "At Anchor",
    "Moored": "Moored",
    "Not under command": "Not Under Command",
    "Restricted manoeuverability": "Restricted Manoeuvrability",
    "Constrained by her draught": "Constrained by Draught",
    "Aground": "Aground",
    "Engaged in Fishing": "Engaged in Fishing",
    "Under way sailing": "Under Way Sailing",
    "Not defined": "Not Defined",
    "Towing astern": "Towing",
    "Pushing ahead/towing alongside": "Towing",
}

# ISO 2-letter → 3-letter country codes (SE Asia + major maritime flags)
ISO2_TO_ISO3: dict[str, str] = {
    "ID": "IDN", "SG": "SGP", "MY": "MYS", "TH": "THA", "VN": "VNM",
    "PH": "PHL", "BN": "BRN", "MM": "MMR", "KH": "KHM", "LA": "LAO",
    "CN": "CHN", "HK": "HKG", "TW": "TWN", "JP": "JPN", "KR": "KOR",
    "IN": "IND", "AU": "AUS", "NZ": "NZL",
    "PA": "PAN", "LR": "LBR", "MH": "MHL", "BS": "BHS", "MT": "MLT",
    "BZ": "BLZ", "MN": "MNG", "CY": "CYP", "BM": "BMU", "KY": "CYM",
    "GI": "GIB", "PT": "PRT", "DK": "DNK", "NO": "NOR", "SE": "SWE",
    "GB": "GBR", "US": "USA", "DE": "DEU", "NL": "NLD", "FR": "FRA",
    "IT": "ITA", "ES": "ESP", "GR": "GRC", "TR": "TUR", "RU": "RUS",
    "AE": "ARE", "SA": "SAU", "QA": "QAT", "KW": "KWT", "BH": "BHR",
    "AT": "AUT", "BE": "BEL", "IE": "IRL", "FI": "FIN",
}

# Geographic bounding box presets
BBOX_PRESETS: dict[str, tuple[float, float, float, float]] = {
    "malacca":   (1.0,  98.5,  7.0,  103.0),
    "singapore": (1.1,  103.5, 1.5,  104.2),
    "scs_west":  (1.0,  103.0, 10.0, 115.0),
    "java_sea":  (-9.0, 105.0, 1.0,  116.0),
    "celebes":   (1.0,  116.0, 8.0,  127.0),
    "sulu_sea":  (4.5,  117.0, 8.0,  123.0),
    "all":       (-12.0, 95.0, 25.0, 141.0),
}


# ── Data classes ─────────────────────────────────────────────────────────────

class PositionReport:
    __slots__ = ("ts", "lat", "lon", "sog", "cog", "heading", "nav_status",
                 "draught", "destination")

    def __init__(self, ts: datetime, lat: float, lon: float,
                 sog: float, cog: float, heading: float, nav_status: str,
                 draught: float, destination: str):
        self.ts = ts
        self.lat = lat
        self.lon = lon
        self.sog = sog
        self.cog = cog
        self.heading = heading
        self.nav_status = nav_status
        self.draught = draught
        self.destination = destination


class VesselInfo:
    def __init__(self, mmsi: str, name: str, callsign: str,
                 vessel_type: str, type_specific: str,
                 country_iso: str, length: float, breadth: float,
                 draught_avg: float, draught_max: float,
                 gross_tonnage: float, deadweight: float,
                 year_built: str, home_port: str):
        self.mmsi = mmsi
        self.name = name or ""
        self.callsign = callsign or ""
        self.vessel_type = vessel_type or ""
        self.type_specific = type_specific or ""
        self.country_iso = country_iso or ""
        self.length = length
        self.breadth = breadth
        self.draught_avg = draught_avg
        self.draught_max = draught_max
        self.gross_tonnage = gross_tonnage
        self.deadweight = deadweight
        self.year_built = year_built or ""
        self.home_port = home_port or ""


# ── Geometry helpers ──────────────────────────────────────────────────────────

def angle_diff(a: float, b: float) -> float:
    """Smallest absolute difference between two bearings (0-180)."""
    diff = abs(a - b) % 360
    return diff if diff <= 180 else 360 - diff


# ── Track simplification ────────────────────────────────────────────────────

def simplify_track(
    positions: list[PositionReport],
    heading_threshold_deg: float = 15.0,
    speed_threshold_kn: float = 2.0,
    min_interval_sec: float = 60.0,
    max_waypoints: int = 30,
) -> list[PositionReport]:
    """Reduce AIS position reports to key waypoints using course/speed change detection."""
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
        time_gap = dt > 1800  # 30min gap

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


# ── Entity type mapping ──────────────────────────────────────────────────────

def map_entity_type(vessel_type: str, type_specific: str,
                    length: Optional[float]) -> str:
    """Map Datalastic type/type_specific to Edge C2 entity type."""
    base = DATALASTIC_TYPE_MAP.get(vessel_type, "CIVILIAN_CARGO")

    # VLCC subdivision for tankers
    if base == "CIVILIAN_TANKER" and length and length >= 250:
        return "CIVILIAN_TANKER_VLCC"

    return base


def should_exclude_vessel(vessel_type: str, type_specific: str,
                          is_navaid: int) -> bool:
    """Return True if the vessel should be excluded."""
    if is_navaid:
        return True
    if vessel_type in EXCLUDE_TYPES:
        return True
    if type_specific and type_specific in EXCLUDE_TYPES:
        return True
    for prefix in EXCLUDE_PREFIXES:
        if vessel_type and vessel_type.startswith(prefix):
            return True
        if type_specific and type_specific.startswith(prefix):
            return True
    return False


# ── Database loading ─────────────────────────────────────────────────────────

def load_port_lookup(conn: sqlite3.Connection) -> dict[str, tuple[str, float, float]]:
    """Build UNLOCODE → (port_name, lat, lon) lookup from ports table."""
    cur = conn.cursor()
    lookup = {}
    for row in cur.execute(
        "SELECT unlocode, port_name, lat, lon FROM ports WHERE unlocode IS NOT NULL"
    ):
        unlocode, port_name, lat, lon = row
        if unlocode:
            lookup[unlocode.strip().upper()] = (port_name, lat, lon)
    return lookup


def resolve_destination(dest_raw: str, port_lookup: dict) -> tuple[str, Optional[tuple[float, float]]]:
    """Try to resolve a destination string to a port name and coordinates.

    AIS destination fields are free-text and messy. We try:
    1. Direct UNLOCODE match (e.g. "SGSIN", "SG SIN", "MYPKG")
    2. Partial match removing spaces/hyphens
    """
    if not dest_raw or dest_raw.strip() in ("", "0", "CLASS B", "VAR", "VARIABLE"):
        return "", None

    cleaned = dest_raw.strip().upper()

    # Direct match
    if cleaned in port_lookup:
        name, lat, lon = port_lookup[cleaned]
        return name, (lat, lon)

    # Remove spaces/hyphens and try (e.g. "SG SIN" → "SGSIN", "SG-TJP" → "SGTJP")
    compact = cleaned.replace(" ", "").replace("-", "")
    if compact in port_lookup:
        name, lat, lon = port_lookup[compact]
        return name, (lat, lon)

    # Try with country code prefix variants (e.g. "SGSIN" → look for "SG SIN" style)
    if len(compact) >= 4:
        with_space = compact[:2] + " " + compact[2:]
        if with_space in port_lookup:
            name, lat, lon = port_lookup[with_space]
            return name, (lat, lon)

    # Return raw destination if no match
    return dest_raw.strip(), None


def load_vessel_details(conn: sqlite3.Connection) -> dict[str, VesselInfo]:
    """Load vessel static data from vessel_details table."""
    cur = conn.cursor()
    vessels = {}
    for row in cur.execute("""
        SELECT mmsi, name, callsign, type, type_specific, country_iso,
               length, breadth, draught_avg, draught_max,
               gross_tonnage, deadweight, year_built, home_port, is_navaid
        FROM vessel_details
    """):
        mmsi = row[0]
        is_navaid = row[14]
        v_type = row[3] or ""
        v_type_specific = row[4] or ""

        if should_exclude_vessel(v_type, v_type_specific, is_navaid):
            continue

        vessels[mmsi] = VesselInfo(
            mmsi=mmsi,
            name=row[1] or "",
            callsign=row[2] or "",
            vessel_type=v_type,
            type_specific=v_type_specific,
            country_iso=row[5] or "",
            length=row[6] or 0.0,
            breadth=row[7] or 0.0,
            draught_avg=row[8] or 0.0,
            draught_max=row[9] or 0.0,
            gross_tonnage=row[10] or 0.0,
            deadweight=row[11] or 0.0,
            year_built=row[12] or "",
            home_port=row[13] or "",
        )
    return vessels


def load_positions(
    conn: sqlite3.Connection,
    vessel_set: set[str],
    bbox: tuple[float, float, float, float],
) -> dict[str, list[PositionReport]]:
    """Load position reports from database, filtered by vessel set and bbox."""
    lat_min, lon_min, lat_max, lon_max = bbox
    cur = conn.cursor()

    tracks: dict[str, list[PositionReport]] = defaultdict(list)

    for row in cur.execute("""
        SELECT mmsi, timestamp_utc, lat, lon, speed, course, heading,
               navigational_status, draught, destination
        FROM positions
        WHERE lat BETWEEN ? AND ?
          AND lon BETWEEN ? AND ?
        ORDER BY mmsi, timestamp_utc
    """, (lat_min, lat_max, lon_min, lon_max)):
        mmsi = row[0]
        if mmsi not in vessel_set:
            continue

        ts_str = row[1]
        ts = _parse_timestamp(ts_str)
        if ts is None:
            continue

        lat, lon = row[2], row[3]
        if lat == 0.0 and lon == 0.0:
            continue

        sog = row[4] or 0.0
        cog = row[5] or 0.0
        heading = row[6] or cog  # fall back to COG if heading missing
        nav_status = row[7] or ""
        draught = row[8] or 0.0
        destination = row[9] or ""

        tracks[mmsi].append(PositionReport(
            ts=ts, lat=lat, lon=lon, sog=sog, cog=cog,
            heading=heading, nav_status=nav_status,
            draught=draught, destination=destination,
        ))

    return dict(tracks)


def _parse_timestamp(ts_str: str) -> Optional[datetime]:
    """Parse ISO timestamp from database."""
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ",
                "%Y-%m-%d %H:%M:%S+00:00", "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S.%fZ"):
        try:
            dt = datetime.strptime(ts_str.strip(), fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    return None


# ── Entity builder ───────────────────────────────────────────────────────────

def build_entity(
    vessel: VesselInfo,
    positions: list[PositionReport],
    simplified: list[PositionReport],
    port_lookup: dict,
) -> dict:
    """Build a scenario_entity dict matching loader.py's _parse_scenario_entity()."""

    entity_type = map_entity_type(vessel.vessel_type, vessel.type_specific,
                                  vessel.length)

    # Build callsign: prefer real name, fall back to MMSI
    raw_name = vessel.name.strip()
    if raw_name and raw_name not in ("", "0", "UNKNOWN", "N/A"):
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
        callsign = f"AIS-{vessel.mmsi}"

    # Waypoints — time offset from first position
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

    # Nav status from first position
    nav_raw = simplified[0].nav_status
    nav_text = NAV_STATUS_NORMALIZE.get(nav_raw, nav_raw or "Under Way Using Engine")

    # Resolve destination
    dest_raw = ""
    for pos in positions:
        if pos.destination and pos.destination.strip() not in ("", "0"):
            dest_raw = pos.destination.strip()
            break
    dest_name, dest_coords = resolve_destination(dest_raw, port_lookup)

    # Flag: convert 2-letter to 3-letter
    flag = ISO2_TO_ISO3.get(vessel.country_iso, vessel.country_iso)

    # Metadata — skip_terrain_check: true because these are real AIS positions;
    # coastline imprecision in Natural Earth 10m causes false on-land detections
    # for vessels in ports/harbours/anchorages.
    metadata: dict = {
        "skip_terrain_check": True,
        "ais_active": True,
        "mmsi": vessel.mmsi,
        "source": "AIS_REAL",
        "nav_status": nav_text,
    }

    if vessel.name:
        metadata["vessel_name"] = vessel.name
    if vessel.callsign:
        metadata["call_sign"] = vessel.callsign
    if flag:
        metadata["flag"] = flag

    # Vessel type description
    if vessel.type_specific and vessel.type_specific != vessel.vessel_type:
        metadata["vessel_type"] = vessel.type_specific
    elif vessel.vessel_type:
        metadata["vessel_type"] = vessel.vessel_type

    # Per-vessel dimensions from AIS data (ground truth)
    if vessel.length and vessel.length > 0:
        metadata["length_m"] = round(vessel.length, 1)
    if vessel.breadth and vessel.breadth > 0:
        metadata["beam_m"] = round(vessel.breadth, 1)

    # Best draught: prefer per-position, then avg, then max
    draught = 0.0
    for pos in positions:
        if pos.draught and pos.draught > 0:
            draught = pos.draught
            break
    if not draught and vessel.draught_avg and vessel.draught_avg > 0:
        draught = vessel.draught_avg
    if not draught and vessel.draught_max and vessel.draught_max > 0:
        draught = vessel.draught_max
    if draught > 0:
        metadata["draught_m"] = round(draught, 1)

    if vessel.gross_tonnage and vessel.gross_tonnage > 0:
        metadata["gross_tonnage"] = round(vessel.gross_tonnage)
    if vessel.deadweight and vessel.deadweight > 0:
        metadata["deadweight"] = round(vessel.deadweight)
    if vessel.year_built:
        metadata["year_built"] = vessel.year_built

    if dest_name:
        metadata["destination_declared"] = dest_name
    if dest_coords:
        metadata["destination_lat"] = round(dest_coords[0], 5)
        metadata["destination_lon"] = round(dest_coords[1], 5)

    return {
        "id": f"AIS-{vessel.mmsi}",
        "type": entity_type,
        "callsign": callsign,
        "initial_position": {
            "lat": round(simplified[0].lat, 5),
            "lon": round(simplified[0].lon, 5),
        },
        "waypoints": waypoints,
        "metadata": metadata,
    }


# ── YAML output ──────────────────────────────────────────────────────────────

def build_yaml_output(
    entities: list[dict],
    bbox: tuple,
    db_path: str,
    stats: dict,
    generated_at: str,
) -> str:
    """Build the complete YAML output."""
    lat_min, lon_min, lat_max, lon_max = bbox

    # Type summary for header
    type_counts = defaultdict(int)
    moving_count = 0
    stationary_count = 0
    for e in entities:
        type_counts[e["type"]] += 1
        nav = e["metadata"].get("nav_status", "")
        if nav in ("Moored", "At Anchor"):
            stationary_count += 1
        else:
            moving_count += 1

    type_lines = "\n".join(
        f"#   {t}: {c}" for t, c in sorted(type_counts.items(), key=lambda x: -x[1])
    )

    header = f"""# Edge C2 Simulator — AIS Background Traffic (Datalastic)
# Generated: {generated_at}
# Source: {Path(db_path).name}
# Bounding box: {lat_min}°N–{lat_max}°N, {lon_min}°E–{lon_max}°E
# Entities: {len(entities)} ({moving_count} moving, {stationary_count} stationary)
#
# Entity type breakdown:
{type_lines}
#
# Usage — include in scenario file under scenario_entities:
#   scenario_entities:
#     - !include ais_background.yaml
#   OR copy the list directly into scenario_entities.
#
# All entities have skip_terrain_check: false and source: AIS_REAL

"""

    entities_yaml = yaml.dump(
        entities,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
        width=120,
    )

    return header + entities_yaml


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Convert Datalastic AIS database to Edge C2 background traffic"
    )
    parser.add_argument("--db", default="scripts/ais_data/ais_capture.db",
                        help="Path to SQLite database (default: scripts/ais_data/ais_capture.db)")
    parser.add_argument("--output", required=True,
                        help="Output YAML file path")
    parser.add_argument("--bbox",
                        help="Bounding box: lat_min,lon_min,lat_max,lon_max")
    parser.add_argument("--preset",
                        choices=list(BBOX_PRESETS.keys()),
                        help="Named geographic preset (overrides --bbox)")
    parser.add_argument("--min-positions", type=int, default=3,
                        help="Minimum position reports to include a vessel (default: 3)")
    parser.add_argument("--max-vessels", type=int, default=500,
                        help="Maximum vessels to output (default: 500)")
    parser.add_argument("--heading-threshold", type=float, default=15.0,
                        help="Heading change threshold for waypoint inclusion (default: 15°)")
    parser.add_argument("--speed-threshold", type=float, default=2.0,
                        help="Speed change threshold for waypoint inclusion (default: 2 kn)")
    parser.add_argument("--max-waypoints", type=int, default=30,
                        help="Maximum waypoints per vessel track (default: 30)")
    parser.add_argument("--exclude-stationary", action="store_true",
                        help="Exclude moored/anchored vessels")
    parser.add_argument("--exclude-fishing", action="store_true",
                        help="Exclude fishing vessels")
    parser.add_argument("--exclude-tugs", action="store_true",
                        help="Exclude tugs and port service vessels")
    parser.add_argument("--types", nargs="+",
                        help="Only include these entity types (e.g. CIVILIAN_CARGO CIVILIAN_TANKER)")
    parser.add_argument("--min-length", type=float, default=0,
                        help="Minimum vessel length in meters (default: 0)")

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

    # Connect to database
    db_path = Path(args.db)
    if not db_path.exists():
        print(f"ERROR: Database not found: {db_path}", file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(str(db_path))

    # Load port lookup for destination resolution
    print("Loading ports...")
    port_lookup = load_port_lookup(conn)
    print(f"  {len(port_lookup)} ports with UNLOCODEs")

    # Load vessel details (pre-filtered for navaids/excluded types)
    print("Loading vessel details...")
    vessels = load_vessel_details(conn)
    print(f"  {len(vessels)} vessels (after navaid/type exclusion)")

    # Load positions within bbox for valid vessels
    print("Loading positions within bounding box...")
    vessel_set = set(vessels.keys())
    tracks = load_positions(conn, vessel_set, bbox)
    print(f"  {sum(len(v) for v in tracks.values())} positions for {len(tracks)} vessels")

    conn.close()

    # Process tracks → entities
    entities = []
    stats = defaultdict(int)

    # Sort by number of positions (most data first = highest quality tracks)
    sorted_mmsis = sorted(tracks.keys(), key=lambda m: len(tracks[m]), reverse=True)

    for mmsi in sorted_mmsis:
        positions = tracks[mmsi]

        if len(positions) < args.min_positions:
            stats["too_few_positions"] += 1
            continue

        vessel = vessels.get(mmsi)
        if not vessel:
            stats["no_vessel_details"] += 1
            continue

        # Min length filter
        if args.min_length and (not vessel.length or vessel.length < args.min_length):
            stats["below_min_length"] += 1
            continue

        # Map entity type
        entity_type = map_entity_type(vessel.vessel_type, vessel.type_specific,
                                      vessel.length)

        # Exclude stationary if requested
        if args.exclude_stationary:
            nav = positions[0].nav_status
            if nav in ("Moored", "At anchor"):
                stats["excluded_stationary"] += 1
                continue

        # Exclude fishing if requested
        if args.exclude_fishing and entity_type == "CIVILIAN_FISHING":
            stats["excluded_fishing"] += 1
            continue

        # Exclude tugs if requested
        if args.exclude_tugs and vessel.vessel_type == "Tug":
            stats["excluded_tugs"] += 1
            continue

        # Filter by type if requested
        if args.types and entity_type not in args.types:
            stats["excluded_type"] += 1
            continue

        # Sort positions by timestamp
        positions.sort(key=lambda p: p.ts)

        # Simplify track
        simplified = simplify_track(
            positions,
            heading_threshold_deg=args.heading_threshold,
            speed_threshold_kn=args.speed_threshold,
            max_waypoints=args.max_waypoints,
        )

        if len(simplified) < 2:
            stats["too_few_simplified"] += 1
            continue

        # Build entity
        entity = build_entity(vessel, positions, simplified, port_lookup)
        entities.append(entity)
        stats[entity_type] += 1

        if len(entities) >= args.max_vessels:
            print(f"  Reached max-vessels limit ({args.max_vessels})")
            break

    # ── Summary ──────────────────────────────────────────────────────────────

    print(f"\n{'='*60}")
    print(f"SUMMARY")
    print(f"{'='*60}")

    # By type
    type_counts = defaultdict(int)
    for e in entities:
        type_counts[e["type"]] += 1
    print(f"\nEntities by type:")
    for t, c in sorted(type_counts.items(), key=lambda x: -x[1]):
        print(f"  {t:30s} {c:5d}")
    print(f"  {'TOTAL':30s} {len(entities):5d}")

    # Geographic distribution (rough quadrants)
    geo_bins = defaultdict(int)
    for e in entities:
        lat = e["initial_position"]["lat"]
        lon = e["initial_position"]["lon"]
        if lon < 103:
            region = "Malacca Strait"
        elif lon < 105:
            region = "Singapore Strait"
        elif lon < 115:
            region = "South China Sea (West)"
        elif lon < 120:
            region = "Borneo / Celebes"
        else:
            region = "Eastern Waters"
        geo_bins[region] += 1

    print(f"\nGeographic distribution:")
    for region, count in sorted(geo_bins.items(), key=lambda x: -x[1]):
        print(f"  {region:30s} {count:5d}")

    # Stationary vs moving
    moving = sum(1 for e in entities
                 if e["metadata"].get("nav_status") not in ("Moored", "At Anchor"))
    stationary = len(entities) - moving
    print(f"\nMovement status:")
    print(f"  {'Moving':30s} {moving:5d}")
    print(f"  {'Stationary (moored/anchored)':30s} {stationary:5d}")

    # Filter stats
    filter_keys = [k for k in stats if k.startswith(("too_", "excluded_", "no_", "below_"))]
    if filter_keys:
        print(f"\nFiltered out:")
        for key in sorted(filter_keys):
            print(f"  {key:30s} {stats[key]:5d}")

    # Flag distribution (top 10)
    flag_counts = defaultdict(int)
    for e in entities:
        flag = e["metadata"].get("flag", "UNK")
        flag_counts[flag] += 1
    print(f"\nTop flags:")
    for flag, count in sorted(flag_counts.items(), key=lambda x: -x[1])[:10]:
        print(f"  {flag:30s} {count:5d}")

    print(f"\n{'='*60}")

    # ── Write output ─────────────────────────────────────────────────────────

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    output_yaml = build_yaml_output(entities, bbox, str(db_path), stats, generated_at)

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(output_yaml)

    print(f"\nWritten: {out_path}")
    print(f"  {len(entities)} entities, {sum(len(e['waypoints']) for e in entities)} total waypoints")


if __name__ == "__main__":
    main()
