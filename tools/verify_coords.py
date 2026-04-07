#!/usr/bin/env python3
"""
verify_coords.py — Terrain validator for scenario coordinates.

Checks whether lat/lon positions are valid for their domain (MARITIME,
GROUND_VEHICLE, PERSONNEL, AIR) using the global-land-mask GLOBE dataset.

KNOWN LIMITATION
----------------
The global-land-mask GLOBE dataset has poor coverage of shallow, semi-enclosed
Southeast Asian seas (Malacca Strait, Sulu Sea, Java Sea). These bodies of
water are often misclassified as land. For coastal and strait operations, add
``skip: true`` to the YAML entry (or ``skip_terrain_check: true`` in scenario
entity metadata) to suppress the check for known-good positions.

A COASTAL WARNING is emitted instead of a hard FAIL when the terrain library
flags a point as invalid BUT a valid point for that domain exists within
~1 km — this typically indicates a coastline edge-case rather than a genuine
error. Hard FAILs are reserved for points where no nearby valid cell exists
(entity truly placed on wrong terrain).

Usage
-----
    # Batch mode — YAML list of {name, lat, lon, domain}
    python tools/verify_coords.py coords.yaml

    # Batch mode — validate initial_positions from a scenario file
    python tools/verify_coords.py config/scenarios/scn_mal_01.yaml

    # Spot-check mode
    python tools/verify_coords.py --lat 2.82 --lon 102.55 --domain MARITIME

YAML list format::

    - name: "KD Keris"
      lat: 2.12
      lon: 101.90
      domain: MARITIME

    - name: "RMAF Subang"
      lat: 3.12
      lon: 101.65
      domain: AIR          # AIR always passes

    - name: "Coastal vessel (known good)"
      lat: 2.82
      lon: 102.55
      domain: MARITIME
      skip: true           # Suppress terrain check (coastal edge case)

Exit codes
----------
  0  All entries passed or warned (no hard failures)
  1  One or more hard failures (entity on clearly wrong terrain)
"""

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import yaml

from simulator.movement.terrain import find_nearest_valid_point, validate_position

# ANSI colours — disabled when stdout is not a tty
_TTY = sys.stdout.isatty()
_GRN = "\033[32m"  if _TTY else ""
_RED = "\033[31m"  if _TTY else ""
_YLW = "\033[33m"  if _TTY else ""
_CYN = "\033[36m"  if _TTY else ""
_DIM = "\033[2m"   if _TTY else ""
_RST = "\033[0m"   if _TTY else ""
_BLD = "\033[1m"   if _TTY else ""

# Distance threshold for "coastal warning" vs hard fail.
# find_nearest_valid_point searches up to COAST_RADIUS_DEG away.
# If it finds a valid point, the original point is near the coast.
_COAST_RADIUS_DEG = 0.05   # ~5.5 km — within this: WARN, beyond: FAIL


def check_entry(name: str, lat: float, lon: float, domain: str,
                skip: bool = False) -> dict:
    """Validate one entry and return a result dict."""
    domain = domain.upper()

    if skip or domain == "AIR":
        return {
            "name": name, "lat": lat, "lon": lon, "domain": domain,
            "status": "skip", "suggestion": None, "skip": skip,
        }

    valid = validate_position(lat, lon, domain)
    if valid:
        return {
            "name": name, "lat": lat, "lon": lon, "domain": domain,
            "status": "pass", "suggestion": None, "skip": False,
        }

    # Invalid — check whether a nearby valid point exists to distinguish
    # coastal edge-cases from genuine placement errors.
    suggestion = find_nearest_valid_point(lat, lon, domain,
                                          search_radius_deg=_COAST_RADIUS_DEG)
    status = "warn" if suggestion else "fail"
    return {
        "name": name, "lat": lat, "lon": lon, "domain": domain,
        "status": status, "suggestion": suggestion, "skip": False,
    }


def _fmt_ll(lat: float, lon: float) -> str:
    return f"{lat:>9.4f}, {lon:>10.4f}"


def print_table(results: list[dict]) -> int:
    """Print a formatted result table. Returns number of hard failures."""
    col_name   = max((len(r["name"]) for r in results), default=4)
    col_name   = max(col_name, 4)
    col_domain = 14

    header = (
        f"  {'NAME':<{col_name}}  {'DOMAIN':<{col_domain}}  "
        f"{'LAT':>9}  {'LON':>10}  STATUS"
    )
    sep = "  " + "─" * (len(header) - 2)

    print()
    print(f"{_BLD}{header}{_RST}")
    print(sep)

    hard_fails = 0
    coastal_warns = 0
    skipped = 0

    for r in results:
        s = r["status"]
        if s == "pass":
            tag = f"{_GRN}✓ PASS{_RST}"
        elif s == "warn":
            tag = f"{_YLW}⚠ COASTAL{_RST}"
            coastal_warns += 1
        elif s == "fail":
            tag = f"{_RED}✗ FAIL{_RST}"
            hard_fails += 1
        else:  # skip
            reason = "AIR" if r["domain"] == "AIR" else "skip=true"
            tag = f"{_DIM}– SKIP ({reason}){_RST}"
            skipped += 1

        print(
            f"  {r['name']:<{col_name}}  {r['domain']:<{col_domain}}  "
            f"{_fmt_ll(r['lat'], r['lon'])}  {tag}"
        )

        if s == "warn":
            slat, slon = r["suggestion"]
            print(
                f"  {'':<{col_name}}  {_YLW}↳ nearest valid  "
                f"{_fmt_ll(slat, slon)}  "
                f"(Δ {abs(slat-r['lat'])*111:.1f} km N/S,  "
                f"{abs(slon-r['lon'])*111:.1f} km E/W){_RST}"
            )
            print(
                f"  {'':<{col_name}}  {_DIM}  Add skip: true if this is a known coastal/strait position.{_RST}"
            )
        elif s == "fail":
            print(
                f"  {'':<{col_name}}  {_RED}↳ no valid {r['domain']} point found within "
                f"{_COAST_RADIUS_DEG*111:.0f} km — check coordinates{_RST}"
            )

    print(sep)

    total = len(results)
    passed = sum(1 for r in results if r["status"] == "pass")

    parts = []
    if passed:
        parts.append(f"{_GRN}{passed} passed{_RST}")
    if coastal_warns:
        parts.append(f"{_YLW}{coastal_warns} coastal warning{'s' if coastal_warns != 1 else ''}{_RST}")
    if hard_fails:
        parts.append(f"{_RED}{_BLD}{hard_fails} hard failure{'s' if hard_fails != 1 else ''}{_RST}")
    if skipped:
        parts.append(f"{_DIM}{skipped} skipped{_RST}")
    print(f"  {',  '.join(parts)}  {_DIM}(of {total} checked){_RST}")

    if coastal_warns:
        print(
            f"\n  {_YLW}Note:{_RST} Coastal warnings are likely false positives from the 1 km land mask.\n"
            f"  Add {_CYN}skip: true{_RST} to suppress, or {_CYN}skip_terrain_check: true{_RST} in scenario entity metadata.\n"
            f"  See: simulator/movement/terrain.py"
        )
    print()

    return hard_fails


# ── YAML parsing ────────────────────────────────────────────────────────────

_TYPE_PREFIXES: list[tuple[str, str]] = [
    ("RMAF_", "AIR"), ("CIVILIAN_COMMERCIAL", "AIR"), ("CIVILIAN_LIGHT", "AIR"),
    ("CIVILIAN_CARGO", "MARITIME"), ("CIVILIAN_TANKER", "MARITIME"),
    ("CIVILIAN_FISHING", "MARITIME"), ("CIVILIAN_BOAT", "MARITIME"),
    ("CIVILIAN_PASSENGER", "MARITIME"), ("SUSPECT_VESSEL", "MARITIME"),
    ("MMEA_", "MARITIME"), ("MIL_NAVAL", "MARITIME"), ("RMP_MARINE", "MARITIME"),
    ("RMP_PATROL_BOAT", "MARITIME"), ("RMP_PATROL_CAR", "GROUND_VEHICLE"),
    ("MIL_VEHICLE", "GROUND_VEHICLE"), ("MIL_APC", "GROUND_VEHICLE"),
    ("MIL_INFANTRY", "PERSONNEL"), ("RMP_OFFICER", "PERSONNEL"),
    ("CI_", "PERSONNEL"), ("HOSTILE_VESSEL", "MARITIME"),
    ("HOSTILE_PERSONNEL", "PERSONNEL"),
]


def _infer_domain(entity_type: str) -> str:
    for prefix, domain in _TYPE_PREFIXES:
        if entity_type.startswith(prefix) or entity_type == prefix.rstrip("_"):
            return domain
    return ""


def _normalise_entries(raw: list, source: str) -> list[dict]:
    out = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            print(f"{_YLW}Warning: skipping non-dict entry {i} in {source}{_RST}",
                  file=sys.stderr)
            continue
        name   = str(item.get("name", f"entry-{i}"))
        lat    = item.get("lat") or item.get("latitude")
        lon    = item.get("lon") or item.get("longitude")
        domain = item.get("domain", "")
        skip   = bool(item.get("skip", False))

        if lat is None or lon is None:
            print(f"{_YLW}Warning: skipping '{name}' — missing lat/lon{_RST}",
                  file=sys.stderr)
            continue
        if not domain:
            print(f"{_YLW}Warning: skipping '{name}' — missing domain{_RST}",
                  file=sys.stderr)
            continue
        out.append({
            "name": name, "lat": float(lat), "lon": float(lon),
            "domain": domain.upper(), "skip": skip,
        })
    return out


def load_yaml_entries(path: Path) -> list[dict]:
    """Load entries from a YAML file (list or scenario format)."""
    with open(path) as f:
        data = yaml.safe_load(f)

    # Plain list
    if isinstance(data, list):
        return _normalise_entries(data, str(path))

    # Scenario YAML
    if isinstance(data, dict) and "scenario" in data:
        scenario = data["scenario"]
        entries = []
        for ent in scenario.get("scenario_entities", []):
            name   = ent.get("id") or ent.get("callsign") or "unnamed"
            pos    = ent.get("initial_position") or {}
            lat    = pos.get("lat") or pos.get("latitude")
            lon    = pos.get("lon") or pos.get("longitude")
            domain = ent.get("domain") or _infer_domain(ent.get("type", ""))
            skip   = bool(ent.get("metadata", {}).get("skip_terrain_check", False))

            if lat is not None and lon is not None and domain:
                entries.append({
                    "name": name, "lat": float(lat), "lon": float(lon),
                    "domain": domain, "skip": skip,
                })
        if not entries:
            print(
                f"{_YLW}Warning: no scenario_entities found in {path}{_RST}\n"
                "Use a plain list file for non-scenario YAML.",
                file=sys.stderr,
            )
        return entries

    # Fallback: top-level dict with name keys
    if isinstance(data, dict):
        entries = []
        for key, val in data.items():
            if isinstance(val, dict) and ("lat" in val or "latitude" in val):
                entries.append({"name": key, **val})
        if entries:
            return _normalise_entries(entries, str(path))

    raise ValueError(
        f"{path}: unrecognised format. "
        "Expected a list of {name, lat, lon, domain} or a scenario YAML."
    )


# ── Entry point ─────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate lat/lon positions against terrain (land vs water).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "file", nargs="?", type=Path,
        help="YAML coordinate list or scenario file.",
    )
    parser.add_argument("--lat",    type=float, help="Latitude  (spot-check mode)")
    parser.add_argument("--lon",    type=float, help="Longitude (spot-check mode)")
    parser.add_argument("--domain", type=str,
                        help="Domain: MARITIME / AIR / GROUND_VEHICLE / PERSONNEL")
    parser.add_argument("--name",   type=str, default="spot-check",
                        help="Label for spot-check output")
    parser.add_argument("--skip",   action="store_true",
                        help="Skip terrain check (spot-check mode)")

    args = parser.parse_args()

    # ── Spot-check mode ──
    if args.lat is not None or args.lon is not None or args.domain is not None:
        missing = [f for f, v in [("--lat", args.lat), ("--lon", args.lon),
                                   ("--domain", args.domain)] if v is None]
        if missing:
            parser.error(f"Spot-check mode requires: {', '.join(missing)}")
        results = [check_entry(args.name, args.lat, args.lon,
                               args.domain, skip=args.skip)]
        return 1 if print_table(results) else 0

    # ── Batch mode ──
    if args.file is None:
        parser.error("Provide a YAML file or --lat/--lon/--domain for spot-check")

    if not args.file.exists():
        print(f"{_RED}Error: file not found: {args.file}{_RST}", file=sys.stderr)
        return 1

    try:
        entries = load_yaml_entries(args.file)
    except (ValueError, yaml.YAMLError) as e:
        print(f"{_RED}Error loading {args.file}: {e}{_RST}", file=sys.stderr)
        return 1

    if not entries:
        print(f"{_YLW}No entries to validate.{_RST}")
        return 0

    print(f"{_DIM}Validating {len(entries)} coordinate(s) from {args.file}…{_RST}")

    results = [
        check_entry(e["name"], e["lat"], e["lon"], e["domain"], skip=e.get("skip", False))
        for e in entries
    ]
    hard_fails = print_table(results)
    return 1 if hard_fails else 0


if __name__ == "__main__":
    sys.exit(main())
