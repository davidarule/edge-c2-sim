/**
 * Scenario Panel — left sidebar panel for the Scenario Builder (BUILD mode).
 *
 * Shows scenario metadata, entity list grouped by agency, background entity
 * groups, and timed events. Provides action buttons for adding/editing/removing
 * entities, events, and background groups, plus New/Load/Save YAML controls.
 */

import { renderSymbol } from '../symbol-renderer.js';

// ── Styles ──

const PANEL_STYLES = `
  .scenario-panel {
    width: 260px; height: 100%;
    background: #0D1117;
    font-family: 'IBM Plex Sans', sans-serif;
    color: #C9D1D9; font-size: 12px;
    display: flex; flex-direction: column;
    overflow: hidden;
    user-select: none;
  }

  /* Top action bar */
  .scenario-top-bar {
    display: flex; align-items: center; gap: 4px;
    padding: 8px 10px;
    flex-shrink: 0;
    border-bottom: 1px solid #30363D;
    background: #161B22;
  }
  .scenario-top-btn {
    padding: 4px 8px; font-size: 11px;
    background: #21262D; border: 1px solid #30363D;
    border-radius: 3px; color: #C9D1D9;
    cursor: pointer; white-space: nowrap;
    font-family: 'IBM Plex Sans', sans-serif;
  }
  .scenario-top-btn:hover {
    background: #30363D; color: #E6EDF3;
  }
  .scenario-top-btn.primary {
    background: rgba(88, 166, 255, 0.15);
    border-color: rgba(88, 166, 255, 0.3);
    color: #58A6FF;
  }
  .scenario-top-btn.primary:hover {
    background: rgba(88, 166, 255, 0.25);
  }

  /* Scrollable body */
  .scenario-body {
    flex: 1; overflow-y: auto; overflow-x: hidden;
    padding: 0 0 8px;
  }
  .scenario-body::-webkit-scrollbar {
    width: 6px;
  }
  .scenario-body::-webkit-scrollbar-track {
    background: transparent;
  }
  .scenario-body::-webkit-scrollbar-thumb {
    background: #30363D; border-radius: 3px;
  }

  /* Section header (collapsible) */
  .scenario-section-header {
    display: flex; align-items: center; gap: 6px;
    padding: 8px 10px; cursor: pointer;
    border-top: 1px solid #21262D;
    background: #161B22;
    transition: background 0.1s;
  }
  .scenario-section-header:first-child {
    border-top: none;
  }
  .scenario-section-header:hover {
    background: #1C2128;
  }
  .scenario-section-toggle {
    font-size: 8px; color: #484F58;
    width: 10px; text-align: center; flex-shrink: 0;
    transition: transform 0.15s;
  }
  .scenario-section-toggle.expanded {
    transform: rotate(90deg);
  }
  .scenario-section-title {
    flex: 1; font-size: 11px; font-weight: 600;
    color: #E6EDF3; text-transform: uppercase;
    letter-spacing: 0.5px;
  }
  .scenario-section-count {
    font-size: 10px; color: #484F58;
    flex-shrink: 0;
  }

  /* Section content */
  .scenario-section-content {
    display: none;
    padding: 0;
  }
  .scenario-section-content.expanded {
    display: block;
  }

  /* Metadata form */
  .scenario-meta-form {
    padding: 8px 10px;
    display: flex; flex-direction: column; gap: 6px;
  }
  .scenario-meta-label {
    font-size: 10px; color: #8B949E;
    text-transform: uppercase; letter-spacing: 0.3px;
    margin-bottom: 2px;
  }
  .scenario-meta-input,
  .scenario-meta-textarea {
    width: 100%; padding: 5px 8px;
    font-size: 12px; background: #161B22;
    border: 1px solid #30363D; border-radius: 3px;
    color: #C9D1D9; box-sizing: border-box;
    font-family: 'IBM Plex Sans', sans-serif;
  }
  .scenario-meta-input:focus,
  .scenario-meta-textarea:focus {
    outline: none; border-color: #58A6FF;
  }
  .scenario-meta-input::placeholder,
  .scenario-meta-textarea::placeholder {
    color: #484F58;
  }
  .scenario-meta-textarea {
    resize: vertical; min-height: 48px;
  }
  .scenario-meta-row {
    display: flex; gap: 6px;
  }
  .scenario-meta-row .scenario-meta-field {
    flex: 1; min-width: 0;
  }
  .scenario-meta-field {
    display: flex; flex-direction: column;
  }

  /* Agency group header */
  .scenario-agency-header {
    display: flex; align-items: center; gap: 6px;
    padding: 6px 10px 6px 20px; cursor: pointer;
    transition: background 0.1s;
  }
  .scenario-agency-header:hover {
    background: #1C2128;
  }
  .scenario-agency-toggle {
    font-size: 8px; color: #484F58;
    width: 10px; text-align: center; flex-shrink: 0;
    transition: transform 0.15s;
  }
  .scenario-agency-toggle.expanded {
    transform: rotate(90deg);
  }
  .scenario-agency-color {
    width: 8px; height: 8px; border-radius: 2px;
    flex-shrink: 0;
  }
  .scenario-agency-name {
    flex: 1; font-size: 11px; font-weight: 600;
    color: #E6EDF3; white-space: nowrap;
    overflow: hidden; text-overflow: ellipsis;
    min-width: 0;
  }
  .scenario-agency-count {
    font-size: 10px; color: #484F58;
    flex-shrink: 0; margin-left: auto;
  }

  /* Agency entity list */
  .scenario-agency-list {
    display: none;
  }
  .scenario-agency-list.expanded {
    display: block;
  }

  /* Entity row */
  .scenario-entity-row {
    display: flex; align-items: center; gap: 6px;
    padding: 4px 10px 4px 36px; cursor: pointer;
    transition: background 0.1s;
  }
  .scenario-entity-row:hover {
    background: #1C2128;
  }
  .scenario-entity-row.selected {
    background: #1F3A5F;
  }
  .scenario-entity-placement {
    font-size: 10px; flex-shrink: 0;
    width: 12px; text-align: center;
  }
  .scenario-entity-placement.placed {
    color: #3FB950;
  }
  .scenario-entity-placement.unplaced {
    color: #484F58;
  }
  .scenario-entity-symbol {
    width: 24px; height: 24px; flex-shrink: 0;
    display: flex; align-items: center; justify-content: center;
  }
  .scenario-entity-symbol img {
    max-width: 24px; max-height: 24px;
    object-fit: contain;
  }
  .scenario-entity-info {
    flex: 1; min-width: 0; overflow: hidden;
  }
  .scenario-entity-callsign {
    font-size: 12px; color: #E6EDF3;
    white-space: nowrap; overflow: hidden;
    text-overflow: ellipsis;
  }
  .scenario-entity-type {
    font-size: 10px; color: #8B949E;
    white-space: nowrap; overflow: hidden;
    text-overflow: ellipsis;
  }

  /* Entity action buttons row */
  .scenario-entity-actions {
    display: flex; align-items: center; gap: 4px;
    padding: 6px 10px;
  }
  .scenario-entity-action-btn {
    padding: 4px 8px; font-size: 11px;
    background: #21262D; border: 1px solid #30363D;
    border-radius: 3px; color: #58A6FF;
    cursor: pointer; white-space: nowrap;
    font-family: 'IBM Plex Sans', sans-serif;
  }
  .scenario-entity-action-btn:hover {
    background: #30363D; color: #79C0FF;
  }

  /* Background group row */
  .scenario-bg-row {
    display: flex; align-items: center; gap: 6px;
    padding: 5px 10px 5px 20px; cursor: pointer;
    transition: background 0.1s;
  }
  .scenario-bg-row:hover {
    background: #1C2128;
  }
  .scenario-bg-type {
    flex: 1; min-width: 0; overflow: hidden;
  }
  .scenario-bg-type-name {
    font-size: 12px; color: #E6EDF3;
    white-space: nowrap; overflow: hidden;
    text-overflow: ellipsis;
  }
  .scenario-bg-type-area {
    font-size: 10px; color: #8B949E;
    white-space: nowrap; overflow: hidden;
    text-overflow: ellipsis;
  }
  .scenario-bg-count {
    font-size: 11px; color: #58A6FF;
    font-weight: 600; flex-shrink: 0;
    background: rgba(88, 166, 255, 0.1);
    padding: 2px 6px; border-radius: 3px;
  }

  /* Event row */
  .scenario-event-row {
    display: flex; align-items: center; gap: 6px;
    padding: 5px 10px 5px 20px; cursor: pointer;
    transition: background 0.1s;
  }
  .scenario-event-row:hover {
    background: #1C2128;
  }
  .scenario-event-time {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 11px; flex-shrink: 0;
    padding: 2px 6px; border-radius: 2px;
    background: rgba(210, 153, 34, 0.2);
    color: #D29922;
  }
  .scenario-event-severity {
    font-size: 12px; flex-shrink: 0;
    width: 16px; text-align: center;
  }
  .scenario-event-info {
    flex: 1; min-width: 0; overflow: hidden;
  }
  .scenario-event-type-label {
    font-size: 11px; color: #E6EDF3;
    white-space: nowrap; overflow: hidden;
    text-overflow: ellipsis;
  }
  .scenario-event-desc {
    font-size: 10px; color: #8B949E;
    white-space: nowrap; overflow: hidden;
    text-overflow: ellipsis;
  }

  /* Add button at bottom of section */
  .scenario-add-btn {
    display: flex; align-items: center; justify-content: center;
    gap: 4px; padding: 6px 10px;
    font-size: 11px; color: #58A6FF;
    cursor: pointer; background: transparent;
    border: none; width: 100%;
    font-family: 'IBM Plex Sans', sans-serif;
    transition: background 0.1s;
  }
  .scenario-add-btn:hover {
    background: #161B22;
  }

  /* Context menu */
  .scenario-context-menu {
    position: fixed; z-index: 10001;
    background: #161B22; border: 1px solid #30363D;
    border-radius: 4px; padding: 4px 0;
    min-width: 150px;
    box-shadow: 0 4px 16px rgba(0,0,0,0.4);
    font-family: 'IBM Plex Sans', sans-serif;
  }
  .scenario-context-item {
    padding: 6px 12px; font-size: 12px;
    color: #C9D1D9; cursor: pointer;
    white-space: nowrap;
  }
  .scenario-context-item:hover {
    background: #21262D; color: #E6EDF3;
  }
  .scenario-context-item.danger {
    color: #F85149;
  }
  .scenario-context-item.danger:hover {
    background: #3D1117;
  }
  .scenario-context-sep {
    height: 1px; background: #30363D;
    margin: 4px 0;
  }

  /* Empty state */
  .scenario-empty-state {
    padding: 20px 10px; text-align: center;
    color: #484F58; font-size: 11px;
  }
`;

// ── Style injection ──

let stylesInjected = false;
function injectStyles() {
  if (stylesInjected) return;
  const style = document.createElement('style');
  style.textContent = PANEL_STYLES;
  document.head.appendChild(style);
  stylesInjected = true;
}

// ── Helpers ──

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

/**
 * Format minutes offset as "HH:MM" or "mm:ss" style badge text.
 * Accepts minutes (number) or an "HH:MM:SS" / "MM:SS" string.
 */
function formatTime(time) {
  if (typeof time === 'number') {
    const h = Math.floor(time / 60);
    const m = Math.floor(time % 60);
    return h > 0
      ? `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`
      : `${String(m).padStart(2, '0')}:00`;
  }
  if (typeof time === 'string') {
    return time;
  }
  return '--:--';
}

const SEVERITY_ICONS = {
  critical: '\u{1F534}',
  high:     '\u{1F7E0}',
  medium:   '\u{1F7E1}',
  low:      '\u{1F535}',
  info:     '\u{2139}\uFE0F',
};

function severityIcon(severity) {
  return SEVERITY_ICONS[(severity || '').toLowerCase()] || '\u{26AA}';
}

/**
 * Check if an entity has been placed on the map (has initial_position with lat/lon).
 */
function isPlaced(entity) {
  if (!entity) return false;
  const pos = entity.initial_position || entity.position;
  if (!pos) return false;
  return typeof pos.lat === 'number' && typeof pos.lon === 'number';
}

// ── Public API ──

/**
 * Initialize the Scenario Panel.
 *
 * @param {HTMLElement} container  DOM element to render into (the builder left sidebar)
 * @param {Object} config          App config with agencyColors, agencyLabels
 * @returns {Object}               Panel API
 */
export function initScenarioPanel(container, config) {
  injectStyles();

  // State
  let scenario = null;    // { metadata, entities, background_entities, events }
  let visible = false;
  let selectedEntityId = null;

  // Collapsed state
  let metadataExpanded = true;
  let entitiesExpanded = true;
  let backgroundExpanded = false;
  let eventsExpanded = false;
  let expandedAgencies = new Set();

  // Callbacks
  const entitySelectCallbacks = [];
  const actionCallbacks = [];

  // ── Build DOM ──

  const panel = document.createElement('div');
  panel.className = 'scenario-panel';

  panel.innerHTML = `
    <div class="scenario-top-bar">
      <button class="scenario-top-btn" data-action="new">New</button>
      <button class="scenario-top-btn" data-action="load-yaml">Load YAML</button>
      <button class="scenario-top-btn primary" data-action="save-yaml">Save YAML</button>
    </div>
    <div class="scenario-body"></div>
  `;

  container.appendChild(panel);

  // ── References ──

  const topBar = panel.querySelector('.scenario-top-bar');
  const body = panel.querySelector('.scenario-body');

  // ── Context menu management ──

  let activeContextMenu = null;

  function dismissContextMenu() {
    if (activeContextMenu) {
      activeContextMenu.remove();
      activeContextMenu = null;
    }
  }

  document.addEventListener('click', (e) => {
    if (activeContextMenu && !activeContextMenu.contains(e.target)) {
      dismissContextMenu();
    }
  });

  document.addEventListener('contextmenu', () => {
    dismissContextMenu();
  });

  function createContextMenu(x, y, items) {
    dismissContextMenu();

    const menu = document.createElement('div');
    menu.className = 'scenario-context-menu';

    for (const item of items) {
      if (item.separator) {
        const sep = document.createElement('div');
        sep.className = 'scenario-context-sep';
        menu.appendChild(sep);
        continue;
      }

      const el = document.createElement('div');
      el.className = `scenario-context-item ${item.danger ? 'danger' : ''}`;
      el.textContent = item.label;
      el.addEventListener('click', (e) => {
        e.stopPropagation();
        dismissContextMenu();
        if (item.action) item.action();
      });
      menu.appendChild(el);
    }

    menu.style.left = `${x}px`;
    menu.style.top = `${y}px`;
    document.body.appendChild(menu);

    // Adjust if overflowing viewport
    const rect = menu.getBoundingClientRect();
    if (rect.right > window.innerWidth) {
      menu.style.left = `${window.innerWidth - rect.width - 4}px`;
    }
    if (rect.bottom > window.innerHeight) {
      menu.style.top = `${window.innerHeight - rect.height - 4}px`;
    }

    activeContextMenu = menu;
  }

  // ── Action dispatch ──

  function fireAction(action, data) {
    for (const cb of actionCallbacks) {
      cb(action, data);
    }
  }

  // ── Top bar events ──

  topBar.addEventListener('click', (e) => {
    const btn = e.target.closest('[data-action]');
    if (!btn) return;
    e.stopPropagation();
    fireAction(btn.dataset.action, null);
  });

  // ── Render ──

  function render() {
    body.innerHTML = '';

    if (!scenario) {
      body.innerHTML = '<div class="scenario-empty-state">No scenario loaded.<br>Click "New" or "Load YAML" to begin.</div>';
      return;
    }

    renderMetadataSection();
    renderEntitiesSection();
    renderBackgroundSection();
    renderEventsSection();
  }

  // ── Metadata section ──

  function renderMetadataSection() {
    const meta = scenario.metadata || {};

    const section = createSection('Metadata', metadataExpanded, null, (expanded) => {
      metadataExpanded = expanded;
    });

    const content = section.querySelector('.scenario-section-content');
    content.innerHTML = `
      <div class="scenario-meta-form">
        <div class="scenario-meta-field">
          <label class="scenario-meta-label">Name</label>
          <input class="scenario-meta-input" type="text" data-field="name"
                 value="${escapeHtml(meta.name || '')}" placeholder="Scenario name">
        </div>
        <div class="scenario-meta-field">
          <label class="scenario-meta-label">Description</label>
          <textarea class="scenario-meta-textarea" data-field="description"
                    rows="3" placeholder="Brief description">${escapeHtml(meta.description || '')}</textarea>
        </div>
        <div class="scenario-meta-row">
          <div class="scenario-meta-field">
            <label class="scenario-meta-label">Duration (min)</label>
            <input class="scenario-meta-input" type="number" data-field="duration_minutes"
                   value="${meta.duration_minutes || ''}" placeholder="45" min="1">
          </div>
        </div>
        <div class="scenario-meta-field">
          <label class="scenario-meta-label">Area of Operations</label>
          <input class="scenario-meta-input" type="text" data-field="area_of_operations"
                 value="${escapeHtml(meta.area_of_operations || '')}" placeholder="e.g. Strait of Malacca">
        </div>
        <div class="scenario-meta-field">
          <label class="scenario-meta-label">Classification</label>
          <input class="scenario-meta-input" type="text" data-field="classification"
                 value="${escapeHtml(meta.classification || '')}" placeholder="e.g. UNCLASSIFIED">
        </div>
      </div>
    `;

    // Wire metadata input changes
    content.querySelectorAll('.scenario-meta-input, .scenario-meta-textarea').forEach(input => {
      input.addEventListener('change', () => {
        if (!scenario.metadata) scenario.metadata = {};
        const field = input.dataset.field;
        let value = input.value;
        if (input.type === 'number') {
          value = value !== '' ? Number(value) : null;
        }
        scenario.metadata[field] = value;
      });
    });

    body.appendChild(section);
  }

  // ── Entities section ──

  function renderEntitiesSection() {
    const entities = scenario.entities || [];

    const section = createSection('Entities', entitiesExpanded, entities.length, (expanded) => {
      entitiesExpanded = expanded;
    });

    const content = section.querySelector('.scenario-section-content');

    if (entities.length === 0) {
      content.innerHTML = '<div class="scenario-empty-state">No entities defined</div>';
    } else {
      // Group by agency
      const byAgency = {};
      for (const entity of entities) {
        const agency = entity.agency || 'UNKNOWN';
        if (!byAgency[agency]) byAgency[agency] = [];
        byAgency[agency].push(entity);
      }

      // Render each agency group
      const agencyOrder = ['RMP', 'MMEA', 'CI', 'RMAF', 'MIL', 'CIVILIAN', 'UNKNOWN'];
      const sortedAgencies = Object.keys(byAgency).sort((a, b) => {
        const ia = agencyOrder.indexOf(a);
        const ib = agencyOrder.indexOf(b);
        return (ia === -1 ? 99 : ia) - (ib === -1 ? 99 : ib);
      });

      for (const agency of sortedAgencies) {
        const agencyEntities = byAgency[agency];
        const isExpanded = expandedAgencies.has(agency);
        const agencyColor = (config.agencyColors && config.agencyColors[agency]) || '#78909C';
        const agencyLabel = (config.agencyLabels && config.agencyLabels[agency]) || agency;

        // Agency header
        const agencyHeader = document.createElement('div');
        agencyHeader.className = 'scenario-agency-header';

        agencyHeader.innerHTML = `
          <span class="scenario-agency-toggle ${isExpanded ? 'expanded' : ''}">\u25B6</span>
          <span class="scenario-agency-color" style="background:${escapeHtml(agencyColor)};"></span>
          <span class="scenario-agency-name">${escapeHtml(agencyLabel)}</span>
          <span class="scenario-agency-count">(${agencyEntities.length})</span>
        `;

        agencyHeader.addEventListener('click', () => {
          if (expandedAgencies.has(agency)) {
            expandedAgencies.delete(agency);
          } else {
            expandedAgencies.add(agency);
          }
          render();
        });

        content.appendChild(agencyHeader);

        // Entity list
        const entityList = document.createElement('div');
        entityList.className = `scenario-agency-list ${isExpanded ? 'expanded' : ''}`;

        for (const entity of agencyEntities) {
          const row = createEntityRow(entity);
          entityList.appendChild(row);
        }

        content.appendChild(entityList);
      }
    }

    // Action buttons
    const actionsRow = document.createElement('div');
    actionsRow.className = 'scenario-entity-actions';
    actionsRow.innerHTML = `
      <button class="scenario-entity-action-btn" data-action="add-from-orbat">+ From ORBAT</button>
      <button class="scenario-entity-action-btn" data-action="add-manual">+ Manual</button>
    `;
    actionsRow.addEventListener('click', (e) => {
      const btn = e.target.closest('[data-action]');
      if (!btn) return;
      e.stopPropagation();
      fireAction(btn.dataset.action, null);
    });
    content.appendChild(actionsRow);

    body.appendChild(section);
  }

  function createEntityRow(entity) {
    const row = document.createElement('div');
    row.className = `scenario-entity-row ${entity.entity_id === selectedEntityId ? 'selected' : ''}`;
    row.dataset.entityId = entity.entity_id || '';

    const placed = isPlaced(entity);
    const placementClass = placed ? 'placed' : 'unplaced';
    const placementChar = placed ? '\u25CF' : '\u25CB';

    const callsign = entity.callsign || entity.entity_id || 'Unnamed';
    const entityType = entity.entity_type || '';
    const sidc = entity.sidc || config.defaultSidc || '10033000001100000000';
    const symbolUrl = renderSymbol(sidc, { size: 24 });

    row.innerHTML = `
      <span class="scenario-entity-placement ${placementClass}">${placementChar}</span>
      <div class="scenario-entity-symbol">
        <img src="${symbolUrl}" alt="">
      </div>
      <div class="scenario-entity-info">
        <div class="scenario-entity-callsign">${escapeHtml(callsign)}</div>
        <div class="scenario-entity-type">${escapeHtml(entityType)}</div>
      </div>
    `;

    // Click to select
    row.addEventListener('click', (e) => {
      e.stopPropagation();
      selectedEntityId = entity.entity_id;

      // Update selection styling
      body.querySelectorAll('.scenario-entity-row.selected').forEach(el => el.classList.remove('selected'));
      row.classList.add('selected');

      // Fire custom event
      const event = new CustomEvent('scenario-entity-select', { detail: { entity } });
      container.dispatchEvent(event);

      for (const cb of entitySelectCallbacks) {
        cb(entity);
      }
    });

    // Right-click context menu
    row.addEventListener('contextmenu', (e) => {
      e.preventDefault();
      e.stopPropagation();
      createContextMenu(e.clientX, e.clientY, [
        {
          label: 'Edit Properties',
          action: () => fireAction('edit-entity', entity)
        },
        {
          label: 'Set Behavior',
          action: () => fireAction('set-behavior', entity)
        },
        {
          label: 'Define Route',
          action: () => fireAction('define-route', entity)
        },
        { separator: true },
        {
          label: 'Remove',
          danger: true,
          action: () => fireAction('remove-entity', entity)
        }
      ]);
    });

    return row;
  }

  // ── Background entities section ──

  function renderBackgroundSection() {
    const bgGroups = scenario.background_entities || [];

    const section = createSection('Background Entities', backgroundExpanded, bgGroups.length, (expanded) => {
      backgroundExpanded = expanded;
    });

    const content = section.querySelector('.scenario-section-content');

    if (bgGroups.length === 0) {
      content.innerHTML = '<div class="scenario-empty-state">No background entities</div>';
    } else {
      for (const group of bgGroups) {
        const row = document.createElement('div');
        row.className = 'scenario-bg-row';

        const typeName = group.entity_type || 'Unknown type';
        const area = group.area || group.zone || group.area_id || '';
        const count = group.count || 0;

        row.innerHTML = `
          <div class="scenario-bg-type">
            <div class="scenario-bg-type-name">${escapeHtml(typeName)}</div>
            ${area ? `<div class="scenario-bg-type-area">${escapeHtml(area)}</div>` : ''}
          </div>
          <span class="scenario-bg-count">${count}</span>
        `;

        row.addEventListener('click', (e) => {
          e.stopPropagation();
          fireAction('edit-background', group);
        });

        row.addEventListener('contextmenu', (e) => {
          e.preventDefault();
          e.stopPropagation();
          createContextMenu(e.clientX, e.clientY, [
            {
              label: 'Edit Group',
              action: () => fireAction('edit-background', group)
            },
            { separator: true },
            {
              label: 'Remove Group',
              danger: true,
              action: () => fireAction('remove-background', group)
            }
          ]);
        });

        content.appendChild(row);
      }
    }

    // Add button
    const addBtn = document.createElement('button');
    addBtn.className = 'scenario-add-btn';
    addBtn.textContent = '+ Background Group';
    addBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      fireAction('add-background', null);
    });
    content.appendChild(addBtn);

    body.appendChild(section);
  }

  // ── Events section ──

  function renderEventsSection() {
    const events = scenario.events || [];

    const section = createSection('Events', eventsExpanded, events.length, (expanded) => {
      eventsExpanded = expanded;
    });

    const content = section.querySelector('.scenario-section-content');

    // Sort events by time
    const sorted = [...events].sort((a, b) => {
      const ta = typeof a.time === 'number' ? a.time : 0;
      const tb = typeof b.time === 'number' ? b.time : 0;
      return ta - tb;
    });

    if (sorted.length === 0) {
      content.innerHTML = '<div class="scenario-empty-state">No events defined</div>';
    } else {
      for (const evt of sorted) {
        const row = document.createElement('div');
        row.className = 'scenario-event-row';

        const time = formatTime(evt.time);
        const type = evt.type || evt.event_type || 'event';
        const severity = evt.severity || 'info';
        const desc = evt.description || '';

        row.innerHTML = `
          <span class="scenario-event-time">${escapeHtml(time)}</span>
          <span class="scenario-event-severity">${severityIcon(severity)}</span>
          <div class="scenario-event-info">
            <div class="scenario-event-type-label">${escapeHtml(type)}</div>
            ${desc ? `<div class="scenario-event-desc">${escapeHtml(desc)}</div>` : ''}
          </div>
        `;

        row.addEventListener('click', (e) => {
          e.stopPropagation();
          fireAction('edit-event', evt);
        });

        row.addEventListener('contextmenu', (e) => {
          e.preventDefault();
          e.stopPropagation();
          createContextMenu(e.clientX, e.clientY, [
            {
              label: 'Edit Event',
              action: () => fireAction('edit-event', evt)
            },
            { separator: true },
            {
              label: 'Remove Event',
              danger: true,
              action: () => fireAction('remove-event', evt)
            }
          ]);
        });

        content.appendChild(row);
      }
    }

    // Add button
    const addBtn = document.createElement('button');
    addBtn.className = 'scenario-add-btn';
    addBtn.textContent = '+ Event';
    addBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      fireAction('add-event', null);
    });
    content.appendChild(addBtn);

    body.appendChild(section);
  }

  // ── Section builder helper ──

  function createSection(title, isExpanded, count, onToggle) {
    const wrapper = document.createDocumentFragment();

    const header = document.createElement('div');
    header.className = 'scenario-section-header';
    header.innerHTML = `
      <span class="scenario-section-toggle ${isExpanded ? 'expanded' : ''}">\u25B6</span>
      <span class="scenario-section-title">${escapeHtml(title)}</span>
      ${count !== null && count !== undefined ? `<span class="scenario-section-count">(${count})</span>` : ''}
    `;

    const content = document.createElement('div');
    content.className = `scenario-section-content ${isExpanded ? 'expanded' : ''}`;

    header.addEventListener('click', () => {
      const nowExpanded = !content.classList.contains('expanded');
      onToggle(nowExpanded);
      render();
    });

    // We need a container div so we can query for .scenario-section-content
    const sectionDiv = document.createElement('div');
    sectionDiv.appendChild(header);
    sectionDiv.appendChild(content);

    return sectionDiv;
  }

  // ── Initial render ──

  render();

  // ── Public API ──

  return {
    /** Show the panel. */
    show() {
      visible = true;
      panel.style.display = 'flex';
      render();
    },

    /** Hide the panel. */
    hide() {
      visible = false;
      panel.style.display = 'none';
      dismissContextMenu();
    },

    /**
     * Load a scenario state into the panel.
     * @param {Object} scenarioState  { metadata, entities, background_entities, events }
     */
    setScenario(scenarioState) {
      scenario = scenarioState;
      selectedEntityId = null;
      // Reset collapsed state for agencies
      expandedAgencies.clear();
      // Expand entities section by default when scenario is loaded
      entitiesExpanded = true;
      metadataExpanded = true;
      backgroundExpanded = false;
      eventsExpanded = false;
      render();
    },

    /**
     * Get the current scenario state (with any metadata edits applied).
     * @returns {Object|null}  { metadata, entities, background_entities, events }
     */
    getScenario() {
      return scenario;
    },

    /** Re-render the panel from current scenario state. */
    refresh() {
      render();
    },

    /**
     * Register a callback for entity selection.
     * @param {function(entity)} callback
     */
    onEntitySelect(callback) {
      if (typeof callback === 'function') {
        entitySelectCallbacks.push(callback);
      }
    },

    /**
     * Register a callback for panel actions.
     * @param {function(action, data)} callback
     *   action: 'new' | 'load-yaml' | 'save-yaml' | 'add-from-orbat' | 'add-manual' |
     *           'add-background' | 'add-event' | 'remove-entity' | 'edit-entity' |
     *           'set-behavior' | 'define-route' | 'edit-event' | 'remove-event' |
     *           'edit-background' | 'remove-background'
     */
    onAction(callback) {
      if (typeof callback === 'function') {
        actionCallbacks.push(callback);
      }
    }
  };
}
