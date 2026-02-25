# Edge C2 Simulator

Multi-domain C2 simulation platform demonstrating coordinated security operations across Malaysian agencies in the Eastern Sabah Security Zone (ESSZONE).

Built for the DSA 2026 defence exhibition (April 20-23, MITEC Kuala Lumpur).

## Quick Start

1. Get a free Cesium Ion token: https://ion.cesium.com/signup
2. Copy `.env.example` to `.env`, add your token
3. Run: `./scripts/demo-start.sh`
4. Open: http://localhost:3000

## Scenarios

| Scenario | Duration | Entities | Description |
|----------|----------|----------|-------------|
| **IUU Fishing Intercept** | 50 min | 16+ | Vietnamese illegal fishing fleet detected and intercepted by MMEA, RMN, RMAF, RMP, and Customs |
| **Kidnapping-for-Ransom Response** | 75 min | 18+ | Armed militant incursion near Semporna, full ESSCOM multi-agency response |
| **Combined Demo** | 120 min | 30+ | Both scenarios back-to-back (recommended for presentations) |

## Architecture

```
Scenario YAML ──► Simulation Engine ──► Transport Layer ──► Display
                    (Python)              (WS/REST/CoT)    (CesiumJS COP)
```

- **Simulation Engine**: Entity movement (waypoint/patrol/intercept), domain simulators (maritime, aviation, ground, personnel), AIS/ADS-B signal generation, event engine
- **Transport Layer**: WebSocket (real-time COP), REST adapter (Edge C2 API, spec-driven), CoT/TAK adapter (ATAK/WinTAK)
- **COP Dashboard**: CesiumJS 3D globe, MIL-STD-2525D military symbology, agency filters, event timeline, demo mode

## Running Without Docker

```bash
# Install Python dependencies
pip install -e .

# Run simulator
python -m scripts.run_simulator --scenario config/scenarios/demo_combined.yaml --speed 5

# In another terminal, start COP dev server
cd cop && npm install && npm run dev
```

## Creating New Scenarios

See `docs/SCENARIO_AUTHORING.md`

## Edge C2 API Integration

See `docs/API_INTEGRATION.md`

## Project Structure

```
simulator/
  core/           # Entity model, clock, entity store
  movement/       # Waypoint, patrol, intercept, noise
  scenario/       # YAML loader, event engine
  domains/        # Maritime, aviation, ground, personnel simulators
  signals/        # AIS NMEA encoder, ADS-B SBS encoder
  transport/      # WebSocket, REST, CoT adapters, registry
cop/              # CesiumJS COP dashboard (Vite + JS)
config/           # Scenarios, API spec
geodata/          # GeoJSON operational data
tests/            # Unit and integration tests
scripts/          # Entry points and utilities
docs/             # Architecture, design, and authoring guides
```

## Tests

```bash
pip install -e ".[dev]"
pytest tests/ -v
```
