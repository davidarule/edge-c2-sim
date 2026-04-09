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

import * as Cesium from 'cesium';
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

  // Preload DISA SVG symbol files for all configured entity types + default
  const sidcsToPreload = [...new Set([
    ...Object.values(config.sidcMap),
    config.defaultSidc,
  ])];
  await preloadSymbols(sidcsToPreload);

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

  // Wire entity list click in PLAY mode sidebar (BUG-015)
  if (filters && filters.onEntityClick) {
    filters.onEntityClick((entity) => {
      detail.show(entity);
      const pos = entity.position;
      if (pos) {
        const alt = entity.domain === 'AIR' ? 20000 : entity.domain === 'MARITIME' ? 5000 : 2000;
        viewer.camera.flyTo({
          destination: Cesium.Cartesian3.fromDegrees(pos.longitude, pos.latitude, alt),
          duration: 1.0
        });
      }
    });
  }

  // Connect WebSocket (controls and timeline need ws reference)
  let controls, timeline, headerControls;

  let settings;

  // Track last scenario file so we only fly camera on scenario change, not every snapshot
  let _lastScenarioFile = null;

  const zoomToAlt = { 7: 600000, 8: 300000, 9: 150000, 10: 75000, 11: 40000, 12: 20000, 13: 10000 };

  const ws = connectWebSocket(config.wsUrl, {
    onSnapshot: (entities, data) => {
      entityManager.loadSnapshot(entities);
      // Clear timeline on snapshot (reset/restart/reconnect) to prevent duplicates (BUG-005)
      if (timeline) timeline.clearEvents();
      console.log(`Snapshot loaded: ${entities.length} entities`);

      const scenarioChanged = data && data.scenario_file && data.scenario_file !== _lastScenarioFile;
      if (data && data.scenario_file) _lastScenarioFile = data.scenario_file;

      if (data && data.scenario_file && headerControls) {
        headerControls.setCurrentScenario(data.scenario_file);
      }
      if (data && data.scenario_meta && headerControls) {
        headerControls.setScenarioMeta(data.scenario_meta);
      }
      if (headerControls) headerControls.setEntities(entities);

      // Fly to scenario center only when the scenario changes (load/switch/restart)
      // Defer 300ms so entity loading (~500 Cesium entities) doesn't disrupt the animation
      if (scenarioChanged) {
        const meta = data.scenario_meta;
        if (meta && meta.center) {
          const alt = zoomToAlt[meta.zoom] || 120000;
          const dest = Cesium.Cartesian3.fromDegrees(meta.center.lon, meta.center.lat, alt);
          setTimeout(() => viewer.camera.flyTo({ destination: dest, duration: 1.5 }), 300);
        }
      }
    },
    onEntityUpdate: (entity) => entityManager.updateEntity(entity),
    onEntityRemove: (id) => entityManager.removeEntity(id),
    onEvent: (event) => {
      if (timeline) timeline.addEvent(event);
      demoMode.handleEvent(event);
    },
    onTrailHistory: (trails) => {
      entityManager.loadTrailHistory(trails);
      console.log(`Trail history loaded for ${Object.keys(trails).length} entities`);
    },
    onClock: (clockState) => {
      if (controls) controls.updateClock(clockState);
      if (headerControls) headerControls.updateClock(clockState);
      syncCesiumClock(viewer, clockState);
    },
    onRoutes: (routes) => {
      if (settings) settings.setRoutes(routes);
    }
  });

  detail.setWs(ws);
  controls = initPlaybackControls('controls', ws, config);
  headerControls = initHeaderControls(ws, config);
  timeline = initTimeline('timeline', viewer, config, entityManager);

  // Compass widget
  initCompass(viewer);

  // Overlay manager (no UI — settings panel handles the checkboxes)
  const overlays = initOverlayManager(viewer, config);

  // Settings panel (unified gear menu)
  settings = initSettingsPanel(viewer, entityManager, ws, config);
  settings.wireOverlays(overlays);
  // Wire header settings button to open the panel
  const headerSettingsBtn = document.getElementById('header-btn-settings');
  if (headerSettingsBtn) headerSettingsBtn.addEventListener('click', () => settings.showPanel(true));

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

  // Wire tab switching between ORBAT, Scenario, and Layers panels (BUG-006/007/016)
  orbatPanel.onTabChange((tabName) => {
    if (tabName === 'scenario') {
      scenarioPanel.show();
      scenarioPanel.setScenario(currentScenario);
    } else {
      scenarioPanel.hide();
    }
  });

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
        // Show scenario panel only if its tab is active (BUG-006/007/016)
        if (orbatPanel.getActiveTab() === 'scenario') {
          scenarioPanel.show();
          scenarioPanel.setScenario(currentScenario);
        } else {
          scenarioPanel.hide();
        }
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
      // Close the validation modal
      const overlay = document.querySelector('.validation-overlay');
      if (overlay) overlay.remove();

      // Fix link: handle by code/field (BUG-013)
      if (item.code === 'E001' || item.field === 'name') {
        // Switch to Scenario tab and focus the name input
        orbatPanel.switchTab('scenario');
        setTimeout(() => {
          const nameInput = document.querySelector('.scenario-name-input, [data-field="name"]');
          if (nameInput) nameInput.focus();
        }, 100);
      } else if (item.code === 'W001' || item.field === 'description') {
        orbatPanel.switchTab('scenario');
        setTimeout(() => {
          const descInput = document.querySelector('.scenario-desc-input, [data-field="description"]');
          if (descInput) descInput.focus();
        }, 100);
      } else if (item.code === 'E002') {
        // No entities — switch to scenario tab
        orbatPanel.switchTab('scenario');
      } else if (item.entityId) {
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
        // Position tooltip fixed above the entity's screen position (not cursor).
        // worldToWindowCoordinates returns canvas-relative coords; tooltip is in
        // viewport/body space, so add the canvas's bounding rect offset.
        const pos = entityData.position;
        const cartesian = pos
          ? Cesium.Cartesian3.fromDegrees(pos.longitude, pos.latitude, pos.altitude_m || 0)
          : null;
        const sp = cartesian
          ? Cesium.SceneTransforms.worldToWindowCoordinates(viewer.scene, cartesian)
          : null;

        // Measure tooltip height while offscreen (offsetHeight=0 when display:none)
        tooltip.style.left = '-9999px';
        tooltip.style.top = '0';
        tooltip.style.transform = 'none';
        tooltip.classList.add('visible');

        if (sp) {
          const canvasRect = viewer.canvas.getBoundingClientRect();
          const tooltipWidth = tooltip.offsetWidth || 200;
          const tooltipHeight = tooltip.offsetHeight || 60;
          const viewportWidth = window.innerWidth;

          // Convert canvas-relative sp to viewport coords, then calc icon geometry
          const vpX = sp.x + canvasRect.left;
          const vpY = sp.y + canvasRect.top;
          // DISA SVG frames have whitespace padding; 0.38 approximates the visible icon half-height
          const iconHalfH = entityManager.getIconSizePx() * 0.30;

          let left = vpX;
          let top = vpY - iconHalfH - tooltipHeight - 4;  // 4px gap above icon top

          // Clamp horizontally to viewport
          if (left - tooltipWidth / 2 < 0) left = tooltipWidth / 2;
          if (left + tooltipWidth / 2 > viewportWidth) left = viewportWidth - tooltipWidth / 2;
          // Flip below icon if no room above
          if (top < 0) top = vpY + iconHalfH + 4;

          tooltip.style.left = `${left}px`;
          tooltip.style.top = `${top}px`;
          tooltip.style.transform = 'translate(-50%, 0)';
        }
        return;
      }
    }
    tooltip.classList.remove('visible');
  }, Cesium.ScreenSpaceEventType.MOUSE_MOVE);

  // Demo mode button in header (currently hidden — keep wiring for when re-enabled)
  const demoBtnEl = document.getElementById('btn-demo-mode');
  if (demoBtnEl) demoBtnEl.addEventListener('click', () => { demoMode.toggle(); });

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
      <span id="header-scenario-name" class="header-scenario">\u2014</span>
      <button class="header-icon-btn header-info-btn" id="btn-scenario-info" title="Scenario Info"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line></svg></button>
    </div>
    <div class="header-center">
      <span id="connection-status" class="connection-disconnected">\u25cb DISCONNECTED</span>
      <button class="ctrl-btn danger" id="header-btn-reset">\u23ee RESET</button>
      <button class="ctrl-btn" id="header-btn-play-pause">&#9654; PLAY</button>
      <div class="header-speed-group" id="header-speed-group"></div>
    </div>
    <div class="header-right">
      <div class="header-clock-group">
        <div class="header-clock" id="header-sim-time">--:--:--</div>
        <div class="header-clock-label">SIM TIME</div>
      </div>
      <button class="header-icon-btn" id="header-btn-settings" title="Settings">\u2699</button>
      <!-- <button class="demo-mode-btn" id="btn-demo-mode">DEMO MODE</button> -->
      <select id="header-scenario-select" class="header-select">
        <option value="">Loading\u2026</option>
      </select>
    </div>
  `;
}

function initHeaderControls(ws, config) {
  const scenarioSelect = document.getElementById('header-scenario-select');
  const scenarioName = document.getElementById('header-scenario-name');
  const infoBtn = document.getElementById('btn-scenario-info');
  const resetBtn = document.getElementById('header-btn-reset');
  const playPauseBtn = document.getElementById('header-btn-play-pause');
  const speedGroup = document.getElementById('header-speed-group');

  let running = false;
  let currentSpeed = config.defaultSpeed;
  let _scenarioMeta = null;
  let _entities = [];
  let _currentScenarioFile = null;

  // Populate scenario dropdown
  ws.listScenarios((list) => {
    if (!list || list.length === 0) {
      scenarioSelect.innerHTML = '<option value="">\u2014 No scenarios \u2014</option>';
      return;
    }
    scenarioSelect.innerHTML = list.map(s =>
      `<option value="${s.file}">${s.name}</option>`
    ).join('');
    if (_currentScenarioFile) {
      scenarioSelect.value = _currentScenarioFile;
      // Update name label from option text if scenario_meta hasn't arrived yet
      if (!_scenarioMeta) {
        const opt = scenarioSelect.querySelector(`option[value="${_currentScenarioFile.replace(/"/g, '\\"')}"]`);
        if (opt) scenarioName.textContent = opt.textContent;
      }
    }
  });

  // Load scenario on select change
  scenarioSelect.addEventListener('change', () => {
    const file = scenarioSelect.value;
    if (!file) return;
    _currentScenarioFile = file;
    _scenarioMeta = null;
    // Show name immediately from option text; will be overwritten by snapshot meta
    const opt = scenarioSelect.options[scenarioSelect.selectedIndex];
    if (opt) scenarioName.textContent = opt.textContent;
    ws.loadScenario(file);
  });

  // Info button
  infoBtn.addEventListener('click', () => {
    showScenarioInfoModal(_scenarioMeta, _entities, _currentScenarioFile);
  });

  // Reset
  resetBtn.addEventListener('click', () => {
    if (confirm('Reset scenario to beginning?')) ws.reset();
  });

  // Play/Pause
  playPauseBtn.addEventListener('click', () => {
    if (running) ws.pause();
    else ws.resume();
  });

  // Speed buttons
  config.speeds.forEach(speed => {
    const btn = document.createElement('button');
    btn.className = 'header-speed-btn' + (speed === currentSpeed ? ' active' : '');
    btn.textContent = `${speed}x`;
    btn.dataset.speed = speed;
    btn.addEventListener('click', () => {
      currentSpeed = speed;
      ws.setSpeed(speed);
      speedGroup.querySelectorAll('.header-speed-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
    });
    speedGroup.appendChild(btn);
  });

  // Keyboard shortcuts
  document.addEventListener('keydown', (e) => {
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.tagName === 'SELECT') return;
    switch (e.key) {
      case ' ': e.preventDefault(); playPauseBtn.click(); break;
      case '1': ws.setSpeed(1); break;
      case '2': ws.setSpeed(2); break;
      case '3': ws.setSpeed(5); break;
      case '4': ws.setSpeed(10); break;
      case '5': ws.setSpeed(60); break;
      case 'f': case 'F':
        if (!e.ctrlKey && !e.metaKey) {
          e.preventDefault();
          if (document.fullscreenElement) document.exitFullscreen();
          else document.documentElement.requestFullscreen();
        }
        break;
    }
  });

  function updateClock(clockState) {
    if (clockState.sim_time) {
      const el = document.getElementById('header-sim-time');
      if (el) el.textContent = new Date(clockState.sim_time).toISOString().substring(11, 19);
    }
    if (clockState.running !== undefined) {
      running = clockState.running;
      playPauseBtn.innerHTML = running ? '&#9208; PAUSE' : '&#9654; PLAY';
      playPauseBtn.classList.toggle('active', running);
    }
    if (clockState.speed !== undefined) {
      currentSpeed = clockState.speed;
      speedGroup.querySelectorAll('.header-speed-btn').forEach(b => {
        b.classList.toggle('active', parseFloat(b.dataset.speed) === currentSpeed);
      });
    }
  }

  function setCurrentScenario(file) {
    _currentScenarioFile = file || null;
    if (!scenarioSelect || !file) return;
    scenarioSelect.value = file;
    // Fallback: show name from option text until scenario_meta arrives
    if (!_scenarioMeta) {
      const opt = scenarioSelect.querySelector(`option[value="${file.replace(/"/g, '\\"')}"]`);
      if (opt) scenarioName.textContent = opt.textContent;
    }
  }

  function setScenarioMeta(meta) {
    _scenarioMeta = meta || null;
    if (meta && meta.name) scenarioName.textContent = meta.name;
  }

  function setEntities(entities) {
    _entities = entities || [];
  }

  return { updateClock, setCurrentScenario, setScenarioMeta, setEntities };
}

function showScenarioInfoModal(meta, entities, scenarioFile) {
  const existing = document.getElementById('scenario-info-overlay');
  if (existing) existing.remove();

  const overlay = document.createElement('div');
  overlay.id = 'scenario-info-overlay';
  overlay.className = 'scenario-info-overlay';

  // Build scenario ID from filename: "config/scenarios/scn_mal_01.yaml" → "SCN-MAL-01"
  const scenarioId = scenarioFile
    ? scenarioFile.replace('config/scenarios/', '').replace('.yaml', '')
        .toUpperCase().replace(/_/g, '-')
    : null;

  // Title: use meta.name directly (backend already formats it as "SCN-MAL-01: Full Name")
  const modalTitle = meta && meta.name
    ? meta.name
    : (scenarioId || 'Scenario Info');

  // Duration
  const durationText = meta && meta.duration_min != null
    ? `${meta.duration_min} minutes`
    : '<span class="info-loading">Loading\u2026</span>';

  // Description
  const descText = meta && meta.description
    ? meta.description
    : '<span class="info-loading">Loading\u2026</span>';

  // ── Separate scenario vs background entities ──
  const allEntities = entities || [];
  const bgEntities = allEntities.filter(e =>
    e.entity_id?.startsWith('AIS-') ||
    e.metadata?.background === true ||
    e.metadata?.source === 'AIS_REAL'
  );
  const scenarioEntities = allEntities.filter(e =>
    !e.entity_id?.startsWith('AIS-') &&
    !e.metadata?.background &&
    e.metadata?.source !== 'AIS_REAL'
  );

  // ── Order of Battle table ──
  let forcesHtml;
  if (scenarioEntities.length > 0) {
    const rows = scenarioEntities.map((e, i) =>
      `<tr class="${i % 2 === 1 ? 'info-row-alt' : ''}">
        <td class="info-td-id">${e.entity_id || '\u2014'}</td>
        <td>${e.callsign || '\u2014'}</td>
        <td>${e.entity_type || '\u2014'}</td>
        <td>${e.agency || '\u2014'}</td>
      </tr>`
    ).join('');
    forcesHtml = `<div class="info-table-scroll">
      <table class="info-forces-table">
        <thead><tr><th>ID</th><th>Callsign</th><th>Type</th><th>Agency</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>`;
  } else {
    forcesHtml = '<p class="info-empty">No scenario entities loaded yet.</p>';
  }

  // ── Background traffic summary ──
  let bgHtml = '';
  if (bgEntities.length > 0) {
    const bgGroups = {};
    bgEntities.forEach(e => {
      const t = (e.entity_type || '').toUpperCase();
      let cat;
      if (t.includes('CARGO')) cat = 'Cargo';
      else if (t.includes('TANKER') || t.includes('VLCC')) cat = 'Tanker';
      else if (t.includes('PASSENGER') || t.includes('FERRY')) cat = 'Passenger';
      else if (t.includes('FISHING')) cat = 'Fishing';
      else if (t.includes('TUG') || t.includes('SUPPLY') || t.includes('OFFSHORE')) cat = 'Service';
      else cat = 'Other';
      bgGroups[cat] = (bgGroups[cat] || 0) + 1;
    });
    const bgSummary = Object.entries(bgGroups)
      .sort((a, b) => b[1] - a[1])
      .map(([cat, n]) => `<span class="bg-tag">${n} ${cat}</span>`)
      .join('');
    bgHtml = `
      <div class="info-field">
        <span class="info-label">BACKGROUND TRAFFIC</span>
        <p class="info-description">
          This scenario includes <strong>${bgEntities.length}</strong> civilian AIS vessels providing
          realistic maritime traffic in the operational area. These are real vessel tracks captured from AIS data.
        </p>
        <div class="bg-tags">${bgSummary}</div>
      </div>`;
  }

  overlay.innerHTML = `
    <div class="scenario-info-modal">
      <div class="info-modal-header">
        <span class="info-modal-title">${modalTitle}</span>
        <button class="info-modal-close" id="info-modal-close">&times;</button>
      </div>
      <div class="info-modal-body">
        <div class="info-meta-row">
          <div class="info-meta-item">
            <span class="info-label">DURATION</span>
            <span class="info-value">${durationText}</span>
          </div>
          <div class="info-meta-item">
            <span class="info-label">ENTITIES</span>
            <span class="info-value">${scenarioEntities.length} scenario + ${bgEntities.length} background</span>
          </div>
        </div>
        <div class="info-field">
          <span class="info-label">DESCRIPTION</span>
          <p class="info-description">${descText}</p>
        </div>
        <div class="info-field">
          <span class="info-label">ORDER OF BATTLE</span>
          ${forcesHtml}
        </div>
        ${bgHtml}
      </div>
    </div>
  `;

  overlay.addEventListener('click', (e) => { if (e.target === overlay) overlay.remove(); });
  overlay.querySelector('#info-modal-close').addEventListener('click', () => overlay.remove());
  document.body.appendChild(overlay);
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
