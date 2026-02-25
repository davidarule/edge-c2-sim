/**
 * ORBAT Picker — modal for selecting assets from the ORBAT to add to a scenario.
 *
 * Multi-select with checkboxes, search, grouped by organisation.
 */

import { OrbatStore } from '../orbat/orbat-store.js';
import { renderSymbol } from '../symbol-renderer.js';

const PICKER_STYLES = `
  .orbat-picker-overlay {
    position: fixed; top: 0; left: 0; right: 0; bottom: 0;
    background: rgba(0,0,0,0.6); z-index: 10000;
    display: flex; align-items: center; justify-content: center;
    font-family: 'IBM Plex Sans', sans-serif;
  }
  .orbat-picker-modal {
    background: #161B22; border: 1px solid #30363D; border-radius: 6px;
    width: 480px; max-height: 80vh; display: flex; flex-direction: column;
    color: #C9D1D9; box-shadow: 0 8px 32px rgba(0,0,0,0.5);
  }
  .orbat-picker-header {
    display: flex; justify-content: space-between; align-items: center;
    padding: 12px 16px; border-bottom: 1px solid #30363D; flex-shrink: 0;
  }
  .orbat-picker-header h3 {
    margin: 0; font-size: 14px; font-weight: 600; color: #E6EDF3;
  }
  .orbat-picker-close {
    background: none; border: none; color: #8B949E; font-size: 18px;
    cursor: pointer; padding: 0 4px;
  }
  .orbat-picker-close:hover { color: #F85149; }
  .orbat-picker-search {
    margin: 8px 16px; padding: 6px 10px; font-size: 12px;
    background: #0D1117; border: 1px solid #30363D; border-radius: 3px;
    color: #C9D1D9; flex-shrink: 0;
  }
  .orbat-picker-search:focus { outline: none; border-color: #58A6FF; }
  .orbat-picker-search::placeholder { color: #484F58; }
  .orbat-picker-body {
    flex: 1; overflow-y: auto; padding: 0 16px 8px;
  }
  .orbat-picker-org {
    margin-bottom: 4px;
  }
  .orbat-picker-org-header {
    display: flex; align-items: center; gap: 6px;
    padding: 6px 0; cursor: pointer; font-size: 12px; font-weight: 600;
  }
  .orbat-picker-org-header:hover { color: #E6EDF3; }
  .orbat-picker-badge {
    width: 10px; height: 10px; border-radius: 2px; flex-shrink: 0;
  }
  .orbat-picker-unit {
    display: flex; align-items: center; gap: 8px;
    padding: 4px 0 4px 20px; font-size: 12px; cursor: pointer;
  }
  .orbat-picker-unit:hover { background: #21262D; border-radius: 3px; }
  .orbat-picker-unit input[type="checkbox"] {
    accent-color: #58A6FF; cursor: pointer; flex-shrink: 0;
  }
  .orbat-picker-unit-name { flex: 1; }
  .orbat-picker-unit-type { color: #484F58; font-size: 10px; }
  .orbat-picker-footer {
    display: flex; justify-content: space-between; align-items: center;
    padding: 12px 16px; border-top: 1px solid #30363D; flex-shrink: 0;
  }
  .orbat-picker-count { font-size: 11px; color: #8B949E; }
  .orbat-picker-btn {
    padding: 6px 16px; border-radius: 3px; font-size: 12px;
    font-family: 'IBM Plex Sans', sans-serif; cursor: pointer; border: none;
  }
  .orbat-picker-btn-add {
    background: #238636; color: #FFF;
  }
  .orbat-picker-btn-add:hover { background: #2EA043; }
  .orbat-picker-btn-add:disabled { opacity: 0.5; cursor: default; }
  .orbat-picker-btn-cancel {
    background: #21262D; color: #C9D1D9; border: 1px solid #30363D;
  }
  .orbat-picker-btn-cancel:hover { background: #30363D; }
`;

let stylesInjected = false;
function injectStyles() {
  if (stylesInjected) return;
  const style = document.createElement('style');
  style.textContent = PICKER_STYLES;
  document.head.appendChild(style);
  stylesInjected = true;
}

/**
 * Open the ORBAT picker modal.
 *
 * @param {string[]} existingIds - IDs already in the scenario (to show warnings)
 * @param {function} onAdd - Callback: (selectedUnits[]) => void
 * @param {function} [onCancel]
 */
export function openOrbatPicker(existingIds = [], onAdd, onCancel) {
  injectStyles();

  const store = new OrbatStore();
  const orbatList = store.getOrbatList();
  if (orbatList.length === 0) return;

  const model = store.loadOrbat(orbatList[0].name);
  if (!model) return;

  const orgs = model.getOrganisations();
  const selected = new Set();
  let searchText = '';

  const overlay = document.createElement('div');
  overlay.className = 'orbat-picker-overlay';

  function render() {
    const query = searchText.toLowerCase();

    let bodyHtml = '';
    for (const org of orgs) {
      const units = (org.units || []).filter(u => {
        if (!query) return true;
        return (u.callsign || '').toLowerCase().includes(query) ||
               (u.id || '').toLowerCase().includes(query) ||
               (u.entity_type || '').toLowerCase().includes(query);
      });
      if (units.length === 0) continue;

      const color = org.color || '#78909C';
      bodyHtml += `<div class="orbat-picker-org">
        <div class="orbat-picker-org-header">
          <span class="orbat-picker-badge" style="background:${color};"></span>
          ${esc(org.abbreviation || org.name)} (${units.length})
        </div>`;

      for (const unit of units) {
        const checked = selected.has(unit.id) ? 'checked' : '';
        const isDupe = existingIds.includes(unit.id);
        const dupeLabel = isDupe ? ' <span style="color:#D29922;font-size:10px;">(already in scenario)</span>' : '';
        bodyHtml += `<div class="orbat-picker-unit">
          <input type="checkbox" data-unit-id="${esc(unit.id)}" ${checked}>
          <span class="orbat-picker-unit-name">${esc(unit.callsign || unit.id)}${dupeLabel}</span>
          <span class="orbat-picker-unit-type">${esc(unit.entity_type || '')}</span>
        </div>`;
      }
      bodyHtml += `</div>`;
    }

    if (!bodyHtml) {
      bodyHtml = '<div style="padding:20px;text-align:center;color:#484F58;">No matching assets</div>';
    }

    overlay.innerHTML = `
      <div class="orbat-picker-modal">
        <div class="orbat-picker-header">
          <h3>Add from ORBAT</h3>
          <button class="orbat-picker-close">\u2715</button>
        </div>
        <input class="orbat-picker-search" type="text" placeholder="Search assets..." value="${esc(searchText)}">
        <div class="orbat-picker-body">${bodyHtml}</div>
        <div class="orbat-picker-footer">
          <span class="orbat-picker-count">${selected.size} selected</span>
          <div style="display:flex;gap:8px;">
            <button class="orbat-picker-btn orbat-picker-btn-cancel">Cancel</button>
            <button class="orbat-picker-btn orbat-picker-btn-add" ${selected.size === 0 ? 'disabled' : ''}>Add to Scenario</button>
          </div>
        </div>
      </div>
    `;

    // Wire events
    overlay.querySelector('.orbat-picker-close').addEventListener('click', close);
    overlay.querySelector('.orbat-picker-btn-cancel').addEventListener('click', close);
    overlay.querySelector('.orbat-picker-btn-add').addEventListener('click', () => {
      const units = [];
      for (const org of orgs) {
        for (const unit of (org.units || [])) {
          if (selected.has(unit.id)) units.push({ ...unit });
        }
      }
      close();
      if (onAdd) onAdd(units);
    });

    const searchInput = overlay.querySelector('.orbat-picker-search');
    searchInput.addEventListener('input', () => {
      searchText = searchInput.value;
      render();
      // Refocus search after re-render
      const newInput = overlay.querySelector('.orbat-picker-search');
      if (newInput) { newInput.focus(); newInput.selectionStart = newInput.selectionEnd = searchText.length; }
    });

    overlay.querySelectorAll('input[data-unit-id]').forEach(cb => {
      cb.addEventListener('change', () => {
        const id = cb.dataset.unitId;
        if (cb.checked) selected.add(id); else selected.delete(id);
        overlay.querySelector('.orbat-picker-count').textContent = `${selected.size} selected`;
        const addBtn = overlay.querySelector('.orbat-picker-btn-add');
        addBtn.disabled = selected.size === 0;
      });
    });

    overlay.addEventListener('click', (e) => {
      if (e.target === overlay) close();
    });
  }

  function close() {
    overlay.remove();
    document.removeEventListener('keydown', onKey);
    if (onCancel && selected.size === 0) onCancel();
  }

  function onKey(e) {
    if (e.key === 'Escape') close();
  }
  document.addEventListener('keydown', onKey);

  document.body.appendChild(overlay);
  render();
}

function esc(s) {
  const div = document.createElement('div');
  div.textContent = s || '';
  return div.innerHTML;
}
