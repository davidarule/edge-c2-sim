# Claude Code — Phase 0 Task Brief

## Context
You are building the backend for an Edge C2 (Command & Control) multi-domain 
simulator. This system generates realistic entity data (ships, aircraft, vehicles, 
troops) representing five Malaysian security agencies and pushes that data via 
REST API to an Edge C2 system, while simultaneously broadcasting to a CesiumJS 
web dashboard via WebSocket.

Read the full implementation plan at: `edge-c2-simulator-plan.md` (in project root)

## Project Setup

Initialize a Python project called `edge-c2-simulator` with the directory 
structure defined in the plan. Key points:

- Python >= 3.11
- Use `pyproject.toml` (no setup.py)
- Use `src` layout NOT required — flat `simulator/` package at project root is fine
- All async using `asyncio` + `aiohttp`

### Dependencies (pyproject.toml)

```toml
[project]
name = "edge-c2-simulator"
version = "0.1.0"
description = "Multi-domain C2 simulation engine for Edge C2 demonstration"
requires-python = ">=3.11"
dependencies = [
    "pyyaml>=6.0",
    "aiohttp>=3.9",
    "websockets>=12.0",
    "pyais>=2.6",
    "shapely>=2.0",
    "geopy>=2.4",
    "click>=8.1",
    "uvicorn>=0.27",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "pytest-cov>=4.1",
    "aioresponses>=0.7",
]

[project.scripts]
edge-c2-sim = "scripts.run_simulator:main"
```

## Phase 0 Implementation Tasks (in order)

### Task 1: Project Structure
Create the full directory tree as specified in the plan. Include `__init__.py` 
in all Python packages. Create placeholder modules with docstrings.

### Task 2: Entity Data Model (`simulator/core/entity.py`)

```python
"""
Entity data model for Edge C2 Simulator.

Every simulated entity (ship, aircraft, vehicle, person) shares a common
base model. Domain-specific data lives in the metadata dict.
"""
```

Implement:
- `Position` dataclass: lat (float), lon (float), alt_m (float, default=0)
- `Agency` enum: RMP, MMEA, CI, RMAF, MIL, CIVILIAN
- `Domain` enum: MARITIME, AIR, GROUND_VEHICLE, PERSONNEL
- `EntityStatus` enum: ACTIVE, IDLE, RESPONDING, INTERCEPTING, RTB
- `Entity` dataclass with ALL fields from the plan's Entity Base Schema:
  - entity_id, entity_type, domain, agency, callsign
  - position (Position), heading_deg, speed_knots, course_deg
  - timestamp (datetime), status (EntityStatus)
  - sidc (str), metadata (dict)
- `Entity.to_dict()` → JSON-serializable dictionary
- `Entity.from_dict(d)` → Entity (class method)
- Helper: `Entity.update_position(lat, lon, alt, heading, speed, course)` 
  that also updates timestamp

Tests (`tests/unit/test_entity.py`):
- Create entity, verify all fields
- Serialize to dict, deserialize back, verify equality
- Update position, verify timestamp changes
- Test all enum values

### Task 3: Simulation Clock (`simulator/core/clock.py`)

```python
"""
Simulation clock with configurable speed multiplier.

The clock drives all simulators. It can run at 1x (real-time), 2x, 5x, 
10x, or 60x speed. Supports pause/resume. All domain simulators query 
this clock for the current simulation time rather than using wall-clock time.
"""
```

Implement:
- `SimulationClock` class
  - `__init__(start_time: datetime, speed: float = 1.0)`
  - `start()` — begins advancing time
  - `pause()` / `resume()` 
  - `set_speed(multiplier: float)` — 1.0, 2.0, 5.0, 10.0, 60.0
  - `get_sim_time() -> datetime` — current simulation time
  - `get_elapsed() -> timedelta` — elapsed sim time since start
  - `is_running -> bool`
  - `speed -> float`
  - `add_tick_callback(callback)` — register function called each tick
  - Internal: uses wall-clock delta * speed_multiplier to advance sim time
- NOT async — simple calculation based on wall clock when queried
  (no background thread needed)

Tests (`tests/unit/test_clock.py`):
- Create clock, verify initial time
- Advance at 1x, verify time matches wall clock (within tolerance)
- Advance at 10x, verify time runs 10x faster  
- Pause, verify time stops advancing
- Resume, verify time continues from pause point
- Change speed mid-run

### Task 4: Entity Store (`simulator/core/entity_store.py`)

```python
"""
Thread-safe in-memory entity state store.

Central registry of all simulated entities. Transport adapters subscribe
to update callbacks to receive entity changes in real-time.
"""
```

Implement:
- `EntityStore` class
  - `add_entity(entity: Entity)` — add new entity, raise if ID exists
  - `update_entity(entity: Entity)` — update existing, raise if not found
  - `upsert_entity(entity: Entity)` — add or update
  - `get_entity(entity_id: str) -> Entity | None`
  - `get_all_entities() -> list[Entity]`
  - `get_entities_by_agency(agency: Agency) -> list[Entity]`
  - `get_entities_by_domain(domain: Domain) -> list[Entity]`
  - `remove_entity(entity_id: str)`
  - `on_update(callback: Callable[[Entity], None])` — register listener
  - `on_event(callback: Callable[[dict], None])` — register event listener
  - `emit_event(event: dict)` — push operational event to all listeners
  - Internal: `dict[str, Entity]` with threading.Lock
- All callbacks are called synchronously on update (adapters handle async)

Tests (`tests/unit/test_entity_store.py`):
- Add entity, retrieve by ID
- Update entity, verify listener called
- Filter by agency, by domain
- Remove entity
- Upsert (create + update)
- Multiple listeners all receive updates

### Task 5: Transport Base & Console Adapter

`simulator/transport/base.py`:
```python
"""
Abstract base class for transport adapters.

Each adapter implements the same interface. The simulator core pushes
entity updates through all registered adapters. Adapters handle the
protocol-specific serialization and delivery.
"""
```

Implement abstract class `TransportAdapter`:
- `async connect()`
- `async disconnect()`
- `async push_entity_update(entity: Entity)`
- `async push_event(event: dict)`
- `async push_bulk_update(entities: list[Entity])`
- `name: str` property

`simulator/transport/console_adapter.py`:
- Prints entity updates to stdout in a readable format
- Format: `[SIM_TIME] [AGENCY] CALLSIGN @ (LAT, LON) HDG SPD STATUS`
- Prints events as: `[SIM_TIME] EVENT: description`
- Rate-limited: max 1 print per entity per 5 seconds (configurable)

### Task 6: WebSocket Adapter (`simulator/transport/websocket_adapter.py`)

```python
"""
WebSocket server that broadcasts entity updates to connected COP clients.

Runs a WebSocket server on a configurable port. All connected clients 
(typically the CesiumJS COP dashboard) receive real-time entity updates,
events, and clock synchronization messages.
"""
```

Implement:
- `WebSocketAdapter(TransportAdapter)` 
  - `__init__(host="0.0.0.0", port=8765)`
  - Manages set of connected clients
  - On client connect: send full entity snapshot (all current entities)
  - `push_entity_update(entity)` → broadcast JSON to all clients
  - `push_event(event)` → broadcast event JSON to all clients
  - Periodic clock sync: every 1 second, broadcast current sim time + speed
  - Handle client disconnect gracefully
  - Handle incoming messages from clients:
    - `{"type": "set_speed", "speed": 5}` → adjust clock speed
    - `{"type": "pause"}` / `{"type": "resume"}`
    - `{"type": "reset"}` → restart scenario
  
Message formats (outgoing):
```json
{"type": "entity_update", "entity": { ...entity.to_dict()... }}
{"type": "entity_remove", "entity_id": "..."}
{"type": "event", "event": { "event_type": "ALERT", "description": "...", ... }}
{"type": "clock", "sim_time": "2026-04-15T08:30:00Z", "speed": 1.0, "running": true}
{"type": "snapshot", "entities": [ ...all entities... ]}
```

Tests (`tests/unit/test_websocket_adapter.py`):
- Start server, connect mock client, verify snapshot received
- Push entity update, verify client receives it
- Push event, verify client receives it
- Multiple clients all receive same messages
- Client disconnect doesn't crash server
- Client sends speed command, verify it's processed

### Task 7: Docker Setup

`docker-compose.yml`:
```yaml
version: "3.8"
services:
  simulator:
    build: .
    ports:
      - "8765:8765"  # WebSocket
    volumes:
      - ./config:/app/config
      - ./geodata:/app/geodata
      - ./scenarios:/app/scenarios
    environment:
      - SIM_SPEED=1
      - SIM_PORT=8765
    command: python -m scripts.run_simulator --scenario config/scenarios/strait_intercept.yaml

  cop:
    image: nginx:alpine
    ports:
      - "3000:80"
    volumes:
      - ./cop/dist:/usr/share/nginx/html
    depends_on:
      - simulator

  # Uncomment when ready for TAK integration
  # freetakserver:
  #   image: freetakteam/freetakserver:latest
  #   ports:
  #     - "8087:8087"
  #     - "8443:8443"
```

`Dockerfile`:
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml .
RUN pip install .
COPY . .
CMD ["python", "-m", "scripts.run_simulator"]
```

### Task 8: Minimal run_simulator.py

`scripts/run_simulator.py` — just enough to:
1. Parse CLI args (--scenario, --speed, --port)
2. Initialize clock
3. Initialize entity store
4. Initialize WebSocket adapter + Console adapter
5. Print "Simulator ready" and wait
6. (Scenario loading comes in Phase 1)

## Files from the architect

The following files have been prepared and should be copied into the project:

- `config/edge_c2_api.yaml` — OpenAPI stub for Edge C2 REST API
- `geodata/routes/strait_tss.geojson` — Strait of Malacca shipping lanes
- `geodata/areas/patrol_zones.geojson` — MMEA patrol zone polygons
- `geodata/bases/security_bases.geojson` — Military/police/coast guard base locations

These are available in the project's shared files. Copy them into the 
appropriate directories in the project structure.

## Quality Requirements

- All code must have docstrings (module, class, and public method level)
- Type hints on all function signatures
- pytest tests for every module (aim for >80% coverage)
- No global state — everything passed via constructor injection
- Async where I/O is involved, sync for pure computation
- YAML config for everything that might change

## What NOT to do yet

- Do NOT implement domain simulators (maritime, aviation, etc.) — Phase 1
- Do NOT implement movement engines — Phase 1
- Do NOT implement the CesiumJS COP — Phase 3
- Do NOT implement the REST adapter — Phase 4
- Do NOT install Eclipse SUMO
- Do NOT set up FreeTAKServer
