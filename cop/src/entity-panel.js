/**
 * Entity detail panel — right sidebar, slides in on entity click.
 */

export function initEntityPanel(containerId, entityManager, viewer) {
  const container = document.getElementById(containerId);
  const app = document.getElementById('app');
  if (!container) return {};

  let currentEntityId = null;
  let following = false;
  let followInterval = null;

  function show(entity) {
    currentEntityId = entity.entity_id;
    app.classList.add('detail-open');

    const pos = entity.position || {};
    const lat = (pos.latitude || 0).toFixed(4);
    const lon = (pos.longitude || 0).toFixed(4);
    const alt = (pos.altitude_m || 0).toFixed(1);

    const agencyColor = getAgencyColor(entity.agency);
    const statusColor = getStatusColor(entity.status);
    const symbolUrl = entityManager.getSymbolImage(entity);

    container.innerHTML = `
      <div class="entity-detail">
        <div class="entity-detail-header">
          <div class="entity-detail-symbol"><img src="${symbolUrl}" alt="symbol"></div>
          <div class="entity-detail-info">
            <div class="entity-detail-callsign">${entity.callsign || entity.entity_id}</div>
            <div class="entity-detail-type">${(entity.entity_type || '').replace(/_/g, ' ')}</div>
            <span class="entity-detail-agency" style="background: ${agencyColor}">${entity.agency || 'UNKNOWN'}</span>
          </div>
        </div>

        <div class="entity-detail-status" style="color: ${statusColor}">
          ${entity.status || 'UNKNOWN'}
        </div>

        <div class="detail-section">
          <div class="detail-section-title">Position</div>
          <div class="detail-row"><span class="detail-key">LAT</span><span class="detail-value">${lat}\u00b0 ${pos.latitude >= 0 ? 'N' : 'S'}</span></div>
          <div class="detail-row"><span class="detail-key">LON</span><span class="detail-value">${lon}\u00b0 ${pos.longitude >= 0 ? 'E' : 'W'}</span></div>
          <div class="detail-row"><span class="detail-key">ALT</span><span class="detail-value">${alt} m</span></div>
        </div>

        <div class="detail-section">
          <div class="detail-section-title">Movement</div>
          <div class="detail-row"><span class="detail-key">SPEED</span><span class="detail-value">${(entity.speed_knots || 0).toFixed(1)} kts</span></div>
          <div class="detail-row"><span class="detail-key">HDG</span><span class="detail-value">${(entity.heading_deg || 0).toFixed(0)}\u00b0</span></div>
          <div class="detail-row"><span class="detail-key">CRS</span><span class="detail-value">${(entity.course_deg || 0).toFixed(0)}\u00b0</span></div>
        </div>

        ${buildMetadataSection(entity)}

        <div class="detail-section">
          <div class="detail-section-title">Info</div>
          <div class="detail-row"><span class="detail-key">ID</span><span class="detail-value">${entity.entity_id}</span></div>
          <div class="detail-row"><span class="detail-key">Domain</span><span class="detail-value">${entity.domain || ''}</span></div>
          ${entity.timestamp ? `<div class="detail-row"><span class="detail-key">Updated</span><span class="detail-value">${new Date(entity.timestamp).toISOString().substring(11, 19)}</span></div>` : ''}
        </div>

        <div class="entity-detail-actions">
          <button class="detail-action-btn" id="btn-flyto">FLY TO</button>
          <button class="detail-action-btn ${following ? 'active' : ''}" id="btn-follow">FOLLOW</button>
          <button class="detail-action-btn" id="btn-track">TRACK</button>
          <button class="detail-action-btn" id="btn-close">CLOSE</button>
        </div>
      </div>
    `;

    // Wire actions
    document.getElementById('btn-flyto').addEventListener('click', () => {
      const flyAlt = entity.domain === 'AIR' ? 20000 : entity.domain === 'MARITIME' ? 5000 : 2000;
      viewer.camera.flyTo({
        destination: Cesium.Cartesian3.fromDegrees(pos.longitude, pos.latitude, flyAlt),
        duration: 1.0
      });
    });

    document.getElementById('btn-follow').addEventListener('click', () => {
      const cesiumEntity = entityManager.getCesiumEntity(entity.entity_id);
      if (cesiumEntity) {
        if (following) {
          viewer.trackedEntity = undefined;
          following = false;
        } else {
          viewer.trackedEntity = cesiumEntity;
          following = true;
        }
        document.getElementById('btn-follow').classList.toggle('active', following);
      }
    });

    document.getElementById('btn-close').addEventListener('click', () => hide());
  }

  function hide() {
    currentEntityId = null;
    following = false;
    viewer.trackedEntity = undefined;
    app.classList.remove('detail-open');
    container.innerHTML = '';
  }

  function buildMetadataSection(entity) {
    const meta = entity.metadata || {};
    const entries = Object.entries(meta).filter(([k, v]) =>
      !['background', 'ais_active', 'vessel_type_code'].includes(k) &&
      typeof v !== 'object'
    );
    if (entries.length === 0) return '';

    const domain = entity.domain || '';
    const title = domain === 'MARITIME' ? 'Maritime Data' :
                  domain === 'AIR' ? 'Aviation Data' :
                  domain === 'GROUND_VEHICLE' ? 'Vehicle Data' :
                  domain === 'PERSONNEL' ? 'Personnel Data' : 'Metadata';

    const rows = entries.slice(0, 8).map(([k, v]) =>
      `<div class="detail-row"><span class="detail-key">${k.replace(/_/g, ' ').toUpperCase()}</span><span class="detail-value">${v}</span></div>`
    ).join('');

    return `<div class="detail-section"><div class="detail-section-title">${title}</div>${rows}</div>`;
  }

  // Escape key closes panel
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') hide();
  });

  return { show, hide, getCurrentEntityId: () => currentEntityId };
}

function getAgencyColor(agency) {
  const colors = {
    RMP: '#1B3A8C', MMEA: '#FF6600', CI: '#2E7D32',
    RMAF: '#5C6BC0', MIL: '#4E342E', CIVILIAN: '#78909C'
  };
  return colors[agency] || '#78909C';
}

function getStatusColor(status) {
  const colors = {
    ACTIVE: '#3FB950', INTERCEPTING: '#F85149', RESPONDING: '#D29922',
    IDLE: '#8B949E', RTB: '#58A6FF', STOPPED: '#F85149'
  };
  return colors[status] || '#8B949E';
}
