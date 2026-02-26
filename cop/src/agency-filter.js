/**
 * Agency filter panel — left sidebar.
 * Toggle visibility per agency and domain.
 * Sections are collapsible.
 */

export function initAgencyFilter(containerId, entityManager, config) {
  const container = document.getElementById(containerId);
  if (!container) return;

  // Build HTML with collapsible sections
  container.innerHTML = `
    <div class="filter-section" id="filter-section-agencies">
      <div class="filter-section-header" data-target="agency-filters">
        <span class="filter-section-title">Agencies</span>
        <span class="filter-section-chevron">\u25bc</span>
      </div>
      <div class="filter-group filter-collapsible" id="agency-filters"></div>
    </div>
    <div class="filter-section" id="filter-section-domains">
      <div class="filter-section-header" data-target="domain-filters">
        <span class="filter-section-title">Domains</span>
        <span class="filter-section-chevron">\u25bc</span>
      </div>
      <div class="filter-group filter-collapsible" id="domain-filters"></div>
    </div>
    <div class="stats-section" id="filter-stats"></div>
    <div class="filter-section" id="filter-section-entities">
      <div class="filter-section-header" data-target="entity-list">
        <span class="filter-section-title">Entities</span>
        <span class="filter-section-chevron">\u25b6</span>
      </div>
      <div class="filter-group filter-collapsible collapsed" id="entity-list" style="max-height: 300px; overflow-y: auto;"></div>
    </div>
  `;

  const agencyGroup = document.getElementById('agency-filters');
  const domainGroup = document.getElementById('domain-filters');
  const statsEl = document.getElementById('filter-stats');

  // Wire collapsible section headers
  container.querySelectorAll('.filter-section-header').forEach(header => {
    header.addEventListener('click', () => {
      const targetId = header.dataset.target;
      const body = document.getElementById(targetId);
      const chevron = header.querySelector('.filter-section-chevron');
      if (body.classList.toggle('collapsed')) {
        chevron.textContent = '\u25b6';
      } else {
        chevron.textContent = '\u25bc';
      }
    });
  });

  // Agency toggles
  for (const [key, label] of Object.entries(config.agencyLabels)) {
    const color = config.agencyColors[key];
    const toggle = document.createElement('div');
    toggle.className = 'filter-toggle';
    toggle.dataset.agency = key;
    toggle.innerHTML = `
      <div class="filter-swatch" style="background: ${color}"></div>
      <span class="filter-label">${key}</span>
      <span class="filter-count" id="count-agency-${key}">0</span>
    `;
    toggle.addEventListener('click', () => {
      const hidden = toggle.classList.toggle('hidden');
      entityManager.setAgencyFilter(key, !hidden);
    });
    agencyGroup.appendChild(toggle);
  }

  // Domain toggles
  for (const [key, label] of Object.entries(config.domainLabels)) {
    const icon = config.domainIcons[key] || '';
    const toggle = document.createElement('div');
    toggle.className = 'filter-toggle';
    toggle.dataset.domain = key;
    toggle.innerHTML = `
      <span style="font-size: 14px">${icon}</span>
      <span class="filter-label">${label}</span>
      <span class="filter-count" id="count-domain-${key}">0</span>
    `;
    toggle.addEventListener('click', () => {
      const hidden = toggle.classList.toggle('hidden');
      entityManager.setDomainFilter(key, !hidden);
    });
    domainGroup.appendChild(toggle);
  }

  const entityListEl = document.getElementById('entity-list');

  // Entity click callbacks (BUG-015)
  const entityClickCallbacks = [];

  // Update counts periodically
  let lastEntityListHash = '';

  function updateCounts() {
    const agencyCounts = entityManager.getCountByAgency();
    const domainCounts = entityManager.getCountByDomain();

    for (const key of Object.keys(config.agencyLabels)) {
      const el = document.getElementById(`count-agency-${key}`);
      if (el) el.textContent = agencyCounts[key] || 0;
    }
    for (const key of Object.keys(config.domainLabels)) {
      const el = document.getElementById(`count-domain-${key}`);
      if (el) el.textContent = domainCounts[key] || 0;
    }

    const total = entityManager.getEntityCount();
    statsEl.innerHTML = `
      <div class="stat-row">
        <span class="stat-label">Total Entities</span>
        <span class="stat-value">${total}</span>
      </div>
    `;

    // Update entity list if visible and changed
    if (entityListEl && !entityListEl.classList.contains('collapsed')) {
      updateEntityList();
    }
  }

  function updateEntityList() {
    const allEntities = entityManager.getAllEntities();
    // Simple hash to avoid unnecessary re-renders
    const hash = allEntities.map(e => e.entity_id).join(',');
    if (hash === lastEntityListHash) return;
    lastEntityListHash = hash;

    entityListEl.innerHTML = '';
    // Sort by agency then callsign
    const sorted = [...allEntities].sort((a, b) => {
      const agencyDiff = (a.agency || '').localeCompare(b.agency || '');
      if (agencyDiff !== 0) return agencyDiff;
      return (a.callsign || a.entity_id || '').localeCompare(b.callsign || b.entity_id || '');
    });

    for (const entity of sorted) {
      const row = document.createElement('div');
      row.className = 'filter-toggle entity-row';
      row.dataset.unitId = entity.entity_id;
      row.style.cssText = 'cursor: pointer; padding: 3px 8px;';
      const color = config.agencyColors[entity.agency] || '#78909C';
      row.innerHTML = `
        <div class="filter-swatch" style="background: ${color}; width: 6px; height: 6px;"></div>
        <span class="filter-label" style="font-size: 11px; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${entity.callsign || entity.entity_id}</span>
      `;
      row.addEventListener('click', () => {
        for (const cb of entityClickCallbacks) {
          cb(entity);
        }
      });
      entityListEl.appendChild(row);
    }
  }

  setInterval(updateCounts, 1000);
  updateCounts();

  return {
    updateCounts,
    onEntityClick(fn) { entityClickCallbacks.push(fn); }
  };
}
