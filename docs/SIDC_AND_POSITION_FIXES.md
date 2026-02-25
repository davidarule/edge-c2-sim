# SIDC Codes, Entity Positions & Symbol Fixes

## Issue 1: SIDC Codes Are Wrong

The current `sidcMap` in `cop/src/config.js` has incorrect **Symbol Set** codes
for most entity types. This is why the helicopter appears upside-down — it's
using Symbol Set 15 (Land Equipment) instead of 01 (Air).

### MIL-STD-2525D SIDC Structure (20 characters)

```
Position  Meaning              Values
------------------------------------------------------
1-2       Version              10 (always)
3         Context              0 = Reality
4         Standard Identity    0=Pending 1=Unknown 2=Assumed Friend
                               3=Friend 4=Neutral 5=Suspect 6=Hostile
5-6       Symbol Set           01=Air  10=Land Unit  15=Land Equipment
                               30=Sea Surface  35=Subsurface
7         Status               0=Present 1=Planned
8-9       HQ/TF/FD             00=Not applicable
10        Echelon/Mobility     0=Unspecified
11-16     Entity/Type/Subtype  6 digits (2 digits each)
17-18     Modifier 1           00=None
19-20     Modifier 2           00=None
```

### What's Wrong in Current Config

| Entity Type | Current Symbol Set | WRONG | Should Be |
|---|---|---|---|
| RMAF_FIGHTER | 10 (Land Unit) | ✗ | 01 (Air) |
| RMAF_HELICOPTER | 15 (Land Equipment) | ✗ | 01 (Air) |
| RMAF_TRANSPORT | 10 (Land Unit) | ✗ | 01 (Air) |
| RMP_HELICOPTER | 15 (Land Equipment) | ✗ | 01 (Air) |
| CIVILIAN_COMMERCIAL | 10 (Land Unit) | ✗ | 01 (Air) |
| CIVILIAN_LIGHT | 10 (Land Unit) | ✗ | 01 (Air) |
| MIL_INFANTRY_SQUAD | 10 (Land Unit) but entity code is maritime | ✗ | 10 (Land Unit) with infantry entity code |
| RMP_PATROL_CAR | 10 (Land Unit) | ⚠ | 10 (Land Unit) — symbol set OK, entity code wrong |

The maritime entities (MMEA_PATROL, MIL_NAVAL, etc.) correctly use Symbol
Set 30, but their entity codes (positions 11-16) appear to be the same
generic code for all — they should differentiate between patrol boats,
frigates, fishing vessels, etc.

### Corrected sidcMap

Replace the entire `sidcMap` object in `cop/src/config.js`:

```javascript
sidcMap: {
  // ===== MARITIME (Symbol Set 30 = Sea Surface) =====

  // Friend — MMEA patrol vessel
  // 3=Friend, 30=Sea Surface, Entity 120402=Patrol Boat
  'MMEA_PATROL':          '10033000001204020000',

  // Friend — MMEA fast intercept craft
  // 3=Friend, 30=Sea Surface, Entity 120401=Patrol Coastal
  'MMEA_FAST_INTERCEPT':  '10033000001204010000',

  // Friend — RMN Naval (G2000 is corvette-class)
  // 3=Friend, 30=Sea Surface, Entity 120103=Corvette
  'MIL_NAVAL':            '10033000001201030000',

  // Suspect — unidentified vessel
  // 5=Suspect, 30=Sea Surface, Entity 140000=Civilian
  'SUSPECT_VESSEL':       '10053000001400000000',

  // Hostile — armed vessel (KFR speedboats)
  // 6=Hostile, 30=Sea Surface, Entity 140000=Civilian
  'HOSTILE_VESSEL':       '10063000001400000000',

  // Neutral — cargo ship
  // 4=Neutral, 30=Sea Surface, Entity 140101=Cargo
  'CIVILIAN_CARGO':       '10043000001401010000',

  // Neutral — fishing vessel
  // 4=Neutral, 30=Sea Surface, Entity 140200=Fishing
  'CIVILIAN_FISHING':     '10043000001402000000',

  // Neutral — tanker
  // 4=Neutral, 30=Sea Surface, Entity 140102=Tanker
  'CIVILIAN_TANKER':      '10043000001401020000',

  // Neutral — passenger/ferry
  // 4=Neutral, 30=Sea Surface, Entity 140103=Passenger
  'CIVILIAN_PASSENGER':   '10043000001401030000',

  // Neutral — generic civilian vessel
  // 4=Neutral, 30=Sea Surface, Entity 140000=Civilian
  'CIVILIAN_BOAT':        '10043000001400000000',

  // Friend — RMP Marine Police boat
  // 3=Friend, 30=Sea Surface, Entity 120402=Patrol Boat
  'RMP_PATROL_CAR':       '10033000001204020000',
  // NOTE: RMP_PATROL_CAR is mislabeled in the backend — it's
  // mapped to Domain.MARITIME in the Python loader. It represents
  // RMP Marine Police vessels, NOT patrol cars. The name should
  // eventually be fixed to RMP_MARINE_PATROL.

  // ===== AIR (Symbol Set 01 = Air) =====

  // Friend — RMAF fighter aircraft
  // 3=Friend, 01=Air, Entity 110102=Fighter
  'RMAF_FIGHTER':         '10030100001101020000',

  // Friend — RMAF helicopter (EC725/Blackhawk)
  // 3=Friend, 01=Air, Entity 110200=Rotary Wing
  'RMAF_HELICOPTER':      '10030100001102000000',

  // Friend — RMAF transport/MPA
  // 3=Friend, 01=Air, Entity 110106=Cargo/Transport
  'RMAF_TRANSPORT':       '10030100001101060000',

  // Friend — RMP helicopter
  // 3=Friend, 01=Air, Entity 110203=Utility Helicopter
  'RMP_HELICOPTER':       '10030100001102030000',

  // Neutral — commercial airline
  // 4=Neutral, 01=Air, Entity 120000=Civilian Air
  'CIVILIAN_COMMERCIAL':  '10040100001200000000',

  // Neutral — light aircraft
  // 4=Neutral, 01=Air, Entity 120100=Civilian Fixed Wing
  'CIVILIAN_LIGHT':       '10040100001201000000',

  // ===== GROUND UNITS (Symbol Set 10 = Land Unit) =====

  // Friend — RMP tactical team (GOF)
  // 3=Friend, 10=Land Unit, Entity 121100=Special Operations Forces
  'RMP_TACTICAL_TEAM':    '10031000001211000000',

  // Friend — Military infantry squad
  // 3=Friend, 10=Land Unit, Entity 120100=Infantry
  'MIL_INFANTRY_SQUAD':   '10031000001201000000',

  // Friend — CI officer / immigration team
  // 3=Friend, 10=Land Unit, Entity 140000=Law Enforcement
  'CI_OFFICER':           '10031000001400000000',
  'CI_IMMIGRATION_TEAM':  '10031000001400000000',

  // Friend — RMP officer
  // 3=Friend, 10=Land Unit, Entity 140000=Law Enforcement
  'RMP_OFFICER':          '10031000001400000000',

  // Hostile — armed personnel
  // 6=Hostile, 10=Land Unit, Entity 120100=Infantry
  'HOSTILE_PERSONNEL':    '10061000001201000000',

  // Neutral — civilian person/tourist
  // 4=Neutral, 10=Land Unit, Entity 110000=Civilian
  'CIVILIAN_TOURIST':     '10041000001100000000',

  // ===== GROUND EQUIPMENT (Symbol Set 15 = Land Equipment) =====

  // Friend — APC
  // 3=Friend, 15=Land Equipment, Entity 120101=APC
  'MIL_APC':              '10031500001201010000',

  // Friend — Military vehicle
  // 3=Friend, 15=Land Equipment, Entity 120200=Wheeled Vehicle
  'MIL_VEHICLE':          '10031500001202000000',
},
```

### IMPORTANT: Verify Each Symbol Visually

The entity codes (positions 11-16) above are my best interpretation of the
2525D standard. Some may not render the expected icon in milsymbol 3.x.

**Claude Code MUST verify each SIDC by generating a test:**

```javascript
// Quick test — run in browser console or create a test page
import ms from 'milsymbol';

const testCodes = {
  'MMEA Patrol':    '10033000001204020000',
  'MIL Naval':      '10033000001201030000',
  'Suspect Vessel': '10053000001400000000',
  'Cargo':          '10043000001401010000',
  'Fishing':        '10043000001402000000',
  'RMAF Fighter':   '10030100001101020000',
  'RMAF Heli':      '10030100001102000000',
  'RMAF Transport': '10030100001101060000',
  'RMP Tactical':   '10031000001211000000',
  'Infantry':       '10031000001201000000',
  'CI Officer':     '10031000001400000000',
  'APC':            '10031500001201010000',
};

for (const [name, sidc] of Object.entries(testCodes)) {
  try {
    const sym = new ms.Symbol(sidc, { size: 50 });
    console.log(`✓ ${name}: ${sidc} → renders OK`);
    // Optionally: document.body.appendChild(sym.asDOM());
  } catch (e) {
    console.error(`✗ ${name}: ${sidc} → FAILED: ${e.message}`);
  }
}
```

**If any code doesn't render a recognizable symbol**, try simplifying the
entity code. The "generic" entity for each symbol set uses `110000` for
positions 11-16, which always renders the basic frame shape with a generic
military icon inside. For example:

- Generic friend air: `10030100001100000000`
- Generic friend sea: `10033000001100000000`
- Generic friend land: `10031000001100000000`

Using generic codes is perfectly acceptable for the demo — the frame shape
and color (friend=blue rectangle, hostile=red diamond, neutral=green square)
is what senior military officials recognize instantly. The specific icon
inside the frame is secondary.

### Expected Visual Result

After fixing the SIDCs:

- **MMEA/RMN/RMP maritime:** Blue rectangle frame with ship icon inside
- **RMAF aircraft:** Blue rectangle frame with aircraft icon inside
- **RMAF helicopter:** Blue rectangle frame with rotary wing icon inside
- **RMP/MIL ground:** Blue rectangle frame with ground unit icon
- **Civilian vessels:** Green square frame with ship icon
- **Suspect vessels:** Yellow diamond frame
- **Hostile speedboats:** Red diamond frame

---

## Issue 2: Naval Vessels Spawning on Land

Several base positions in the scenario YAML files use town-center coordinates
rather than harbor/port coordinates. This puts ships on land.

### Positions to Fix

**In `config/scenarios/sulu_sea_fishing_intercept.yaml`:**

| Entity | Current Position | Problem | Fix |
|---|---|---|---|
| MMEA-PV-101 | 5.84, 118.07 | Sandakan town center — ON LAND | 5.84, 118.12 |
| RMN-FIC-101 | 5.84, 118.10 | MAWILLA 2 — slightly inland | 5.84, 118.12 |
| RMP-MP-101 | 4.48, 118.61 | Semporna — on land | 4.48, 118.62 |
| RMP-MP-102 | 5.84, 118.07 | Sandakan — on land | 5.84, 118.12 |
| CI-TEAM-101 | 5.84, 118.07 | Sandakan — on land | 5.84, 118.12 |
| CI-IMMI-101 | 5.84, 118.07 | Sandakan — on land | 5.84, 118.12 |

**In `config/scenarios/semporna_kfr_response.yaml`:**

| Entity | Current Position | Problem | Fix |
|---|---|---|---|
| RMP-MP-201 | 4.48, 118.61 | Semporna town | 4.48, 118.62 |
| RMP-MP-202 | 4.48, 118.62 | OK — barely |  |
| RMN-FIC-201 | 4.48, 118.61 | Semporna — on land | 4.48, 118.63 |
| RMN-FIC-202 | 5.84, 118.10 | MAWILLA 2 | 5.84, 118.12 |
| RMN-PV-201 | 5.03, 118.33 | Lahad Datu — check | 5.03, 118.35 |
| MMEA-PV-201 | 4.48, 118.61 | Semporna | 4.48, 118.63 |

**In `config/scenarios/demo_combined.yaml`:** Apply the same fixes.

### Corrected Base Coordinates (Maritime)

These are harbor/anchorage positions just offshore:

```
Sandakan Harbor:    5.84°N, 118.12°E   (Sandakan Bay, near MAWILLA 2)
Semporna Jetty:     4.48°N, 118.63°E   (Semporna Strait, near RMN detachment)
Lahad Datu Port:    5.03°N, 118.35°E   (Lahad Datu Bay)
Tawau Port:         4.25°N, 117.90°E   (Tawau Bay)
Kudat Harbor:       6.88°N, 116.85°E   (Kudat Bay)
```

### Ground/Personnel Entities Stay Where They Are

Only move entities that are `Domain.MARITIME` (ships, boats). Personnel and
ground vehicles at town-center positions are fine — police stations, army
camps, and CI checkpoints ARE on land.

### How to Fix

For each scenario YAML, find every entity with a maritime type
(MMEA_PATROL, MMEA_FAST_INTERCEPT, MIL_NAVAL, RMP_PATROL_CAR, SUSPECT_VESSEL)
and adjust their `initial_position` to the corrected harbor coordinates above.

Also check that all waypoints for maritime entities are over water, not
cutting across land.

---

## Issue 3: Python Backend SIDC Codes

The Python backend (`simulator/scenario/loader.py`) also has short-form SIDC
codes in `ENTITY_TYPES` that are sent via WebSocket. These are the `"SHSP------"`
style codes that were causing the original rendering failure.

Since we already fixed `entity-manager.js` to ignore `entity.sidc` and use
`config.sidcMap[entity.entity_type]` instead, these backend codes don't affect
rendering. But they should still be cleaned up for consistency and for any
future TAK/CoT usage.

### RMP_PATROL_CAR Domain Bug

In `simulator/scenario/loader.py` line 78, `RMP_PATROL_CAR` is mapped to
`Domain.MARITIME`. This is actually correct for the current scenarios — it
represents RMP Marine Police vessels, not land patrol cars. But the name is
misleading. Consider adding a comment explaining this, or renaming to
`RMP_MARINE_PATROL` if Claude Code has time.

---

## Summary — What Claude Code Should Do

1. **Replace the entire `sidcMap`** in `cop/src/config.js` with the corrected
   version above
2. **Verify each SIDC** renders correctly in milsymbol by creating a quick
   test (generate all symbols, check they look right)
3. **If any entity code doesn't render well**, fall back to the generic code
   for that symbol set (e.g., `110000` for positions 11-16)
4. **Fix maritime entity positions** in all three scenario YAML files
   (fishing, KFR, combined) using the corrected harbor coordinates
5. **Rebuild both containers** (simulator for YAML changes, COP for config):
   ```bash
   docker-compose down --timeout 5
   docker-compose build
   docker-compose up -d
   ```
