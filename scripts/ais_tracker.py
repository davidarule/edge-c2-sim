#!/usr/bin/env python3
"""
ais_tracker.py — Track builder via Datalastic /vessel_bulk
==========================================================
Polls all discovered vessels at regular intervals to build movement tracks.
"""

import argparse
import math
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

BULK_BATCH_SIZE = 100


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
        # params can be a dict or list of tuples (for repeated keys)
        if isinstance(params, list):
            params.insert(0, ("api-key", self.api_key))
        else:
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

    def vessel_bulk(self, mmsi_list):
        """Query up to 100 vessels at once."""
        params = [("mmsi", str(m)) for m in mmsi_list[:BULK_BATCH_SIZE]]
        return self._request("vessel_bulk", params)


def get_all_mmsis(conn):
    """Get all discovered MMSIs from the database."""
    cursor = conn.execute("SELECT mmsi FROM vessels ORDER BY mmsi")
    return [row[0] for row in cursor.fetchall()]


def store_position(conn, vessel, source="track"):
    """Insert a position record for a vessel.

    Uses last_position_UTC from the API response as timestamp.
    """
    mmsi = str(vessel.get("mmsi", ""))
    if not mmsi or mmsi == "0":
        return False

    lat = vessel.get("lat")
    lon = vessel.get("lon")
    if lat is None or lon is None:
        return False

    timestamp = vessel.get("last_position_UTC") or vessel.get("last_position_utc", "")
    if not timestamp:
        return False

    try:
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
            vessel.get("navigation_status"),
            vessel.get("draught"),
            vessel.get("destination"),
            vessel.get("eta_UTC") or vessel.get("eta"),
            source,
        ))
        return True
    except sqlite3.IntegrityError:
        return False


def run_tracker(args):
    api_key = args.api_key or os.environ.get("DATALASTIC_API_KEY")
    if not api_key:
        print("ERROR: No API key. Set DATALASTIC_API_KEY or use --api-key")
        sys.exit(1)

    if not os.path.exists(args.db_path):
        print(f"ERROR: Database not found at {args.db_path}")
        print("Run ais_discovery.py first to populate the vessel database.")
        sys.exit(1)

    conn = sqlite3.connect(args.db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")

    client = DatalasticClient(api_key)
    all_mmsis = get_all_mmsis(conn)

    if not all_mmsis:
        print("No vessels in database. Run ais_discovery.py first.")
        conn.close()
        sys.exit(1)

    num_batches = math.ceil(len(all_mmsis) / BULK_BATCH_SIZE)
    num_polls = args.polls
    poll_interval = args.interval * 60  # convert minutes to seconds

    print(f"{'='*60}")
    print(f"TRACKING PLAN")
    print(f"{'='*60}")
    print(f"  Vessels to track:  {len(all_mmsis):,}")
    print(f"  Batches per poll:  {num_batches} (of {BULK_BATCH_SIZE})")
    print(f"  Poll interval:     {args.interval} min")
    print(f"  Number of polls:   {num_polls}")
    print(f"  Total duration:    {num_polls * args.interval} min")
    print(f"  Est. API calls:    {num_batches * num_polls:,}")
    print(f"  Database:          {args.db_path}")
    print(f"{'='*60}")

    total_new_positions = 0
    track_start = time.time()

    for poll in range(num_polls):
        poll_start = time.time()
        poll_positions = 0
        poll_updated = 0
        poll_missing = 0
        now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        print(f"\nPoll {poll + 1}/{num_polls} starting at {now_utc}...")

        for batch_idx in range(num_batches):
            batch_start = batch_idx * BULK_BATCH_SIZE
            batch_mmsis = all_mmsis[batch_start:batch_start + BULK_BATCH_SIZE]

            result = client.vessel_bulk(batch_mmsis)

            if result and "data" in result:
                data = result["data"]
                # Bulk may return list directly or {"vessels": [...]}
                if isinstance(data, list):
                    vessels = data
                elif isinstance(data, dict):
                    vessels = data.get("vessels", [])
                else:
                    vessels = []

                for v in vessels:
                    if store_position(conn, v, "track"):
                        poll_positions += 1
                        poll_updated += 1
                # Count missing vessels
                returned_mmsis = {str(v.get("mmsi", "")) for v in vessels}
                poll_missing += sum(1 for m in batch_mmsis if m not in returned_mmsis)
            else:
                poll_missing += len(batch_mmsis)

            # Progress within poll
            if (batch_idx + 1) % 20 == 0:
                print(f"  Batch {batch_idx + 1}/{num_batches} — "
                      f"{poll_positions} positions this poll")

        conn.commit()
        total_new_positions += poll_positions

        poll_elapsed = time.time() - poll_start
        print(f"Poll {poll + 1}/{num_polls} complete — "
              f"{poll_updated:,} vessels updated, "
              f"{poll_positions:,} new positions, "
              f"{poll_missing:,} missing — "
              f"{poll_elapsed:.1f}s")

        # Wait for next poll (skip wait on last poll)
        if poll < num_polls - 1:
            wait_time = max(0, poll_interval - poll_elapsed)
            if wait_time > 0:
                print(f"  Waiting {wait_time:.0f}s until next poll...")
                time.sleep(wait_time)

    elapsed = time.time() - track_start

    # Summary
    total_positions = conn.execute("SELECT COUNT(*) FROM positions").fetchone()[0]
    track_positions = conn.execute("SELECT COUNT(*) FROM positions WHERE source='track'").fetchone()[0]

    print(f"\n{'='*60}")
    print(f"TRACKING COMPLETE")
    print(f"{'='*60}")
    print(f"  Polls completed:   {num_polls}")
    print(f"  New positions:     {total_new_positions:,}")
    print(f"  Total positions:   {total_positions:,} (discovery: {total_positions - track_positions:,}, track: {track_positions:,})")
    print(f"  API calls:         {client.request_count}")
    print(f"  Time:              {elapsed/60:.1f} min")

    conn.close()


def main():
    parser = argparse.ArgumentParser(description="Datalastic AIS vessel tracker")
    parser.add_argument("--api-key", help="Datalastic API key (or set DATALASTIC_API_KEY)")
    parser.add_argument("--db-path", default=DEFAULT_DB, help="SQLite database path")
    parser.add_argument("--interval", type=float, default=10, help="Minutes between polls (default: 10)")
    parser.add_argument("--polls", type=int, default=12, help="Number of polls (default: 12 = 2 hours at 10min)")
    args = parser.parse_args()
    run_tracker(args)


if __name__ == "__main__":
    main()
