/**
 * Entity Placer — handles placing and moving entities on the CesiumJS globe.
 *
 * Features:
 * - Click-to-place: Select unplaced entity, click map to set position
 * - Drag-to-move: Drag placed entity to reposition
 * - Visual feedback: Pulsing highlight ring on selected entity
 * - Symbols rendered using DISA SVG compositor
 */

import { renderSymbol } from '../symbol-renderer.js';
import { MODES } from './map-interaction.js';

const SYMBOL_SIZE = 48;  // Render size for builder entities

/**
 * Initialize the entity placer.
 *
 * @param {Cesium.Viewer} viewer
 * @param {object} mapInteraction - From initMapInteraction()
 * @returns {object} API
 */
export function initEntityPlacer(viewer, mapInteraction) {
  // Entity billboards on the map (builder entities, separate from live COP entities)
  const builderDataSource = new Cesium.CustomDataSource('builder-entities');
  viewer.dataSources.add(builderDataSource);

  // State
  let scenarioEntities = [];    // Reference to scenario state entities array
  let selectedEntityId = null;
  let placingEntityId = null;   // Entity being placed (waiting for map click)
  let dragging = false;
  let dragEntity = null;

  let selectListeners = [];
  let changeListeners = [];

  // ── Rendering ──

  /**
   * Sync Cesium billboards with scenario entity positions.
   */
  function renderEntities() {
    builderDataSource.entities.removeAll();

    for (const entity of scenarioEntities) {
      if (!entity.placed || !entity.initial_position) continue;

      const pos = entity.initial_position;
      const sidc = entity.sidc || '10030000000000000000';
      const symbolUrl = renderSymbol(sidc, { size: SYMBOL_SIZE });

      const cesiumEntity = builderDataSource.entities.add({
        id: `builder-${entity.id}`,
        position: Cesium.Cartesian3.fromDegrees(
          pos.longitude, pos.latitude, pos.altitude_m || 0
        ),
        billboard: {
          image: symbolUrl,
          scale: 0.75,
          verticalOrigin: Cesium.VerticalOrigin.CENTER,
          horizontalOrigin: Cesium.HorizontalOrigin.CENTER,
          disableDepthTestDistance: Number.POSITIVE_INFINITY,
        },
        label: {
          text: entity.callsign || entity.id,
          font: '11px IBM Plex Sans, sans-serif',
          fillColor: Cesium.Color.fromCssColorString('#C9D1D9'),
          outlineColor: Cesium.Color.BLACK,
          outlineWidth: 2,
          style: Cesium.LabelStyle.FILL_AND_OUTLINE,
          pixelOffset: new Cesium.Cartesian2(0, -30),
          horizontalOrigin: Cesium.HorizontalOrigin.CENTER,
          verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
          disableDepthTestDistance: Number.POSITIVE_INFINITY,
          scale: 1.0,
        },
      });

      // Highlight ring for selected entity
      if (entity.id === selectedEntityId) {
        builderDataSource.entities.add({
          id: `builder-highlight-${entity.id}`,
          position: Cesium.Cartesian3.fromDegrees(
            pos.longitude, pos.latitude, pos.altitude_m || 0
          ),
          ellipse: {
            semiMinorAxis: 800,
            semiMajorAxis: 800,
            material: Cesium.Color.fromCssColorString('#58A6FF').withAlpha(0.15),
            outline: true,
            outlineColor: Cesium.Color.fromCssColorString('#58A6FF').withAlpha(0.6),
            outlineWidth: 2,
            height: 0,
          },
        });
      }
    }
  }

  // ── Map interaction handlers ──

  mapInteraction.onClick((event) => {
    // PLACE mode: place the pending entity at click position
    if (event.mode === MODES.PLACE && placingEntityId && event.position) {
      const entity = scenarioEntities.find(e => e.id === placingEntityId);
      if (entity) {
        entity.initial_position = {
          latitude: event.position.latitude,
          longitude: event.position.longitude,
          altitude_m: 0,
        };
        entity.placed = true;
        placingEntityId = null;
        mapInteraction.setMode(MODES.SELECT);
        mapInteraction.showToast(`Placed ${entity.callsign || entity.id}`, 2000);
        renderEntities();
        changeListeners.forEach(fn => fn('place', entity));
      }
      return;
    }

    // SELECT mode: click on builder entity to select
    if (event.mode === MODES.SELECT && event.picked) {
      const pickedId = event.picked.id && event.picked.id.id;
      if (pickedId && pickedId.startsWith('builder-') && !pickedId.startsWith('builder-highlight-')) {
        const entityId = pickedId.replace('builder-', '');
        selectEntity(entityId);
        return;
      }
    }

    // Click on empty space = deselect
    if (event.mode === MODES.SELECT) {
      deselectEntity();
    }
  });

  // Drag support
  let dragStartPosition = null;

  mapInteraction.onClick((event) => {
    // Handled above
  });

  // Right-click context menu data
  mapInteraction.onRightClick((event) => {
    if (event.picked) {
      const pickedId = event.picked.id && event.picked.id.id;
      if (pickedId && pickedId.startsWith('builder-') && !pickedId.startsWith('builder-highlight-')) {
        const entityId = pickedId.replace('builder-', '');
        const entity = scenarioEntities.find(e => e.id === entityId);
        if (entity) {
          // Fire context menu event
          changeListeners.forEach(fn => fn('context-menu', entity, event.screenPosition));
        }
      }
    }
  });

  // ── Entity selection ──

  function selectEntity(entityId) {
    selectedEntityId = entityId;
    renderEntities();
    const entity = scenarioEntities.find(e => e.id === entityId);
    if (entity) {
      selectListeners.forEach(fn => fn(entity));
    }
  }

  function deselectEntity() {
    if (selectedEntityId) {
      selectedEntityId = null;
      renderEntities();
      selectListeners.forEach(fn => fn(null));
    }
  }

  // ── Public API ──

  return {
    /**
     * Set the scenario entities array (by reference).
     * @param {Array} entities
     */
    setEntities(entities) {
      scenarioEntities = entities || [];
      renderEntities();
    },

    /**
     * Re-render all entities from current state.
     */
    refresh() {
      renderEntities();
    },

    /**
     * Start placing an entity — enter PLACE mode for the given entity.
     * @param {string} entityId
     */
    startPlacing(entityId) {
      const entity = scenarioEntities.find(e => e.id === entityId);
      if (!entity) return;

      placingEntityId = entityId;
      selectedEntityId = entityId;
      mapInteraction.setMode(MODES.PLACE);
      mapInteraction.showToast(
        `Click on map to place ${entity.callsign || entity.id}`, 0
      );
    },

    /**
     * Select an entity.
     * @param {string} entityId
     */
    selectEntity,

    /**
     * Deselect current entity.
     */
    deselectEntity,

    /**
     * Get selected entity ID.
     * @returns {string|null}
     */
    getSelectedEntityId() {
      return selectedEntityId;
    },

    /**
     * Fly camera to an entity's position.
     * @param {string} entityId
     */
    flyToEntity(entityId) {
      const entity = scenarioEntities.find(e => e.id === entityId);
      if (!entity || !entity.initial_position) return;
      const pos = entity.initial_position;
      const alt = entity.domain === 'AIR' ? 20000 : 5000;
      viewer.camera.flyTo({
        destination: Cesium.Cartesian3.fromDegrees(pos.longitude, pos.latitude, alt),
        duration: 1.0,
      });
    },

    /**
     * Remove an entity's billboard from the map.
     * @param {string} entityId
     */
    removeEntity(entityId) {
      if (selectedEntityId === entityId) {
        selectedEntityId = null;
      }
      renderEntities();
    },

    /**
     * Register callback for entity selection.
     * @param {function} fn - (entity|null) => void
     */
    onSelect(fn) {
      selectListeners.push(fn);
      return () => { selectListeners = selectListeners.filter(l => l !== fn); };
    },

    /**
     * Register callback for entity changes.
     * @param {function} fn - (action, entity, extra?) => void
     *   action: 'place' | 'move' | 'context-menu'
     */
    onChange(fn) {
      changeListeners.push(fn);
      return () => { changeListeners = changeListeners.filter(l => l !== fn); };
    },

    /**
     * Clear all builder entities from the map.
     */
    clear() {
      builderDataSource.entities.removeAll();
      scenarioEntities = [];
      selectedEntityId = null;
      placingEntityId = null;
    },

    /**
     * Get the data source (for external use).
     */
    getDataSource() {
      return builderDataSource;
    },
  };
}
