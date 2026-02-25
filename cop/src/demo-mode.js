/**
 * Demo mode — automated camera for presentations.
 *
 * When active, camera automatically repositions to focus on the action
 * as events fire. Operator can interrupt at any time by clicking the
 * globe, and resume by pressing the demo mode button.
 */

const CAMERA_PRESETS = {
  DETECTION:  { altitude: 150000, pitch: -45, duration: 2.0 },
  ALERT:      { altitude: 100000, pitch: -50, duration: 1.5 },
  ORDER:      { altitude: 50000,  pitch: -60, duration: 1.5 },
  INTERCEPT:  { altitude: 10000,  pitch: -70, duration: 2.0 },
  BOARDING:   { altitude: 3000,   pitch: -80, duration: 2.5 },
  INCIDENT:   { altitude: 20000,  pitch: -65, duration: 2.0 },
  RESOLUTION: { altitude: 200000, pitch: -45, duration: 3.0 },
  DEPLOY:     { altitude: 30000,  pitch: -55, duration: 1.5 },
  PURSUIT:    { altitude: 15000,  pitch: -65, duration: 2.0 },
  SEIZURE:    { altitude: 5000,   pitch: -75, duration: 2.0 }
};

export function initDemoMode(viewer, entityManager) {
  let active = false;
  let interrupted = false;

  function handleEvent(event) {
    if (!active || interrupted) return;

    const eventType = event.event_type || 'ALERT';
    const preset = CAMERA_PRESETS[eventType] || CAMERA_PRESETS.ALERT;

    let targetLon, targetLat;
    if (event.position) {
      targetLon = event.position.longitude;
      targetLat = event.position.latitude;
    } else if (event.target) {
      const entity = entityManager.getEntity(event.target);
      if (entity && entity.position) {
        targetLon = entity.position.longitude;
        targetLat = entity.position.latitude;
      }
    }

    if (targetLon != null && targetLat != null) {
      viewer.camera.flyTo({
        destination: Cesium.Cartesian3.fromDegrees(targetLon, targetLat, preset.altitude),
        orientation: {
          heading: 0,
          pitch: Cesium.Math.toRadians(preset.pitch),
          roll: 0
        },
        duration: preset.duration
      });
    }

    showEventOverlay(event.description, event.severity || 'INFO');
  }

  function showEventOverlay(text, severity) {
    const overlay = document.getElementById('event-overlay');
    if (!overlay) return;
    overlay.textContent = text;
    overlay.className = `event-overlay severity-${severity.toLowerCase()} visible`;
    setTimeout(() => overlay.classList.remove('visible'), 4000);
  }

  // Interrupt on user camera interaction
  const handler = new Cesium.ScreenSpaceEventHandler(viewer.scene.canvas);
  handler.setInputAction(() => {
    if (active) interrupted = true;
  }, Cesium.ScreenSpaceEventType.LEFT_DOWN);

  // Keyboard shortcut
  document.addEventListener('keydown', (e) => {
    if (e.target.tagName === 'INPUT') return;
    if (e.key === 'd' || e.key === 'D') {
      if (!e.ctrlKey && !e.metaKey) toggle();
    }
    if (e.key === 'r' || e.key === 'R') {
      if (!e.ctrlKey && !e.metaKey) {
        if (active && interrupted) resume();
      }
    }
  });

  function toggle() {
    active = !active;
    interrupted = false;
    const btn = document.getElementById('btn-demo-mode');
    if (btn) btn.classList.toggle('active', active);
    return active;
  }

  function resume() {
    interrupted = false;
  }

  return {
    toggle,
    isActive: () => active,
    handleEvent,
    interrupt: () => { interrupted = true; },
    resume
  };
}
