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
    skyAtmosphere: false
  });

  // Dark globe background
  viewer.scene.globe.baseColor = Cesium.Color.fromCssColorString('#0a0e17');
  viewer.scene.backgroundColor = Cesium.Color.fromCssColorString('#0a0e17');
  viewer.scene.globe.showGroundAtmosphere = false;

  // Anti-aliasing
  if (viewer.scene.postProcessStages.fxaa) {
    viewer.scene.postProcessStages.fxaa.enabled = true;
  }

  // Hide Cesium credits
  viewer.cesiumWidget.creditContainer.style.display = 'none';

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
