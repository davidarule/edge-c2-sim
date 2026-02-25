# CLAUDE.md

This file provides guidance to Claude Code when working with the Edge C2 Simulation Platform.

## Project Overview

Edge C2 is a multi-domain Command & Control simulation platform for defense demonstration. It implements **Plan B** (open-source production system), targeting DSA 2026 (April 20-23, MITEC KL).

**Objective:** Generate realistic entity data (maritime, aviation, ground vehicles, personnel) across five Malaysian agencies, push to Edge C2 REST API, with CesiumJS 3D COP for live demonstration.

### Roles

| Role | Assigned To | Responsibility |
|------|-------------|----------------|
| Architect / Requirements / Design | Claude (Chat/Desktop) | System design, data models, API contracts, scenario scripts |
| Implementation / Testing | Claude Code | All software development, tests, CI/CD, containerization |
| Infrastructure / Accounts / Data | Dave (Human) | Account setup, API keys, server provisioning, geo data validation |

### Architecture

Three-tier: **Simulation Engine (Python)** -> **Message Bus (WebSocket/REST/CoT)** -> **Display Frontend(s)**

```
Simulation Engine (Python)
  ├── Maritime Simulator (AIS gen)
  ├── Aviation Simulator (ADSB gen)
  ├── Vehicle Simulator (waypoint/OSM)
  └── Personnel Simulator (waypoint)
         │
    Entity State Store (In-Memory Dict)
         │
    ┌────┼────┐
    ▼    ▼    ▼
  REST  WS   CoT
  (Edge C2) (CesiumJS COP) (TAK Clients)
```

### Key Design Principles

1. **Transport is pluggable** — all adapters implement `push_entity_update(entity)` and `push_event(event)`
2. **Simulation clock is decoupled** — 1x/2x/5x/10x/60x speed, pause/resume
3. **Scenarios are declarative YAML** — no code changes for new scenarios
4. **Edge C2 API is YAML-driven** — swap `edge_c2_api.yaml` when real spec arrives
5. **Entity model is domain-agnostic** — common base with domain-specific metadata

## Project Structure

```
edge-c2-simulator/
├── config/
│   ├── agencies.yaml                # Agency definitions
│   ├── entity_types.yaml            # Entity type definitions
│   ├── edge_c2_api.yaml             # OpenAPI stub for Edge C2
│   └── scenarios/                   # Scenario YAML files
├── simulator/
│   ├── core/                        # Clock, entity, store, scenario loader, event engine
│   ├── domains/                     # Maritime, aviation, ground_vehicle, personnel
│   ├── movement/                    # Waypoint, patrol, intercept, noise, road_network
│   ├── signals/                     # AIS encoder, ADSB encoder
│   └── transport/                   # REST, WebSocket, CoT, MQTT, console adapters
├── cop/                             # CesiumJS Common Operating Picture (Vite + JS)
│   └── src/                         # app.js, entity_renderer, ws_client, controls
├── tak_integration/                 # Optional FreeTAKServer bridge
├── geodata/                         # Malaysian GeoJSON (routes, areas, bases)
├── tests/                           # Unit, integration, e2e tests
├── scripts/                         # Entry points and utilities
└── docs/                            # Architecture, guides, research
```

## Build Commands

```bash
# Install Python dependencies
pip install -e ".[dev]"

# Run simulator
python scripts/run_simulator.py --scenario config/scenarios/strait_intercept.yaml --speed 1

# Run COP frontend
cd cop && npm install && npm run dev

# Run tests
pytest tests/

# Docker full stack
docker-compose up
```

## Data Model

### Agencies: RMP, MMEA, CI, RMAF, MIL
### Domains: MARITIME, AIR, GROUND_VEHICLE, PERSONNEL
### Entity statuses: ACTIVE, IDLE, RESPONDING, INTERCEPTING, RTB

### Entity base fields
`entity_id, entity_type, domain, agency, callsign, position(lat/lon/alt), heading_deg, speed_knots, course_deg, timestamp, status, sidc, metadata{}`

## Scenarios

1. **Strait Intercept** — Suspect vessel disables AIS in Strait of Malacca, multi-agency maritime intercept (45 min)
2. **Border Bombing** — IED at Padang Besar border crossing, multi-agency ground/air response (60 min)

## Task Management

This project uses **Flux** for task management. Claude Desktop generates plans, requirements, architecture, design, and task assignments. Claude Code and Dave execute tasks.

## Implementation Phases

- **Phase 0**: Foundation — project structure, entity model, clock, store, WebSocket transport
- **Phase 1**: Movement Engine — waypoint, patrol, intercept, noise, scenario loader, event engine
- **Phase 2**: Domain Simulators — maritime, aviation, ground, personnel + signal encoders
- **Phase 3**: CesiumJS COP — 3D globe, entity rendering, controls, agency filters, timeline
- **Phase 4**: Integration — REST adapter, CoT adapter, Edge C2 API stub, full scenario tests
- **Phase 5**: Polish — animations, demo automation, performance, error handling

## Technology Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Simulation Engine | Python 3.11+ | Core logic |
| Async | aiohttp + asyncio | HTTP + event loop |
| AIS Encoding | pyais | Maritime signals |
| Geometry | Shapely | Patrol areas |
| Geodesic | geopy | Distance/bearing |
| WebSocket | websockets | COP communication |
| COP Display | CesiumJS | 3D globe |
| Symbology | milsymbol.js | MIL-STD-2525D |
| Build | Vite | COP bundling |
| TAK | PyTAK | CoT generation |
| Testing | pytest | Unit + integration |
| CLI | Click | Command line |

---

## Coding Guidelines

### 1. Think Before Coding
- State assumptions explicitly. If uncertain, ask.
- If multiple approaches exist, present tradeoffs.

### 2. Simplicity First
- Minimum code that solves the problem.
- No speculative features or abstractions.

### 3. Surgical Changes
- Touch only what you must. Match existing style.

### 4. Goal-Driven Execution
- Define success criteria before implementing.
- Write tests. Verify each step.
