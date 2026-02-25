/**
 * Event timeline — bottom panel with scrollable event log.
 */

export function initTimeline(containerId, viewer, config) {
  const container = document.getElementById(containerId);
  if (!container) return {};

  container.innerHTML = `
    <div class="timeline-header">
      <span class="timeline-title">Event Timeline</span>
      <div class="timeline-drag-handle"></div>
    </div>
    <div class="timeline-events" id="timeline-events"></div>
  `;

  const eventsContainer = document.getElementById('timeline-events');
  const events = [];

  function addEvent(event) {
    events.push(event);

    const row = document.createElement('div');
    row.className = `timeline-event`;

    const severity = (event.severity || 'INFO').toLowerCase();
    if (severity === 'critical') row.classList.add('severity-critical');

    // Time
    const time = event.time ? new Date(event.time).toISOString().substring(11, 16) : '--:--';

    // Agency badge
    const agencies = event.alert_agencies || [];
    const agency = agencies[0] || 'ESSCOM';
    const agencyColor = config.agencyColors[agency] || config.agencyColors.UNKNOWN;

    row.innerHTML = `
      <span class="event-time">${time}</span>
      <span class="event-agency-badge" style="background: ${agencyColor}">${agency}</span>
      <span class="event-description ${severity === 'warning' ? 'warning' : ''} ${severity === 'critical' ? 'critical' : ''}">${event.description || ''}</span>
    `;

    // Click to fly to event position
    if (event.position) {
      row.style.cursor = 'pointer';
      row.addEventListener('click', () => {
        viewer.camera.flyTo({
          destination: Cesium.Cartesian3.fromDegrees(
            event.position.longitude,
            event.position.latitude,
            80000
          ),
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

    // Flash animation for critical events
    if (severity === 'critical' || severity === 'warning') {
      row.classList.add('flash');
      setTimeout(() => row.classList.remove('flash'), 1000);
    }

    // Auto-scroll to bottom
    eventsContainer.scrollTop = eventsContainer.scrollHeight;

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

  function getEventCount() {
    return events.length;
  }

  return { addEvent, getEventCount };
}
