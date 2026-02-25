/**
 * Context Menu — reusable right-click context menu for the Scenario Builder.
 *
 * Shows a positioned menu with items, submenus, dividers.
 * Dismisses on click outside, ESC, or item click.
 */

const MENU_STYLES = `
  .builder-ctx-menu {
    position: fixed;
    z-index: 10001;
    min-width: 180px;
    background: #161B22;
    border: 1px solid #30363D;
    border-radius: 4px;
    padding: 4px 0;
    font-family: 'IBM Plex Sans', sans-serif;
    font-size: 12px;
    color: #C9D1D9;
    box-shadow: 0 4px 16px rgba(0,0,0,0.4);
  }
  .builder-ctx-item {
    padding: 6px 12px;
    cursor: pointer;
    display: flex;
    align-items: center;
    gap: 8px;
    white-space: nowrap;
  }
  .builder-ctx-item:hover {
    background: #21262D;
  }
  .builder-ctx-item.danger:hover {
    background: rgba(248,81,73,0.15);
    color: #F85149;
  }
  .builder-ctx-item .ctx-icon {
    width: 16px; text-align: center;
    font-size: 12px; color: #8B949E;
  }
  .builder-ctx-item:hover .ctx-icon {
    color: #C9D1D9;
  }
  .builder-ctx-item.danger:hover .ctx-icon {
    color: #F85149;
  }
  .builder-ctx-divider {
    height: 1px;
    background: #30363D;
    margin: 4px 0;
  }
  .builder-ctx-label {
    padding: 4px 12px;
    font-size: 10px;
    color: #484F58;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }
`;

let stylesInjected = false;
function injectStyles() {
  if (stylesInjected) return;
  const style = document.createElement('style');
  style.textContent = MENU_STYLES;
  document.head.appendChild(style);
  stylesInjected = true;
}

let activeMenu = null;

function dismissMenu() {
  if (activeMenu) {
    activeMenu.remove();
    activeMenu = null;
  }
  document.removeEventListener('click', onDocClick);
  document.removeEventListener('keydown', onDocKeydown);
  document.removeEventListener('contextmenu', onDocContext);
}

function onDocClick() { dismissMenu(); }
function onDocKeydown(e) { if (e.key === 'Escape') dismissMenu(); }
function onDocContext() { dismissMenu(); }

/**
 * Show a context menu at the given screen position.
 *
 * @param {number} x - Screen X
 * @param {number} y - Screen Y
 * @param {Array} items - Menu items:
 *   { label, icon?, action, danger? }
 *   { divider: true }
 *   { header: 'Section Label' }
 * @param {function} onAction - Callback: (action) => void
 */
export function showContextMenu(x, y, items, onAction) {
  injectStyles();
  dismissMenu();

  const menu = document.createElement('div');
  menu.className = 'builder-ctx-menu';

  for (const item of items) {
    if (item.divider) {
      const div = document.createElement('div');
      div.className = 'builder-ctx-divider';
      menu.appendChild(div);
      continue;
    }

    if (item.header) {
      const lbl = document.createElement('div');
      lbl.className = 'builder-ctx-label';
      lbl.textContent = item.header;
      menu.appendChild(lbl);
      continue;
    }

    const el = document.createElement('div');
    el.className = `builder-ctx-item${item.danger ? ' danger' : ''}`;
    el.innerHTML = `
      ${item.icon ? `<span class="ctx-icon">${item.icon}</span>` : ''}
      <span>${item.label}</span>
    `;
    el.addEventListener('click', (e) => {
      e.stopPropagation();
      dismissMenu();
      if (onAction) onAction(item.action);
    });
    menu.appendChild(el);
  }

  document.body.appendChild(menu);
  activeMenu = menu;

  // Position with viewport bounds checking
  const rect = menu.getBoundingClientRect();
  const viewW = window.innerWidth;
  const viewH = window.innerHeight;

  let left = x;
  let top = y;

  if (left + rect.width > viewW) {
    left = viewW - rect.width - 8;
  }
  if (top + rect.height > viewH) {
    top = viewH - rect.height - 8;
  }
  if (left < 0) left = 8;
  if (top < 0) top = 8;

  menu.style.left = `${left}px`;
  menu.style.top = `${top}px`;

  // Dismiss on next tick to avoid catching the opening click
  requestAnimationFrame(() => {
    document.addEventListener('click', onDocClick);
    document.addEventListener('keydown', onDocKeydown);
    document.addEventListener('contextmenu', onDocContext);
  });
}

/**
 * Dismiss any open context menu.
 */
export { dismissMenu };

// ── Predefined menu templates ──

/**
 * Entity context menu items for right-clicking an entity on the map.
 */
export function entityMenuItems(entity) {
  return [
    { header: entity.callsign || entity.id },
    { label: 'Edit Properties', icon: '\u270E', action: 'edit' },
    { label: 'Set Behavior', icon: '\u2699', action: 'set-behavior' },
    { label: 'Define Route', icon: '\u2B9E', action: 'define-route' },
    { label: 'Add Event', icon: '\u26A1', action: 'add-event-for-entity' },
    { divider: true },
    { label: 'Duplicate', icon: '\u2398', action: 'duplicate' },
    { label: 'Fly To', icon: '\u2708', action: 'fly-to' },
    { label: 'Show in Panel', icon: '\u2261', action: 'show-in-panel' },
    { divider: true },
    { label: 'Remove', icon: '\u2715', action: 'remove', danger: true },
  ];
}

/**
 * Map context menu items for right-clicking on empty map space.
 */
export function mapMenuItems(position) {
  const posStr = position
    ? `${position.latitude.toFixed(5)}, ${position.longitude.toFixed(5)}`
    : 'N/A';
  return [
    { header: posStr },
    { label: 'Add Entity Here', icon: '\u2295', action: 'add-entity' },
    { label: 'Add Waypoint Here', icon: '\u2B24', action: 'add-waypoint' },
    { label: 'Add Reference Point', icon: '\u2316', action: 'add-reference' },
    { divider: true },
    { label: 'Copy Coordinates', icon: '\u2398', action: 'copy-coords' },
    { label: 'Center Map Here', icon: '\u2316', action: 'center-map' },
    { label: 'Measure from Here', icon: '\uD83D\uDCCF', action: 'measure' },
  ];
}
