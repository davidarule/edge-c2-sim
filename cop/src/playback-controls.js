/**
 * Playback controls — bottom bar showing scenario progress.
 * Play/pause, speed, and reset have moved to the header bar.
 */

export function initPlaybackControls(containerId, ws, config) {
  const container = document.getElementById(containerId);
  if (!container) return {};

  container.innerHTML = `
    <div class="controls-progress-only">
      <div class="progress-bar" id="progress-bar">
        <div class="progress-fill" id="progress-fill"></div>
      </div>
    </div>
  `;

  const progressFill = document.getElementById('progress-fill');

  function updateClock(clockState) {
    if (clockState.scenario_progress !== undefined && progressFill) {
      progressFill.style.width = `${(clockState.scenario_progress * 100).toFixed(1)}%`;
    }
  }

  return { updateClock };
}
