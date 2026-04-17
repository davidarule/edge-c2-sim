"""
Validate one scenario file or every scenario in config/scenarios/.

Usage:
    python scripts/validate_scenarios.py                       # all *.yaml in config/scenarios/
    python scripts/validate_scenarios.py path/to/scenario.yaml # single file
    python scripts/validate_scenarios.py path/to/dir           # all *.yaml in dir
"""

import sys
from pathlib import Path

from scripts.validate_scenario import validate

DEFAULT_DIR = Path(__file__).resolve().parent.parent / "config" / "scenarios"


def collect_targets(arg: str | None) -> list[Path]:
    target = Path(arg) if arg else DEFAULT_DIR
    if target.is_file():
        return [target]
    if target.is_dir():
        return sorted(target.glob("*.yaml"))
    print(f"Error: {target} is not a file or directory")
    sys.exit(2)


def main() -> None:
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    targets = collect_targets(arg)

    if not targets:
        print(f"No YAML files found in {arg or DEFAULT_DIR}")
        sys.exit(1)

    results: list[tuple[Path, bool]] = []
    for path in targets:
        print("=" * 70)
        ok = validate(str(path))
        results.append((path, ok))
        print()

    print("=" * 70)
    print("Summary")
    print("=" * 70)
    passed = sum(1 for _, ok in results if ok)
    failed = len(results) - passed
    for path, ok in results:
        marker = "PASS" if ok else "FAIL"
        print(f"  {marker}  {path}")
    print(f"\n{passed}/{len(results)} passed, {failed} failed")

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
