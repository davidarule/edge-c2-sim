#!/usr/bin/env python3
"""
ais_export.py — Export SQLite capture data for simulator replay
===============================================================
Exports sim_tracks.csv, vessel_catalogue.csv, and capture_summary.json.
Applies track simplification to reduce waypoints.
"""

import argparse
import csv
import json
import math
import os
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime


DEFAULT_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ais_data", "ais_capture.db")
DEFAULT_OUTPUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ais_data")

# Track simplification thresholds
MIN_COURSE_CHANGE_DEG = 5.0
MIN_SPEED_CHANGE_KN = 2.0
MIN_TIME_GAP_SEC = 300  # Always keep points with >5min gaps


def angle_diff(a, b):
    """Absolute angular difference, handling wrap-around."""
    if a is None or b is None:
        return 360  # Force keep if no course data
    d = abs(a - b) % 360
    return min(d, 360 - d)


def simplify_track(positions):
    """Reduce track waypoints, keeping points where course/speed changed significantly.

    positions: list of dicts with at least course, speed, timestamp_utc
    Returns filtered list.
    """
    if len(positions) <= 2:
        return positions

    simplified = [positions[0]]  # Always keep first

    for i in range(1, len(positions) - 1):
        prev = simplified[-1]
        curr = positions[i]

        # Always keep if large time gap
        try:
            t_prev = datetime.fromisoformat(prev["timestamp_utc"].replace("Z", "+00:00"))
            t_curr = datetime.fromisoformat(curr["timestamp_utc"].replace("Z", "+00:00"))
            gap_sec = (t_curr - t_prev).total_seconds()
        except (ValueError, TypeError):
            gap_sec = MIN_TIME_GAP_SEC + 1  # Keep on parse error

        if gap_sec >= MIN_TIME_GAP_SEC:
            simplified.append(curr)
            continue

        # Keep if course changed
        course_change = angle_diff(prev.get("course"), curr.get("course"))
        if course_change >= MIN_COURSE_CHANGE_DEG:
            simplified.append(curr)
            continue

        # Keep if speed changed
        prev_speed = prev.get("speed") or 0
        curr_speed = curr.get("speed") or 0
        if abs(curr_speed - prev_speed) >= MIN_SPEED_CHANGE_KN:
            simplified.append(curr)
            continue

    simplified.append(positions[-1])  # Always keep last
    return simplified


def run_export(args):
    if not os.path.exists(args.db_path):
        print(f"ERROR: Database not found at {args.db_path}")
        sys.exit(1)

    os.makedirs(args.output_dir, exist_ok=True)

    conn = sqlite3.connect(args.db_path)
    conn.row_factory = sqlite3.Row

    # Load all positions grouped by mmsi
    print("Loading positions from database...")
    cursor = conn.execute("""
        SELECT p.mmsi, p.timestamp_utc, p.lat, p.lon, p.speed, p.course, p.heading,
               p.navigational_status, p.draught, p.destination, p.eta, p.source,
               v.imo, v.name, v.callsign, v.type, v.type_specific, v.country_iso,
               v.length, v.breadth
        FROM positions p
        JOIN vessels v ON p.mmsi = v.mmsi
        ORDER BY p.mmsi, p.timestamp_utc
    """)
    rows = cursor.fetchall()
    print(f"  {len(rows):,} position records loaded")

    # Group by mmsi
    tracks = defaultdict(list)
    for row in rows:
        tracks[row["mmsi"]].append(dict(row))

    # Simplify tracks
    print("Simplifying tracks...")
    total_before = len(rows)
    total_after = 0
    simplified_tracks = {}
    for mmsi, positions in tracks.items():
        simplified = simplify_track(positions) if not args.no_simplify else positions
        simplified_tracks[mmsi] = simplified
        total_after += len(simplified)

    reduction = (1 - total_after / total_before) * 100 if total_before > 0 else 0
    print(f"  {total_before:,} → {total_after:,} positions ({reduction:.1f}% reduction)")

    # Export sim_tracks.csv
    tracks_path = os.path.join(args.output_dir, "sim_tracks.csv")
    print(f"Writing {tracks_path}...")

    track_headers = [
        "mmsi", "timestamp_utc", "lat", "lon", "speed", "course", "heading",
        "navigational_status", "draught", "destination", "eta", "source",
        "imo", "name", "callsign", "type", "type_specific", "country_iso",
        "length", "breadth",
    ]

    track_count = 0
    with open(tracks_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=track_headers, extrasaction="ignore")
        writer.writeheader()
        for mmsi in sorted(simplified_tracks.keys()):
            for pos in simplified_tracks[mmsi]:
                writer.writerow(pos)
                track_count += 1

    print(f"  {track_count:,} rows written")

    # Load vessel details for catalogue
    print("Loading vessel details...")
    has_details = False
    try:
        conn.execute("SELECT 1 FROM vessel_details LIMIT 1")
        has_details = True
    except sqlite3.OperationalError:
        pass

    catalogue_path = os.path.join(args.output_dir, "vessel_catalogue.csv")
    print(f"Writing {catalogue_path}...")

    if has_details:
        cursor = conn.execute("""
            SELECT v.mmsi, COALESCE(d.imo, v.imo) as imo,
                   COALESCE(d.name, v.name) as name,
                   COALESCE(d.callsign, v.callsign) as callsign,
                   COALESCE(d.type, v.type) as type,
                   COALESCE(d.type_specific, v.type_specific) as type_specific,
                   COALESCE(d.country_iso, v.country_iso) as country_iso,
                   COALESCE(d.length, v.length) as length,
                   COALESCE(d.breadth, v.breadth) as breadth,
                   d.draught_max, d.gross_tonnage, d.deadweight, d.teu,
                   d.year_built, d.speed_max
            FROM vessels v
            LEFT JOIN vessel_details d ON v.mmsi = d.mmsi
            ORDER BY v.mmsi
        """)
    else:
        cursor = conn.execute("""
            SELECT mmsi, imo, name, callsign, type, type_specific, country_iso,
                   length, breadth,
                   NULL as draught_max, NULL as gross_tonnage, NULL as deadweight,
                   NULL as teu, NULL as year_built, NULL as speed_max
            FROM vessels
            ORDER BY mmsi
        """)

    catalogue_headers = [
        "mmsi", "imo", "name", "callsign", "type", "type_specific", "country_iso",
        "length", "breadth", "draught_max", "gross_tonnage", "deadweight", "teu",
        "year_built", "speed_max",
    ]

    catalogue_rows = cursor.fetchall()
    with open(catalogue_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(catalogue_headers)
        for row in catalogue_rows:
            writer.writerow(list(row))

    print(f"  {len(catalogue_rows):,} vessels written")

    # Capture summary
    summary_path = os.path.join(args.output_dir, "capture_summary.json")
    print(f"Writing {summary_path}...")

    total_vessels = conn.execute("SELECT COUNT(*) FROM vessels").fetchone()[0]
    total_positions = conn.execute("SELECT COUNT(*) FROM positions").fetchone()[0]
    discovery_positions = conn.execute("SELECT COUNT(*) FROM positions WHERE source='discovery'").fetchone()[0]
    track_positions = conn.execute("SELECT COUNT(*) FROM positions WHERE source='track'").fetchone()[0]

    # Type breakdown
    type_cursor = conn.execute("SELECT type, COUNT(*) FROM vessels GROUP BY type ORDER BY COUNT(*) DESC")
    type_breakdown = {row[0] or "Unknown": row[1] for row in type_cursor.fetchall()}

    # Country breakdown
    country_cursor = conn.execute("SELECT country_iso, COUNT(*) FROM vessels GROUP BY country_iso ORDER BY COUNT(*) DESC LIMIT 30")
    country_breakdown = {row[0] or "Unknown": row[1] for row in country_cursor.fetchall()}

    # Time range
    time_range = conn.execute("""
        SELECT MIN(timestamp_utc), MAX(timestamp_utc) FROM positions
    """).fetchone()

    # Vessels with tracks (>1 position)
    vessels_with_tracks = conn.execute("""
        SELECT COUNT(*) FROM (
            SELECT mmsi FROM positions GROUP BY mmsi HAVING COUNT(*) > 1
        )
    """).fetchone()[0]

    enriched_count = 0
    if has_details:
        enriched_count = conn.execute("""
            SELECT COUNT(*) FROM vessel_details WHERE name IS NOT NULL AND name != ''
        """).fetchone()[0]

    summary = {
        "capture_date": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "Datalastic API",
        "region": "Southeast Asia (lat -11 to 8, lon 93 to 142)",
        "total_vessels": total_vessels,
        "vessels_with_tracks": vessels_with_tracks,
        "enriched_vessels": enriched_count,
        "total_positions": total_positions,
        "discovery_positions": discovery_positions,
        "track_positions": track_positions,
        "exported_positions": track_count,
        "simplification_reduction_pct": round(reduction, 1),
        "time_range": {
            "first": time_range[0],
            "last": time_range[1],
        },
        "type_breakdown": type_breakdown,
        "country_breakdown": country_breakdown,
    }

    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)

    print(f"\n{'='*60}")
    print(f"EXPORT COMPLETE")
    print(f"{'='*60}")
    print(f"  sim_tracks.csv:       {track_count:,} positions ({len(simplified_tracks):,} vessels)")
    print(f"  vessel_catalogue.csv: {len(catalogue_rows):,} vessels")
    print(f"  capture_summary.json: written")
    print(f"\nFiles in: {args.output_dir}")

    conn.close()


def main():
    parser = argparse.ArgumentParser(description="Export AIS capture data for simulator")
    parser.add_argument("--db-path", default=DEFAULT_DB, help="SQLite database path")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT, help="Output directory")
    parser.add_argument("--no-simplify", action="store_true", help="Skip track simplification")
    args = parser.parse_args()
    run_export(args)


if __name__ == "__main__":
    main()
