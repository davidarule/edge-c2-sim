#!/usr/bin/env python3
"""
ais_enrich.py — Static data enrichment via Datalastic /vessel_info
==================================================================
Fetches full vessel specs for each discovered vessel.
"""

import argparse
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone

import requests

API_BASE = "https://api.datalastic.com/api/v0"
DEFAULT_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ais_data", "ais_capture.db")

# Rate limiting
MIN_REQUEST_INTERVAL = 1.0 / 8.5

# Retry config
MAX_RETRIES = 5
INITIAL_BACKOFF = 2.0


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

    def vessel_info(self, mmsi):
        """Get static vessel information."""
        return self._request("vessel_info", {"mmsi": mmsi})


def init_details_table(conn):
    """Create the vessel_details table if it doesn't exist."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS vessel_details (
            mmsi TEXT PRIMARY KEY,
            uuid TEXT,
            imo TEXT,
            eni TEXT,
            name TEXT,
            callsign TEXT,
            type TEXT,
            type_specific TEXT,
            country_iso TEXT,
            country_name TEXT,
            length REAL,
            breadth REAL,
            draught_avg REAL,
            draught_max REAL,
            gross_tonnage REAL,
            deadweight REAL,
            teu REAL,
            year_built TEXT,
            speed_avg REAL,
            speed_max REAL,
            home_port TEXT,
            is_navaid INTEGER DEFAULT 0,
            enriched_utc TEXT,
            FOREIGN KEY (mmsi) REFERENCES vessels(mmsi)
        )
    """)
    conn.commit()


def get_unenriched_mmsis(conn):
    """Get MMSIs that haven't been enriched yet."""
    cursor = conn.execute("""
        SELECT v.mmsi FROM vessels v
        LEFT JOIN vessel_details d ON v.mmsi = d.mmsi
        WHERE d.mmsi IS NULL
        ORDER BY v.mmsi
    """)
    return [row[0] for row in cursor.fetchall()]


def store_vessel_details(conn, mmsi, data, now_utc):
    """Store enriched vessel details.

    Datalastic response: {"data": {vessel fields...}, "meta": {...}}
    Returns True if stored, False if skipped (navaid).
    """
    vessel = data.get("data", {}) if isinstance(data, dict) else {}
    if not isinstance(vessel, dict):
        vessel = {}

    # Skip navigation aids — they aren't real vessels
    if vessel.get("is_navaid", False):
        conn.execute("""
            INSERT OR REPLACE INTO vessel_details (mmsi, is_navaid, enriched_utc)
            VALUES (?, 1, ?)
        """, (mmsi, now_utc))
        return False

    conn.execute("""
        INSERT OR REPLACE INTO vessel_details
            (mmsi, uuid, imo, eni, name, callsign, type, type_specific,
             country_iso, country_name, length, breadth, draught_avg, draught_max,
             gross_tonnage, deadweight, teu, year_built, speed_avg, speed_max,
             home_port, is_navaid, enriched_utc)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
    """, (
        mmsi,
        vessel.get("uuid", ""),
        str(vessel.get("imo") or ""),
        vessel.get("eni", ""),
        vessel.get("name", ""),
        vessel.get("callsign", ""),
        vessel.get("type", ""),
        vessel.get("type_specific", ""),
        vessel.get("country_iso", ""),
        vessel.get("country_name", ""),
        vessel.get("length"),
        vessel.get("breadth"),
        vessel.get("draught_avg"),
        vessel.get("draught_max"),
        vessel.get("gross_tonnage"),
        vessel.get("deadweight"),
        vessel.get("teu"),
        vessel.get("year_built", ""),
        vessel.get("speed_avg"),
        vessel.get("speed_max"),
        vessel.get("home_port", ""),
        now_utc,
    ))
    return True


def run_enrich(args):
    api_key = args.api_key or os.environ.get("DATALASTIC_API_KEY")
    if not api_key:
        print("ERROR: No API key. Set DATALASTIC_API_KEY or use --api-key")
        sys.exit(1)

    if not os.path.exists(args.db_path):
        print(f"ERROR: Database not found at {args.db_path}")
        print("Run ais_discovery.py first.")
        sys.exit(1)

    conn = sqlite3.connect(args.db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")

    init_details_table(conn)

    client = DatalasticClient(api_key)
    unenriched = get_unenriched_mmsis(conn)

    if not unenriched:
        print("All vessels already enriched.")
        conn.close()
        return

    total_vessels = conn.execute("SELECT COUNT(*) FROM vessels").fetchone()[0]
    already_enriched = total_vessels - len(unenriched)

    est_time_min = len(unenriched) * MIN_REQUEST_INTERVAL / 60.0

    print(f"{'='*60}")
    print(f"ENRICHMENT PLAN")
    print(f"{'='*60}")
    print(f"  Total vessels:     {total_vessels:,}")
    print(f"  Already enriched:  {already_enriched:,}")
    print(f"  To enrich:         {len(unenriched):,}")
    print(f"  Est. API calls:    {len(unenriched):,}")
    print(f"  Est. time:         {est_time_min:.1f} min ({est_time_min/60:.1f} hr)")
    print(f"  Database:          {args.db_path}")
    print(f"{'='*60}")

    enriched = 0
    skipped_navaids = 0
    failed = 0
    enrich_start = time.time()

    for i, mmsi in enumerate(unenriched):
        result = client.vessel_info(mmsi)
        now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        if result:
            stored = store_vessel_details(conn, mmsi, result, now_utc)
            if stored:
                enriched += 1
            else:
                skipped_navaids += 1
        else:
            # Store a minimal record so we don't retry
            conn.execute("""
                INSERT OR REPLACE INTO vessel_details (mmsi, enriched_utc)
                VALUES (?, ?)
            """, (mmsi, now_utc))
            failed += 1

        # Commit every 50 vessels
        if (i + 1) % 50 == 0:
            conn.commit()

        # Progress every 100 vessels
        if (i + 1) % 100 == 0:
            elapsed = time.time() - enrich_start
            rate = (i + 1) / elapsed if elapsed > 0 else 0
            eta_min = (len(unenriched) - i - 1) / rate / 60.0 if rate > 0 else 0
            print(f"Enriched {already_enriched + i + 1}/{total_vessels} — "
                  f"{enriched} ok, {skipped_navaids} navaids, {failed} failed — "
                  f"{rate:.1f} req/s — ETA {eta_min:.0f} min")

    conn.commit()
    elapsed = time.time() - enrich_start

    print(f"\n{'='*60}")
    print(f"ENRICHMENT COMPLETE")
    print(f"{'='*60}")
    print(f"  Enriched:          {enriched:,}")
    print(f"  Skipped (navaids): {skipped_navaids:,}")
    print(f"  Failed:            {failed:,}")
    print(f"  API calls:         {client.request_count}")
    print(f"  Time:              {elapsed/60:.1f} min")

    conn.close()


def main():
    parser = argparse.ArgumentParser(description="Datalastic AIS vessel enrichment")
    parser.add_argument("--api-key", help="Datalastic API key (or set DATALASTIC_API_KEY)")
    parser.add_argument("--db-path", default=DEFAULT_DB, help="SQLite database path")
    args = parser.parse_args()
    run_enrich(args)


if __name__ == "__main__":
    main()
