/**
 * Entity lifecycle management for CesiumJS.
 *
 * Each simulation entity maps to a Cesium Billboard (symbol) + Label (callsign)
 * + Polyline (track trail). Uses milsymbol.js to generate MIL-STD-2525D icons.
 *
 * Features:
 * - Smooth position interpolation via SampledPositionProperty
 * - Trail polylines with fading alpha
 * - Entity clustering at high altitude
 * - Symbol caching for performance
 */

import ms from 'milsymbol';

const MAX_TRAIL_POINTS = 15;
const TRAIL_UPDATE_INTERVAL = 3; // Update trail every Nth position update
const CLUSTER_ALTITUDE = 0; // Cluster above 500km

export function initEntityManager(viewer, config) {
  const entities = new Map();
  const trailPositions = new Map();
  const updateCounters = new Map(); // Track update count per entity for trail throttling
  const symbolCache = new Map();
  const clickHandlers = [];
  const doubleClickHandlers = [];
  const filters = { agencies: new Set(), domains: new Set() };
  let clusterMode = false;
  const clusterEntities = [];

  // === MILSYMBOL ===
  function getSymbolImage(entity) {
    const sidc = entity.sidc || config.sidcMap[entity.entity_type] || config.defaultSidc;
    if (symbolCache.has(sidc)) return symbolCache.get(sidc);

    try {
      const symbol = new ms.Symbol(sidc, {
        size: 40,
        frame: true,
        fill: true,
        strokeWidth: 1.5,
        infoFields: false
      });
      const url = symbol.toDataURL();
      symbolCache.set(sidc, url);
      return url;
    } catch (e) {
      console.warn('Symbol generation failed for SIDC:', sidc, e);
      const fallback = new ms.Symbol(config.defaultSidc, {
        size: 28, frame: true, fill: true, strokeWidth: 1.5, infoFields: false
      });
      const url = fallback.toDataURL();
      symbolCache.set(sidc, url);
      return url;
    }
  }

  function getAgencyColor(agency) {
    return config.agencyColors[agency] || config.agencyColors.UNKNOWN;
  }

  // === ENTITY CRUD ===
  function addOrUpdateEntity(entityData) {
    const id = entityData.entity_id;
    if (entities.has(id)) {
      updateExisting(id, entityData);
    } else {
      createNew(entityData);
    }
  }

  function createNew(entityData) {
    const id = entityData.entity_id;
    const pos = entityData.position || {};
    const lat = pos.latitude || 0;
    const lon = pos.longitude || 0;
    const alt = pos.altitude_m || 0;

    // Use SampledPositionProperty for smooth interpolation
    const sampledPosition = new Cesium.SampledPositionProperty();
    sampledPosition.setInterpolationOptions({
      interpolationDegree: 1,
      interpolationAlgorithm: Cesium.LinearApproximation
    });

    // Add initial sample
    const now = entityData.timestamp
      ? Cesium.JulianDate.fromIso8601(entityData.timestamp)
      : viewer.clock.currentTime;
    sampledPosition.addSample(now, Cesium.Cartesian3.fromDegrees(lon, lat, alt));

    const cesiumEntity = viewer.entities.add({
      id: `entity-${id}`,
      position: sampledPosition,
      billboard: {
        image: getSymbolImage(entityData),
        verticalOrigin: Cesium.VerticalOrigin.CENTER,
        horizontalOrigin: Cesium.HorizontalOrigin.CENTER,
        scale: 1.0,
        rotation: 0,
        disableDepthTestDistance: Number.POSITIVE_INFINITY
      },
      label: {
        text: entityData.callsign || id,
        font: '12px IBM Plex Mono',
        fillColor: Cesium.Color.WHITE,
        outlineColor: Cesium.Color.BLACK,
        outlineWidth: 2,
        style: Cesium.LabelStyle.FILL_AND_OUTLINE,
        verticalOrigin: Cesium.VerticalOrigin.TOP,
        pixelOffset: new Cesium.Cartesian2(0, 20),
        distanceDisplayCondition: new Cesium.DistanceDisplayCondition(0, 200000),
        disableDepthTestDistance: Number.POSITIVE_INFINITY
      }
    });

    // Track trail with fading alpha
    trailPositions.set(id, [{ lat, lon, alt }]);
    updateCounters.set(id, 0);

    const agencyColor = Cesium.Color.fromCssColorString(getAgencyColor(entityData.agency));

    const cesiumTrail = viewer.entities.add({
      id: `trail-${id}`,
      polyline: {
        positions: new Cesium.CallbackProperty(() => {
          const points = trailPositions.get(id) || [];
          return points.map(p => Cesium.Cartesian3.fromDegrees(p.lon, p.lat, p.alt || 0));
        }, false),
        width: 2,
        material: new Cesium.PolylineGlowMaterialProperty({
          glowPower: 0.15,
          color: agencyColor.withAlpha(0.5)
        })
      }
    });

    entities.set(id, {
      cesiumEntity,
      cesiumTrail,
      sampledPosition,
      data: entityData,
      visible: true
    });

    applyVisibility(id);
  }

  function updateExisting(id, entityData) {
    const entry = entities.get(id);
    if (!entry) return;

    const pos = entityData.position || {};
    const lat = pos.latitude || 0;
    const lon = pos.longitude || 0;
    const alt = pos.altitude_m || 0;

    // Add position sample for smooth interpolation
    const time = entityData.timestamp
      ? Cesium.JulianDate.fromIso8601(entityData.timestamp)
      : viewer.clock.currentTime;
    entry.sampledPosition.addSample(time, Cesium.Cartesian3.fromDegrees(lon, lat, alt));

    // Update heading rotation
    // rotation removed 

    // Regenerate symbol only if type/status changed
    if (entityData.entity_type !== entry.data.entity_type ||
        entityData.status !== entry.data.status) {
      entry.cesiumEntity.billboard.image = getSymbolImage(entityData);
    }

    entry.cesiumEntity.label.text = entityData.callsign || id;

    // Throttled trail update (every Nth update)
    const count = (updateCounters.get(id) || 0) + 1;
    updateCounters.set(id, count);
    if (count % TRAIL_UPDATE_INTERVAL === 0) {
      const trail = trailPositions.get(id) || [];
      trail.push({ lat, lon, alt });
      if (trail.length > MAX_TRAIL_POINTS) trail.shift();
      trailPositions.set(id, trail);
    }

    entry.data = entityData;
  }

  function removeEntity(id) {
    const entry = entities.get(id);
    if (entry) {
      viewer.entities.remove(entry.cesiumEntity);
      viewer.entities.remove(entry.cesiumTrail);
      entities.delete(id);
      trailPositions.delete(id);
      updateCounters.delete(id);
    }
  }

  // === FILTERING ===
  function setAgencyFilter(agency, visible) {
    if (visible) filters.agencies.delete(agency);
    else filters.agencies.add(agency);
    entities.forEach((_, id) => applyVisibility(id));
  }

  function setDomainFilter(domain, visible) {
    if (visible) filters.domains.delete(domain);
    else filters.domains.add(domain);
    entities.forEach((_, id) => applyVisibility(id));
  }

  function applyVisibility(id) {
    const entry = entities.get(id);
    if (!entry) return;

    const hidden = filters.agencies.has(entry.data.agency) ||
                   filters.domains.has(entry.data.domain);

    entry.cesiumEntity.show = !hidden && !clusterMode;
    entry.cesiumTrail.show = !hidden && !clusterMode;
    entry.visible = !hidden;
  }

  // === CLUSTERING ===
  function updateClustering() {
    const cameraHeight = viewer.camera.positionCartographic.height;
    const shouldCluster = cameraHeight > CLUSTER_ALTITUDE;

    if (shouldCluster === clusterMode) return;
    clusterMode = shouldCluster;

    if (clusterMode) {
      // Hide individual entities, show clusters
      entities.forEach((entry) => {
        entry.cesiumEntity.show = false;
        entry.cesiumTrail.show = false;
      });
      buildClusters();
    } else {
      // Show individual entities, remove clusters
      clearClusters();
      entities.forEach((_, id) => applyVisibility(id));
    }
  }

  function buildClusters() {
    clearClusters();
    const gridSize = 0.5; // degrees
    const grid = new Map();

    entities.forEach((entry) => {
      if (!entry.visible) return;
      const pos = entry.data.position || {};
      const gridKey = `${Math.floor((pos.latitude || 0) / gridSize)}_${Math.floor((pos.longitude || 0) / gridSize)}`;
      if (!grid.has(gridKey)) {
        grid.set(gridKey, { lat: 0, lon: 0, count: 0, agencies: {} });
      }
      const cell = grid.get(gridKey);
      cell.lat += (pos.latitude || 0);
      cell.lon += (pos.longitude || 0);
      cell.count++;
      const agency = entry.data.agency || 'UNKNOWN';
      cell.agencies[agency] = (cell.agencies[agency] || 0) + 1;
    });

    grid.forEach((cell, key) => {
      if (cell.count === 0) return;
      const lat = cell.lat / cell.count;
      const lon = cell.lon / cell.count;

      // Dominant agency color
      const dominant = Object.entries(cell.agencies).sort((a, b) => b[1] - a[1])[0];
      const color = getAgencyColor(dominant ? dominant[0] : 'UNKNOWN');

      const clusterEntity = viewer.entities.add({
        id: `cluster-${key}`,
        position: Cesium.Cartesian3.fromDegrees(lon, lat, 0),
        point: {
          pixelSize: Math.min(12 + cell.count * 2, 40),
          color: Cesium.Color.fromCssColorString(color).withAlpha(0.8),
          outlineColor: Cesium.Color.WHITE,
          outlineWidth: 1,
          disableDepthTestDistance: Number.POSITIVE_INFINITY
        },
        label: {
          text: String(cell.count),
          font: '11px IBM Plex Mono',
          fillColor: Cesium.Color.WHITE,
          outlineColor: Cesium.Color.BLACK,
          outlineWidth: 2,
          style: Cesium.LabelStyle.FILL_AND_OUTLINE,
          verticalOrigin: Cesium.VerticalOrigin.CENTER,
          horizontalOrigin: Cesium.HorizontalOrigin.CENTER,
          disableDepthTestDistance: Number.POSITIVE_INFINITY
        }
      });
      clusterEntities.push(clusterEntity);
    });
  }

  function clearClusters() {
    clusterEntities.forEach(e => viewer.entities.remove(e));
    clusterEntities.length = 0;
  }

  // Check clustering every 2 seconds
  // setInterval(updateClustering, 2000);

  // === CLICK EVENTS ===
  function fireClick(entityData) {
    clickHandlers.forEach(fn => fn(entityData));
  }

  function fireDoubleClick(entityData) {
    doubleClickHandlers.forEach(fn => fn(entityData));
  }

  // === API ===
  return {
    loadSnapshot(entityList) {
      entities.forEach((_, id) => removeEntity(id));
      entityList.forEach(e => addOrUpdateEntity(e));
    },
    updateEntity: addOrUpdateEntity,
    removeEntity,
    setAgencyFilter,
    setDomainFilter,
    getEntity: (id) => entities.get(id)?.data,
    getCesiumEntity: (id) => entities.get(id)?.cesiumEntity,
    getAllEntities: () => [...entities.values()].map(e => e.data),
    getEntityCount: () => entities.size,
    getCountByAgency() {
      const counts = {};
      entities.forEach(e => {
        if (!e.visible) return;
        const a = e.data.agency || 'UNKNOWN';
        counts[a] = (counts[a] || 0) + 1;
      });
      return counts;
    },
    getCountByDomain() {
      const counts = {};
      entities.forEach(e => {
        if (!e.visible) return;
        const d = e.data.domain || 'UNKNOWN';
        counts[d] = (counts[d] || 0) + 1;
      });
      return counts;
    },
    onEntityClick: (fn) => clickHandlers.push(fn),
    onEntityDoubleClick: (fn) => doubleClickHandlers.push(fn),
    _fireClick: fireClick,
    _fireDoubleClick: fireDoubleClick,
    getSymbolImage
  };
}
