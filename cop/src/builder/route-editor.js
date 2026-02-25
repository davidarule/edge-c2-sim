/**
 * Route Editor — waypoint route drawing and editing for the Scenario Builder.
 *
 * Features:
 * - Click-to-add waypoints in WAYPOINT mode
 * - Drag waypoints to reposition with live polyline updates
 * - Right-click context menu: Insert Before, Insert After, Delete, Copy Coordinates
 * - Double-click route line to insert waypoint at that position
 * - Floating popover for waypoint properties (speed, altitude, time)
 * - Auto-calculated cumulative travel times using geodesic math
 * - Agency-colored route lines and waypoint markers
 */

import { MODES } from './map-interaction.js';
import { geodesicDistance, travelTime, formatDuration } from '../shared/map-utils.js';

// ── Constants ──

const WP_MARKER_SIZE = 14;
const WP_FONT = '9px IBM Plex Sans, sans-serif';
const WP_LABEL_FONT = '10px IBM Plex Sans, sans-serif';
const ROUTE_LINE_WIDTH = 2;
const DEFAULT_SPEED_KNOTS = 12;
const ROUTE_DS_NAME = 'builder-routes';

// ── Styles ──

const POPOVER_STYLES = `
  .wp-popover {
    position: absolute;
    z-index: 60;
    display: none;
    min-width: 180px;
    background: rgba(13,17,23,0.95);
    border: 1px solid #30363D;
    border-radius: 4px;
    padding: 8px;
    font-family: 'IBM Plex Sans', sans-serif;
    font-size: 11px;
    color: #C9D1D9;
    pointer-events: auto;
    box-shadow: 0 4px 12px rgba(0,0,0,0.4);
  }
  .wp-popover.visible { display: block; }

  .wp-popover-title {
    font-weight: 600;
    font-size: 11px;
    color: #58A6FF;
    margin-bottom: 6px;
    padding-bottom: 4px;
    border-bottom: 1px solid #21262D;
  }

  .wp-popover-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 4px;
  }
  .wp-popover-row:last-child { margin-bottom: 0; }

  .wp-popover-label {
    color: #8B949E;
    font-size: 10px;
    min-width: 50px;
  }

  .wp-popover-value {
    color: #C9D1D9;
    font-size: 11px;
    font-family: 'IBM Plex Mono', monospace;
    text-align: right;
  }

  .wp-popover input[type="number"] {
    width: 60px;
    padding: 2px 4px;
    background: #0D1117;
    border: 1px solid #30363D;
    border-radius: 3px;
    color: #C9D1D9;
    font-size: 10px;
    font-family: 'IBM Plex Mono', monospace;
    text-align: right;
    outline: none;
  }
  .wp-popover input[type="number"]:focus {
    border-color: #58A6FF;
  }

  .wp-popover-auto {
    font-size: 9px;
    color: #6E7681;
    font-style: italic;
    margin-left: 4px;
  }

  .wp-context-menu {
    position: absolute;
    z-index: 70;
    display: none;
    min-width: 140px;
    background: rgba(13,17,23,0.95);
    border: 1px solid #30363D;
    border-radius: 4px;
    padding: 4px 0;
    font-family: 'IBM Plex Sans', sans-serif;
    font-size: 11px;
    color: #C9D1D9;
    box-shadow: 0 4px 12px rgba(0,0,0,0.4);
  }
  .wp-context-menu.visible { display: block; }

  .wp-context-item {
    padding: 5px 12px;
    cursor: pointer;
    white-space: nowrap;
  }
  .wp-context-item:hover {
    background: #21262D;
    color: #F0F6FC;
  }
  .wp-context-item.danger { color: #F85149; }
  .wp-context-item.danger:hover { background: rgba(248,81,73,0.15); }
  .wp-context-divider {
    height: 1px;
    background: #21262D;
    margin: 4px 0;
  }
`;

let stylesInjected = false;
function injectStyles() {
  if (stylesInjected) return;
  const style = document.createElement('style');
  style.textContent = POPOVER_STYLES;
  document.head.appendChild(style);
  stylesInjected = true;
}

// ── Canvas-drawn waypoint marker ──

/**
 * Create a data URL for a numbered waypoint circle.
 * @param {number} num - Waypoint sequence number
 * @param {string} borderColor - CSS color for the border
 * @param {boolean} selected - Whether this waypoint is selected
 * @returns {string} Data URL of the canvas image
 */
function createWaypointImage(num, borderColor, selected) {
  const size = WP_MARKER_SIZE * 2; // 2x for retina
  const canvas = document.createElement('canvas');
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext('2d');
  const cx = size / 2;
  const cy = size / 2;
  const r = (size / 2) - 2;

  // Outer glow when selected
  if (selected) {
    ctx.beginPath();
    ctx.arc(cx, cy, r + 2, 0, Math.PI * 2);
    ctx.fillStyle = borderColor;
    ctx.globalAlpha = 0.4;
    ctx.fill();
    ctx.globalAlpha = 1.0;
  }

  // White fill
  ctx.beginPath();
  ctx.arc(cx, cy, r, 0, Math.PI * 2);
  ctx.fillStyle = '#FFFFFF';
  ctx.fill();

  // Colored border
  ctx.lineWidth = selected ? 3 : 2;
  ctx.strokeStyle = borderColor;
  ctx.stroke();

  // Centered number
  ctx.fillStyle = '#0D1117';
  ctx.font = `bold ${Math.round(size * 0.4)}px IBM Plex Sans, sans-serif`;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText(String(num), cx, cy + 1);

  return canvas.toDataURL();
}

// ── Travel time computation ──

/**
 * Recalculate cumulative travel times for a waypoints array.
 * The entity's initial_position is the implicit start point.
 * @param {object} entity - Scenario entity with initial_position and waypoints
 */
function recalcTimes(entity) {
  const wps = entity.waypoints;
  if (!wps || wps.length === 0) return;

  let prevLat, prevLon;
  if (entity.initial_position) {
    prevLat = entity.initial_position.latitude;
    prevLon = entity.initial_position.longitude;
  } else if (wps.length > 0) {
    prevLat = wps[0].latitude;
    prevLon = wps[0].longitude;
  }

  let cumulative = 0;
  for (let i = 0; i < wps.length; i++) {
    const wp = wps[i];
    const speed = wp.speed_knots || DEFAULT_SPEED_KNOTS;

    if (i === 0 && !entity.initial_position) {
      wp._time_seconds = 0;
    } else {
      const dt = travelTime(prevLat, prevLon, wp.latitude, wp.longitude, speed);
      cumulative += (dt === Infinity ? 0 : dt);
      if (!wp._manual_time) {
        wp._time_seconds = cumulative;
      }
    }

    prevLat = wp.latitude;
    prevLon = wp.longitude;
  }
}

// ── Main export ──

/**
 * Initialize the route editor.
 *
 * @param {Cesium.Viewer} viewer
 * @param {object} mapInteraction - From initMapInteraction()
 * @param {object} config - From initConfig()
 * @returns {object} Route editor API
 */
export function initRouteEditor(viewer, mapInteraction, config) {
  injectStyles();

  const routeDataSource = new Cesium.CustomDataSource(ROUTE_DS_NAME);
  viewer.dataSources.add(routeDataSource);

  // ── State ──

  let scenarioEntities = [];
  let editingEntityId = null;
  let selectedWpIndex = -1;
  let changeCallbacks = [];

  // Drag state
  let dragging = false;
  let dragWpIndex = -1;
  let dragEntityId = null;

  // ── DOM elements ──

  const cesiumContainer = document.getElementById('cesium-container');

  // Popover
  const popover = document.createElement('div');
  popover.className = 'wp-popover';
  cesiumContainer.appendChild(popover);

  // Context menu
  const ctxMenu = document.createElement('div');
  ctxMenu.className = 'wp-context-menu';
  cesiumContainer.appendChild(ctxMenu);

  // ── Cesium drag handler (separate from map-interaction for waypoint dragging) ──

  const dragHandler = new Cesium.ScreenSpaceEventHandler(viewer.scene.canvas);

  dragHandler.setInputAction((movement) => {
    if (mapInteraction.getMode() !== MODES.WAYPOINT) return;
    if (!editingEntityId) return;

    const picked = viewer.scene.pick(movement.position);
    if (!picked || !picked.id || !picked.id.id) return;

    const pickedId = picked.id.id;
    const wpMatch = pickedId.match(/^route-wp-(.+)-(\d+)$/);
    if (!wpMatch) return;

    const entityId = wpMatch[1];
    const wpIdx = parseInt(wpMatch[2], 10);

    if (entityId !== editingEntityId) return;

    dragging = true;
    dragWpIndex = wpIdx;
    dragEntityId = entityId;
    viewer.scene.screenSpaceCameraController.enableRotate = false;
    viewer.scene.screenSpaceCameraController.enableTranslate = false;
  }, Cesium.ScreenSpaceEventType.LEFT_DOWN);

  dragHandler.setInputAction((movement) => {
    if (!dragging || dragWpIndex < 0) return;

    const cartesian = viewer.camera.pickEllipsoid(
      movement.endPosition, viewer.scene.globe.ellipsoid
    );
    if (!cartesian) return;

    const carto = Cesium.Cartographic.fromCartesian(cartesian);
    const lat = Cesium.Math.toDegrees(carto.latitude);
    const lon = Cesium.Math.toDegrees(carto.longitude);

    const entity = scenarioEntities.find(e => e.id === dragEntityId);
    if (!entity || !entity.waypoints || dragWpIndex >= entity.waypoints.length) return;

    entity.waypoints[dragWpIndex].latitude = lat;
    entity.waypoints[dragWpIndex].longitude = lon;

    recalcTimes(entity);
    renderRouteForEntity(entity);
    updatePopoverPosition();
  }, Cesium.ScreenSpaceEventType.MOUSE_MOVE);

  dragHandler.setInputAction(() => {
    if (dragging) {
      dragging = false;
      viewer.scene.screenSpaceCameraController.enableRotate = true;
      viewer.scene.screenSpaceCameraController.enableTranslate = true;

      if (dragEntityId) {
        const entity = scenarioEntities.find(e => e.id === dragEntityId);
        if (entity) {
          notifyChange(entity);
        }
      }
      dragWpIndex = -1;
      dragEntityId = null;
    }
  }, Cesium.ScreenSpaceEventType.LEFT_UP);

  // Double-click on route line to insert waypoint
  dragHandler.setInputAction((movement) => {
    if (mapInteraction.getMode() !== MODES.WAYPOINT) return;
    if (!editingEntityId) return;

    const picked = viewer.scene.pick(movement.position);
    if (!picked || !picked.id || !picked.id.id) return;

    const pickedId = picked.id.id;
    const lineMatch = pickedId.match(/^route-line-(.+)-(\d+)$/);
    if (!lineMatch) return;

    const entityId = lineMatch[1];
    const segIdx = parseInt(lineMatch[2], 10);

    if (entityId !== editingEntityId) return;

    const cartesian = viewer.camera.pickEllipsoid(
      movement.position, viewer.scene.globe.ellipsoid
    );
    if (!cartesian) return;

    const carto = Cesium.Cartographic.fromCartesian(cartesian);
    const lat = Cesium.Math.toDegrees(carto.latitude);
    const lon = Cesium.Math.toDegrees(carto.longitude);

    const entity = scenarioEntities.find(e => e.id === entityId);
    if (!entity || !entity.waypoints) return;

    // Insert after segIdx
    const insertIdx = segIdx + 1;
    const prevWp = entity.waypoints[segIdx];
    const newWp = {
      latitude: lat,
      longitude: lon,
      altitude_m: prevWp ? prevWp.altitude_m : 0,
      speed_knots: prevWp ? prevWp.speed_knots : DEFAULT_SPEED_KNOTS,
      _time_seconds: 0,
      _manual_time: false,
    };

    entity.waypoints.splice(insertIdx, 0, newWp);
    recalcTimes(entity);
    selectedWpIndex = insertIdx;
    renderRouteForEntity(entity);
    showPopover(entity, insertIdx);
    notifyChange(entity);
  }, Cesium.ScreenSpaceEventType.LEFT_DOUBLE_CLICK);

  // ── Map interaction listeners ──

  // Click handler — add waypoints or select them
  mapInteraction.onClick((event) => {
    // Dismiss context menu on any click
    hideContextMenu();

    if (event.mode !== MODES.WAYPOINT) return;
    if (!editingEntityId) return;
    if (dragging) return;

    const entity = scenarioEntities.find(e => e.id === editingEntityId);
    if (!entity) return;

    // Check if clicked on an existing waypoint marker
    if (event.picked && event.picked.id && event.picked.id.id) {
      const pickedId = event.picked.id.id;
      const wpMatch = pickedId.match(/^route-wp-(.+)-(\d+)$/);
      if (wpMatch && wpMatch[1] === editingEntityId) {
        const wpIdx = parseInt(wpMatch[2], 10);
        selectedWpIndex = wpIdx;
        renderRouteForEntity(entity);
        showPopover(entity, wpIdx);
        return;
      }
    }

    // Otherwise, add a new waypoint at click position
    if (!event.position) return;

    if (!entity.waypoints) {
      entity.waypoints = [];
    }

    const prevSpeed = entity.waypoints.length > 0
      ? entity.waypoints[entity.waypoints.length - 1].speed_knots
      : (entity.cruise_speed_knots || DEFAULT_SPEED_KNOTS);

    const newWp = {
      latitude: event.position.latitude,
      longitude: event.position.longitude,
      altitude_m: entity.domain === 'AIR' ? (entity.cruise_altitude_m || 3000) : 0,
      speed_knots: prevSpeed,
      _time_seconds: 0,
      _manual_time: false,
    };

    entity.waypoints.push(newWp);
    recalcTimes(entity);

    selectedWpIndex = entity.waypoints.length - 1;
    renderRouteForEntity(entity);
    showPopover(entity, selectedWpIndex);
    notifyChange(entity);
  });

  // Right-click handler — waypoint context menu
  mapInteraction.onRightClick((event) => {
    if (event.mode !== MODES.WAYPOINT) return;
    if (!editingEntityId) return;

    if (!event.picked || !event.picked.id || !event.picked.id.id) {
      hideContextMenu();
      return;
    }

    const pickedId = event.picked.id.id;
    const wpMatch = pickedId.match(/^route-wp-(.+)-(\d+)$/);
    if (!wpMatch || wpMatch[1] !== editingEntityId) {
      hideContextMenu();
      return;
    }

    const wpIdx = parseInt(wpMatch[2], 10);
    const entity = scenarioEntities.find(e => e.id === editingEntityId);
    if (!entity || !entity.waypoints) return;

    selectedWpIndex = wpIdx;
    renderRouteForEntity(entity);
    showContextMenu(entity, wpIdx, event.screenPosition);
  });

  // Mode change — stop editing if leaving WAYPOINT mode
  mapInteraction.onModeChange((mode) => {
    if (mode !== MODES.WAYPOINT) {
      stopEditing();
    }
  });

  // Close popover/context when clicking outside
  document.addEventListener('mousedown', (e) => {
    if (!popover.contains(e.target) && !ctxMenu.contains(e.target)) {
      // Don't hide popover on canvas clicks in WAYPOINT mode (handled by click listener)
      if (!viewer.scene.canvas.contains(e.target)) {
        hidePopover();
      }
    }
    if (!ctxMenu.contains(e.target)) {
      hideContextMenu();
    }
  });

  // ── Rendering ──

  /**
   * Get the agency color for an entity.
   */
  function getAgencyColor(entity) {
    const agency = entity.agency || 'UNKNOWN';
    return config.agencyColors[agency] || config.agencyColors.UNKNOWN || '#78909C';
  }

  /**
   * Remove all route visuals for a specific entity.
   */
  function clearRouteVisuals(entityId) {
    const toRemove = [];
    const entities = routeDataSource.entities.values;
    for (let i = 0; i < entities.length; i++) {
      const eid = entities[i].id;
      if (eid.includes(entityId)) {
        toRemove.push(entities[i]);
      }
    }
    toRemove.forEach(e => routeDataSource.entities.remove(e));
  }

  /**
   * Render the route (waypoints + polylines) for a single entity.
   */
  function renderRouteForEntity(entity) {
    clearRouteVisuals(entity.id);

    if (!entity.waypoints || entity.waypoints.length === 0) return;

    const color = getAgencyColor(entity);
    const cesiumColor = Cesium.Color.fromCssColorString(color);
    const isEditing = entity.id === editingEntityId;

    // Build the full position chain: start position + all waypoints
    const positionChain = [];

    if (entity.initial_position) {
      positionChain.push({
        latitude: entity.initial_position.latitude,
        longitude: entity.initial_position.longitude,
        altitude_m: entity.initial_position.altitude_m || 0,
      });
    }

    for (const wp of entity.waypoints) {
      positionChain.push({
        latitude: wp.latitude,
        longitude: wp.longitude,
        altitude_m: wp.altitude_m || 0,
      });
    }

    // Draw polyline segments (one entity per segment for double-click insertion)
    for (let i = 0; i < positionChain.length - 1; i++) {
      const p1 = positionChain[i];
      const p2 = positionChain[i + 1];

      routeDataSource.entities.add({
        id: `route-line-${entity.id}-${i}`,
        polyline: {
          positions: Cesium.Cartesian3.fromDegreesArrayHeights([
            p1.longitude, p1.latitude, p1.altitude_m,
            p2.longitude, p2.latitude, p2.altitude_m,
          ]),
          width: ROUTE_LINE_WIDTH,
          material: cesiumColor.withAlpha(isEditing ? 0.9 : 0.5),
          clampToGround: entity.domain !== 'AIR',
          disableDepthTestDistance: Number.POSITIVE_INFINITY,
        },
      });
    }

    // Draw waypoint markers
    for (let i = 0; i < entity.waypoints.length; i++) {
      const wp = entity.waypoints[i];
      const isSelected = isEditing && i === selectedWpIndex;
      const wpNum = i + 1;

      const markerImage = createWaypointImage(wpNum, color, isSelected);
      const speed = wp.speed_knots || DEFAULT_SPEED_KNOTS;
      const timeStr = formatDuration(wp._time_seconds || 0);
      const autoLabel = wp._manual_time ? '' : '';

      routeDataSource.entities.add({
        id: `route-wp-${entity.id}-${i}`,
        position: Cesium.Cartesian3.fromDegrees(
          wp.longitude, wp.latitude, wp.altitude_m || 0
        ),
        billboard: {
          image: markerImage,
          scale: 0.5,  // Canvas is 2x, display at 1x
          verticalOrigin: Cesium.VerticalOrigin.CENTER,
          horizontalOrigin: Cesium.HorizontalOrigin.CENTER,
          disableDepthTestDistance: Number.POSITIVE_INFINITY,
        },
        label: {
          text: `WP${wpNum} ${speed}kts ${timeStr}`,
          font: WP_LABEL_FONT,
          fillColor: Cesium.Color.fromCssColorString('#C9D1D9'),
          outlineColor: Cesium.Color.BLACK,
          outlineWidth: 2,
          style: Cesium.LabelStyle.FILL_AND_OUTLINE,
          pixelOffset: new Cesium.Cartesian2(0, 14),
          horizontalOrigin: Cesium.HorizontalOrigin.CENTER,
          verticalOrigin: Cesium.VerticalOrigin.TOP,
          disableDepthTestDistance: Number.POSITIVE_INFINITY,
          scale: 1.0,
          show: isEditing,
        },
      });
    }
  }

  /**
   * Render routes for all entities that have waypoints.
   */
  function renderAllRoutes() {
    routeDataSource.entities.removeAll();
    for (const entity of scenarioEntities) {
      if (entity.waypoints && entity.waypoints.length > 0) {
        recalcTimes(entity);
        renderRouteForEntity(entity);
      }
    }
  }

  // ── Popover ──

  function showPopover(entity, wpIdx) {
    if (!entity.waypoints || wpIdx < 0 || wpIdx >= entity.waypoints.length) {
      hidePopover();
      return;
    }

    const wp = entity.waypoints[wpIdx];
    const wpNum = wpIdx + 1;
    const timeStr = formatDuration(wp._time_seconds || 0);
    const isAir = entity.domain === 'AIR';

    popover.innerHTML = `
      <div class="wp-popover-title">Waypoint ${wpNum}</div>
      <div class="wp-popover-row">
        <span class="wp-popover-label">Lat</span>
        <span class="wp-popover-value">${wp.latitude.toFixed(6)}</span>
      </div>
      <div class="wp-popover-row">
        <span class="wp-popover-label">Lon</span>
        <span class="wp-popover-value">${wp.longitude.toFixed(6)}</span>
      </div>
      <div class="wp-popover-row">
        <span class="wp-popover-label">Speed</span>
        <input type="number" class="wp-speed-input" value="${wp.speed_knots || DEFAULT_SPEED_KNOTS}"
               min="0" max="900" step="1" /> <span style="color:#8B949E; font-size:10px">kts</span>
      </div>
      ${isAir ? `
      <div class="wp-popover-row">
        <span class="wp-popover-label">Altitude</span>
        <input type="number" class="wp-alt-input" value="${wp.altitude_m || 0}"
               min="0" max="20000" step="100" /> <span style="color:#8B949E; font-size:10px">m</span>
      </div>` : ''}
      <div class="wp-popover-row">
        <span class="wp-popover-label">Time</span>
        <span class="wp-popover-value">${timeStr}</span>
        ${!wp._manual_time ? '<span class="wp-popover-auto">(auto)</span>' : ''}
      </div>
    `;

    // Wire up speed input
    const speedInput = popover.querySelector('.wp-speed-input');
    if (speedInput) {
      speedInput.addEventListener('change', () => {
        const val = parseFloat(speedInput.value);
        if (!isNaN(val) && val > 0) {
          wp.speed_knots = val;
          recalcTimes(entity);
          renderRouteForEntity(entity);
          showPopover(entity, wpIdx);  // Refresh popover with new time
          notifyChange(entity);
        }
      });
    }

    // Wire up altitude input
    const altInput = popover.querySelector('.wp-alt-input');
    if (altInput) {
      altInput.addEventListener('change', () => {
        const val = parseFloat(altInput.value);
        if (!isNaN(val) && val >= 0) {
          wp.altitude_m = val;
          renderRouteForEntity(entity);
          notifyChange(entity);
        }
      });
    }

    popover.classList.add('visible');
    updatePopoverPosition();
  }

  function updatePopoverPosition() {
    if (selectedWpIndex < 0 || !editingEntityId) return;

    const entity = scenarioEntities.find(e => e.id === editingEntityId);
    if (!entity || !entity.waypoints || selectedWpIndex >= entity.waypoints.length) return;

    const wp = entity.waypoints[selectedWpIndex];
    const cartesian = Cesium.Cartesian3.fromDegrees(
      wp.longitude, wp.latitude, wp.altitude_m || 0
    );
    const screenPos = Cesium.SceneTransforms.wgs84ToWindowCoordinates(
      viewer.scene, cartesian
    );

    if (screenPos) {
      const containerRect = cesiumContainer.getBoundingClientRect();
      let left = screenPos.x - containerRect.left + 20;
      let top = screenPos.y - containerRect.top - 20;

      // Keep popover in bounds
      const pw = popover.offsetWidth || 180;
      const ph = popover.offsetHeight || 140;
      if (left + pw > containerRect.width) left = screenPos.x - containerRect.left - pw - 20;
      if (top + ph > containerRect.height) top = containerRect.height - ph - 8;
      if (top < 8) top = 8;

      popover.style.left = `${left}px`;
      popover.style.top = `${top}px`;
    }
  }

  function hidePopover() {
    popover.classList.remove('visible');
  }

  // Update popover position on camera move
  viewer.scene.preRender.addEventListener(() => {
    if (popover.classList.contains('visible')) {
      updatePopoverPosition();
    }
  });

  // ── Context Menu ──

  function showContextMenu(entity, wpIdx, screenPosition) {
    hidePopover();

    const wp = entity.waypoints[wpIdx];
    const wpNum = wpIdx + 1;

    ctxMenu.innerHTML = '';

    const items = [
      { label: `Insert Before WP${wpNum}`, action: 'insert-before' },
      { label: `Insert After WP${wpNum}`, action: 'insert-after' },
      { divider: true },
      { label: 'Copy Coordinates', action: 'copy-coords' },
      { divider: true },
      { label: `Delete WP${wpNum}`, action: 'delete', danger: true },
    ];

    for (const item of items) {
      if (item.divider) {
        const div = document.createElement('div');
        div.className = 'wp-context-divider';
        ctxMenu.appendChild(div);
        continue;
      }

      const el = document.createElement('div');
      el.className = `wp-context-item${item.danger ? ' danger' : ''}`;
      el.textContent = item.label;
      el.addEventListener('click', () => {
        hideContextMenu();
        handleContextAction(entity, wpIdx, item.action);
      });
      ctxMenu.appendChild(el);
    }

    const containerRect = cesiumContainer.getBoundingClientRect();
    let left = screenPosition.x - containerRect.left;
    let top = screenPosition.y - containerRect.top;

    // Keep in bounds
    ctxMenu.classList.add('visible');
    const mw = ctxMenu.offsetWidth || 140;
    const mh = ctxMenu.offsetHeight || 120;
    if (left + mw > containerRect.width) left -= mw;
    if (top + mh > containerRect.height) top -= mh;

    ctxMenu.style.left = `${left}px`;
    ctxMenu.style.top = `${top}px`;
  }

  function hideContextMenu() {
    ctxMenu.classList.remove('visible');
  }

  function handleContextAction(entity, wpIdx, action) {
    const wps = entity.waypoints;
    if (!wps) return;

    switch (action) {
      case 'insert-before': {
        const ref = wps[wpIdx];
        // Midpoint between previous position and this waypoint
        let prevLat, prevLon;
        if (wpIdx > 0) {
          prevLat = wps[wpIdx - 1].latitude;
          prevLon = wps[wpIdx - 1].longitude;
        } else if (entity.initial_position) {
          prevLat = entity.initial_position.latitude;
          prevLon = entity.initial_position.longitude;
        } else {
          prevLat = ref.latitude;
          prevLon = ref.longitude;
        }

        const newWp = {
          latitude: (prevLat + ref.latitude) / 2,
          longitude: (prevLon + ref.longitude) / 2,
          altitude_m: ref.altitude_m || 0,
          speed_knots: ref.speed_knots || DEFAULT_SPEED_KNOTS,
          _time_seconds: 0,
          _manual_time: false,
        };
        wps.splice(wpIdx, 0, newWp);
        selectedWpIndex = wpIdx;
        recalcTimes(entity);
        renderRouteForEntity(entity);
        showPopover(entity, wpIdx);
        notifyChange(entity);
        break;
      }

      case 'insert-after': {
        const ref = wps[wpIdx];
        let nextLat, nextLon;
        if (wpIdx < wps.length - 1) {
          nextLat = wps[wpIdx + 1].latitude;
          nextLon = wps[wpIdx + 1].longitude;
        } else {
          // Last waypoint — offset slightly
          nextLat = ref.latitude + 0.01;
          nextLon = ref.longitude + 0.01;
        }

        const newWp = {
          latitude: (ref.latitude + nextLat) / 2,
          longitude: (ref.longitude + nextLon) / 2,
          altitude_m: ref.altitude_m || 0,
          speed_knots: ref.speed_knots || DEFAULT_SPEED_KNOTS,
          _time_seconds: 0,
          _manual_time: false,
        };
        wps.splice(wpIdx + 1, 0, newWp);
        selectedWpIndex = wpIdx + 1;
        recalcTimes(entity);
        renderRouteForEntity(entity);
        showPopover(entity, wpIdx + 1);
        notifyChange(entity);
        break;
      }

      case 'delete': {
        wps.splice(wpIdx, 1);
        if (selectedWpIndex >= wps.length) {
          selectedWpIndex = wps.length - 1;
        }
        recalcTimes(entity);
        renderRouteForEntity(entity);
        if (selectedWpIndex >= 0) {
          showPopover(entity, selectedWpIndex);
        } else {
          hidePopover();
        }
        notifyChange(entity);
        break;
      }

      case 'copy-coords': {
        const wp = wps[wpIdx];
        const text = `${wp.latitude.toFixed(6)}, ${wp.longitude.toFixed(6)}`;
        navigator.clipboard.writeText(text).then(() => {
          mapInteraction.showToast('Coordinates copied', 1500);
        }).catch(() => {
          // Fallback: prompt
          window.prompt('Coordinates:', text);
        });
        break;
      }
    }
  }

  // ── Notification ──

  function notifyChange(entity) {
    changeCallbacks.forEach(fn => fn(entity));
  }

  // ── Public API ──

  function stopEditing() {
    editingEntityId = null;
    selectedWpIndex = -1;
    dragging = false;
    dragWpIndex = -1;
    dragEntityId = null;
    hidePopover();
    hideContextMenu();
    renderAllRoutes();
  }

  return {
    /**
     * Start editing the route for a given entity.
     * Enters WAYPOINT mode and focuses on this entity's waypoints.
     * @param {object} entity - Scenario entity object
     */
    editRoute(entity) {
      if (!entity) return;

      editingEntityId = entity.id;
      selectedWpIndex = -1;

      if (!entity.waypoints) {
        entity.waypoints = [];
      }

      recalcTimes(entity);
      mapInteraction.setMode(MODES.WAYPOINT);
      mapInteraction.showToast(
        `Route mode: click to add waypoints for ${entity.callsign || entity.id}. ESC to finish.`,
        0
      );

      renderAllRoutes();
    },

    /**
     * Stop editing and deselect the current route.
     */
    stopEditing,

    /**
     * Re-render routes for all entities with waypoints.
     */
    refresh() {
      renderAllRoutes();
    },

    /**
     * Set the reference to the scenario entities array.
     * @param {Array} entities
     */
    setEntities(entities) {
      scenarioEntities = entities || [];
      renderAllRoutes();
    },

    /**
     * Get the ID of the entity whose route is currently being edited.
     * @returns {string|null}
     */
    getEditingEntityId() {
      return editingEntityId;
    },

    /**
     * Register a callback for when waypoints change.
     * @param {function} callback - (entity) => void
     * @returns {function} Unsubscribe function
     */
    onRouteChange(callback) {
      changeCallbacks.push(callback);
      return () => { changeCallbacks = changeCallbacks.filter(c => c !== callback); };
    },

    /**
     * Remove all route visuals from the map.
     */
    clear() {
      editingEntityId = null;
      selectedWpIndex = -1;
      hidePopover();
      hideContextMenu();
      routeDataSource.entities.removeAll();
    },

    /**
     * Destroy the route editor and clean up resources.
     */
    destroy() {
      dragHandler.destroy();
      popover.remove();
      ctxMenu.remove();
      viewer.dataSources.remove(routeDataSource);
    },

    /**
     * Get the data source (for external use).
     */
    getDataSource() {
      return routeDataSource;
    },
  };
}
