# Edge C2 Simulator — Implementation Plan

## Project Overview

**Objective:** Build a multi-domain simulation system that generates realistic entity data (maritime, aviation, ground vehicles, personnel) across five Malaysian agencies and pushes it to the Edge C2 REST API, with a CesiumJS-based 3D Common Operating Picture for live demonstration.

**Demo audience:** Senior Malaysian defense/security officials (April 2026)
**Timeline:** 1–3 weeks active development
**Cost:** $0 software licensing (all open-source)

---

## Roles

| Role | Assigned To | Responsibility |
|------|-------------|----------------|
| Architect / Requirements / Design | Claude (Chat) | System design, data models, API contracts, scenario scripts, integration design |
| Implementation / Testing | Claude Code | All software development, test generation, CI/CD, containerization |
| Infrastructure / Accounts / Data | You (Human) | Account setup, API keys, server provisioning, Edge C2 API spec, Malaysian geo data validation |

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        SIMULATION ENGINE (Python)                    │
│                                                                     │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐           │
│  │ Maritime  │  │ Aviation │  │ Vehicle  │  │ Personnel│           │
│  │ Simulator │  │ Simulator│  │ Simulator│  │ Simulator│           │
│  │ (AIS gen) │  │(ADSB gen)│  │(SUMO/OSM)│  │(Waypoint)│           │
│  └─────┬─────┘  └─────┬────┘  └─────┬────┘  └─────┬────┘           │
│        │              │              │              │                │
│        └──────────────┴──────────────┴──────────────┘                │
│                              │                                       │
│                    ┌─────────▼──────────┐                            │
│                    │  Entity State Store │                            │
│                    │   (In-Memory Dict)  │                            │
│                    └─────────┬──────────┘                            │
│                              │                                       │
│              ┌───────────────┼───────────────┐                       │
│              ▼               ▼               ▼                       │
│   ┌──────────────┐ ┌────────────────┐ ┌──────────────┐              │
│   │ Transport:   │ │ Transport:     │ │ Transport:   │              │
│   │ REST Adapter │ │ WebSocket Push │ │ CoT/TAK      │              │
│   │ (Edge C2 API)│ │ (CesiumJS COP)│ │ (TAK Clients)│              │
│   └──────┬───────┘ └───────┬────────┘ └──────┬───────┘              │
│          │                 │                  │                       │
└──────────┼─────────────────┼──────────────────┼──────────────────────┘
           │                 │                  │
           ▼                 ▼                  ▼
    ┌──────────────┐ ┌───────────────┐  ┌──────────────┐
    │  Edge C2 API │ │ CesiumJS COP  │  │ ATAK/WinTAK  │
    │  (YAML-stub  │ │ (3D Globe     │  │ (Optional     │
    │   initially) │ │  Dashboard)   │  │  TAK clients) │
    └──────────────┘ └───────────────┘  └──────────────┘
```

### Key Design Principles

1. **Transport is a pluggable interface.** Every adapter implements `push_entity_update(entity)` and `push_event(event)`. REST is the default. WebSocket, CoT/TAK, MQTT, DIS — all are drop-in replacements.

2. **Simulation clock is decoupled.** A central clock drives all simulators. It can run at 1x, 2x, 5x, 10x, 60x. Pause/resume/rewind supported. This is critical for demo pacing.

3. **Scenarios are declarative JSON/YAML files.** No code changes to create new scenarios. A scenario file defines: initial entity positions, waypoints, speeds, events (bombing triggers, intercept orders), agency assignments, and timing.

4. **Edge C2 API contract is YAML-driven.** A single `edge_c2_api.yaml` OpenAPI spec defines the target. The REST adapter auto-generates payloads from this spec. When the real API spec arrives, swap the YAML and regenerate — zero code changes to the simulator core.

5. **Entity model is domain-agnostic.** Every entity (ship, aircraft, vehicle, person) shares a common base: `entity_id`, `entity_type`, `agency`, `position(lat, lon, alt)`, `heading`, `speed`, `timestamp`, `metadata{}`. Domain-specific fields extend via `metadata`.

---

## Data Model

### Entity Base Schema

```yaml
Entity:
  entity_id: string          # Unique ID (e.g., "MMEA-PV-001")
  entity_type: string        # Enum: see Entity Types below
  domain: string             # Enum: MARITIME, AIR, GROUND_VEHICLE, PERSONNEL
  agency: string             # Enum: RMP, MMEA, CI, RMAF, MIL
  callsign: string           # Display name (e.g., "KD Keris")
  position:
    latitude: float          # WGS84 decimal degrees
    longitude: float         # WGS84 decimal degrees
    altitude_m: float        # Meters above sea level (0 for surface)
  heading_deg: float         # True heading 0-360
  speed_knots: float         # Speed in knots (all domains normalized to knots)
  course_deg: float          # Course over ground
  timestamp: datetime        # ISO 8601 UTC
  status: string             # Enum: ACTIVE, IDLE, RESPONDING, INTERCEPTING, RTB
  sidc: string               # MIL-STD-2525D Symbol ID Code
  metadata: object           # Domain-specific (see below)
```

### Agency Definitions

```yaml
Agencies:
  RMP:
    full_name: "Royal Malaysia Police (Polis Diraja Malaysia)"
    abbreviation: "RMP"
    color: "#1B3A8C"         # Dark blue
    domains: [GROUND_VEHICLE, PERSONNEL, AIR]
    
  MMEA:
    full_name: "Malaysian Maritime Enforcement Agency (APMM)"
    abbreviation: "MMEA"
    color: "#FF6600"         # Orange
    domains: [MARITIME]
    
  CI:
    full_name: "Royal Malaysian Customs and Immigration"
    abbreviation: "CI"
    color: "#2E7D32"         # Green
    domains: [GROUND_VEHICLE, PERSONNEL]
    
  RMAF:
    full_name: "Royal Malaysian Air Force (TUDM)"
    abbreviation: "RMAF"
    color: "#5C6BC0"         # Indigo
    domains: [AIR]
    
  MIL:
    full_name: "Malaysian Armed Forces (ATM)"
    abbreviation: "MIL"
    color: "#4E342E"         # Brown
    domains: [GROUND_VEHICLE, PERSONNEL, AIR, MARITIME]
```

### Entity Types by Domain

```yaml
Maritime:
  CIVILIAN_CARGO:
    speed_range_knots: [10, 16]
    ais_type: 70  # Cargo
    example: "MV Strait Runner"
    
  CIVILIAN_TANKER:
    speed_range_knots: [10, 15]
    ais_type: 80  # Tanker
    example: "MT Malacca Spirit"
    
  CIVILIAN_FISHING:
    speed_range_knots: [3, 8]
    ais_type: 30  # Fishing
    example: "Nelayan Jaya"
    
  CIVILIAN_PASSENGER:
    speed_range_knots: [12, 22]
    ais_type: 60  # Passenger
    example: "Star Cruises"
    
  MMEA_PATROL:
    speed_range_knots: [12, 30]
    ais_type: 55  # Law enforcement
    example: "KM Marlin"
    agency: MMEA
    
  MMEA_FAST_INTERCEPT:
    speed_range_knots: [25, 45]
    ais_type: 55
    example: "KM Penggalang"
    agency: MMEA
    
  MIL_NAVAL:
    speed_range_knots: [15, 30]
    ais_type: 35  # Military
    example: "KD Keris"
    agency: MIL
    
  SUSPECT_VESSEL:
    speed_range_knots: [8, 40]  # Variable — evading
    ais_type: 0   # AIS may be OFF (dark target)
    example: "Unknown Vessel"

Aviation:
  CIVILIAN_COMMERCIAL:
    speed_range_knots: [140, 500]  # Approach to cruise
    alt_range_ft: [0, 41000]
    adsb_category: A5  # Heavy
    example: "MAS 370"
    
  CIVILIAN_LIGHT:
    speed_range_knots: [80, 200]
    alt_range_ft: [0, 15000]
    adsb_category: A1  # Light
    example: "9M-ABC"
    
  RMAF_FIGHTER:
    speed_range_knots: [200, 600]
    alt_range_ft: [0, 50000]
    adsb_category: ""  # Military — may not squawk ADSB
    example: "TUDM Hawk"
    agency: RMAF
    
  RMAF_TRANSPORT:
    speed_range_knots: [150, 300]
    alt_range_ft: [0, 30000]
    example: "TUDM C-130"
    agency: RMAF
    
  RMAF_HELICOPTER:
    speed_range_knots: [0, 150]
    alt_range_ft: [0, 10000]
    example: "TUDM EC725"
    agency: RMAF
    
  RMP_HELICOPTER:
    speed_range_knots: [0, 140]
    alt_range_ft: [0, 8000]
    example: "PDRM Air Wing"
    agency: RMP

Ground_Vehicle:
  RMP_PATROL_CAR:
    speed_range_kmh: [0, 140]
    example: "PDRM MPV-023"
    agency: RMP
    
  RMP_TACTICAL:
    speed_range_kmh: [0, 100]
    example: "PDRM VAT-69"
    agency: RMP
    
  CI_CHECKPOINT_VEHICLE:
    speed_range_kmh: [0, 120]
    example: "CUSTOMS-VH-012"
    agency: CI
    
  CI_MOBILE_UNIT:
    speed_range_kmh: [0, 120]
    example: "IMMI-PATROL-007"
    agency: CI
    
  MIL_APC:
    speed_range_kmh: [0, 80]
    example: "ATM APC-DEFTECH"
    agency: MIL
    
  MIL_TRANSPORT:
    speed_range_kmh: [0, 90]
    example: "ATM TRANSPORT-04"
    agency: MIL
    
  MIL_COMMAND:
    speed_range_kmh: [0, 100]
    example: "ATM CMD-01"
    agency: MIL

Personnel:
  RMP_OFFICER:
    speed_range_kmh: [0, 6]    # Walking/running
    example: "PO Sgt Ahmad"
    agency: RMP
    
  RMP_TACTICAL_TEAM:
    speed_range_kmh: [0, 6]
    example: "UTK Team Alpha"
    agency: RMP
    
  CI_OFFICER:
    speed_range_kmh: [0, 5]
    example: "CUSTOMS Officer Lin"
    agency: CI
    
  CI_IMMIGRATION_TEAM:
    speed_range_kmh: [0, 5]
    example: "IMMI Team B"
    agency: CI
    
  MIL_INFANTRY_SQUAD:
    speed_range_kmh: [0, 6]
    example: "ATM 1 RAMD Squad 3"
    agency: MIL
    
  MIL_SPECIAL_FORCES:
    speed_range_kmh: [0, 8]
    example: "GGK Team Bravo"
    agency: MIL
```

### Domain-Specific Metadata

```yaml
Maritime_Metadata:
  mmsi: string               # 9-digit Maritime Mobile Service Identity
  imo_number: string         # IMO ship ID
  vessel_name: string
  vessel_type_ais: int       # AIS vessel type code
  draught_m: float
  destination: string
  eta: datetime
  nav_status: int            # AIS navigation status (0=underway, 1=at anchor, etc.)
  ais_active: boolean        # False = dark target (suspect vessels)
  
Aviation_Metadata:
  icao_hex: string           # 24-bit ICAO address
  squawk: string             # Transponder code
  flight_number: string
  aircraft_type: string      # ICAO type designator (e.g., "B738", "SU30")
  vertical_rate_fpm: float   # Feet per minute
  on_ground: boolean
  adsb_active: boolean       # False = military stealth
  
Vehicle_Metadata:
  plate_number: string
  vehicle_model: string
  unit_assignment: string    # "Johor Bahru District", "Northern Brigade"
  
Personnel_Metadata:
  unit_name: string
  unit_size: int             # Number of people in group
  equipment: list[string]    # ["rifle", "radio", "NVG"]
  formation: string          # "patrol", "checkpoint", "cordon"
```

---

## Scenario Definitions

### Scenario 1: Suspect Ship Intercept (Strait of Malacca)

```yaml
scenario:
  name: "Suspect Ship Intercept — Strait of Malacca"
  description: "A cargo vessel disables its AIS transponder while transiting the Strait of Malacca, triggering a multi-agency maritime intercept operation."
  duration_minutes: 45
  center: { lat: 2.5, lon: 102.0 }  # Central Strait of Malacca
  zoom: 8

  # Background traffic (always running)
  background_entities:
    - type: CIVILIAN_CARGO
      count: 15
      route: "strait_tss_westbound"    # Predefined Traffic Separation Scheme
      speed_variation: 0.1             # ±10% speed randomization
      
    - type: CIVILIAN_CARGO
      count: 12
      route: "strait_tss_eastbound"
      
    - type: CIVILIAN_TANKER
      count: 8
      route: "strait_tss_westbound"
      
    - type: CIVILIAN_FISHING
      count: 20
      area: "malacca_fishing_grounds"  # Random patrol within polygon
      
    - type: CIVILIAN_COMMERCIAL       # Aircraft
      count: 6
      route: "klia_approach_patterns"

  # Scripted scenario entities
  scenario_entities:
    - id: "SUSPECT-001"
      type: SUSPECT_VESSEL
      callsign: "MV Dark Horizon"
      initial_position: { lat: 2.8, lon: 101.5 }
      waypoints:
        - { lat: 2.6, lon: 101.8, speed: 12, time: "00:00" }
        - { lat: 2.4, lon: 102.0, speed: 12, time: "00:10" }
        # AIS goes dark at 00:10
        - { lat: 2.2, lon: 102.2, speed: 14, time: "00:20", ais_active: false }
        - { lat: 2.0, lon: 102.5, speed: 16, time: "00:30", ais_active: false }
      metadata:
        mmsi: "000000000"
        vessel_name: "MV Dark Horizon"
        
    - id: "MMEA-PV-001"
      type: MMEA_PATROL
      callsign: "KM Marlin"
      agency: MMEA
      initial_position: { lat: 2.3, lon: 102.1 }
      behavior: "patrol"
      patrol_area: "zone_bravo"
      # Responds to intercept order at event trigger
      
    - id: "MMEA-FI-001"
      type: MMEA_FAST_INTERCEPT
      callsign: "KM Penggalang"
      agency: MMEA
      initial_position: { lat: 2.1, lon: 101.9 }
      behavior: "standby"
      # Scrambles on intercept order
      
    - id: "RMAF-MPA-001"
      type: RMAF_TRANSPORT
      callsign: "TUDM Beechcraft MPA"
      agency: RMAF
      initial_position: { lat: 3.1, lon: 101.7 }  # Subang airbase
      behavior: "standby"
      # Airborne surveillance dispatch
      
    - id: "MIL-NAV-001"
      type: MIL_NAVAL
      callsign: "KD Keris"
      agency: MIL
      initial_position: { lat: 1.9, lon: 102.3 }
      behavior: "patrol"
      patrol_area: "zone_charlie"

  # Timed events driving the scenario
  events:
    - time: "00:10"
      type: "AIS_LOSS"
      description: "SUSPECT-001 AIS transponder goes dark"
      target: "SUSPECT-001"
      alert_agencies: [MMEA]
      
    - time: "00:12"
      type: "ALERT"
      description: "MMEA Maritime Surveillance Center detects AIS anomaly"
      alert_agencies: [MMEA, MIL]
      
    - time: "00:14"
      type: "ORDER"
      description: "MMEA orders KM Marlin to investigate last known position"
      target: "MMEA-PV-001"
      action: "intercept"
      intercept_target: "SUSPECT-001"
      
    - time: "00:16"
      type: "ORDER"
      description: "RMAF dispatches maritime patrol aircraft"
      target: "RMAF-MPA-001"
      action: "search_area"
      area: "suspect_last_known"
      
    - time: "00:20"
      type: "DETECTION"
      description: "RMAF MPA locates suspect vessel via radar"
      source: "RMAF-MPA-001"
      detected: "SUSPECT-001"
      
    - time: "00:22"
      type: "ORDER"
      description: "MMEA scrambles fast intercept boat"
      target: "MMEA-FI-001"
      action: "intercept"
      intercept_target: "SUSPECT-001"
      
    - time: "00:28"
      type: "ORDER"
      description: "Malaysian Navy KD Keris diverted to assist"
      target: "MIL-NAV-001"
      action: "intercept"
      intercept_target: "SUSPECT-001"
      
    - time: "00:35"
      type: "INTERCEPT"
      description: "KM Penggalang intercepts suspect vessel"
      source: "MMEA-FI-001"
      target: "SUSPECT-001"
      
    - time: "00:38"
      type: "BOARDING"
      description: "MMEA boarding team boards suspect vessel"
      source: "MMEA-FI-001"
      target: "SUSPECT-001"
      
    - time: "00:42"
      type: "RESOLUTION"
      description: "Contraband discovered. Vessel escorted to port"
      target: "SUSPECT-001"
      action: "escort_to_port"
      escort: ["MMEA-PV-001", "MIL-NAV-001"]
```

### Scenario 2: Bombing on Border (Thai-Malaysian Border)

```yaml
scenario:
  name: "Border Bombing Response — Perlis/Kedah"
  description: "An IED detonates near a border crossing in Perlis. Multi-agency response involving RMP, Military, Customs & Immigration, and RMAF."
  duration_minutes: 60
  center: { lat: 6.65, lon: 100.18 }  # Padang Besar border area
  zoom: 12

  background_entities:
    - type: CI_CHECKPOINT_VEHICLE
      count: 4
      area: "padang_besar_crossing"
      behavior: "stationary"
      
    - type: RMP_PATROL_CAR
      count: 3
      route: "perlis_patrol_route_1"
      
    - type: CIVILIAN_LIGHT   # Aircraft
      count: 2
      route: "northern_corridor"

  scenario_entities:
    # Customs & Immigration at border
    - id: "CI-CP-001"
      type: CI_OFFICER
      callsign: "Customs Post Alpha"
      agency: CI
      initial_position: { lat: 6.6625, lon: 100.1850 }
      behavior: "stationary"
      metadata:
        unit_size: 8
        formation: "checkpoint"
        
    - id: "CI-CP-002"
      type: CI_IMMIGRATION_TEAM
      callsign: "Immigration Post Alpha"
      agency: CI
      initial_position: { lat: 6.6630, lon: 100.1855 }
      behavior: "stationary"
      metadata:
        unit_size: 6
        formation: "checkpoint"

    # RMP first responders
    - id: "RMP-PC-001"
      type: RMP_PATROL_CAR
      callsign: "PDRM Perlis 01"
      agency: RMP
      initial_position: { lat: 6.65, lon: 100.17 }
      behavior: "patrol"
      patrol_route: "kangar_patrol"
      
    - id: "RMP-PC-002"
      type: RMP_PATROL_CAR
      callsign: "PDRM Perlis 02"
      agency: RMP
      initial_position: { lat: 6.64, lon: 100.20 }
      behavior: "patrol"
      
    # RMP tactical unit
    - id: "RMP-TAC-001"
      type: RMP_TACTICAL
      callsign: "VAT-69 Team Alpha"
      agency: RMP
      initial_position: { lat: 6.43, lon: 100.19 }  # Alor Setar base
      behavior: "standby"
      
    - id: "RMP-TAC-TEAM"
      type: RMP_TACTICAL_TEAM
      callsign: "UTK QRF"
      agency: RMP
      initial_position: { lat: 6.43, lon: 100.19 }
      behavior: "standby"
      metadata:
        unit_size: 12
        equipment: ["rifle", "radio", "body_armor", "EOD_kit"]

    # Military QRF
    - id: "MIL-APC-001"
      type: MIL_APC
      callsign: "ATM 1 RAMD APC"
      agency: MIL
      initial_position: { lat: 6.12, lon: 100.37 }  # Taiping / Kamunting
      behavior: "standby"
      
    - id: "MIL-INF-001"
      type: MIL_INFANTRY_SQUAD
      callsign: "1 RAMD Squad 1"
      agency: MIL
      initial_position: { lat: 6.12, lon: 100.37 }
      behavior: "standby"
      metadata:
        unit_size: 10
        equipment: ["rifle", "radio", "NVG"]
        
    - id: "MIL-SF-001"
      type: MIL_SPECIAL_FORCES
      callsign: "GGK Team Bravo"
      agency: MIL
      initial_position: { lat: 3.05, lon: 101.70 }  # KL — will be airlifted
      behavior: "standby"
      metadata:
        unit_size: 8
        equipment: ["rifle", "radio", "NVG", "EOD_advanced"]
      
    # RMAF assets
    - id: "RMAF-HELI-001"
      type: RMAF_HELICOPTER
      callsign: "TUDM EC725 Rescue"
      agency: RMAF
      initial_position: { lat: 5.47, lon: 100.39 }  # Butterworth AFB
      behavior: "standby"
      
    - id: "RMP-HELI-001"
      type: RMP_HELICOPTER
      callsign: "PDRM Air Wing 01"
      agency: RMP
      initial_position: { lat: 6.17, lon: 100.40 }
      behavior: "standby"

  events:
    - time: "00:00"
      type: "INCIDENT"
      description: "IED detonation at Padang Besar border crossing"
      position: { lat: 6.6628, lon: 100.1852 }
      severity: "CRITICAL"
      alert_agencies: [RMP, CI, MIL]
      
    - time: "00:01"
      type: "ALERT"
      description: "CI officers at checkpoint report explosion, casualties"
      source: "CI-CP-001"
      alert_agencies: [RMP, CI, MIL, RMAF]
      
    - time: "00:02"
      type: "ORDER"
      description: "RMP Perlis patrol cars dispatched to scene"
      targets: ["RMP-PC-001", "RMP-PC-002"]
      action: "respond"
      destination: { lat: 6.6628, lon: 100.1852 }
      
    - time: "00:03"
      type: "ORDER"
      description: "CI locks down border crossing — all lanes closed"
      target: "CI-CP-001"
      action: "lockdown"
      
    - time: "00:05"
      type: "ARRIVAL"
      description: "First RMP patrol arrives at scene, establishes cordon"
      source: "RMP-PC-001"
      
    - time: "00:06"
      type: "ORDER"
      description: "RMP OCPD requests VAT-69 tactical response team"
      targets: ["RMP-TAC-001", "RMP-TAC-TEAM"]
      action: "deploy"
      destination: { lat: 6.6628, lon: 100.1852 }
      
    - time: "00:08"
      type: "ORDER"
      description: "RMP Air Wing helicopter dispatched for aerial surveillance"
      target: "RMP-HELI-001"
      action: "deploy"
      area: "padang_besar_border"
      
    - time: "00:10"
      type: "ORDER"
      description: "RMAF EC725 dispatched for CASEVAC"
      target: "RMAF-HELI-001"
      action: "deploy"
      destination: { lat: 6.6628, lon: 100.1852 }
      
    - time: "00:12"
      type: "ORDER"
      description: "Military QRF activated — 1 RAMD deployed from Kamunting"
      targets: ["MIL-APC-001", "MIL-INF-001"]
      action: "deploy"
      destination: { lat: 6.6628, lon: 100.1852 }
      
    - time: "00:15"
      type: "ARRIVAL"
      description: "RMP helicopter on station, providing aerial ISR"
      source: "RMP-HELI-001"
      
    - time: "00:18"
      type: "DETECTION"
      description: "RMP helicopter identifies suspicious vehicle fleeing north"
      source: "RMP-HELI-001"
      detected: "SUSPECT-VH-001"
      # This triggers a new entity to appear
      
    - time: "00:20"
      type: "ORDER"
      description: "CI requests immigration team reinforcements at border"
      target: "CI-CP-002"
      action: "reinforce"
      
    - time: "00:22"
      type: "ARRIVAL"
      description: "RMAF EC725 arrives, begins CASEVAC"
      source: "RMAF-HELI-001"
      
    - time: "00:25"
      type: "ORDER"
      description: "GGK Special Forces team activated, deploying from KL"
      target: "MIL-SF-001"
      action: "airlift"
      destination: { lat: 6.6628, lon: 100.1852 }
      
    - time: "00:30"
      type: "ARRIVAL"
      description: "VAT-69 tactical team arrives, assumes tactical control"
      source: "RMP-TAC-001"
      
    - time: "00:35"
      type: "ARRIVAL"
      description: "Military QRF arrives, establishes outer cordon"
      source: "MIL-APC-001"
      
    - time: "00:40"
      type: "ORDER"
      description: "Joint command post established — RMP, MIL, CI coordination"
      action: "establish_jcp"
      position: { lat: 6.660, lon: 100.183 }
      
    - time: "00:50"
      type: "ARRIVAL"
      description: "GGK arrives via RMAF transport, deploys for EOD sweep"
      source: "MIL-SF-001"
      
    - time: "00:55"
      type: "RESOLUTION"
      description: "Area secured. EOD sweep complete. Investigation begins."
      action: "secure"
```

---

## Project Structure

```
edge-c2-simulator/
├── README.md
├── docker-compose.yml              # Full stack: sim + COP + FreeTAKServer
├── pyproject.toml                   # Python project config
├── .env.example                     # Environment variables template
│
├── config/
│   ├── agencies.yaml                # Agency definitions (colors, domains)
│   ├── entity_types.yaml            # All entity type definitions
│   ├── edge_c2_api.yaml             # OpenAPI stub for Edge C2 (YAML-driven)
│   └── scenarios/
│       ├── strait_intercept.yaml    # Scenario 1
│       ├── border_bombing.yaml      # Scenario 2
│       └── demo_combined.yaml       # Both scenarios for full demo
│
├── simulator/
│   ├── __init__.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── clock.py                 # Simulation clock (1x–60x, pause/resume)
│   │   ├── entity.py                # Entity base class and state management
│   │   ├── entity_store.py          # In-memory entity state store
│   │   ├── scenario_loader.py       # YAML scenario parser
│   │   └── event_engine.py          # Timed event processor
│   │
│   ├── domains/
│   │   ├── __init__.py
│   │   ├── maritime.py              # Ship movement, AIS generation
│   │   ├── aviation.py              # Aircraft movement, ADSB generation
│   │   ├── ground_vehicle.py        # Vehicle movement (road-network aware)
│   │   └── personnel.py             # Troop/officer movement
│   │
│   ├── movement/
│   │   ├── __init__.py
│   │   ├── waypoint.py              # Waypoint-based movement interpolation
│   │   ├── patrol.py                # Random patrol within polygon
│   │   ├── intercept.py             # Pursuit/intercept calculations
│   │   ├── road_network.py          # OSM road-following (optional SUMO)
│   │   └── noise.py                 # Position/speed noise for realism
│   │
│   ├── signals/
│   │   ├── __init__.py
│   │   ├── ais_encoder.py           # AIS NMEA sentence generation
│   │   └── adsb_encoder.py          # ADS-B message generation
│   │
│   └── transport/
│       ├── __init__.py
│       ├── base.py                  # Abstract transport interface
│       ├── rest_adapter.py          # REST API push (Edge C2)
│       ├── websocket_adapter.py     # WebSocket push (CesiumJS COP)
│       ├── cot_adapter.py           # CoT/TAK protocol (FreeTAKServer)
│       ├── mqtt_adapter.py          # MQTT adapter (future)
│       └── console_adapter.py       # Debug: print to console
│
├── cop/                             # CesiumJS Common Operating Picture
│   ├── package.json
│   ├── index.html
│   ├── src/
│   │   ├── app.js                   # Main CesiumJS application
│   │   ├── entity_renderer.js       # Entity rendering with milsymbol
│   │   ├── websocket_client.js      # WebSocket connection to simulator
│   │   ├── scenario_controls.js     # Play/pause/speed controls
│   │   ├── agency_filters.js        # Toggle agencies on/off
│   │   ├── timeline.js              # Event timeline display
│   │   ├── entity_panel.js          # Entity detail panel on click
│   │   └── styles/
│   │       └── cop.css              # Dark theme COP styling
│   └── assets/
│       └── icons/                   # Agency logos, custom markers
│
├── tak_integration/                 # Optional TAK ecosystem bridge
│   ├── cot_generator.py             # CoT XML generator for all entity types
│   └── freetakserver_config/        # FTS configuration files
│
├── geodata/                         # Malaysian geographic data
│   ├── routes/
│   │   ├── strait_tss.geojson       # Strait of Malacca TSS lanes
│   │   ├── rmaf_airways.geojson     # Malaysian airways
│   │   └── border_roads.geojson     # Thai-Malaysian border road network
│   ├── areas/
│   │   ├── patrol_zones.geojson     # MMEA patrol zone polygons
│   │   ├── fishing_grounds.geojson  # Fishing area polygons
│   │   └── border_crossings.geojson # Known border crossing points
│   └── bases/
│       ├── military_bases.geojson   # MAF base locations
│       ├── police_stations.geojson  # RMP station locations
│       └── naval_bases.geojson      # RMN base locations
│
├── tests/
│   ├── unit/
│   │   ├── test_entity.py
│   │   ├── test_clock.py
│   │   ├── test_movement.py
│   │   ├── test_ais_encoder.py
│   │   ├── test_adsb_encoder.py
│   │   └── test_scenario_loader.py
│   ├── integration/
│   │   ├── test_scenario_execution.py
│   │   ├── test_transport_adapters.py
│   │   └── test_websocket_cop.py
│   └── e2e/
│       └── test_full_scenario.py
│
├── scripts/
│   ├── run_simulator.py             # Main entry point
│   ├── run_cop.py                   # Start COP web server
│   ├── generate_background_traffic.py  # One-off route generation
│   └── validate_scenario.py         # Validate scenario YAML files
│
└── docs/
    ├── ARCHITECTURE.md
    ├── SCENARIO_AUTHORING.md         # How to write new scenarios
    ├── TRANSPORT_ADAPTERS.md         # How to add new transport layers
    └── EDGE_C2_INTEGRATION.md        # Edge C2 API integration guide
```

---

## Implementation Phases

### Phase 0: Foundation (Day 1–2) — IN PARALLEL

**Claude Code tasks (start immediately):**

```
TASK: Initialize the edge-c2-simulator project

1. Create the full project directory structure as specified above
2. Set up pyproject.toml with these dependencies:
   - Python >= 3.11
   - pyyaml
   - aiohttp (async HTTP server + client)
   - websockets
   - pyais (AIS encoding/decoding)
   - shapely (geometry — patrol areas, polygons)
   - geopy (distance calculations)
   - click (CLI)
   - uvicorn (ASGI server for COP)
   - pytest, pytest-asyncio (testing)
   
3. Implement simulator/core/clock.py:
   - SimulationClock class with start(), pause(), resume(), set_speed(multiplier)
   - Supports 1x, 2x, 5x, 10x, 60x speed multipliers
   - get_sim_time() returns current simulation datetime
   - Emits tick events at configurable intervals (default 1 second sim-time)
   - Full pytest test suite in tests/unit/test_clock.py

4. Implement simulator/core/entity.py:
   - Entity dataclass matching the Entity Base Schema in this document
   - Position dataclass (lat, lon, alt)
   - EntityType enum covering all types in the data model
   - Agency enum: RMP, MMEA, CI, RMAF, MIL
   - Domain enum: MARITIME, AIR, GROUND_VEHICLE, PERSONNEL
   - Status enum: ACTIVE, IDLE, RESPONDING, INTERCEPTING, RTB
   - Full pytest test suite

5. Implement simulator/core/entity_store.py:
   - Thread-safe in-memory dictionary of entities
   - add_entity(), update_entity(), get_entity(), get_all_entities()
   - get_entities_by_agency(), get_entities_by_domain()
   - on_update callback registration (for transport layer notification)
   - Full pytest test suite

6. Implement simulator/transport/base.py:
   - Abstract base class TransportAdapter
   - Methods: connect(), disconnect(), push_entity_update(entity),
     push_event(event), push_bulk_update(entities)
   - All async

7. Implement simulator/transport/console_adapter.py:
   - Debug adapter that prints entity updates to console
   - Useful for development/testing without any external services

8. Implement simulator/transport/websocket_adapter.py:
   - WebSocket server on configurable port (default 8765)
   - Broadcasts entity updates as JSON to all connected clients
   - Handles client connect/disconnect gracefully
   - Message format: { "type": "entity_update", "entity": {...} }
   - Also sends: { "type": "event", "event": {...} }
   - Also sends: { "type": "clock", "sim_time": "...", "speed": 1 }
   - Full pytest test suite with mock WebSocket client

9. Set up docker-compose.yml with:
   - simulator service (Python)
   - cop service (static file server for CesiumJS app, nginx)
   - Placeholder for freetakserver service (commented out initially)

10. Create .env.example with:
    - CESIUM_ION_TOKEN=your_token_here
    - EDGE_C2_API_URL=http://localhost:8080/api/v1
    - EDGE_C2_API_KEY=stub
    - SIM_SPEED=1
    - SIM_PORT=8765
    - COP_PORT=3000

11. Create a minimal README.md with:
    - Project description
    - Quick start instructions
    - Architecture overview link
    - Environment setup

NOTE: Do NOT install Eclipse SUMO yet — we'll use pure waypoint-based 
movement initially and add SUMO as an enhancement later. Keep the 
road_network.py module as a stub with a clear interface.
```

**Your tasks (start immediately):**

```
TASK: Account & infrastructure setup

1. CESIUM ION ACCOUNT (Required — free tier is sufficient)
   - Go to: https://ion.cesium.com/signup
   - Sign up for a free Community account
   - Go to Access Tokens → create a token with all default scopes
   - Save the token — Claude Code will need it for the COP frontend
   - Free tier gives: 500,000 tiles/month, 3D terrain, satellite imagery
   - This is the single most important account for the visual demo

2. GITHUB REPOSITORY
   - Create a private repo: edge-c2-simulator
   - Add Claude Code as a collaborator if using a shared workflow
   - Or just provide the repo URL so Claude Code can push to it

3. SERVER / LAPTOP FOR DEMO
   - The demo can run on a single laptop (Docker Desktop)
   - Recommended: modern laptop with 16GB+ RAM, decent GPU
   - OS: macOS, Windows, or Linux with Docker
   - Alternatively: a cloud VM (AWS EC2 t3.xlarge or similar)
   - Decision needed: will the April demo be on local hardware or cloud?

4. EDGE C2 API SPECIFICATION
   - When the Edge C2 API spec becomes available, provide it as:
     - OpenAPI 3.0 YAML/JSON (preferred), OR
     - Swagger JSON, OR
     - Even a rough text description of endpoints
   - Key question: what data does Edge C2 expect per entity?
     - Just position + metadata? Or full AIS/ADSB message payloads?
   - For now, we will build a stub YAML and swap it later
   - NO BLOCKER — we proceed without it

5. MALAYSIAN GEOGRAPHIC DATA VALIDATION
   - You may know better than open-source data:
     - Are the military base locations I've listed approximately correct?
       (Butterworth AFB, Kamunting army base, Subang airbase)
     - Any specific border crossings to feature? (I defaulted to
       Padang Besar as it's the largest)
     - Any specific MMEA patrol zones or naval base locations?
   - Not a blocker — we can adjust coordinates later

6. AGENCY BRANDING
   - If you have logos or official color codes for the Malaysian agencies
     (RMP, MMEA, CI, RMAF, ATM), share them
   - We'll use them on the COP display for agency filtering
   - Not a blocker — I've assigned reasonable default colors

7. INSTALL DOCKER DESKTOP (if not already installed)
   - https://www.docker.com/products/docker-desktop
   - Required for running the full stack locally
```

### Phase 1: Movement Engine (Day 2–4)

**Claude Code tasks:**

```
TASK: Build entity movement systems

1. Implement simulator/movement/waypoint.py:
   - WaypointMovement class
   - Input: list of waypoints with (lat, lon, alt, speed, time)
   - Interpolates position between waypoints using great-circle math
   - Returns (lat, lon, alt, heading, speed) for any given sim_time
   - Handles speed transitions smoothly (not instant jumps)
   - Tests with known distances (e.g., KL to Penang = ~350km)

2. Implement simulator/movement/patrol.py:
   - PatrolMovement class
   - Input: GeoJSON polygon defining patrol area
   - Generates random waypoints within polygon
   - Entity moves between waypoints with configurable dwell time
   - Speed varies within entity type's range
   - Heading changes smoothly (no instant 180° turns)

3. Implement simulator/movement/intercept.py:
   - InterceptMovement class
   - Input: source entity, target entity, max speed
   - Calculates intercept course (lead pursuit, not tail chase)
   - Updates heading and speed each tick to converge on target
   - Detects "intercept achieved" when within configurable radius
   - Maritime intercept: accounts for target course changes
   - Air intercept: includes altitude convergence

4. Implement simulator/movement/noise.py:
   - PositionNoise class
   - Adds realistic GPS-like noise to positions:
     - ±5m for ground vehicles (GPS)
     - ±15m for maritime (AIS)
     - ±50m for aviation (radar uncertainty)
   - Adds speed variation: ±2% continuous drift
   - Adds heading oscillation: ±1–3° 
   - Makes everything look real, not computer-generated

5. Implement simulator/core/scenario_loader.py:
   - Parses YAML scenario files
   - Validates against entity type definitions
   - Creates Entity objects with assigned MovementStrategy
   - Resolves route references (e.g., "strait_tss_westbound") to
     actual GeoJSON waypoints
   - Returns ScenarioState with all entities and event timeline

6. Implement simulator/core/event_engine.py:
   - Processes timed events from scenario definition
   - At each tick, checks if any events should fire
   - Event types: ALERT, ORDER, DETECTION, ARRIVAL, INCIDENT, RESOLUTION
   - ORDER events modify entity behavior (change movement strategy,
     e.g., from "patrol" to "intercept")
   - Emits events through transport layer for COP display

7. Tests for all of the above — comprehensive unit tests plus
   an integration test that loads strait_intercept.yaml and runs
   the first 5 minutes of simulation, verifying entity positions
   are reasonable.
```

### Phase 2: Domain Simulators (Day 4–6)

**Claude Code tasks:**

```
TASK: Build domain-specific simulators

1. Implement simulator/domains/maritime.py:
   - MaritimeSimulator class
   - Manages all maritime entities
   - Generates AIS NMEA sentences via simulator/signals/ais_encoder.py
   - Ship behavior: follow TSS lanes, adjust for traffic, slow near
     pilot boarding areas
   - Suspect vessel behavior: disable AIS, change speed, alter course
   - Background traffic: spawn civilian ships at edges, transit through

2. Implement simulator/signals/ais_encoder.py:
   - Uses pyais library for NMEA encoding
   - Generates AIS Message Type 1/2/3 (position reports) from entity state
   - Generates AIS Message Type 5 (static data) on entity creation
   - Configurable update rate: fast movers every 2s, slow every 10s
   - Returns properly formatted NMEA sentence strings

3. Implement simulator/domains/aviation.py:
   - AviationSimulator class
   - Aircraft follow realistic speed/altitude profiles:
     - Takeoff: accelerate + climb
     - Cruise: level flight at assigned altitude
     - Descent: reduce speed + descend
   - Fighters can "scramble" — rapid acceleration and climb
   - Helicopters: lower altitude, can hover (speed=0)
   - Generates ADSB data via simulator/signals/adsb_encoder.py

4. Implement simulator/signals/adsb_encoder.py:
   - Generates SBS-format messages (BaseStation format)
   - MSG types 1–4 covering ID, position, airborne velocity
   - ICAO hex addresses for each aircraft
   - Military aircraft can have adsb_active=false (no signal generated)

5. Implement simulator/domains/ground_vehicle.py:
   - GroundVehicleSimulator class
   - Vehicles follow waypoint routes (road-network stub initially)
   - Speed limited by vehicle type max
   - Emergency response: vehicles increase speed, use direct routes
   - Convoy behavior: multiple vehicles maintaining spacing

6. Implement simulator/domains/personnel.py:
   - PersonnelSimulator class
   - Walking speed entities (3–8 km/h)
   - Formations: patrol (moving), checkpoint (stationary), cordon (ring)
   - Groups move as a unit with slight position spread
   - Can "deploy" from vehicle (linked entity)

7. Main orchestrator: scripts/run_simulator.py
   - CLI entry point using Click
   - Loads scenario YAML
   - Initializes all domain simulators
   - Starts simulation clock
   - Runs async event loop
   - Options: --scenario, --speed, --port, --transport (rest/ws/cot/console)

8. Full test suite for each domain simulator
```

### Phase 3: CesiumJS COP Dashboard (Day 5–8)

**Claude Code tasks:**

```
TASK: Build CesiumJS Common Operating Picture

1. Set up cop/ as a modern web project:
   - Vite for build tooling
   - CesiumJS (latest via npm)
   - milsymbol.js for MIL-STD-2525D symbology
   - Reconnecting-WebSocket for reliable WS connection

2. cop/src/app.js — Main application:
   - Initialize CesiumJS viewer with:
     - Dark map theme (Cesium Dark or custom style)
     - 3D globe with terrain enabled
     - Initial view centered on Malaysia (lat: 4.2, lon: 108.0, zoom appropriate)
   - Top bar: Edge C2 branding, simulation clock, speed controls
   - Left panel: Agency filter toggles with color swatches
   - Right panel: Entity detail (shows on click)
   - Bottom panel: Event timeline / activity log
   - Professional dark theme suitable for command center

3. cop/src/entity_renderer.js:
   - Receives entity updates via WebSocket
   - For each entity:
     a. Generate milsymbol icon using SIDC code
     b. Create/update Cesium Billboard at entity position
     c. Show heading indicator (velocity vector line)
     d. Trail: keep last 10 positions, draw polyline track history
     e. On hover: show tooltip (callsign, speed, agency)
     f. On click: populate right detail panel
   - Entity color follows agency color scheme
   - Smooth animation between position updates using
     SampledPositionProperty

4. cop/src/websocket_client.js:
   - Connect to simulator WebSocket (ws://localhost:8765)
   - Handle message types: entity_update, event, clock
   - Reconnect automatically on disconnect
   - Queue updates during reconnection

5. cop/src/scenario_controls.js:
   - Play / Pause / Speed buttons (1x, 2x, 5x, 10x)
   - Sends speed commands back to simulator via WebSocket
   - Displays current simulation time prominently
   - Scenario selector dropdown (if multiple scenarios loaded)

6. cop/src/agency_filters.js:
   - Toggle buttons for each agency: RMP, MMEA, CI, RMAF, MIL
   - Each with agency color swatch
   - Filter also by domain: Maritime, Air, Ground, Personnel
   - "Civilian" toggle for background traffic
   - Toggles show/hide entities in real-time

7. cop/src/timeline.js:
   - Scrollable event log at bottom of screen
   - Events appear as they fire in the scenario
   - Color-coded by agency
   - Click event to fly camera to event location
   - Format: [TIME] [AGENCY] Description

8. cop/src/entity_panel.js:
   - Right sidebar that shows on entity click
   - Entity callsign, type, agency (with logo)
   - Current position (lat/lon), heading, speed
   - Status (ACTIVE, INTERCEPTING, etc.)
   - For maritime: MMSI, vessel name, destination
   - For aviation: flight number, altitude, squawk
   - "Follow" button to lock camera on entity
   - "Track History" toggle

9. Styling requirements:
   - Dark theme throughout (command center aesthetic)
   - Agency colors consistent with config
   - Clean, professional typography (no playful fonts)
   - Responsive enough for 1080p and 4K displays
   - The "big screen in the command center" look
   
10. Build and serve via Docker nginx container
```

### Phase 4: Integration & Edge C2 Adapter (Day 7–10)

**Claude Code tasks:**

```
TASK: Build Edge C2 REST adapter and integrate everything

1. Implement simulator/transport/rest_adapter.py:
   - Reads edge_c2_api.yaml (OpenAPI spec) to understand endpoints
   - Maps entity updates to API payloads
   - Configurable endpoint mapping:
     entity_update: POST /api/v1/entities/{entity_id}/position
     event:         POST /api/v1/events
     bulk_update:   POST /api/v1/entities/bulk
   - Handles authentication (API key header, Bearer token, or none)
   - Retry logic with exponential backoff
   - Batch mode: accumulate updates, send in bulk every N seconds
   - Dry-run mode: log what WOULD be sent without actual HTTP calls
   - Full test suite with mocked HTTP endpoints

2. Create config/edge_c2_api.yaml STUB:
   - OpenAPI 3.0 spec with reasonable defaults
   - Endpoints for:
     - POST /entities/{id}/position (lat, lon, alt, heading, speed, timestamp)
     - POST /entities/{id} (full entity creation/update)
     - POST /events (event notifications)
     - POST /entities/bulk (batch position updates)
     - GET /entities (list — for verification)
   - This WILL be replaced when the real spec arrives
   - The adapter should regenerate payloads from spec automatically

3. Implement simulator/transport/cot_adapter.py:
   - Generates Cursor on Target XML for each entity update
   - Maps entity types to CoT type codes:
     RMP vehicle: a-f-G-U-C-I (friendly ground unit civilian law enforcement)
     MMEA vessel: a-f-S-X-N (friendly surface vessel law enforcement)
     RMAF aircraft: a-f-A-M-F (friendly air military fixed wing)
     MIL infantry: a-f-G-U-C (friendly ground unit combat)
     Suspect vessel: a-h-S-X (hostile surface vessel)
     Civilian ship: a-n-S-C (neutral surface cargo)
   - Sends via TCP to FreeTAKServer (or any TAK server)
   - Uses pytak library for CoT XML generation
   - Full test suite

4. Integration test: full scenario run
   - Load strait_intercept.yaml
   - Run at 60x speed
   - Verify all entities update correctly
   - Verify events fire at correct sim times
   - Verify WebSocket broadcasts all updates
   - Verify REST adapter generates correct payloads (dry-run)
   - Verify COP renders entities (browser automation or screenshot)

5. Docker compose full stack test:
   - docker-compose up runs everything
   - Simulator starts, loads scenario, begins broadcasting
   - COP connects via WebSocket, renders entities
   - REST adapter logs (dry-run) what it would push to Edge C2
```

### Phase 5: Polish & Demo Preparation (Day 9–14)

**Claude Code tasks:**

```
TASK: Polish for demo

1. COP visual polish:
   - Smooth entity animations (no jumping)
   - Track trails fade over time
   - Event notifications appear as toast messages
   - Fly-to animations when clicking events
   - Entity clustering at low zoom levels
   - Mini-map in corner
   - Agency legend with entity counts
   - "Demo mode" auto-fly-through of key moments

2. Scenario polish:
   - Ensure all background traffic looks realistic
   - Verify Strait of Malacca TSS routes match real charts
   - Add weather overlay option (rain, visibility)
   - Add day/night cycle tied to simulation time

3. Demo automation:
   - "Narrated demo" mode: pre-scripted camera movements
     synced to scenario events
   - Auto-zoom to action as events unfold
   - Configurable: operator can take manual control at any time
   - Reset-to-start button for re-running demo

4. Performance optimization:
   - Handle 100+ simultaneous entities without lag
   - WebSocket message batching (send bulk every 100ms, not per-entity)
   - CesiumJS entity pooling for background traffic
   - Test on target demo hardware

5. Error handling:
   - Graceful degradation if Edge C2 API is down
   - WebSocket auto-reconnect
   - Scenario validation on load (clear error messages)
   - Health check endpoint
```

**Your tasks for Phase 5:**

```
1. VALIDATE SCENARIO CONTENT:
   - Review both scenario narratives for accuracy
   - Confirm agency chain of command makes sense
   - Confirm entity types match real Malaysian assets
   - Any corrections to geography, unit names, base locations

2. EDGE C2 API SPEC:
   - Provide the real API spec when available
   - We will swap the stub YAML and test integration
   - Key info needed: authentication method, endpoint URLs,
     payload format, rate limits

3. DEMO ENVIRONMENT:
   - Set up the laptop/server for the April demo
   - Install Docker, clone repo, run docker-compose up
   - Test on the actual display (projector? wall screen? laptop screen?)
   - Test network configuration (firewalls, ports)

4. BRANDING:
   - Company logo for Edge C2 branding on COP header
   - Any specific color scheme or branding guidelines
   - Malaysian agency logos if available
```

---

## Technology Stack Summary

| Component | Technology | License | Purpose |
|-----------|-----------|---------|---------|
| Simulation Engine | Python 3.11+ | - | Core simulation logic |
| Async Framework | aiohttp + asyncio | Apache 2.0 | Async HTTP + event loop |
| AIS Encoding | pyais | MIT | Maritime signal generation |
| Geometry | Shapely | BSD | Patrol areas, polygons |
| Geodesic Math | geopy | MIT | Distance, bearing calculations |
| WebSocket | websockets | BSD | Real-time COP communication |
| COP Display | CesiumJS | Apache 2.0 | 3D globe visualization |
| Military Symbols | milsymbol.js | MIT | MIL-STD-2525D icons |
| Build Tool | Vite | MIT | COP frontend bundling |
| TAK Protocol | PyTAK | Apache 2.0 | CoT XML generation |
| TAK Server | FreeTAKServer | EPL | Optional TAK distribution |
| Containerization | Docker | Apache 2.0 | Deployment packaging |
| Testing | pytest | MIT | Unit + integration tests |
| Config Format | YAML | - | Scenarios + config |
| CLI | Click | BSD | Command-line interface |

---

## Risk Register

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Edge C2 API spec arrives late or changes significantly | Medium | High | YAML-driven adapter regenerates payloads automatically. Stub API allows full development to proceed. |
| CesiumJS free tier rate limits during demo | High | Low | Cache tiles locally before demo. Test tile usage in rehearsal. Consider Cesium Ion paid tier if needed ($100/mo). |
| 100+ entities cause browser performance issues | Medium | Medium | Entity clustering, LOD rendering, WebSocket batching. Test early on target hardware. |
| Malaysian geographic data inaccurate | Low | Medium | Use OpenStreetMap + satellite verification. Human validates key locations. |
| Demo network environment restrictive | High | Medium | Package everything in Docker for offline capability. CesiumJS can use offline tile cache. |
| FreeTAKServer instability | Low | Medium | FreeTAKServer is optional — the WebSocket COP works independently. TAK is a nice-to-have. |

---

## Immediate Action Items

### Claude Code — START NOW:
Execute Phase 0 tasks above. Priority order:
1. Project structure + pyproject.toml
2. Entity data model (entity.py)
3. Simulation clock (clock.py) + tests
4. Entity store (entity_store.py) + tests
5. WebSocket transport adapter + tests
6. Console transport adapter
7. Docker setup

### You — START NOW:
1. **Cesium Ion account** — 10 minutes, free, required
2. **GitHub repo** — 5 minutes
3. **Review this plan** — flag anything wrong or missing
4. **Edge C2 API** — start requesting the spec from whoever is building it. Even a rough draft helps.
5. **Docker Desktop** — install if not already present

### Claude (Chat) — CONTINUING:
1. Create the GeoJSON geodata files (Strait of Malacca TSS routes, patrol zones, base locations)
2. Write the full OpenAPI stub for edge_c2_api.yaml
3. Finalize scenario YAML files with precise coordinates
4. Design the COP dashboard wireframe
5. Write SCENARIO_AUTHORING.md so new scenarios can be created easily
