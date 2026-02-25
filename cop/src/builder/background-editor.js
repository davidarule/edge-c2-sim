/**
 * Background Editor — modal dialog for creating and editing background
 * (ambient traffic) entity groups in the Scenario Builder.
 *
 * Background groups define clusters of ambient entities (cargo ships, tankers,
 * fishing vessels, etc.) that populate the simulation area with realistic
 * maritime traffic.
 *
 * Uses the same dark theme and patterns as event-editor.js.
 */

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

export const BACKGROUND_ENTITY_TYPES = [
  'CARGO_SHIP', 'TANKER', 'FISHING_VESSEL', 'PASSENGER_FERRY',
  'SAILING_VESSEL', 'PLEASURE_CRAFT', 'TUG', 'BULK_CARRIER',
];

const PREDEFINED_AREAS = [
  { value: 'sulu_sea', label: 'Sulu Sea' },
  { value: 'esszone', label: 'ESSZONE' },
  { value: 'sabah_coast', label: 'Sabah Coast' },
  { value: 'strait_malacca', label: 'Strait of Malacca' },
  { value: '__custom__', label: 'Custom Area' },
];

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const MODAL_STYLES = `
  .bge-overlay {
    position: fixed; top: 0; left: 0; right: 0; bottom: 0;
    background: rgba(0,0,0,0.6); z-index: 10000;
    display: flex; align-items: center; justify-content: center;
    font-family: 'IBM Plex Sans', sans-serif;
  }
  .bge-modal {
    background: #161B22; border: 1px solid #30363D; border-radius: 6px;
    width: 480px; max-height: 90vh; display: flex; flex-direction: column;
    color: #C9D1D9; box-shadow: 0 8px 32px rgba(0,0,0,0.5);
  }
  .bge-modal-header {
    display: flex; justify-content: space-between; align-items: center;
    padding: 12px 16px; border-bottom: 1px solid #30363D; flex-shrink: 0;
  }
  .bge-modal-header h3 {
    margin: 0; font-size: 14px; font-weight: 600; letter-spacing: 0.5px;
    text-transform: uppercase; color: #E6EDF3;
  }
  .bge-modal-close {
    background: none; border: none; color: #8B949E; font-size: 18px;
    cursor: pointer; padding: 0 4px; line-height: 1;
  }
  .bge-modal-close:hover { color: #F85149; }
  .bge-modal-body {
    flex: 1; overflow-y: auto; padding: 16px; display: flex;
    flex-direction: column; gap: 12px;
  }
  .bge-modal-body::-webkit-scrollbar { width: 6px; }
  .bge-modal-body::-webkit-scrollbar-track { background: transparent; }
  .bge-modal-body::-webkit-scrollbar-thumb { background: #30363D; border-radius: 3px; }

  /* Form rows */
  .bge-row {
    display: flex; align-items: center; gap: 8px;
  }
  .bge-row label {
    width: 80px; font-size: 11px; color: #8B949E; flex-shrink: 0;
    text-align: right;
  }
  .bge-row select, .bge-row input {
    flex: 1; padding: 5px 8px; font-size: 12px;
    background: #0D1117; border: 1px solid #30363D; border-radius: 3px;
    color: #C9D1D9; font-family: 'IBM Plex Sans', sans-serif;
  }
  .bge-row select:focus, .bge-row input:focus {
    outline: none; border-color: #58A6FF;
  }

  /* Checkbox row */
  .bge-check-row {
    display: flex; align-items: center; gap: 8px;
    margin-left: 88px;
  }
  .bge-check-row label {
    display: flex; align-items: center; gap: 6px;
    font-size: 12px; cursor: pointer; color: #C9D1D9;
  }
  .bge-check-row input[type="checkbox"] {
    accent-color: #58A6FF; cursor: pointer;
  }

  /* Speed range row */
  .bge-speed-row {
    display: flex; align-items: center; gap: 8px;
  }
  .bge-speed-row label {
    width: 80px; font-size: 11px; color: #8B949E; flex-shrink: 0;
    text-align: right;
  }
  .bge-speed-row input {
    width: 70px; padding: 5px 8px; font-size: 12px;
    background: #0D1117; border: 1px solid #30363D; border-radius: 3px;
    color: #C9D1D9; font-family: 'IBM Plex Sans', sans-serif;
  }
  .bge-speed-row input:focus { outline: none; border-color: #58A6FF; }
  .bge-speed-row .bge-speed-sep {
    font-size: 11px; color: #484F58;
  }

  /* Custom area note */
  .bge-note {
    margin-left: 88px; font-size: 11px; color: #484F58;
    font-style: italic;
  }

  /* Section labels */
  .bge-section {
    display: flex; align-items: center; gap: 8px;
    margin-top: 4px;
  }
  .bge-section-label {
    font-size: 10px; color: #484F58; text-transform: uppercase;
    letter-spacing: 0.8px; white-space: nowrap;
  }
  .bge-section-line {
    flex: 1; height: 1px; background: #21262D;
  }
  .bge-section-btn {
    background: none; border: 1px solid #30363D; color: #58A6FF;
    font-size: 11px; padding: 2px 8px; border-radius: 3px; cursor: pointer;
    font-family: 'IBM Plex Sans', sans-serif; white-space: nowrap;
  }
  .bge-section-btn:hover { background: rgba(88,166,255,0.1); }

  /* Metadata key-value rows */
  .bge-meta-list {
    display: flex; flex-direction: column; gap: 6px;
    margin-left: 88px;
  }
  .bge-meta-item {
    display: flex; align-items: center; gap: 6px;
  }
  .bge-meta-item input {
    flex: 1; padding: 4px 6px; font-size: 12px;
    background: #0D1117; border: 1px solid #30363D; border-radius: 3px;
    color: #C9D1D9; font-family: 'IBM Plex Sans', sans-serif;
  }
  .bge-meta-item input:focus { outline: none; border-color: #58A6FF; }
  .bge-meta-item input.bge-meta-key { flex: 0.4; }
  .bge-meta-item input.bge-meta-val { flex: 0.6; }
  .bge-meta-remove {
    background: none; border: none; color: #484F58; font-size: 14px;
    cursor: pointer; padding: 0 2px; line-height: 1; flex-shrink: 0;
  }
  .bge-meta-remove:hover { color: #F85149; }

  /* Footer */
  .bge-modal-footer {
    display: flex; justify-content: space-between; align-items: center;
    padding: 12px 16px; border-top: 1px solid #30363D; flex-shrink: 0;
  }
  .bge-btn {
    padding: 6px 16px; border-radius: 3px; font-size: 12px;
    font-family: 'IBM Plex Sans', sans-serif; cursor: pointer; border: none;
  }
  .bge-btn-primary {
    background: #238636; color: #FFF;
  }
  .bge-btn-primary:hover { background: #2EA043; }
  .bge-btn-secondary {
    background: #21262D; color: #C9D1D9; border: 1px solid #30363D;
  }
  .bge-btn-secondary:hover { background: #30363D; }

  /* Validation error */
  .bge-error {
    color: #F85149; font-size: 11px; padding: 0 16px 0 88px;
    margin-top: -6px;
  }
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

function optionsFromArray(arr, selected) {
  return arr.map(v =>
    `<option value="${v}" ${v === selected ? 'selected' : ''}>${v}</option>`
  ).join('');
}

function areaOptions(selected) {
  return PREDEFINED_AREAS.map(a =>
    `<option value="${a.value}" ${a.value === selected ? 'selected' : ''}>${a.label}</option>`
  ).join('');
}

function clone(obj) {
  if (obj == null) return null;
  return JSON.parse(JSON.stringify(obj));
}

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

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Open the Background Editor modal.
 *
 * @param {Object|null} group     Existing background group to edit, or null for new
 * @param {Function}    onSave    Callback: (groupObject) => void
 * @param {Function}    [onCancel] Optional callback on cancel/close
 */
export function openBackgroundEditor(group, onSave, onCancel) {
  injectStyles();

  const isNew = !group;

  // Working copy of the group state
  const state = {
    type: BACKGROUND_ENTITY_TYPES[0],
    count: 8,
    speed_range: { min: 8, max: 14 },
    area: 'sulu_sea',
    custom_area: null,
    ais_active: true,
    flag: 'various',
    metadata: {},
  };

  // Metadata as editable key-value pairs
  let metaEntries = [];

  // Populate from existing group
  if (group) {
    state.type = group.type || BACKGROUND_ENTITY_TYPES[0];
    state.count = group.count != null ? group.count : 8;
    if (group.speed_range) {
      state.speed_range = {
        min: group.speed_range.min != null ? group.speed_range.min : 8,
        max: group.speed_range.max != null ? group.speed_range.max : 14,
      };
    }
    state.area = group.area || 'sulu_sea';
    state.custom_area = group.custom_area ? clone(group.custom_area) : null;
    state.ais_active = group.ais_active != null ? group.ais_active : true;
    state.flag = group.flag || 'various';
    state.metadata = group.metadata ? clone(group.metadata) : {};

    // If area is not a predefined one, treat as custom
    if (!PREDEFINED_AREAS.some(a => a.value === state.area && a.value !== '__custom__')) {
      state.area = '__custom__';
    }
  }

  // Populate metaEntries from metadata object
  metaEntries = Object.entries(state.metadata).map(([k, v]) => ({
    key: k, value: String(v),
  }));

  // -- Create DOM --

  const overlay = document.createElement('div');
  overlay.className = 'bge-overlay';

  function isCustomArea() {
    return state.area === '__custom__';
  }

  function render() {
    overlay.innerHTML = `
      <div class="bge-modal">
        <div class="bge-modal-header">
          <h3>${isNew ? 'New Background Group' : 'Edit Background Group'}</h3>
          <button class="bge-modal-close" title="Close">\u2715</button>
        </div>
        <div class="bge-modal-body">

          <!-- Type -->
          <div class="bge-row">
            <label>Type</label>
            <select id="bge-type">${optionsFromArray(BACKGROUND_ENTITY_TYPES, state.type)}</select>
          </div>

          <!-- Count -->
          <div class="bge-row">
            <label>Count</label>
            <input type="number" id="bge-count" value="${state.count}" min="1" max="50">
          </div>

          <!-- Speed Range -->
          <div class="bge-speed-row">
            <label>Speed (kn)</label>
            <input type="number" id="bge-speed-min" value="${state.speed_range.min}" min="0" max="50" step="0.5">
            <span class="bge-speed-sep">to</span>
            <input type="number" id="bge-speed-max" value="${state.speed_range.max}" min="0" max="50" step="0.5">
          </div>
          <div class="bge-error" id="bge-speed-error" style="display:none;"></div>

          <!-- Area -->
          <div class="bge-row">
            <label>Area</label>
            <select id="bge-area">${areaOptions(state.area)}</select>
          </div>
          ${isCustomArea() ? '<div class="bge-note">Draw area on map in AREA mode</div>' : ''}

          <!-- AIS Active -->
          <div class="bge-check-row">
            <label>
              <input type="checkbox" id="bge-ais" ${state.ais_active ? 'checked' : ''}>
              AIS Active
            </label>
          </div>

          <!-- Flag -->
          <div class="bge-row">
            <label>Flag</label>
            <input type="text" id="bge-flag" value="${escapeAttr(state.flag)}" placeholder="e.g. various, MY, SG">
          </div>

          <!-- Metadata -->
          <div class="bge-section">
            <span class="bge-section-label">Metadata</span>
            <span class="bge-section-line"></span>
            <button class="bge-section-btn" id="bge-add-meta">+ Add Field</button>
          </div>
          <div class="bge-meta-list" id="bge-meta-list">
            ${renderMetaEntries()}
          </div>

        </div>
        <div class="bge-modal-footer">
          <button class="bge-btn bge-btn-secondary" id="bge-cancel">Cancel</button>
          <button class="bge-btn bge-btn-primary" id="bge-save">Save Group</button>
        </div>
      </div>
    `;
  }

  function renderMetaEntries() {
    if (metaEntries.length === 0) return '';
    return metaEntries.map((entry, i) => `
      <div class="bge-meta-item">
        <input type="text" class="bge-meta-key" data-meta-idx="${i}"
               value="${escapeAttr(entry.key)}" placeholder="key">
        <input type="text" class="bge-meta-val" data-meta-idx="${i}"
               value="${escapeAttr(entry.value)}" placeholder="value">
        <button class="bge-meta-remove" data-meta-idx="${i}" title="Remove">\u2715</button>
      </div>
    `).join('');
  }

  // -- Initial render and attach --

  render();
  document.body.appendChild(overlay);

  // -- Wire events --

  function wireEvents() {
    const modal = overlay.querySelector('.bge-modal');
    if (!modal) return;

    // Close button
    modal.querySelector('.bge-modal-close').addEventListener('click', doCancel);

    // Cancel button
    modal.querySelector('#bge-cancel').addEventListener('click', doCancel);

    // Save button
    modal.querySelector('#bge-save').addEventListener('click', doSave);

    // Backdrop click
    overlay.addEventListener('click', (e) => {
      if (e.target === overlay) doCancel();
    });

    // Type select
    const typeSelect = modal.querySelector('#bge-type');
    typeSelect.addEventListener('change', () => {
      state.type = typeSelect.value;
    });

    // Count input
    const countInput = modal.querySelector('#bge-count');
    countInput.addEventListener('input', () => {
      const val = parseInt(countInput.value, 10);
      if (!isNaN(val)) state.count = Math.max(1, Math.min(50, val));
    });

    // Speed range
    const speedMin = modal.querySelector('#bge-speed-min');
    const speedMax = modal.querySelector('#bge-speed-max');
    speedMin.addEventListener('input', () => {
      const val = parseFloat(speedMin.value);
      if (!isNaN(val)) state.speed_range.min = val;
      clearError('bge-speed-error');
    });
    speedMax.addEventListener('input', () => {
      const val = parseFloat(speedMax.value);
      if (!isNaN(val)) state.speed_range.max = val;
      clearError('bge-speed-error');
    });

    // Area select
    const areaSelect = modal.querySelector('#bge-area');
    areaSelect.addEventListener('change', () => {
      state.area = areaSelect.value;
      reRender();
    });

    // AIS checkbox
    const aisCheck = modal.querySelector('#bge-ais');
    aisCheck.addEventListener('change', () => {
      state.ais_active = aisCheck.checked;
    });

    // Flag input
    const flagInput = modal.querySelector('#bge-flag');
    flagInput.addEventListener('input', () => {
      state.flag = flagInput.value.trim();
    });

    // Add metadata button
    const addMetaBtn = modal.querySelector('#bge-add-meta');
    addMetaBtn.addEventListener('click', () => {
      metaEntries.push({ key: '', value: '' });
      reRender();
    });

    // Metadata key/value inputs
    modal.querySelectorAll('.bge-meta-key').forEach(el => {
      el.addEventListener('input', () => {
        const idx = parseInt(el.dataset.metaIdx, 10);
        if (metaEntries[idx]) metaEntries[idx].key = el.value;
      });
    });
    modal.querySelectorAll('.bge-meta-val').forEach(el => {
      el.addEventListener('input', () => {
        const idx = parseInt(el.dataset.metaIdx, 10);
        if (metaEntries[idx]) metaEntries[idx].value = el.value;
      });
    });

    // Metadata remove buttons
    modal.querySelectorAll('.bge-meta-remove').forEach(btn => {
      btn.addEventListener('click', () => {
        const idx = parseInt(btn.dataset.metaIdx, 10);
        metaEntries.splice(idx, 1);
        reRender();
      });
    });
  }

  function clearError(id) {
    const el = overlay.querySelector(`#${id}`);
    if (el) el.style.display = 'none';
  }

  function showError(id, msg) {
    const el = overlay.querySelector(`#${id}`);
    if (el) {
      el.textContent = msg;
      el.style.display = 'block';
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
    // Validate speed range
    if (state.speed_range.min > state.speed_range.max) {
      showError('bge-speed-error', 'Min speed must be less than or equal to max speed.');
      return;
    }

    // Build metadata object from entries
    const metadata = {};
    for (const entry of metaEntries) {
      const k = entry.key.trim();
      if (k) metadata[k] = entry.value;
    }

    // Build result
    const result = {
      type: state.type,
      count: state.count,
      speed_range: { min: state.speed_range.min, max: state.speed_range.max },
      area: state.area === '__custom__' ? 'custom' : state.area,
      custom_area: state.area === '__custom__' ? state.custom_area : null,
      ais_active: state.ais_active,
      flag: state.flag || 'various',
      metadata: metadata,
    };

    close();
    onSave(result);
  }

  function close() {
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
