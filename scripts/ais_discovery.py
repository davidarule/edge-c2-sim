#!/usr/bin/env python3
"""
ais_discovery.py — Datalastic area scan / vessel discovery
==========================================================
Scans Southeast Asian waters using a grid of /vessel_inradius calls.
Stores discovered vessels and positions in a SQLite database.
"""

import argparse
import json
import math
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone

import requests

# Add project root to path for terrain import
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.terrain import is_land


# --- Constants ---

API_BASE = "https://api.datalastic.com/api/v0"
DEFAULT_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ais_data", "ais_capture.db")

# SE Asia bounding box
LAT_MIN, LAT_MAX = -11.0, 8.0
LON_MIN, LON_MAX = 93.0, 142.0

# Rate limiting: 600 req/min → 10 req/s, target 8.5 for safety margin
MIN_REQUEST_INTERVAL = 1.0 / 8.5  # ~0.118s

# Land check: skip scan points more than this many nm inland
COAST_BUFFER_NM = 20
COAST_BUFFER_DEG = COAST_BUFFER_NM / 60.0  # ~0.333°

# Retry config
MAX_RETRIES = 5
INITIAL_BACKOFF = 2.0


def nm_to_deg_lat(nm):
    """Convert nautical miles to degrees latitude."""
    return nm / 60.0


def nm_to_deg_lon(nm, lat):
    """Convert nautical miles to degrees longitude at a given latitude."""
    return nm / (60.0 * math.cos(math.radians(lat)))


def init_db(db_path):
    """Create SQLite database and tables if they don't exist."""
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS vessels (
            mmsi TEXT PRIMARY KEY,
            imo TEXT,
            name TEXT,
            callsign TEXT,
            type TEXT,
            type_specific TEXT,
            country_iso TEXT,
            length REAL,
            breadth REAL,
            first_seen_utc TEXT
        );

        CREATE TABLE IF NOT EXISTS positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mmsi TEXT NOT NULL,
            timestamp_utc TEXT NOT NULL,
            lat REAL NOT NULL,
            lon REAL NOT NULL,
            speed REAL,
            course REAL,
            heading REAL,
            navigational_status TEXT,
            draught REAL,
            destination TEXT,
            eta TEXT,
            source TEXT DEFAULT 'discovery',
            FOREIGN KEY (mmsi) REFERENCES vessels(mmsi),
            UNIQUE(mmsi, timestamp_utc)
        );

        CREATE TABLE IF NOT EXISTS scan_progress (
            cell_key TEXT PRIMARY KEY,
            scanned_utc TEXT,
            vessel_count INTEGER
        );

        CREATE INDEX IF NOT EXISTS idx_positions_mmsi ON positions(mmsi);
        CREATE INDEX IF NOT EXISTS idx_positions_timestamp ON positions(timestamp_utc);
    """)
    conn.commit()
    return conn


def generate_grid(radius_nm, spacing_factor=0.85):
    """Generate scan grid points covering the SE Asia bounding box.

    spacing_factor: fraction of diameter between points (< 1.0 = overlap)
    """
    spacing_nm = radius_nm * 2 * spacing_factor
    points = []

    lat = LAT_MIN
    while lat <= LAT_MAX:
        lon_spacing = nm_to_deg_lon(spacing_nm, lat)
        lon = LON_MIN
        while lon <= LON_MAX:
            points.append((round(lat, 4), round(lon, 4)))
            lon += lon_spacing
        lat += nm_to_deg_lat(spacing_nm)

    return points


def is_near_sea(lat, lon):
    """Check if a point is at sea or within COAST_BUFFER of the coast.

    Uses a quick check: if the point itself is sea, return True.
    If on land, check 8 cardinal/ordinal directions at COAST_BUFFER distance.
    """
    if not is_land(lat, lon):
        return True

    # Check nearby points for sea
    for dlat, dlon in [
        (COAST_BUFFER_DEG, 0), (-COAST_BUFFER_DEG, 0),
        (0, COAST_BUFFER_DEG), (0, -COAST_BUFFER_DEG),
        (COAST_BUFFER_DEG, COAST_BUFFER_DEG), (-COAST_BUFFER_DEG, -COAST_BUFFER_DEG),
        (COAST_BUFFER_DEG, -COAST_BUFFER_DEG), (-COAST_BUFFER_DEG, COAST_BUFFER_DEG),
    ]:
        if not is_land(lat + dlat, lon + dlon):
            return True
    return False


def filter_sea_points(points):
    """Filter grid points to only those near the sea."""
    print(f"Filtering {len(points)} grid points using terrain data...")
    sea_points = []
    for i, (lat, lon) in enumerate(points):
        if is_near_sea(lat, lon):
            sea_points.append((lat, lon))
        if (i + 1) % 500 == 0:
            print(f"  Checked {i+1}/{len(points)} — {len(sea_points)} sea points so far")
    print(f"  {len(sea_points)} sea/coastal points out of {len(points)} total ({100*len(sea_points)/len(points):.1f}%)")
    return sea_points


def cell_key(lat, lon):
    return f"{lat:.4f},{lon:.4f}"


def get_scanned_cells(conn):
    """Get set of already-scanned cell keys."""
    cursor = conn.execute("SELECT cell_key FROM scan_progress")
    return {row[0] for row in cursor.fetchall()}


class DatalasticClient:
    """Rate-limited Datalastic API client with retries."""

    def __init__(self, api_key):
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json"})
        self.last_request_time = 0
        self.request_count = 0

    def _throttle(self):
        elapsed = time.time() - self.last_request_time
        if elapsed < MIN_REQUEST_INTERVAL:
            time.sleep(MIN_REQUEST_INTERVAL - elapsed)

    def _request(self, endpoint, params):
        params["api-key"] = self.api_key
        url = f"{API_BASE}/{endpoint}"

        for attempt in range(MAX_RETRIES):
            self._throttle()
            self.last_request_time = time.time()
            self.request_count += 1

            try:
                resp = self.session.get(url, params=params, timeout=30)

                if resp.status_code == 200:
                    body = resp.json()
                    meta = body.get("meta", {})
                    if not meta.get("success", False):
                        msg = meta.get("message", "unknown error")
                        print(f"  API returned success=false: {msg}")
                        return None
                    return body
                elif resp.status_code == 429:
                    wait = INITIAL_BACKOFF * (2 ** attempt)
                    print(f"  Rate limited (429), backing off {wait:.1f}s...")
                    time.sleep(wait)
                elif resp.status_code in (500, 502, 503):
                    wait = INITIAL_BACKOFF * (2 ** attempt)
                    print(f"  Server error ({resp.status_code}), retrying in {wait:.1f}s...")
                    time.sleep(wait)
                else:
                    print(f"  API error {resp.status_code}: {resp.text[:200]}")
                    return None
            except requests.RequestException as e:
                wait = INITIAL_BACKOFF * (2 ** attempt)
                print(f"  Request error: {e}, retrying in {wait:.1f}s...")
                time.sleep(wait)

        print(f"  Failed after {MAX_RETRIES} retries")
        return None

    def check_stat(self):
        """Check API credit usage."""
        return self._request("stat", {})

    def vessel_inradius(self, lat, lon, radius):
        """Area scan for vessels within radius of a point."""
        return self._request("vessel_inradius", {
            "lat": lat,
            "lon": lon,
            "radius": radius,
        })

    def test_radius(self, lat, lon):
        """Test what radius values the API accepts. Returns best working radius.

        Response format: {"data": {"point": {...}, "total": N, "vessels": [...]}, "meta": {"success": true}}
        Error format: {"meta": {"message": {"radius": "must be no greater than 50"}, "success": false}}
        """
        for radius in [50, 25, 10]:
            print(f"  Testing radius={radius}nm at ({lat}, {lon})...")
            result = self.vessel_inradius(lat, lon, radius)
            if result and "data" in result:
                data = result["data"]
                vessels = data.get("vessels", [])
                total = data.get("total", len(vessels))
                print(f"  ✓ radius={radius}nm works — {total} vessels found ({len(vessels)} returned)")
                return radius, result
            else:
                print(f"  ✗ radius={radius}nm — rejected or failed")
        return None, None


def store_vessel(conn, vessel, now_utc):
    """Insert or update a vessel record."""
    mmsi = str(vessel.get("mmsi", ""))
    if not mmsi or mmsi == "0":
        return None

    conn.execute("""
        INSERT OR IGNORE INTO vessels (mmsi, imo, name, callsign, type, type_specific,
                                        country_iso, length, breadth, first_seen_utc)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        mmsi,
        str(vessel.get("imo", "")),
        vessel.get("name", ""),
        vessel.get("callsign", ""),
        vessel.get("type", ""),
        vessel.get("type_specific", ""),
        vessel.get("country_iso", ""),
        vessel.get("length"),
        vessel.get("breadth"),
        now_utc,
    ))
    return mmsi


def store_position(conn, vessel, source="discovery"):
    """Insert a position record for a vessel.

    Uses last_position_UTC from the API response as timestamp.
    Falls back to eta_UTC for the eta field.
    """
    mmsi = str(vessel.get("mmsi", ""))
    if not mmsi or mmsi == "0":
        return

    lat = vessel.get("lat")
    lon = vessel.get("lon")
    if lat is None or lon is None:
        return

    # Use the vessel's own timestamp, not wall-clock time
    timestamp = vessel.get("last_position_UTC") or vessel.get("last_position_utc", "")
    if not timestamp:
        return

    conn.execute("""
        INSERT OR IGNORE INTO positions
            (mmsi, timestamp_utc, lat, lon, speed, course, heading,
             navigational_status, draught, destination, eta, source)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        mmsi,
        timestamp,
        lat,
        lon,
        vessel.get("speed"),
        vessel.get("course"),
        vessel.get("heading"),
        vessel.get("navigational_status"),  # may be None for inradius
        vessel.get("draught"),              # may be None for inradius
        vessel.get("destination"),
        vessel.get("eta_UTC") or vessel.get("eta"),
        source,
    ))


def run_discovery(args):
    api_key = args.api_key or os.environ.get("DATALASTIC_API_KEY")
    if not api_key and not args.dry_run:
        print("ERROR: No API key. Set DATALASTIC_API_KEY or use --api-key")
        sys.exit(1)

    radius = args.radius or 50  # default assumption for dry-run
    test_result = None

    if not args.dry_run:
        client = DatalasticClient(api_key)

        # Check API status
        print("Checking API status...")
        stat = client.check_stat()
        if stat:
            print(f"  API status: {json.dumps(stat, indent=2)}")
        else:
            print("  WARNING: Could not check API status, proceeding anyway...")

        # Test radius at Singapore
        print("\nTesting scan radius at Singapore (1.27, 103.85)...")
        radius_test, test_result = client.test_radius(1.27, 103.85)
        if radius_test is None:
            print("ERROR: Could not find a working radius. Check API key and quota.")
            sys.exit(1)

        if args.radius:
            radius = args.radius
            print(f"Using user-specified radius: {radius}nm")
        else:
            radius = radius_test
    else:
        print(f"DRY RUN — using estimated radius: {radius}nm")

    # Generate grid
    print(f"\nGenerating scan grid (radius={radius}nm)...")
    all_points = generate_grid(radius)
    print(f"  Raw grid: {len(all_points)} points")

    sea_points = filter_sea_points(all_points)

    # Open database
    conn = init_db(args.db_path)
    scanned = get_scanned_cells(conn)
    remaining = [(lat, lon) for lat, lon in sea_points if cell_key(lat, lon) not in scanned]

    # Capture plan
    total_cells = len(sea_points)
    already_done = len(scanned)
    to_scan = len(remaining)
    est_time_min = to_scan * MIN_REQUEST_INTERVAL / 60.0

    print(f"\n{'='*60}")
    print(f"CAPTURE PLAN")
    print(f"{'='*60}")
    print(f"  Scan radius:       {radius} nm")
    print(f"  Total grid cells:  {total_cells}")
    print(f"  Already scanned:   {already_done}")
    print(f"  Remaining:         {to_scan}")
    print(f"  Est. API calls:    {to_scan}")
    print(f"  Est. time:         {est_time_min:.1f} min ({est_time_min/60:.1f} hr) at rate limit")
    print(f"  Database:          {args.db_path}")
    print(f"{'='*60}")

    if args.dry_run:
        print("\n--dry-run specified, exiting.")
        conn.close()
        return

    # Process test result first (avoid wasting the call)
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if test_result and "data" in test_result:
        vessels = test_result["data"].get("vessels", [])
        for v in vessels:
            mmsi = store_vessel(conn, v, now_utc)
            if mmsi:
                store_position(conn, v, "discovery")
        sg_key = cell_key(1.27, 103.85)
        conn.execute("INSERT OR IGNORE INTO scan_progress (cell_key, scanned_utc, vessel_count) VALUES (?, ?, ?)",
                      (sg_key, now_utc, len(vessels)))
        conn.commit()

    # Main scan loop
    unique_vessels = set()
    cursor = conn.execute("SELECT mmsi FROM vessels")
    unique_vessels.update(row[0] for row in cursor.fetchall())

    total_positions = 0
    scan_start = time.time()

    for i, (lat, lon) in enumerate(remaining):
        ck = cell_key(lat, lon)

        result = client.vessel_inradius(lat, lon, radius)
        now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        vessel_count = 0
        if result and "data" in result:
            vessels = result["data"].get("vessels", [])
            for v in vessels:
                mmsi = store_vessel(conn, v, now_utc)
                if mmsi:
                    store_position(conn, v, "discovery")
                    unique_vessels.add(mmsi)
                    vessel_count += 1
                    total_positions += 1

        conn.execute(
            "INSERT OR IGNORE INTO scan_progress (cell_key, scanned_utc, vessel_count) VALUES (?, ?, ?)",
            (ck, now_utc, vessel_count))

        # Commit every 10 cells
        if (i + 1) % 10 == 0:
            conn.commit()

        # Progress log every 25 cells
        if (i + 1) % 25 == 0 or i == 0:
            elapsed = time.time() - scan_start
            rate = (i + 1) / elapsed if elapsed > 0 else 0
            eta_min = (to_scan - i - 1) / rate / 60.0 if rate > 0 else 0
            print(f"Scanned cell {already_done + i + 1}/{total_cells} — "
                  f"{len(unique_vessels):,} unique vessels, "
                  f"{total_positions:,} positions — "
                  f"{rate:.1f} req/s — ETA {eta_min:.0f} min")

    conn.commit()

    # Summary
    elapsed = time.time() - scan_start
    print(f"\n{'='*60}")
    print(f"DISCOVERY COMPLETE")
    print(f"{'='*60}")
    print(f"  Cells scanned:     {to_scan}")
    print(f"  Total vessels:     {len(unique_vessels):,}")
    print(f"  API calls:         {client.request_count}")
    print(f"  Time:              {elapsed/60:.1f} min")

    # Type breakdown
    cursor = conn.execute("SELECT type, COUNT(*) FROM vessels GROUP BY type ORDER BY COUNT(*) DESC LIMIT 20")
    rows = cursor.fetchall()
    if rows:
        print(f"\n  Vessel type breakdown:")
        for vtype, count in rows:
            print(f"    {vtype or 'Unknown':30s} {count:,}")

    conn.close()


def main():
    parser = argparse.ArgumentParser(description="Datalastic AIS vessel discovery scan")
    parser.add_argument("--api-key", help="Datalastic API key (or set DATALASTIC_API_KEY)")
    parser.add_argument("--db-path", default=DEFAULT_DB, help="SQLite database path")
    parser.add_argument("--radius", type=float, help="Override scan radius in nautical miles")
    parser.add_argument("--dry-run", action="store_true", help="Show capture plan without making API calls")
    args = parser.parse_args()
    run_discovery(args)


if __name__ == "__main__":
    main()
