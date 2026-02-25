/**
 * WebSocket client with auto-reconnect.
 *
 * Connects to simulation engine, dispatches messages to callbacks.
 * Sends commands (speed, pause, resume, reset) back to simulator.
 */

import ReconnectingWebSocket from 'reconnecting-websocket';

export function connectWebSocket(url, handlers) {
  console.log(`Connecting to WebSocket: ${url}`);

  const ws = new ReconnectingWebSocket(url, [], {
    maxRetries: 50,
    reconnectionDelayGrowFactor: 1.3,
    maxReconnectionDelay: 10000,
    minReconnectionDelay: 1000
  });

  ws.addEventListener('open', () => {
    console.log('WebSocket connected to simulator');
    updateConnectionStatus('connected');
    // Request initial snapshot
    ws.send(JSON.stringify({ cmd: 'snapshot' }));
  });

  ws.addEventListener('close', () => {
    console.log('WebSocket disconnected');
    updateConnectionStatus('disconnected');
  });

  ws.addEventListener('error', (err) => {
    console.warn('WebSocket error:', err);
  });

  ws.addEventListener('message', (event) => {
    try {
      const msg = JSON.parse(event.data);

      switch (msg.type) {
        case 'snapshot':
          if (handlers.onSnapshot) handlers.onSnapshot(msg.entities || []);
          break;
        case 'entity_update':
          if (handlers.onEntityUpdate) handlers.onEntityUpdate(msg.entity);
          break;
        case 'entity_batch':
          if (handlers.onEntityUpdate && msg.entities) {
            msg.entities.forEach(e => handlers.onEntityUpdate(e));
          }
          break;
        case 'entity_remove':
          if (handlers.onEntityRemove) handlers.onEntityRemove(msg.entity_id);
          break;
        case 'event':
          if (handlers.onEvent) handlers.onEvent(msg.event);
          break;
        case 'clock':
          if (handlers.onClock) handlers.onClock(msg);
          break;
        case 'routes':
          if (handlers.onRoutes) handlers.onRoutes(msg.routes);
          break;
        default:
          console.debug('Unknown message type:', msg.type);
      }
    } catch (e) {
      console.warn('Failed to parse WebSocket message:', e);
    }
  });

  return {
    raw: ws,
    setSpeed: (speed) => ws.send(JSON.stringify({ cmd: 'set_speed', speed })),
    pause: () => ws.send(JSON.stringify({ cmd: 'pause' })),
    resume: () => ws.send(JSON.stringify({ cmd: 'resume' })),
    reset: () => ws.send(JSON.stringify({ cmd: 'reset' })),
    restart: () => ws.send(JSON.stringify({ cmd: 'restart' })),
    requestSnapshot: () => ws.send(JSON.stringify({ cmd: 'snapshot' })),
    updateSidc: (entityType, sidc) => ws.send(JSON.stringify({
      cmd: 'update_sidc', entity_type: entityType, sidc
    }))
  };
}

function updateConnectionStatus(status) {
  const indicator = document.getElementById('connection-status');
  if (indicator) {
    indicator.className = `connection-${status}`;
    indicator.textContent = status === 'connected' ? '\u25cf LIVE' : '\u25cb DISCONNECTED';
  }
}
