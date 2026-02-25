# Claude Code — Phase 4 Task Brief: Edge C2 REST Adapter & TAK Integration

## Context

Phases 0-3 built a working simulation + COP. Phase 4 connects the simulator 
to the actual Edge C2 system via its REST API, and optionally to TAK endpoints 
via Cursor on Target (CoT) XML. This is where the simulator becomes a real 
integration layer rather than a standalone demo.

**Read first:**
- `config/edge_c2_api.yaml` — OpenAPI 3.0 stub (to be replaced with real spec)
- `edge-c2-simulator-plan.md` — REST adapter architecture

After Phase 4, the simulator pushes data to Edge C2 in real-time, and can 
optionally feed TAK clients (ATAK/WinTAK) via FreeTAKServer.

---

## Task 1: REST Adapter (`simulator/transport/rest_adapter.py`)

The REST adapter reads the Edge C2 OpenAPI spec and maps entity updates to 
HTTP API calls. It must be **spec-driven** — when the real API spec arrives, 
swapping the YAML file should be the only change needed.

```python
"""
REST API transport adapter for Edge C2.

Reads an OpenAPI 3.0 spec to determine endpoints, maps entity updates
to API payloads, handles authentication and retries. Supports both
individual entity updates (high-frequency) and batch mode (efficient).

Design principle: The spec is the contract. When the real Edge C2 API 
spec arrives, swap the YAML and everything regenerates.
"""

import aiohttp
import yaml
from typing import Optional

class RESTAdapter(TransportBase):
    def __init__(
        self,
        api_spec_path: str = "config/edge_c2_api.yaml",
        base_url: str = "http://localhost:9000",
        api_key: Optional[str] = None,
        bearer_token: Optional[str] = None,
        batch_mode: bool = True,
        batch_interval_s: float = 1.0,
        dry_run: bool = False,   # Log payloads without sending
        max_retries: int = 3
    ):
        """
        api_spec_path: Path to OpenAPI 3.0 YAML spec
        base_url: Edge C2 API base URL
        api_key: X-API-Key header value (if spec uses apiKey auth)
        bearer_token: Bearer token (if spec uses bearer auth)
        batch_mode: Accumulate updates, send in bulk every batch_interval_s
        dry_run: Generate and log payloads without making HTTP requests
        """
    
    async def initialize(self):
        """
        1. Load and parse OpenAPI spec
        2. Build endpoint mapping from spec paths
        3. Extract schema definitions for payload validation
        4. Create aiohttp session with auth headers
        """
    
    async def push_entity_update(self, entity: dict):
        """
        Map entity to API payload and send.
        
        Uses spec to determine:
        - Which endpoint: POST /entities/{id}/position (lightweight)
        - Payload structure: from PositionUpdate schema in spec
        - Required fields: from schema's 'required' list
        """
    
    async def push_bulk_update(self, entities: list[dict]):
        """
        If spec has a bulk endpoint (POST /entities/bulk), use it.
        Otherwise, send individual updates sequentially.
        """
    
    async def push_event(self, event: dict):
        """
        Map scenario event to API event payload.
        Uses: POST /events endpoint from spec.
        """
    
    async def push_ais_signal(self, nmea_sentence: str):
        """
        Push raw AIS NMEA to Edge C2 signals endpoint.
        Uses: POST /signals/ais (if spec has this endpoint).
        """
    
    async def push_adsb_signal(self, sbs_message: str):
        """
        Push ADS-B SBS message to Edge C2.
        Uses: POST /signals/adsb (if spec has this endpoint).
        """
    
    async def health_check(self) -> bool:
        """
        Hit GET /health endpoint. Return True if 200 OK.
        Used by main loop to verify Edge C2 is reachable.
        """
```

### Spec-Driven Endpoint Mapping

Parse the OpenAPI spec to build endpoint mappings dynamically:

```python
def _build_endpoint_map(self, spec: dict):
    """
    Scan spec paths for known operation patterns:
    
    Entity position update:
      Look for: POST path containing 'entities' and 'position'
      e.g., /api/v1/entities/{entity_id}/position
    
    Entity create/update:
      Look for: PUT path containing 'entities/{entity_id}'
      e.g., /api/v1/entities/{entity_id}
    
    Bulk update:
      Look for: POST path containing 'entities' and 'bulk'
      e.g., /api/v1/entities/bulk
    
    Event:
      Look for: POST path containing 'events'
      e.g., /api/v1/events
    
    AIS signal:
      Look for: POST path containing 'signals' and 'ais'
    
    ADS-B signal:
      Look for: POST path containing 'signals' and 'adsb'
    
    Health:
      Look for: GET path containing 'health'
    """
    self.endpoints = {}
    for path, methods in spec.get('paths', {}).items():
        for method, operation in methods.items():
            # Pattern matching logic
            if 'position' in path and method == 'post':
                self.endpoints['position_update'] = (method, path)
            elif 'bulk' in path and method == 'post':
                self.endpoints['bulk_update'] = (method, path)
            # ... etc
```

### Payload Generation

Map entity dict to API schema:

```python
def _entity_to_position_payload(self, entity: dict) -> dict:
    """
    Generate payload conforming to spec's PositionUpdate schema.
    
    Reads required/optional fields from the schema definition.
    Maps entity fields to schema fields:
      entity.position.latitude → payload.latitude
      entity.position.longitude → payload.longitude
      entity.heading_deg → payload.heading
      entity.speed_knots → payload.speed
      entity.timestamp → payload.timestamp
    
    Unknown fields in entity that don't map to schema are dropped.
    Missing required fields log a warning.
    """

def _entity_to_full_payload(self, entity: dict) -> dict:
    """
    Generate full entity payload for create/update.
    Maps all entity fields including metadata.
    """

def _event_to_payload(self, event: dict) -> dict:
    """Map scenario event to API event schema."""
```

### Batch Mode

```python
class BatchBuffer:
    def __init__(self, interval_s: float, flush_callback):
        self.buffer = []
        self.interval = interval_s
        self.flush_callback = flush_callback
        self._task = None
    
    def add(self, payload: dict):
        self.buffer.append(payload)
    
    async def start(self):
        """Start background flush loop."""
        while True:
            await asyncio.sleep(self.interval)
            if self.buffer:
                batch = self.buffer.copy()
                self.buffer.clear()
                await self.flush_callback(batch)
    
    async def flush_now(self):
        """Force immediate flush."""
        if self.buffer:
            batch = self.buffer.copy()
            self.buffer.clear()
            await self.flush_callback(batch)
```

### Retry Logic

```python
async def _send_with_retry(self, method: str, url: str, payload: dict) -> bool:
    """
    Send HTTP request with exponential backoff retry.
    
    Retries on: 429 (rate limit), 500, 502, 503, 504
    Does NOT retry on: 400, 401, 403, 404 (client errors)
    
    Backoff: 1s, 2s, 4s (max 3 retries)
    Logs all attempts in dry_run mode.
    """
```

### Dry Run Mode

When `dry_run=True`, the adapter does everything except make HTTP requests:
- Parses the spec
- Generates payloads
- Logs each payload to console and to a file (`logs/rest_adapter_dry_run.jsonl`)
- Reports what WOULD have been sent

This is critical for development before the real Edge C2 API is available.

### Tests (`tests/unit/test_rest_adapter.py`):

- Spec parsing: loads `config/edge_c2_api.yaml` without error
- Endpoint mapping: finds position, bulk, event, health endpoints
- Payload generation: entity dict → valid PositionUpdate payload
- Batch mode: accumulates and flushes correctly
- Dry run: logs payloads without HTTP calls
- Retry: simulates 503 then 200, verifies retry works
- Auth headers: API key or Bearer token added to requests
- Missing spec endpoint: graceful degradation (log warning, skip)

### Integration test:

- Start a mock HTTP server on :9000
- Run REST adapter with `edge_c2_api.yaml` spec
- Push 10 entity updates
- Verify mock received correct payloads
- Push an event, verify received
- Health check returns true

---

## Task 2: CoT/TAK Adapter (`simulator/transport/cot_adapter.py`)

Optional but impressive for demo — feed live entity data to ATAK/WinTAK 
tablets via Cursor on Target (CoT) XML protocol.

```python
"""
Cursor on Target (CoT) transport adapter.

Generates CoT XML messages and sends them via TCP to a TAK server
(FreeTAKServer or TAK Server). Allows ATAK/WinTAK clients to display
simulated entities alongside real operational data.

CoT is the standard messaging protocol for tactical awareness in the
TAK ecosystem used by US/NATO/partner militaries.
"""

import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

class CoTAdapter(TransportBase):
    def __init__(
        self,
        tak_host: str = "localhost",
        tak_port: int = 8087,        # FreeTAKServer default CoT port
        stale_seconds: int = 30,      # How long until entity goes stale
        enabled: bool = False         # Off by default, enable if TAK available
    ):
        pass
    
    async def connect(self):
        """Open TCP connection to TAK server."""
    
    async def push_entity_update(self, entity: dict):
        """Convert entity to CoT XML and send."""
        cot_xml = self._entity_to_cot(entity)
        await self._send(cot_xml)
    
    async def push_event(self, event: dict):
        """Convert scenario event to CoT GeoChat or Alert."""
    
    def _entity_to_cot(self, entity: dict) -> str:
        """
        Generate CoT XML event for an entity.
        
        <event version="2.0" uid="{entity_id}" type="{cot_type}"
               time="{timestamp}" start="{timestamp}" stale="{stale_time}"
               how="m-g">
          <point lat="{lat}" lon="{lon}" hae="{alt}" ce="15" le="15"/>
          <detail>
            <contact callsign="{callsign}"/>
            <track speed="{speed_m_s}" course="{heading}"/>
            <remarks>{agency}: {entity_type} — {status}</remarks>
            <__group name="{agency}" role="{role}"/>
            <status readiness="{status}"/>
          </detail>
        </event>
        """
    
    def _entity_type_to_cot_type(self, entity: dict) -> str:
        """
        Map entity type + affiliation to CoT type string.
        
        CoT type format: a-{affiliation}-{dimension}-{function}
        
        Affiliation:
          f = friendly
          h = hostile
          n = neutral
          u = unknown
        
        Dimension:
          G = ground
          A = air
          S = surface (maritime)
          U = subsurface
        
        Mappings:
          MMEA_PATROL:         a-f-S-X-N     (friendly surface, non-combatant)
          MMEA_FAST_INTERCEPT: a-f-S-X-N
          MIL_NAVAL:           a-f-S-C       (friendly surface combatant)
          SUSPECT_VESSEL:      a-h-S-X       (hostile surface)
          CIVILIAN_CARGO:      a-n-S-C-M     (neutral surface, merchant)
          CIVILIAN_FISHING:    a-n-S-C-F     (neutral surface, fishing)
          RMAF_FIGHTER:        a-f-A-M-F     (friendly air, military, fighter)
          RMAF_HELICOPTER:     a-f-A-M-H     (friendly air, military, helicopter)
          RMAF_TRANSPORT:      a-f-A-M-C     (friendly air, military, cargo)
          RMP_HELICOPTER:      a-f-A-C-H     (friendly air, civilian, helicopter)
          RMP_PATROL_CAR:      a-f-G-E-V-C-P (friendly ground, equipment, vehicle, 
                                               civilian, police)
          RMP_TACTICAL_TEAM:   a-f-G-U-C-I   (friendly ground, unit, combat, infantry)
          MIL_APC:             a-f-G-E-V-A   (friendly ground, equipment, vehicle, armor)
          MIL_INFANTRY_SQUAD:  a-f-G-U-C-I
          CI_OFFICER:          a-f-G-U-C-I
        """
```

### CoT message structure:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<event version="2.0"
       uid="MMEA-PV-101"
       type="a-f-S-X-N"
       time="2026-04-15T08:14:32.000Z"
       start="2026-04-15T08:14:32.000Z"
       stale="2026-04-15T08:15:02.000Z"
       how="m-g">
  <point lat="5.84" lon="118.07" hae="0.0" ce="15.0" le="15.0"/>
  <detail>
    <contact callsign="KM Semporna"/>
    <track speed="9.52" course="45.2"/>
    <remarks>MMEA: MMEA_PATROL — ACTIVE | Speed: 18.5 kts</remarks>
    <__group name="MMEA" role="Team Lead"/>
    <status readiness="true"/>
    <uid Droid="KM Semporna"/>
    <precisionlocation altsrc="GPS" geopointsrc="GPS"/>
  </detail>
</event>
```

### Speed conversion for CoT:

CoT `track.speed` is in meters/second, not knots:
```python
speed_ms = entity['speed_knots'] * 0.514444
```

### Event to CoT GeoChat:

Scenario events become CoT GeoChat messages visible as alerts in ATAK:

```xml
<event version="2.0" uid="event-{event_id}" type="b-t-f"
       time="{time}" start="{time}" stale="{stale}">
  <point lat="{lat}" lon="{lon}" hae="0" ce="999999" le="999999"/>
  <detail>
    <__chat chatroom="ESSCOM" groupOwner="ESSCOM">
      <chatgrp uid0="simulator" uid1="ESSCOM"/>
    </__chat>
    <remarks source="ESSCOM">{event.description}</remarks>
    <link uid="event-{id}" type="a-f-G" relation="p-p"/>
  </detail>
</event>
```

### Tests:

- CoT XML validates against schema
- Entity → CoT type mapping covers all entity types
- Speed correctly converted to m/s
- Stale time is timestamp + stale_seconds
- Event → GeoChat format correct
- TCP connection handles disconnect/reconnect

---

## Task 3: FreeTAKServer Docker Setup

Add FreeTAKServer to `docker-compose.yml` as an optional service:

```yaml
  freetakserver:
    image: freetakteam/freetakserver:latest
    ports:
      - "8087:8087"    # CoT TCP
      - "8443:8443"    # REST API
      - "19023:19023"  # WebMap
    volumes:
      - fts_data:/opt/FTSData
    environment:
      - FTS_CONNECTION_MESSAGE=Edge C2 Simulator connected
    profiles:
      - tak  # Only starts with: docker-compose --profile tak up
    
volumes:
  fts_data:
```

The `profiles: [tak]` means FreeTAKServer only starts if explicitly requested:
```bash
docker-compose --profile tak up  # With TAK
docker-compose up                # Without TAK (default)
```

---

## Task 4: Transport Registry

Refactor transport initialization so all adapters are managed uniformly:

```python
"""
Transport registry — manages all active transport adapters.

Supports multiple simultaneous transports (e.g., WebSocket + REST + CoT).
Each transport implements the same interface.
"""

class TransportRegistry:
    def __init__(self):
        self.transports: list[TransportBase] = []
    
    def register(self, adapter: TransportBase):
        self.transports.append(adapter)
    
    async def push_entity_update(self, entity: dict):
        for t in self.transports:
            try:
                await t.push_entity_update(entity)
            except Exception as e:
                logger.warning(f"Transport {t.__class__.__name__} failed: {e}")
    
    async def push_bulk_update(self, entities: list[dict]):
        for t in self.transports:
            try:
                await t.push_bulk_update(entities)
            except Exception as e:
                logger.warning(f"Transport {t.__class__.__name__} failed: {e}")
    
    async def push_event(self, event: dict):
        for t in self.transports:
            try:
                await t.push_event(event)
            except Exception as e:
                logger.warning(f"Transport {t.__class__.__name__} failed: {e}")
    
    async def close_all(self):
        for t in self.transports:
            await t.close()
```

Update `run_simulator.py` CLI:
```bash
edge-c2-sim --scenario ... \
            --transport ws,console,rest \
            --rest-url http://edge-c2-api:9000 \
            --rest-api-key my-api-key \
            --rest-dry-run \
            --cot-host freetakserver \
            --cot-port 8087
```

### Tests:

- Registry pushes to multiple transports
- One transport failure doesn't stop others
- CLI flags correctly configure each transport

---

## Task 5: End-to-End Integration Test

`tests/integration/test_full_stack.py`:

```python
"""
Full stack integration test.

Starts: simulator + WebSocket server + REST adapter (dry run) + mock REST server
Runs: sulu_sea_fishing_intercept at 60x speed
Verifies:
  1. WebSocket broadcasts all entity updates
  2. REST adapter generates correct payloads for each endpoint
  3. Events are broadcast through all transports
  4. AIS signals are pushed to /signals/ais
  5. Scenario completes without errors
  6. Entity lifecycle: create → update → intercept → stop
"""

import asyncio
import aiohttp
from aiohttp import web

async def test_full_stack():
    # Start mock REST server
    mock_received = []
    
    async def mock_handler(request):
        body = await request.json()
        mock_received.append({
            'method': request.method,
            'path': request.path,
            'body': body
        })
        return web.json_response({'status': 'ok'})
    
    app = web.Application()
    app.router.add_route('*', '/{path:.*}', mock_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, 'localhost', 9999)
    await site.start()
    
    # Load and run scenario
    loader = ScenarioLoader()
    state = loader.load("config/scenarios/sulu_sea_fishing_intercept.yaml")
    
    clock = SimulationClock(state.start_time, speed=60.0)
    store = EntityStore()
    event_engine = EventEngine(state.events, store, state.movements, state.start_time)
    
    # Configure transports
    registry = TransportRegistry()
    ws_adapter = WebSocketAdapter(port=0)  # Random port
    rest_adapter = RESTAdapter(
        api_spec_path="config/edge_c2_api.yaml",
        base_url="http://localhost:9999",
        dry_run=False  # Actually send to mock
    )
    console_adapter = ConsoleAdapter(quiet=True)
    
    registry.register(ws_adapter)
    registry.register(rest_adapter)
    registry.register(console_adapter)
    
    await rest_adapter.initialize()
    await ws_adapter.start()
    
    # Run simulation
    # ... (run loop for scenario duration at 60x) ...
    
    # Verify REST calls
    position_updates = [r for r in mock_received if 'position' in r['path']]
    event_posts = [r for r in mock_received if 'events' in r['path']]
    
    assert len(position_updates) > 100  # Many position updates
    assert len(event_posts) == 17       # All scenario events
    
    # Verify payload structure
    sample = position_updates[0]['body']
    assert 'latitude' in sample
    assert 'longitude' in sample
    assert 'timestamp' in sample
    
    # Cleanup
    await runner.cleanup()
    await ws_adapter.stop()
```

---

## Task 6: API Spec Swap Documentation

Create `docs/API_INTEGRATION.md` documenting how to swap the stub API spec:

```markdown
# Edge C2 API Integration Guide

## Swapping the API Specification

When the real Edge C2 API spec arrives:

1. Save the new spec as `config/edge_c2_api.yaml`
2. Run the validator:
   ```bash
   python scripts/validate_api_spec.py config/edge_c2_api.yaml
   ```
3. Start the simulator with REST adapter (dry run first):
   ```bash
   edge-c2-sim --scenario ... --transport ws,rest --rest-dry-run
   ```
4. Check logs for any mapping warnings
5. If field names differ, update `config/field_mapping.yaml`
6. Remove --rest-dry-run to go live

## Field Mapping Override

If the real API uses different field names, create `config/field_mapping.yaml`:

```yaml
entity_to_api:
  position.latitude: lat
  position.longitude: lng  
  heading_deg: bearing
  speed_knots: speed
  timestamp: time
```

The REST adapter will apply these mappings before sending payloads.
```

---

## Definition of Done

Phase 4 is complete when:

1. REST adapter loads OpenAPI spec and generates correct payloads
2. Dry run mode logs all payloads without making HTTP requests
3. Batch mode accumulates and sends bulk updates
4. Retry logic handles 503/429 with exponential backoff
5. Health check endpoint works
6. CoT adapter generates valid CoT XML for all entity types
7. FreeTAKServer docker service starts with `--profile tak`
8. Transport registry manages multiple simultaneous transports
9. One transport failure doesn't crash others
10. Full integration test passes with mock REST server
11. API_INTEGRATION.md documents spec swap procedure
