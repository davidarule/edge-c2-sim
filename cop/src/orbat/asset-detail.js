/**
 * Asset Detail/Edit Panel — right sidebar for editing a selected ORBAT unit.
 *
 * Renders an editable form with identity, SIDC, performance, altitude,
 * home base, sensors, metadata, and notes sections. Integrates with
 * the SIDC Builder modal and supports map-pick for home base coordinates.
 */

import { VALID_DOMAINS, VALID_AGENCIES, VALID_STATUSES, VALID_SENSORS, validateUnit } from './orbat-model.js';
import { openSidcBuilder } from './sidc-builder.js';
import { renderSymbol } from '../symbol-renderer.js';

// ── Known entity types (derived from sidcMap keys in config) ──

const KNOWN_ENTITY_TYPES = [
  'MMEA_PATROL', 'MMEA_FAST_INTERCEPT',
  'MIL_NAVAL', 'MIL_NAVAL_FIC', 'MIL_INFANTRY_SQUAD', 'MIL_APC', 'MIL_VEHICLE',
  'SUSPECT_VESSEL', 'HOSTILE_VESSEL',
  'CIVILIAN_CARGO', 'CIVILIAN_FISHING', 'CIVILIAN_TANKER', 'CIVILIAN_PASSENGER',
  'CIVILIAN_BOAT', 'CIVILIAN_COMMERCIAL', 'CIVILIAN_LIGHT', 'CIVILIAN_TOURIST',
  'RMP_PATROL_CAR', 'RMP_TACTICAL_TEAM', 'RMP_OFFICER', 'RMP_HELICOPTER',
  'RMAF_FIGHTER', 'RMAF_HELICOPTER', 'RMAF_TRANSPORT', 'RMAF_MPA',
  'CI_OFFICER', 'CI_IMMIGRATION_TEAM',
  'HOSTILE_PERSONNEL',
];

// ── Styles ──

const PANEL_STYLES = `
  .asset-detail-panel {
    position: absolute; top: 0; right: 0; bottom: 0;
    width: 300px; background: #0D1117;
    border-left: 1px solid #30363D;
    font-family: 'IBM Plex Sans', sans-serif;
    font-size: 12px; color: #C9D1D9;
    display: flex; flex-direction: column;
    transform: translateX(100%);
    transition: transform 0.2s ease-out;
    z-index: 500;
    overflow: hidden;
  }
  .asset-detail-panel.visible {
    transform: translateX(0);
  }

  .asset-detail-header {
    display: flex; align-items: center; gap: 10px;
    padding: 10px 12px;
    border-bottom: 1px solid #30363D;
    background: #161B22;
    flex-shrink: 0;
  }
  .asset-detail-back {
    background: none; border: none; color: #58A6FF;
    font-size: 12px; cursor: pointer; padding: 0;
    font-family: 'IBM Plex Sans', sans-serif;
    white-space: nowrap; flex-shrink: 0;
  }
  .asset-detail-back:hover { text-decoration: underline; }
  .asset-detail-symbol {
    width: 48px; height: 48px; flex-shrink: 0;
    display: flex; align-items: center; justify-content: center;
  }
  .asset-detail-symbol img { max-width: 48px; max-height: 48px; }
  .asset-detail-title {
    flex: 1; min-width: 0; overflow: hidden;
  }
  .asset-detail-callsign {
    font-size: 13px; font-weight: 600; color: #E6EDF3;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  }
  .asset-detail-type-label {
    font-size: 11px; color: #8B949E;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  }
  .asset-detail-agency-badge {
    display: inline-block; font-size: 10px; font-weight: 600;
    padding: 2px 6px; border-radius: 3px; color: #FFF;
    margin-top: 2px; text-transform: uppercase;
  }

  .asset-detail-body {
    flex: 1; overflow-y: auto; overflow-x: hidden;
    padding: 8px 12px 80px 12px;
  }

  .ad-section-title {
    font-size: 10px; text-transform: uppercase; color: #484F58;
    letter-spacing: 0.8px; margin: 12px 0 6px 0;
    padding-bottom: 3px; border-bottom: 1px solid #21262D;
  }
  .ad-section-title:first-child { margin-top: 4px; }

  .ad-field {
    display: flex; flex-direction: column; gap: 2px;
    margin-bottom: 6px;
  }
  .ad-field-row {
    display: flex; align-items: center; gap: 6px;
    margin-bottom: 6px;
  }
  .ad-label {
    font-size: 11px; color: #8B949E; flex-shrink: 0;
  }
  .ad-field-row .ad-label {
    width: 70px; text-align: right;
  }

  .ad-input, .ad-select, .ad-textarea {
    width: 100%; box-sizing: border-box;
    background: #0D1117; border: 1px solid #30363D;
    border-radius: 3px; padding: 4px 6px;
    font-size: 12px; color: #C9D1D9;
    font-family: 'IBM Plex Sans', sans-serif;
  }
  .ad-field-row .ad-input {
    flex: 1; min-width: 0;
  }
  .ad-input:focus, .ad-select:focus, .ad-textarea:focus {
    outline: none; border-color: #58A6FF;
  }
  .ad-input.invalid, .ad-select.invalid {
    border-color: #F85149;
  }
  .ad-input.invalid:focus, .ad-select.invalid:focus {
    border-color: #F85149;
  }
  .ad-error-tip {
    font-size: 10px; color: #F85149; margin-top: 1px;
  }
  .ad-textarea {
    min-height: 60px; resize: vertical;
  }
  .ad-unit-label {
    font-size: 10px; color: #484F58; flex-shrink: 0;
  }

  .ad-sidc-display {
    font-family: 'IBM Plex Mono', monospace; font-size: 11px;
    color: #58A6FF; background: #161B22;
    padding: 4px 6px; border-radius: 3px;
    border: 1px solid #30363D;
    letter-spacing: 1px; word-break: break-all;
    margin-bottom: 4px;
  }
  .ad-sidc-btn {
    background: #21262D; border: 1px solid #30363D;
    color: #C9D1D9; padding: 4px 10px; border-radius: 3px;
    font-size: 11px; cursor: pointer;
    font-family: 'IBM Plex Sans', sans-serif;
  }
  .ad-sidc-btn:hover { background: #30363D; border-color: #58A6FF; }

  .ad-checkbox-row {
    display: flex; align-items: center; gap: 6px;
    margin-bottom: 4px;
  }
  .ad-checkbox-row input[type="checkbox"] {
    accent-color: #58A6FF;
  }
  .ad-checkbox-row label {
    font-size: 12px; color: #C9D1D9; cursor: pointer;
  }

  .ad-sensor-grid {
    display: grid; grid-template-columns: 1fr 1fr;
    gap: 2px 8px;
  }

  .ad-pick-btn {
    background: #21262D; border: 1px solid #30363D;
    color: #C9D1D9; padding: 3px 8px; border-radius: 3px;
    font-size: 11px; cursor: pointer;
    font-family: 'IBM Plex Sans', sans-serif;
    flex-shrink: 0;
  }
  .ad-pick-btn:hover { background: #30363D; border-color: #58A6FF; }

  .asset-detail-footer {
    display: flex; gap: 6px; padding: 8px 12px;
    border-top: 1px solid #30363D;
    background: #161B22; flex-shrink: 0;
  }
  .ad-btn {
    flex: 1; padding: 6px 0; border-radius: 3px;
    font-size: 12px; font-weight: 500; border: none;
    cursor: pointer; font-family: 'IBM Plex Sans', sans-serif;
    text-align: center;
  }
  .ad-btn-save {
    background: #238636; color: #FFF;
  }
  .ad-btn-save:hover { background: #2EA043; }
  .ad-btn-delete {
    background: #21262D; color: #F85149; border: 1px solid #30363D;
  }
  .ad-btn-delete:hover { background: #30363D; }
  .ad-btn-duplicate {
    background: #21262D; color: #C9D1D9; border: 1px solid #30363D;
  }
  .ad-btn-duplicate:hover { background: #30363D; }
`;

// ── Inject styles once ──

let stylesInjected = false;
function injectStyles() {
  if (stylesInjected) return;
  const style = document.createElement('style');
  style.textContent = PANEL_STYLES;
  document.head.appendChild(style);
  stylesInjected = true;
}

// ── Sensor display labels ──

const SENSOR_LABELS = {
  radar: 'Radar',
  ais_receiver: 'AIS Receiver',
  eo_ir: 'EO/IR',
  esm: 'ESM',
  sonar: 'Sonar',
  adsb_receiver: 'ADS-B Receiver',
};

// ── Helper: get agency color ──

function getAgencyColor(agency, config) {
  if (config && config.agencyColors && config.agencyColors[agency]) {
    return config.agencyColors[agency];
  }
  const fallback = {
    RMP: '#1B3A8C', MMEA: '#FF6600', CI: '#2E7D32',
    RMAF: '#5C6BC0', MIL: '#4E342E', CIVILIAN: '#78909C',
  };
  return fallback[agency] || '#78909C';
}

// ── Helper: debounce ──

function debounce(fn, ms) {
  let timer = null;
  return function (...args) {
    if (timer) clearTimeout(timer);
    timer = setTimeout(() => { fn.apply(this, args); timer = null; }, ms);
  };
}

// ── Public API ──

/**
 * Initialize the Asset Detail panel.
 *
 * @param {HTMLElement} container  DOM element for the right sidebar
 * @param {Object} config         App config (agencyColors, domainLabels, etc.)
 * @returns {Object} API: { show, hide, onSave, onDelete, onDuplicate, onPickFromMap, refresh }
 */
export function initAssetDetail(container, config) {
  injectStyles();

  // State
  let currentUnit = null;
  let currentOrgId = null;
  let saveCallback = null;
  let deleteCallback = null;
  let duplicateCallback = null;
  let pickFromMapCallback = null;
  let fieldErrors = {};

  // Create panel wrapper
  const panel = document.createElement('div');
  panel.className = 'asset-detail-panel';
  container.appendChild(panel);

  // ── Debounced auto-save on blur ──

  const debouncedSave = debounce(() => {
    if (currentUnit && saveCallback) {
      saveCallback({ ...currentUnit }, currentOrgId);
    }
  }, 500);

  // ── Collect form values into unit ──

  function collectFormValues() {
    if (!currentUnit) return;

    const val = (id) => {
      const el = panel.querySelector(`#ad-${id}`);
      return el ? el.value : undefined;
    };
    const numVal = (id) => {
      const el = panel.querySelector(`#ad-${id}`);
      if (!el || el.value === '') return undefined;
      const n = parseFloat(el.value);
      return isNaN(n) ? undefined : n;
    };
    const checked = (id) => {
      const el = panel.querySelector(`#ad-${id}`);
      return el ? el.checked : false;
    };

    currentUnit.callsign = val('callsign') || currentUnit.callsign;
    currentUnit.entity_type = val('entity-type') || currentUnit.entity_type;
    currentUnit.domain = val('domain') || currentUnit.domain;
    currentUnit.agency = val('agency') || currentUnit.agency;
    currentUnit.status = val('status') || currentUnit.status;

    // Performance
    currentUnit.speed_min = numVal('speed-min');
    currentUnit.speed_max = numVal('speed-max');
    currentUnit.speed_cruise = numVal('speed-cruise');

    // Altitude (AIR only)
    if (currentUnit.domain === 'AIR') {
      currentUnit.altitude_min = numVal('alt-min');
      currentUnit.altitude_max = numVal('alt-max');
      currentUnit.altitude_cruise = numVal('alt-cruise');
    }

    // Home base
    if (!currentUnit.home_base) currentUnit.home_base = {};
    const hbName = val('hb-name');
    if (hbName !== undefined) currentUnit.home_base.name = hbName;
    const hbLat = numVal('hb-lat');
    if (hbLat !== undefined) currentUnit.home_base.lat = hbLat;
    const hbLon = numVal('hb-lon');
    if (hbLon !== undefined) currentUnit.home_base.lon = hbLon;

    // Sensors
    currentUnit.sensors = VALID_SENSORS.filter(s => checked(`sensor-${s}`));

    // Metadata
    if (!currentUnit.metadata) currentUnit.metadata = {};
    currentUnit.metadata.ais_active = checked('meta-ais-active');
    currentUnit.metadata.adsb_active = checked('meta-adsb-active');
    const metaFlag = val('meta-flag');
    if (metaFlag !== undefined) currentUnit.metadata.flag = metaFlag;
    const metaVessel = val('meta-vessel-type');
    if (metaVessel !== undefined) currentUnit.metadata.vessel_type = metaVessel;
    const metaAircraft = val('meta-aircraft-type');
    if (metaAircraft !== undefined) currentUnit.metadata.aircraft_type = metaAircraft;
    const metaMmsi = val('meta-mmsi');
    if (metaMmsi !== undefined) currentUnit.metadata.mmsi = metaMmsi;
    const metaIcao = val('meta-icao-hex');
    if (metaIcao !== undefined) currentUnit.metadata.icao_hex = metaIcao;

    // Notes
    const notes = val('notes');
    if (notes !== undefined) currentUnit.notes = notes;
  }

  // ── Validate and show errors ──

  function validateAndMark() {
    if (!currentUnit) return true;
    const result = validateUnit(currentUnit);
    fieldErrors = {};

    // Clear all error states
    panel.querySelectorAll('.ad-input.invalid, .ad-select.invalid').forEach(el => {
      el.classList.remove('invalid');
    });
    panel.querySelectorAll('.ad-error-tip').forEach(el => el.remove());

    if (result.valid) return true;

    for (const err of result.errors) {
      // Map error messages to field IDs
      let fieldId = null;
      if (err.includes('domain')) fieldId = 'ad-domain';
      else if (err.includes('agency')) fieldId = 'ad-agency';
      else if (err.includes('entity_type')) fieldId = 'ad-entity-type';
      else if (err.includes('home_base.lat')) fieldId = 'ad-hb-lat';
      else if (err.includes('home_base.lon')) fieldId = 'ad-hb-lon';
      else if (err.includes('speed_min')) fieldId = 'ad-speed-min';
      else if (err.includes('speed_max')) fieldId = 'ad-speed-max';
      else if (err.includes('speed_cruise')) fieldId = 'ad-speed-cruise';
      else if (err.includes('altitude_min')) fieldId = 'ad-alt-min';
      else if (err.includes('altitude_max')) fieldId = 'ad-alt-max';
      else if (err.includes('altitude_cruise')) fieldId = 'ad-alt-cruise';
      else if (err.includes('status')) fieldId = 'ad-status';
      else if (err.includes('sidc')) fieldId = null; // SIDC is read-only

      if (fieldId) {
        fieldErrors[fieldId] = err;
        const el = panel.querySelector(`#${fieldId}`);
        if (el) {
          el.classList.add('invalid');
          const tip = document.createElement('div');
          tip.className = 'ad-error-tip';
          tip.textContent = err;
          el.parentNode.appendChild(tip);
        }
      }
    }

    return result.valid;
  }

  // ── Field blur handler ──

  function onFieldBlur() {
    collectFormValues();
    validateAndMark();
    debouncedSave();
  }

  // ── Domain change handler (toggles altitude section) ──

  function onDomainChange() {
    collectFormValues();
    const altSection = panel.querySelector('#ad-altitude-section');
    if (altSection) {
      altSection.style.display = currentUnit.domain === 'AIR' ? '' : 'none';
    }
    validateAndMark();
    debouncedSave();
  }

  // ── Render the panel ──

  function render() {
    if (!currentUnit) {
      panel.innerHTML = '';
      return;
    }

    const unit = currentUnit;
    const meta = unit.metadata || {};
    const hb = unit.home_base || {};
    const sidc = unit.sidc || '10030000000000000000';
    const symbolUrl = renderSymbol(sidc, { size: 48 });
    const agencyColor = getAgencyColor(unit.agency, config);
    const isAir = unit.domain === 'AIR';

    // Build entity type options: combine known types with current value
    const typeOptions = new Set(KNOWN_ENTITY_TYPES);
    if (unit.entity_type) typeOptions.add(unit.entity_type);
    const sortedTypes = [...typeOptions].sort();

    panel.innerHTML = `
      <div class="asset-detail-header">
        <div style="display:flex;flex-direction:column;width:100%;">
          <button class="asset-detail-back" id="ad-back-btn">\u25C4 Back to list</button>
          <div style="display:flex;align-items:center;gap:10px;margin-top:6px;">
            <div class="asset-detail-symbol">
              <img id="ad-symbol-preview" src="${symbolUrl}" alt="symbol">
            </div>
            <div class="asset-detail-title">
              <div class="asset-detail-callsign">${unit.callsign || unit.id}</div>
              <div class="asset-detail-type-label">${(unit.entity_type || '').replace(/_/g, ' ')}</div>
              <span class="asset-detail-agency-badge" style="background:${agencyColor}">${unit.agency || 'UNKNOWN'}</span>
            </div>
          </div>
        </div>
      </div>

      <div class="asset-detail-body">

        <!-- Identity -->
        <div class="ad-section-title">Identity</div>

        <div class="ad-field">
          <label class="ad-label">Callsign</label>
          <input class="ad-input" id="ad-callsign" type="text" value="${escAttr(unit.callsign || '')}">
        </div>

        <div class="ad-field">
          <label class="ad-label">Entity Type</label>
          <select class="ad-select" id="ad-entity-type">
            ${sortedTypes.map(t => `<option value="${t}" ${t === unit.entity_type ? 'selected' : ''}>${t.replace(/_/g, ' ')}</option>`).join('')}
          </select>
        </div>

        <div class="ad-field">
          <label class="ad-label">Domain</label>
          <select class="ad-select" id="ad-domain">
            ${VALID_DOMAINS.map(d => `<option value="${d}" ${d === unit.domain ? 'selected' : ''}>${d}</option>`).join('')}
          </select>
        </div>

        <div class="ad-field">
          <label class="ad-label">Agency</label>
          <select class="ad-select" id="ad-agency">
            ${VALID_AGENCIES.map(a => `<option value="${a}" ${a === unit.agency ? 'selected' : ''}>${a}</option>`).join('')}
          </select>
        </div>

        <div class="ad-field">
          <label class="ad-label">Status</label>
          <select class="ad-select" id="ad-status">
            ${VALID_STATUSES.map(s => `<option value="${s}" ${s === unit.status ? 'selected' : ''}>${s}</option>`).join('')}
          </select>
        </div>

        <!-- SIDC -->
        <div class="ad-section-title">SIDC</div>
        <div class="ad-sidc-display" id="ad-sidc-display">${sidc}</div>
        <button class="ad-sidc-btn" id="ad-sidc-open-btn">Open SIDC Builder</button>

        <!-- Performance -->
        <div class="ad-section-title">Performance</div>
        <div class="ad-field-row">
          <label class="ad-label">Speed Min</label>
          <input class="ad-input" id="ad-speed-min" type="number" min="0" step="0.1"
            value="${unit.speed_min != null ? unit.speed_min : ''}">
          <span class="ad-unit-label">kts</span>
        </div>
        <div class="ad-field-row">
          <label class="ad-label">Speed Max</label>
          <input class="ad-input" id="ad-speed-max" type="number" min="0" step="0.1"
            value="${unit.speed_max != null ? unit.speed_max : ''}">
          <span class="ad-unit-label">kts</span>
        </div>
        <div class="ad-field-row">
          <label class="ad-label">Speed Cruise</label>
          <input class="ad-input" id="ad-speed-cruise" type="number" min="0" step="0.1"
            value="${unit.speed_cruise != null ? unit.speed_cruise : ''}">
          <span class="ad-unit-label">kts</span>
        </div>

        <!-- Altitude (AIR only) -->
        <div id="ad-altitude-section" style="${isAir ? '' : 'display:none'}">
          <div class="ad-section-title">Altitude</div>
          <div class="ad-field-row">
            <label class="ad-label">Alt Min</label>
            <input class="ad-input" id="ad-alt-min" type="number" min="0" step="100"
              value="${unit.altitude_min != null ? unit.altitude_min : ''}">
            <span class="ad-unit-label">ft</span>
          </div>
          <div class="ad-field-row">
            <label class="ad-label">Alt Max</label>
            <input class="ad-input" id="ad-alt-max" type="number" min="0" step="100"
              value="${unit.altitude_max != null ? unit.altitude_max : ''}">
            <span class="ad-unit-label">ft</span>
          </div>
          <div class="ad-field-row">
            <label class="ad-label">Alt Cruise</label>
            <input class="ad-input" id="ad-alt-cruise" type="number" min="0" step="100"
              value="${unit.altitude_cruise != null ? unit.altitude_cruise : ''}">
            <span class="ad-unit-label">ft</span>
          </div>
        </div>

        <!-- Home Base -->
        <div class="ad-section-title">Home Base</div>
        <div class="ad-field">
          <label class="ad-label">Name</label>
          <input class="ad-input" id="ad-hb-name" type="text" value="${escAttr(hb.name || '')}">
        </div>
        <div class="ad-field-row">
          <label class="ad-label">Lat</label>
          <input class="ad-input" id="ad-hb-lat" type="number" min="-90" max="90" step="0.0001"
            value="${hb.lat != null ? hb.lat : ''}">
        </div>
        <div class="ad-field-row">
          <label class="ad-label">Lon</label>
          <input class="ad-input" id="ad-hb-lon" type="number" min="-180" max="180" step="0.0001"
            value="${hb.lon != null ? hb.lon : ''}">
          <button class="ad-pick-btn" id="ad-pick-map-btn">Pick from Map</button>
        </div>

        <!-- Sensors -->
        <div class="ad-section-title">Sensors</div>
        <div class="ad-sensor-grid">
          ${VALID_SENSORS.map(s => `
            <div class="ad-checkbox-row">
              <input type="checkbox" id="ad-sensor-${s}" ${(unit.sensors || []).includes(s) ? 'checked' : ''}>
              <label for="ad-sensor-${s}">${SENSOR_LABELS[s] || s}</label>
            </div>
          `).join('')}
        </div>

        <!-- Metadata -->
        <div class="ad-section-title">Metadata</div>
        <div class="ad-checkbox-row">
          <input type="checkbox" id="ad-meta-ais-active" ${meta.ais_active ? 'checked' : ''}>
          <label for="ad-meta-ais-active">AIS Active</label>
        </div>
        <div class="ad-checkbox-row">
          <input type="checkbox" id="ad-meta-adsb-active" ${meta.adsb_active ? 'checked' : ''}>
          <label for="ad-meta-adsb-active">ADSB Active</label>
        </div>
        <div class="ad-field">
          <label class="ad-label">Flag</label>
          <input class="ad-input" id="ad-meta-flag" type="text" value="${escAttr(meta.flag || '')}">
        </div>
        <div class="ad-field">
          <label class="ad-label">Vessel Type</label>
          <input class="ad-input" id="ad-meta-vessel-type" type="text" value="${escAttr(meta.vessel_type || '')}">
        </div>
        <div class="ad-field">
          <label class="ad-label">Aircraft Type</label>
          <input class="ad-input" id="ad-meta-aircraft-type" type="text" value="${escAttr(meta.aircraft_type || '')}">
        </div>
        <div class="ad-field">
          <label class="ad-label">MMSI</label>
          <input class="ad-input" id="ad-meta-mmsi" type="text" value="${escAttr(meta.mmsi || '')}">
        </div>
        <div class="ad-field">
          <label class="ad-label">ICAO Hex</label>
          <input class="ad-input" id="ad-meta-icao-hex" type="text" value="${escAttr(meta.icao_hex || '')}">
        </div>

        <!-- Notes -->
        <div class="ad-section-title">Notes</div>
        <textarea class="ad-textarea" id="ad-notes">${escHtml(unit.notes || '')}</textarea>

      </div>

      <div class="asset-detail-footer">
        <button class="ad-btn ad-btn-save" id="ad-btn-save">Save</button>
        <button class="ad-btn ad-btn-delete" id="ad-btn-delete">Delete</button>
        <button class="ad-btn ad-btn-duplicate" id="ad-btn-duplicate">Duplicate</button>
      </div>
    `;

    wireEvents();
  }

  // ── Wire DOM events ──

  function wireEvents() {
    // Back button
    const backBtn = panel.querySelector('#ad-back-btn');
    if (backBtn) {
      backBtn.addEventListener('click', () => hide());
    }

    // All text/number inputs: blur -> collect + validate + auto-save
    panel.querySelectorAll('.ad-input, .ad-textarea').forEach(el => {
      el.addEventListener('blur', onFieldBlur);
    });

    // All selects: change -> collect + validate + auto-save
    panel.querySelectorAll('.ad-select').forEach(el => {
      el.addEventListener('change', () => {
        // Special handling for domain change
        if (el.id === 'ad-domain') {
          onDomainChange();
        } else {
          onFieldBlur();
        }
      });
    });

    // Sensor checkboxes: change -> collect + auto-save
    VALID_SENSORS.forEach(s => {
      const cb = panel.querySelector(`#ad-sensor-${s}`);
      if (cb) cb.addEventListener('change', onFieldBlur);
    });

    // Metadata checkboxes
    const aisCb = panel.querySelector('#ad-meta-ais-active');
    if (aisCb) aisCb.addEventListener('change', onFieldBlur);
    const adsbCb = panel.querySelector('#ad-meta-adsb-active');
    if (adsbCb) adsbCb.addEventListener('change', onFieldBlur);

    // SIDC Builder button
    const sidcBtn = panel.querySelector('#ad-sidc-open-btn');
    if (sidcBtn) {
      sidcBtn.addEventListener('click', () => {
        const currentSidc = currentUnit.sidc || '10030000000000000000';
        openSidcBuilder(currentSidc, (newSidc) => {
          currentUnit.sidc = newSidc;
          // Update preview and display
          const display = panel.querySelector('#ad-sidc-display');
          if (display) display.textContent = newSidc;
          const previewImg = panel.querySelector('#ad-symbol-preview');
          if (previewImg) previewImg.src = renderSymbol(newSidc, { size: 48 });
          debouncedSave();
        });
      });
    }

    // Pick from Map
    const pickBtn = panel.querySelector('#ad-pick-map-btn');
    if (pickBtn) {
      pickBtn.addEventListener('click', () => {
        if (!pickFromMapCallback) return;
        pickBtn.textContent = 'Click map...';
        pickBtn.disabled = true;
        pickFromMapCallback((coords) => {
          if (coords && coords.lat != null && coords.lon != null) {
            const latInput = panel.querySelector('#ad-hb-lat');
            const lonInput = panel.querySelector('#ad-hb-lon');
            if (latInput) latInput.value = coords.lat.toFixed(4);
            if (lonInput) lonInput.value = coords.lon.toFixed(4);
            collectFormValues();
            debouncedSave();
          }
          pickBtn.textContent = 'Pick from Map';
          pickBtn.disabled = false;
        });
      });
    }

    // Save button
    const saveBtn = panel.querySelector('#ad-btn-save');
    if (saveBtn) {
      saveBtn.addEventListener('click', () => {
        collectFormValues();
        const valid = validateAndMark();
        if (valid && saveCallback) {
          saveCallback({ ...currentUnit }, currentOrgId);
        }
      });
    }

    // Delete button
    const deleteBtn = panel.querySelector('#ad-btn-delete');
    if (deleteBtn) {
      deleteBtn.addEventListener('click', () => {
        if (!currentUnit) return;
        const name = currentUnit.callsign || currentUnit.id;
        const confirmed = window.confirm(`Delete asset "${name}"? This cannot be undone.`);
        if (confirmed && deleteCallback) {
          deleteCallback(currentUnit.id, currentOrgId);
          hide();
        }
      });
    }

    // Duplicate button
    const dupBtn = panel.querySelector('#ad-btn-duplicate');
    if (dupBtn) {
      dupBtn.addEventListener('click', () => {
        if (!currentUnit || !duplicateCallback) return;
        collectFormValues();
        const copy = JSON.parse(JSON.stringify(currentUnit));
        copy.id = currentUnit.id + '_copy';
        copy.callsign = (copy.callsign || copy.id) + ' (Copy)';
        duplicateCallback(copy, currentOrgId);
      });
    }

    // Update callsign display on input
    const callsignInput = panel.querySelector('#ad-callsign');
    if (callsignInput) {
      callsignInput.addEventListener('input', () => {
        const display = panel.querySelector('.asset-detail-callsign');
        if (display) display.textContent = callsignInput.value || currentUnit.id;
      });
    }

    // Update type label on change
    const typeSelect = panel.querySelector('#ad-entity-type');
    if (typeSelect) {
      typeSelect.addEventListener('change', () => {
        const display = panel.querySelector('.asset-detail-type-label');
        if (display) display.textContent = (typeSelect.value || '').replace(/_/g, ' ');
      });
    }

    // Update agency badge on change
    const agencySelect = panel.querySelector('#ad-agency');
    if (agencySelect) {
      agencySelect.addEventListener('change', () => {
        const badge = panel.querySelector('.asset-detail-agency-badge');
        if (badge) {
          badge.textContent = agencySelect.value;
          badge.style.background = getAgencyColor(agencySelect.value, config);
        }
      });
    }
  }

  // ── Public methods ──

  function show(unit, orgId) {
    currentUnit = JSON.parse(JSON.stringify(unit)); // deep copy for editing
    currentOrgId = orgId;
    fieldErrors = {};
    render();
    // Slide in
    requestAnimationFrame(() => {
      panel.classList.add('visible');
    });
  }

  function hide() {
    panel.classList.remove('visible');
    currentUnit = null;
    currentOrgId = null;
    fieldErrors = {};
    // Clear content after transition
    setTimeout(() => {
      if (!currentUnit) panel.innerHTML = '';
    }, 250);
  }

  function refresh() {
    if (currentUnit) {
      render();
    }
  }

  // Escape key closes panel
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && currentUnit) {
      hide();
    }
  });

  return {
    show,
    hide,
    onSave(callback) { saveCallback = callback; },
    onDelete(callback) { deleteCallback = callback; },
    onDuplicate(callback) { duplicateCallback = callback; },
    onPickFromMap(callback) { pickFromMapCallback = callback; },
    refresh,
  };
}

// ── HTML/attribute escaping ──

function escAttr(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/"/g, '&quot;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

function escHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}
