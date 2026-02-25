# SIDC & Symbol Fixes for Claude Code

All codes below verified `validIcon === true` with milsymbol 3.0.3.
milsymbol 3.x implements 2525E, NOT 2525D — some 2525D subtype codes are invalid and render as upside-down `?`.

---

## 1. Replace `sidcMap` in `cop/src/config.js`

```js
sidcMap: {
  // ===== MARITIME (Symbol Set 30) =====
  'MMEA_PATROL':          '10033000001204020000',  // Patrol Coastal, Station Ship
  'MMEA_FAST_INTERCEPT':  '10033000001204010000',  // Patrol Coastal, Patrol Craft
  'MIL_NAVAL':            '10033000001201000000',  // Combatant Line generic ← WAS 1201030000 (INVALID corvette subtype)
  'MIL_NAVAL_FIC':        '10033000001204010000',  // NEW — Patrol Coastal (for G2000 Fast Interceptor Craft)
  'SUSPECT_VESSEL':       '10053000001400000000',  // Suspect, Non-Military
  'HOSTILE_VESSEL':       '10063000001400000000',  // Hostile, Non-Military
  'CIVILIAN_CARGO':       '10043000001401010000',  // Neutral, Merchant Cargo
  'CIVILIAN_FISHING':     '10043000001402000000',  // Neutral, Fishing
  'CIVILIAN_TANKER':      '10043000001401020000',  // Neutral, Merchant Tanker
  'CIVILIAN_PASSENGER':   '10043000001401030000',  // Neutral, Merchant Passenger
  'CIVILIAN_BOAT':        '10043000001400000000',  // Neutral, Non-Military generic
  'RMP_PATROL_CAR':       '10033000001204020000',  // Patrol Coastal (RMP Marine Police)

  // ===== AIR (Symbol Set 01) =====
  'RMAF_FIGHTER':         '10030100001101020000',  // Fixed Wing, Fighter/Bomber
  'RMAF_HELICOPTER':      '10030100001102000000',  // Rotary Wing
  'RMAF_TRANSPORT':       '10030100001101060000',  // Fixed Wing, C2/Transport
  'RMAF_MPA':             '10030100001101040000',  // NEW — Fixed Wing, Patrol (for Beechcraft MPA)
  'RMP_HELICOPTER':       '10030100001102000000',  // Rotary Wing ← WAS 1102030000 (INVALID utility subtype)
  'CIVILIAN_COMMERCIAL':  '10040100001200000000',  // Neutral, Civilian generic
  'CIVILIAN_LIGHT':       '10040100001201000000',  // Neutral, Civilian Fixed Wing

  // ===== GROUND UNITS (Symbol Set 10) =====
  'RMP_TACTICAL_TEAM':    '10031000001211000000',  // SOF
  'MIL_INFANTRY_SQUAD':   '10031000001201000000',  // Infantry
  'RMP_OFFICER':          '10031000001400000000',  // Law Enforcement
  'HOSTILE_PERSONNEL':    '10061000001201000000',  // Hostile Infantry
  'CIVILIAN_TOURIST':     '10041000001100000000',  // Neutral Civilian

  // ===== GROUND EQUIPMENT (Symbol Set 15) =====
  'MIL_APC':              '10031500001201010000',  // APC
  'MIL_VEHICLE':          '10031500001201000000',  // Armored Vehicle generic
  'CI_OFFICER':           '10031500001703000000',  // LE Customs Service ← WAS Land Unit 1400 (generic LE)
  'CI_IMMIGRATION_TEAM':  '10031500001703000000',  // LE Customs Service ← WAS Land Unit 1400 (generic LE)
},
```

## 2. Update scenario YAMLs (`demo_combined.yaml`, `sulu_sea_fishing_intercept.yaml`, `semporna_kfr_response.yaml`)

**G2000 Fast Interceptor Craft** — change `type: MIL_NAVAL` → `type: MIL_NAVAL_FIC`:
- `RMN-FIC-101` (KD G2000 Alpha)
- `RMN-FIC-201` (KD G2000 Bravo)
- `RMN-FIC-202` (KD G2000 Charlie)

**Beechcraft MPA** — change `type: RMAF_TRANSPORT` → `type: RMAF_MPA`:
- `RMAF-MPA-101` (TUDM MPA Beechcraft)

## 3. Fix `entity-manager.js` — enable type amplifiers

In `getSymbolImage()`, change:

```js
// OLD (broken — no type labels, size too small)
const symbol = new ms.Symbol(sidc, {
  size: 24,
  frame: true,
  fill: true,
  strokeWidth: 1,
  infoFields: false
});
```

To:

```js
const shortType = getShortType(entity);
const cacheKey = `${sidc}_${shortType}`;
if (symbolCache.has(cacheKey)) return symbolCache.get(cacheKey);

const symbol = new ms.Symbol(sidc, {
  size: 35,
  frame: true,
  fill: true,
  strokeWidth: 1.5,
  infoFields: true,
  type: shortType,
});
```

Add helper function:

```js
function getShortType(entity) {
  if (entity.metadata?.type_code) return entity.metadata.type_code;
  const typeMap = {
    'MIL_NAVAL':           'NAV',
    'MIL_NAVAL_FIC':       'FIC',
    'MMEA_PATROL':         'PB',
    'MMEA_FAST_INTERCEPT': 'FIC',
    'RMAF_FIGHTER':        'FTR',
    'RMAF_HELICOPTER':     'RW',
    'RMAF_TRANSPORT':      'C',
    'RMAF_MPA':            'MPA',
    'RMP_HELICOPTER':      'RW',
    'RMP_PATROL_CAR':      'MP',
    'RMP_TACTICAL_TEAM':   'SOF',
    'MIL_INFANTRY_SQUAD':  'INF',
    'CI_OFFICER':          'CI',
    'CI_IMMIGRATION_TEAM': 'IMM',
    'CIVILIAN_FISHING':    'FV',
    'CIVILIAN_CARGO':      'CGO',
    'CIVILIAN_TANKER':     'TKR',
    'CIVILIAN_COMMERCIAL': 'CIV',
    'SUSPECT_VESSEL':      '?',
    'HOSTILE_VESSEL':      'HOS',
    'HOSTILE_PERSONNEL':   'HOS',
    'MIL_APC':             'APC',
  };
  return typeMap[entity.entity_type] || '';
}
```

## 4. Fix `entity-panel.js` — [object Object] bug

In `buildMetadataSection()`, filter out non-primitive values:

```js
const entries = Object.entries(meta).filter(([k, v]) =>
  !['background', 'ais_active', 'vessel_type_code'].includes(k) &&
  typeof v !== 'object'
);
```

## 5. Fix trail "spokes" for decluttered entities

In `entity-manager.js` `declutterEntities()`, when applying ring offsets:

```js
// Inside the ring offset loop — add this line:
entry.cesiumTrail.show = false;
```

And in the ungrouped reset section:

```js
// Add this line when resetting ungrouped entities:
entry.cesiumTrail.show = true;
```

Also add minimum-distance threshold in `updateExisting()` before pushing trail points:

```js
const lastPoint = trail[trail.length - 1];
const dist = Math.sqrt(Math.pow(lat - lastPoint.lat, 2) + Math.pow(lon - lastPoint.lon, 2));
if (dist > 0.0001) {  // ~11 meters — skip if entity hasn't moved
  trail.push({ lat, lon, alt });
  if (trail.length > MAX_TRAIL_POINTS) trail.shift();
}
```

## Summary of broken codes that caused upside-down `?`

| Entity Type | Old Entity Code | Why Broken | Fixed Entity Code |
|---|---|---|---|
| MIL_NAVAL | `120103` (corvette) | Subtype `03` not in milsymbol 3.x/2525E | `120100` (Combatant Line generic) |
| RMP_HELICOPTER | `110203` (utility heli) | Subtype `03` not in milsymbol 3.x/2525E | `110200` (Rotary Wing generic) |
| CI_OFFICER | `140000` in Symbol Set 10 | Worked but wrong symbol type | `170300` in Symbol Set 15 (Customs Service) |
