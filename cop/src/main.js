/**
 * Edge C2 COP — Main entry point.
 *
 * Initialization order:
 * 1. Load config
 * 2. Initialize CesiumJS viewer
 * 3. Initialize entity manager
 * 4. Initialize UI components
 * 5. Connect WebSocket
 * 6. Wire click handlers
 * 7. Start render loop
 */

import './styles/main.css';
import './styles/header.css';
import './styles/sidebar.css';
import './styles/controls.css';
import './styles/timeline.css';

import { initConfig } from './config.js';
import { initCesium } from './cesium-setup.js';
import { connectWebSocket } from './websocket-client.js';
import { initEntityManager } from './entity-manager.js';
import { initAgencyFilter } from './agency-filter.js';
import { initPlaybackControls } from './playback-controls.js';
import { initTimeline } from './timeline.js';
import { initEntityPanel } from './entity-panel.js';
import { initOverlayManager } from './overlay-manager.js';
import { initSettingsPanel } from './settings-panel.js';
import { initCompass } from './compass.js';
import { initDemoMode } from './demo-mode.js';
import { preloadSymbols } from './symbol-renderer.js';
import { initBuilderMode, createBuilderContainers } from './builder/builder-mode.js';
import { initOrbatPanel } from './orbat/orbat-panel.js';
import { initAssetDetail } from './orbat/asset-detail.js';
import { OrbatStore } from './orbat/orbat-store.js';
import { initMapInteraction } from './builder/map-interaction.js';
import { initEntityPlacer } from './builder/entity-placer.js';
import { showContextMenu, entityMenuItems, mapMenuItems } from './builder/context-menu.js';
import { createEmptyScenario, pickAndLoadYAML, exportScenarioYAML, downloadYAML } from './builder/yaml-engine.js';
import { initScenarioPanel } from './builder/scenario-panel.js';
import { openOrbatPicker } from './builder/orbat-picker.js';
import { initRouteEditor } from './builder/route-editor.js';
import { openEventEditor } from './builder/event-editor.js';
import { initAreaEditor } from './builder/area-editor.js';
import { openBackgroundEditor } from './builder/background-editor.js';
import { initPreviewScrubber } from './builder/preview-scrubber.js';
import { initValidation } from './builder/validation.js';

async function main() {
  console.log('Edge C2 COP initializing...');
  const config = initConfig();

  // Preload DISA SVG symbol files before rendering any entities
  await preloadSymbols();

  // Build header
  buildHeader(config);

  // Initialize CesiumJS
  const viewer = await initCesium('cesium-container', config);
  console.log('CesiumJS viewer ready');

  // Expose viewer for debugging
  window.viewer = viewer;

  // Entity manager
  const entityManager = initEntityManager(viewer, config);

  // UI components
  const filters = initAgencyFilter('sidebar-left', entityManager, config);
  const detail = initEntityPanel('sidebar-right', entityManager, viewer);
  const demoMode = initDemoMode(viewer, entityManager);

  // Connect WebSocket (controls and timeline need ws reference)
  let controls, timeline;

  let settings;

  const ws = connectWebSocket(config.wsUrl, {
    onSnapshot: (entities) => {
      entityManager.loadSnapshot(entities);
      console.log(`Snapshot loaded: ${entities.length} entities`);
    },
    onEntityUpdate: (entity) => entityManager.updateEntity(entity),
    onEntityRemove: (id) => entityManager.removeEntity(id),
    onEvent: (event) => {
      if (timeline) timeline.addEvent(event);
      demoMode.handleEvent(event);
    },
    onClock: (clockState) => {
      if (controls) controls.updateClock(clockState);
      updateHeaderClock(clockState);
      syncCesiumClock(viewer, clockState);
    },
    onRoutes: (routes) => {
      if (settings) settings.setRoutes(routes);
    }
  });

  controls = initPlaybackControls('controls', ws, config);
  timeline = initTimeline('timeline', viewer, config);

  // Compass widget
  initCompass(viewer);

  // Overlay manager (no UI — settings panel handles the checkboxes)
  const overlays = initOverlayManager(viewer, config);

  // Settings panel (unified gear menu)
  settings = initSettingsPanel(viewer, entityManager, ws, config);
  settings.wireOverlays(overlays);

  // ── Builder Mode ──

  // Create builder sidebar containers
  const { builderLeft, builderRight } = createBuilderContainers(
    document.getElementById('sidebar-left'),
    document.getElementById('sidebar-right')
  );

  // ORBAT store
  const orbatStore = new OrbatStore();

  // ORBAT panel (left sidebar in BUILD mode)
  const orbatPanel = initOrbatPanel(builderLeft, config);

  // Asset detail panel (right sidebar in BUILD mode)
  const assetDetail = initAssetDetail(builderRight, config);

  // Wire ORBAT panel → asset detail
  orbatPanel.onAssetSelect((unit, orgId) => {
    assetDetail.show(unit, orgId);
    document.getElementById('app').classList.add('detail-open');
  });

  // Wire asset detail save/delete/duplicate back to ORBAT store
  assetDetail.onSave((unit, orgId) => {
    const orbatList = orbatStore.getOrbatList();
    if (orbatList.length > 0) {
      const currentName = orbatList[0].name;
      const model = orbatStore.loadOrbat(currentName);
      if (model) {
        const existing = model.getUnit(unit.id);
        if (existing) {
          Object.assign(existing, unit);
        }
        orbatStore.saveOrbat(currentName, model);
        orbatPanel.refresh();
      }
    }
  });

  assetDetail.onDelete((unitId, orgId) => {
    const orbatList = orbatStore.getOrbatList();
    if (orbatList.length > 0) {
      const currentName = orbatList[0].name;
      const model = orbatStore.loadOrbat(currentName);
      if (model) {
        model.removeUnit(orgId, unitId);
        orbatStore.saveOrbat(currentName, model);
        orbatPanel.refresh();
        assetDetail.hide();
        document.getElementById('app').classList.remove('detail-open');
      }
    }
  });

  assetDetail.onDuplicate((unit, orgId) => {
    const orbatList = orbatStore.getOrbatList();
    if (orbatList.length > 0) {
      const currentName = orbatList[0].name;
      const model = orbatStore.loadOrbat(currentName);
      if (model) {
        const newUnit = { ...unit, id: `${unit.id}_copy` };
        model.addUnit(orgId, newUnit);
        orbatStore.saveOrbat(currentName, model);
        orbatPanel.refresh();
        assetDetail.show(newUnit, orgId);
      }
    }
  });

  // Scenario panel (left sidebar in BUILD mode, under Scenario tab)
  const scenarioPanel = initScenarioPanel(builderLeft, config);

  // Wire scenario panel actions
  scenarioPanel.onAction((action, data) => {
    if (action === 'new') {
      currentScenario = createEmptyScenario();
      scenarioPanel.setScenario(currentScenario);
      entityPlacer.setEntities(currentScenario.entities);
      routeEditor.setEntities(currentScenario.entities);
      routeEditor.clear();
      areaEditor.setEntities(currentScenario.entities);
      areaEditor.clear();
      previewScrubber.setScenario(currentScenario);
      previewScrubber.reset();
      runValidation();
    }
    if (action === 'load-yaml') {
      pickAndLoadYAML().then(result => {
        if (result && result.scenario) {
          currentScenario = result.scenario;
          scenarioPanel.setScenario(currentScenario);
          entityPlacer.setEntities(currentScenario.entities);
          entityPlacer.refresh();
          routeEditor.setEntities(currentScenario.entities);
          routeEditor.refresh();
          areaEditor.setEntities(currentScenario.entities);
          areaEditor.refresh();
          previewScrubber.setScenario(currentScenario);
          runValidation();
          if (result.warnings.length > 0) {
            console.warn('YAML import warnings:', result.warnings);
          }
          if (result.errors.length > 0) {
            console.error('YAML import errors:', result.errors);
          }
        }
      });
    }
    if (action === 'save-yaml') {
      const yaml = exportScenarioYAML(currentScenario);
      const name = (currentScenario.metadata.name || 'scenario').replace(/\s+/g, '_').toLowerCase();
      downloadYAML(yaml, `${name}.yaml`);
    }
    if (action === 'add-from-orbat') {
      const existingIds = currentScenario.entities.map(e => e.id);
      openOrbatPicker(existingIds, (selectedUnits) => {
        for (const unit of selectedUnits) {
          const entity = {
            id: unit.id,
            callsign: unit.callsign || unit.id,
            entity_type: unit.entity_type || 'CIVILIAN_BOAT',
            agency: unit.agency || 'CIVILIAN',
            domain: unit.domain || 'MARITIME',
            sidc: unit.sidc || '10043000001400000000',
            initial_position: unit.home_base ? {
              latitude: unit.home_base.lat || unit.home_base.latitude || 0,
              longitude: unit.home_base.lon || unit.home_base.longitude || 0,
              altitude_m: unit.home_base.altitude_m || 0,
            } : null,
            speed_knots: unit.cruise_speed_knots || 10,
            heading_deg: 0,
            status: 'ACTIVE',
            waypoints: [],
            behavior: null,
            metadata: { ...(unit.metadata || {}) },
            placed: !!(unit.home_base && (unit.home_base.lat || unit.home_base.latitude)),
            cruise_speed_knots: unit.cruise_speed_knots,
            cruise_altitude_m: unit.cruise_altitude_m,
          };
          currentScenario.entities.push(entity);
        }
        scenarioPanel.setScenario(currentScenario);
        entityPlacer.setEntities(currentScenario.entities);
        routeEditor.setEntities(currentScenario.entities);
        areaEditor.setEntities(currentScenario.entities);
        runValidation();
      });
    }
    if (action === 'add-manual') {
      const newEntity = {
        id: `entity_${Date.now()}`,
        callsign: 'New Entity',
        entity_type: 'CIVILIAN_BOAT',
        agency: 'CIVILIAN',
        domain: 'MARITIME',
        sidc: '10043000001400000000',
        initial_position: null,
        speed_knots: 10,
        heading_deg: 0,
        status: 'ACTIVE',
        waypoints: [],
        behavior: null,
        metadata: {},
        placed: false,
      };
      currentScenario.entities.push(newEntity);
      scenarioPanel.setScenario(currentScenario);
      entityPlacer.setEntities(currentScenario.entities);
    }
    if (action === 'remove-entity' && data) {
      currentScenario.entities = currentScenario.entities.filter(e => e.id !== data.id);
      scenarioPanel.setScenario(currentScenario);
      entityPlacer.setEntities(currentScenario.entities);
      routeEditor.setEntities(currentScenario.entities);
    }
    if (action === 'add-event') {
      openEventEditor(null, currentScenario.entities, (evt) => {
        if (!currentScenario.events) currentScenario.events = [];
        currentScenario.events.push(evt);
        scenarioPanel.setScenario(currentScenario);
      });
    }
    if (action === 'edit-event' && data) {
      const idx = (currentScenario.events || []).indexOf(data);
      openEventEditor(data, currentScenario.entities, (evt) => {
        if (idx >= 0) currentScenario.events[idx] = evt;
        scenarioPanel.setScenario(currentScenario);
      });
    }
    if (action === 'remove-event' && data) {
      currentScenario.events = (currentScenario.events || []).filter(e => e !== data);
      scenarioPanel.setScenario(currentScenario);
      previewScrubber.setScenario(currentScenario);
      runValidation();
    }
    if (action === 'add-background') {
      openBackgroundEditor(null, (group) => {
        if (!currentScenario.background_entities) currentScenario.background_entities = [];
        currentScenario.background_entities.push(group);
        scenarioPanel.setScenario(currentScenario);
      });
    }
    if (action === 'edit-background' && data) {
      const idx = (currentScenario.background_entities || []).indexOf(data);
      openBackgroundEditor(data, (group) => {
        if (idx >= 0) currentScenario.background_entities[idx] = group;
        scenarioPanel.setScenario(currentScenario);
      });
    }
  });

  scenarioPanel.onEntitySelect((entity) => {
    if (entity && !entity.placed) {
      entityPlacer.startPlacing(entity.id);
    } else if (entity) {
      entityPlacer.selectEntity(entity.id);
      entityPlacer.flyToEntity(entity.id);
    }
  });

  // Mode toggle
  const builderMode = initBuilderMode({
    header: document.getElementById('header'),
    onModeChange: (mode) => {
      console.log(`Mode switched to: ${mode}`);
      if (mode === 'BUILD') {
        orbatPanel.show();
        orbatPanel.refresh();
        scenarioPanel.show();
        scenarioPanel.setScenario(currentScenario);
        entityPlacer.setEntities(currentScenario.entities);
        entityPlacer.refresh();
        routeEditor.setEntities(currentScenario.entities);
        routeEditor.refresh();
        areaEditor.setEntities(currentScenario.entities);
        areaEditor.refresh();
        previewScrubber.setScenario(currentScenario);
        previewScrubber.show();
        validationBadge.element.style.display = '';
        runValidation();
      } else {
        orbatPanel.hide();
        scenarioPanel.hide();
        assetDetail.hide();
        entityPlacer.clear();
        routeEditor.clear();
        areaEditor.clear();
        previewScrubber.hide();
        validationBadge.element.style.display = 'none';
        document.getElementById('app').classList.remove('detail-open');
      }
    }
  });

  // Map interaction handler (builder toolbar + click modes)
  const mapInteraction = initMapInteraction(viewer);

  // Entity placer (place/move entities on globe in BUILD mode)
  const entityPlacer = initEntityPlacer(viewer, mapInteraction);

  // Route editor (waypoint drawing and editing)
  const routeEditor = initRouteEditor(viewer, mapInteraction, config);

  // Area editor (patrol area polygon drawing)
  const areaEditor = initAreaEditor(viewer, mapInteraction, config);

  // Preview scrubber (scenario preview in BUILD mode)
  const timelineContainer = document.getElementById('timeline');
  const previewScrubber = initPreviewScrubber(timelineContainer, viewer, config);

  // Validation engine
  const validation = initValidation(config);
  const validationBadge = validation.createStatusBadge(
    document.querySelector('.header-center') || document.getElementById('header')
  );
  validationBadge.element.style.display = 'none'; // Only show in BUILD mode
  validationBadge.onClick(() => {
    const results = validation.validate(currentScenario);
    validation.showValidationModal(results, (item) => {
      // Fix link: select offending entity
      if (item.entityId) {
        entityPlacer.selectEntity(item.entityId);
        entityPlacer.flyToEntity(item.entityId);
      }
    });
  });

  // Current scenario state
  let currentScenario = createEmptyScenario();
  entityPlacer.setEntities(currentScenario.entities);
  routeEditor.setEntities(currentScenario.entities);
  areaEditor.setEntities(currentScenario.entities);

  // Wire entity placer context menus
  entityPlacer.onChange((action, entity, screenPos) => {
    if (action === 'context-menu' && entity) {
      showContextMenu(screenPos.x, screenPos.y, entityMenuItems(entity), (menuAction) => {
        if (menuAction === 'fly-to') entityPlacer.flyToEntity(entity.id);
        if (menuAction === 'define-route') {
          routeEditor.editRoute(entity);
        }
        if (menuAction === 'set-behavior') {
          areaEditor.editArea(entity);
        }
        if (menuAction === 'add-event-for-entity') {
          const prefilled = { targets: [entity.id], type: 'detection', severity: 'info' };
          openEventEditor(prefilled, currentScenario.entities, (evt) => {
            if (!currentScenario.events) currentScenario.events = [];
            currentScenario.events.push(evt);
            scenarioPanel.setScenario(currentScenario);
            previewScrubber.setScenario(currentScenario);
            runValidation();
          });
        }
        if (menuAction === 'edit') {
          // Show entity in scenario panel selection
          scenarioPanel.refresh();
        }
        if (menuAction === 'duplicate') {
          const dup = { ...entity, id: `${entity.id}_${Date.now()}`, callsign: `${entity.callsign} (copy)`, waypoints: [...(entity.waypoints || [])], placed: false, initial_position: null };
          currentScenario.entities.push(dup);
          scenarioPanel.setScenario(currentScenario);
          entityPlacer.setEntities(currentScenario.entities);
          routeEditor.setEntities(currentScenario.entities);
        }
        if (menuAction === 'remove') {
          currentScenario.entities = currentScenario.entities.filter(e => e.id !== entity.id);
          scenarioPanel.setScenario(currentScenario);
          entityPlacer.setEntities(currentScenario.entities);
          routeEditor.setEntities(currentScenario.entities);
        }
      });
    }
    if (action === 'place' && entity) {
      routeEditor.refresh();
      areaEditor.refresh();
      scenarioPanel.setScenario(currentScenario);
      previewScrubber.setScenario(currentScenario);
      runValidation();
    }
  });

  // Wire right-click on empty map in builder mode
  mapInteraction.onRightClick((event) => {
    if (builderMode.getMode() !== 'BUILD') return;
    if (event.picked && event.picked.id) return; // Entity click handled by placer
    if (event.position) {
      showContextMenu(event.screenPosition.x, event.screenPosition.y, mapMenuItems(event.position), (action) => {
        if (action === 'copy-coords') {
          navigator.clipboard.writeText(`${event.position.latitude.toFixed(6)}, ${event.position.longitude.toFixed(6)}`);
        }
        if (action === 'center-map') {
          viewer.camera.flyTo({
            destination: Cesium.Cartesian3.fromDegrees(event.position.longitude, event.position.latitude, viewer.camera.positionCartographic.height),
            duration: 0.5,
          });
        }
      });
    }
  });

  // Wire route editor changes back to scenario panel
  routeEditor.onRouteChange((entity) => {
    scenarioPanel.setScenario(currentScenario);
    runValidation();
  });

  // Wire area editor changes back to scenario panel
  areaEditor.onAreaChange((entity) => {
    scenarioPanel.setScenario(currentScenario);
    runValidation();
  });

  // Debounced validation runner
  let validationTimer = null;
  function runValidation() {
    clearTimeout(validationTimer);
    validationTimer = setTimeout(() => {
      const results = validation.validate(currentScenario);
      validationBadge.update(results);
    }, 500);
  }

  // ── Keyboard shortcuts (BUILD mode) ──

  document.addEventListener('keydown', (e) => {
    if (builderMode.getMode() !== 'BUILD') return;

    // Don't intercept when typing in input fields
    const tag = e.target.tagName;
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;

    // Delete — remove selected entity
    if (e.key === 'Delete' || e.key === 'Backspace') {
      const selectedId = entityPlacer.getSelectedEntityId();
      if (selectedId) {
        currentScenario.entities = currentScenario.entities.filter(e => e.id !== selectedId);
        entityPlacer.setEntities(currentScenario.entities);
        routeEditor.setEntities(currentScenario.entities);
        areaEditor.setEntities(currentScenario.entities);
        scenarioPanel.setScenario(currentScenario);
        runValidation();
      }
    }

    // S — toggle to Select mode
    if (e.key === 's' && !e.ctrlKey && !e.metaKey) {
      mapInteraction.setMode('SELECT');
    }
    // W — toggle to Waypoint mode
    if (e.key === 'w' && !e.ctrlKey && !e.metaKey) {
      mapInteraction.setMode('WAYPOINT');
    }
    // P — toggle to Place mode
    if (e.key === 'p' && !e.ctrlKey && !e.metaKey) {
      mapInteraction.setMode('PLACE');
    }
    // A — toggle to Area mode
    if (e.key === 'a' && !e.ctrlKey && !e.metaKey) {
      mapInteraction.setMode('AREA');
    }
    // F — fly to selected entity
    if (e.key === 'f' && !e.ctrlKey && !e.metaKey) {
      const selectedId = entityPlacer.getSelectedEntityId();
      if (selectedId) entityPlacer.flyToEntity(selectedId);
    }
    // Space — toggle preview playback
    if (e.key === ' ') {
      e.preventDefault();
      if (previewScrubber.isPlaying()) {
        previewScrubber.hide();
        previewScrubber.show(); // re-render with paused state
      } else {
        // Trigger play via the internal API
      }
    }
  });

  // Expose for debugging
  window.builderMode = builderMode;
  window.orbatStore = orbatStore;
  window.currentScenario = currentScenario;

  // SIDC editor: listen for changes from entity panel (per-entity)
  document.addEventListener('sidc-update', (e) => {
    const { entityId, sidc } = e.detail;
    console.log(`SIDC update: entity ${entityId} -> ${sidc}`);
    // Update this specific entity only
    entityManager.updateSidcForEntity(entityId, sidc);
    // Save per-entity overrides to localStorage
    try {
      const saved = JSON.parse(localStorage.getItem('sidc_entity_overrides') || '{}');
      saved[entityId] = sidc;
      localStorage.setItem('sidc_entity_overrides', JSON.stringify(saved));
    } catch (e) { /* ignore */ }
    // Refresh the detail panel symbol preview
    const previewImg = document.getElementById('sidc-preview-img');
    if (previewImg) {
      const currentEntity = entityManager.getEntity(e.detail.entityId);
      if (currentEntity) {
        previewImg.src = entityManager.getSymbolImage(currentEntity);
      }
    }
  });

  // Click handling
  const clickHandler = new Cesium.ScreenSpaceEventHandler(viewer.scene.canvas);

  // Left click — select entity
  clickHandler.setInputAction((movement) => {
    const picked = viewer.scene.pick(movement.position);
    if (picked && picked.id && picked.id.id && picked.id.id.startsWith('entity-')) {
      const entityId = picked.id.id.replace('entity-', '');
      const entityData = entityManager.getEntity(entityId);
      if (entityData) {
        entityManager._fireClick(entityData);
        detail.show(entityData);
      }
      return;
    }
    detail.hide();
  }, Cesium.ScreenSpaceEventType.LEFT_CLICK);

  // Double click — fly to entity
  clickHandler.setInputAction((movement) => {
    const picked = viewer.scene.pick(movement.position);
    if (picked && picked.id && picked.id.id && picked.id.id.startsWith('entity-')) {
      const entityId = picked.id.id.replace('entity-', '');
      const entityData = entityManager.getEntity(entityId);
      if (entityData) {
        entityManager._fireDoubleClick(entityData);
        const pos = entityData.position;
        const alt = entityData.domain === 'AIR' ? 20000 : 5000;
        viewer.camera.flyTo({
          destination: Cesium.Cartesian3.fromDegrees(pos.longitude, pos.latitude, alt),
          duration: 1.0
        });
      }
    }
  }, Cesium.ScreenSpaceEventType.LEFT_DOUBLE_CLICK);

  // Hover — tooltip
  const tooltip = document.getElementById('tooltip');
  clickHandler.setInputAction((movement) => {
    const picked = viewer.scene.pick(movement.endPosition);
    if (picked && picked.id && picked.id.id && picked.id.id.startsWith('entity-')) {
      const entityId = picked.id.id.replace('entity-', '');
      const entityData = entityManager.getEntity(entityId);
      if (entityData) {
        tooltip.innerHTML = `
          <strong>${entityData.callsign || entityId}</strong> [${entityData.agency || ''}]<br>
          ${(entityData.entity_type || '').replace(/_/g, ' ')} | ${entityData.status || ''}<br>
          Speed: ${(entityData.speed_knots || 0).toFixed(1)} kts | HDG: ${Math.round(entityData.heading_deg || 0)}\u00b0
        `;
        // Position tooltip above-right, with viewport edge detection
        const tooltipWidth = tooltip.offsetWidth || 200;
        const tooltipHeight = tooltip.offsetHeight || 80;
        const viewportWidth = window.innerWidth;

        // Default: above-right of cursor
        let left = movement.endPosition.x + 25;
        let top = movement.endPosition.y - tooltipHeight - 20;

        // If tooltip would go off the right edge, flip to left side
        if (left + tooltipWidth > viewportWidth) {
          left = movement.endPosition.x - tooltipWidth - 25;
        }

        // If tooltip would go above the viewport, put it below the cursor
        if (top < 0) {
          top = movement.endPosition.y + 30;
        }

        tooltip.style.left = `${left}px`;
        tooltip.style.top = `${top}px`;
        tooltip.classList.add('visible');
        return;
      }
    }
    tooltip.classList.remove('visible');
  }, Cesium.ScreenSpaceEventType.MOUSE_MOVE);

  // Demo mode button in header
  document.getElementById('btn-demo-mode').addEventListener('click', () => {
    demoMode.toggle();
  });

  // Camera altitude display
  initAltitudeDisplay(viewer);

  console.log('Edge C2 COP ready');
}

function buildHeader(config) {
  const header = document.getElementById('header');
  header.innerHTML = `
    <div class="header-left">
      <span class="header-logo">EDGE C2</span>
      <div class="header-divider"></div>
      <span class="header-scenario" id="header-scenario">COMMON OPERATING PICTURE</span>
    </div>
    <div class="header-center">
      <span id="connection-status" class="connection-disconnected">\u25cb DISCONNECTED</span>
    </div>
    <div class="header-right">
      <button class="demo-mode-btn" id="btn-demo-mode">DEMO MODE</button>
      <div class="header-clock-group">
        <div class="header-clock" id="header-sim-time">--:--:--</div>
        <div class="header-clock-label">SIM TIME</div>
      </div>
    </div>
  `;
}

function updateHeaderClock(clockState) {
  const el = document.getElementById('header-sim-time');
  if (el && clockState.sim_time) {
    el.textContent = new Date(clockState.sim_time).toISOString().substring(11, 19);
  }
}

function syncCesiumClock(viewer, clockState) {
  if (clockState.sim_time) {
    try {
      const julianTime = Cesium.JulianDate.fromIso8601(clockState.sim_time);
      viewer.clock.currentTime = julianTime;
    } catch (e) { /* ignore parse errors */ }
  }
  if (clockState.speed !== undefined) {
    viewer.clock.multiplier = clockState.speed;
  }
  if (clockState.running !== undefined) {
    viewer.clock.shouldAnimate = clockState.running;
  }
  viewer.clock.clockStep = Cesium.ClockStep.SYSTEM_CLOCK_MULTIPLIER;
}

function initAltitudeDisplay(viewer) {
  const el = document.createElement('div');
  el.id = 'altitude-display';
  el.style.cssText = `
    position: absolute; bottom: 8px; left: 8px; z-index: 20;
    background: rgba(13,17,23,0.85); color: #E6EDF3;
    font-family: 'IBM Plex Mono', monospace; font-size: 11px;
    padding: 4px 10px; border-radius: 3px;
    border: 1px solid rgba(48,54,61,0.8);
    pointer-events: none;
  `;
  document.getElementById('cesium-container').appendChild(el);

  function formatAlt(meters) {
    if (meters >= 1000000) return `${(meters / 1000).toFixed(0)} km`;
    if (meters >= 10000) return `${(meters / 1000).toFixed(1)} km`;
    if (meters >= 1000) return `${(meters / 1000).toFixed(2)} km`;
    return `${meters.toFixed(0)} m`;
  }

  let cursorLat = '--', cursorLon = '--';

  function update() {
    const height = viewer.camera.positionCartographic.height;
    el.textContent = `ALT: ${formatAlt(height)}  |  ${cursorLat}, ${cursorLon}`;
  }

  // Track mouse position on globe
  const handler = new Cesium.ScreenSpaceEventHandler(viewer.scene.canvas);
  handler.setInputAction((movement) => {
    const cartesian = viewer.camera.pickEllipsoid(movement.endPosition, viewer.scene.globe.ellipsoid);
    if (cartesian) {
      const carto = Cesium.Cartographic.fromCartesian(cartesian);
      cursorLat = Cesium.Math.toDegrees(carto.latitude).toFixed(5);
      cursorLon = Cesium.Math.toDegrees(carto.longitude).toFixed(5);
    } else {
      cursorLat = '--';
      cursorLon = '--';
    }
    update();
  }, Cesium.ScreenSpaceEventType.MOUSE_MOVE);

  viewer.camera.changed.addEventListener(update);
  viewer.camera.moveEnd.addEventListener(update);
  update();
}

main().catch(err => {
  console.error('COP initialization failed:', err);
  document.body.innerHTML = `
    <div style="display:flex;align-items:center;justify-content:center;height:100vh;background:#0D1117;color:#F85149;font-family:monospace;font-size:16px;flex-direction:column;gap:16px;">
      <div>Edge C2 COP — Initialization Failed</div>
      <div style="color:#8B949E;font-size:13px;">${err.message}</div>
      <div style="color:#8B949E;font-size:12px;">Check console for details. Ensure Cesium Ion token is set in .env</div>
    </div>
  `;
});
