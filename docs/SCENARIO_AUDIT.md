# Demo Scenario Audit — Entity Types, SIDCs & Event Alignment

## SIDC Structure Reference (MIL-STD-2525D, 20 digits)

```
Pos 1-2:   Coding Scheme (10 = Set A / 2525D)
Pos 3:     Context (0 = Reality)
Pos 4:     Standard Identity (3=Friend, 4=Neutral, 5=Suspect, 6=Hostile)
Pos 5-6:   Symbol Set (01=Air, 10=Land Unit, 15=Land Equipment, 30=Sea Surface)
Pos 7:     Status (0=Present)
Pos 8:     HQ/TF/FD (0=N/A)
Pos 9-10:  Echelon/Mobility (00=N/A)
Pos 11-16: Entity Code (from JMSML)
Pos 17-18: Sector 1 Modifier
Pos 19-20: Sector 2 Modifier
```

---

## PART A: Entity-by-Entity Audit

### Legend
- ✅ = Correct, no changes needed
- ❌ = Wrong type or SIDC — must fix
- ⚠️ = Partially correct — improvement needed
- 🆕 = New type needed in sidcMap

---

### SUSPECT / HOSTILE VESSELS

| Entity ID | Callsign | Current Type | Correct Type | SIDC | Entity Code | Status |
|-----------|----------|-------------|-------------|------|-------------|--------|
| IFF-001 | Unknown Trawler 1 | SUSPECT_VESSEL | SUSPECT_VESSEL | `10053000001400000000` | 140000 (Non-Military) | ✅ |
| IFF-002 | Unknown Trawler 2 | SUSPECT_VESSEL | SUSPECT_VESSEL | `10053000001400000000` | 140000 | ✅ |
| IFF-003 | Unknown Trawler 3 | SUSPECT_VESSEL | SUSPECT_VESSEL | `10053000001400000000` | 140000 | ✅ |
| IFF-004 | Unknown Trawler 4 | SUSPECT_VESSEL | SUSPECT_VESSEL | `10053000001400000000` | 140000 | ✅ |
| IFF-005 | Unknown Mothership | SUSPECT_VESSEL | SUSPECT_VESSEL | `10053000001400000000` | 140000 | ✅ |
| HOSTILE-001 | Suspect Speedboat 1 | SUSPECT_VESSEL | SUSPECT_VESSEL → HOSTILE_VESSEL | see note | 140000 | ⚠️ |
| HOSTILE-002 | Suspect Speedboat 2 | SUSPECT_VESSEL | SUSPECT_VESSEL → HOSTILE_VESSEL | see note | 140000 | ⚠️ |

**HOSTILE-001 / HOSTILE-002 note:** These start as unknown contacts detected by
radar at 01:05. At that point, SUSPECT (identity=5) is correct — they haven't
attacked yet. But after the armed attack at 01:23, they should change to HOSTILE
(identity=6), switching the SIDC from `10053000001400000000` to `10063000001400000000`.
This changes the symbol frame from a yellow diamond to a red diamond — critical
visual feedback for the demo audience.

**Required:** A new event type or event action that changes an entity's standard
identity (and therefore SIDC) mid-scenario. The INCIDENT event at 01:23 should
trigger this reclassification for both HOSTILE-001 and HOSTILE-002.

---

### MMEA (Maritime Enforcement)

| Entity ID | Callsign | Current Type | Correct Type | SIDC | Entity Code | SVG Icon | Status |
|-----------|----------|-------------|-------------|------|-------------|----------|--------|
| MMEA-PV-101 | KM Semporna | MMEA_PATROL | MMEA_PATROL | `10033000001204020000` | 120402 (Station Ship) | SeaSurface/30_120402.svg | ✅ |
| MMEA-FI-101 | KM Penggalang 7 | MMEA_FAST_INTERCEPT | MMEA_FAST_INTERCEPT | `10033000001204010000` | 120401 (Patrol Craft) | SeaSurface/30_120401.svg | ✅ |
| MMEA-PV-102 | KM Sangitan | MMEA_PATROL | MMEA_PATROL | `10033000001204020000` | 120402 (Station Ship) | SeaSurface/30_120402.svg | ✅ |

---

### RMN (Navy)

| Entity ID | Callsign | Current Type | Correct Type | SIDC | Entity Code | SVG Icon | Status |
|-----------|----------|-------------|-------------|------|-------------|----------|--------|
| RMN-FIC-101 | KD G2000 Alpha | MIL_NAVAL | **MIL_NAVAL_FIC** | `10033000001204010000` | 120401 (Patrol Craft) | SeaSurface/30_120401.svg | ❌ |
| RMN-PV-101 | KD Keris | MIL_NAVAL | MIL_NAVAL | `10033000001201030000` | 120103 (Corvette) | SeaSurface/30_120103.svg | ✅ |
| RMN-FIC-201 | KD G2000 Bravo | MIL_NAVAL | **MIL_NAVAL_FIC** | `10033000001204010000` | 120401 (Patrol Craft) | SeaSurface/30_120401.svg | ❌ |
| RMN-FIC-202 | KD G2000 Charlie | MIL_NAVAL | **MIL_NAVAL_FIC** | `10033000001204010000` | 120401 (Patrol Craft) | SeaSurface/30_120401.svg | ❌ |

**Why:** The G2000 Mk II Fast Interceptor Craft is a small, fast patrol boat — NOT a
corvette. MIL_NAVAL maps to entity code 120103 (Corvette, matching KD Keris), but
the G2000 is functionally a coastal patrol craft. MIL_NAVAL_FIC already exists in
the sidcMap with the correct code 120401 (Patrol, Coastal, Patrol Craft).

**Fix:** Change `type: MIL_NAVAL` → `type: MIL_NAVAL_FIC` for all three G2000 entities.

---

### RMAF (Air Force)

| Entity ID | Callsign | Current Type | Correct Type | SIDC | Entity Code | SVG Icon | Status |
|-----------|----------|-------------|-------------|------|-------------|----------|--------|
| RMAF-MPA-101 | TUDM MPA Beechcraft | RMAF_TRANSPORT | **RMAF_MPA** | `10030100001101040000` | 110104 (FW Patrol) | Air/01_110104.svg | ❌ |
| RMAF-HELI-101 | TUDM EC725 Sandakan | RMAF_HELICOPTER | RMAF_HELICOPTER | `10030100001102000000` | 110200 (Rotary Wing) | Air/01_110200.svg | ✅ |
| RMAF-HELI-201 | TUDM EC725 Hunter | RMAF_HELICOPTER | RMAF_HELICOPTER | `10030100001102000000` | 110200 | Air/01_110200.svg | ✅ |
| RMAF-HELI-202 | TUDM Blackhawk 1 | RMAF_HELICOPTER | RMAF_HELICOPTER | `10030100001102000000` | 110200 | Air/01_110200.svg | ✅ |

**Why RMAF-MPA-101 is wrong:** The Beechcraft King Air 350 is RMAF's maritime patrol
aircraft (MPA). RMAF_TRANSPORT maps to entity code 110131 (Fixed Wing, Passenger)
with "C" and "L" modifiers — that's a cargo/logistics transport like a C-130.
RMAF_MPA maps to 110104 (Fixed Wing, Patrol) which is specifically the MPA icon.

**Visual difference:** RMAF_TRANSPORT shows "PX" text with C+L modifier letters.
RMAF_MPA shows the correct patrol aircraft icon (surveillance aircraft silhouette).

**Fix:** Change `type: RMAF_TRANSPORT` → `type: RMAF_MPA` for RMAF-MPA-101.

---

### RMP (Police)

| Entity ID | Callsign | Current Type | Correct Type | SIDC | Entity Code | SVG Icon | Status |
|-----------|----------|-------------|-------------|------|-------------|----------|--------|
| RMP-MP-101 | PDRM Marine 01 | RMP_PATROL_CAR | **RMP_MARINE_PATROL** | `10033000001204010000` | 120401 (Patrol Craft) | SeaSurface/30_120401.svg | ❌ |
| RMP-MP-102 | PDRM Marine 02 | RMP_PATROL_CAR | **RMP_MARINE_PATROL** | `10033000001204010000` | 120401 (Patrol Craft) | SeaSurface/30_120401.svg | ❌ |
| RMP-MP-201 | PDRM Marine Semporna 01 | RMP_PATROL_CAR | **RMP_MARINE_PATROL** | `10033000001204010000` | 120401 (Patrol Craft) | SeaSurface/30_120401.svg | ❌ |
| RMP-GOF-201 | GOF Tactical Team Alpha | RMP_TACTICAL_TEAM | RMP_TACTICAL_TEAM | `10031000001211000000` | 121100 (SOF) | Land/10_121100.svg | ✅ |
| RMP-GOF-202 | GOF Team Bravo | RMP_TACTICAL_TEAM | RMP_TACTICAL_TEAM | `10031000001211000000` | 121100 (SOF) | Land/10_121100.svg | ✅ |

**Why RMP-MP-* are wrong:** The metadata says `vessel_type: "Rigid Hull Fender Boat"` —
these are BOATS, not patrol cars. RMP_PATROL_CAR is a Ground Vehicle type (Symbol
Set 15 or 10), which means these marine police vessels currently render with a ground
vehicle icon in a rectangle frame, instead of a maritime icon in a semicircle frame.

**Fix:** Create new type `RMP_MARINE_PATROL` in the sidcMap:
```js
'RMP_MARINE_PATROL': '10033000001204010000',  // Friend, Sea Surface, Patrol Craft
```
This gives them the correct maritime frame (cyan semicircle) with patrol craft icon.
Also update the entity type definitions so the domain is correctly set to MARITIME.

---

### CI (Customs & Immigration)

| Entity ID | Callsign | Current Type | Correct Type | SIDC | Entity Code | SVG Icon | Status |
|-----------|----------|-------------|-------------|------|-------------|----------|--------|
| CI-TEAM-101 | Customs Boarding Team A | CI_OFFICER | CI_OFFICER | `10031500001703000000` | 170300 (LE Customs) | Land/15_170300.svg | ✅ |
| CI-IMMI-101 | Immigration Team Sandakan | CI_IMMIGRATION_TEAM | CI_IMMIGRATION_TEAM | `10031500001703000000` | 170300 (LE Customs) | Land/15_170300.svg | ✅ |
| CI-BORDER-201 | Immigration Rapid Response | CI_OFFICER | CI_OFFICER | `10031500001703000000` | 170300 (LE Customs) | Land/15_170300.svg | ✅ |

---

### MIL (Army)

| Entity ID | Callsign | Current Type | Correct Type | SIDC | Entity Code | SVG Icon | Status |
|-----------|----------|-------------|-------------|------|-------------|----------|--------|
| MIL-INF-201 | Malay Regiment Squad 1 | MIL_INFANTRY_SQUAD | MIL_INFANTRY_SQUAD | `10031000001201000000` | 120100 (Infantry) | Land/10_120100.svg | ✅ |

---

### BACKGROUND ENTITIES

| Type | Count | Domain | SIDC | Entity Code | Status |
|------|-------|--------|------|-------------|--------|
| CIVILIAN_FISHING | 30 | Maritime | `10043000001402000000` | 140200 (Fishing) | ✅ |
| CIVILIAN_CARGO | 6 | Maritime | `10043000001401010000` | 140101 (Merchant Cargo) | ✅ |
| CIVILIAN_TANKER | 4 | Maritime | `10043000001401020000` | 140102 (Merchant Tanker) | ✅ |
| CIVILIAN_PASSENGER | 4 | Maritime | `10043000001401030000` | 140103 (Merchant Passenger) | ✅ |
| CIVILIAN_LIGHT | 3 | Air | `10040100001201000000` | 120100 (Civilian FW) | ✅ |

---

## PART B: Required Changes to sidcMap (config.js)

Add this new entry:

```js
// In sidcMap, add:
'RMP_MARINE_PATROL':  '10033000001204010000',  // Friend, Sea Surface, Patrol, Coastal, Patrol Craft
```

Also need the corresponding SVG frame `Frames/0_3_30_0.svg` (already used for MMEA
vessels) and icon `SeaSurface/30_120401.svg` (already used for MMEA_FAST_INTERCEPT).
No new SVG files required.

Also need `HOSTILE_VESSEL` in the sidcMap for the affiliation change:
```js
'HOSTILE_VESSEL':     '10063000001400000000',  // Hostile, Sea Surface, Non-Military
```
This entry already exists in the REPLACE_MILSYMBOL spec but verify it's in the
deployed config.js.

---

## PART C: Event-Simulation Alignment — THE BIG PROBLEM

### The Core Issue

Events fire at hardcoded times. Entity movement is physics-based. These are
completely disconnected. The timeline says "KM Sangitan intercepts Trawler 1"
at 00:30, but the InterceptMovement calculates actual convergence based on
speeds and distances. If those don't match, the COP shows:

- **Timeline says:** "MMEA KM Sangitan intercepts Trawler 1" ✅
- **Map shows:** KM Sangitan still 60km from Trawler 1 ❌

This is exactly what David is seeing. The timeline is "just saying stuff" that
doesn't correspond to what's actually happening on screen.

### Physics Check: Every INTERCEPT Event

I calculated actual transit distances vs. available time for each intercept.
Speeds are max speeds from the entity type definitions.

#### Event at 00:30 — MMEA-PV-102 intercepts IFF-001
- ORDER issued: 00:04
- MMEA-PV-102 starts at: (5.50, 118.30)
- IFF-001 at 00:04 is at approx: (5.72, 118.82) — interpolating waypoints
- Distance: ~65 km
- MMEA_PATROL max speed: 30 kts (56 km/h)
- Travel time needed at max speed: ~70 minutes
- Time available (00:04 → 00:30): 26 minutes → covers ~24 km
- **❌ PHYSICALLY IMPOSSIBLE — short by ~41 km**

#### Event at 00:32 — MMEA-FI-101 intercepts IFF-003
- ORDER issued: 00:16
- MMEA-FI-101 starts at: (4.48, 118.61) — Semporna
- IFF-003 at 00:16 is at approx: (5.66, 118.79)
- Distance: ~135 km
- MMEA_FAST_INTERCEPT max speed: 45 kts (83 km/h)
- Travel time needed: ~98 minutes
- Time available (00:16 → 00:32): 16 minutes → covers ~22 km
- **❌ PHYSICALLY IMPOSSIBLE — short by ~113 km**

#### Event at 00:35 — RMP-MP-102 boards IFF-001
- Depends on MMEA-PV-102 having already intercepted, which didn't happen
- **❌ CASCADING FAILURE**

#### Event at 00:38 — RMN-FIC-101 intercepts IFF-004
- ORDER issued: 00:08
- RMN-FIC-101 starts at: (5.84, 118.10) — Sandakan
- IFF-004 at 00:08 is at approx: (5.76, 118.79)
- Distance: ~78 km
- MIL_NAVAL (G2000) max speed: ~35 kts (65 km/h)
- Travel time needed: ~72 minutes
- Time available (00:08 → 00:38): 30 minutes → covers ~32 km
- **❌ PHYSICALLY IMPOSSIBLE — short by ~46 km**

#### Event at 00:40 — MMEA-PV-101 intercepts IFF-005
- ORDER issued: 00:10
- MMEA-PV-101 starts at: (5.84, 118.07) — Sandakan coast
- IFF-005 at 00:10 is at approx: (5.80, 118.90)
- Distance: ~93 km
- Travel time needed at 30 kts: ~100 minutes
- Time available (00:10 → 00:40): 30 minutes → covers ~28 km
- **❌ PHYSICALLY IMPOSSIBLE — short by ~65 km**

#### Part 2 Intercepts (01:55, 02:05) — similar problems likely

### Root Cause

The scenario was written as a narrative with dramatically-paced events, but
the entity starting positions are spread across the real ESSZONE geography
(Sandakan, Semporna, Lahad Datu — up to 200km apart). Real-world multi-agency
responses DO take hours. A 55-minute Part 1 can't accommodate realistic
transit times across these distances.

### Two-Part Fix

#### Fix 1: Architectural — Proximity-Triggered Events (Long Term)

INTERCEPT, BOARDING, and ARRIVAL events should NOT fire at fixed times.
They should fire when the simulation engine detects proximity:

```python
# In the event engine tick:
if event.type in ('INTERCEPT', 'BOARDING', 'ARRIVAL'):
    source = entity_store.get_entity(event.source)
    target = entity_store.get_entity(event.target)
    distance = haversine(source.position, target.position)
    if distance < INTERCEPT_RADIUS_KM:  # e.g., 0.5 km
        fire_event(event)
```

This makes the timeline truthful — it only announces an intercept when the
entities have actually converged. The `time` field in the YAML becomes a
"no earlier than" constraint rather than a fixed trigger.

For ORDER events, fixed times are correct — a commander issues an order at
a specific time. For outcome events (INTERCEPT, BOARDING, ARRIVAL), proximity
triggering is required.

#### Fix 2: Scenario Choreography — Tighten Distances (Short Term for Demo)

For the April demo, we need the scenario to work NOW. The practical fix:

**Move friendly force starting positions much closer to the action area.**

The fishing fleet operates around (5.65-5.85, 118.70-119.00). Instead of
having responders start at Sandakan port (118.07), Semporna (118.61), and
Labuan (115.25), put them on patrol NEAR the action:

| Entity | Current Start | Proposed Start | Rationale |
|--------|--------------|----------------|-----------|
| MMEA-PV-102 | (5.50, 118.30) | (5.60, 118.65) | Already on patrol near fleet |
| MMEA-PV-101 | (5.84, 118.07) | (5.75, 118.55) | Patrol route near fleet area |
| MMEA-FI-101 | (4.48, 118.61) | (5.55, 118.60) | Pre-positioned for quick response |
| RMN-FIC-101 | (5.84, 118.10) | (5.80, 118.50) | Patrol near fishing grounds |
| RMN-PV-101 | (5.20, 118.50) | (5.40, 118.70) | Nearby patrol |
| RMP-MP-101 | (4.48, 118.61) | (5.50, 118.55) | Marine police near area |
| RMP-MP-102 | (5.84, 118.07) | (5.65, 118.50) | Marine police nearby |

With these positions, 20-30 minute intercepts at max speed cover 20-30 km,
which is the actual distance to targets. The timeline becomes physically
plausible.

Aircraft (RMAF-MPA-101, RMAF-HELI-101) can keep their distant starting
positions since aircraft are fast enough — a Beechcraft at 220 kts covers
Labuan to ESSZONE (~350 km) in about 55 minutes.

For Part 2, apply the same principle — pre-position responders in the
Semporna area so the KFR response can unfold in the stated timeframe.

---

## PART D: Deploy Events Missing Destinations

Several ORDER events with `action: "deploy"` have no `destination` field.
Without a destination, the simulator has nowhere to send the entity:

| Time | Target | Description | Missing |
|------|--------|-------------|---------|
| 00:18 | RMP-MP-101, RMP-MP-102 | Marine Police deployed for boarding | `destination` |
| 00:20 | RMAF-HELI-101 | Helicopter dispatched from Lahad Datu | `destination` |
| 01:29 | RMAF-HELI-201 | EC725 for armed surveillance | `destination` |
| 01:30 | RMAF-HELI-202 | Blackhawk to airlift GOF Alpha | `destination` |
| 01:33 | RMN-FIC-202 | G2000 Charlie to block northern route | `destination` |

**Fix:** Add destinations for each:
```yaml
# 00:18 — Marine Police deploy to fishing fleet area
destination: { lat: 5.65, lon: 118.80 }

# 00:20 — Helicopter to fishing fleet overwatch
destination: { lat: 5.70, lon: 118.85 }

# 01:29 — EC725 to Pulau Bum Bum area for surveillance
destination: { lat: 4.50, lon: 118.68 }

# 01:30 — Blackhawk to Sandakan to pick up GOF Alpha, then to Semporna
destination: { lat: 5.84, lon: 118.07 }  # first leg: Sandakan pickup

# 01:33 — G2000 Charlie to northern blocking position
destination: { lat: 4.75, lon: 119.00 }
```

---

## PART E: Summary of All Required Changes

### Scenario YAML Changes

1. **RMAF-MPA-101**: `type: RMAF_TRANSPORT` → `type: RMAF_MPA`
2. **RMN-FIC-101**: `type: MIL_NAVAL` → `type: MIL_NAVAL_FIC`
3. **RMN-FIC-201**: `type: MIL_NAVAL` → `type: MIL_NAVAL_FIC`
4. **RMN-FIC-202**: `type: MIL_NAVAL` → `type: MIL_NAVAL_FIC`
5. **RMP-MP-101**: `type: RMP_PATROL_CAR` → `type: RMP_MARINE_PATROL` 🆕
6. **RMP-MP-102**: `type: RMP_PATROL_CAR` → `type: RMP_MARINE_PATROL` 🆕
7. **RMP-MP-201**: `type: RMP_PATROL_CAR` → `type: RMP_MARINE_PATROL` 🆕
8. Tighten starting positions for all responder entities (see Part C table)
9. Add `destination` to 5 deploy events (see Part D)
10. Add affiliation change mechanism for HOSTILE-001/002 at 01:23

### Config/Code Changes

11. Add `RMP_MARINE_PATROL` to sidcMap in config.js
12. Verify `HOSTILE_VESSEL` exists in sidcMap
13. Add `RMP_MARINE_PATROL` to entity type definitions with `domain: MARITIME`
14. Implement proximity-triggered events for INTERCEPT/BOARDING/ARRIVAL types

### Also Check in edge-c2-simulator-plan.md

15. The Strait of Malacca example scenario also has `RMAF-MPA-001` with
    `type: RMAF_TRANSPORT` and callsign "TUDM Beechcraft MPA" — same bug.
    Should be `type: RMAF_MPA`.
