/**
 * Entity lifecycle management for CesiumJS.
 *
 * Each simulation entity maps to a Cesium Billboard (symbol) + Label (callsign)
 * + Polyline (track trail). Uses JMSML DISA SVGs for MIL-STD-2525D symbols.
 *
 * Features:
 * - Smooth position interpolation via SampledPositionProperty
 * - Trail polylines with fading alpha
 * - Pixel-distance declutter with ring offset (pixelOffset only, no extra entities)
 * - Symbol caching for performance
 */

import { renderSymbol, clearSymbolCache } from './symbol-renderer.js';

const TRAIL_UPDATE_INTERVAL = 2; // Update trail every Nth position update
const SYMBOL_RENDER_SIZE = 128;  // Render SVGs at high res to avoid blur when scaled
const TRAIL_WIDTH = 6;           // Trail polyline width in pixels

// Trail duration options in hours (slider stops)
const TRAIL_DURATIONS = [1, 4, 12, 24];
const DEFAULT_TRAIL_DURATION_H = 4;

// === DECLUTTER CONFIG ===
const OVERLAP_THRESHOLD_PX = 30;      // Entities closer than this (in pixels) get spread
const SPREAD_RADIUS_PX_MAX = 50;      // Maximum spread at low altitude
const DECLUTTER_INTERVAL_MS = 1000;   // How often to recalculate
const MIN_SPEED_TO_SKIP = 1.0;        // Don't declutter moving entities (knots)
const SCALE_DOWN_THRESHOLD = 6;       // Scale down billboards for groups this size or larger
const DECLUTTER_FULL_ALT = 5000;      // Below 5km: full spread radius
const DECLUTTER_ZERO_ALT = 80000;     // Above 80km: no declutter (0px spread)

export function initEntityManager(viewer, config) {
  // Use a CustomDataSource so Cesium EntityCluster works
  const dataSource = new Cesium.CustomDataSource('entities');
  viewer.dataSources.add(dataSource);

  const entities = new Map();
  const trailPositions = new Map();
  const updateCounters = new Map();
  const symbolCache = new Map();
  const clickHandlers = [];
  const doubleClickHandlers = [];
  const filters = { agencies: new Set(), domains: new Set() };

  // Global display state (settable via settings panel)
  let globalIconSizePx = 40;   // desired display size in pixels
  let globalIconScale = globalIconSizePx / SYMBOL_RENDER_SIZE;
  let globalLabelsVisible = true;
  let globalTrailsVisible = true;
  let globalTrailDurationH = DEFAULT_TRAIL_DURATION_H;
  let clusteringEnabled = false;

  // Per-entity SIDC overrides (entity_id -> sidc)
  const entitySidcOverrides = new Map();

  // Per-entity trail visibility overrides (entity_id -> boolean)
  const entityTrailOverrides = new Map();

  // Declutter state
  const declutterOffsets = new Map(); // entity_id -> { x, y } pixel offset
  const declutteredIds = new Set();   // entity IDs currently in a declutter group

  // === JMSML SYMBOL RENDERING ===
  function getSidcForEntity(entity) {
    // Per-entity override takes precedence
    if (entitySidcOverrides.has(entity.entity_id)) {
      return entitySidcOverrides.get(entity.entity_id);
    }
    return config.sidcMap[entity.entity_type] || config.defaultSidc;
  }

  function getSymbolImage(entity) {
    const sidc = getSidcForEntity(entity);
    if (symbolCache.has(sidc)) return symbolCache.get(sidc);

    const url = renderSymbol(sidc, { size: SYMBOL_RENDER_SIZE });
    symbolCache.set(sidc, url);
    return url;
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

    const cesiumEntity = dataSource.entities.add({
      id: `entity-${id}`,
      position: sampledPosition,
      billboard: {
        image: getSymbolImage(entityData),
        verticalOrigin: Cesium.VerticalOrigin.CENTER,
        horizontalOrigin: Cesium.HorizontalOrigin.CENTER,
        scale: globalIconScale,
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
        show: globalLabelsVisible,
        verticalOrigin: Cesium.VerticalOrigin.TOP,
        pixelOffset: new Cesium.Cartesian2(0, 20),
        distanceDisplayCondition: new Cesium.DistanceDisplayCondition(0, 200000),
        disableDepthTestDistance: Number.POSITIVE_INFINITY
      }
    });

    const ts = entityData.timestamp ? new Date(entityData.timestamp).getTime() : Date.now();
    trailPositions.set(id, [{ lat, lon, alt, ts }]);
    updateCounters.set(id, 0);

    const agencyColor = Cesium.Color.fromCssColorString(getAgencyColor(entityData.agency));

    const cesiumTrail = dataSource.entities.add({
      id: `trail-${id}`,
      polyline: {
        positions: new Cesium.CallbackProperty(() => {
          const points = trailPositions.get(id) || [];
          return points.map(p => Cesium.Cartesian3.fromDegrees(p.lon, p.lat, p.alt || 0));
        }, false),
        width: TRAIL_WIDTH,
        show: globalTrailsVisible,
        material: new Cesium.PolylineGlowMaterialProperty({
          glowPower: 0.15,
          color: agencyColor.withAlpha(0.85)
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
        const ts = entityData.timestamp ? new Date(entityData.timestamp).getTime() : Date.now();
        trail.push({ lat, lon, alt, ts });
        // Prune points older than trail duration
        const cutoff = ts - globalTrailDurationH * 3600 * 1000;
        while (trail.length > 2 && trail[0].ts < cutoff) {
          trail.shift();
        }
      }
    }

    entry.data = entityData;
  }

  function removeEntity(id) {
    const entry = entities.get(id);
    if (entry) {
      dataSource.entities.remove(entry.cesiumEntity);
      dataSource.entities.remove(entry.cesiumTrail);
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

    // Per-entity trail override takes precedence over global toggle
    const trailOverride = entityTrailOverrides.get(id);
    const trailVisible = trailOverride !== undefined ? trailOverride : globalTrailsVisible;

    entry.cesiumEntity.show = !hidden;
    entry.cesiumEntity.label.show = !hidden && globalLabelsVisible;
    entry.cesiumTrail.show = !hidden && trailVisible;
    entry.visible = !hidden;
  }

  // === PIXEL-DISTANCE DECLUTTER WITH RING OFFSET ===
  // Altitude-adaptive: full spread at low altitude, disabled at high altitude
  // to prevent geographic displacement (50px at 100km ≈ 6km displacement)

  function getEffectiveSpreadRadius() {
    const height = viewer.camera.positionCartographic.height;
    if (height <= DECLUTTER_FULL_ALT) return SPREAD_RADIUS_PX_MAX;
    if (height >= DECLUTTER_ZERO_ALT) return 0;
    // Linear interpolation between full and zero
    const t = (height - DECLUTTER_FULL_ALT) / (DECLUTTER_ZERO_ALT - DECLUTTER_FULL_ALT);
    return SPREAD_RADIUS_PX_MAX * (1 - t);
  }

  function getTrailVisibleForEntity(id) {
    const override = entityTrailOverrides.get(id);
    return override !== undefined ? override : globalTrailsVisible;
  }

  function resetAllDeclutter() {
    declutterOffsets.forEach((_, id) => {
      const entry = entities.get(id);
      if (entry && entry.cesiumEntity.billboard) {
        entry.cesiumEntity.billboard.pixelOffset = new Cesium.Cartesian2(0, 0);
        entry.cesiumEntity.billboard.scale = globalIconScale;
        entry.cesiumEntity.label.pixelOffset = new Cesium.Cartesian2(0, 20);
        entry.cesiumEntity.label.show = globalLabelsVisible && entry.visible;
        entry.cesiumTrail.show = getTrailVisibleForEntity(id) && entry.visible;
      }
    });
    declutterOffsets.clear();
    declutteredIds.clear();
  }

  function resetEntry(id) {
    const entry = entities.get(id);
    if (entry && entry.cesiumEntity.billboard) {
      entry.cesiumEntity.billboard.pixelOffset = new Cesium.Cartesian2(0, 0);
      entry.cesiumEntity.billboard.scale = globalIconScale;
      entry.cesiumEntity.label.pixelOffset = new Cesium.Cartesian2(0, 20);
      entry.cesiumEntity.label.show = globalLabelsVisible && entry.visible;
      entry.cesiumTrail.show = getTrailVisibleForEntity(id) && entry.visible;
    }
    declutterOffsets.delete(id);
    declutteredIds.delete(id);
  }

  function declutterEntities() {
    // Disable declutter when Cesium clustering is active
    if (clusteringEnabled) {
      if (declutterOffsets.size > 0) resetAllDeclutter();
      return;
    }

    const spreadRadius = getEffectiveSpreadRadius();

    // At high altitude, disable declutter entirely — show all at true positions
    if (spreadRadius < 2) {
      if (declutterOffsets.size > 0) resetAllDeclutter();
      return;
    }

    const scene = viewer.scene;
    const screenPositions = [];

    // Step 1: Project all entities to screen space
    entities.forEach((entry, id) => {
      if (!entry.visible) return;

      // Skip moving entities — they'll separate naturally
      const speed = entry.data.speed_knots || 0;
      if (speed > MIN_SPEED_TO_SKIP) {
        if (declutterOffsets.has(id)) resetEntry(id);
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

    // Scale overlap threshold with spread radius
    const effectiveThreshold = OVERLAP_THRESHOLD_PX * (spreadRadius / SPREAD_RADIUS_PX_MAX);

    // Step 2: Find overlapping groups
    const groups = findOverlapGroups(screenPositions, effectiveThreshold);

    // Step 3: Reset offsets for ungrouped entities
    const groupedIds = new Set();
    groups.forEach(group => group.forEach(item => groupedIds.add(item.id)));

    declutterOffsets.forEach((_, id) => {
      if (!groupedIds.has(id)) resetEntry(id);
    });

    // Step 4: Apply ring offsets to grouped entities
    groups.forEach(group => {
      if (group.length <= 1) return;

      const n = group.length;
      const scaleMultiplier = n >= SCALE_DOWN_THRESHOLD ? 0.8 : 1.0;

      for (let i = 0; i < n; i++) {
        const angle = (2 * Math.PI * i) / n - Math.PI / 2; // Start from top
        const offsetX = Math.cos(angle) * spreadRadius;
        const offsetY = Math.sin(angle) * spreadRadius;

        const item = group[i];
        const entry = entities.get(item.id);
        if (entry && entry.cesiumEntity.billboard) {
          entry.cesiumEntity.billboard.pixelOffset = new Cesium.Cartesian2(offsetX, offsetY);
          entry.cesiumEntity.billboard.scale = globalIconScale * scaleMultiplier;
          // Hide labels and trails in declutter groups to reduce visual clutter
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
    getSymbolImage,
    getSidc(entity) {
      return getSidcForEntity(entity);
    },
    setIconScale(sizePx) {
      globalIconSizePx = sizePx;
      globalIconScale = sizePx / SYMBOL_RENDER_SIZE;
      entities.forEach((entry) => {
        if (entry.cesiumEntity.billboard) {
          entry.cesiumEntity.billboard.scale = globalIconScale;
        }
      });
    },
    setLabelsVisible(visible) {
      globalLabelsVisible = visible;
      entities.forEach((entry) => {
        if (entry.cesiumEntity.label) {
          entry.cesiumEntity.label.show = visible && entry.visible;
        }
      });
    },
    setTrailsVisible(visible) {
      globalTrailsVisible = visible;
      entities.forEach((entry, id) => {
        const trailOverride = entityTrailOverrides.get(id);
        const show = trailOverride !== undefined ? trailOverride : visible;
        entry.cesiumTrail.show = show && entry.visible;
      });
    },
    updateSidcForEntity(entityId, newSidc) {
      // Per-entity SIDC override
      entitySidcOverrides.set(entityId, newSidc);
      symbolCache.clear();
      clearSymbolCache();
      const entry = entities.get(entityId);
      if (entry) {
        entry.cesiumEntity.billboard.image = getSymbolImage(entry.data);
      }
    },
    updateSidcForType(entityType, newSidc) {
      // Update config mapping for type-wide changes
      config.sidcMap[entityType] = newSidc;
      symbolCache.clear();
      clearSymbolCache();
      entities.forEach((entry, id) => {
        // Skip entities with per-entity overrides
        if (entitySidcOverrides.has(id)) return;
        if (entry.data.entity_type === entityType) {
          entry.cesiumEntity.billboard.image = getSymbolImage(entry.data);
        }
      });
    },
    setTrailDuration(hours) {
      globalTrailDurationH = hours;
      // Prune existing trails to new duration
      const now = Date.now();
      const cutoff = now - hours * 3600 * 1000;
      trailPositions.forEach((trail) => {
        while (trail.length > 2 && trail[0].ts < cutoff) {
          trail.shift();
        }
      });
    },
    getTrailDuration() {
      return globalTrailDurationH;
    },
    setEntityTrailVisible(entityId, visible) {
      if (visible === null || visible === undefined) {
        entityTrailOverrides.delete(entityId);  // Reset to global
      } else {
        entityTrailOverrides.set(entityId, visible);
      }
      const entry = entities.get(entityId);
      if (entry) {
        entry.cesiumTrail.show = visible !== false && entry.visible;
      }
    },
    getEntityTrailVisible(entityId) {
      const override = entityTrailOverrides.get(entityId);
      return override !== undefined ? override : globalTrailsVisible;
    },
    setClusteringEnabled(enabled) {
      clusteringEnabled = enabled;
    },
    getDataSource() {
      return dataSource;
    }
  };
}
