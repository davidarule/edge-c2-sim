/**
 * Compass widget — SVG compass rose that rotates with camera heading.
 * Positioned bottom-right of cesium-container.
 */

export function initCompass(viewer) {
  const container = document.getElementById('cesium-container');

  const wrapper = document.createElement('div');
  wrapper.id = 'compass-widget';
  wrapper.style.cssText = `
    position: absolute; bottom: 12px; right: 12px; z-index: 20;
    width: 80px; height: 80px; pointer-events: none;
  `;

  wrapper.innerHTML = `
    <svg id="compass-rose" viewBox="0 0 100 100" width="80" height="80" xmlns="http://www.w3.org/2000/svg">
      <!-- Outer ring -->
      <circle cx="50" cy="50" r="46" fill="rgba(13,17,23,0.7)" stroke="#30363D" stroke-width="1.5"/>
      <!-- Tick marks -->
      <line x1="50" y1="6" x2="50" y2="14" stroke="#8B949E" stroke-width="1"/>
      <line x1="50" y1="86" x2="50" y2="94" stroke="#8B949E" stroke-width="1"/>
      <line x1="6" y1="50" x2="14" y2="50" stroke="#8B949E" stroke-width="1"/>
      <line x1="86" y1="50" x2="94" y2="50" stroke="#8B949E" stroke-width="1"/>
      <!-- Compass diamond -->
      <polygon points="50,12 56,50 50,88 44,50" fill="none" stroke="#30363D" stroke-width="0.5"/>
      <!-- North pointer (red) -->
      <polygon points="50,12 56,50 44,50" fill="#F85149" opacity="0.8"/>
      <!-- South pointer (dim) -->
      <polygon points="50,88 56,50 44,50" fill="#8B949E" opacity="0.3"/>
      <!-- Center dot -->
      <circle cx="50" cy="50" r="3" fill="#C9D1D9"/>
      <!-- Cardinal labels -->
      <text x="50" y="24" text-anchor="middle" fill="#F85149" font-family="IBM Plex Sans, sans-serif" font-size="10" font-weight="600">N</text>
      <text x="50" y="82" text-anchor="middle" fill="#8B949E" font-family="IBM Plex Sans, sans-serif" font-size="9">S</text>
      <text x="18" y="54" text-anchor="middle" fill="#8B949E" font-family="IBM Plex Sans, sans-serif" font-size="9">W</text>
      <text x="82" y="54" text-anchor="middle" fill="#8B949E" font-family="IBM Plex Sans, sans-serif" font-size="9">E</text>
    </svg>
  `;

  container.appendChild(wrapper);

  const roseSvg = document.getElementById('compass-rose');

  function update() {
    const heading = Cesium.Math.toDegrees(viewer.camera.heading);
    roseSvg.style.transform = `rotate(${-heading}deg)`;
  }

  viewer.camera.changed.addEventListener(update);
  viewer.camera.moveEnd.addEventListener(update);
  update();
}
