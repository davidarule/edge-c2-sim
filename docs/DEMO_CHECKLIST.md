# Demo Day Checklist

## Day Before

- [ ] Docker images built and tested on demo laptop
- [ ] .env file configured with Cesium Ion token
- [ ] Internet access verified (Cesium tile loading)
- [ ] OR: Cesium tile cache populated for offline use
- [ ] Scenario runs start-to-finish without errors
- [ ] External display tested (resolution, HDMI/USB-C)
- [ ] Browser: Chrome, fullscreen, bookmark to localhost:3000
- [ ] Backup: second laptop with same setup

## 1 Hour Before

- [ ] `docker-compose up`
- [ ] Open http://localhost:3000 in Chrome
- [ ] Verify entities appear on globe
- [ ] Run through first 2 minutes at 5x to verify
- [ ] Reset scenario
- [ ] Connect external display
- [ ] Set browser to fullscreen (F11)
- [ ] Test audio (if presenting with narration)

## During Demo

- [ ] Start with scenario paused — show the ESSZONE overview
- [ ] Press Play at 5x speed
- [ ] Enable demo mode (D key) for auto-camera
- [ ] Slow to 2x during action sequences
- [ ] 1x during boarding/resolution for dramatic effect
- [ ] Use agency filters to highlight specific forces
- [ ] Click entities to show detail panel when discussing

## Troubleshooting

- **COP blank/not loading:** Check Cesium token in .env, check internet
- **No entities:** Check simulator health: `curl http://localhost:8766/health`
- **Entities frozen:** Check WebSocket: browser console should show updates
- **Slow/laggy:** Close other browser tabs, reduce speed
- **Display issues:** Try Ctrl+F5 to force reload
