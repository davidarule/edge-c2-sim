/**
 * Entity detail panel — right sidebar, slides in on entity click.
 * SIDC fields (Identity, Symbol Set, Main Icon, Mod1, Mod2) are editable dropdowns.
 * Changes are dispatched as 'sidc-update' CustomEvents on the document.
 */

export function initEntityPanel(containerId, entityManager, viewer) {
  const container = document.getElementById(containerId);
  const app = document.getElementById('app');
  if (!container) return {};

  let currentEntityId = null;
  let following = false;

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
          <div class="entity-detail-symbol"><img src="${symbolUrl}" alt="symbol" id="sidc-preview-img"></div>
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
        ${buildSidcSection(entity, entityManager)}

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

    // Wire SIDC editor dropdowns
    wireSidcEditor(entity);
  }

  function wireSidcEditor(entity) {
    const selIdentity = document.getElementById('sidc-identity');
    const selSymbolSet = document.getElementById('sidc-symbolset');
    const selMainIcon = document.getElementById('sidc-mainicon');
    const selMod1 = document.getElementById('sidc-mod1');
    const selMod2 = document.getElementById('sidc-mod2');
    if (!selIdentity) return; // No SIDC section

    function onSidcChange() {
      const identity = selIdentity.value;
      const symbolSet = selSymbolSet.value;
      const entity6 = selMainIcon.value;
      const mod1 = selMod1.value;
      const mod2 = selMod2.value;
      const newSidc = `100${identity}${symbolSet}0000${entity6}${mod1}${mod2}`;

      // Update the SIDC display
      const sidcDisplay = document.getElementById('sidc-code-display');
      if (sidcDisplay) sidcDisplay.textContent = newSidc;

      // Dispatch event for main.js to handle (which also updates the preview image)
      document.dispatchEvent(new CustomEvent('sidc-update', {
        detail: {
          entityType: entity.entity_type,
          entityId: entity.entity_id,
          sidc: newSidc,
        }
      }));
    }

    // When Symbol Set changes, repopulate Main Icon dropdown
    selSymbolSet.addEventListener('change', () => {
      const newSS = selSymbolSet.value;
      populateMainIconDropdown(selMainIcon, newSS, '000000');
      populateModDropdowns(selMod1, selMod2, newSS, '00', '00');
      onSidcChange();
    });

    selIdentity.addEventListener('change', onSidcChange);
    selMainIcon.addEventListener('change', onSidcChange);
    selMod1.addEventListener('change', onSidcChange);
    selMod2.addEventListener('change', onSidcChange);
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
      !['background', 'ais_active', 'vessel_type_code', 'entity_type_name'].includes(k) &&
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

// === SIDC DECODER / EDITOR ===
// MIL-STD-2525D/E 20-character numeric SIDC breakdown

const IDENTITY_LABELS = {
  '0': 'Pending', '1': 'Unknown', '2': 'Assumed Friend',
  '3': 'Friend', '4': 'Neutral', '5': 'Suspect', '6': 'Hostile'
};
const SYMBOL_SET_LABELS = {
  '01': 'Air', '02': 'Air Missile', '05': 'Space',
  '10': 'Land Unit', '11': 'Land Civilian', '15': 'Land Equipment',
  '20': 'Land Installation', '30': 'Sea Surface', '35': 'Sea Subsurface',
  '36': 'Mine Warfare', '40': 'Activity'
};
const STATUS_LABELS = {
  '0': 'Present', '1': 'Planned', '2': 'Fully Capable',
  '3': 'Damaged', '4': 'Destroyed', '5': 'Full to Capacity'
};

// Main icon names: key is SymbolSet(2) + Entity(2) + Type(2) + Subtype(2)
const ENTITY_LABELS = {
  // Sea Surface (30)
  '30120000': 'Military Combatant',
  '30120100': 'Carrier',
  '30120200': 'Surface Combatant, Line',
  '30120201': 'Battleship', '30120202': 'Cruiser', '30120203': 'Destroyer',
  '30120204': 'Frigate', '30120205': 'Corvette', '30120206': 'LCS',
  '30120300': 'Amphibious Warfare Ship',
  '30120400': 'Mine Warfare Ship', '30120401': 'Mine Layer', '30120402': 'Mine Sweeper',
  '30120500': 'Patrol Boat', '30120501': 'Patrol Craft', '30120502': 'Patrol Ship',
  '30120800': 'Speedboat', '30120801': 'RHIB',
  '30140000': 'Civilian', '30140100': 'Merchant Ship',
  '30140101': 'Cargo', '30140102': 'Container', '30140109': 'Oiler/Tanker',
  '30140110': 'Passenger', '30140200': 'Fishing Vessel',
  '30140201': 'Drifter', '30140202': 'Trawler',
  '30140300': 'Law Enforcement Vessel',
  '30140400': 'Leisure Sail', '30140500': 'Leisure Motor',
  // Air (01)
  '01110000': 'Military Air', '01110100': 'Fixed-Wing',
  '01110102': 'Attack/Strike', '01110103': 'Bomber',
  '01110104': 'Fighter', '01110105': 'Fighter/Bomber',
  '01110107': 'Cargo', '01110110': 'Patrol', '01110200': 'Rotary-Wing',
  '01120000': 'Civilian Air', '01120100': 'Civilian Fixed Wing',
  // Land Unit (10)
  '10120500': 'Armor', '10121100': 'Infantry', '10121300': 'Recon/Cavalry',
  '10121700': 'Special Forces', '10121800': 'SOF',
  '10110000': 'Civilian', '10140000': 'Law Enforcement',
  // Land Equipment (15)
  '15120100': 'Armored Vehicle', '15120101': 'APC',
  '15170000': 'Law Enforcement', '15170200': 'Border Patrol',
  '15170300': 'Customs Service', '15170700': 'Police',
};

// Modifier labels keyed by Symbol Set
const MOD1_LABELS = {
  '30': {
    '00': '(none)', '01': 'Own Ship', '02': 'AAW', '03': 'ASW', '04': 'Escort',
    '05': 'EW', '06': 'ISR', '12': 'SOF', '13': 'Surface Warfare',
    '15': 'Guided Missile', '19': 'Helo-Equipped',
  },
  '01': {
    '00': '(none)', '01': 'Attack', '02': 'Bomber', '03': 'Cargo',
    '04': 'Fighter', '05': 'Interceptor', '06': 'Tanker/Refueler',
  },
  '10': { '00': '(none)' },
  '15': { '00': '(none)' },
};
const MOD2_LABELS = {
  '30': {
    '00': '(none)', '01': 'Nuclear', '02': 'Heavy', '03': 'Light',
    '04': 'Medium', '09': 'Fast',
  },
  '01': { '00': '(none)' },
  '10': { '00': '(none)' },
  '15': { '00': '(none)' },
};

function decodeSidc(sidc) {
  if (!sidc || sidc.length !== 20) return null;
  const identity = sidc[3];
  const symbolSet = sidc.substring(4, 6);
  const status = sidc[6];
  const entity6 = sidc.substring(10, 16);
  const mod1 = sidc.substring(16, 18);
  const mod2 = sidc.substring(18, 20);
  const entityKey = symbolSet + entity6;
  const mainIcon = ENTITY_LABELS[entityKey]
    || ENTITY_LABELS[symbolSet + entity6.substring(0, 4) + '00']
    || ENTITY_LABELS[symbolSet + entity6.substring(0, 2) + '0000']
    || `${entity6}`;
  const mod1Labels = MOD1_LABELS[symbolSet] || MOD1_LABELS['30'];
  const mod2Labels = MOD2_LABELS[symbolSet] || MOD2_LABELS['30'];
  const mod1Label = mod1Labels[mod1] || (mod1 !== '00' ? mod1 : '');
  const mod2Label = mod2Labels[mod2] || (mod2 !== '00' ? mod2 : '');

  return {
    sidc,
    identityCode: identity,
    identity: IDENTITY_LABELS[identity] || identity,
    symbolSetCode: symbolSet,
    symbolSet: SYMBOL_SET_LABELS[symbolSet] || symbolSet,
    statusCode: status,
    status: STATUS_LABELS[status] || status,
    entity6,
    mainIcon,
    mod1Code: mod1,
    mod1: mod1Label,
    mod2Code: mod2,
    mod2: mod2Label,
  };
}

function buildSelectOptions(map, selectedKey) {
  return Object.entries(map).map(([code, label]) => {
    const sel = code === selectedKey ? ' selected' : '';
    return `<option value="${code}"${sel}>${code} — ${label}</option>`;
  }).join('');
}

function getEntityLabelsForSymbolSet(symbolSet) {
  const result = {};
  for (const [key, label] of Object.entries(ENTITY_LABELS)) {
    if (key.startsWith(symbolSet)) {
      const entity6 = key.substring(2); // strip the 2-digit symbol set prefix
      result[entity6] = label;
    }
  }
  return result;
}

function populateMainIconDropdown(select, symbolSet, currentEntity6) {
  const icons = getEntityLabelsForSymbolSet(symbolSet);
  select.innerHTML = '';
  for (const [code, label] of Object.entries(icons)) {
    const opt = document.createElement('option');
    opt.value = code;
    opt.textContent = `${code} — ${label}`;
    if (code === currentEntity6) opt.selected = true;
    select.appendChild(opt);
  }
  // If current value not in list, add it
  if (!icons[currentEntity6] && currentEntity6) {
    const opt = document.createElement('option');
    opt.value = currentEntity6;
    opt.textContent = `${currentEntity6} — (custom)`;
    opt.selected = true;
    select.insertBefore(opt, select.firstChild);
  }
}

function populateModDropdowns(mod1Select, mod2Select, symbolSet, currentMod1, currentMod2) {
  const m1Labels = MOD1_LABELS[symbolSet] || { '00': '(none)' };
  const m2Labels = MOD2_LABELS[symbolSet] || { '00': '(none)' };

  mod1Select.innerHTML = '';
  for (const [code, label] of Object.entries(m1Labels)) {
    const opt = document.createElement('option');
    opt.value = code;
    opt.textContent = `${code} — ${label}`;
    if (code === currentMod1) opt.selected = true;
    mod1Select.appendChild(opt);
  }
  if (!m1Labels[currentMod1] && currentMod1 !== '00') {
    const opt = document.createElement('option');
    opt.value = currentMod1;
    opt.textContent = `${currentMod1} — (custom)`;
    opt.selected = true;
    mod1Select.insertBefore(opt, mod1Select.firstChild);
  }

  mod2Select.innerHTML = '';
  for (const [code, label] of Object.entries(m2Labels)) {
    const opt = document.createElement('option');
    opt.value = code;
    opt.textContent = `${code} — ${label}`;
    if (code === currentMod2) opt.selected = true;
    mod2Select.appendChild(opt);
  }
  if (!m2Labels[currentMod2] && currentMod2 !== '00') {
    const opt = document.createElement('option');
    opt.value = currentMod2;
    opt.textContent = `${currentMod2} — (custom)`;
    opt.selected = true;
    mod2Select.insertBefore(opt, mod2Select.firstChild);
  }
}

function buildSidcSection(entity, entityManager) {
  const sidc = entityManager.getSidc ? entityManager.getSidc(entity)
    : (window.__copConfig?.sidcMap?.[entity.entity_type] || '');
  if (!sidc) return '';
  const d = decodeSidc(sidc);
  if (!d) return '';

  const entityIcons = getEntityLabelsForSymbolSet(d.symbolSetCode);
  const m1Labels = MOD1_LABELS[d.symbolSetCode] || { '00': '(none)' };
  const m2Labels = MOD2_LABELS[d.symbolSetCode] || { '00': '(none)' };

  // Build main icon options
  let mainIconOpts = '';
  let foundCurrent = false;
  for (const [code, label] of Object.entries(entityIcons)) {
    const sel = code === d.entity6 ? ' selected' : '';
    if (code === d.entity6) foundCurrent = true;
    mainIconOpts += `<option value="${code}"${sel}>${code} \u2014 ${label}</option>`;
  }
  if (!foundCurrent && d.entity6) {
    mainIconOpts = `<option value="${d.entity6}" selected>${d.entity6} \u2014 (custom)</option>` + mainIconOpts;
  }

  const selectStyle = 'style="width:100%;background:#161B22;color:#E6EDF3;border:1px solid #30363D;border-radius:3px;padding:3px 4px;font-size:11px;font-family:\'IBM Plex Mono\',monospace;cursor:pointer;"';

  return `
    <div class="detail-section">
      <div class="detail-section-title">MIL-STD-2525 Symbol</div>
      <div class="detail-row">
        <span class="detail-key">SIDC</span>
        <span class="detail-value" id="sidc-code-display" style="font-size:10px;letter-spacing:1px">${d.sidc}</span>
      </div>
      <div class="detail-row">
        <span class="detail-key">Identity</span>
        <span class="detail-value">
          <select id="sidc-identity" ${selectStyle}>
            ${buildSelectOptions(IDENTITY_LABELS, d.identityCode)}
          </select>
        </span>
      </div>
      <div class="detail-row">
        <span class="detail-key">Symbol Set</span>
        <span class="detail-value">
          <select id="sidc-symbolset" ${selectStyle}>
            ${buildSelectOptions(SYMBOL_SET_LABELS, d.symbolSetCode)}
          </select>
        </span>
      </div>
      <div class="detail-row">
        <span class="detail-key">Main Icon</span>
        <span class="detail-value">
          <select id="sidc-mainicon" ${selectStyle}>
            ${mainIconOpts}
          </select>
        </span>
      </div>
      <div class="detail-row">
        <span class="detail-key">Modifier 1</span>
        <span class="detail-value">
          <select id="sidc-mod1" ${selectStyle}>
            ${buildSelectOptions(m1Labels, d.mod1Code)}
          </select>
        </span>
      </div>
      <div class="detail-row">
        <span class="detail-key">Modifier 2</span>
        <span class="detail-value">
          <select id="sidc-mod2" ${selectStyle}>
            ${buildSelectOptions(m2Labels, d.mod2Code)}
          </select>
        </span>
      </div>
    </div>`;
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
