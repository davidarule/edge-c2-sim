/**
 * Builder Mode Controller — handles PLAY ↔ BUILD mode switching.
 *
 * BUILD mode:
 *   - Disconnects WebSocket live feed
 *   - Shows ORBAT panel in left sidebar (replaces agency filter)
 *   - Shows Asset Detail in right sidebar (replaces entity panel)
 *   - Enables map interaction handlers for entity placement
 *   - Shows builder toolbar
 *
 * PLAY mode (default):
 *   - Normal COP operation: WebSocket, playback, timeline, filters
 */

let currentMode = 'PLAY';
let listeners = [];

// References set during init
let playComponents = null;   // { sidebar, detail, controls, timeline, settings, ws }
let buildComponents = null;  // { orbatPanel, assetDetail }
let headerEl = null;

/**
 * Inject the PLAY/BUILD toggle into the header and wire up mode switching.
 *
 * @param {object} opts
 * @param {HTMLElement} opts.header         - Header element
 * @param {object}      opts.playComponents - { sidebar, detail, controls, timeline, settings }
 * @param {object}      opts.ws             - WebSocket client (with disconnect/reconnect)
 * @param {function}    opts.onModeChange   - Callback: (mode) => void
 * @returns {{ getMode, setMode, onModeChange }}
 */
export function initBuilderMode(opts) {
  headerEl = opts.header || document.getElementById('header');
  playComponents = opts.playComponents || {};

  // ── Inject mode toggle into header ──

  const toggleContainer = document.createElement('div');
  toggleContainer.className = 'mode-toggle';
  toggleContainer.innerHTML = `
    <button class="mode-btn active" data-mode="PLAY">PLAY</button>
    <button class="mode-btn" data-mode="BUILD">BUILD</button>
  `;

  // Insert after the header-left section
  const headerLeft = headerEl.querySelector('.header-left');
  if (headerLeft) {
    headerLeft.after(toggleContainer);
  } else {
    headerEl.prepend(toggleContainer);
  }

  // Inject styles
  const style = document.createElement('style');
  style.textContent = `
    .mode-toggle {
      display: flex;
      gap: 0;
      border: 1px solid var(--border);
      border-radius: 4px;
      overflow: hidden;
      margin-left: 8px;
    }
    .mode-btn {
      background: transparent;
      border: none;
      color: var(--text-secondary);
      font-family: var(--font-sans);
      font-size: 11px;
      font-weight: 600;
      letter-spacing: 0.8px;
      padding: 4px 12px;
      cursor: pointer;
      transition: all 0.15s;
    }
    .mode-btn:hover {
      color: var(--text-primary);
      background: var(--bg-tertiary);
    }
    .mode-btn.active[data-mode="PLAY"] {
      background: rgba(63, 185, 80, 0.15);
      color: var(--status-active);
    }
    .mode-btn.active[data-mode="BUILD"] {
      background: rgba(88, 166, 255, 0.15);
      color: var(--severity-info);
    }

    /* BUILD mode layout adjustments */
    #app.build-mode {
      grid-template-columns: 260px 1fr 0px;
      grid-template-rows: 48px 1fr 0px 0px;
      grid-template-areas:
        "header   header  header"
        "sidebar  viewport detail"
        "controls controls controls"
        "timeline timeline timeline";
    }
    #app.build-mode.detail-open {
      grid-template-columns: 260px 1fr 300px;
    }
    #app.build-mode #controls,
    #app.build-mode #timeline {
      display: none;
    }

    /* Builder sidebar */
    .builder-sidebar {
      display: none;
      flex-direction: column;
      height: 100%;
      overflow: hidden;
      background: var(--bg-secondary);
      border-right: 1px solid var(--border);
    }
    .build-mode .builder-sidebar { display: flex; }
    .build-mode .play-sidebar { display: none; }

    /* Builder right panel */
    .builder-detail {
      display: none;
      flex-direction: column;
      height: 100%;
      overflow: hidden;
      background: var(--bg-secondary);
      border-left: 1px solid var(--border);
    }
    .build-mode .builder-detail { display: flex; }
    .build-mode .play-detail { display: none; }
  `;
  document.head.appendChild(style);

  // ── Wire toggle buttons ──

  toggleContainer.querySelectorAll('.mode-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      setMode(btn.dataset.mode);
    });
  });

  // ── Mode switching logic ──

  function setMode(mode) {
    if (mode === currentMode) return;
    currentMode = mode;

    const app = document.getElementById('app');

    // Update toggle buttons
    toggleContainer.querySelectorAll('.mode-btn').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.mode === mode);
    });

    if (mode === 'BUILD') {
      app.classList.add('build-mode');
      // Notify listeners
      listeners.forEach(fn => fn('BUILD'));
      if (opts.onModeChange) opts.onModeChange('BUILD');
    } else {
      app.classList.remove('build-mode');
      app.classList.remove('detail-open');
      listeners.forEach(fn => fn('PLAY'));
      if (opts.onModeChange) opts.onModeChange('PLAY');
    }
  }

  function getMode() {
    return currentMode;
  }

  function onModeChange(fn) {
    listeners.push(fn);
    return () => {
      listeners = listeners.filter(l => l !== fn);
    };
  }

  return { getMode, setMode, onModeChange };
}

/**
 * Setup the builder sidebar containers in the DOM.
 * Call this during app initialization to create the sidebar wrappers.
 *
 * @param {HTMLElement} leftSidebar  - The #sidebar-left element
 * @param {HTMLElement} rightSidebar - The #sidebar-right element
 * @returns {{ builderLeft: HTMLElement, builderRight: HTMLElement }}
 */
export function createBuilderContainers(leftSidebar, rightSidebar) {
  // Wrap existing play-mode content
  const playLeftContent = leftSidebar.querySelector('.agency-filter') ||
                          leftSidebar.firstElementChild;
  if (playLeftContent && !playLeftContent.classList.contains('play-sidebar')) {
    // Wrap all existing children in a play-sidebar div
    const playWrapper = document.createElement('div');
    playWrapper.className = 'play-sidebar';
    playWrapper.style.cssText = 'display: flex; flex-direction: column; height: 100%; overflow: hidden;';
    while (leftSidebar.firstChild) {
      playWrapper.appendChild(leftSidebar.firstChild);
    }
    leftSidebar.appendChild(playWrapper);
  }

  // Create builder sidebar container
  const builderLeft = document.createElement('div');
  builderLeft.className = 'builder-sidebar';
  builderLeft.id = 'builder-sidebar-left';
  leftSidebar.appendChild(builderLeft);

  // Right sidebar: wrap existing play content
  const playRightContent = rightSidebar.firstElementChild;
  if (playRightContent && !playRightContent.classList.contains('play-detail')) {
    const playWrapper = document.createElement('div');
    playWrapper.className = 'play-detail';
    playWrapper.style.cssText = 'display: flex; flex-direction: column; height: 100%; overflow: hidden;';
    while (rightSidebar.firstChild) {
      playWrapper.appendChild(rightSidebar.firstChild);
    }
    rightSidebar.appendChild(playWrapper);
  }

  // Create builder detail container
  const builderRight = document.createElement('div');
  builderRight.className = 'builder-detail';
  builderRight.id = 'builder-sidebar-right';
  rightSidebar.appendChild(builderRight);

  return { builderLeft, builderRight };
}
