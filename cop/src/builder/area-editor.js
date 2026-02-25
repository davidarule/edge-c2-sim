/**
 * Area Editor — patrol area polygon drawing and editing for the Scenario Builder.
 *
 * Features:
 * - Click-to-add vertices in AREA mode to define polygon outline
 * - Double-click to close the polygon (connect last vertex to first)
 * - Drag vertices to reposition with live polygon updates
 * - Right-click vertex context menu: Delete Vertex, Insert After
 * - Semi-transparent agency-colored fill with dashed border
 * - All entities with patrol_area shown (faded for non-editing)
 */

import { MODES } from './map-interaction.js';

// ── Constants ──

const VERTEX_MARKER_SIZE = 10;
const BORDER_WIDTH = 2;
const AREA_DS_NAME = 'builder-areas';

// ── Styles ──

const AREA_STYLES = `
  .area-context-menu {
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
  .area-context-menu.visible { display: block; }

  .area-context-item {
    padding: 5px 12px;
    cursor: pointer;
    white-space: nowrap;
  }
  .area-context-item:hover {
    background: #21262D;
    color: #F0F6FC;
  }
  .area-context-item.danger { color: #F85149; }
  .area-context-item.danger:hover { background: rgba(248,81,73,0.15); }
  .area-context-divider {
    height: 1px;
    background: #21262D;
    margin: 4px 0;
  }
`;

let stylesInjected = false;
function injectStyles() {
  if (stylesInjected) return;
  const style = document.createElement('style');
  style.textContent = AREA_STYLES;
  document.head.appendChild(style);
  stylesInjected = true;
}

// ── Canvas-drawn vertex marker ──

/**
 * Create a data URL for a vertex circle marker.
 * @param {string} borderColor - CSS color for the border
 * @param {boolean} selected - Whether this vertex is selected (glow highlight)
 * @returns {string} Data URL of the canvas image
 */
function createVertexImage(borderColor, selected) {
  const size = VERTEX_MARKER_SIZE * 2; // 2x for retina
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

  return canvas.toDataURL();
}

// ── Main export ──

/**
 * Initialize the area editor.
 *
 * @param {Cesium.Viewer} viewer
 * @param {object} mapInteraction - From initMapInteraction()
 * @param {object} config - From initConfig()
 * @returns {object} Area editor API
 */
export function initAreaEditor(viewer, mapInteraction, config) {
  injectStyles();

  const areaDataSource = new Cesium.CustomDataSource(AREA_DS_NAME);
  viewer.dataSources.add(areaDataSource);

  // ── State ──

  let scenarioEntities = [];
  let editingEntityId = null;
  let selectedVertexIndex = -1;
  let changeCallbacks = [];

  // Drag state
  let dragging = false;
  let dragVertexIndex = -1;
  let dragEntityId = null;

  // ── DOM elements ──

  const cesiumContainer = document.getElementById('cesium-container');

  // Context menu
  const ctxMenu = document.createElement('div');
  ctxMenu.className = 'area-context-menu';
  cesiumContainer.appendChild(ctxMenu);

  // ── Cesium drag handler (separate from map-interaction for vertex dragging) ──

  const dragHandler = new Cesium.ScreenSpaceEventHandler(viewer.scene.canvas);

  dragHandler.setInputAction((movement) => {
    if (mapInteraction.getMode() !== MODES.AREA) return;
    if (!editingEntityId) return;

    const picked = viewer.scene.pick(movement.position);
    if (!picked || !picked.id || !picked.id.id) return;

    const pickedId = picked.id.id;
    const vtxMatch = pickedId.match(/^area-vertex-(.+)-(\d+)$/);
    if (!vtxMatch) return;

    const entityId = vtxMatch[1];
    const vtxIdx = parseInt(vtxMatch[2], 10);

    if (entityId !== editingEntityId) return;

    dragging = true;
    dragVertexIndex = vtxIdx;
    dragEntityId = entityId;
    viewer.scene.screenSpaceCameraController.enableRotate = false;
    viewer.scene.screenSpaceCameraController.enableTranslate = false;
  }, Cesium.ScreenSpaceEventType.LEFT_DOWN);

  dragHandler.setInputAction((movement) => {
    if (!dragging || dragVertexIndex < 0) return;

    const cartesian = viewer.camera.pickEllipsoid(
      movement.endPosition, viewer.scene.globe.ellipsoid
    );
    if (!cartesian) return;

    const carto = Cesium.Cartographic.fromCartesian(cartesian);
    const lat = Cesium.Math.toDegrees(carto.latitude);
    const lon = Cesium.Math.toDegrees(carto.longitude);

    const entity = scenarioEntities.find(e => e.id === dragEntityId);
    if (!entity || !entity.patrol_area || dragVertexIndex >= entity.patrol_area.length) return;

    entity.patrol_area[dragVertexIndex].latitude = lat;
    entity.patrol_area[dragVertexIndex].longitude = lon;

    renderAreaForEntity(entity);
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
      dragVertexIndex = -1;
      dragEntityId = null;
    }
  }, Cesium.ScreenSpaceEventType.LEFT_UP);

  // Double-click to close polygon
  dragHandler.setInputAction((movement) => {
    if (mapInteraction.getMode() !== MODES.AREA) return;
    if (!editingEntityId) return;

    const entity = scenarioEntities.find(e => e.id === editingEntityId);
    if (!entity || !entity.patrol_area || entity.patrol_area.length < 3) return;

    // Close polygon — re-render to show the completed polygon fill
    renderAreaForEntity(entity);
    notifyChange(entity);
    mapInteraction.showToast(
      `Area closed with ${entity.patrol_area.length} vertices. Click vertices to adjust.`,
      3000
    );
  }, Cesium.ScreenSpaceEventType.LEFT_DOUBLE_CLICK);

  // ── Map interaction listeners ──

  // Click handler — add vertices or select them
  mapInteraction.onClick((event) => {
    // Dismiss context menu on any click
    hideContextMenu();

    if (event.mode !== MODES.AREA) return;
    if (!editingEntityId) return;
    if (dragging) return;

    const entity = scenarioEntities.find(e => e.id === editingEntityId);
    if (!entity) return;

    // Check if clicked on an existing vertex marker
    if (event.picked && event.picked.id && event.picked.id.id) {
      const pickedId = event.picked.id.id;
      const vtxMatch = pickedId.match(/^area-vertex-(.+)-(\d+)$/);
      if (vtxMatch && vtxMatch[1] === editingEntityId) {
        const vtxIdx = parseInt(vtxMatch[2], 10);
        selectedVertexIndex = vtxIdx;
        renderAreaForEntity(entity);
        return;
      }
    }

    // Otherwise, add a new vertex at click position
    if (!event.position) return;

    if (!entity.patrol_area) {
      entity.patrol_area = [];
    }

    const newVertex = {
      latitude: event.position.latitude,
      longitude: event.position.longitude,
    };

    entity.patrol_area.push(newVertex);
    selectedVertexIndex = entity.patrol_area.length - 1;
    renderAreaForEntity(entity);
    notifyChange(entity);
  });

  // Right-click handler — vertex context menu
  mapInteraction.onRightClick((event) => {
    if (event.mode !== MODES.AREA) return;
    if (!editingEntityId) return;

    if (!event.picked || !event.picked.id || !event.picked.id.id) {
      hideContextMenu();
      return;
    }

    const pickedId = event.picked.id.id;
    const vtxMatch = pickedId.match(/^area-vertex-(.+)-(\d+)$/);
    if (!vtxMatch || vtxMatch[1] !== editingEntityId) {
      hideContextMenu();
      return;
    }

    const vtxIdx = parseInt(vtxMatch[2], 10);
    const entity = scenarioEntities.find(e => e.id === editingEntityId);
    if (!entity || !entity.patrol_area) return;

    selectedVertexIndex = vtxIdx;
    renderAreaForEntity(entity);
    showContextMenu(entity, vtxIdx, event.screenPosition);
  });

  // Mode change — stop editing if leaving AREA mode
  mapInteraction.onModeChange((mode) => {
    if (mode !== MODES.AREA) {
      stopEditing();
    }
  });

  // Close context when clicking outside
  document.addEventListener('mousedown', (e) => {
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
   * Remove all area visuals for a specific entity.
   */
  function clearAreaVisuals(entityId) {
    const toRemove = [];
    const entities = areaDataSource.entities.values;
    for (let i = 0; i < entities.length; i++) {
      const eid = entities[i].id;
      if (eid.includes(entityId)) {
        toRemove.push(entities[i]);
      }
    }
    toRemove.forEach(e => areaDataSource.entities.remove(e));
  }

  /**
   * Render the patrol area polygon and vertices for a single entity.
   */
  function renderAreaForEntity(entity) {
    clearAreaVisuals(entity.id);

    if (!entity.patrol_area || entity.patrol_area.length === 0) return;

    const color = getAgencyColor(entity);
    const cesiumColor = Cesium.Color.fromCssColorString(color);
    const isEditing = entity.id === editingEntityId;
    const vertices = entity.patrol_area;

    // Draw filled polygon if we have at least 3 vertices
    if (vertices.length >= 3) {
      const positions = vertices.map(v =>
        Cesium.Cartesian3.fromDegrees(v.longitude, v.latitude)
      );

      areaDataSource.entities.add({
        id: `area-poly-${entity.id}`,
        polygon: {
          hierarchy: new Cesium.PolygonHierarchy(positions),
          material: cesiumColor.withAlpha(isEditing ? 0.15 : 0.08),
          outline: true,
          outlineColor: cesiumColor.withAlpha(isEditing ? 0.6 : 0.3),
          outlineWidth: BORDER_WIDTH,
          height: 0,
        },
      });
    }

    // Draw border polyline (closed loop) — needed because polygon outline
    // doesn't support dashed style; this gives us more visual control
    if (vertices.length >= 2) {
      const linePositions = vertices.map(v =>
        Cesium.Cartesian3.fromDegrees(v.longitude, v.latitude)
      );
      // Close the loop if 3+ vertices
      if (vertices.length >= 3) {
        linePositions.push(Cesium.Cartesian3.fromDegrees(
          vertices[0].longitude, vertices[0].latitude
        ));
      }

      areaDataSource.entities.add({
        id: `area-line-${entity.id}`,
        polyline: {
          positions: linePositions,
          width: BORDER_WIDTH,
          material: new Cesium.PolylineDashMaterialProperty({
            color: cesiumColor.withAlpha(isEditing ? 0.6 : 0.3),
            dashLength: 12,
          }),
          clampToGround: true,
          disableDepthTestDistance: Number.POSITIVE_INFINITY,
        },
      });
    }

    // Draw vertex markers (only when editing, or just small dots when not)
    for (let i = 0; i < vertices.length; i++) {
      const v = vertices[i];
      const isSelected = isEditing && i === selectedVertexIndex;

      if (!isEditing) continue; // Only show vertex markers when editing

      const markerImage = createVertexImage(color, isSelected);

      areaDataSource.entities.add({
        id: `area-vertex-${entity.id}-${i}`,
        position: Cesium.Cartesian3.fromDegrees(v.longitude, v.latitude),
        billboard: {
          image: markerImage,
          scale: 0.5,  // Canvas is 2x, display at 1x
          verticalOrigin: Cesium.VerticalOrigin.CENTER,
          horizontalOrigin: Cesium.HorizontalOrigin.CENTER,
          disableDepthTestDistance: Number.POSITIVE_INFINITY,
        },
        label: {
          text: `V${i + 1}`,
          font: '9px IBM Plex Sans, sans-serif',
          fillColor: Cesium.Color.fromCssColorString('#C9D1D9'),
          outlineColor: Cesium.Color.BLACK,
          outlineWidth: 2,
          style: Cesium.LabelStyle.FILL_AND_OUTLINE,
          pixelOffset: new Cesium.Cartesian2(0, 12),
          horizontalOrigin: Cesium.HorizontalOrigin.CENTER,
          verticalOrigin: Cesium.VerticalOrigin.TOP,
          disableDepthTestDistance: Number.POSITIVE_INFINITY,
          scale: 1.0,
        },
      });
    }
  }

  /**
   * Render areas for all entities that have patrol_area defined.
   */
  function renderAllAreas() {
    areaDataSource.entities.removeAll();
    for (const entity of scenarioEntities) {
      if (entity.patrol_area && entity.patrol_area.length > 0) {
        renderAreaForEntity(entity);
      }
    }
  }

  // ── Context Menu ──

  function showContextMenu(entity, vtxIdx, screenPosition) {
    const vtxNum = vtxIdx + 1;

    ctxMenu.innerHTML = '';

    const items = [
      { label: `Insert After V${vtxNum}`, action: 'insert-after' },
      { divider: true },
      { label: 'Copy Coordinates', action: 'copy-coords' },
      { divider: true },
      { label: `Delete V${vtxNum}`, action: 'delete', danger: true },
    ];

    for (const item of items) {
      if (item.divider) {
        const div = document.createElement('div');
        div.className = 'area-context-divider';
        ctxMenu.appendChild(div);
        continue;
      }

      const el = document.createElement('div');
      el.className = `area-context-item${item.danger ? ' danger' : ''}`;
      el.textContent = item.label;
      el.addEventListener('click', () => {
        hideContextMenu();
        handleContextAction(entity, vtxIdx, item.action);
      });
      ctxMenu.appendChild(el);
    }

    const containerRect = cesiumContainer.getBoundingClientRect();
    let left = screenPosition.x - containerRect.left;
    let top = screenPosition.y - containerRect.top;

    // Keep in bounds
    ctxMenu.classList.add('visible');
    const mw = ctxMenu.offsetWidth || 140;
    const mh = ctxMenu.offsetHeight || 100;
    if (left + mw > containerRect.width) left -= mw;
    if (top + mh > containerRect.height) top -= mh;

    ctxMenu.style.left = `${left}px`;
    ctxMenu.style.top = `${top}px`;
  }

  function hideContextMenu() {
    ctxMenu.classList.remove('visible');
  }

  function handleContextAction(entity, vtxIdx, action) {
    const area = entity.patrol_area;
    if (!area) return;

    switch (action) {
      case 'insert-after': {
        const ref = area[vtxIdx];
        // Midpoint between this vertex and the next (wrapping around)
        const nextIdx = (vtxIdx + 1) % area.length;
        const next = area[nextIdx];

        const newVertex = {
          latitude: (ref.latitude + next.latitude) / 2,
          longitude: (ref.longitude + next.longitude) / 2,
        };
        area.splice(vtxIdx + 1, 0, newVertex);
        selectedVertexIndex = vtxIdx + 1;
        renderAreaForEntity(entity);
        notifyChange(entity);
        break;
      }

      case 'delete': {
        area.splice(vtxIdx, 1);
        if (selectedVertexIndex >= area.length) {
          selectedVertexIndex = area.length - 1;
        }
        renderAreaForEntity(entity);
        notifyChange(entity);
        break;
      }

      case 'copy-coords': {
        const v = area[vtxIdx];
        const text = `${v.latitude.toFixed(6)}, ${v.longitude.toFixed(6)}`;
        navigator.clipboard.writeText(text).then(() => {
          mapInteraction.showToast('Coordinates copied', 1500);
        }).catch(() => {
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
    selectedVertexIndex = -1;
    dragging = false;
    dragVertexIndex = -1;
    dragEntityId = null;
    hideContextMenu();
    renderAllAreas();
  }

  return {
    /**
     * Start editing the patrol area for a given entity.
     * Enters AREA mode and focuses on this entity's polygon.
     * @param {object} entity - Scenario entity object
     */
    editArea(entity) {
      if (!entity) return;

      editingEntityId = entity.id;
      selectedVertexIndex = -1;

      if (!entity.patrol_area) {
        entity.patrol_area = [];
      }

      mapInteraction.setMode(MODES.AREA);
      mapInteraction.showToast(
        `Area mode: click to add vertices for ${entity.callsign || entity.id}. Double-click to close. ESC to finish.`,
        0
      );

      renderAllAreas();
    },

    /**
     * Stop editing and deselect the current area.
     */
    stopEditing,

    /**
     * Re-render areas for all entities with patrol_area.
     */
    refresh() {
      renderAllAreas();
    },

    /**
     * Set the reference to the scenario entities array.
     * @param {Array} entities
     */
    setEntities(entities) {
      scenarioEntities = entities || [];
      renderAllAreas();
    },

    /**
     * Get the ID of the entity whose area is currently being edited.
     * @returns {string|null}
     */
    getEditingEntityId() {
      return editingEntityId;
    },

    /**
     * Register a callback for when the patrol area changes.
     * @param {function} callback - (entity) => void
     * @returns {function} Unsubscribe function
     */
    onAreaChange(callback) {
      changeCallbacks.push(callback);
      return () => { changeCallbacks = changeCallbacks.filter(c => c !== callback); };
    },

    /**
     * Remove all area visuals from the map.
     */
    clear() {
      editingEntityId = null;
      selectedVertexIndex = -1;
      hideContextMenu();
      areaDataSource.entities.removeAll();
    },

    /**
     * Destroy the area editor and clean up resources.
     */
    destroy() {
      dragHandler.destroy();
      ctxMenu.remove();
      viewer.dataSources.remove(areaDataSource);
    },

    /**
     * Get the data source (for external use).
     */
    getDataSource() {
      return areaDataSource;
    },
  };
}
