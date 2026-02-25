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
