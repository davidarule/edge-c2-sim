#!/usr/bin/env python3
"""
AIS Data Post-Processor
========================
Merges position and static CSV files from ais_capture.py into a single
simulator-ready dataset with one row per vessel position, enriched with
vessel metadata (name, type, dimensions, destination).

Also generates a summary report and a vessel catalogue.

Usage:
  python ais_postprocess.py --positions positions_*.csv --statics statics_*.csv

Author: David Rule / BrumbieSoft
"""

import argparse
import csv
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

# AIS ship type codes to human-readable categories
SHIP_TYPE_MAP = {
    range(20, 30): "Wing in Ground",
    range(30, 36): "Fishing / Towing / Dredging",
    range(36, 40): "Sailing / Pleasure / HSC",
    range(40, 50): "High Speed Craft",
    range(50, 60): "Pilot / SAR / Tug / Port Tender / Anti-pollution / Law / Medical",
    range(60, 70): "Passenger",
    range(70, 80): "Cargo",
    range(80, 90): "Tanker",
    range(90, 100): "Other",
}


def get_ship_category(type_code):
    """Map AIS ship type code to a category string."""
    if not type_code:
        return "Unknown"
    try:
        code = int(type_code)
    except (ValueError, TypeError):
        return "Unknown"
    for code_range, category in SHIP_TYPE_MAP.items():
        if code in code_range:
            return category
    return f"Type {code}"


def load_statics(statics_path: str) -> dict:
    """Load static data CSV, keeping the most recent record per MMSI."""
    vessels = {}
    count = 0
    with open(statics_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            mmsi = row.get("mmsi", "")
            if not mmsi:
                continue

            # Keep the record with the most data (prefer ShipStaticData over StaticDataReport)
            existing = vessels.get(mmsi)
            if existing and existing.get("message_type") == "ShipStaticData" and row.get("message_type") != "ShipStaticData":
                continue

            vessels[mmsi] = row
            count += 1

    return vessels, count


def merge_and_write(positions_path: str, statics: dict, output_path: str):
    """Merge position records with static data and write enriched CSV."""

    MERGED_HEADERS = [
        "timestamp_utc",
        "mmsi",
        "ship_name",
        "imo_number",
        "call_sign",
        "ship_type_code",
        "ship_category",
        "latitude",
        "longitude",
        "sog_knots",
        "cog_degrees",
        "true_heading",
        "rate_of_turn",
        "nav_status_code",
        "nav_status_text",
        "position_accuracy",
        "length_m",
        "beam_m",
        "draught_m",
        "destination",
    ]

    pos_count = 0
    enriched_count = 0
    unique_mmsis = set()

    with open(positions_path, "r", encoding="utf-8") as fin, \
         open(output_path, "w", newline="", encoding="utf-8") as fout:

        reader = csv.DictReader(fin)
        writer = csv.DictWriter(fout, fieldnames=MERGED_HEADERS)
        writer.writeheader()

        for row in reader:
            mmsi = row.get("mmsi", "")
            unique_mmsis.add(mmsi)
            static = statics.get(mmsi, {})

            # Use static name if position name is empty
            name = row.get("ship_name", "").strip()
            if not name:
                name = static.get("vessel_name", "").strip() or static.get("ship_name", "").strip()

            ship_type = static.get("ship_type_code", "")
            category = get_ship_category(ship_type)

            merged_row = {
                "timestamp_utc": row.get("timestamp_utc", ""),
                "mmsi": mmsi,
                "ship_name": name,
                "imo_number": static.get("imo_number", ""),
                "call_sign": static.get("call_sign", ""),
                "ship_type_code": ship_type,
                "ship_category": category,
                "latitude": row.get("latitude", ""),
                "longitude": row.get("longitude", ""),
                "sog_knots": row.get("sog_knots", ""),
                "cog_degrees": row.get("cog_degrees", ""),
                "true_heading": row.get("true_heading", ""),
                "rate_of_turn": row.get("rate_of_turn", ""),
                "nav_status_code": row.get("nav_status_code", ""),
                "nav_status_text": row.get("nav_status_text", ""),
                "position_accuracy": row.get("position_accuracy", ""),
                "length_m": static.get("length_m", ""),
                "beam_m": static.get("beam_m", ""),
                "draught_m": static.get("draught_m", ""),
                "destination": static.get("destination", ""),
            }

            writer.writerow(merged_row)
            pos_count += 1
            if static:
                enriched_count += 1

    return pos_count, enriched_count, len(unique_mmsis)


def generate_vessel_catalogue(statics: dict, output_path: str):
    """Generate a vessel catalogue CSV from static data."""
    CATALOGUE_HEADERS = [
        "mmsi",
        "imo_number",
        "ship_name",
        "call_sign",
        "ship_type_code",
        "ship_category",
        "length_m",
        "beam_m",
        "draught_m",
        "destination",
    ]

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CATALOGUE_HEADERS)
        writer.writeheader()

        for mmsi, data in sorted(statics.items()):
            name = data.get("vessel_name", "").strip() or data.get("ship_name", "").strip()
            ship_type = data.get("ship_type_code", "")

            writer.writerow({
                "mmsi": mmsi,
                "imo_number": data.get("imo_number", ""),
                "ship_name": name,
                "call_sign": data.get("call_sign", ""),
                "ship_type_code": ship_type,
                "ship_category": get_ship_category(ship_type),
                "length_m": data.get("length_m", ""),
                "beam_m": data.get("beam_m", ""),
                "draught_m": data.get("draught_m", ""),
                "destination": data.get("destination", ""),
            })

    return len(statics)


def generate_summary(stats: dict, output_path: str):
    """Write a JSON summary report."""
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2, default=str)


def main():
    parser = argparse.ArgumentParser(
        description="Merge AIS position and static data into a simulator-ready dataset.",
    )
    parser.add_argument("--positions", required=True, help="Path to positions CSV")
    parser.add_argument("--statics", required=True, help="Path to statics CSV")
    parser.add_argument("--output-dir", default="./ais_data", help="Output directory")

    args = parser.parse_args()
    outdir = Path(args.output_dir)
    outdir.mkdir(parents=True, exist_ok=True)

    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")

    # Load static data
    print(f"Loading static data from {args.statics}...")
    statics, static_records = load_statics(args.statics)
    print(f"  Loaded {static_records:,} static records for {len(statics):,} unique vessels")

    # Merge
    merged_path = outdir / f"sim_seed_{ts}.csv"
    print(f"\nMerging with positions from {args.positions}...")
    pos_count, enriched, unique = merge_and_write(args.positions, statics, str(merged_path))
    enrichment_pct = (enriched / pos_count * 100) if pos_count else 0
    print(f"  {pos_count:,} position records")
    print(f"  {unique:,} unique vessels")
    print(f"  {enrichment_pct:.1f}% of positions enriched with static data")

    # Vessel catalogue
    catalogue_path = outdir / f"vessel_catalogue_{ts}.csv"
    cat_count = generate_vessel_catalogue(statics, str(catalogue_path))
    print(f"\nVessel catalogue: {cat_count:,} vessels -> {catalogue_path}")

    # Summary
    summary = {
        "generated_utc": datetime.utcnow().isoformat(),
        "source_positions": args.positions,
        "source_statics": args.statics,
        "position_records": pos_count,
        "static_records": static_records,
        "unique_vessels": unique,
        "vessels_with_metadata": len(statics),
        "enrichment_pct": round(enrichment_pct, 1),
        "output_files": {
            "merged": str(merged_path),
            "catalogue": str(catalogue_path),
        },
    }
    summary_path = outdir / f"capture_summary_{ts}.json"
    generate_summary(summary, str(summary_path))

    print(f"\n{'=' * 60}")
    print(f"  OUTPUT FILES:")
    print(f"    Merged data:      {merged_path}")
    print(f"    Vessel catalogue: {catalogue_path}")
    print(f"    Summary:          {summary_path}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
