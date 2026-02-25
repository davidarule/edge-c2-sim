/**
 * Entity lifecycle management for CesiumJS.
 *
 * Each simulation entity maps to a Cesium Billboard (symbol) + Label (callsign)
 * + Polyline (track trail). Uses milsymbol.js to generate MIL-STD-2525D icons.
 *
 * Features:
 * - Smooth position interpolation via SampledPositionProperty
 * - Trail polylines with fading alpha
 * - Pixel-distance declutter with ring offset (pixelOffset only, no extra entities)
 * - Symbol caching for performance
 */

import ms from 'milsymbol';

const MAX_TRAIL_POINTS = 15;
const TRAIL_UPDATE_INTERVAL = 3; // Update trail every Nth position update

// === DECLUTTER CONFIG ===
const OVERLAP_THRESHOLD_PX = 30;  // Entities closer than this (in pixels) get spread
const SPREAD_RADIUS_PX = 50;      // How far to push them apart (in pixels)
const DECLUTTER_INTERVAL_MS = 1000; // How often to recalculate
const MIN_SPEED_TO_SKIP = 1.0;     // Don't declutter moving entities (knots)
const SCALE_DOWN_THRESHOLD = 6;    // Scale down billboards for groups this size or larger

export function initEntityManager(viewer, config) {
  const entities = new Map();
  const trailPositions = new Map();
  const updateCounters = new Map();
  const symbolCache = new Map();
  const clickHandlers = [];
  const doubleClickHandlers = [];
  const filters = { agencies: new Set(), domains: new Set() };

  // Declutter state
  const declutterOffsets = new Map(); // entity_id -> { x, y } pixel offset
  const declutteredIds = new Set();   // entity IDs currently in a declutter group

  // === MILSYMBOL ===
  const shortTypeMap = {
    'MIL_NAVAL':           'NAV',
    'MIL_NAVAL_FIC':       'FIC',
    'MMEA_PATROL':         'PB',
    'MMEA_FAST_INTERCEPT': 'FIC',
    'RMAF_FIGHTER':        'FTR',
    'RMAF_HELICOPTER':     'RW',
    'RMAF_TRANSPORT':      'C',
    'RMAF_MPA':            'MPA',
    'RMP_HELICOPTER':      'RW',
    'RMP_PATROL_CAR':      'MP',
    'RMP_TACTICAL_TEAM':   'SOF',
    'MIL_INFANTRY_SQUAD':  'INF',
    'CI_OFFICER':          'CI',
    'CI_IMMIGRATION_TEAM': 'IMM',
    'CIVILIAN_FISHING':    'FV',
    'CIVILIAN_CARGO':      'CGO',
    'CIVILIAN_TANKER':     'TKR',
    'CIVILIAN_COMMERCIAL': 'CIV',
    'SUSPECT_VESSEL':      '?',
    'HOSTILE_VESSEL':      'HOS',
    'HOSTILE_PERSONNEL':   'HOS',
    'MIL_APC':             'APC',
  };

  function getShortType(entity) {
    if (entity.metadata?.type_code) return entity.metadata.type_code;
    return shortTypeMap[entity.entity_type] || '';
  }

  function getSymbolImage(entity) {
    const sidc = config.sidcMap[entity.entity_type] || config.defaultSidc;
    const shortType = getShortType(entity);
    const cacheKey = `${sidc}_${shortType}`;
    if (symbolCache.has(cacheKey)) return symbolCache.get(cacheKey);

    try {
      const symbol = new ms.Symbol(sidc, {
        size: 35,
        frame: true,
        fill: true,
        strokeWidth: 1.5,
        infoFields: true,
        type: shortType,
      });
      const url = symbol.toDataURL();
      symbolCache.set(cacheKey, url);
      return url;
    } catch (e) {
      console.warn('Symbol generation failed for SIDC:', sidc, e);
      const fallback = new ms.Symbol(config.defaultSidc, {
        size: 35, frame: true, fill: true, strokeWidth: 1.5, infoFields: false
      });
      const url = fallback.toDataURL();
      symbolCache.set(cacheKey, url);
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

    const sampledPosition = new Cesium.SampledPositionProperty();
    sampledPosition.setInterpolationOptions({
      interpolationDegree: 1,
      interpolationAlgorithm: Cesium.LinearApproximation
    });
    sampledPosition.forwardExtrapolationType = Cesium.ExtrapolationType.HOLD;
    sampledPosition.backwardExtrapolationType = Cesium.ExtrapolationType.HOLD;

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
        pixelOffset: new Cesium.Cartesian2(0, 0),
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

    const time = entityData.timestamp
      ? Cesium.JulianDate.fromIso8601(entityData.timestamp)
      : viewer.clock.currentTime;
    entry.sampledPosition.addSample(time, Cesium.Cartesian3.fromDegrees(lon, lat, alt));

    if (entityData.entity_type !== entry.data.entity_type ||
        entityData.status !== entry.data.status) {
      entry.cesiumEntity.billboard.image = getSymbolImage(entityData);
    }

    entry.cesiumEntity.label.text = entityData.callsign || id;

    const count = (updateCounters.get(id) || 0) + 1;
    updateCounters.set(id, count);
    if (count % TRAIL_UPDATE_INTERVAL === 0) {
      const trail = trailPositions.get(id) || [];
      const lastPoint = trail[trail.length - 1];
      const dist = lastPoint
        ? Math.sqrt(Math.pow(lat - lastPoint.lat, 2) + Math.pow(lon - lastPoint.lon, 2))
        : Infinity;
      if (dist > 0.0001) {  // ~11 meters — skip if entity hasn't moved
        trail.push({ lat, lon, alt });
        if (trail.length > MAX_TRAIL_POINTS) trail.shift();
      }
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
      declutterOffsets.delete(id);
      declutteredIds.delete(id);
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

  // === PIXEL-DISTANCE DECLUTTER WITH RING OFFSET ===

  function declutterEntities() {
    const scene = viewer.scene;
    const screenPositions = [];

    // Step 1: Project all entities to screen space
    entities.forEach((entry, id) => {
      if (!entry.visible) return;

      // Skip moving entities — they'll separate naturally
      const speed = entry.data.speed_knots || 0;
      if (speed > MIN_SPEED_TO_SKIP) {
        // Reset any existing offset
        if (declutterOffsets.has(id)) {
          entry.cesiumEntity.billboard.pixelOffset = new Cesium.Cartesian2(0, 0);
          entry.cesiumEntity.billboard.scale = 1.0;
          entry.cesiumEntity.label.pixelOffset = new Cesium.Cartesian2(0, 20);
          entry.cesiumEntity.label.show = true;
          entry.cesiumTrail.show = true;
          declutterOffsets.delete(id);
          declutteredIds.delete(id);
        }
        return;
      }

      const pos = entry.data.position;
      if (!pos) return;

      const cartesian = Cesium.Cartesian3.fromDegrees(
        pos.longitude, pos.latitude, pos.altitude_m || 0
      );
      const screenPos = Cesium.SceneTransforms.worldToWindowCoordinates(scene, cartesian);

      if (screenPos) {
        screenPositions.push({ id, screenPos, entry });
      }
    });

    // Step 2: Find overlapping groups
    const groups = findOverlapGroups(screenPositions, OVERLAP_THRESHOLD_PX);

    // Step 3: Reset offsets for ungrouped entities
    const groupedIds = new Set();
    groups.forEach(group => group.forEach(item => groupedIds.add(item.id)));

    declutterOffsets.forEach((_, id) => {
      if (!groupedIds.has(id)) {
        const entry = entities.get(id);
        if (entry && entry.cesiumEntity.billboard) {
          entry.cesiumEntity.billboard.pixelOffset = new Cesium.Cartesian2(0, 0);
          entry.cesiumEntity.billboard.scale = 1.0;
          entry.cesiumEntity.label.pixelOffset = new Cesium.Cartesian2(0, 20);
          entry.cesiumEntity.label.show = true;
          entry.cesiumTrail.show = true;
        }
        declutterOffsets.delete(id);
        declutteredIds.delete(id);
      }
    });

    // Step 4: Apply ring offsets to grouped entities
    groups.forEach(group => {
      if (group.length <= 1) return;

      const n = group.length;
      const scaleDown = n >= SCALE_DOWN_THRESHOLD ? 0.8 : 1.0;

      for (let i = 0; i < n; i++) {
        const angle = (2 * Math.PI * i) / n - Math.PI / 2; // Start from top
        const offsetX = Math.cos(angle) * SPREAD_RADIUS_PX;
        const offsetY = Math.sin(angle) * SPREAD_RADIUS_PX;

        const item = group[i];
        const entry = entities.get(item.id);
        if (entry && entry.cesiumEntity.billboard) {
          entry.cesiumEntity.billboard.pixelOffset = new Cesium.Cartesian2(offsetX, offsetY);
          entry.cesiumEntity.billboard.scale = scaleDown;
          // Hide labels and trails in declutter groups to reduce overlap
          entry.cesiumEntity.label.show = false;
          entry.cesiumTrail.show = false;
          declutterOffsets.set(item.id, { x: offsetX, y: offsetY });
          declutteredIds.add(item.id);
        }
      }
    });
  }

  function findOverlapGroups(items, threshold) {
    const visited = new Set();
    const groups = [];

    for (let i = 0; i < items.length; i++) {
      if (visited.has(i)) continue;

      const group = [items[i]];
      visited.add(i);

      for (let j = i + 1; j < items.length; j++) {
        if (visited.has(j)) continue;

        // Check distance to ANY member of the group
        const closeToGroup = group.some(member => {
          const dx = member.screenPos.x - items[j].screenPos.x;
          const dy = member.screenPos.y - items[j].screenPos.y;
          return Math.sqrt(dx * dx + dy * dy) < threshold;
        });

        if (closeToGroup) {
          group.push(items[j]);
          visited.add(j);
        }
      }

      if (group.length > 1) {
        groups.push(group);
      }
    }

    return groups;
  }

  // Run declutter periodically
  setInterval(declutterEntities, DECLUTTER_INTERVAL_MS);

  // Also run on camera move end
  viewer.camera.moveEnd.addEventListener(declutterEntities);

  // Initial declutter after entities load
  setTimeout(declutterEntities, 2000);

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
      setTimeout(declutterEntities, 500);
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
