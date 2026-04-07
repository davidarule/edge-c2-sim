---
name: edge-c2-scenario
description: >
  Build Edge C2 Simulator operational scenarios for Southeast Asia.
  Use whenever authoring or modifying a scenario YAML file. Contains
  the mandatory pre-flight checklist, coordinate verification workflow,
  regional force library references, physics calculation templates,
  and the full scenario authoring methodology. This skill must be read
  before writing a single coordinate or entity definition.
---

# Edge C2 Simulator — Scenario Building Skill

## The Cardinal Rule

**Never place a coordinate in a scenario YAML without first verifying it is
on the correct terrain for that entity's domain.**

The global_land_mask library at 1km resolution correctly identifies ocean
vs land for the majority of Southeast Asia. However it has edge cases near:
- Narrow channels and straits (Malacca, Singapore, Lombok)
- Coastal ports and harbours (points may fall on the harbour wall, not water)
- Small islands

Run `tools/verify_coords.py` on every coordinate before accepting it.
If it fails, use the nearest valid fix returned by the tool.

---

## STEP 1: UNDERSTAND THE SCENARIO REQUEST

Before touching any file, extract these facts from the scenario description:

```
Geographic region:    [e.g. Strait of Malacca, central section]
Scenario archetype:   [see catalogue below]
Nations involved:     [MY / ID / SG / PH / other]
Agencies involved:    [MMEA, RMN, RMAF, TNI-AL, RSN, etc.]
Duration (minutes):   [recommended: 30-90min]
Demo speed:           [1x, 2x, 5x — affects how long it runs]
Audience:             [military officials, civilian, mixed]
```

---

## STEP 2: SELECT FORCES FROM THE ORBAT LIBRARY

Read the relevant ORBAT files in `reference/orbat/`:
- `malaysia.yaml` — RMN, RMAF, MMEA, RMP Marine, Customs & Immigration
- `indonesia.yaml` — TNI-AL, TNI-AU, Bakamla, Polairud
- `singapore.yaml` — RSN, RSAF, PCG, MPA Singapore
- `entity_types.yaml` — canonical type→SIDC→domain→speed mapping

**Selection rules:**
1. Pick the home base that makes geographic sense for the scenario
2. Use realistic vessel names from the ORBAT (not invented callsigns)
3. Mark invented/composite callsigns clearly with `# fictional`
4. Use the correct `entity_type` from entity_types.yaml — not an approximation
5. Check the SIDC is correct for the standard identity (Friend/Neutral/Unknown/Hostile)

---

## STEP 3: SELECT AND VERIFY ALL COORDINATES

### 3a. Start with the reference coordinates in `reference/geography/candidate_coords.yaml`

These are pre-verified base positions for every naval base, airfield, and key
port in the region. Use them as entity starting positions where possible.

If you need a patrol position or waypoint that is not in the reference:

### 3b. Generate candidate coordinates

Use the geographic bounding boxes below to generate candidates that are
definitely in open water for the region.

**STRAIT OF MALACCA — Open Water Reference Grid**

The strait runs roughly NW-SE between the Malay Peninsula and Sumatra.
VERIFIED open-water positions (passed global_land_mask check):

| Label              | Lat    | Lon     | Notes                          |
|--------------------|--------|---------|--------------------------------|
| MAL-NW-1           | 5.20°N | 99.80°E | North strait, off Penang       |
| MAL-NW-2           | 4.50°N | 100.00°E| Central-north strait           |
| MAL-CTR-1          | 4.00°N | 100.20°E| Central strait — clear water   |
| MAL-CTR-2          | 3.50°N | 100.50°E| Central strait                 |
| MAL-SE-1           | 3.00°N | 100.80°E| Southern central               |
| MAL-SE-2           | 2.50°N | 101.20°E| Southern strait — verify!      |
| MAL-SE-3           | 2.00°N | 102.00°E| Southern strait — verify!      |

⚠️ The strait narrows significantly below 3°N. Always run verify_coords.py
on any waypoint south of 3°N in the Malacca area.

**SINGAPORE STRAIT — Open Water Reference Grid**

| Label              | Lat    | Lon     | Notes                          |
|--------------------|--------|---------|--------------------------------|
| SIN-W-1            | 1.25°N | 103.50°E| West approach                  |
| SIN-CTR-1          | 1.20°N | 103.80°E| Central Singapore Strait       |
| SIN-E-1            | 1.20°N | 104.20°E| East approach                  |

**SOUTH CHINA SEA (West) — Open Water Grid**

| Label              | Lat    | Lon     | Notes                          |
|--------------------|--------|---------|--------------------------------|
| SCS-W-1            | 3.80°N | 104.50°E| Off Pahang coast               |
| SCS-W-2            | 5.00°N | 104.80°E| Off Terengganu                 |
| SCS-W-3            | 6.50°N | 105.00°E| Off Kelantan                   |

**SULU SEA / ESSZONE — Open Water Grid**

| Label              | Lat    | Lon     | Notes                          |
|--------------------|--------|---------|--------------------------------|
| SULU-1             | 5.50°N | 118.50°E| Central ESSZONE               |
| SULU-2             | 4.50°N | 119.00°E| Southern ESSZONE              |
| SULU-3             | 6.00°N | 119.50°E| Northern ESSZONE              |
| SULU-4             | 7.00°N | 120.50°E| Open Sulu Sea                 |

### 3c. Verify every coordinate with the tool

```bash
# Single coordinate check
python tools/verify_coords.py --lat 4.0 --lon 100.2 --domain MARITIME

# Batch check a candidate list
python tools/verify_coords.py reference/geography/candidate_coords.yaml

# Check all waypoints in a scenario file (run before deployment)
python tools/verify_scenario.py config/scenarios/scn_mal_01.yaml
```

**A coordinate is only accepted when verify_coords.py returns PASS.**

If it returns FAIL with a suggested fix:
- If the fix is within 2km of the original: accept it and update the coordinate
- If the fix is >2km away: question whether the original location was correct
- Never use `skip_terrain_check: true` to bypass a failing coordinate —
  only use it after you have confirmed the coordinate is correct by other means
  (e.g. satellite imagery confirms it is coastal/harbour)

---

## STEP 4: CALCULATE INTERCEPT PHYSICS

Every INTERCEPT event must be physically achievable. Calculate BEFORE writing events.

### Physics Template

```
ORDER issued at:     T+[order_time] minutes
Responding entity:   [callsign]
Entity position at order time: [interpolate from waypoints]
Target position at order time: [interpolate from waypoints]
Distance (nm):       [calculate using geodesic distance]
Responding entity max speed (kn): [from entity_types.yaml]
Transit time (min):  distance / speed * 60
Arrival time:        order_time + transit_time
Event time:          must be >= arrival_time
```

### Distance Quick Reference (1° latitude ≈ 60nm, 1° longitude ≈ 60nm at equator)

```python
# Use this formula for rough checks:
import math
def dist_nm(lat1, lon1, lat2, lon2):
    dlat = (lat2 - lat1) * 60  # nautical miles
    dlon = (lon2 - lon1) * 60 * math.cos(math.radians((lat1+lat2)/2))
    return math.sqrt(dlat**2 + dlon**2)
```

### Speed Reference

| Entity Type             | Patrol Speed (kn) | Max Sprint (kn) |
|-------------------------|-------------------|-----------------|
| MMEA_PATROL             | 10–12             | 22              |
| MMEA_FAST_INTERCEPT     | 15–20             | 45              |
| MIL_NAVAL (frigate/OPV) | 12–15             | 28–30           |
| MIL_NAVAL_FIC           | 15–20             | 35–40           |
| RMP_MARINE_PATROL       | 10–12             | 35              |
| RMAF_MPA (Beechcraft)   | 180               | 270             |
| RMAF_MPA (CN-235)       | 150               | 200             |
| RMAF_HELICOPTER (EC725) | 100               | 150             |
| RMAF_FIGHTER            | 400               | 1000+           |

### Pre-positioning Rule

If an intercept event must happen within 30 minutes of a scenario starting,
the responding unit **must start within range** at scenario start.
Do not rely on transit from a home base if that transit time exceeds the
available window. Pre-position the unit on patrol closer to the action.

---

## STEP 5: DESIGN THE EVENT TIMELINE

### Event Sequence Pattern (maritime intercept)

```
T+00:00  DETECTION    — First sensor contact or anomaly detected
T+02:00  ALERT        — Watch centre evaluates and escalates
T+04:00  ALERT        — Cross-agency notification
T+06:00  ORDER        — First asset ordered to investigate/intercept
T+08:00  ORDER        — Additional assets ordered
T+10:00  DETECTION    — Surveillance update (aircraft/radar confirms)
T+[X]    INTERCEPT    — First vessel arrives (must pass physics check)
T+[X+3]  ALERT        — Contact report: what do they see?
T+[X+5]  ORDER        — Boarding team authorised
T+[X+8]  BOARDING     — Boarding team transfers
T+[X+12] DETECTION    — What boarding team finds
T+[X+15] ALERT        — Endstate — outcome summarised for officials
```

### Event Types (valid values for the `type` field)
```
DETECTION    — Sensor/visual contact, intelligence report
ALERT        — Notification, assessment, escalation
ORDER        — Command to an entity to take action
AIS_LOSS     — AIS transponder goes dark (target: entity_id)
INTERCEPT    — Physical intercept achieved
BOARDING     — Boarding team on target vessel
SAR_CALLOUT  — SAR activation (for humanitarian scenarios)
DISTRESS     — SSAS/MAYDAY received
ENDSTATE     — Scenario conclusion narrative
```

### Event Narrative Writing Guidelines
- Write as if narrating from the operations centre
- Include relevant technical detail (speed, bearing, MMSI, channel)
- Name the agencies and assets explicitly
- Keep severity consistent: INFO → WARNING → CRITICAL → INFO (resolution)

---

## STEP 6: CONFIGURE BACKGROUND TRAFFIC

Background entities require area or route IDs from the geodata files.
Current available areas and routes:

**Verify available geodata before referencing:**
```bash
python tools/list_geodata.py
```

For Malacca Strait scenarios, the following route/area IDs are available
after the Malacca geodata has been created (Claude Code task):
- `malacca_tss_northwestbound` — NW TSS lane
- `malacca_tss_southeastbound` — SE TSS lane
- `malacca_fishing_grounds` — Malaysian coastal fishing
- `singapore_strait_tss` — Singapore Strait TSS

If a route/area does not exist in the geodata, do NOT reference it —
background entities for that type will silently fail to spawn.
Either create the geodata first (Claude Code task) or omit that background type.

---

## STEP 7: WRITE THE SCENARIO YAML

### File naming convention
```
config/scenarios/scn_[region_code]_[sequence].yaml

Region codes:
  mal — Strait of Malacca
  sin — Singapore Strait
  scs — South China Sea
  ess — ESSZONE (Eastern Sabah)
  sul — Sulu Sea
  cel — Celebes Sea
  nat — Natuna Islands
  and — Andaman Sea
```

### YAML Structure Template

```yaml
# SCN-XXX-NN: [Short Name] — [Region]
# [Standard header with physics validation summary]

scenario:
  name: "SCN-XXX-NN: [Full Name]"
  description: |
    [2-3 paragraph description]
    Demonstrates: [comma-separated capability list]
  duration_minutes: [30-120]
  center: { lat: [verified open water], lon: [verified open water] }
  zoom: [7-10, higher = more zoomed in]

  background_entities:
    - type: [from entity_types.yaml]
      count: [2-20]
      route: [verified route_id from geodata]  # OR
      area:  [verified zone_id from geodata]
      speed_variation: 0.1
      metadata:
        ais_active: true

  scenario_entities:
    - id: "[AGENCY]-[TYPE]-[NNN]"
      type: [from entity_types.yaml]
      callsign: "[realistic callsign from ORBAT]"
      agency: [MMEA|MIL|RMP|RMAF|CI|CIVILIAN]
      initial_position: { lat: [VERIFIED], lon: [VERIFIED] }
      behavior: "patrol"   # or "standby" or "waypoint"
      waypoints:
        - { lat: [VERIFIED], lon: [VERIFIED], speed: [kn], time: "HH:MM" }
      metadata:
        skip_terrain_check: false  # Only set true if VERIFIED via satellite
        vessel_type: "[realistic type]"

  events:
    - time: "HH:MM"
      type: "[event type]"
      description: "[Operational narrative — 1-3 sentences]"
      [additional fields per event type]
      severity: "[INFO|WARNING|CRITICAL]"
```

---

## STEP 8: VALIDATE BEFORE DEPLOYMENT

Run the full pre-flight check:

```bash
# 1. Validate YAML syntax and schema
python tools/validate_scenario.py config/scenarios/scn_xxx_nn.yaml

# 2. Verify all coordinates
python tools/verify_coords.py config/scenarios/scn_xxx_nn.yaml

# 3. Check intercept physics (if implemented)
python tools/check_physics.py config/scenarios/scn_xxx_nn.yaml
```

All three must pass before the file is deployed to the server.

---

## SCENARIO ARCHETYPE CATALOGUE

### Type 1: AIS Dark Target Intercept
**Trigger:** Vessel kills AIS mid-transit
**Response:** MMEA surveillance → fast intercept → MPA support → boarding
**Good for:** Demonstrating maritime domain awareness, AIS monitoring
**Region:** Malacca Strait, Singapore Strait, SCS transit lanes

### Type 2: Armed Robbery at Sea (ARAS)
**Trigger:** SSAS distress from commercial vessel
**Response:** MMEA + RMN response, helicopter overwatch, tactical boarding
**Good for:** Multi-agency coordination, high-drama narratives
**Region:** Malacca Strait, Singapore approaches

### Type 3: Trilateral Coordinated Patrol (MALSINDO)
**Trigger:** Routine patrol — incident triggers cross-border coordination
**Response:** Malaysia + Indonesia + Singapore coordinated response
**Good for:** Coalition COP, handoff procedures, political messaging
**Region:** Malacca Strait TSS, Singapore Strait

### Type 4: IUU Fishing Intercept
**Trigger:** Foreign fishing fleet detected in EEZ
**Response:** MMEA intercept, RMN support, RMP Marine boarding, CI processing
**Good for:** Law enforcement workflow, multi-agency boarding operations
**Region:** ESSZONE, South China Sea, Malacca Strait approaches

### Type 5: Mass Casualty SAR
**Trigger:** Vessel collision or grounding with mass casualties
**Response:** MRSC activation, IAMSAR, multi-vessel convergence, MEDEVAC
**Good for:** Humanitarian operations, non-combat response
**Region:** TSS zones (where collisions occur), busy shipping areas

### Type 6: Human Trafficking Interdiction
**Trigger:** Intel report on migrant vessel
**Response:** MMEA + Immigration coordinated intercept, processing ashore
**Good for:** Law enforcement, Immigration agency role in COP
**Region:** Malacca Strait (Indonesia→Malaysia routes), Andaman

### Type 7: Kidnapping-for-Ransom Response (KFR)
**Trigger:** Village/vessel attack by armed group
**Response:** Military + RMP GOF + MMEA full activation
**Good for:** High-intensity operations, aerial insertion, pursuit
**Region:** ESSZONE (Operation Pasir context)

### Type 8: EEZ Intrusion / Naval Standoff
**Trigger:** Foreign naval vessel enters disputed waters
**Response:** RMN intercept and shadow, diplomatic notification
**Good for:** Maritime sovereignty, naval domain
**Region:** Natuna Islands area, Spratlys, Ambalat

### Type 9: Narcotics/Contraband Intercept
**Trigger:** Intel tip, drone detection, or radar anomaly
**Response:** MMEA + Customs coordinated intercept, boarding, seizure
**Good for:** Customs agency role, contraband detection
**Region:** Any strait or EEZ

### Type 10: Oil Spill Crisis
**Trigger:** Tanker grounding or collision causing spill
**Response:** MMEA, DoE, Port Authority, exclusion zones, boom deployment
**Good for:** Environmental ops, civilian-military blend, dynamic zones
**Region:** Malacca TSS, port approaches

---

## HOW SCENARIO IDEAS ARE DEVELOPED

1. **Start with the geography** — what operational challenges does this region
   actually face? Research real incidents (piracy reports, RECAAP database,
   Malaysian newspaper archives, MMEA annual reports).

2. **Identify the realistic participants** — which agencies would actually
   respond in this region? Read the ORBAT files. Which vessels are homeported
   within response range?

3. **Define the scenario objective** — what does this scenario prove the
   system can do? Each scenario should demonstrate 2-4 distinct capabilities.

4. **Work backwards from the climax** — decide what the key moment is
   (boarding, intercept, rescue), then build the timeline that leads to it.

5. **Apply the physics test early** — can the responders physically reach
   the scene in time? If not, adjust starting positions or scenario timing.

---

## REGIONAL GEOGRAPHY QUICK REFERENCE

### Malacca Strait
- Runs NW-SE between Peninsular Malaysia and Sumatra
- Width: ~250km north (Langkawi) to ~65km south (Singapore)
- **Malaysian coast (east side of strait):**
  - Penang: 5.4°N, 100.3°E
  - Lumut/Perak coast: 4.2°N, 100.6°E
  - Port Klang: 3.0°N, 101.4°E (coast is ~101.4°E at 3°N)
  - Malacca city: 2.2°N, 102.2°E (east bank of strait)
- **Sumatran coast (west side of strait):**
  - Belawan/Medan area: 3.8°N, 98.7°E
  - Dumai: 1.7°N, 101.5°E
- **TSS centre line (approximate):**
  - At 5°N: ~100.0°E
  - At 4°N: ~100.3°E
  - At 3°N: ~100.8°E
  - At 2°N: ~101.5°E
- **Critical insight:** The strait at 2-3°N is narrow. Positions at 102°E
  at those latitudes are ON the Malay Peninsula, not in the strait.

### Singapore Strait
- Width: ~15km at narrowest
- TSS centre: ~1.2°N, 103.5-104.2°E
- Singapore main island: 1.3°N, 103.8°E

### South China Sea (West Malaysia)
- Open water begins ~50nm east of the coast
- At Pahang coast (3.8°N), open water from ~104.0°E eastward

### ESSZONE (Sabah)
- Operational area: 4-7°N, 117-120°E
- Sandakan: 5.84°N, 118.07°E
- Semporna: 4.48°N, 118.62°E
- Tawau: 4.25°N, 117.89°E
- Open Sulu Sea: 5-7°N, 119-121°E

---

## KNOWN TERRAIN CHECKER EDGE CASES

The global_land_mask library (GLOBE dataset, 1km resolution) has known issues at:

1. **Port Klang area (3.0°N, 101.4°E)** — the harbour and reclaimed land
   can cause water points near the coast to fail. Use positions 0.1° offshore.

2. **Malacca Strait below 2.5°N** — strait is narrow, both coasts close.
   Any position east of 101.5°E at 2°N is likely on the Malay Peninsula.
   Verify all waypoints here.

3. **Singapore Strait** — extremely narrow. The checker may classify some
   TSS positions as land due to the small islands. Verify all Singapore area
   coordinates.

4. **Small islands** — positions on or near islands (Langkawi, Tioman, Redang)
   may fail even when the intent is the surrounding water. Move 1-2nm offshore.

5. **Harbour positions** — many naval base positions are technically on
   reclaimed land or at the harbour wall. Use `skip_terrain_check: true`
   ONLY after confirming via satellite imagery that the entity spawns in
   the correct location for the scenario narrative.
