/**
 * Map overlay manager — GeoJSON overlays (ESSZONE boundary, patrol sectors, etc.)
 *
 * No UI — the settings panel handles toggle checkboxes.
 */

export function initOverlayManager(viewer, config) {
  const overlays = new Map();

  // Overlay definitions
  const overlayDefs = [
    {
      id: 'esszone',
      label: 'ESSZONE Boundary',
      url: '/geodata/areas/esszone_sulu_sea.geojson',
      style: {
        stroke: Cesium.Color.YELLOW.withAlpha(0.8),
        strokeWidth: 4,
        fill: Cesium.Color.YELLOW.withAlpha(0.03)
      },
      defaultVisible: false
    }
  ];

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

  function getOverlayDefs() {
    return overlayDefs;
  }

  // Initialize — load overlays (no UI)
  overlayDefs.forEach(def => loadOverlay(def));

  return { toggleOverlay, getOverlayDefs };
}
