/**
 * Agency filter panel — left sidebar.
 * Toggle visibility per agency and domain.
 */

export function initAgencyFilter(containerId, entityManager, config) {
  const container = document.getElementById(containerId);
  if (!container) return;

  // Build HTML
  container.innerHTML = `
    <div class="filter-section">
      <div class="filter-section-title">Agencies</div>
      <div class="filter-group" id="agency-filters"></div>
    </div>
    <div class="filter-section">
      <div class="filter-section-title">Domains</div>
      <div class="filter-group" id="domain-filters"></div>
    </div>
    <div class="stats-section" id="filter-stats"></div>
  `;

  const agencyGroup = document.getElementById('agency-filters');
  const domainGroup = document.getElementById('domain-filters');
  const statsEl = document.getElementById('filter-stats');

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

  // Update counts periodically
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
  }

  setInterval(updateCounts, 1000);
  updateCounts();

  return { updateCounts };
}
