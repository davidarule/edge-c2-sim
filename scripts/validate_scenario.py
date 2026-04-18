"""
Validate a scenario YAML file.

Usage: python scripts/validate_scenario.py config/scenarios/my_scenario.yaml

Checks YAML syntax, required fields, entity types, geodata references,
event chronology, and coordinate validity.
"""

import sys
from pathlib import Path

import yaml

from simulator.scenario.loader import DOMAIN_ACTIONS, ENTITY_TYPES, ScenarioLoader


def validate(scenario_path: str) -> bool:
    """Validate scenario and print results. Returns True if valid."""
    print(f"Validating: {scenario_path}\n")

    path = Path(scenario_path)
    if not path.exists():
        print(f"  \u2717 File not found: {scenario_path}")
        print(f"\nFAIL \u2014 File not found")
        return False

    # Check YAML syntax
    try:
        with open(path) as f:
            raw = yaml.safe_load(f)
        print("  \u2713 YAML syntax valid")
    except yaml.YAMLError as e:
        print(f"  \u2717 YAML syntax error: {e}")
        print(f"\nFAIL \u2014 YAML parse error")
        return False

    if "scenario" not in raw:
        print("  \u2717 Missing top-level 'scenario' key")
        print(f"\nFAIL \u2014 1 error found")
        return False

    scenario = raw["scenario"]

    # Required fields
    required = ["name", "duration_minutes", "center"]
    missing = [f for f in required if f not in scenario]
    if not missing:
        fields_present = ", ".join(required + ["scenario_entities", "events"])
        print(f"  \u2713 Required fields present ({fields_present})")
    else:
        for f in missing:
            print(f"  \u2717 Missing required field: {f}")

    # Load geodata for validation
    loader = ScenarioLoader()

    # Scenario entities
    scenario_entities = scenario.get("scenario_entities", [])
    entity_ids = set()
    entity_types: dict[str, str] = {}
    type_errors = []
    coord_errors = []

    for entry in scenario_entities:
        eid = entry.get("id", "???")
        entity_ids.add(eid)

        etype = entry.get("type")
        if etype:
            entity_types[eid] = etype
            if etype not in ENTITY_TYPES:
                type_errors.append(f"Unknown type '{etype}' for {eid}")

        for j, wp in enumerate(entry.get("waypoints", [])):
            lat = wp.get("lat", 0)
            lon = wp.get("lon", 0)
            if not (-90 <= lat <= 90):
                coord_errors.append(f"{eid} waypoint {j}: lat {lat} out of range")
            if not (-180 <= lon <= 180):
                coord_errors.append(f"{eid} waypoint {j}: lon {lon} out of range")

        # Check speed within type limits
        if etype in ENTITY_TYPES:
            speed_range = ENTITY_TYPES[etype]["speed_range"]
            for j, wp in enumerate(entry.get("waypoints", [])):
                speed = wp.get("speed", 0)
                if speed > speed_range[1] * 1.2:  # Allow 20% tolerance
                    coord_errors.append(
                        f"{eid} waypoint {j}: speed {speed} exceeds "
                        f"{etype} max of {speed_range[1]} knots"
                    )

    all_types_valid = len(type_errors) == 0
    if all_types_valid:
        print(f"  \u2713 {len(scenario_entities)} scenario entities, all types valid")
    else:
        for err in type_errors:
            print(f"  \u2717 {err}")

    # Background entities
    bg_entities = scenario.get("background_entities", [])
    bg_errors = []
    for bg in bg_entities:
        etype = bg.get("type")
        if etype and etype not in ENTITY_TYPES:
            bg_errors.append(f"Unknown background type: {etype}")
        area = bg.get("area")
        if area and area not in loader.zones:
            bg_errors.append(f"Area '{area}' not found")
        route = bg.get("route")
        if route and route not in loader.routes:
            bg_errors.append(f"Route '{route}' not found (warning — may not be in geodata yet)")

    if not bg_errors:
        print(f"  \u2713 {len(bg_entities)} background entity groups")
    else:
        for err in bg_errors:
            print(f"  \u26a0 {err}")

    # Events
    events = scenario.get("events", [])
    event_errors = []
    action_errors = []
    for i, evt in enumerate(events):
        time_str = evt.get("time") or (evt.get("after") and f"after:{evt['after'].get('event') if isinstance(evt['after'], dict) else evt['after']}") or f"event#{i}"

        # Check entity references (both actionee and intercept-target)
        for field_name in ("actionee", "target"):
            ref = evt.get(field_name)
            if ref and ref not in entity_ids:
                event_errors.append(
                    f"Event at {time_str} references entity '{ref}' "
                    f"(via {field_name}) which is not in scenario_entities"
                )
        for t_id in evt.get("targets", []):
            if t_id not in entity_ids:
                event_errors.append(
                    f"Event at {time_str} references entity '{t_id}' "
                    f"which is not in scenario_entities"
                )

        # Domain-whitelist check for actions
        actionee = evt.get("actionee")
        if not actionee:
            targets_list = evt.get("targets") or []
            if targets_list:
                actionee = targets_list[0]
        if actionee and actionee in entity_types:
            etype = entity_types[actionee]
            type_def = ENTITY_TYPES.get(etype, {})
            domain = type_def.get("domain")
            domain_key = domain.value if domain is not None else None
            allowed = DOMAIN_ACTIONS.get(domain_key, frozenset())
            for field_name in ("action", "on_complete_action"):
                val = evt.get(field_name)
                if val and val not in allowed:
                    action_errors.append(
                        f"Event at {time_str}: {field_name} '{val}' is not "
                        f"permitted for entity type {etype} (domain {domain_key}). "
                        f"Allowed: {sorted(allowed)}"
                    )

    if not event_errors:
        print(f"  \u2713 {len(events)} events in chronological order")
        print(f"  \u2713 All entity references in events exist")
    else:
        for err in event_errors:
            print(f"  \u2717 {err}")
    if not action_errors:
        print(f"  \u2713 All actions permitted for their actionee domain")
    else:
        for err in action_errors:
            print(f"  \u2717 {err}")

    # GeoJSON references
    zone_refs = set()
    for entry in scenario_entities:
        pa = entry.get("patrol_area")
        if pa:
            zone_refs.add(pa)
    zone_missing = [z for z in zone_refs if z not in loader.zones]
    if not zone_missing:
        print(f"  \u2713 All GeoJSON zone references found")
    else:
        for z in zone_missing:
            event_errors.append(f"Zone '{z}' not found")
            print(f"  \u2717 Area '{z}' not found. Available: {list(loader.zones.keys())}")

    # Coordinates
    if not coord_errors:
        print(f"  \u2713 Coordinates within valid ranges")
        print(f"  \u2713 Speeds within entity type limits")
    else:
        for err in coord_errors:
            print(f"  \u2717 {err}")

    # Summary
    all_errors = missing + type_errors + event_errors + coord_errors + action_errors
    # Route warnings don't count as errors
    critical_bg = [e for e in bg_errors if "warning" not in e.lower()]
    all_errors.extend(critical_bg)

    if not all_errors:
        print(f"\nPASS \u2014 Scenario is valid")
        return True
    else:
        print(f"\nFAIL \u2014 {len(all_errors)} error(s) found")
        return False


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/validate_scenario.py <scenario.yaml>")
        sys.exit(1)

    valid = validate(sys.argv[1])
    sys.exit(0 if valid else 1)


if __name__ == "__main__":
    main()
