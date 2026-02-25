/**
 * Event Editor — modal dialog for creating and editing scenario events.
 *
 * Events are timed triggers that drive the scenario narrative: detections,
 * orders, intercepts, boarding actions, alerts, and resolutions.
 *
 * Uses the same dark theme and patterns as sidc-builder.js.
 */

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

export const EVENT_TYPES = [
  'detection', 'communication', 'status_change', 'movement',
  'engagement', 'intel', 'alert', 'environmental',
];

export const SEVERITY_LEVELS = ['info', 'warning', 'critical'];

export const ACTION_TYPES = [
  'intercept', 'patrol', 'search', 'move_to', 'rtb', 'hold',
  'broadcast', 'ais_dark', 'ais_restore',
];

const AGENCIES = ['RMP', 'MMEA', 'CI', 'RMAF', 'MIL'];

const TIME_RE = /^\d{2,}:\d{2}$/;

// Map action types to the extra parameter fields they require.
const ACTION_PARAMS = {
  intercept:   ['intercept_target'],
  move_to:     ['destination'],
  search:      ['search_area'],
  broadcast:   ['message'],
  patrol:      ['patrol_area'],
  rtb:         [],
  hold:        [],
  ais_dark:    [],
  ais_restore: [],
};

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const MODAL_STYLES = `
  .evt-overlay {
    position: fixed; top: 0; left: 0; right: 0; bottom: 0;
    background: rgba(0,0,0,0.6); z-index: 10000;
    display: flex; align-items: center; justify-content: center;
    font-family: 'IBM Plex Sans', sans-serif;
  }
  .evt-modal {
    background: #161B22; border: 1px solid #30363D; border-radius: 6px;
    width: 560px; max-height: 90vh; display: flex; flex-direction: column;
    color: #C9D1D9; box-shadow: 0 8px 32px rgba(0,0,0,0.5);
  }
  .evt-modal-header {
    display: flex; justify-content: space-between; align-items: center;
    padding: 12px 16px; border-bottom: 1px solid #30363D; flex-shrink: 0;
  }
  .evt-modal-header h3 {
    margin: 0; font-size: 14px; font-weight: 600; letter-spacing: 0.5px;
    text-transform: uppercase; color: #E6EDF3;
  }
  .evt-modal-close {
    background: none; border: none; color: #8B949E; font-size: 18px;
    cursor: pointer; padding: 0 4px; line-height: 1;
  }
  .evt-modal-close:hover { color: #F85149; }
  .evt-modal-body {
    flex: 1; overflow-y: auto; padding: 16px; display: flex;
    flex-direction: column; gap: 12px;
  }
  .evt-modal-body::-webkit-scrollbar { width: 6px; }
  .evt-modal-body::-webkit-scrollbar-track { background: transparent; }
  .evt-modal-body::-webkit-scrollbar-thumb { background: #30363D; border-radius: 3px; }

  /* Form rows */
  .evt-row {
    display: flex; align-items: center; gap: 8px;
  }
  .evt-row label {
    width: 80px; font-size: 11px; color: #8B949E; flex-shrink: 0;
    text-align: right;
  }
  .evt-row select, .evt-row input, .evt-row textarea {
    flex: 1; padding: 5px 8px; font-size: 12px;
    background: #0D1117; border: 1px solid #30363D; border-radius: 3px;
    color: #C9D1D9; font-family: 'IBM Plex Sans', sans-serif;
  }
  .evt-row select:focus, .evt-row input:focus, .evt-row textarea:focus {
    outline: none; border-color: #58A6FF;
  }
  .evt-row textarea {
    resize: vertical; min-height: 48px;
  }
  .evt-row .evt-time-hint {
    font-size: 10px; color: #484F58; flex-shrink: 0;
  }

  /* Section labels */
  .evt-section {
    display: flex; align-items: center; gap: 8px;
    margin-top: 4px;
  }
  .evt-section-label {
    font-size: 10px; color: #484F58; text-transform: uppercase;
    letter-spacing: 0.8px; white-space: nowrap;
  }
  .evt-section-line {
    flex: 1; height: 1px; background: #21262D;
  }
  .evt-section-btn {
    background: none; border: 1px solid #30363D; color: #58A6FF;
    font-size: 11px; padding: 2px 8px; border-radius: 3px; cursor: pointer;
    font-family: 'IBM Plex Sans', sans-serif; white-space: nowrap;
  }
  .evt-section-btn:hover { background: rgba(88,166,255,0.1); }

  /* Target list */
  .evt-target-list {
    display: flex; flex-direction: column; gap: 4px;
    margin-left: 88px;
  }
  .evt-target-item {
    display: flex; align-items: center; gap: 6px;
    padding: 3px 8px; background: #0D1117; border: 1px solid #30363D;
    border-radius: 3px; font-size: 12px;
  }
  .evt-target-item .evt-target-label {
    flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  }
  .evt-target-item .evt-target-id {
    color: #58A6FF; font-family: 'IBM Plex Mono', monospace; font-size: 11px;
  }
  .evt-target-item .evt-target-name {
    color: #8B949E; margin-left: 6px;
  }
  .evt-target-remove {
    background: none; border: none; color: #484F58; font-size: 14px;
    cursor: pointer; padding: 0 2px; line-height: 1; flex-shrink: 0;
  }
  .evt-target-remove:hover { color: #F85149; }

  /* Action cards */
  .evt-action-list {
    display: flex; flex-direction: column; gap: 8px;
    margin-left: 88px;
  }
  .evt-action-card {
    background: #0D1117; border: 1px solid #30363D; border-radius: 4px;
    padding: 8px 10px; display: flex; flex-direction: column; gap: 6px;
  }
  .evt-action-card-header {
    display: flex; align-items: center; gap: 8px;
  }
  .evt-action-card-header label {
    width: 56px; font-size: 11px; color: #8B949E; text-align: right;
    flex-shrink: 0;
  }
  .evt-action-card-header select, .evt-action-card-header input,
  .evt-action-card-header textarea {
    flex: 1; padding: 4px 6px; font-size: 12px;
    background: #161B22; border: 1px solid #30363D; border-radius: 3px;
    color: #C9D1D9; font-family: 'IBM Plex Sans', sans-serif;
  }
  .evt-action-card-header select:focus, .evt-action-card-header input:focus,
  .evt-action-card-header textarea:focus {
    outline: none; border-color: #58A6FF;
  }
  .evt-action-card-header textarea {
    resize: vertical; min-height: 36px;
  }
  .evt-action-remove {
    background: none; border: 1px solid #30363D; color: #8B949E;
    font-size: 11px; padding: 2px 8px; border-radius: 3px; cursor: pointer;
    font-family: 'IBM Plex Sans', sans-serif; flex-shrink: 0;
  }
  .evt-action-remove:hover { color: #F85149; border-color: #F85149; }

  /* Agency checkboxes */
  .evt-agency-row {
    display: flex; align-items: center; gap: 10px;
    margin-left: 88px; flex-wrap: wrap;
  }
  .evt-agency-label {
    display: flex; align-items: center; gap: 4px;
    font-size: 12px; cursor: pointer; color: #C9D1D9;
  }
  .evt-agency-label input[type="checkbox"] {
    accent-color: #58A6FF; cursor: pointer;
  }

  /* Position row */
  .evt-pos-row {
    display: flex; align-items: center; gap: 8px;
    margin-left: 88px;
  }
  .evt-pos-row label {
    width: auto; font-size: 11px; color: #8B949E; flex-shrink: 0;
  }
  .evt-pos-row input {
    width: 100px; padding: 4px 6px; font-size: 12px;
    background: #0D1117; border: 1px solid #30363D; border-radius: 3px;
    color: #C9D1D9; font-family: 'IBM Plex Sans', sans-serif;
  }
  .evt-pos-row input:focus { outline: none; border-color: #58A6FF; }
  .evt-pos-pick {
    background: none; border: 1px solid #30363D; color: #58A6FF;
    font-size: 11px; padding: 3px 8px; border-radius: 3px; cursor: pointer;
    font-family: 'IBM Plex Sans', sans-serif; white-space: nowrap;
  }
  .evt-pos-pick:hover { background: rgba(88,166,255,0.1); }
  .evt-pos-pick.active {
    background: rgba(88,166,255,0.2); border-color: #58A6FF;
    color: #FFF;
  }

  /* Footer */
  .evt-modal-footer {
    display: flex; justify-content: space-between; align-items: center;
    padding: 12px 16px; border-top: 1px solid #30363D; flex-shrink: 0;
  }
  .evt-btn {
    padding: 6px 16px; border-radius: 3px; font-size: 12px;
    font-family: 'IBM Plex Sans', sans-serif; cursor: pointer; border: none;
  }
  .evt-btn-primary {
    background: #238636; color: #FFF;
  }
  .evt-btn-primary:hover { background: #2EA043; }
  .evt-btn-secondary {
    background: #21262D; color: #C9D1D9; border: 1px solid #30363D;
  }
  .evt-btn-secondary:hover { background: #30363D; }

  /* Validation error */
  .evt-error {
    color: #F85149; font-size: 11px; padding: 0 16px 0 88px;
    margin-top: -6px;
  }

  /* Add target dropdown row */
  .evt-add-target-row {
    display: flex; align-items: center; gap: 6px;
    margin-left: 88px;
  }
  .evt-add-target-row select {
    flex: 1; padding: 4px 6px; font-size: 12px;
    background: #0D1117; border: 1px solid #30363D; border-radius: 3px;
    color: #C9D1D9;
  }
  .evt-add-target-row select:focus { outline: none; border-color: #58A6FF; }
`;

// ---------------------------------------------------------------------------
// Style injection
// ---------------------------------------------------------------------------

let stylesInjected = false;

function injectStyles() {
  if (stylesInjected) return;
  const style = document.createElement('style');
  style.textContent = MODAL_STYLES;
  document.head.appendChild(style);
  stylesInjected = true;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Build an <option> list from an array of strings.
 */
function optionsFromArray(arr, selected) {
  return arr.map(v =>
    `<option value="${v}" ${v === selected ? 'selected' : ''}>${v}</option>`
  ).join('');
}

/**
 * Build an entity dropdown option list.
 * Each entity should have at least { id, callsign }.
 */
function entityOptions(entities, selected) {
  let html = '<option value="">-- select --</option>';
  for (const e of entities) {
    const label = e.callsign ? `${e.id} - ${e.callsign}` : e.id;
    const sel = e.id === selected ? 'selected' : '';
    html += `<option value="${e.id}" ${sel}>${label}</option>`;
  }
  return html;
}

/**
 * Deep clone a plain object.
 */
function clone(obj) {
  if (obj == null) return null;
  return JSON.parse(JSON.stringify(obj));
}

/**
 * Validate MM:SS time format.
 */
function isValidTime(t) {
  if (!t || typeof t !== 'string') return false;
  if (!TIME_RE.test(t)) return false;
  const parts = t.split(':');
  const ss = parseInt(parts[1], 10);
  return ss < 60;
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Open the Event Editor modal.
 *
 * @param {Object|null} event           Existing event to edit, or null for new
 * @param {Array}       scenarioEntities Array of entities with { id, callsign, ... }
 * @param {Function}    onSave          Callback: (eventObject) => void
 * @param {Function}    [onCancel]      Optional callback on cancel/close
 */
export function openEventEditor(event, scenarioEntities, onSave, onCancel) {
  injectStyles();

  const entities = scenarioEntities || [];
  const isNew = !event;

  // Working copy of the event state
  const state = {
    time: '',
    type: EVENT_TYPES[0],
    severity: SEVERITY_LEVELS[0],
    description: '',
    targets: [],
    actions: [],
    alert_agencies: [],
    position: null,
  };

  // Populate from existing event
  if (event) {
    state.time = event.time || '';
    state.type = event.type || EVENT_TYPES[0];
    state.severity = event.severity || SEVERITY_LEVELS[0];
    state.description = event.description || '';
    state.targets = Array.isArray(event.targets) ? [...event.targets] : [];
    state.actions = Array.isArray(event.actions) ? clone(event.actions) : [];
    state.alert_agencies = Array.isArray(event.alert_agencies) ? [...event.alert_agencies] : [];
    state.position = event.position ? clone(event.position) : null;
  }

  // Track map-pick mode
  let pickingPosition = false;
  let pickCallback = null;

  // ── Create DOM ──

  const overlay = document.createElement('div');
  overlay.className = 'evt-overlay';

  function render() {
    overlay.innerHTML = `
      <div class="evt-modal">
        <div class="evt-modal-header">
          <h3>${isNew ? 'New Event' : 'Edit Event'}</h3>
          <button class="evt-modal-close" title="Close">\u2715</button>
        </div>
        <div class="evt-modal-body">

          <!-- Time -->
          <div class="evt-row">
            <label>Time</label>
            <input type="text" id="evt-time" value="${escapeAttr(state.time)}"
                   placeholder="05:00" maxlength="8">
            <span class="evt-time-hint">(MM:SS)</span>
          </div>
          <div class="evt-error" id="evt-time-error" style="display:none;"></div>

          <!-- Type -->
          <div class="evt-row">
            <label>Type</label>
            <select id="evt-type">${optionsFromArray(EVENT_TYPES, state.type)}</select>
          </div>

          <!-- Severity -->
          <div class="evt-row">
            <label>Severity</label>
            <select id="evt-severity">${optionsFromArray(SEVERITY_LEVELS, state.severity)}</select>
          </div>

          <!-- Description -->
          <div class="evt-row">
            <label>Description</label>
            <textarea id="evt-desc" rows="2" placeholder="Event description...">${escapeHTML(state.description)}</textarea>
          </div>

          <!-- Target Entities -->
          <div class="evt-section">
            <span class="evt-section-label">Target Entities</span>
            <span class="evt-section-line"></span>
            <button class="evt-section-btn" id="evt-add-target-btn">+ Add Target</button>
          </div>
          <div id="evt-add-target-container" style="display:none;">
            <div class="evt-add-target-row">
              <select id="evt-target-select">${entityOptions(entities.filter(e => !state.targets.includes(e.id)), '')}</select>
              <button class="evt-section-btn" id="evt-confirm-target">Add</button>
            </div>
          </div>
          <div class="evt-target-list" id="evt-target-list">
            ${renderTargets()}
          </div>

          <!-- Actions -->
          <div class="evt-section">
            <span class="evt-section-label">Actions</span>
            <span class="evt-section-line"></span>
            <button class="evt-section-btn" id="evt-add-action-btn">+ Add Action</button>
          </div>
          <div class="evt-action-list" id="evt-action-list">
            ${renderActions()}
          </div>

          <!-- Alert Agencies -->
          <div class="evt-section">
            <span class="evt-section-label">Alert Agencies</span>
            <span class="evt-section-line"></span>
          </div>
          <div class="evt-agency-row">
            ${AGENCIES.map(a => `
              <label class="evt-agency-label">
                <input type="checkbox" data-agency="${a}"
                       ${state.alert_agencies.includes(a) ? 'checked' : ''}>
                ${a}
              </label>
            `).join('')}
          </div>

          <!-- Position -->
          <div class="evt-section">
            <span class="evt-section-label">Position (optional)</span>
            <span class="evt-section-line"></span>
          </div>
          <div class="evt-pos-row">
            <label>Lat:</label>
            <input type="text" id="evt-pos-lat" placeholder="e.g. 5.80"
                   value="${state.position ? state.position.latitude : ''}">
            <label>Lon:</label>
            <input type="text" id="evt-pos-lon" placeholder="e.g. 118.88"
                   value="${state.position ? state.position.longitude : ''}">
            <button class="evt-pos-pick ${pickingPosition ? 'active' : ''}"
                    id="evt-pos-pick" title="Click on map to set position">Pick from Map</button>
          </div>

        </div>
        <div class="evt-modal-footer">
          <button class="evt-btn evt-btn-secondary" id="evt-cancel">Cancel</button>
          <button class="evt-btn evt-btn-primary" id="evt-save">Save Event</button>
        </div>
      </div>
    `;
  }

  function renderTargets() {
    if (state.targets.length === 0) return '';
    return state.targets.map((tid, i) => {
      const ent = entities.find(e => e.id === tid);
      const name = ent && ent.callsign ? ent.callsign : '';
      return `
        <div class="evt-target-item">
          <div class="evt-target-label">
            <span class="evt-target-id">${escapeHTML(tid)}</span>
            ${name ? `<span class="evt-target-name">${escapeHTML(name)}</span>` : ''}
          </div>
          <button class="evt-target-remove" data-target-idx="${i}" title="Remove">\u2715</button>
        </div>
      `;
    }).join('');
  }

  function renderActions() {
    if (state.actions.length === 0) return '';
    return state.actions.map((act, i) => {
      const actionType = act.action || ACTION_TYPES[0];
      const params = ACTION_PARAMS[actionType] || [];
      let paramsHTML = '';

      for (const param of params) {
        paramsHTML += renderActionParam(param, act, i);
      }

      return `
        <div class="evt-action-card" data-action-idx="${i}">
          <div class="evt-action-card-header">
            <label>Action</label>
            <select class="evt-action-type" data-action-idx="${i}">
              ${optionsFromArray(ACTION_TYPES, actionType)}
            </select>
            <button class="evt-action-remove" data-action-idx="${i}">Remove</button>
          </div>
          ${paramsHTML}
        </div>
      `;
    }).join('');
  }

  function renderActionParam(param, action, actionIdx) {
    if (param === 'intercept_target') {
      return `
        <div class="evt-action-card-header">
          <label>Target</label>
          <select class="evt-action-param" data-action-idx="${actionIdx}" data-param="intercept_target">
            ${entityOptions(entities, action.intercept_target || '')}
          </select>
        </div>
      `;
    }
    if (param === 'destination') {
      const dest = action.destination || {};
      const lat = dest.latitude != null ? dest.latitude : (dest.lat != null ? dest.lat : '');
      const lon = dest.longitude != null ? dest.longitude : (dest.lon != null ? dest.lon : '');
      return `
        <div class="evt-action-card-header">
          <label>Dest Lat</label>
          <input type="text" class="evt-action-param" data-action-idx="${actionIdx}"
                 data-param="dest_lat" value="${lat}" placeholder="Latitude">
        </div>
        <div class="evt-action-card-header">
          <label>Dest Lon</label>
          <input type="text" class="evt-action-param" data-action-idx="${actionIdx}"
                 data-param="dest_lon" value="${lon}" placeholder="Longitude">
        </div>
      `;
    }
    if (param === 'search_area') {
      return `
        <div class="evt-action-card-header">
          <label>Area</label>
          <input type="text" class="evt-action-param" data-action-idx="${actionIdx}"
                 data-param="search_area" value="${escapeAttr(action.search_area || action.area || '')}"
                 placeholder="Area polygon ID or entity ID">
        </div>
      `;
    }
    if (param === 'message') {
      return `
        <div class="evt-action-card-header">
          <label>Message</label>
          <textarea class="evt-action-param" data-action-idx="${actionIdx}"
                    data-param="message" rows="2"
                    placeholder="Broadcast message...">${escapeHTML(action.message || '')}</textarea>
        </div>
      `;
    }
    if (param === 'patrol_area') {
      return `
        <div class="evt-action-card-header">
          <label>Area</label>
          <input type="text" class="evt-action-param" data-action-idx="${actionIdx}"
                 data-param="patrol_area" value="${escapeAttr(action.patrol_area || '')}"
                 placeholder="Patrol area polygon ID">
        </div>
      `;
    }
    return '';
  }

  // ── Initial render and attach ──

  render();
  document.body.appendChild(overlay);

  // ── Wire events ──

  function wireEvents() {
    const modal = overlay.querySelector('.evt-modal');
    if (!modal) return;

    // Close button
    modal.querySelector('.evt-modal-close').addEventListener('click', doCancel);

    // Cancel button
    modal.querySelector('#evt-cancel').addEventListener('click', doCancel);

    // Save button
    modal.querySelector('#evt-save').addEventListener('click', doSave);

    // Backdrop click
    overlay.addEventListener('click', (e) => {
      if (e.target === overlay) doCancel();
    });

    // Time input
    const timeInput = modal.querySelector('#evt-time');
    timeInput.addEventListener('input', () => {
      state.time = timeInput.value.trim();
      clearTimeError();
    });

    // Type select
    const typeSelect = modal.querySelector('#evt-type');
    typeSelect.addEventListener('change', () => {
      state.type = typeSelect.value;
    });

    // Severity select
    const sevSelect = modal.querySelector('#evt-severity');
    sevSelect.addEventListener('change', () => {
      state.severity = sevSelect.value;
    });

    // Description textarea
    const descArea = modal.querySelector('#evt-desc');
    descArea.addEventListener('input', () => {
      state.description = descArea.value;
    });

    // Add target toggle
    const addTargetBtn = modal.querySelector('#evt-add-target-btn');
    const addTargetContainer = modal.querySelector('#evt-add-target-container');
    addTargetBtn.addEventListener('click', () => {
      const showing = addTargetContainer.style.display !== 'none';
      addTargetContainer.style.display = showing ? 'none' : 'block';
      if (!showing) {
        // Refresh the select options (exclude already-added targets)
        const sel = addTargetContainer.querySelector('#evt-target-select');
        sel.innerHTML = entityOptions(
          entities.filter(e => !state.targets.includes(e.id)), ''
        );
      }
    });

    // Confirm add target
    const confirmTargetBtn = modal.querySelector('#evt-confirm-target');
    if (confirmTargetBtn) {
      confirmTargetBtn.addEventListener('click', () => {
        const sel = modal.querySelector('#evt-target-select');
        const val = sel.value;
        if (val && !state.targets.includes(val)) {
          state.targets.push(val);
          reRender();
        }
      });
    }

    // Remove target buttons
    modal.querySelectorAll('.evt-target-remove').forEach(btn => {
      btn.addEventListener('click', () => {
        const idx = parseInt(btn.dataset.targetIdx, 10);
        state.targets.splice(idx, 1);
        reRender();
      });
    });

    // Add action button
    const addActionBtn = modal.querySelector('#evt-add-action-btn');
    addActionBtn.addEventListener('click', () => {
      state.actions.push({ action: ACTION_TYPES[0] });
      reRender();
    });

    // Action type selects
    modal.querySelectorAll('.evt-action-type').forEach(sel => {
      sel.addEventListener('change', () => {
        const idx = parseInt(sel.dataset.actionIdx, 10);
        const newType = sel.value;
        // Preserve the action entry but reset params
        state.actions[idx] = { action: newType };
        reRender();
      });
    });

    // Action remove buttons
    modal.querySelectorAll('.evt-action-remove').forEach(btn => {
      btn.addEventListener('click', () => {
        const idx = parseInt(btn.dataset.actionIdx, 10);
        state.actions.splice(idx, 1);
        reRender();
      });
    });

    // Action param inputs
    modal.querySelectorAll('.evt-action-param').forEach(el => {
      const idx = parseInt(el.dataset.actionIdx, 10);
      const param = el.dataset.param;
      const evtType = el.tagName === 'SELECT' ? 'change' : 'input';
      el.addEventListener(evtType, () => {
        syncActionParam(idx, param, el.value);
      });
    });

    // Agency checkboxes
    modal.querySelectorAll('[data-agency]').forEach(cb => {
      cb.addEventListener('change', () => {
        const agency = cb.dataset.agency;
        if (cb.checked) {
          if (!state.alert_agencies.includes(agency)) {
            state.alert_agencies.push(agency);
          }
        } else {
          state.alert_agencies = state.alert_agencies.filter(a => a !== agency);
        }
      });
    });

    // Position inputs
    const posLat = modal.querySelector('#evt-pos-lat');
    const posLon = modal.querySelector('#evt-pos-lon');
    posLat.addEventListener('input', () => syncPosition(posLat.value, posLon.value));
    posLon.addEventListener('input', () => syncPosition(posLat.value, posLon.value));

    // Pick from map button
    const pickBtn = modal.querySelector('#evt-pos-pick');
    pickBtn.addEventListener('click', () => {
      pickingPosition = !pickingPosition;
      pickBtn.classList.toggle('active', pickingPosition);
      if (pickingPosition) {
        pickBtn.textContent = 'Click Map...';
        // Expose a callback on the overlay element so external code can call it
        pickCallback = (lat, lon) => {
          state.position = { latitude: lat, longitude: lon };
          pickingPosition = false;
          reRender();
        };
        overlay._onMapPick = pickCallback;
      } else {
        pickBtn.textContent = 'Pick from Map';
        pickCallback = null;
        overlay._onMapPick = null;
      }
    });
  }

  function syncActionParam(actionIdx, param, value) {
    const action = state.actions[actionIdx];
    if (!action) return;

    if (param === 'intercept_target') {
      action.intercept_target = value || undefined;
    } else if (param === 'dest_lat' || param === 'dest_lon') {
      if (!action.destination) {
        action.destination = { latitude: null, longitude: null };
      }
      const num = parseFloat(value);
      if (param === 'dest_lat') {
        action.destination.latitude = isNaN(num) ? null : num;
      } else {
        action.destination.longitude = isNaN(num) ? null : num;
      }
    } else if (param === 'search_area') {
      action.search_area = value || undefined;
    } else if (param === 'message') {
      action.message = value || undefined;
    } else if (param === 'patrol_area') {
      action.patrol_area = value || undefined;
    }
  }

  function syncPosition(latStr, lonStr) {
    const lat = parseFloat(latStr);
    const lon = parseFloat(lonStr);
    if (!isNaN(lat) && !isNaN(lon)) {
      state.position = { latitude: lat, longitude: lon };
    } else if (latStr === '' && lonStr === '') {
      state.position = null;
    }
  }

  function clearTimeError() {
    const errEl = overlay.querySelector('#evt-time-error');
    if (errEl) errEl.style.display = 'none';
  }

  function showTimeError(msg) {
    const errEl = overlay.querySelector('#evt-time-error');
    if (errEl) {
      errEl.textContent = msg;
      errEl.style.display = 'block';
    }
  }

  function reRender() {
    render();
    wireEvents();
  }

  function doCancel() {
    close();
    if (onCancel) onCancel();
  }

  function doSave() {
    // Validate time
    if (!state.time) {
      showTimeError('Time is required.');
      overlay.querySelector('#evt-time')?.focus();
      return;
    }
    if (!isValidTime(state.time)) {
      showTimeError('Invalid format. Use MM:SS (e.g., 05:30). Seconds must be 00-59.');
      overlay.querySelector('#evt-time')?.focus();
      return;
    }

    // Build result event
    const result = {
      time: state.time,
      type: state.type,
      severity: state.severity,
      description: state.description,
      targets: [...state.targets],
      actions: clone(state.actions) || [],
      alert_agencies: [...state.alert_agencies],
      position: state.position ? clone(state.position) : null,
    };

    // Clean up empty arrays/nulls for cleanliness
    if (result.targets.length === 0) result.targets = [];
    if (result.actions.length === 0) result.actions = [];
    if (result.alert_agencies.length === 0) result.alert_agencies = [];

    close();
    onSave(result);
  }

  function close() {
    pickingPosition = false;
    pickCallback = null;
    overlay._onMapPick = null;
    overlay.remove();
    document.removeEventListener('keydown', onKeydown);
  }

  function onKeydown(e) {
    if (e.key === 'Escape') {
      doCancel();
    }
  }

  document.addEventListener('keydown', onKeydown);

  // Initial wiring
  wireEvents();
}

// ---------------------------------------------------------------------------
// Utility: HTML escaping
// ---------------------------------------------------------------------------

function escapeHTML(str) {
  if (!str) return '';
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function escapeAttr(str) {
  if (!str) return '';
  return str
    .replace(/&/g, '&amp;')
    .replace(/"/g, '&quot;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}
