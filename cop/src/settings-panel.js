/**
 * Unified Settings & Control panel.
 *
 * Replaces the old overlay-manager gear icon menu.
 * Sections: Simulation, Display, Clustering, Overlays.
 */

export function initSettingsPanel(viewer, entityManager, ws, config) {
  const cesiumContainer = document.getElementById('cesium-container');

  // State
  let panelOpen = false;
  let iconScale = 40;           // px (maps to billboard scale = px/40)
  let labelsVisible = true;
  let trailsVisible = true;
  let clusteringEnabled = false;
  let plannedTracksVisible = false;
  let routeEntities = [];       // Cesium entities for planned tracks
  let routeData = null;         // Raw route data from WS

  // References to overlay manager (set via wireOverlays)
  let overlayManager = null;

  // ── Build panel HTML ──

  const panel = document.createElement('div');
  panel.id = 'settings-panel';
  panel.style.cssText = `
    position: absolute; top: 10px; right: 10px; z-index: 100;
    width: 220px; max-height: calc(100% - 20px);
    background: rgba(22,27,34,0.95); border: 1px solid #30363D;
    border-radius: 4px; display: none; overflow: hidden;
    font-family: 'IBM Plex Sans', sans-serif; color: #C9D1D9;
    display: none; flex-direction: column;
  `;

  const toggleBtn = document.createElement('button');
  toggleBtn.id = 'settings-toggle';
  toggleBtn.innerHTML = '\u2699';
  toggleBtn.title = 'Settings';
  toggleBtn.style.cssText = `
    position: absolute; top: 10px; right: 10px; z-index: 101;
    background: rgba(13,17,23,0.8); border: 1px solid #30363D;
    border-radius: 4px; padding: 5px 9px; cursor: pointer;
    color: #8B949E; font-size: 16px; line-height: 1;
  `;

  toggleBtn.addEventListener('click', () => { showPanel(true); });

  function showPanel(open) {
    panelOpen = open;
    panel.style.display = open ? 'flex' : 'none';
    toggleBtn.style.display = open ? 'none' : 'block';
  }

  // ── Panel content ──

  panel.innerHTML = `
    <div class="settings-header" style="
      padding: 8px 10px; display: flex; justify-content: space-between; align-items: center;
      border-bottom: 1px solid #30363D; flex-shrink: 0;
    ">
      <span style="font-size: 11px; letter-spacing: 1px; color: #8B949E; text-transform: uppercase;">\u2699 SETTINGS</span>
      <button id="settings-close" style="
        background: none; border: none; color: #8B949E; cursor: pointer;
        font-size: 14px; padding: 0 2px; line-height: 1;
      ">\u2715</button>
    </div>
    <div class="settings-body" style="overflow-y: auto; padding: 0; flex: 1;">

      <!-- SIMULATION -->
      <div class="settings-section">
        <div class="settings-section-title">SIMULATION</div>
        <div class="settings-row">
          <button id="btn-restart-sim" class="settings-btn">Restart Simulator</button>
        </div>
      </div>

      <!-- DISPLAY -->
      <div class="settings-section">
        <div class="settings-section-title">DISPLAY</div>
        <div class="settings-row" style="flex-direction: column; align-items: stretch;">
          <div style="display: flex; justify-content: space-between; margin-bottom: 4px;">
            <span>Icon Size</span>
            <span id="icon-size-val" style="color: #8B949E; font-family: 'IBM Plex Mono', monospace;">40px</span>
          </div>
          <input id="slider-icon-size" type="range" min="20" max="80" value="40" class="settings-slider">
        </div>
        <div class="settings-row">
          <label class="settings-check-label">
            <input type="checkbox" id="chk-labels" checked>
            <span>Show Labels</span>
          </label>
        </div>
        <div class="settings-row">
          <label class="settings-check-label">
            <input type="checkbox" id="chk-trails" checked>
            <span>Show Trails</span>
          </label>
        </div>
      </div>

      <!-- CLUSTERING -->
      <div class="settings-section">
        <div class="settings-section-title">CLUSTERING</div>
        <div class="settings-row">
          <label class="settings-check-label">
            <input type="checkbox" id="chk-clustering">
            <span>Enable Clustering</span>
          </label>
        </div>
      </div>

      <!-- OVERLAYS -->
      <div class="settings-section">
        <div class="settings-section-title">OVERLAYS</div>
        <div id="overlay-checkboxes"></div>
        <div class="settings-row">
          <label class="settings-check-label">
            <input type="checkbox" id="chk-planned-tracks">
            <span>Show Planned Tracks</span>
          </label>
        </div>
      </div>
    </div>
  `;

  cesiumContainer.appendChild(panel);
  cesiumContainer.appendChild(toggleBtn);

  // Inject scoped styles
  const style = document.createElement('style');
  style.textContent = `
    #settings-panel .settings-section {
      border-bottom: 1px solid #30363D;
      padding: 8px 10px;
    }
    #settings-panel .settings-section:last-child {
      border-bottom: none;
    }
    #settings-panel .settings-section-title {
      font-size: 11px; font-weight: 600;
      letter-spacing: 0.8px; color: #8B949E;
      text-transform: uppercase; margin-bottom: 6px;
    }
    #settings-panel .settings-row {
      display: flex; align-items: center;
      padding: 3px 0; font-size: 12px;
    }
    #settings-panel .settings-check-label {
      display: flex; align-items: center; gap: 6px;
      cursor: pointer; font-size: 12px;
    }
    #settings-panel .settings-check-label input[type="checkbox"] {
      accent-color: #58A6FF; cursor: pointer;
    }
    #settings-panel .settings-btn {
      width: 100%; padding: 5px 0; border: 1px solid #30363D;
      background: #21262D; color: #C9D1D9; border-radius: 3px;
      cursor: pointer; font-family: 'IBM Plex Sans', sans-serif;
      font-size: 12px;
    }
    #settings-panel .settings-btn:hover {
      background: #30363D;
    }
    #settings-panel .settings-slider {
      -webkit-appearance: none; width: 100%; height: 4px;
      background: #30363D; border-radius: 2px; outline: none;
    }
    #settings-panel .settings-slider::-webkit-slider-thumb {
      -webkit-appearance: none; width: 14px; height: 14px;
      background: #58A6FF; border-radius: 50%; cursor: pointer;
    }
    #settings-panel .settings-slider::-moz-range-thumb {
      width: 14px; height: 14px;
      background: #58A6FF; border-radius: 50%; cursor: pointer;
      border: none;
    }
  `;
  document.head.appendChild(style);

  // ── Wire events ──

  panel.querySelector('#settings-close').addEventListener('click', () => showPanel(false));

  // Restart
  panel.querySelector('#btn-restart-sim').addEventListener('click', () => {
    ws.restart();
  });

  // Icon size slider
  const sliderIconSize = panel.querySelector('#slider-icon-size');
  const iconSizeVal = panel.querySelector('#icon-size-val');
  sliderIconSize.addEventListener('input', () => {
    iconScale = parseInt(sliderIconSize.value, 10);
    iconSizeVal.textContent = `${iconScale}px`;
    entityManager.setIconScale(iconScale);
  });

  // Show Labels
  panel.querySelector('#chk-labels').addEventListener('change', (e) => {
    labelsVisible = e.target.checked;
    entityManager.setLabelsVisible(labelsVisible);
  });

  // Show Trails
  panel.querySelector('#chk-trails').addEventListener('change', (e) => {
    trailsVisible = e.target.checked;
    entityManager.setTrailsVisible(trailsVisible);
  });

  // Clustering
  panel.querySelector('#chk-clustering').addEventListener('change', (e) => {
    clusteringEnabled = e.target.checked;
    entityManager.setClusteringEnabled(clusteringEnabled);
    applyClustering(clusteringEnabled);
  });

  // Planned tracks
  panel.querySelector('#chk-planned-tracks').addEventListener('change', (e) => {
    plannedTracksVisible = e.target.checked;
    renderPlannedTracks();
  });

  // ── Clustering ──

  function applyClustering(enabled) {
    const ds = entityManager.getDataSource();
    if (!ds || !ds.clustering) return;
    const cluster = ds.clustering;
    cluster.enabled = enabled;
    if (enabled) {
      cluster.pixelRange = 50;
      cluster.minimumClusterSize = 2;
      cluster.clusterBillboards = true;
      cluster.clusterLabels = true;
      cluster.clusterPoints = false;

      // Generate cluster billboard: circle with count
      if (!cluster._settingsPanelListenerAdded) {
        cluster.clusterEvent.addEventListener((clusteredEntities, clusterObj) => {
          clusterObj.label.show = false;
          clusterObj.billboard.show = true;
          clusterObj.billboard.image = makeClusterIcon(clusteredEntities.length);
          clusterObj.billboard.verticalOrigin = Cesium.VerticalOrigin.CENTER;
          clusterObj.billboard.horizontalOrigin = Cesium.HorizontalOrigin.CENTER;
          clusterObj.billboard.disableDepthTestDistance = Number.POSITIVE_INFINITY;
        });
        cluster._settingsPanelListenerAdded = true;
      }
    }
  }

  const clusterIconCache = new Map();
  function makeClusterIcon(count) {
    if (clusterIconCache.has(count)) return clusterIconCache.get(count);
    const size = 36;
    const canvas = document.createElement('canvas');
    canvas.width = size;
    canvas.height = size;
    const ctx = canvas.getContext('2d');
    // Circle
    ctx.beginPath();
    ctx.arc(size / 2, size / 2, size / 2 - 2, 0, Math.PI * 2);
    ctx.fillStyle = 'rgba(88,166,255,0.85)';
    ctx.fill();
    ctx.strokeStyle = '#C9D1D9';
    ctx.lineWidth = 1.5;
    ctx.stroke();
    // Count text
    ctx.fillStyle = '#FFFFFF';
    ctx.font = 'bold 13px IBM Plex Sans, sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(String(count), size / 2, size / 2);
    const url = canvas.toDataURL();
    clusterIconCache.set(count, url);
    return url;
  }

  // ── Planned tracks (dashed polylines) ──

  function renderPlannedTracks() {
    // Remove existing
    routeEntities.forEach(e => viewer.entities.remove(e));
    routeEntities = [];

    if (!plannedTracksVisible || !routeData) return;

    routeData.forEach(route => {
      const positions = route.waypoints.map(wp =>
        Cesium.Cartesian3.fromDegrees(wp.longitude, wp.latitude, wp.altitude_m || 0)
      );
      if (positions.length < 2) return;

      const agencyColor = config.agencyColors[route.agency] || '#8B949E';
      const color = Cesium.Color.fromCssColorString(agencyColor).withAlpha(0.6);

      const entity = viewer.entities.add({
        id: `route-${route.entity_id}`,
        polyline: {
          positions,
          width: 2,
          material: new Cesium.PolylineDashMaterialProperty({
            color,
            dashLength: 12,
            dashPattern: parseInt('1111000011110000', 2)
          })
        }
      });
      routeEntities.push(entity);
    });
  }

  // ── Overlay integration ──

  function wireOverlays(ovManager) {
    overlayManager = ovManager;
    const container = panel.querySelector('#overlay-checkboxes');
    const defs = ovManager.getOverlayDefs();
    defs.forEach(def => {
      const row = document.createElement('div');
      row.className = 'settings-row';
      row.innerHTML = `
        <label class="settings-check-label">
          <input type="checkbox" data-overlay-id="${def.id}" ${def.defaultVisible ? 'checked' : ''}>
          <span>${def.label}</span>
        </label>
      `;
      row.querySelector('input').addEventListener('change', (e) => {
        ovManager.toggleOverlay(def.id, e.target.checked);
      });
      container.appendChild(row);
    });
  }

  // ── Public API ──

  return {
    setRoutes(data) {
      routeData = data;
      renderPlannedTracks();
    },
    wireOverlays,
    showPanel
  };
}
