"""
Terrain validator — ensures entities stay in their correct domain.

Maritime entities must be on water, ground entities on land.
Uses global-land-mask (GLOBE dataset, ~1km resolution) for fast
offline land/water classification.
"""

import logging
from functools import lru_cache

import numpy as np
from global_land_mask import globe

logger = logging.getLogger(__name__)

# Buffer: points within this many degrees of coastline are "ambiguous"
# ~1km ≈ 0.009° at equator. We use a small buffer for port/coastal ops.
COAST_BUFFER_DEG = 0.01


def is_land(lat: float, lon: float) -> bool:
    """Check if a single point is on land."""
    return bool(globe.is_land(lat, lon))


def is_water(lat: float, lon: float) -> bool:
    """Check if a single point is on water."""
    return bool(globe.is_ocean(lat, lon))


def validate_position(lat: float, lon: float, domain: str) -> bool:
    """Check if position is valid for the given domain.

    Returns True if valid, False if the entity would be on wrong terrain.
    AIR domain is always valid.
    """
    if domain == "AIR":
        return True
    on_land = is_land(lat, lon)
    if domain == "MARITIME":
        return not on_land
    if domain in ("GROUND_VEHICLE", "PERSONNEL"):
        return on_land
    return True


def validate_waypoints_batch(
    lats: list[float], lons: list[float], domain: str
) -> list[int]:
    """Return indices of invalid waypoints for the domain.

    Uses vectorized NumPy check for performance.
    """
    if domain == "AIR" or not lats:
        return []

    lat_arr = np.array(lats, dtype=np.float64)
    lon_arr = np.array(lons, dtype=np.float64)
    on_land = globe.is_land(lat_arr, lon_arr)

    if domain == "MARITIME":
        invalid = np.where(on_land)[0]
    elif domain in ("GROUND_VEHICLE", "PERSONNEL"):
        invalid = np.where(~on_land)[0]
    else:
        return []

    return invalid.tolist()


def find_nearest_valid_point(
    lat: float, lon: float, domain: str,
    search_radius_deg: float = 0.05, steps: int = 8
) -> tuple[float, float] | None:
    """Search nearby for a valid point in the given domain.

    Searches in concentric rings around the invalid point.
    Returns (lat, lon) of nearest valid point, or None if not found.
    """
    import math

    for ring in range(1, 6):
        radius = search_radius_deg * ring / 5
        for i in range(steps * ring):
            angle = 2 * math.pi * i / (steps * ring)
            test_lat = lat + radius * math.sin(angle)
            test_lon = lon + radius * math.cos(angle)
            if validate_position(test_lat, test_lon, domain):
                return test_lat, test_lon

    return None


def fix_waypoint_terrain(
    waypoints: list[dict], domain: str
) -> tuple[list[dict], int]:
    """Validate waypoints and fix any that are on wrong terrain.

    Args:
        waypoints: List of dicts with 'lat' and 'lon' keys.
        domain: Entity domain string.

    Returns:
        (fixed_waypoints, fix_count) — modified list and number of fixes applied.
    """
    if domain == "AIR":
        return waypoints, 0

    lats = [wp["lat"] for wp in waypoints]
    lons = [wp["lon"] for wp in waypoints]
    invalid_indices = validate_waypoints_batch(lats, lons, domain)

    if not invalid_indices:
        return waypoints, 0

    fixed = list(waypoints)
    fix_count = 0

    for idx in invalid_indices:
        wp = fixed[idx]
        correction = find_nearest_valid_point(wp["lat"], wp["lon"], domain)
        if correction:
            logger.info(
                f"Terrain fix: ({wp['lat']:.4f}, {wp['lon']:.4f}) -> "
                f"({correction[0]:.4f}, {correction[1]:.4f}) [{domain}]"
            )
            fixed[idx] = {**wp, "lat": correction[0], "lon": correction[1]}
            fix_count += 1
        else:
            logger.warning(
                f"Terrain fix FAILED: ({wp['lat']:.4f}, {wp['lon']:.4f}) "
                f"no valid {domain} point within search radius"
            )

    return fixed, fix_count
