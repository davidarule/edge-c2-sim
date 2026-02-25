/**
 * Playback controls — bottom bar with play/pause/speed and clock.
 */

export function initPlaybackControls(containerId, ws, config) {
  const container = document.getElementById(containerId);
  if (!container) return {};

  let running = false;
  let currentSpeed = config.defaultSpeed;
  let simTime = '';
  let progress = 0;

  container.innerHTML = `
    <div class="controls-left">
      <button class="ctrl-btn" id="btn-play-pause">&#9654; PLAY</button>
      <div class="speed-group" id="speed-group"></div>
      <button class="ctrl-btn danger" id="btn-reset">&#10226; RESET</button>
    </div>
    <div class="controls-center">
      <div class="progress-bar" id="progress-bar">
        <div class="progress-fill" id="progress-fill"></div>
      </div>
    </div>
    <div class="controls-right">
      <span class="controls-clock" id="sim-clock">--:--:--</span>
    </div>
  `;

  const playPauseBtn = document.getElementById('btn-play-pause');
  const speedGroup = document.getElementById('speed-group');
  const resetBtn = document.getElementById('btn-reset');
  const simClock = document.getElementById('sim-clock');
  const progressFill = document.getElementById('progress-fill');

  // Speed buttons
  config.speeds.forEach(speed => {
    const btn = document.createElement('button');
    btn.className = 'speed-btn' + (speed === currentSpeed ? ' active' : '');
    btn.textContent = `${speed}x`;
    btn.dataset.speed = speed;
    btn.addEventListener('click', () => {
      currentSpeed = speed;
      if (ws) ws.setSpeed(speed);
      speedGroup.querySelectorAll('.speed-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
    });
    speedGroup.appendChild(btn);
  });

  // Play/Pause
  playPauseBtn.addEventListener('click', () => {
    if (running) {
      if (ws) ws.pause();
    } else {
      if (ws) ws.resume();
    }
  });

  // Reset
  resetBtn.addEventListener('click', () => {
    if (confirm('Reset scenario to beginning?')) {
      if (ws) ws.reset();
    }
  });

  function updateClock(clockState) {
    if (clockState.sim_time) {
      simTime = clockState.sim_time;
      const d = new Date(simTime);
      simClock.textContent = d.toISOString().substring(11, 19);
    }
    if (clockState.running !== undefined) {
      running = clockState.running;
      playPauseBtn.innerHTML = running ? '&#9208; PAUSE' : '&#9654; PLAY';
      container.className = running ? '' : 'paused';
    }
    if (clockState.speed !== undefined) {
      currentSpeed = clockState.speed;
      speedGroup.querySelectorAll('.speed-btn').forEach(b => {
        b.classList.toggle('active', parseFloat(b.dataset.speed) === currentSpeed);
      });
    }
    if (clockState.scenario_progress !== undefined) {
      progress = clockState.scenario_progress;
      progressFill.style.width = `${(progress * 100).toFixed(1)}%`;
    }
  }

  // Keyboard shortcuts
  document.addEventListener('keydown', (e) => {
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;

    switch (e.key) {
      case ' ':
        e.preventDefault();
        playPauseBtn.click();
        break;
      case '1': if (ws) ws.setSpeed(1); break;
      case '2': if (ws) ws.setSpeed(2); break;
      case '3': if (ws) ws.setSpeed(5); break;
      case '4': if (ws) ws.setSpeed(10); break;
      case '5': if (ws) ws.setSpeed(60); break;
      case 'f':
      case 'F':
        if (!e.ctrlKey && !e.metaKey) {
          e.preventDefault();
          if (document.fullscreenElement) document.exitFullscreen();
          else document.documentElement.requestFullscreen();
        }
        break;
    }
  });

  return { updateClock };
}
