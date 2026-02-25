/**
 * Map overlay manager — GeoJSON overlays (ESSZONE boundary, patrol sectors, etc.)
 */

export function initOverlayManager(viewer, config) {
  const overlays = new Map();
  let menuVisible = false;

  // Create overlay toggle menu (gear icon, top-right of viewport)
  const cesiumContainer = document.getElementById('cesium-container');
  const menu = document.createElement('div');
  menu.id = 'overlay-menu';
  menu.style.cssText = `
    position: absolute; top: 10px; right: 10px; z-index: 100;
    background: rgba(13, 17, 23, 0.9); border: 1px solid #30363D;
    border-radius: 4px; padding: 0; min-width: 180px;
    display: none;
  `;

  const toggleBtn = document.createElement('button');
  toggleBtn.innerHTML = '\u2699 Overlays';
  toggleBtn.style.cssText = `
    position: absolute; top: 10px; right: 10px; z-index: 101;
    background: rgba(13, 17, 23, 0.8); border: 1px solid #30363D;
    border-radius: 4px; padding: 4px 10px; cursor: pointer;
    color: #8B949E; font-family: 'IBM Plex Sans', sans-serif; font-size: 12px;
  `;
  toggleBtn.addEventListener('click', () => {
    menuVisible = !menuVisible;
    menu.style.display = menuVisible ? 'block' : 'none';
    toggleBtn.style.display = menuVisible ? 'none' : 'block';
  });

  cesiumContainer.appendChild(toggleBtn);
  cesiumContainer.appendChild(menu);

  // Overlay definitions
  const overlayDefs = [
    {
      id: 'esszone',
      label: 'ESSZONE Boundary',
      url: '/geodata/areas/esszone_sulu_sea.geojson',
      style: {
        stroke: Cesium.Color.YELLOW.withAlpha(0.8),
        strokeWidth: 2,
        fill: Cesium.Color.YELLOW.withAlpha(0.03)
      },
      defaultVisible: false
    }
  ];

  function buildMenu() {
    menu.innerHTML = `
      <div style="padding: 8px 12px; border-bottom: 1px solid #30363D; display: flex; justify-content: space-between; align-items: center;">
        <span style="font-size: 11px; text-transform: uppercase; letter-spacing: 1px; color: #8B949E;">Overlays</span>
        <button id="overlay-close" style="background: none; border: none; color: #8B949E; cursor: pointer; font-size: 14px;">\u2715</button>
      </div>
    `;

    overlayDefs.forEach(def => {
      const row = document.createElement('div');
      row.style.cssText = 'padding: 6px 12px; display: flex; align-items: center; gap: 8px; cursor: pointer;';
      row.innerHTML = `
        <input type="checkbox" id="overlay-${def.id}" ${def.defaultVisible ? 'checked' : ''} style="cursor: pointer;">
        <label for="overlay-${def.id}" style="font-size: 12px; color: #C9D1D9; cursor: pointer;">${def.label}</label>
      `;
      row.querySelector('input').addEventListener('change', (e) => {
        toggleOverlay(def.id, e.target.checked);
      });
      menu.appendChild(row);
    });

    document.getElementById('overlay-close').addEventListener('click', () => {
      menuVisible = false;
      menu.style.display = 'none';
      toggleBtn.style.display = 'block';
    });
  }

  async function loadOverlay(def) {
    try {
      const dataSource = await Cesium.GeoJsonDataSource.load(def.url, {
        stroke: def.style.stroke || Cesium.Color.YELLOW,
        strokeWidth: def.style.strokeWidth || 2,
        fill: def.style.fill || Cesium.Color.TRANSPARENT,
        markerSize: 0
      });
      dataSource.show = def.defaultVisible;
      viewer.dataSources.add(dataSource);
      overlays.set(def.id, dataSource);
    } catch (e) {
      console.warn(`Failed to load overlay ${def.id}:`, e.message);
    }
  }

  function toggleOverlay(id, visible) {
    const ds = overlays.get(id);
    if (ds) ds.show = visible;
  }

  // Initialize
  buildMenu();
  overlayDefs.forEach(def => loadOverlay(def));

  return { toggleOverlay };
}
