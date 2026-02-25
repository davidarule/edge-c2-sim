/**
 * SIDC Builder — interactive modal for constructing MIL-STD-2525D SIDCs.
 *
 * Renders a modal dialog with:
 *   - Live SVG symbol preview (DISA compositor)
 *   - Dropdowns for context, identity, symbol set, status, HQ/TF, echelon
 *   - Collapsible entity tree browser with search
 *   - Modifier 1/2 dropdowns
 *   - Common presets for quick selection
 *   - Copy SIDC button
 */

import { renderSymbol } from '../symbol-renderer.js';
import jmsmlData from '../data/jmsml-entities.json';

// ── SIDC position constants ──

const CONTEXTS = jmsmlData.contexts;    // { "0": "Reality", "1": "Exercise", "2": "Simulation" }
const IDENTITIES = jmsmlData.identities; // { "0": "Pending", ..., "6": "Hostile" }
const STATUSES = jmsmlData.statuses;     // { "0": "Present", "1": "Planned/Anticipated" }
const HQTF = jmsmlData.hqtfDummy;       // { "0": "Not Applicable", ... }
const ECHELONS = jmsmlData.echelons;     // { "00": "Unspecified", ... }
const SYMBOL_SETS = {};

for (const [code, data] of Object.entries(jmsmlData.symbolSets)) {
  SYMBOL_SETS[code] = data.name;
}

// ── Common presets ──

const PRESETS = [
  { label: '— Select Preset —', sidc: null },
  { label: 'MMEA Patrol Vessel', sidc: '10033000001204020000' },
  { label: 'MMEA Fast Intercept', sidc: '10033000001204010000' },
  { label: 'RMN Frigate', sidc: '10033000001202060000' },
  { label: 'RMN Fast Interceptor', sidc: '10033000001204010000' },
  { label: 'Suspect Vessel', sidc: '10053000001400000000' },
  { label: 'RMAF Fixed-Wing (Fighter)', sidc: '10030100001101040000' },
  { label: 'RMAF Helicopter', sidc: '10030100001102000000' },
  { label: 'RMAF MPA', sidc: '10030100001101040000' },
  { label: 'Infantry Unit', sidc: '10031000001201000000' },
  { label: 'SOF Unit', sidc: '10031000001211000000' },
  { label: 'Police Patrol Car', sidc: '10031500001403000000' },
  { label: 'Customs Vehicle', sidc: '10031500001703000000' },
];

// ── Helper: parse SIDC into fields ──

function parseSidc(sidc) {
  const s = (sidc || '10030000000000000000').padEnd(20, '0');
  return {
    version:   s.slice(0, 2),
    context:   s[2],
    identity:  s[3],
    symbolSet: s.slice(4, 6),
    status:    s[6],
    hqtf:      s[7],
    echelon:   s.slice(8, 10),
    entity:    s.slice(10, 12),
    type:      s.slice(12, 14),
    subtype:   s.slice(14, 16),
    mod1:      s.slice(16, 18),
    mod2:      s.slice(18, 20),
  };
}

function buildSidc(fields) {
  return `${fields.version}${fields.context}${fields.identity}${fields.symbolSet}${fields.status}${fields.hqtf}${fields.echelon}${fields.entity}${fields.type}${fields.subtype}${fields.mod1}${fields.mod2}`;
}

// ── Styles ──

const MODAL_STYLES = `
  .sidc-overlay {
    position: fixed; top: 0; left: 0; right: 0; bottom: 0;
    background: rgba(0,0,0,0.6); z-index: 10000;
    display: flex; align-items: center; justify-content: center;
    font-family: 'IBM Plex Sans', sans-serif;
  }
  .sidc-modal {
    background: #161B22; border: 1px solid #30363D; border-radius: 6px;
    width: 660px; max-height: 90vh; display: flex; flex-direction: column;
    color: #C9D1D9; box-shadow: 0 8px 32px rgba(0,0,0,0.5);
  }
  .sidc-modal-header {
    display: flex; justify-content: space-between; align-items: center;
    padding: 12px 16px; border-bottom: 1px solid #30363D; flex-shrink: 0;
  }
  .sidc-modal-header h3 {
    margin: 0; font-size: 14px; font-weight: 600; letter-spacing: 0.5px;
    text-transform: uppercase; color: #E6EDF3;
  }
  .sidc-modal-close {
    background: none; border: none; color: #8B949E; font-size: 18px;
    cursor: pointer; padding: 0 4px; line-height: 1;
  }
  .sidc-modal-close:hover { color: #F85149; }
  .sidc-modal-body {
    display: flex; gap: 16px; padding: 16px; overflow-y: auto; flex: 1;
  }
  .sidc-preview-col {
    display: flex; flex-direction: column; align-items: center; gap: 10px;
    flex-shrink: 0; width: 160px;
  }
  .sidc-preview-box {
    width: 140px; height: 180px; background: #0D1117;
    border: 1px solid #30363D; border-radius: 4px;
    display: flex; align-items: center; justify-content: center;
  }
  .sidc-preview-box img { max-width: 120px; max-height: 160px; }
  .sidc-code-display {
    font-family: 'IBM Plex Mono', monospace; font-size: 12px;
    color: #58A6FF; word-break: break-all; text-align: center;
    padding: 4px 8px; background: #0D1117; border-radius: 3px;
    border: 1px solid #30363D; width: 100%; cursor: pointer;
    user-select: all;
  }
  .sidc-code-display:hover { border-color: #58A6FF; }
  .sidc-preset-select {
    width: 100%; padding: 4px 6px; font-size: 11px;
    background: #21262D; border: 1px solid #30363D; border-radius: 3px;
    color: #C9D1D9; cursor: pointer;
  }
  .sidc-controls-col {
    flex: 1; display: flex; flex-direction: column; gap: 6px;
    min-width: 0;
  }
  .sidc-row {
    display: flex; align-items: center; gap: 8px;
  }
  .sidc-row label {
    width: 80px; font-size: 11px; color: #8B949E; flex-shrink: 0;
    text-align: right;
  }
  .sidc-row select, .sidc-row input {
    flex: 1; padding: 4px 6px; font-size: 12px;
    background: #0D1117; border: 1px solid #30363D; border-radius: 3px;
    color: #C9D1D9;
  }
  .sidc-row select:focus, .sidc-row input:focus {
    outline: none; border-color: #58A6FF;
  }
  .sidc-section-label {
    font-size: 10px; color: #484F58; text-transform: uppercase;
    letter-spacing: 0.8px; margin-top: 4px; padding-left: 88px;
  }
  .sidc-tree-container {
    flex: 1; min-height: 140px; max-height: 240px; overflow-y: auto;
    background: #0D1117; border: 1px solid #30363D; border-radius: 3px;
    padding: 4px; margin-left: 88px;
  }
  .sidc-tree-node {
    cursor: pointer; padding: 2px 4px; font-size: 12px;
    border-radius: 2px; white-space: nowrap;
  }
  .sidc-tree-node:hover { background: #21262D; }
  .sidc-tree-node.selected { background: #1F3A5F; color: #58A6FF; }
  .sidc-tree-node.entity { padding-left: 8px; }
  .sidc-tree-node.type { padding-left: 24px; }
  .sidc-tree-node.subtype { padding-left: 40px; }
  .sidc-tree-toggle {
    display: inline-block; width: 14px; text-align: center;
    color: #484F58; font-size: 10px;
  }
  .sidc-search {
    margin-left: 88px; padding: 4px 6px; font-size: 12px;
    background: #0D1117; border: 1px solid #30363D; border-radius: 3px;
    color: #C9D1D9; width: calc(100% - 88px);
  }
  .sidc-search:focus { outline: none; border-color: #58A6FF; }
  .sidc-search::placeholder { color: #484F58; }
  .sidc-modal-footer {
    display: flex; justify-content: space-between; align-items: center;
    padding: 12px 16px; border-top: 1px solid #30363D; flex-shrink: 0;
  }
  .sidc-btn {
    padding: 6px 16px; border-radius: 3px; font-size: 12px;
    font-family: 'IBM Plex Sans', sans-serif; cursor: pointer; border: none;
  }
  .sidc-btn-primary {
    background: #238636; color: #FFF;
  }
  .sidc-btn-primary:hover { background: #2EA043; }
  .sidc-btn-secondary {
    background: #21262D; color: #C9D1D9; border: 1px solid #30363D;
  }
  .sidc-btn-secondary:hover { background: #30363D; }
  .sidc-btn-copy {
    background: none; border: 1px solid #30363D; color: #8B949E;
    padding: 3px 8px; font-size: 11px; border-radius: 3px; cursor: pointer;
  }
  .sidc-btn-copy:hover { color: #58A6FF; border-color: #58A6FF; }
`;

// ── Inject styles once ──

let stylesInjected = false;
function injectStyles() {
  if (stylesInjected) return;
  const style = document.createElement('style');
  style.textContent = MODAL_STYLES;
  document.head.appendChild(style);
  stylesInjected = true;
}

// ── Build entity tree for a symbol set ──

function buildEntityTree(symbolSetCode) {
  const ssData = jmsmlData.symbolSets[symbolSetCode];
  if (!ssData || !ssData.entities) return [];

  const tree = [];
  const entities = ssData.entities;

  for (const [entityCode, entityData] of Object.entries(entities)) {
    const entityNode = {
      code: entityCode,
      name: entityData.name,
      level: 'entity',
      entity6: `${entityCode}0000`,
      children: [],
    };

    if (entityData.types) {
      for (const [typeCode, typeData] of Object.entries(entityData.types)) {
        const typeDigits = typeCode.slice(2, 4); // typeCode is 4 digits (entity+type)
        const typeNode = {
          code: typeCode,
          name: typeData.name,
          level: 'type',
          entity6: `${entityCode}${typeDigits}00`,
          children: [],
        };

        if (typeData.subtypes) {
          for (const [subCode, subData] of Object.entries(typeData.subtypes)) {
            const subDigits = subCode.slice(4, 6); // subCode is 6 digits
            typeNode.children.push({
              code: subCode,
              name: subData.name,
              level: 'subtype',
              entity6: `${entityCode}${typeDigits}${subDigits}`,
              children: [],
            });
          }
        }

        entityNode.children.push(typeNode);
      }
    }

    tree.push(entityNode);
  }

  return tree;
}

// ── Get modifiers for a symbol set ──

function getModifiers(symbolSetCode, modNum) {
  const ssData = jmsmlData.symbolSets[symbolSetCode];
  if (!ssData) return [];
  const key = modNum === 1 ? 'modifiers1' : 'modifiers2';
  const mods = ssData[key] || {};
  return Object.entries(mods).map(([code, name]) => ({ code, name }));
}

// ── Public API ──

/**
 * Open the SIDC Builder modal.
 *
 * @param {string} initialSidc   Current SIDC to start editing (or empty for default)
 * @param {function} onApply     Callback receiving the new 20-digit SIDC string
 * @param {function} [onCancel]  Optional callback on cancel
 */
export function openSidcBuilder(initialSidc, onApply, onCancel) {
  injectStyles();

  const fields = parseSidc(initialSidc);
  let currentTree = buildEntityTree(fields.symbolSet);
  let expandedNodes = new Set();
  let searchText = '';

  // ── Create DOM ──

  const overlay = document.createElement('div');
  overlay.className = 'sidc-overlay';

  overlay.innerHTML = `
    <div class="sidc-modal">
      <div class="sidc-modal-header">
        <h3>SIDC Builder</h3>
        <button class="sidc-modal-close" title="Close">\u2715</button>
      </div>
      <div class="sidc-modal-body">
        <div class="sidc-preview-col">
          <div class="sidc-preview-box"><img id="sidc-builder-preview" alt="Symbol preview"></div>
          <div class="sidc-code-display" id="sidc-builder-code" title="Click to copy"></div>
          <button class="sidc-btn-copy" id="sidc-builder-copy">Copy SIDC</button>
          <select class="sidc-preset-select" id="sidc-builder-preset">
            ${PRESETS.map((p, i) => `<option value="${i}">${p.label}</option>`).join('')}
          </select>
        </div>
        <div class="sidc-controls-col">
          <div class="sidc-section-label">Standard Identity</div>
          <div class="sidc-row">
            <label>Context</label>
            <select id="sidc-ctx">${optionsFrom(CONTEXTS, fields.context)}</select>
          </div>
          <div class="sidc-row">
            <label>Identity</label>
            <select id="sidc-id">${optionsFrom(IDENTITIES, fields.identity)}</select>
          </div>
          <div class="sidc-row">
            <label>Symbol Set</label>
            <select id="sidc-ss">${optionsFrom(SYMBOL_SETS, fields.symbolSet)}</select>
          </div>
          <div class="sidc-row">
            <label>Status</label>
            <select id="sidc-status">${optionsFrom(STATUSES, fields.status)}</select>
          </div>
          <div class="sidc-row">
            <label>HQ/TF</label>
            <select id="sidc-hqtf">${optionsFrom(HQTF, fields.hqtf)}</select>
          </div>
          <div class="sidc-row">
            <label>Echelon</label>
            <select id="sidc-ech">${optionsFrom(ECHELONS, fields.echelon)}</select>
          </div>

          <div class="sidc-section-label">Entity</div>
          <input class="sidc-search" id="sidc-search" type="text" placeholder="Search entities...">
          <div class="sidc-tree-container" id="sidc-tree"></div>

          <div class="sidc-section-label">Modifiers</div>
          <div class="sidc-row">
            <label>Modifier 1</label>
            <select id="sidc-mod1"></select>
          </div>
          <div class="sidc-row">
            <label>Modifier 2</label>
            <select id="sidc-mod2"></select>
          </div>
        </div>
      </div>
      <div class="sidc-modal-footer">
        <button class="sidc-btn sidc-btn-secondary" id="sidc-cancel">Cancel</button>
        <button class="sidc-btn sidc-btn-primary" id="sidc-apply">Apply SIDC</button>
      </div>
    </div>
  `;

  document.body.appendChild(overlay);

  // ── References ──

  const previewImg = overlay.querySelector('#sidc-builder-preview');
  const codeDisplay = overlay.querySelector('#sidc-builder-code');
  const presetSelect = overlay.querySelector('#sidc-builder-preset');
  const ctxSelect = overlay.querySelector('#sidc-ctx');
  const idSelect = overlay.querySelector('#sidc-id');
  const ssSelect = overlay.querySelector('#sidc-ss');
  const statusSelect = overlay.querySelector('#sidc-status');
  const hqtfSelect = overlay.querySelector('#sidc-hqtf');
  const echSelect = overlay.querySelector('#sidc-ech');
  const searchInput = overlay.querySelector('#sidc-search');
  const treeContainer = overlay.querySelector('#sidc-tree');
  const mod1Select = overlay.querySelector('#sidc-mod1');
  const mod2Select = overlay.querySelector('#sidc-mod2');

  // ── Render functions ──

  function updatePreview() {
    const sidc = buildSidc(fields);
    codeDisplay.textContent = sidc;
    const url = renderSymbol(sidc, { size: 120 });
    previewImg.src = url;
  }

  function updateModifiers() {
    const mods1 = getModifiers(fields.symbolSet, 1);
    const mods2 = getModifiers(fields.symbolSet, 2);

    mod1Select.innerHTML = `<option value="00">None</option>` +
      mods1.map(m => `<option value="${m.code}" ${m.code === fields.mod1 ? 'selected' : ''}>${m.code} — ${m.name}</option>`).join('');

    mod2Select.innerHTML = `<option value="00">None</option>` +
      mods2.map(m => `<option value="${m.code}" ${m.code === fields.mod2 ? 'selected' : ''}>${m.code} — ${m.name}</option>`).join('');
  }

  function renderTree() {
    const query = searchText.toLowerCase();
    treeContainer.innerHTML = '';

    function matchesSearch(node) {
      if (!query) return true;
      if (node.name.toLowerCase().includes(query)) return true;
      return node.children.some(c => matchesSearch(c));
    }

    function renderNode(node) {
      if (!matchesSearch(node)) return;

      const hasChildren = node.children.length > 0;
      const isExpanded = expandedNodes.has(node.code) || query.length > 0;
      const selectedEntity6 = `${fields.entity}${fields.type}${fields.subtype}`;
      const isSelected = node.entity6 === selectedEntity6;

      const div = document.createElement('div');
      div.className = `sidc-tree-node ${node.level}${isSelected ? ' selected' : ''}`;

      const toggle = hasChildren
        ? `<span class="sidc-tree-toggle">${isExpanded ? '\u25BC' : '\u25B6'}</span>`
        : `<span class="sidc-tree-toggle">\u2022</span>`;

      div.innerHTML = `${toggle} ${node.name} <span style="color:#484F58;font-size:10px;margin-left:4px;">${node.entity6}</span>`;

      div.addEventListener('click', (e) => {
        e.stopPropagation();

        if (hasChildren) {
          if (expandedNodes.has(node.code)) {
            expandedNodes.delete(node.code);
          } else {
            expandedNodes.add(node.code);
          }
        }

        // Select this node
        fields.entity = node.entity6.slice(0, 2);
        fields.type = node.entity6.slice(2, 4);
        fields.subtype = node.entity6.slice(4, 6);

        renderTree();
        updatePreview();
      });

      treeContainer.appendChild(div);

      if (hasChildren && isExpanded) {
        for (const child of node.children) {
          renderNode(child);
        }
      }
    }

    for (const node of currentTree) {
      renderNode(node);
    }
  }

  // ── Wire events ──

  ctxSelect.addEventListener('change', () => {
    fields.context = ctxSelect.value;
    updatePreview();
  });

  idSelect.addEventListener('change', () => {
    fields.identity = idSelect.value;
    updatePreview();
  });

  ssSelect.addEventListener('change', () => {
    fields.symbolSet = ssSelect.value;
    // Reset entity selection
    fields.entity = '00';
    fields.type = '00';
    fields.subtype = '00';
    fields.mod1 = '00';
    fields.mod2 = '00';
    currentTree = buildEntityTree(fields.symbolSet);
    expandedNodes.clear();
    searchText = '';
    searchInput.value = '';
    renderTree();
    updateModifiers();
    updatePreview();
  });

  statusSelect.addEventListener('change', () => {
    fields.status = statusSelect.value;
    updatePreview();
  });

  hqtfSelect.addEventListener('change', () => {
    fields.hqtf = hqtfSelect.value;
    updatePreview();
  });

  echSelect.addEventListener('change', () => {
    fields.echelon = echSelect.value;
    updatePreview();
  });

  mod1Select.addEventListener('change', () => {
    fields.mod1 = mod1Select.value;
    updatePreview();
  });

  mod2Select.addEventListener('change', () => {
    fields.mod2 = mod2Select.value;
    updatePreview();
  });

  searchInput.addEventListener('input', () => {
    searchText = searchInput.value.trim();
    renderTree();
  });

  presetSelect.addEventListener('change', () => {
    const idx = parseInt(presetSelect.value, 10);
    const preset = PRESETS[idx];
    if (!preset || !preset.sidc) return;

    const pf = parseSidc(preset.sidc);
    Object.assign(fields, pf);

    // Update all dropdowns
    ctxSelect.value = fields.context;
    idSelect.value = fields.identity;
    ssSelect.value = fields.symbolSet;
    statusSelect.value = fields.status;
    hqtfSelect.value = fields.hqtf;
    echSelect.value = fields.echelon;

    currentTree = buildEntityTree(fields.symbolSet);
    expandedNodes.clear();
    searchText = '';
    searchInput.value = '';
    renderTree();
    updateModifiers();
    updatePreview();
  });

  // Copy SIDC
  overlay.querySelector('#sidc-builder-copy').addEventListener('click', () => {
    const sidc = buildSidc(fields);
    navigator.clipboard.writeText(sidc).then(() => {
      const btn = overlay.querySelector('#sidc-builder-copy');
      btn.textContent = 'Copied!';
      setTimeout(() => { btn.textContent = 'Copy SIDC'; }, 1500);
    });
  });

  codeDisplay.addEventListener('click', () => {
    const sidc = buildSidc(fields);
    navigator.clipboard.writeText(sidc);
  });

  // Cancel / Close
  function close() {
    overlay.remove();
  }

  overlay.querySelector('.sidc-modal-close').addEventListener('click', () => {
    close();
    if (onCancel) onCancel();
  });

  overlay.querySelector('#sidc-cancel').addEventListener('click', () => {
    close();
    if (onCancel) onCancel();
  });

  // Click overlay backdrop to close
  overlay.addEventListener('click', (e) => {
    if (e.target === overlay) {
      close();
      if (onCancel) onCancel();
    }
  });

  // Apply
  overlay.querySelector('#sidc-apply').addEventListener('click', () => {
    const sidc = buildSidc(fields);
    close();
    onApply(sidc);
  });

  // Escape key
  function onKeydown(e) {
    if (e.key === 'Escape') {
      close();
      if (onCancel) onCancel();
      document.removeEventListener('keydown', onKeydown);
    }
  }
  document.addEventListener('keydown', onKeydown);

  // ── Initial render ──

  updateModifiers();
  renderTree();
  updatePreview();

  // Auto-expand to show current selection
  if (fields.entity !== '00') {
    expandedNodes.add(fields.entity);
    if (fields.type !== '00') {
      const typeCode = `${fields.entity}${fields.type}`;
      expandedNodes.add(typeCode);
    }
    renderTree();
  }
}

// ── Helper: build <option> elements ──

function optionsFrom(map, selected) {
  return Object.entries(map)
    .map(([value, label]) => `<option value="${value}" ${value === selected ? 'selected' : ''}>${value} — ${label}</option>`)
    .join('');
}
