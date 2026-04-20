/**
 * Map overlay manager — GeoJSON overlays (ESSZONE boundary, patrol sectors, etc.)
 *
 * No UI — the settings panel handles toggle checkboxes.
 */

import * as Cesium from 'cesium';

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
    },
    {
      id: 'my_eez',
      label: 'Malaysian Waters (EEZ — Strait)',
      url: '/geodata/boundaries/malaysia_eez_peninsula.geojson',
      style: {
        // Jalur Gemilang red
        stroke: Cesium.Color.fromCssColorString('#CC0001').withAlpha(0.85),
        strokeWidth: 2,
        fill: Cesium.Color.fromCssColorString('#CC0001').withAlpha(0.08)
      },
      defaultVisible: false
    },
    {
      id: 'my_eez_sulu',
      label: 'Malaysian Waters (EEZ — Sulu Sea)',
      url: '/geodata/boundaries/malaysia_eez_sulu.geojson',
      style: {
        stroke: Cesium.Color.fromCssColorString('#CC0001').withAlpha(0.85),
        strokeWidth: 2,
        fill: Cesium.Color.fromCssColorString('#CC0001').withAlpha(0.08)
      },
      defaultVisible: false
    },
    {
      id: 'id_eez',
      label: 'Indonesian Waters (EEZ — Sumatra)',
      url: '/geodata/boundaries/indonesia_eez_sumatra.geojson',
      style: {
        // Merah Putih red
        stroke: Cesium.Color.fromCssColorString('#E70011').withAlpha(0.85),
        strokeWidth: 2,
        fill: Cesium.Color.fromCssColorString('#FFFFFF').withAlpha(0.06)
      },
      defaultVisible: false
    },
    {
      id: 'my_id_median',
      label: 'MY–ID Maritime Boundary (1970)',
      url: '/geodata/boundaries/my_id_median_line.geojson',
      style: {
        stroke: Cesium.Color.fromCssColorString('#FFFFFF').withAlpha(0.95),
        strokeWidth: 3,
        fill: Cesium.Color.TRANSPARENT
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
        markerSize: 1,
        markerColor: Cesium.Color.TRANSPARENT
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
