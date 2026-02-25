/**
 * Entity lifecycle management for CesiumJS.
 *
 * Each simulation entity maps to a Cesium Billboard (symbol) + Label (callsign)
 * + Polyline (track trail). Uses milsymbol.js to generate MIL-STD-2525D icons.
 */

import ms from 'milsymbol';

const MAX_TRAIL_POINTS = 15;

export function initEntityManager(viewer, config) {
  const entities = new Map();
  const trailPositions = new Map();
  const symbolCache = new Map();
  const clickHandlers = [];
  const doubleClickHandlers = [];
  const filters = { agencies: new Set(), domains: new Set() };

  // === MILSYMBOL ===
  function getSymbolImage(entity) {
    const sidc = entity.sidc || config.sidcMap[entity.entity_type] || config.defaultSidc;
    if (symbolCache.has(sidc)) return symbolCache.get(sidc);

    try {
      const symbol = new ms.Symbol(sidc, {
        size: 28,
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
      // Fallback: generate generic friendly symbol
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

    const cesiumEntity = viewer.entities.add({
      id: `entity-${id}`,
      position: Cesium.Cartesian3.fromDegrees(lon, lat, alt),
      billboard: {
        image: getSymbolImage(entityData),
        verticalOrigin: Cesium.VerticalOrigin.CENTER,
        horizontalOrigin: Cesium.HorizontalOrigin.CENTER,
        scale: 1.0,
        rotation: Cesium.Math.toRadians(-(entityData.heading_deg || 0)),
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

    // Track trail
    trailPositions.set(id, [{ lat, lon, alt }]);

    const cesiumTrail = viewer.entities.add({
      id: `trail-${id}`,
      polyline: {
        positions: new Cesium.CallbackProperty(() => {
          const points = trailPositions.get(id) || [];
          return points.map(p => Cesium.Cartesian3.fromDegrees(p.lon, p.lat, p.alt || 0));
        }, false),
        width: 2,
        material: Cesium.Color.fromCssColorString(getAgencyColor(entityData.agency)).withAlpha(0.5)
      }
    });

    entities.set(id, {
      cesiumEntity,
      cesiumTrail,
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

    entry.cesiumEntity.position = Cesium.Cartesian3.fromDegrees(lon, lat, alt);
    entry.cesiumEntity.billboard.rotation = Cesium.Math.toRadians(-(entityData.heading_deg || 0));

    // Regenerate symbol only if type/status changed
    if (entityData.entity_type !== entry.data.entity_type ||
        entityData.status !== entry.data.status) {
      entry.cesiumEntity.billboard.image = getSymbolImage(entityData);
    }

    entry.cesiumEntity.label.text = entityData.callsign || id;

    // Update trail
    const trail = trailPositions.get(id) || [];
    trail.push({ lat, lon, alt });
    if (trail.length > MAX_TRAIL_POINTS) trail.shift();
    trailPositions.set(id, trail);

    entry.data = entityData;
  }

  function removeEntity(id) {
    const entry = entities.get(id);
    if (entry) {
      viewer.entities.remove(entry.cesiumEntity);
      viewer.entities.remove(entry.cesiumTrail);
      entities.delete(id);
      trailPositions.delete(id);
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

    entry.cesiumEntity.show = !hidden;
    entry.cesiumTrail.show = !hidden;
    entry.visible = !hidden;
  }

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
