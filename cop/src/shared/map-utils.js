/**
 * Shared map / geodesic utilities for the Scenario Builder.
 *
 * Great-circle distance, bearing, and position interpolation.
 */

const EARTH_RADIUS_M = 6371000;
const DEG2RAD = Math.PI / 180;
const RAD2DEG = 180 / Math.PI;

/**
 * Compute great-circle distance between two points in meters.
 * Uses the Haversine formula.
 * @param {number} lat1 Degrees
 * @param {number} lon1 Degrees
 * @param {number} lat2 Degrees
 * @param {number} lon2 Degrees
 * @returns {number} Distance in meters
 */
export function geodesicDistance(lat1, lon1, lat2, lon2) {
  const dLat = (lat2 - lat1) * DEG2RAD;
  const dLon = (lon2 - lon1) * DEG2RAD;
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(lat1 * DEG2RAD) * Math.cos(lat2 * DEG2RAD) *
    Math.sin(dLon / 2) ** 2;
  return EARTH_RADIUS_M * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

/**
 * Compute initial bearing from point 1 to point 2.
 * @returns {number} Bearing in degrees (0-360)
 */
export function geodesicBearing(lat1, lon1, lat2, lon2) {
  const f1 = lat1 * DEG2RAD;
  const f2 = lat2 * DEG2RAD;
  const dL = (lon2 - lon1) * DEG2RAD;
  const y = Math.sin(dL) * Math.cos(f2);
  const x = Math.cos(f1) * Math.sin(f2) - Math.sin(f1) * Math.cos(f2) * Math.cos(dL);
  return ((Math.atan2(y, x) * RAD2DEG) + 360) % 360;
}

/**
 * Interpolate position along great-circle path.
 * @param {number} lat1 Start lat (degrees)
 * @param {number} lon1 Start lon (degrees)
 * @param {number} lat2 End lat (degrees)
 * @param {number} lon2 End lon (degrees)
 * @param {number} fraction 0.0 = start, 1.0 = end
 * @returns {{ lat: number, lon: number }}
 */
export function geodesicInterpolate(lat1, lon1, lat2, lon2, fraction) {
  if (fraction <= 0) return { lat: lat1, lon: lon1 };
  if (fraction >= 1) return { lat: lat2, lon: lon2 };

  const f1 = lat1 * DEG2RAD;
  const l1 = lon1 * DEG2RAD;
  const f2 = lat2 * DEG2RAD;
  const l2 = lon2 * DEG2RAD;

  const d = 2 * Math.asin(Math.sqrt(
    Math.sin((f2 - f1) / 2) ** 2 +
    Math.cos(f1) * Math.cos(f2) * Math.sin((l2 - l1) / 2) ** 2
  ));

  if (d < 1e-12) return { lat: lat1, lon: lon1 };

  const A = Math.sin((1 - fraction) * d) / Math.sin(d);
  const B = Math.sin(fraction * d) / Math.sin(d);

  const x = A * Math.cos(f1) * Math.cos(l1) + B * Math.cos(f2) * Math.cos(l2);
  const y = A * Math.cos(f1) * Math.sin(l1) + B * Math.cos(f2) * Math.sin(l2);
  const z = A * Math.sin(f1) + B * Math.sin(f2);

  return {
    lat: Math.atan2(z, Math.sqrt(x * x + y * y)) * RAD2DEG,
    lon: Math.atan2(y, x) * RAD2DEG,
  };
}

/**
 * Calculate travel time between two waypoints at a given speed.
 * @param {number} lat1 Degrees
 * @param {number} lon1 Degrees
 * @param {number} lat2 Degrees
 * @param {number} lon2 Degrees
 * @param {number} speedKnots Speed in knots
 * @returns {number} Time in seconds
 */
export function travelTime(lat1, lon1, lat2, lon2, speedKnots) {
  if (speedKnots <= 0) return Infinity;
  const distM = geodesicDistance(lat1, lon1, lat2, lon2);
  const speedMs = speedKnots * 0.514444; // knots to m/s
  return distM / speedMs;
}

/**
 * Convert meters to nautical miles.
 */
export function metersToNM(m) {
  return m / 1852;
}

/**
 * Format seconds as MM:SS or HH:MM:SS.
 */
export function formatDuration(seconds) {
  const s = Math.round(seconds);
  if (s < 3600) {
    const mm = String(Math.floor(s / 60)).padStart(2, '0');
    const ss = String(s % 60).padStart(2, '0');
    return `${mm}:${ss}`;
  }
  const hh = Math.floor(s / 3600);
  const mm = String(Math.floor((s % 3600) / 60)).padStart(2, '0');
  const ss = String(s % 60).padStart(2, '0');
  return `${hh}:${mm}:${ss}`;
}
