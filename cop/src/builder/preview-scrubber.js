/**
 * Preview Scrubber — timeline preview for the Scenario Builder.
 *
 * Replaces the event timeline in BUILD mode with:
 * - A scrubber bar showing scenario duration
 * - Event tick marks on the bar
 * - Play/pause with speed controls (1x, 2x, 5x, 10x)
 * - Entity position interpolation along waypoints
 * - Purely client-side, no WebSocket or simulator needed
 */

import { geodesicDistance, geodesicInterpolate } from '../shared/map-utils.js';
import { renderSymbol } from '../symbol-renderer.js';

// ── Constants ──

const SYMBOL_SIZE = 48;
const PREVIEW_DS_NAME = 'builder-preview';

// ── Styles ──

const SCRUBBER_STYLES = `
  .preview-scrubber {
    display: flex; flex-direction: column; height: 100%;
    background: #0D1117; color: #C9D1D9;
    font-family: 'IBM Plex Sans', sans-serif;
  }
  .preview-header {
    display: flex; align-items: center; gap: 8px;
    padding: 6px 12px; border-bottom: 1px solid #30363D;
    flex-shrink: 0;
  }
  .preview-title { font-size: 11px; font-weight: 600; color: #E6EDF3; }
  .preview-time {
    font-family: 'IBM Plex Mono', 'JetBrains Mono', monospace;
    font-size: 13px; color: #58A6FF; min-width: 50px;
  }
  .preview-controls { display: flex; gap: 2px; margin-left: auto; }
  .preview-btn {
    padding: 3px 8px; border: none; border-radius: 3px;
    background: transparent; color: #8B949E;
    font-family: 'IBM Plex Sans', sans-serif; font-size: 10px;
    cursor: pointer;
  }
  .preview-btn:hover { background: #21262D; color: #C9D1D9; }
  .preview-btn.active { background: rgba(88,166,255,0.15); color: #58A6FF; }
  .preview-play-btn {
    padding: 3px 10px; border: none; border-radius: 3px;
    background: #238636; color: #FFF; font-size: 11px;
    font-family: 'IBM Plex Sans', sans-serif; cursor: pointer;
  }
  .preview-play-btn:hover { background: #2EA043; }
  .preview-play-btn.paused { background: #21262D; color: #8B949E; border: 1px solid #30363D; }
  .preview-bar-container {
    padding: 8px 12px; flex-shrink: 0;
  }
  .preview-bar {
    position: relative; height: 20px; background: #161B22;
    border: 1px solid #30363D; border-radius: 3px; cursor: pointer;
  }
  .preview-bar-fill {
    position: absolute; top: 0; left: 0; bottom: 0;
    background: rgba(88,166,255,0.15); border-radius: 3px 0 0 3px;
    pointer-events: none;
  }
  .preview-bar-handle {
    position: absolute; top: -2px; width: 3px; height: 24px;
    background: #58A6FF; border-radius: 2px; cursor: ew-resize;
    transform: translateX(-1px);
  }
  .preview-bar-tick {
    position: absolute; top: 0; width: 2px; height: 100%;
    border-radius: 1px; pointer-events: none;
  }
  .preview-bar-tick.info { background: rgba(88,166,255,0.5); }
  .preview-bar-tick.warning { background: rgba(210,153,34,0.5); }
  .preview-bar-tick.critical { background: rgba(248,81,73,0.5); }
  .preview-bar-tick.active { opacity: 1; }
  .preview-events-log {
    flex: 1; overflow-y: auto; padding: 4px 12px;
    font-size: 11px;
  }
  .preview-event-row {
    display: flex; gap: 8px; padding: 3px 0; align-items: baseline;
    border-bottom: 1px solid rgba(48,54,61,0.3);
  }
  .preview-event-row.past { opacity: 0.5; }
  .preview-event-row.current { background: rgba(88,166,255,0.08); border-radius: 3px; padding: 3px 4px; }
  .preview-event-time {
    font-family: 'IBM Plex Mono', monospace; font-size: 10px;
    color: #D29922; min-width: 40px; flex-shrink: 0;
  }
  .preview-event-desc { color: #C9D1D9; flex: 1; }
  .preview-event-severity { font-size: 9px; flex-shrink: 0; }
  .preview-event-severity.critical { color: #F85149; }
  .preview-event-severity.warning { color: #D29922; }
  .preview-event-severity.info { color: #58A6FF; }
`;

let stylesInjected = false;
function injectStyles() {
  if (stylesInjected) return;
  const style = document.createElement('style');
  style.textContent = SCRUBBER_STYLES;
  document.head.appendChild(style);
  stylesInjected = true;
}

/**
 * Parse event time "MM:SS" to seconds.
 */
function parseTimeToSeconds(timeStr) {
  if (!timeStr || typeof timeStr !== 'string') return 0;
  const parts = timeStr.split(':');
  if (parts.length !== 2) return 0;
  return parseInt(parts[0], 10) * 60 + parseInt(parts[1], 10);
}

/**
 * Format seconds to "MM:SS".
 */
function formatTime(seconds) {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

/**
 * Initialize the preview scrubber.
 *
 * @param {HTMLElement} container - Container element (replaces timeline in BUILD mode)
 * @param {Cesium.Viewer} viewer
 * @param {object} config
 * @returns {object} API
 */
export function initPreviewScrubber(container, viewer, config) {
  injectStyles();

  const previewDataSource = new Cesium.CustomDataSource(PREVIEW_DS_NAME);
  viewer.dataSources.add(previewDataSource);

  // State
  let scenario = null;
  let playing = false;
  let speed = 1;
  let currentTime = 0; // seconds
  let durationSeconds = 3600; // default 60 min
  let animFrameId = null;
  let lastFrameTime = 0;
  let visible = false;

  // DOM — append scrubber alongside existing timeline content (don't clear)
  const root = document.createElement('div');
  root.className = 'preview-scrubber';
  root.style.display = 'none';
  container.appendChild(root);

  function render() {
    const events = (scenario && scenario.events) || [];
    const sortedEvents = [...events].sort((a, b) =>
      parseTimeToSeconds(a.time) - parseTimeToSeconds(b.time)
    );

    root.innerHTML = `
      <div class="preview-header">
        <button class="preview-play-btn ${playing ? '' : 'paused'}" data-action="toggle">
          ${playing ? '⏸ Pause' : '▶ Play'}
        </button>
        <span class="preview-time">${formatTime(currentTime)}</span>
        <span style="color:#484F58;font-size:10px;">/ ${formatTime(durationSeconds)}</span>
        <div class="preview-controls">
          ${[1, 2, 5, 10].map(s =>
            `<button class="preview-btn ${speed === s ? 'active' : ''}" data-speed="${s}">${s}x</button>`
          ).join('')}
        </div>
        <button class="preview-btn" data-action="reset" title="Reset to start">⟲</button>
      </div>
      <div class="preview-bar-container">
        <div class="preview-bar" data-action="seek">
          <div class="preview-bar-fill" style="width:${(currentTime / durationSeconds * 100).toFixed(1)}%"></div>
          ${sortedEvents.map(ev => {
            const t = parseTimeToSeconds(ev.time);
            const pct = (t / durationSeconds * 100).toFixed(1);
            const sev = (ev.severity || 'info').toLowerCase();
            const active = Math.abs(t - currentTime) < 2 ? ' active' : '';
            return `<div class="preview-bar-tick ${sev}${active}" style="left:${pct}%" title="${ev.time} - ${ev.description || ''}"></div>`;
          }).join('')}
          <div class="preview-bar-handle" style="left:${(currentTime / durationSeconds * 100).toFixed(1)}%"></div>
        </div>
      </div>
      <div class="preview-events-log">
        ${sortedEvents.map(ev => {
          const t = parseTimeToSeconds(ev.time);
          const sev = (ev.severity || 'info').toLowerCase();
          let cls = '';
          if (t < currentTime - 1) cls = 'past';
          else if (Math.abs(t - currentTime) <= 2) cls = 'current';
          return `<div class="preview-event-row ${cls}">
            <span class="preview-event-time">${ev.time || '--:--'}</span>
            <span class="preview-event-desc">${escapeHtml(ev.description || ev.type || '')}</span>
            <span class="preview-event-severity ${sev}">${sev.toUpperCase()}</span>
          </div>`;
        }).join('')}
        ${sortedEvents.length === 0 ? '<div style="padding:12px;text-align:center;color:#484F58;">No events defined</div>' : ''}
      </div>
    `;

    wireEvents();
  }

  function wireEvents() {
    // Play/pause toggle
    const playBtn = root.querySelector('[data-action="toggle"]');
    if (playBtn) playBtn.addEventListener('click', togglePlay);

    // Speed buttons
    root.querySelectorAll('[data-speed]').forEach(btn => {
      btn.addEventListener('click', () => {
        speed = parseInt(btn.dataset.speed, 10);
        render();
      });
    });

    // Reset
    const resetBtn = root.querySelector('[data-action="reset"]');
    if (resetBtn) resetBtn.addEventListener('click', () => {
      currentTime = 0;
      stop();
      render();
      updatePreviewEntities();
    });

    // Seek bar
    const bar = root.querySelector('[data-action="seek"]');
    if (bar) {
      let seeking = false;

      const doSeek = (e) => {
        const rect = bar.getBoundingClientRect();
        const pct = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
        currentTime = pct * durationSeconds;
        render();
        updatePreviewEntities();
      };

      bar.addEventListener('mousedown', (e) => {
        seeking = true;
        doSeek(e);
      });
      document.addEventListener('mousemove', (e) => {
        if (seeking) doSeek(e);
      });
      document.addEventListener('mouseup', () => { seeking = false; });
    }
  }

  // ── Playback ──

  function togglePlay() {
    if (playing) {
      stop();
    } else {
      play();
    }
    render();
  }

  function play() {
    if (playing) return;
    if (currentTime >= durationSeconds) currentTime = 0;
    playing = true;
    lastFrameTime = performance.now();
    tick();
  }

  function stop() {
    playing = false;
    if (animFrameId) {
      cancelAnimationFrame(animFrameId);
      animFrameId = null;
    }
  }

  function tick() {
    if (!playing) return;

    const now = performance.now();
    const dt = (now - lastFrameTime) / 1000; // real seconds elapsed
    lastFrameTime = now;

    currentTime += dt * speed;

    if (currentTime >= durationSeconds) {
      currentTime = durationSeconds;
      stop();
      render();
      updatePreviewEntities();
      return;
    }

    updatePreviewEntities();

    // Update time display and bar (lightweight, no full re-render)
    const timeEl = root.querySelector('.preview-time');
    if (timeEl) timeEl.textContent = formatTime(currentTime);

    const fill = root.querySelector('.preview-bar-fill');
    if (fill) fill.style.width = `${(currentTime / durationSeconds * 100).toFixed(1)}%`;

    const handle = root.querySelector('.preview-bar-handle');
    if (handle) handle.style.left = `${(currentTime / durationSeconds * 100).toFixed(1)}%`;

    // Highlight current events
    const eventRows = root.querySelectorAll('.preview-event-row');
    const events = (scenario && scenario.events) || [];
    const sortedEvents = [...events].sort((a, b) =>
      parseTimeToSeconds(a.time) - parseTimeToSeconds(b.time)
    );
    eventRows.forEach((row, i) => {
      if (i >= sortedEvents.length) return;
      const t = parseTimeToSeconds(sortedEvents[i].time);
      row.className = 'preview-event-row';
      if (t < currentTime - 1) row.classList.add('past');
      else if (Math.abs(t - currentTime) <= 2) row.classList.add('current');
    });

    animFrameId = requestAnimationFrame(tick);
  }

  // ── Entity position interpolation ──

  /**
   * Interpolate entity position at a given time along its waypoints.
   */
  function interpolateEntityPosition(entity, timeSeconds) {
    if (!entity.initial_position) return null;

    const wps = entity.waypoints || [];
    if (wps.length === 0) {
      return {
        latitude: entity.initial_position.latitude,
        longitude: entity.initial_position.longitude,
        altitude_m: entity.initial_position.altitude_m || 0,
      };
    }

    // Build position chain: start position + all waypoints
    const chain = [
      {
        latitude: entity.initial_position.latitude,
        longitude: entity.initial_position.longitude,
        altitude_m: entity.initial_position.altitude_m || 0,
        _time_seconds: 0,
      },
    ];

    // Calculate cumulative times for waypoints
    let cumulativeTime = 0;
    for (let i = 0; i < wps.length; i++) {
      const prev = i === 0 ? chain[0] : wps[i - 1];
      const wp = wps[i];
      const dist = geodesicDistance(
        prev.latitude, prev.longitude,
        wp.latitude, wp.longitude
      );
      const speedMs = ((wp.speed_knots || 10) * 1852) / 3600; // knots to m/s
      const segTime = speedMs > 0 ? dist / speedMs : 0;
      cumulativeTime += segTime;

      chain.push({
        latitude: wp.latitude,
        longitude: wp.longitude,
        altitude_m: wp.altitude_m || 0,
        _time_seconds: cumulativeTime,
      });
    }

    // Find segment at current time
    if (timeSeconds <= 0) return chain[0];
    if (timeSeconds >= cumulativeTime && cumulativeTime > 0) return chain[chain.length - 1];

    for (let i = 1; i < chain.length; i++) {
      if (timeSeconds <= chain[i]._time_seconds) {
        const segStart = chain[i - 1];
        const segEnd = chain[i];
        const segDuration = segEnd._time_seconds - segStart._time_seconds;
        const t = segDuration > 0
          ? (timeSeconds - segStart._time_seconds) / segDuration
          : 0;

        const interp = geodesicInterpolate(
          segStart.latitude, segStart.longitude,
          segEnd.latitude, segEnd.longitude,
          Math.max(0, Math.min(1, t))
        );

        const alt = segStart.altitude_m + (segEnd.altitude_m - segStart.altitude_m) * t;

        return {
          latitude: interp.latitude,
          longitude: interp.longitude,
          altitude_m: alt,
        };
      }
    }

    return chain[chain.length - 1];
  }

  /**
   * Update all preview entity positions on the globe.
   */
  function updatePreviewEntities() {
    previewDataSource.entities.removeAll();

    if (!scenario) return;
    const entities = scenario.entities || [];

    for (const entity of entities) {
      if (!entity.placed || !entity.initial_position) continue;

      const pos = interpolateEntityPosition(entity, currentTime);
      if (!pos) continue;

      const sidc = entity.sidc || '10030000000000000000';
      const symbolUrl = renderSymbol(sidc, { size: SYMBOL_SIZE });

      previewDataSource.entities.add({
        id: `preview-${entity.id}`,
        position: Cesium.Cartesian3.fromDegrees(
          pos.longitude, pos.latitude, pos.altitude_m || 0
        ),
        billboard: {
          image: symbolUrl,
          scale: 0.75,
          verticalOrigin: Cesium.VerticalOrigin.CENTER,
          horizontalOrigin: Cesium.HorizontalOrigin.CENTER,
          disableDepthTestDistance: Number.POSITIVE_INFINITY,
        },
        label: {
          text: entity.callsign || entity.id,
          font: '11px IBM Plex Sans, sans-serif',
          fillColor: Cesium.Color.fromCssColorString('#C9D1D9'),
          outlineColor: Cesium.Color.BLACK,
          outlineWidth: 2,
          style: Cesium.LabelStyle.FILL_AND_OUTLINE,
          pixelOffset: new Cesium.Cartesian2(0, -30),
          horizontalOrigin: Cesium.HorizontalOrigin.CENTER,
          verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
          disableDepthTestDistance: Number.POSITIVE_INFINITY,
          scale: 1.0,
        },
      });
    }
  }

  // ── Public API ──

  return {
    /**
     * Show the preview scrubber.
     */
    show() {
      visible = true;
      root.style.display = 'flex';
      render();
    },

    /**
     * Hide the preview scrubber and stop playback.
     */
    hide() {
      visible = false;
      root.style.display = 'none';
      stop();
      previewDataSource.entities.removeAll();
    },

    /**
     * Set the scenario to preview.
     * @param {object} scen - Scenario state object
     */
    setScenario(scen) {
      scenario = scen;
      if (scen && scen.metadata && scen.metadata.duration_minutes) {
        durationSeconds = scen.metadata.duration_minutes * 60;
      } else {
        durationSeconds = 3600;
      }
      if (visible) render();
    },

    /**
     * Reset to beginning.
     */
    reset() {
      currentTime = 0;
      stop();
      if (visible) {
        render();
        updatePreviewEntities();
      }
    },

    /**
     * Check if currently playing.
     */
    isPlaying() { return playing; },

    /**
     * Get current preview time in seconds.
     */
    getCurrentTime() { return currentTime; },

    /**
     * Destroy and clean up.
     */
    destroy() {
      stop();
      previewDataSource.entities.removeAll();
      viewer.dataSources.remove(previewDataSource);
      root.remove();
    },

    /**
     * Get the data source (for external use).
     */
    getDataSource() {
      return previewDataSource;
    },
  };
}

function escapeHtml(s) {
  const div = document.createElement('div');
  div.textContent = s || '';
  return div.innerHTML;
}
