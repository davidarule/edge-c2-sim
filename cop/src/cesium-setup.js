/**
 * Initialize CesiumJS viewer with dark theme and ESSZONE camera.
 * Supports offline mode (air-gapped) using bundled NaturalEarthII imagery.
 */
import * as Cesium from 'cesium';

export async function initCesium(containerId, config) {
  const offlineMode = !config.cesiumToken || config.cesiumToken === '' ||
                      import.meta.env.VITE_OFFLINE_MODE === 'true';

  if (!offlineMode) {
    Cesium.Ion.defaultAccessToken = config.cesiumToken;
  }

  const viewerOptions = {
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
  };

  if (offlineMode) {
    viewerOptions.baseLayer = Cesium.ImageryLayer.fromProviderAsync(
      Cesium.TileMapServiceImageryProvider.fromUrl(
        Cesium.buildModuleUrl('Assets/Textures/NaturalEarthII')
      )
    );
    viewerOptions.terrain = undefined;
    console.log('[CesiumSetup] Offline mode — using bundled NaturalEarthII imagery');
  }

  const viewer = new Cesium.Viewer(containerId, viewerOptions);

  if (offlineMode) {
    viewer.scene.terrainProvider = new Cesium.EllipsoidTerrainProvider();
  }

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

  // Recover from Cesium render errors instead of stopping permanently
  viewer.scene.renderError.addEventListener((scene, error) => {
    console.warn('Cesium render error (recovering):', error);
    viewer.useDefaultRenderLoop = true;
  });

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
