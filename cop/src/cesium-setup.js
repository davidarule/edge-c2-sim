/**
 * Initialize CesiumJS viewer with dark theme and ESSZONE camera.
 */

export async function initCesium(containerId, config) {
  Cesium.Ion.defaultAccessToken = config.cesiumToken;

  const viewer = new Cesium.Viewer(containerId, {
    animation: false,
    timeline: false,
    baseLayerPicker: false,
    geocoder: false,
    homeButton: false,
    sceneModePicker: false,
    navigationHelpButton: false,
    fullscreenButton: false,
    infoBox: false,
    selectionIndicator: false,
    skyBox: false,
    skyAtmosphere: true
  });

  // Dark globe
  viewer.scene.globe.baseColor = Cesium.Color.fromCssColorString('#0a0e17');
  viewer.scene.backgroundColor = Cesium.Color.fromCssColorString('#0a0e17');
  viewer.scene.globe.enableLighting = true;
  viewer.scene.globe.showGroundAtmosphere = true;

  // Anti-aliasing
  if (viewer.scene.postProcessStages.fxaa) {
    viewer.scene.postProcessStages.fxaa.enabled = true;
  }

  // Hide Cesium credits (we attribute in our footer)
  viewer.cesiumWidget.creditContainer.style.display = 'none';

  // Try to load terrain
  try {
    viewer.scene.terrainProvider = await Cesium.CesiumTerrainProvider.fromIonAssetId(1);
  } catch (e) {
    console.warn('Terrain loading failed, using ellipsoid:', e.message);
  }

  // Try dark imagery layer
  try {
    const darkLayer = await Cesium.ImageryLayer.fromProviderAsync(
      Cesium.IonImageryProvider.fromAssetId(3845)
    );
    viewer.imageryLayers.removeAll();
    viewer.imageryLayers.add(darkLayer);
  } catch (e) {
    console.warn('Dark imagery failed, using default:', e.message);
  }

  // Initial camera — ESSZONE overview
  viewer.camera.flyTo({
    destination: Cesium.Cartesian3.fromDegrees(
      config.initialCenter.lon,
      config.initialCenter.lat,
      config.initialAltitude
    ),
    orientation: {
      heading: Cesium.Math.toRadians(0),
      pitch: Cesium.Math.toRadians(-60),
      roll: 0
    },
    duration: 0
  });

  return viewer;
}
