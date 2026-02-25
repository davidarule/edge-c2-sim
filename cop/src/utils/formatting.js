/**
 * Formatting utilities for coordinates, time, speed.
 */

export function formatCoord(deg, isLat) {
  const dir = isLat ? (deg >= 0 ? 'N' : 'S') : (deg >= 0 ? 'E' : 'W');
  return `${Math.abs(deg).toFixed(4)}\u00b0 ${dir}`;
}

export function formatTime(isoString) {
  if (!isoString) return '--:--:--';
  const d = new Date(isoString);
  return d.toISOString().substring(11, 19);
}

export function formatSpeed(knots) {
  return `${(knots || 0).toFixed(1)} kts`;
}

export function formatHeading(deg) {
  return `${Math.round(deg || 0).toString().padStart(3, '0')}\u00b0`;
}

export function formatAltitude(meters) {
  if (meters == null || meters === 0) return '0 m';
  if (meters > 1000) return `${(meters / 0.3048).toFixed(0)} ft`;
  return `${meters.toFixed(0)} m`;
}
