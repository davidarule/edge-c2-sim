/**
 * ORBAT Manager Panel — left sidebar panel for the Scenario Builder.
 *
 * Renders a collapsible organisation tree of all assets in the current ORBAT,
 * with search, import/export, context menus, and asset selection events.
 */

import { OrbatStore } from './orbat-store.js';
import { importCSV, exportCSV, downloadCSV, exportJSON } from './csv-io.js';
import { renderSymbol } from '../symbol-renderer.js';

// ── Styles ──

const PANEL_STYLES = `
  .orbat-panel {
    width: 260px; height: 100%;
    background: #0D1117;
    font-family: 'IBM Plex Sans', sans-serif;
    color: #C9D1D9; font-size: 12px;
    display: flex; flex-direction: column;
    overflow: hidden;
    user-select: none;
  }

  /* Tab bar */
  .orbat-tab-bar {
    display: flex; flex-shrink: 0;
    border-bottom: 1px solid #30363D;
    background: #161B22;
  }
  .orbat-tab {
    flex: 1; padding: 8px 0; text-align: center;
    font-size: 11px; font-weight: 600;
    letter-spacing: 0.5px; text-transform: uppercase;
    color: #484F58; cursor: default;
    border-bottom: 2px solid transparent;
    transition: color 0.15s;
  }
  .orbat-tab.active {
    color: #58A6FF; border-bottom-color: #58A6FF; cursor: pointer;
  }
  .orbat-tab.placeholder {
    opacity: 0.4;
  }

  /* ORBAT selector */
  .orbat-selector-row {
    display: flex; align-items: center; gap: 6px;
    padding: 8px 10px 4px;
    flex-shrink: 0;
  }
  .orbat-selector-row select {
    flex: 1; padding: 4px 6px; font-size: 11px;
    background: #161B22; border: 1px solid #30363D;
    border-radius: 3px; color: #C9D1D9;
    font-family: 'IBM Plex Sans', sans-serif;
    cursor: pointer; min-width: 0;
  }
  .orbat-selector-row select:focus {
    outline: none; border-color: #58A6FF;
  }

  /* Action buttons row */
  .orbat-actions-row {
    display: flex; align-items: center; gap: 4px;
    padding: 4px 10px 6px;
    flex-shrink: 0;
  }
  .orbat-action-btn {
    padding: 4px 8px; font-size: 11px;
    background: #21262D; border: 1px solid #30363D;
    border-radius: 3px; color: #C9D1D9;
    cursor: pointer; white-space: nowrap;
    font-family: 'IBM Plex Sans', sans-serif;
    position: relative;
  }
  .orbat-action-btn:hover {
    background: #30363D; color: #E6EDF3;
  }

  /* Search box */
  .orbat-search-row {
    padding: 0 10px 6px;
    flex-shrink: 0;
  }
  .orbat-search-input {
    width: 100%; padding: 5px 8px;
    font-size: 12px; background: #161B22;
    border: 1px solid #30363D; border-radius: 3px;
    color: #C9D1D9; box-sizing: border-box;
    font-family: 'IBM Plex Sans', sans-serif;
  }
  .orbat-search-input:focus {
    outline: none; border-color: #58A6FF;
  }
  .orbat-search-input::placeholder {
    color: #484F58;
  }

  /* Scrollable tree body */
  .orbat-tree-body {
    flex: 1; overflow-y: auto; overflow-x: hidden;
    padding: 0 0 4px;
  }
  .orbat-tree-body::-webkit-scrollbar {
    width: 6px;
  }
  .orbat-tree-body::-webkit-scrollbar-track {
    background: transparent;
  }
  .orbat-tree-body::-webkit-scrollbar-thumb {
    background: #30363D; border-radius: 3px;
  }

  /* Org header */
  .orbat-org-header {
    display: flex; align-items: center; gap: 6px;
    padding: 6px 10px; cursor: pointer;
    border-top: 1px solid #21262D;
    background: #161B22;
    transition: background 0.1s;
  }
  .orbat-org-header:first-child {
    border-top: none;
  }
  .orbat-org-header:hover {
    background: #1C2128;
  }
  .orbat-org-toggle {
    font-size: 8px; color: #484F58;
    width: 10px; text-align: center; flex-shrink: 0;
    transition: transform 0.15s;
  }
  .orbat-org-toggle.expanded {
    transform: rotate(90deg);
  }
  .orbat-org-color {
    width: 8px; height: 8px; border-radius: 2px;
    flex-shrink: 0;
  }
  .orbat-org-name {
    flex: 1; font-size: 11px; font-weight: 600;
    color: #E6EDF3; white-space: nowrap;
    overflow: hidden; text-overflow: ellipsis;
    min-width: 0;
  }
  .orbat-org-abbr {
    font-size: 10px; color: #8B949E;
    margin-left: 2px; flex-shrink: 0;
  }
  .orbat-org-count {
    font-size: 10px; color: #484F58;
    flex-shrink: 0; margin-left: auto;
  }

  /* Asset list */
  .orbat-asset-list {
    display: none;
  }
  .orbat-asset-list.expanded {
    display: block;
  }

  /* Asset row */
  .orbat-asset-row {
    display: flex; align-items: center; gap: 6px;
    padding: 4px 10px 4px 26px; cursor: pointer;
    transition: background 0.1s;
  }
  .orbat-asset-row:hover {
    background: #1C2128;
  }
  .orbat-asset-row.selected {
    background: #1F3A5F;
  }
  .orbat-asset-symbol {
    width: 24px; height: 24px; flex-shrink: 0;
    display: flex; align-items: center; justify-content: center;
  }
  .orbat-asset-symbol img {
    max-width: 24px; max-height: 24px;
    object-fit: contain;
  }
  .orbat-asset-info {
    flex: 1; min-width: 0; overflow: hidden;
  }
  .orbat-asset-callsign {
    font-size: 12px; color: #E6EDF3;
    white-space: nowrap; overflow: hidden;
    text-overflow: ellipsis;
  }
  .orbat-asset-type {
    font-size: 10px; color: #8B949E;
    white-space: nowrap; overflow: hidden;
    text-overflow: ellipsis;
  }

  /* Add Organisation button */
  .orbat-add-org-btn {
    display: flex; align-items: center; justify-content: center;
    gap: 4px; padding: 8px 10px;
    font-size: 11px; color: #58A6FF;
    cursor: pointer; border-top: 1px solid #21262D;
    flex-shrink: 0; background: transparent;
    border-left: none; border-right: none; border-bottom: none;
    width: 100; font-family: 'IBM Plex Sans', sans-serif;
    transition: background 0.1s;
  }
  .orbat-add-org-btn:hover {
    background: #161B22;
  }

  /* Context menu */
  .orbat-context-menu {
    position: fixed; z-index: 10001;
    background: #161B22; border: 1px solid #30363D;
    border-radius: 4px; padding: 4px 0;
    min-width: 150px;
    box-shadow: 0 4px 16px rgba(0,0,0,0.4);
    font-family: 'IBM Plex Sans', sans-serif;
  }
  .orbat-context-item {
    padding: 6px 12px; font-size: 12px;
    color: #C9D1D9; cursor: pointer;
    white-space: nowrap;
  }
  .orbat-context-item:hover {
    background: #21262D; color: #E6EDF3;
  }
  .orbat-context-item.danger {
    color: #F85149;
  }
  .orbat-context-item.danger:hover {
    background: #3D1117;
  }
  .orbat-context-sep {
    height: 1px; background: #30363D;
    margin: 4px 0;
  }

  /* Export dropdown */
  .orbat-export-dropdown {
    position: absolute; top: 100%; left: 0;
    z-index: 10001;
    background: #161B22; border: 1px solid #30363D;
    border-radius: 4px; padding: 4px 0;
    min-width: 130px;
    box-shadow: 0 4px 16px rgba(0,0,0,0.4);
    margin-top: 2px;
  }
  .orbat-export-dropdown .orbat-context-item {
    padding: 5px 10px; font-size: 11px;
  }

  /* Empty state */
  .orbat-empty-state {
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

function downloadJSON(jsonString, filename) {
  const blob = new Blob([jsonString], { type: 'application/json;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename || 'orbat.json';
  a.style.display = 'none';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

// ── Public API ──

/**
 * Initialize the ORBAT Manager panel.
 *
 * @param {HTMLElement} container  DOM element to render into (the left sidebar div)
 * @param {Object} config          App config with agencyColors, agencyLabels
 * @returns {Object}               Panel API: show, hide, refresh, getSelectedUnit, onAssetSelect, onAssetAction
 */
export function initOrbatPanel(container, config) {
  injectStyles();

  const store = new OrbatStore();

  // State
  let currentOrbatName = null;
  let currentModel = null;
  let expandedOrgs = new Set();
  let searchQuery = '';
  let selectedUnitId = null;
  let visible = false;

  // Callbacks
  const assetSelectCallbacks = [];
  const assetActionCallbacks = [];

  // Hidden file input for CSV/JSON import
  const fileInput = document.createElement('input');
  fileInput.type = 'file';
  fileInput.accept = '.csv,.json';
  fileInput.style.display = 'none';
  document.body.appendChild(fileInput);

  // ── Build DOM ──

  const panel = document.createElement('div');
  panel.className = 'orbat-panel';

  panel.innerHTML = `
    <div class="orbat-tab-bar">
      <div class="orbat-tab placeholder">Scenario</div>
      <div class="orbat-tab active">ORBAT</div>
      <div class="orbat-tab placeholder">Layers</div>
    </div>
    <div class="orbat-selector-row">
      <select class="orbat-selector"></select>
    </div>
    <div class="orbat-actions-row">
      <button class="orbat-action-btn orbat-btn-import">Import CSV</button>
      <button class="orbat-action-btn orbat-btn-export" style="position:relative;">Export \u25BE</button>
      <button class="orbat-action-btn orbat-btn-add" style="margin-left:auto;">+ Add</button>
    </div>
    <div class="orbat-search-row">
      <input class="orbat-search-input" type="text" placeholder="Search assets...">
    </div>
    <div class="orbat-tree-body"></div>
    <button class="orbat-add-org-btn">+ Add Organisation</button>
  `;

  container.appendChild(panel);

  // ── References ──

  const selectorEl = panel.querySelector('.orbat-selector');
  const importBtn = panel.querySelector('.orbat-btn-import');
  const exportBtn = panel.querySelector('.orbat-btn-export');
  const addBtn = panel.querySelector('.orbat-btn-add');
  const searchInput = panel.querySelector('.orbat-search-input');
  const treeBody = panel.querySelector('.orbat-tree-body');
  const addOrgBtn = panel.querySelector('.orbat-add-org-btn');

  // ── Context menu management ──

  let activeContextMenu = null;
  let activeExportDropdown = null;

  function dismissContextMenu() {
    if (activeContextMenu) {
      activeContextMenu.remove();
      activeContextMenu = null;
    }
  }

  function dismissExportDropdown() {
    if (activeExportDropdown) {
      activeExportDropdown.remove();
      activeExportDropdown = null;
    }
  }

  function dismissAll() {
    dismissContextMenu();
    dismissExportDropdown();
  }

  document.addEventListener('click', (e) => {
    if (activeContextMenu && !activeContextMenu.contains(e.target)) {
      dismissContextMenu();
    }
    if (activeExportDropdown && !activeExportDropdown.contains(e.target) && e.target !== exportBtn) {
      dismissExportDropdown();
    }
  });

  document.addEventListener('contextmenu', () => {
    // Dismiss our custom menus when the user opens a native context menu elsewhere
    dismissAll();
  });

  // ── Populate ORBAT selector ──

  function populateSelector() {
    const orbats = store.getOrbatList();
    selectorEl.innerHTML = '';

    if (orbats.length === 0) {
      const opt = document.createElement('option');
      opt.value = '';
      opt.textContent = '(No ORBATs)';
      selectorEl.appendChild(opt);
      currentOrbatName = null;
      currentModel = null;
      return;
    }

    for (const orbat of orbats) {
      const opt = document.createElement('option');
      opt.value = orbat.name;
      opt.textContent = orbat.name;
      selectorEl.appendChild(opt);
    }

    // Select current or first
    if (currentOrbatName && orbats.find(o => o.name === currentOrbatName)) {
      selectorEl.value = currentOrbatName;
    } else {
      currentOrbatName = orbats[0].name;
      selectorEl.value = currentOrbatName;
    }

    loadCurrentOrbat();
  }

  function loadCurrentOrbat() {
    if (!currentOrbatName) {
      currentModel = null;
      renderTree();
      return;
    }
    currentModel = store.loadOrbat(currentOrbatName);
    renderTree();
  }

  // ── Render org tree ──

  function renderTree() {
    treeBody.innerHTML = '';

    if (!currentModel) {
      treeBody.innerHTML = '<div class="orbat-empty-state">No ORBAT loaded</div>';
      return;
    }

    const orgs = currentModel.getOrganisations();
    const query = searchQuery.toLowerCase().trim();

    let hasVisibleContent = false;

    for (const org of orgs) {
      const units = org.units || [];

      // Filter units by search
      const filteredUnits = query
        ? units.filter(u => {
            const callsign = (u.callsign || u.name || '').toLowerCase();
            const id = (u.id || '').toLowerCase();
            const type = (u.entity_type || '').toLowerCase();
            return callsign.includes(query) || id.includes(query) || type.includes(query);
          })
        : units;

      // Skip entire org if search yields no results
      if (query && filteredUnits.length === 0) continue;

      hasVisibleContent = true;

      const isExpanded = expandedOrgs.has(org.id) || (query.length > 0);
      const orgColor = org.color || (config.agencyColors && config.agencyColors[org.abbreviation]) || '#78909C';

      // Org header
      const header = document.createElement('div');
      header.className = 'orbat-org-header';
      header.dataset.orgId = org.id;

      header.innerHTML = `
        <span class="orbat-org-toggle ${isExpanded ? 'expanded' : ''}">\u25B6</span>
        <span class="orbat-org-color" style="background:${escapeHtml(orgColor)};"></span>
        <span class="orbat-org-abbr">${escapeHtml(org.abbreviation || '')}</span>
        <span class="orbat-org-name">${escapeHtml(org.name || 'Unnamed')}</span>
        <span class="orbat-org-count">(${filteredUnits.length})</span>
      `;

      header.addEventListener('click', () => {
        if (expandedOrgs.has(org.id)) {
          expandedOrgs.delete(org.id);
        } else {
          expandedOrgs.add(org.id);
        }
        renderTree();
      });

      header.addEventListener('contextmenu', (e) => {
        e.preventDefault();
        e.stopPropagation();
        showOrgContextMenu(e.clientX, e.clientY, org);
      });

      treeBody.appendChild(header);

      // Asset list
      const assetList = document.createElement('div');
      assetList.className = `orbat-asset-list ${isExpanded ? 'expanded' : ''}`;

      for (const unit of filteredUnits) {
        const row = document.createElement('div');
        row.className = `orbat-asset-row ${unit.id === selectedUnitId ? 'selected' : ''}`;
        row.dataset.unitId = unit.id;
        row.dataset.orgId = org.id;

        const displayName = unit.callsign || unit.name || unit.id;
        const displayType = unit.entity_type || '';
        const sidc = unit.sidc || config.defaultSidc || '10033000001100000000';
        const symbolUrl = renderSymbol(sidc, { size: 24 });

        row.innerHTML = `
          <div class="orbat-asset-symbol">
            <img src="${symbolUrl}" alt="">
          </div>
          <div class="orbat-asset-info">
            <div class="orbat-asset-callsign">${escapeHtml(displayName)}</div>
            <div class="orbat-asset-type">${escapeHtml(displayType)}</div>
          </div>
        `;

        row.addEventListener('click', (e) => {
          e.stopPropagation();
          selectedUnitId = unit.id;
          // Update selection styling
          treeBody.querySelectorAll('.orbat-asset-row.selected').forEach(el => el.classList.remove('selected'));
          row.classList.add('selected');
          // Fire event
          const event = new CustomEvent('orbat-asset-select', { detail: { unit, orgId: org.id } });
          container.dispatchEvent(event);
          for (const cb of assetSelectCallbacks) {
            cb(unit, org.id);
          }
        });

        row.addEventListener('contextmenu', (e) => {
          e.preventDefault();
          e.stopPropagation();
          showAssetContextMenu(e.clientX, e.clientY, unit, org.id);
        });

        assetList.appendChild(row);
      }

      treeBody.appendChild(assetList);
    }

    if (!hasVisibleContent) {
      const msg = query
        ? 'No assets match the search'
        : 'No organisations in this ORBAT';
      treeBody.innerHTML = `<div class="orbat-empty-state">${msg}</div>`;
    }
  }

  // ── Context menus ──

  function createContextMenu(x, y, items) {
    dismissContextMenu();

    const menu = document.createElement('div');
    menu.className = 'orbat-context-menu';

    for (const item of items) {
      if (item.separator) {
        const sep = document.createElement('div');
        sep.className = 'orbat-context-sep';
        menu.appendChild(sep);
        continue;
      }

      const el = document.createElement('div');
      el.className = `orbat-context-item ${item.danger ? 'danger' : ''}`;
      el.textContent = item.label;
      el.addEventListener('click', (e) => {
        e.stopPropagation();
        dismissContextMenu();
        if (item.action) item.action();
      });
      menu.appendChild(el);
    }

    // Position — keep within viewport
    menu.style.left = `${x}px`;
    menu.style.top = `${y}px`;
    document.body.appendChild(menu);

    // Adjust if overflowing
    const rect = menu.getBoundingClientRect();
    if (rect.right > window.innerWidth) {
      menu.style.left = `${window.innerWidth - rect.width - 4}px`;
    }
    if (rect.bottom > window.innerHeight) {
      menu.style.top = `${window.innerHeight - rect.height - 4}px`;
    }

    activeContextMenu = menu;
  }

  function showAssetContextMenu(x, y, unit, orgId) {
    createContextMenu(x, y, [
      {
        label: 'Edit',
        action: () => fireAction('edit', unit, orgId)
      },
      {
        label: 'Duplicate',
        action: () => fireAction('duplicate', unit, orgId)
      },
      {
        label: 'Show on Map',
        action: () => fireAction('show-on-map', unit, orgId)
      },
      { separator: true },
      {
        label: 'Delete',
        danger: true,
        action: () => fireAction('delete', unit, orgId)
      }
    ]);
  }

  function showOrgContextMenu(x, y, org) {
    createContextMenu(x, y, [
      {
        label: 'Add Asset',
        action: () => fireAction('add-asset', null, org.id)
      },
      {
        label: 'Rename',
        action: () => fireAction('rename-org', null, org.id)
      },
      { separator: true },
      {
        label: 'Delete Organisation',
        danger: true,
        action: () => fireAction('delete-org', null, org.id)
      }
    ]);
  }

  function fireAction(action, unit, orgId) {
    for (const cb of assetActionCallbacks) {
      cb(action, unit, orgId);
    }
  }

  // ── Export dropdown ──

  function showExportDropdown() {
    if (activeExportDropdown) {
      dismissExportDropdown();
      return;
    }

    const btnRect = exportBtn.getBoundingClientRect();
    const dropdown = document.createElement('div');
    dropdown.className = 'orbat-export-dropdown';
    dropdown.style.position = 'fixed';
    dropdown.style.left = `${btnRect.left}px`;
    dropdown.style.top = `${btnRect.bottom + 2}px`;

    const csvItem = document.createElement('div');
    csvItem.className = 'orbat-context-item';
    csvItem.textContent = 'Export CSV';
    csvItem.addEventListener('click', (e) => {
      e.stopPropagation();
      dismissExportDropdown();
      handleExportCSV();
    });
    dropdown.appendChild(csvItem);

    const jsonItem = document.createElement('div');
    jsonItem.className = 'orbat-context-item';
    jsonItem.textContent = 'Export JSON';
    jsonItem.addEventListener('click', (e) => {
      e.stopPropagation();
      dismissExportDropdown();
      handleExportJSON();
    });
    dropdown.appendChild(jsonItem);

    document.body.appendChild(dropdown);
    activeExportDropdown = dropdown;
  }

  // ── Import / Export handlers ──

  function handleImportCSV() {
    fileInput.accept = '.csv';
    fileInput.onchange = (e) => {
      const file = e.target.files[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = (ev) => {
        try {
          const csvString = ev.target.result;
          const result = importCSV(csvString);

          if (result.errors.length > 0) {
            console.warn('[orbat-panel] CSV import errors:', result.errors);
          }
          if (result.warnings.length > 0) {
            console.warn('[orbat-panel] CSV import warnings:', result.warnings);
          }

          if (result.organisations.length === 0) {
            console.error('[orbat-panel] No valid data found in CSV');
            return;
          }

          // Merge imported organisations into current model
          if (!currentModel) return;

          for (const org of result.organisations) {
            // Check if org with same name exists
            const existingOrgs = currentModel.getOrganisations();
            const existing = existingOrgs.find(o => o.name === org.name);
            if (existing) {
              // Add units to existing org
              for (const unit of org.units) {
                currentModel.addUnit(existing.id, unit);
              }
            } else {
              currentModel.addOrganisation(org);
            }
          }

          store.saveOrbat(currentOrbatName, currentModel);
          renderTree();
        } catch (err) {
          console.error('[orbat-panel] CSV import failed:', err);
        }
      };
      reader.readAsText(file);
      // Reset so same file can be selected again
      fileInput.value = '';
    };
    fileInput.click();
  }

  function handleExportCSV() {
    if (!currentModel || !currentOrbatName) return;
    const csvString = exportCSV(currentModel);
    const filename = `${currentOrbatName.replace(/[^a-zA-Z0-9_-]/g, '_')}.csv`;
    downloadCSV(csvString, filename);
  }

  function handleExportJSON() {
    if (!currentOrbatName) return;
    const jsonString = store.exportToJSON(currentOrbatName);
    if (!jsonString) return;
    const filename = `${currentOrbatName.replace(/[^a-zA-Z0-9_-]/g, '_')}.json`;
    downloadJSON(jsonString, filename);
  }

  // ── Wire events ──

  selectorEl.addEventListener('change', () => {
    currentOrbatName = selectorEl.value;
    expandedOrgs.clear();
    searchQuery = '';
    searchInput.value = '';
    selectedUnitId = null;
    loadCurrentOrbat();
  });

  importBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    handleImportCSV();
  });

  exportBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    showExportDropdown();
  });

  addBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    fireAction('add-asset', null, null);
  });

  searchInput.addEventListener('input', () => {
    searchQuery = searchInput.value;
    renderTree();
  });

  addOrgBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    fireAction('add-org', null, null);
  });

  // ── Initial load ──

  populateSelector();

  // ── Public API ──

  return {
    /** Show the panel. */
    show() {
      visible = true;
      panel.style.display = 'flex';
      populateSelector();
    },

    /** Hide the panel. */
    hide() {
      visible = false;
      panel.style.display = 'none';
      dismissAll();
    },

    /** Re-render the tree from store. */
    refresh() {
      populateSelector();
    },

    /** Get the currently selected unit data, or null. */
    getSelectedUnit() {
      if (!selectedUnitId || !currentModel) return null;
      const unit = currentModel.getUnit(selectedUnitId);
      return unit || null;
    },

    /**
     * Register a callback for asset selection.
     * @param {function(unit, orgId)} callback
     */
    onAssetSelect(callback) {
      if (typeof callback === 'function') {
        assetSelectCallbacks.push(callback);
      }
    },

    /**
     * Register a callback for context menu actions.
     * @param {function(action, unit, orgId)} callback
     *   action: 'edit' | 'duplicate' | 'delete' | 'show-on-map' |
     *           'add-asset' | 'rename-org' | 'delete-org' | 'add-org'
     */
    onAssetAction(callback) {
      if (typeof callback === 'function') {
        assetActionCallbacks.push(callback);
      }
    }
  };
}
