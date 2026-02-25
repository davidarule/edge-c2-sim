/**
 * Map Interaction Handler — manages click modes for the Scenario Builder.
 *
 * Modes: SELECT, PLACE, WAYPOINT, AREA, MEASURE
 * Only one mode active at a time. SELECT is default.
 */

// ── Mode constants ──

export const MODES = {
  SELECT:   'SELECT',
  PLACE:    'PLACE',
  WAYPOINT: 'WAYPOINT',
  AREA:     'AREA',
  MEASURE:  'MEASURE',
};

const MODE_CURSORS = {
  SELECT:   'default',
  PLACE:    'crosshair',
  WAYPOINT: 'crosshair',
  AREA:     'crosshair',
  MEASURE:  'crosshair',
};

const MODE_LABELS = {
  SELECT:   'Select',
  PLACE:    'Place',
  WAYPOINT: 'Route',
  AREA:     'Area',
  MEASURE:  'Measure',
};

const MODE_ICONS = {
  SELECT:   '\u2B95',   // ⮕ arrow
  PLACE:    '\u2295',   // ⊕ circled plus
  WAYPOINT: '\u2B9E',   // ⮞ route
  AREA:     '\u2B1F',   // ⬟ pentagon
  MEASURE:  '\uD83D\uDCCF', // 📏 ruler
};

// ── Styles ──

const TOOLBAR_STYLES = `
  .builder-toolbar {
    position: absolute;
    top: 8px; left: 270px;
    z-index: 50;
    display: none;
    gap: 2px;
    background: rgba(13,17,23,0.9);
    border: 1px solid #30363D;
    border-radius: 4px;
    padding: 3px;
    font-family: 'IBM Plex Sans', sans-serif;
  }
  .build-mode .builder-toolbar { display: flex; }

  .toolbar-btn {
    padding: 5px 10px;
    border: none;
    background: transparent;
    color: #8B949E;
    font-size: 11px;
    font-family: 'IBM Plex Sans', sans-serif;
    cursor: pointer;
    border-radius: 3px;
    white-space: nowrap;
    transition: all 0.1s;
  }
  .toolbar-btn:hover {
    background: #21262D;
    color: #C9D1D9;
  }
  .toolbar-btn.active {
    background: rgba(88,166,255,0.15);
    color: #58A6FF;
  }

  .toolbar-divider {
    width: 1px;
    background: #30363D;
    margin: 2px 4px;
  }

  /* Mode toast */
  .mode-toast {
    position: absolute;
    bottom: 50px; left: 50%;
    transform: translateX(-50%);
    z-index: 50;
    display: none;
    padding: 6px 16px;
    background: rgba(13,17,23,0.9);
    border: 1px solid #30363D;
    border-radius: 4px;
    font-family: 'IBM Plex Sans', sans-serif;
    font-size: 12px;
    color: #8B949E;
    pointer-events: none;
  }
  .mode-toast.visible { display: block; }
`;

let stylesInjected = false;
function injectStyles() {
  if (stylesInjected) return;
  const style = document.createElement('style');
  style.textContent = TOOLBAR_STYLES;
  document.head.appendChild(style);
  stylesInjected = true;
}

/**
 * Initialize the map interaction handler.
 *
 * @param {Cesium.Viewer} viewer
 * @returns {object} API
 */
export function initMapInteraction(viewer) {
  injectStyles();

  let currentMode = MODES.SELECT;
  let modeListeners = [];
  let clickListeners = [];
  let rightClickListeners = [];
  let moveListeners = [];

  // ── Build toolbar ──

  const cesiumContainer = document.getElementById('cesium-container');

  const toolbar = document.createElement('div');
  toolbar.className = 'builder-toolbar';

  for (const mode of Object.values(MODES)) {
    const btn = document.createElement('button');
    btn.className = `toolbar-btn${mode === MODES.SELECT ? ' active' : ''}`;
    btn.dataset.mode = mode;
    btn.textContent = `${MODE_ICONS[mode]} ${MODE_LABELS[mode]}`;
    btn.title = `${MODE_LABELS[mode]} mode`;
    btn.addEventListener('click', () => setMode(mode));
    toolbar.appendChild(btn);
  }

  cesiumContainer.appendChild(toolbar);

  // Mode toast
  const toast = document.createElement('div');
  toast.className = 'mode-toast';
  cesiumContainer.appendChild(toast);

  // ── Cesium event handlers ──

  const handler = new Cesium.ScreenSpaceEventHandler(viewer.scene.canvas);

  // Left click
  handler.setInputAction((movement) => {
    const cartesian = viewer.camera.pickEllipsoid(
      movement.position, viewer.scene.globe.ellipsoid
    );
    const picked = viewer.scene.pick(movement.position);

    let position = null;
    if (cartesian) {
      const carto = Cesium.Cartographic.fromCartesian(cartesian);
      position = {
        latitude: Cesium.Math.toDegrees(carto.latitude),
        longitude: Cesium.Math.toDegrees(carto.longitude),
      };
    }

    const event = {
      mode: currentMode,
      position,
      picked,
      screenPosition: movement.position,
    };

    clickListeners.forEach(fn => fn(event));
  }, Cesium.ScreenSpaceEventType.LEFT_CLICK);

  // Right click
  handler.setInputAction((movement) => {
    const cartesian = viewer.camera.pickEllipsoid(
      movement.position, viewer.scene.globe.ellipsoid
    );
    const picked = viewer.scene.pick(movement.position);

    let position = null;
    if (cartesian) {
      const carto = Cesium.Cartographic.fromCartesian(cartesian);
      position = {
        latitude: Cesium.Math.toDegrees(carto.latitude),
        longitude: Cesium.Math.toDegrees(carto.longitude),
      };
    }

    rightClickListeners.forEach(fn => fn({
      mode: currentMode,
      position,
      picked,
      screenPosition: movement.position,
    }));
  }, Cesium.ScreenSpaceEventType.RIGHT_CLICK);

  // Mouse move
  handler.setInputAction((movement) => {
    const cartesian = viewer.camera.pickEllipsoid(
      movement.endPosition, viewer.scene.globe.ellipsoid
    );
    let position = null;
    if (cartesian) {
      const carto = Cesium.Cartographic.fromCartesian(cartesian);
      position = {
        latitude: Cesium.Math.toDegrees(carto.latitude),
        longitude: Cesium.Math.toDegrees(carto.longitude),
      };
    }

    moveListeners.forEach(fn => fn({
      mode: currentMode,
      position,
      screenPosition: movement.endPosition,
    }));
  }, Cesium.ScreenSpaceEventType.MOUSE_MOVE);

  // ── Mode management ──

  function setMode(mode) {
    if (!MODES[mode]) return;
    currentMode = mode;

    // Update toolbar buttons
    toolbar.querySelectorAll('.toolbar-btn').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.mode === mode);
    });

    // Update cursor
    viewer.scene.canvas.style.cursor = MODE_CURSORS[mode] || 'default';

    // Show toast for non-SELECT modes
    if (mode !== MODES.SELECT) {
      toast.textContent = `${MODE_LABELS[mode]} mode — click on map. ESC to cancel.`;
      toast.classList.add('visible');
    } else {
      toast.classList.remove('visible');
    }

    // Notify listeners
    modeListeners.forEach(fn => fn(mode));
  }

  // ESC to return to SELECT
  function onKeydown(e) {
    if (e.key === 'Escape' && currentMode !== MODES.SELECT) {
      setMode(MODES.SELECT);
    }
  }
  document.addEventListener('keydown', onKeydown);

  return {
    getMode() { return currentMode; },
    setMode,
    MODES,

    onModeChange(fn) {
      modeListeners.push(fn);
      return () => { modeListeners = modeListeners.filter(l => l !== fn); };
    },
    onClick(fn) {
      clickListeners.push(fn);
      return () => { clickListeners = clickListeners.filter(l => l !== fn); };
    },
    onRightClick(fn) {
      rightClickListeners.push(fn);
      return () => { rightClickListeners = rightClickListeners.filter(l => l !== fn); };
    },
    onMouseMove(fn) {
      moveListeners.push(fn);
      return () => { moveListeners = moveListeners.filter(l => l !== fn); };
    },

    showToast(message, duration = 3000) {
      toast.textContent = message;
      toast.classList.add('visible');
      if (duration > 0) {
        setTimeout(() => toast.classList.remove('visible'), duration);
      }
    },
    hideToast() {
      toast.classList.remove('visible');
    },

    destroy() {
      handler.destroy();
      document.removeEventListener('keydown', onKeydown);
      toolbar.remove();
      toast.remove();
    }
  };
}
