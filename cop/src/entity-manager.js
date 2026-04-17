/**
 * Entity lifecycle management for CesiumJS.
 *
 * Each simulation entity maps to a Cesium Billboard (symbol)
 * + Polyline (track trail). Callsign labels are HTML overlay divs
 * (pooled, RAF-updated at 30fps) for crisp rendering at any zoom level.
 * Uses JMSML DISA SVGs for MIL-STD-2525D symbols.
 *
 * Features:
 * - Live position via CallbackProperty (reads entry.data.position each frame)
 * - Trail polylines with fading alpha
 * - Pixel-distance declutter with ring offset (pixelOffset only, no extra entities)
 * - Pooled HTML labels — no Cesium Label objects
 * - Symbol caching for performance
 */

import * as Cesium from 'cesium';
import { renderSymbol, clearSymbolCache } from './symbol-renderer.js';

const TRAIL_UPDATE_INTERVAL = 2; // Update trail every Nth position update
const SYMBOL_RENDER_SIZE = 256;  // Render SVGs at 256px — crisp up to 80px display at 2× DPR
const TRAIL_WIDTH = 1.5;         // Trail polyline width in pixels
const MAX_TRAIL_POINTS = 300;    // Max trail points per entity (ring buffer)
const MIN_TRAIL_DISTANCE_DEG = 0.001; // ~111 meters — minimum distance between trail points

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
  let globalIconSizePx = 60;   // desired display size in pixels (matches settings-panel default)
  let globalIconScale = globalIconSizePx / SYMBOL_RENDER_SIZE;
  let globalLabelsVisible = true;
  let globalTrailsVisible = true;
  let globalTrailDurationH = DEFAULT_TRAIL_DURATION_H;
  let clusteringEnabled = false;

  // Set of entity IDs currently absorbed into a Cesium cluster — labels suppressed
  const cesiumClusteredIds = new Set();

  // === HTML LABEL OVERLAY ===
  // Pool of divs positioned over the Cesium canvas each RAF frame.
  const LABEL_POOL_SIZE = 150;
  const LABEL_MAX_ALT = 2000000;   // no labels above 2,000km
  const LABEL_AIS_MAX_ALT = 500000; // AIS labels only below 500km
  const LABEL_FRAME_MS = 33;       // ~30fps

  const labelOverlay = document.createElement('div');
  labelOverlay.id = 'entity-labels-overlay';
  labelOverlay.style.cssText = 'position:absolute;inset:0;pointer-events:none;overflow:hidden;z-index:5;';
  viewer.container.appendChild(labelOverlay);

  const labelPool = [];
  for (let i = 0; i < LABEL_POOL_SIZE; i++) {
    const div = document.createElement('div');
    div.className = 'entity-label';
    div.style.cssText = 'position:absolute;display:none;transform:translate(-50%,0);';
    labelOverlay.appendChild(div);
    labelPool.push(div);
  }

  let lastLabelFrameTs = 0;
  function updateLabelOverlay(ts) {
    requestAnimationFrame(updateLabelOverlay);
    if (ts - lastLabelFrameTs < LABEL_FRAME_MS) return;
    lastLabelFrameTs = ts;

    // Hide all pool slots
    for (const div of labelPool) div.style.display = 'none';

    if (!globalLabelsVisible) return;

    const altitude = viewer.camera.positionCartographic.height;
    if (altitude > LABEL_MAX_ALT) return;

    const scene = viewer.scene;
    const cw = viewer.canvas.clientWidth;
    const ch = viewer.canvas.clientHeight;
    let poolIdx = 0;

    entities.forEach((entry, id) => {
      if (poolIdx >= LABEL_POOL_SIZE) return;
      if (!entry.visible) return;
      if (declutteredIds.has(id)) return;
      if (cesiumClusteredIds.has(id)) return;

      // AIS labels only when zoomed in enough
      if (id.startsWith('AIS-') && altitude > LABEL_AIS_MAX_ALT) return;

      const pos = entry.data.position;
      if (!pos) return;

      const cartesian = Cesium.Cartesian3.fromDegrees(
        pos.longitude, pos.latitude, pos.altitude_m || 0
      );
      const sp = Cesium.SceneTransforms.worldToWindowCoordinates(scene, cartesian);
      if (!sp) return;

      // Apply declutter pixel offset if active
      const off = declutterOffsets.get(id);
      const sx = sp.x + (off ? off.x : 0);
      // Place label 4px below the icon's bottom edge.
      // The visible symbol is approximately square, so use iconSizePx as both dimensions.
      const iconHalfH = globalIconSizePx * 0.30;
      const sy = sp.y + (off ? off.y : 0) + iconHalfH + 4;

      // Frustum check — skip off-screen entities
      if (sx < -60 || sx > cw + 60 || sy < -20 || sy > ch + 20) return;

      const div = labelPool[poolIdx++];
      const text = entry.data.callsign || id;
      if (div.textContent !== text) div.textContent = text;
      div.style.left = `${Math.round(sx)}px`;
      div.style.top = `${Math.round(sy)}px`;
      div.style.display = 'block';
    });
  }
  requestAnimationFrame(updateLabelOverlay);

  // Per-entity SIDC overrides (entity_id -> sidc)
  const entitySidcOverrides = new Map();

  // Per-entity trail visibility overrides (entity_id -> boolean)
  const entityTrailOverrides = new Map();

  // Refresh billboards when background SVG fetches complete
  window.addEventListener('symbols-updated', (e) => {
    const updatedSidc = e.detail?.sidc;
    if (!updatedSidc) return;

    // Invalidate local symbol cache for this SIDC
    symbolCache.delete(updatedSidc);

    // Re-render billboards for all entities using this SIDC
    entities.forEach((entry) => {
      const sidc = getSidcForEntity(entry.data);
      if (sidc === updatedSidc) {
        entry.cesiumEntity.billboard.image = getSymbolImage(entry.data);
      }
    });
  });

  // Snapshot generation counter — suppress trail accumulation for first N updates after reset
  let snapshotGeneration = 0;

  // Declutter state
  const declutterOffsets = new Map(); // entity_id -> { x, y } pixel offset
  const declutteredIds = new Set();   // entity IDs currently in a declutter group

  // === JMSML SYMBOL RENDERING ===
  function getSidcForEntity(entity) {
    // Per-entity override takes precedence (set by SIDC change events)
    if (entitySidcOverrides.has(entity.entity_id)) {
      return entitySidcOverrides.get(entity.entity_id);
    }
    // Entity-level SIDC from server (e.g., initial identity override)
    if (entity.sidc && entity.sidc.length >= 20) {
      return entity.sidc;
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

    const livePosition = new Cesium.CallbackProperty((time, result) => {
      const entry = entities.get(id);
      const p = entry?.data?.position;
      if (!p || p.latitude == null || p.longitude == null) return undefined;
      return Cesium.Cartesian3.fromDegrees(
        p.longitude, p.latitude, p.altitude_m || 0,
        Cesium.Ellipsoid.WGS84, result
      );
    }, false);

    const cesiumEntity = dataSource.entities.add({
      id: `entity-${id}`,
      position: livePosition,
      billboard: {
        image: getSymbolImage(entityData),
        verticalOrigin: Cesium.VerticalOrigin.CENTER,
        horizontalOrigin: Cesium.HorizontalOrigin.CENTER,
        scale: globalIconScale,
        rotation: 0,
        pixelOffset: new Cesium.Cartesian2(0, 0),
        disableDepthTestDistance: Number.POSITIVE_INFINITY
      },
      // No Cesium Label — callsign labels are HTML overlay divs (see updateLabelOverlay)
    });

    const ts = entityData.timestamp ? new Date(entityData.timestamp).getTime() : Date.now();
    trailPositions.set(id, [{ lat, lon, alt, ts }]);
    updateCounters.set(id, 0);

    const agencyColor = Cesium.Color.fromCssColorString(getAgencyColor(entityData.agency));

    const cesiumTrail = dataSource.entities.add({
      id: `trail-${id}`,
      polyline: {
        positions: [],
        width: TRAIL_WIDTH,
        show: globalTrailsVisible,
        material: agencyColor.withAlpha(0.9),
        clampToGround: false,
        disableDepthTestDistance: Number.POSITIVE_INFINITY
      }
    });

    entities.set(id, {
      cesiumEntity,
      cesiumTrail,
      data: entityData,
      visible: true,
      createdAtGeneration: snapshotGeneration
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

    const typeChanged = entityData.entity_type !== entry.data.entity_type;
    // Detect per-entity SIDC change (e.g. identity escalation: Unknown→Suspect→Hostile)
    const sidcChanged = entityData.sidc && entityData.sidc.length >= 10
      && entityData.sidc !== entry.data.sidc;
    if (sidcChanged) {
      entitySidcOverrides.set(id, entityData.sidc);
      symbolCache.delete(entityData.sidc);
    }
    if (typeChanged || sidcChanged || entityData.status !== entry.data.status) {
      entry.cesiumEntity.billboard.image = getSymbolImage(entityData);
    }

    // AIS tracking state: grey out when transponder goes dark, restore on reclassification
    const prevAisActive = entry.data.metadata?.ais_active !== false;
    const currAisActive = entityData.metadata?.ais_active !== false;
    if (typeChanged) {
      // Entity reclassified — restore full-colour rendering regardless of ais_active
      entry.cesiumEntity.billboard.color = Cesium.Color.WHITE;
      entry.cesiumTrail.polyline.material =
        Cesium.Color.fromCssColorString(getAgencyColor(entityData.agency)).withAlpha(0.9);
    } else if (!currAisActive && prevAisActive) {
      // AIS just went dark — grey out symbol and trail
      entry.cesiumEntity.billboard.color = new Cesium.Color(0.53, 0.53, 0.53, 0.65);
      entry.cesiumTrail.polyline.material = new Cesium.Color(0.53, 0.53, 0.53, 0.45);
    }

    const count = (updateCounters.get(id) || 0) + 1;
    updateCounters.set(id, count);
    // Skip trail accumulation for first few updates after a snapshot to prevent
    // trail artifacts from old->new position jumps, regardless of sim speed
    const suppressTrail = entry.createdAtGeneration === snapshotGeneration && count < TRAIL_UPDATE_INTERVAL * 3;
    const isStationary = (entityData.speed_knots || 0) < 0.1;
    if (!suppressTrail && !isStationary && count % TRAIL_UPDATE_INTERVAL === 0) {
      const trail = trailPositions.get(id) || [];
      // Use clean track position (pre-noise) if available, else noisy position
      const meta = entityData.metadata || {};
      const trailLat = meta.track_lat != null ? meta.track_lat : lat;
      const trailLon = meta.track_lon != null ? meta.track_lon : lon;
      const lastPoint = trail[trail.length - 1];
      const dist = lastPoint
        ? Math.sqrt(Math.pow(trailLat - lastPoint.lat, 2) + Math.pow(trailLon - lastPoint.lon, 2))
        : Infinity;
      if (dist > MIN_TRAIL_DISTANCE_DEG) {
        const ts = entityData.timestamp ? new Date(entityData.timestamp).getTime() : Date.now();
        trail.push({ lat: trailLat, lon: trailLon, alt, ts });
        // Cap max trail points (drop oldest)
        while (trail.length > MAX_TRAIL_POINTS) {
          trail.shift();
        }
        // Prune points older than trail duration
        const cutoff = ts - globalTrailDurationH * 3600 * 1000;
        while (trail.length > 2 && trail[0].ts < cutoff) {
          trail.shift();
        }
        // Update Cesium polyline positions directly (no CallbackProperty)
        if (trail.length >= 2) {
          entry.cesiumTrail.polyline.positions = trail
            .filter(p => p.lat != null && p.lon != null && isFinite(p.lat) && isFinite(p.lon))
            .map(p => Cesium.Cartesian3.fromDegrees(p.lon, p.lat, p.alt || 0));
        }
      }
    }

    entry.data = entityData;

    // Re-apply visibility on every update so filter/trail state stays in sync
    applyVisibility(id);
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
          // Hide trails in declutter groups; HTML labels excluded via declutteredIds check
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
      trailPositions.clear();
      updateCounters.clear();
      entityTrailOverrides.clear();
      snapshotGeneration++;
      entityList.forEach(e => addOrUpdateEntity(e));
      setTimeout(declutterEntities, 500);
    },
    loadTrailHistory(trailData) {
      // trailData: { entity_id: [ {lat, lon, alt, ts}, ... ], ... }
      if (!trailData) return;
      for (const [id, points] of Object.entries(trailData)) {
        if (!entities.has(id)) continue;
        const trail = trailPositions.get(id) || [];
        // Prepend history before current trail points
        const historyPoints = points.map(p => ({
          lat: p.lat, lon: p.lon, alt: p.alt || 0,
          ts: p.ts || 0
        }));
        // Merge: history + existing (dedup by checking last history ts vs first existing ts)
        const merged = [...historyPoints];
        for (const existing of trail) {
          if (!historyPoints.length || existing.ts > historyPoints[historyPoints.length - 1].ts) {
            merged.push(existing);
          }
        }
        // Prune to trail duration
        if (merged.length > 0) {
          const latestTs = merged[merged.length - 1].ts;
          const cutoff = latestTs - globalTrailDurationH * 3600 * 1000;
          while (merged.length > 2 && merged[0].ts < cutoff) {
            merged.shift();
          }
        }
        trailPositions.set(id, merged);
        // Update Cesium polyline
        const entry = entities.get(id);
        if (entry && merged.length >= 2) {
          entry.cesiumTrail.polyline.positions = merged
            .filter(p => p.lat != null && p.lon != null && isFinite(p.lat) && isFinite(p.lon))
            .map(p => Cesium.Cartesian3.fromDegrees(p.lon, p.lat, p.alt || 0));
        }
      }
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
    getIconSizePx() {
      return globalIconSizePx;
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
      // HTML label overlay is driven by the RAF loop reading globalLabelsVisible
      if (!visible) {
        for (const div of labelPool) div.style.display = 'none';
      }
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
      // Prune existing trails to new duration and update polylines
      const now = Date.now();
      const cutoff = now - hours * 3600 * 1000;
      trailPositions.forEach((trail, id) => {
        while (trail.length > 2 && trail[0].ts < cutoff) {
          trail.shift();
        }
        const entry = entities.get(id);
        if (entry && trail.length >= 2) {
          entry.cesiumTrail.polyline.positions = trail
            .filter(p => p.lat != null && p.lon != null && isFinite(p.lat) && isFinite(p.lon))
            .map(p => Cesium.Cartesian3.fromDegrees(p.lon, p.lat, p.alt || 0));
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
      if (!enabled) cesiumClusteredIds.clear();
    },
    clearCesiumClustered() {
      cesiumClusteredIds.clear();
    },
    addCesiumClustered(entityId) {
      cesiumClusteredIds.add(entityId);
    },
    getDataSource() {
      return dataSource;
    }
  };
}
