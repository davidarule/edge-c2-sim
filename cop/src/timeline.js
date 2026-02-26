/**
 * Event timeline — bottom panel with scrollable event log.
 * Resizable via drag handle, with expand/collapse toggle.
 */

export function initTimeline(containerId, viewer, config) {
  const container = document.getElementById(containerId);
  if (!container) return {};

  // Size presets
  const SIZE_COLLAPSED = 28;   // header only
  const SIZE_DEFAULT = 120;
  const SIZE_EXPANDED = 350;
  const SIZE_MIN = 28;
  const SIZE_MAX = 500;

  let currentHeight = SIZE_DEFAULT;
  let isCollapsed = false;

  container.innerHTML = `
    <div class="timeline-header">
      <div style="display: flex; align-items: center;">
        <span class="timeline-title">Event Timeline</span>
        <span class="timeline-event-count" id="timeline-event-count"></span>
      </div>
      <div class="timeline-controls">
        <button class="timeline-expand-btn" id="timeline-toggle-btn" title="Expand/Collapse">\u25b2</button>
        <div class="timeline-drag-handle"></div>
      </div>
    </div>
    <div class="timeline-events" id="timeline-events"></div>
  `;

  const eventsContainer = document.getElementById('timeline-events');
  const toggleBtn = document.getElementById('timeline-toggle-btn');
  const countEl = document.getElementById('timeline-event-count');
  const headerEl = container.querySelector('.timeline-header');
  const events = [];

  // Drag overlay — covers the entire page during drag so Cesium doesn't steal events
  const dragOverlay = document.createElement('div');
  dragOverlay.style.cssText = `
    position: fixed; top: 0; left: 0; right: 0; bottom: 0;
    z-index: 9999; cursor: ns-resize; display: none;
  `;
  document.body.appendChild(dragOverlay);

  // Apply height to grid
  function applyHeight(h) {
    const app = document.getElementById('app');
    const isBuild = app.classList.contains('build-mode');
    if (isBuild) {
      app.style.gridTemplateRows = `48px 1fr 0px ${h}px`;
    } else {
      app.style.gridTemplateRows = `48px 1fr 40px ${h}px`;
    }
    currentHeight = h;
  }

  function updateToggleIcon() {
    if (isCollapsed || currentHeight <= SIZE_COLLAPSED) {
      toggleBtn.textContent = '\u25b2';
      toggleBtn.title = 'Expand';
    } else {
      toggleBtn.textContent = '\u25bc';
      toggleBtn.title = 'Collapse';
    }
  }

  // Toggle expand/collapse
  toggleBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    if (isCollapsed) {
      applyHeight(SIZE_DEFAULT);
      isCollapsed = false;
    } else if (currentHeight < SIZE_EXPANDED) {
      applyHeight(SIZE_EXPANDED);
    } else {
      applyHeight(SIZE_COLLAPSED);
      isCollapsed = true;
    }
    updateToggleIcon();
  });

  // Double-click header to toggle
  headerEl.addEventListener('dblclick', () => {
    if (isCollapsed || currentHeight <= SIZE_COLLAPSED) {
      applyHeight(SIZE_EXPANDED);
      isCollapsed = false;
    } else {
      applyHeight(SIZE_COLLAPSED);
      isCollapsed = true;
    }
    updateToggleIcon();
  });

  // Drag resize
  let dragging = false;
  let startY = 0;
  let startHeight = 0;

  headerEl.addEventListener('mousedown', (e) => {
    // Don't start drag on button click
    if (e.target.closest('.timeline-expand-btn')) return;
    dragging = true;
    startY = e.clientY;
    startHeight = currentHeight;
    dragOverlay.style.display = 'block';
    document.body.style.userSelect = 'none';
    e.preventDefault();
  });

  function onMouseMove(e) {
    if (!dragging) return;
    const delta = startY - e.clientY; // drag up = increase height
    const newHeight = Math.max(SIZE_MIN, Math.min(SIZE_MAX, startHeight + delta));
    applyHeight(newHeight);
    isCollapsed = newHeight <= SIZE_COLLAPSED;
    updateToggleIcon();
  }

  function onMouseUp() {
    if (dragging) {
      dragging = false;
      dragOverlay.style.display = 'none';
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    }
  }

  document.addEventListener('mousemove', onMouseMove);
  document.addEventListener('mouseup', onMouseUp);
  dragOverlay.addEventListener('mousemove', onMouseMove);
  dragOverlay.addEventListener('mouseup', onMouseUp);

  function addEvent(event) {
    events.push(event);

    const row = document.createElement('div');
    row.className = `timeline-event`;

    const severity = (event.severity || 'INFO').toLowerCase();
    if (severity === 'critical') row.classList.add('severity-critical');

    // Time — try ISO string first, then time_offset_s
    let timeStr = '--:--';
    if (event.time) {
      const d = new Date(event.time);
      if (!isNaN(d.getTime())) {
        timeStr = d.toISOString().substring(11, 16);
      }
    } else if (event.time_offset_s !== undefined) {
      // Format offset as HH:MM from start
      const totalMin = Math.floor(event.time_offset_s / 60);
      const h = Math.floor(totalMin / 60);
      const m = totalMin % 60;
      timeStr = `+${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`;
    }

    // Agency badge
    const agencies = event.alert_agencies || [];
    const agency = agencies[0] || 'ESSCOM';
    const agencyColor = config.agencyColors[agency] || config.agencyColors.UNKNOWN;

    row.innerHTML = `
      <span class="event-time">${timeStr}</span>
      <span class="event-agency-badge" style="background: ${agencyColor}">${agency}</span>
      <span class="event-description ${severity === 'warning' ? 'warning' : ''} ${severity === 'critical' ? 'critical' : ''}">${event.description || ''}</span>
    `;

    // Click to fly to event position
    const lon = event.position?.lon ?? event.position?.longitude;
    const lat = event.position?.lat ?? event.position?.latitude;
    if (lon !== undefined && lat !== undefined) {
      row.style.cursor = 'pointer';
      row.addEventListener('click', () => {
        viewer.camera.flyTo({
          destination: Cesium.Cartesian3.fromDegrees(lon, lat, 80000),
          orientation: {
            heading: 0,
            pitch: Cesium.Math.toRadians(-60),
            roll: 0
          },
          duration: 1.5
        });
      });
    }

    eventsContainer.appendChild(row);

    // Update count
    countEl.textContent = `(${events.length})`;

    // Flash animation for critical events
    if (severity === 'critical' || severity === 'warning') {
      row.classList.add('flash');
      setTimeout(() => row.classList.remove('flash'), 1000);
    }

    // Auto-scroll to bottom
    eventsContainer.scrollTop = eventsContainer.scrollHeight;

    // Auto-expand if collapsed and critical event arrives
    if (isCollapsed && (severity === 'critical' || severity === 'warning')) {
      applyHeight(SIZE_DEFAULT);
      isCollapsed = false;
      toggleBtn.textContent = '\u25b2';
    }

    // Toast notification for critical events
    if (severity === 'critical' || severity === 'warning') {
      showToast(event, agencyColor, severity);
    }
  }

  function showToast(event, agencyColor, severity) {
    const toastContainer = document.getElementById('toast-container');
    if (!toastContainer) return;

    const toast = document.createElement('div');
    toast.className = `toast toast-${severity}`;
    toast.innerHTML = `
      <span class="toast-agency" style="color: ${agencyColor}">${(event.alert_agencies || ['ESSCOM'])[0]}</span>
      <span>${event.description || ''}</span>
    `;
    toastContainer.appendChild(toast);
    setTimeout(() => toast.classList.add('toast-exit'), 4000);
    setTimeout(() => toast.remove(), 5000);
  }

  function clearEvents() {
    events.length = 0;
    eventsContainer.innerHTML = '';
    countEl.textContent = '';
  }

  function getEventCount() {
    return events.length;
  }

  return { addEvent, clearEvents, getEventCount };
}
