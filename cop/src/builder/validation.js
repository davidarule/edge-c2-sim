/**
 * Continuous Validation Engine for the Scenario Builder.
 *
 * Provides pure validation of scenario state, a status badge for the header,
 * and a detailed modal for reviewing and fixing issues.
 */

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const TIME_RE = /^\d{2,}:\d{2}$/;

const SEVERITY_COLORS = {
  error:   '#F85149',
  warning: '#D29922',
  info:    '#58A6FF',
};

const SEVERITY_ICONS = {
  error:   '\u2716',  // heavy X
  warning: '\u26A0',  // warning triangle
  info:    '\u2139',   // info circle
};

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const VALIDATION_STYLES = `
  /* Status badge */
  .validation-badge {
    display: inline-flex; align-items: center; gap: 5px;
    padding: 3px 10px; border-radius: 12px;
    font-family: 'IBM Plex Sans', sans-serif;
    font-size: 11px; font-weight: 600;
    cursor: pointer; user-select: none;
    border: 1px solid #30363D;
    background: #161B22; color: #C9D1D9;
    transition: background 0.15s, border-color 0.15s;
    white-space: nowrap;
  }
  .validation-badge:hover {
    background: #1C2128;
  }
  .validation-badge .badge-dot {
    width: 8px; height: 8px; border-radius: 50%;
    flex-shrink: 0;
  }
  .validation-badge.valid .badge-dot { background: #3FB950; }
  .validation-badge.warnings .badge-dot { background: #D29922; }
  .validation-badge.errors .badge-dot { background: #F85149; }

  /* Modal overlay */
  .validation-overlay {
    position: fixed; inset: 0; z-index: 20000;
    background: rgba(0, 0, 0, 0.6);
    display: flex; align-items: center; justify-content: center;
    font-family: 'IBM Plex Sans', sans-serif;
  }

  /* Modal container */
  .validation-modal {
    background: #161B22;
    border: 1px solid #30363D;
    border-radius: 8px;
    width: 520px; max-width: 90vw;
    max-height: 80vh;
    display: flex; flex-direction: column;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.5);
  }

  /* Modal header */
  .validation-modal-header {
    display: flex; align-items: center; justify-content: space-between;
    padding: 14px 18px;
    border-bottom: 1px solid #30363D;
    flex-shrink: 0;
  }
  .validation-modal-title {
    font-size: 15px; font-weight: 600; color: #E6EDF3;
  }
  .validation-modal-close {
    width: 28px; height: 28px;
    display: flex; align-items: center; justify-content: center;
    background: transparent; border: none;
    color: #8B949E; font-size: 18px;
    cursor: pointer; border-radius: 4px;
  }
  .validation-modal-close:hover {
    background: #21262D; color: #E6EDF3;
  }

  /* Modal body */
  .validation-modal-body {
    flex: 1; overflow-y: auto; padding: 12px 18px 18px;
  }
  .validation-modal-body::-webkit-scrollbar { width: 6px; }
  .validation-modal-body::-webkit-scrollbar-track { background: transparent; }
  .validation-modal-body::-webkit-scrollbar-thumb { background: #30363D; border-radius: 3px; }

  /* Section within modal */
  .validation-section {
    margin-bottom: 16px;
  }
  .validation-section:last-child {
    margin-bottom: 0;
  }
  .validation-section-header {
    font-size: 11px; font-weight: 600;
    text-transform: uppercase; letter-spacing: 0.5px;
    padding: 6px 0; margin-bottom: 4px;
  }

  /* Item row */
  .validation-item {
    display: flex; align-items: flex-start; gap: 8px;
    padding: 7px 10px;
    border-radius: 4px;
    margin-bottom: 2px;
    font-size: 12px; color: #C9D1D9;
    line-height: 1.4;
  }
  .validation-item.error   { background: rgba(248, 81, 73, 0.08); }
  .validation-item.warning { background: rgba(210, 153, 34, 0.08); }
  .validation-item.info    { background: rgba(88, 166, 255, 0.08); }

  .validation-item-icon {
    flex-shrink: 0; width: 16px; text-align: center;
    font-size: 12px; line-height: 1.4;
  }
  .validation-item-body {
    flex: 1; min-width: 0;
  }
  .validation-item-code {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 10px; opacity: 0.6;
    margin-right: 6px;
  }
  .validation-item-fix {
    flex-shrink: 0;
    background: none; border: none;
    font-family: 'IBM Plex Sans', sans-serif;
    font-size: 11px; cursor: pointer;
    padding: 2px 8px; border-radius: 3px;
    white-space: nowrap;
  }
  .validation-item.error .validation-item-fix {
    color: #F85149;
  }
  .validation-item.error .validation-item-fix:hover {
    background: rgba(248, 81, 73, 0.15);
  }
  .validation-item.warning .validation-item-fix {
    color: #D29922;
  }
  .validation-item.warning .validation-item-fix:hover {
    background: rgba(210, 153, 34, 0.15);
  }

  /* Empty state */
  .validation-empty {
    text-align: center; padding: 24px 0;
    color: #3FB950; font-size: 13px;
  }
  .validation-empty-icon {
    font-size: 28px; margin-bottom: 8px;
  }
`;

let stylesInjected = false;

function injectStyles() {
  if (stylesInjected) return;
  const style = document.createElement('style');
  style.textContent = VALIDATION_STYLES;
  document.head.appendChild(style);
  stylesInjected = true;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function timeToSeconds(time) {
  if (!time || typeof time !== 'string') return -1;
  const m = TIME_RE.exec(time);
  if (!m) return -1;
  const parts = time.split(':');
  return parseInt(parts[0], 10) * 60 + parseInt(parts[1], 10);
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

// ---------------------------------------------------------------------------
// Validation logic (pure)
// ---------------------------------------------------------------------------

/**
 * Run all validation checks on a scenario.
 *
 * @param {Object} scenario  Builder scenario state { metadata, entities, background_entities, events }
 * @returns {{ errors: Array, warnings: Array, info: Array }}
 *   Each item: { code, message, severity, entityId?, eventIndex?, field? }
 */
function validate(scenario) {
  const errors = [];
  const warnings = [];
  const info = [];

  if (!scenario) {
    errors.push({ code: 'E002', message: 'No scenario loaded', severity: 'error' });
    return { errors, warnings, info };
  }

  const meta = scenario.metadata || {};
  const entities = scenario.entities || [];
  const events = scenario.events || [];
  const bgEntities = scenario.background_entities || [];

  // --- Errors ---

  // E001: no name
  if (!meta.name || meta.name.trim() === '') {
    errors.push({ code: 'E001', message: 'Scenario has no name', severity: 'error', field: 'name' });
  }

  // E002: no entities
  if (entities.length === 0) {
    errors.push({ code: 'E002', message: 'Scenario has no entities', severity: 'error' });
  }

  // Build entity ID set for reference checks
  const entityIds = new Set();
  const seenIds = new Set();

  for (let i = 0; i < entities.length; i++) {
    const ent = entities[i];
    const eid = ent.id || ent.entity_id || '';

    // E004: duplicate ID
    if (eid && seenIds.has(eid)) {
      errors.push({
        code: 'E004',
        message: `Duplicate entity ID "${eid}"`,
        severity: 'error',
        entityId: eid,
      });
    }
    if (eid) {
      seenIds.add(eid);
      entityIds.add(eid);
    }

    // E003: no position
    const pos = ent.initial_position;
    const hasPos = pos && (
      (typeof pos.latitude === 'number' && typeof pos.longitude === 'number') ||
      (typeof pos.lat === 'number' && typeof pos.lon === 'number')
    );
    if (!hasPos && !ent.placed) {
      errors.push({
        code: 'E003',
        message: `Entity "${eid || 'unnamed'}" has no position (not placed)`,
        severity: 'error',
        entityId: eid,
        field: 'initial_position',
      });
    }

    // E007: invalid SIDC
    if (ent.sidc) {
      const sidc = String(ent.sidc);
      if (sidc.length !== 20 || !/^\d{20}$/.test(sidc)) {
        errors.push({
          code: 'E007',
          message: `Entity "${eid || 'unnamed'}" has invalid SIDC "${sidc}" (must be 20 digits)`,
          severity: 'error',
          entityId: eid,
          field: 'sidc',
        });
      }
    }

    // W002: no waypoints
    if (!ent.waypoints || ent.waypoints.length === 0) {
      warnings.push({
        code: 'W002',
        message: `Entity "${eid || 'unnamed'}" has no waypoints (stationary)`,
        severity: 'warning',
        entityId: eid,
      });
    }

    // W003: speed exceeds 900 knots
    const speed = ent.speed_knots || 0;
    if (speed > 900) {
      warnings.push({
        code: 'W003',
        message: `Entity "${eid || 'unnamed'}" speed ${speed} kts exceeds 900 knots`,
        severity: 'warning',
        entityId: eid,
        field: 'speed_knots',
      });
    }
  }

  // Event checks
  let lastSec = -1;
  let chronoOk = true;

  for (let i = 0; i < events.length; i++) {
    const evt = events[i];

    // E006: invalid time format
    if (!evt.time || !TIME_RE.test(evt.time)) {
      errors.push({
        code: 'E006',
        message: `Event ${i + 1} has invalid time format "${evt.time || '(empty)'}" (expected MM:SS)`,
        severity: 'error',
        eventIndex: i,
        field: 'time',
      });
    } else {
      const sec = timeToSeconds(evt.time);
      if (sec < lastSec) {
        chronoOk = false;
      }
      lastSec = sec;
    }

    // E005: references non-existent entity
    const targets = evt.targets || (evt.target ? [evt.target] : []);
    for (const tid of targets) {
      if (tid && !entityIds.has(tid)) {
        errors.push({
          code: 'E005',
          message: `Event ${i + 1} references non-existent entity "${tid}"`,
          severity: 'error',
          eventIndex: i,
          field: 'targets',
        });
      }
    }
  }

  // W004: events not in chronological order
  if (!chronoOk) {
    warnings.push({
      code: 'W004',
      message: 'Events are not in chronological order',
      severity: 'warning',
    });
  }

  // --- Warnings ---

  // W001: no description
  if (!meta.description || meta.description.trim() === '') {
    warnings.push({
      code: 'W001',
      message: 'Scenario has no description',
      severity: 'warning',
      field: 'description',
    });
  }

  // W005: background group count > 30
  for (let i = 0; i < bgEntities.length; i++) {
    const bg = bgEntities[i];
    if (bg.count > 30) {
      warnings.push({
        code: 'W005',
        message: `Background group "${bg.entity_type || bg.type || i}" has count ${bg.count} (>30, performance concern)`,
        severity: 'warning',
      });
    }
  }

  // W006: duration is 0 or not set
  if (!meta.duration_minutes || meta.duration_minutes <= 0) {
    warnings.push({
      code: 'W006',
      message: 'Scenario duration is 0 or not set',
      severity: 'warning',
      field: 'duration_minutes',
    });
  }

  // --- Info ---

  // I001: total entity count
  info.push({
    code: 'I001',
    message: `${entities.length} scenario ${entities.length === 1 ? 'entity' : 'entities'}`,
    severity: 'info',
  });

  // I002: total event count
  info.push({
    code: 'I002',
    message: `${events.length} ${events.length === 1 ? 'event' : 'events'}`,
    severity: 'info',
  });

  // I003: estimated duration from last event time
  if (events.length > 0) {
    let maxSec = 0;
    for (const evt of events) {
      const sec = timeToSeconds(evt.time);
      if (sec > maxSec) maxSec = sec;
    }
    if (maxSec > 0) {
      const mins = Math.floor(maxSec / 60);
      const secs = maxSec % 60;
      info.push({
        code: 'I003',
        message: `Estimated duration from last event: ${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`,
        severity: 'info',
      });
    }
  }

  return { errors, warnings, info };
}

// ---------------------------------------------------------------------------
// Status badge UI
// ---------------------------------------------------------------------------

/**
 * Create a validation status badge in the given container.
 *
 * @param {HTMLElement} container  Element to append badge into
 * @returns {{ update(results): void }}
 */
function createStatusBadge(container) {
  injectStyles();

  const badge = document.createElement('div');
  badge.className = 'validation-badge valid';
  badge.innerHTML = '<span class="badge-dot"></span><span class="badge-text">Valid</span>';
  container.appendChild(badge);

  const textEl = badge.querySelector('.badge-text');

  let currentResults = null;
  let onClickCallback = null;

  badge.addEventListener('click', () => {
    if (onClickCallback) {
      onClickCallback(currentResults);
    }
  });

  return {
    /**
     * Update the badge with new validation results.
     * @param {{ errors: Array, warnings: Array, info: Array }} results
     */
    update(results) {
      currentResults = results;
      const errCount = results.errors.length;
      const warnCount = results.warnings.length;

      badge.classList.remove('valid', 'warnings', 'errors');

      if (errCount > 0) {
        badge.classList.add('errors');
        textEl.textContent = `${errCount} Error${errCount !== 1 ? 's' : ''}`;
      } else if (warnCount > 0) {
        badge.classList.add('warnings');
        textEl.textContent = `${warnCount} Issue${warnCount !== 1 ? 's' : ''}`;
      } else {
        badge.classList.add('valid');
        textEl.textContent = 'Valid';
      }
    },

    /**
     * Set the click handler for the badge.
     * @param {function} cb  Called with current results when badge is clicked
     */
    onClick(cb) {
      onClickCallback = cb;
    },

    /** Get the badge DOM element. */
    element: badge,
  };
}

// ---------------------------------------------------------------------------
// Validation modal UI
// ---------------------------------------------------------------------------

/**
 * Show a modal with detailed validation results.
 *
 * @param {{ errors: Array, warnings: Array, info: Array }} results
 * @param {function} [onFix]  Called with the item when a "Fix" link is clicked
 */
function showValidationModal(results, onFix) {
  injectStyles();

  // Remove any existing modal
  const existing = document.querySelector('.validation-overlay');
  if (existing) existing.remove();

  const overlay = document.createElement('div');
  overlay.className = 'validation-overlay';

  const modal = document.createElement('div');
  modal.className = 'validation-modal';

  // Header
  const header = document.createElement('div');
  header.className = 'validation-modal-header';

  const errCount = results.errors.length;
  const warnCount = results.warnings.length;
  const infoCount = results.info.length;
  const totalIssues = errCount + warnCount;
  let titleText;
  if (totalIssues === 0) {
    titleText = 'Validation Passed';
  } else {
    const parts = [];
    if (errCount > 0) parts.push(`${errCount} Error${errCount !== 1 ? 's' : ''}`);
    if (warnCount > 0) parts.push(`${warnCount} Warning${warnCount !== 1 ? 's' : ''}`);
    titleText = `Validation: ${parts.join(', ')}`;
  }

  header.innerHTML = `
    <span class="validation-modal-title">${escapeHtml(titleText)}</span>
    <button class="validation-modal-close">\u00D7</button>
  `;
  modal.appendChild(header);

  // Body
  const body = document.createElement('div');
  body.className = 'validation-modal-body';

  const hasAny = results.errors.length > 0 || results.warnings.length > 0 || results.info.length > 0;

  if (!hasAny) {
    body.innerHTML = `
      <div class="validation-empty">
        <div class="validation-empty-icon">\u2714</div>
        No issues found
      </div>
    `;
  } else {
    // Errors section
    if (results.errors.length > 0) {
      body.appendChild(buildSection('Errors', 'error', results.errors, onFix));
    }
    // Warnings section
    if (results.warnings.length > 0) {
      body.appendChild(buildSection('Warnings', 'warning', results.warnings, onFix));
    }
    // Info section
    if (results.info.length > 0) {
      body.appendChild(buildSection('Info', 'info', results.info, null));
    }
  }

  modal.appendChild(body);
  overlay.appendChild(modal);
  document.body.appendChild(overlay);

  // Close handlers
  function close() {
    overlay.remove();
  }

  header.querySelector('.validation-modal-close').addEventListener('click', close);

  overlay.addEventListener('click', (e) => {
    if (e.target === overlay) close();
  });

  const onKeyDown = (e) => {
    if (e.key === 'Escape') {
      close();
      document.removeEventListener('keydown', onKeyDown);
    }
  };
  document.addEventListener('keydown', onKeyDown);
}

/**
 * Build a section of validation items.
 */
function buildSection(title, severity, items, onFix) {
  const section = document.createElement('div');
  section.className = 'validation-section';

  const sectionHeader = document.createElement('div');
  sectionHeader.className = 'validation-section-header';
  sectionHeader.style.color = SEVERITY_COLORS[severity] || '#C9D1D9';
  sectionHeader.textContent = `${title} (${items.length})`;
  section.appendChild(sectionHeader);

  for (const item of items) {
    const row = document.createElement('div');
    row.className = `validation-item ${severity}`;

    const icon = document.createElement('span');
    icon.className = 'validation-item-icon';
    icon.style.color = SEVERITY_COLORS[severity] || '#C9D1D9';
    icon.textContent = SEVERITY_ICONS[severity] || '';
    row.appendChild(icon);

    const bodyEl = document.createElement('span');
    bodyEl.className = 'validation-item-body';
    bodyEl.innerHTML = `<span class="validation-item-code">${escapeHtml(item.code)}</span>${escapeHtml(item.message)}`;
    row.appendChild(bodyEl);

    // Fix link (only for errors/warnings with a field or entityId)
    if (onFix && severity !== 'info' && (item.field || item.entityId != null || item.eventIndex != null)) {
      const fixBtn = document.createElement('button');
      fixBtn.className = 'validation-item-fix';
      fixBtn.textContent = 'Fix';
      fixBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        onFix(item);
      });
      row.appendChild(fixBtn);
    }

    section.appendChild(row);
  }

  return section;
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Initialize the validation engine.
 *
 * @param {Object} [config]  Reserved for future options
 * @returns {{ validate, createStatusBadge, showValidationModal }}
 */
export function initValidation(config) {
  return {
    validate,
    createStatusBadge,
    showValidationModal,
  };
}
