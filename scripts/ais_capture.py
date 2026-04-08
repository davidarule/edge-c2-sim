#!/usr/bin/env python3
"""
AIS Data Capture for Southeast Asian Waters
============================================
Captures live AIS data from AISStream.io WebSocket API for the region covering
Indonesia, Malaysia, Singapore, Borneo, and Brunei.

Outputs two CSV files:
  - positions_YYYYMMDD_HHMMSS.csv  (vessel position reports)
  - statics_YYYYMMDD_HHMMSS.csv    (vessel static/voyage data)

These can be combined post-capture to create a complete simulator seed dataset.

Prerequisites:
  pip install websockets

Usage:
  1. Sign up at https://aisstream.io/authenticate (free, via GitHub)
  2. Generate an API key at https://aisstream.io/apikeys
  3. Run:  python ais_capture.py --api-key YOUR_KEY --duration 120

Author: David Rule / BrumbieSoft
"""

import argparse
import asyncio
import csv
import json
import logging
import os
import signal
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

try:
    import websockets
except ImportError:
    print("ERROR: 'websockets' package required. Install with:")
    print("  pip install websockets")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Region definition: Southeast Asian waters
# ---------------------------------------------------------------------------
# The region is large enough that we split it into sub-boxes to help
# AISStream route data efficiently. These overlap slightly at boundaries.

BOUNDING_BOXES = [
    # Box 1: Strait of Malacca + West Malaysia + Singapore
    # SW corner -> NE corner
    [[-2.0, 95.0], [8.0, 106.0]],

    # Box 2: South China Sea (southern portion) + East Malaysia + Brunei
    [[-1.0, 106.0], [8.0, 120.0]],

    # Box 3: Java Sea + Southern Borneo + Eastern Indonesia
    [[-11.0, 106.0], [-1.0, 142.0]],

    # Box 4: Celebes Sea + Eastern Borneo + Philippines border
    [[-1.0, 120.0], [8.0, 142.0]],

    # Box 5: Western Sumatra / Indian Ocean approach
    [[-8.0, 93.0], [-2.0, 106.0]],
]

# AIS message types we want for simulator seeding
POSITION_MSG_TYPES = [
    "PositionReport",               # Class A position (msg 1,2,3)
    "StandardClassBPositionReport",  # Class B position (msg 18)
    "ExtendedClassBPositionReport",  # Extended Class B (msg 19)
]

STATIC_MSG_TYPES = [
    "ShipStaticData",   # Class A static + voyage (msg 5)
    "StaticDataReport", # Class B static (msg 24)
]

ALL_MSG_TYPES = POSITION_MSG_TYPES + STATIC_MSG_TYPES

# Navigation status codes (ITU-R M.1371)
NAV_STATUS = {
    0: "Under way using engine",
    1: "At anchor",
    2: "Not under command",
    3: "Restricted manoeuvrability",
    4: "Constrained by draught",
    5: "Moored",
    6: "Aground",
    7: "Engaged in fishing",
    8: "Under way sailing",
    9: "Reserved (HSC)",
    10: "Reserved (WIG)",
    11: "Power-driven vessel towing astern",
    12: "Power-driven vessel pushing ahead/towing alongside",
    13: "Reserved",
    14: "AIS-SART / MOB / EPIRB",
    15: "Undefined (default)",
}


# ---------------------------------------------------------------------------
# CSV writers
# ---------------------------------------------------------------------------

POSITION_HEADERS = [
    "timestamp_utc",
    "mmsi",
    "ship_name",
    "message_type",
    "latitude",
    "longitude",
    "sog_knots",
    "cog_degrees",
    "true_heading",
    "rate_of_turn",
    "nav_status_code",
    "nav_status_text",
    "position_accuracy",
]

STATIC_HEADERS = [
    "timestamp_utc",
    "mmsi",
    "ship_name",
    "message_type",
    "imo_number",
    "call_sign",
    "vessel_name",
    "ship_type_code",
    "dim_a",
    "dim_b",
    "dim_c",
    "dim_d",
    "length_m",
    "beam_m",
    "draught_m",
    "destination",
    "eta_month",
    "eta_day",
    "eta_hour",
    "eta_minute",
]


class AISCapture:
    """Captures AIS data from AISStream.io and writes to CSV files."""

    def __init__(self, api_key: str, duration_minutes: int, output_dir: str):
        self.api_key = api_key
        self.duration = timedelta(minutes=duration_minutes)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.start_time = None
        self.stop_event = asyncio.Event()

        # Counters
        self.position_count = 0
        self.static_count = 0
        self.unique_mmsis = set()
        self.error_count = 0
        self.reconnect_count = 0

        # File handles (opened in start())
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        self.pos_path = self.output_dir / f"positions_{ts}.csv"
        self.static_path = self.output_dir / f"statics_{ts}.csv"
        self._pos_file = None
        self._static_file = None
        self._pos_writer = None
        self._static_writer = None

        # Logger
        self.log = logging.getLogger("ais_capture")

    def _open_files(self):
        self._pos_file = open(self.pos_path, "w", newline="", encoding="utf-8")
        self._static_file = open(self.static_path, "w", newline="", encoding="utf-8")
        self._pos_writer = csv.writer(self._pos_file)
        self._static_writer = csv.writer(self._static_file)
        self._pos_writer.writerow(POSITION_HEADERS)
        self._static_writer.writerow(STATIC_HEADERS)

    def _close_files(self):
        if self._pos_file:
            self._pos_file.close()
        if self._static_file:
            self._static_file.close()

    def _flush_files(self):
        if self._pos_file:
            self._pos_file.flush()
        if self._static_file:
            self._static_file.flush()

    # ------------------------------------------------------------------
    # Message processing
    # ------------------------------------------------------------------

    def _process_position(self, msg: dict, msg_type: str, metadata: dict):
        """Extract position fields from any position message type."""
        body = msg.get(msg_type, {})

        mmsi = body.get("UserID", metadata.get("MMSI", ""))
        ship_name = metadata.get("ShipName", "").strip()
        ts = metadata.get("time_utc", datetime.now(timezone.utc).isoformat())
        lat = body.get("Latitude", metadata.get("latitude"))
        lon = body.get("Longitude", metadata.get("longitude"))
        sog = body.get("Sog", "")
        cog = body.get("Cog", "")
        heading = body.get("TrueHeading", "")
        rot = body.get("RateOfTurn", "")
        nav_code = body.get("NavigationalStatus", "")
        nav_text = NAV_STATUS.get(nav_code, "") if isinstance(nav_code, int) else ""
        accuracy = body.get("PositionAccuracy", "")

        # Filter out invalid positions (0,0 or None)
        if lat is None or lon is None:
            return
        if abs(lat) < 0.001 and abs(lon) < 0.001:
            return
        # 511 = heading not available
        if heading == 511:
            heading = ""

        self._pos_writer.writerow([
            ts, mmsi, ship_name, msg_type,
            lat, lon, sog, cog, heading, rot,
            nav_code, nav_text, accuracy,
        ])

        self.position_count += 1
        self.unique_mmsis.add(mmsi)

    def _process_static(self, msg: dict, msg_type: str, metadata: dict):
        """Extract static/voyage fields."""
        body = msg.get(msg_type, {})

        mmsi = body.get("UserID", metadata.get("MMSI", ""))
        ship_name_meta = metadata.get("ShipName", "").strip()
        ts = metadata.get("time_utc", datetime.now(timezone.utc).isoformat())

        if msg_type == "ShipStaticData":
            imo = body.get("ImoNumber", "")
            callsign = body.get("CallSign", "").strip()
            name = body.get("Name", "").strip()
            ship_type = body.get("Type", "")
            dim = body.get("Dimension", {})
            draught = body.get("MaximumStaticDraught", "")
            dest = body.get("Destination", "").strip()
            eta = body.get("Eta", {})

            dim_a = dim.get("A", 0)
            dim_b = dim.get("B", 0)
            dim_c = dim.get("C", 0)
            dim_d = dim.get("D", 0)
            length = dim_a + dim_b if (dim_a and dim_b) else ""
            beam = dim_c + dim_d if (dim_c and dim_d) else ""

            self._static_writer.writerow([
                ts, mmsi, ship_name_meta, msg_type,
                imo, callsign, name, ship_type,
                dim_a, dim_b, dim_c, dim_d,
                length, beam, draught, dest,
                eta.get("Month", ""), eta.get("Day", ""),
                eta.get("Hour", ""), eta.get("Minute", ""),
            ])

        elif msg_type == "StaticDataReport":
            report_b = body.get("ReportB", {})
            report_a = body.get("ReportA", {})

            name = report_a.get("Name", "").strip() if report_a.get("Valid") else ""
            callsign = report_b.get("CallSign", "").strip() if report_b.get("Valid") else ""
            ship_type = report_b.get("ShipType", "") if report_b.get("Valid") else ""
            dim = report_b.get("Dimension", {}) if report_b.get("Valid") else {}

            dim_a = dim.get("A", 0)
            dim_b = dim.get("B", 0)
            dim_c = dim.get("C", 0)
            dim_d = dim.get("D", 0)
            length = dim_a + dim_b if (dim_a and dim_b) else ""
            beam = dim_c + dim_d if (dim_c and dim_d) else ""

            self._static_writer.writerow([
                ts, mmsi, ship_name_meta, msg_type,
                "", callsign, name, ship_type,
                dim_a, dim_b, dim_c, dim_d,
                length, beam, "", "",
                "", "", "", "",
            ])

        self.static_count += 1
        self.unique_mmsis.add(mmsi)

    def _process_message(self, raw: str):
        """Parse and route a single AIS message."""
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            self.error_count += 1
            return

        # Check for error messages
        if "error" in data:
            self.log.error(f"AISStream error: {data['error']}")
            self.error_count += 1
            return

        msg_type = data.get("MessageType", "")
        metadata = data.get("MetaData", {})
        message = data.get("Message", {})

        if msg_type in POSITION_MSG_TYPES:
            self._process_position(message, msg_type, metadata)
        elif msg_type in STATIC_MSG_TYPES:
            self._process_static(message, msg_type, metadata)

    # ------------------------------------------------------------------
    # Status display
    # ------------------------------------------------------------------

    def _print_status(self):
        elapsed = datetime.now(timezone.utc) - self.start_time
        remaining = self.duration - elapsed
        if remaining.total_seconds() < 0:
            remaining = timedelta(0)

        mins_elapsed = int(elapsed.total_seconds() // 60)
        secs_elapsed = int(elapsed.total_seconds() % 60)
        mins_remain = int(remaining.total_seconds() // 60)
        secs_remain = int(remaining.total_seconds() % 60)

        rate = self.position_count / max(elapsed.total_seconds(), 1)

        status = (
            f"\r  [{mins_elapsed:02d}:{secs_elapsed:02d} elapsed | "
            f"{mins_remain:02d}:{secs_remain:02d} remaining]  "
            f"Positions: {self.position_count:,}  "
            f"Statics: {self.static_count:,}  "
            f"Unique vessels: {len(self.unique_mmsis):,}  "
            f"Rate: {rate:.1f} pos/sec  "
            f"Errors: {self.error_count}"
        )
        print(status, end="", flush=True)

    # ------------------------------------------------------------------
    # WebSocket connection with reconnect
    # ------------------------------------------------------------------

    async def _connect_and_stream(self):
        """Single connection attempt. Returns normally on clean exit, raises on error."""
        subscription = {
            "APIKey": self.api_key,
            "BoundingBoxes": BOUNDING_BOXES,
            "FilterMessageTypes": ALL_MSG_TYPES,
        }

        self.log.info("Connecting to AISStream.io...")

        async with websockets.connect(
            "wss://stream.aisstream.io/v0/stream",
            ping_interval=20,
            ping_timeout=30,
            close_timeout=5,
            max_size=2**20,  # 1 MB max message
        ) as ws:
            await ws.send(json.dumps(subscription))
            self.log.info("Subscription sent. Waiting for data...")

            status_interval = 5  # seconds
            last_status = datetime.now(timezone.utc)
            flush_interval = 30  # seconds
            last_flush = datetime.now(timezone.utc)

            async for raw_msg in ws:
                # Check duration
                now = datetime.now(timezone.utc)
                if now - self.start_time >= self.duration:
                    self.log.info("\nCapture duration reached.")
                    self.stop_event.set()
                    return

                if self.stop_event.is_set():
                    return

                self._process_message(raw_msg)

                # Periodic status
                if (now - last_status).total_seconds() >= status_interval:
                    self._print_status()
                    last_status = now

                # Periodic flush
                if (now - last_flush).total_seconds() >= flush_interval:
                    self._flush_files()
                    last_flush = now

    async def run(self):
        """Main capture loop with automatic reconnection."""
        self._open_files()
        self.start_time = datetime.now(timezone.utc)

        print("=" * 72)
        print("  AIS Data Capture — Southeast Asian Waters")
        print(f"  Duration: {int(self.duration.total_seconds() // 60)} minutes")
        print(f"  Output:   {self.pos_path}")
        print(f"            {self.static_path}")
        print(f"  Region:   {len(BOUNDING_BOXES)} bounding boxes covering")
        print("            Strait of Malacca, South China Sea, Java Sea,")
        print("            Celebes Sea, Borneo, and surrounding waters")
        print(f"  Messages: {', '.join(ALL_MSG_TYPES)}")
        print("=" * 72)
        print("  Press Ctrl+C to stop early.\n")

        max_retries = 20
        retry_delay = 2  # seconds, doubles on each retry

        while not self.stop_event.is_set():
            try:
                await self._connect_and_stream()
            except (
                websockets.exceptions.ConnectionClosed,
                websockets.exceptions.ConnectionClosedError,
                websockets.exceptions.ConnectionClosedOK,
                ConnectionRefusedError,
                OSError,
            ) as e:
                self.reconnect_count += 1
                if self.reconnect_count > max_retries:
                    self.log.error(f"\nMax reconnect attempts ({max_retries}) reached. Stopping.")
                    break

                delay = min(retry_delay * (2 ** (self.reconnect_count - 1)), 60)
                self.log.warning(
                    f"\nConnection lost ({e.__class__.__name__}). "
                    f"Reconnecting in {delay}s (attempt {self.reconnect_count}/{max_retries})..."
                )
                await asyncio.sleep(delay)
            except asyncio.CancelledError:
                break

        # Final flush and close
        self._flush_files()
        self._close_files()

        # Summary
        elapsed = datetime.now(timezone.utc) - self.start_time
        print("\n")
        print("=" * 72)
        print("  CAPTURE COMPLETE")
        print(f"  Duration:        {int(elapsed.total_seconds() // 60)}m {int(elapsed.total_seconds() % 60)}s")
        print(f"  Position records: {self.position_count:,}")
        print(f"  Static records:   {self.static_count:,}")
        print(f"  Unique vessels:   {len(self.unique_mmsis):,}")
        print(f"  Reconnections:    {self.reconnect_count}")
        print(f"  Errors:           {self.error_count}")
        print(f"  Files:")
        print(f"    {self.pos_path}  ({self.pos_path.stat().st_size / 1024:.1f} KB)")
        print(f"    {self.static_path}  ({self.static_path.stat().st_size / 1024:.1f} KB)")
        print("=" * 72)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Capture AIS data from AISStream.io for Southeast Asian waters.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Capture 2 hours of data:
  python ais_capture.py --api-key abc123def456 --duration 120

  # Quick 5-minute test capture:
  python ais_capture.py --api-key abc123def456 --duration 5 --output ./test_data

  # Use environment variable for API key:
  export AISSTREAM_API_KEY=abc123def456
  python ais_capture.py --duration 120
        """,
    )
    parser.add_argument(
        "--api-key",
        default=os.environ.get("AISSTREAM_API_KEY", ""),
        help="AISStream.io API key (or set AISSTREAM_API_KEY env var)",
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=120,
        help="Capture duration in minutes (default: 120)",
    )
    parser.add_argument(
        "--output",
        default="./ais_data",
        help="Output directory (default: ./ais_data)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    if not args.api_key:
        print("ERROR: API key required.")
        print("  Get one free at: https://aisstream.io/authenticate")
        print("  Then: python ais_capture.py --api-key YOUR_KEY")
        print("  Or:   export AISSTREAM_API_KEY=YOUR_KEY")
        sys.exit(1)

    # Logging
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    capture = AISCapture(
        api_key=args.api_key,
        duration_minutes=args.duration,
        output_dir=args.output,
    )

    # Handle Ctrl+C gracefully
    loop = asyncio.new_event_loop()

    def signal_handler():
        print("\n\n  Ctrl+C received — finishing up...")
        capture.stop_event.set()

    try:
        loop.add_signal_handler(signal.SIGINT, signal_handler)
    except NotImplementedError:
        # Windows doesn't support add_signal_handler
        pass

    try:
        loop.run_until_complete(capture.run())
    except KeyboardInterrupt:
        capture.stop_event.set()
        # Give it a moment to flush
        loop.run_until_complete(asyncio.sleep(0.5))
    finally:
        loop.close()


if __name__ == "__main__":
    main()
