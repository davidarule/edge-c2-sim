# Replace milsymbol with JMSML SVG Symbol Renderer

## Context

milsymbol 3.0.3 implements MIL-STD-2525**E**. Our SIDCs are 2525**D**. Many entity codes
don't exist in milsymbol and render as upside-down `?` or fallback "MIL" text. The
milsymbol `type` amplifier also only places text OUTSIDE the frame as a small label — 
it does NOT put text inside the symbol like the standard requires.

A working JMSML-based symbol builder already exists at `~/joint-military-symbology-xml`.
It uses the official DISA SVG files from the Esri JMSML repo to composite correct
MIL-STD-2525D symbols by layering frame + icon + modifiers. **This works perfectly.**

## Task

Port the JMSML SVG symbol rendering from `~/joint-military-symbology-xml` into the 
COP at `~/edge_c2_sim/cop/`. Remove the milsymbol dependency entirely.

---

## Step 1: Study the existing symbol builder

Look at `~/joint-military-symbology-xml` — you (Claude Code) already built this.
Understand how it:

1. Parses a 20-digit SIDC into components
2. Selects the correct **frame** SVG
3. Selects the correct **entity icon** SVG  
4. Selects **modifier 1** and **modifier 2** SVGs (if positions 17-20 are non-zero)
5. Composites them into a single layered SVG
6. Renders the result

The compositing logic is the critical piece. Copy it.

---

## Step 2: Understand the DISA SVG file naming

The SVGs live in `~/joint-military-symbology-xml/svg/MIL_STD_2525D_Symbols/`

### Frames
**Path:** `Frames/{context}_{identity}_{symbolSet}_{status}.svg`

Uses SIDC positions 3, 4, 5-6, and 7, with underscores between.

Examples:
- `0_3_01_0.svg` = Reality, Friend, Air, Present (cyan half-oval)
- `0_3_30_0.svg` = Reality, Friend, Sea Surface, Present (cyan semicircle)
- `0_4_30_0.svg` = Reality, Neutral, Sea Surface, Present (green square)
- `0_5_30_0.svg` = Reality, Suspect, Sea Surface, Present (yellow diamond)
- `0_6_30_0.svg` = Reality, Hostile, Sea Surface, Present (red diamond)
- `0_3_10_0.svg` = Reality, Friend, Land Unit, Present (cyan rectangle)
- `0_3_15_0.svg` = Reality, Friend, Land Equipment, Present (cyan rectangle)

### Entity Icons
**Path:** `Appendices/{FolderName}/{symbolSet}_{entity6}.svg`

Uses SIDC positions 5-6 (symbol set) and 11-16 (entity code).

Symbol Set to folder mapping:
- `01` → `Air/`
- `10` → `Land/`  (for both units and equipment)
- `15` → `Land/`  (ground equipment shares Land folder)
- `30` → `SeaSurface/`

Examples:
- `Air/01_110131.svg` = Fixed Wing, Passenger → renders "PX" text
- `Air/01_110104.svg` = Fixed Wing, Patrol → renders patrol icon
- `Air/01_110200.svg` = Rotary Wing → renders helicopter icon
- `SeaSurface/30_120103.svg` = Combatant, Line, Corvette
- `SeaSurface/30_140200.svg` = Non-Military, Fishing
- `Land/10_121100.svg` = SOF
- `Land/15_170300.svg` = LE Customs Service

**Full-frame icons** (that touch the frame border) have suffix `_0`, `_1`, `_2`, `_3`:
- `_0` = Unknown frame shape
- `_1` = Friend frame shape  
- `_2` = Neutral frame shape
- `_3` = Hostile frame shape

Check if any of our icons are full-frame. If so, use the suffix matching the identity.

### Modifiers
**Mod1 path:** `Appendices/{FolderName}/mod1/{symbolSet}_{mod2digits}1.svg`
**Mod2 path:** `Appendices/{FolderName}/mod2/{symbolSet}_{mod2digits}2.svg`

Uses SIDC positions 17-18 (mod1) and 19-20 (mod2). The trailing `1` or `2` in filename
indicates which modifier layer it is.

Example for RMAF_TRANSPORT SIDC `10030100001101310303`:
- Mod1: `Air/mod1/01_031.svg` (renders "C" = Cargo capability)
- Mod2: `Air/mod2/01_032.svg` (renders "L" = Large)

---

## Step 3: Create `cop/src/symbol-renderer.js`

Create a new module that replaces milsymbol entirely. It must:

1. **Accept a 20-digit SIDC string** and size option
2. **Parse SIDC** into context, identity, symbolSet, status, entity, mod1, mod2
3. **Load SVG files** (frame + icon + optional modifiers)
4. **Composite them** into a single SVG by layering (frame is base, icon centered on top, modifiers on top of that)
5. **Return a data URL** (`data:image/svg+xml;base64,...`) — same interface as milsymbol's `toDataURL()`
6. **Cache results** by SIDC string

### SVG Compositing

The DISA SVGs all use a standard coordinate space (approximately 200x200 viewBox). To composite:

```js
function compositeSymbol(frameSvg, iconSvg, mod1Svg, mod2Svg, size) {
  // All DISA SVGs share the same coordinate space
  // Layer them: frame first (back), then icon (middle), then modifiers (front)
  // 
  // Extract the inner content of each SVG (everything inside <svg>...</svg>)
  // Combine into a single SVG with shared viewBox
  //
  // Pseudo-code:
  // 1. Parse frame SVG to get viewBox dimensions
  // 2. Create new SVG element with that viewBox
  // 3. Insert frame content as first group
  // 4. Insert icon content as second group (centered)
  // 5. Insert mod1/mod2 content as third/fourth groups
  // 6. Serialize to string, convert to data URL
}
```

**IMPORTANT**: Look at how you already do this in `~/joint-military-symbology-xml`. 
Don't reinvent it — copy the working compositing code.

### Bundling SVG files

Two approaches — pick whichever the existing symbol builder uses:

**Option A: Bundle SVGs as static files**
Copy needed SVGs into `cop/public/svg/` and fetch them at runtime:
```js
const response = await fetch(`/svg/Frames/${frameName}.svg`);
const svgText = await response.text();
```

**Option B: Inline SVGs into a JS module at build time** (RECOMMENDED)
Create a build script that reads all needed SVGs and generates a JS file:
```js
// Generated file: svg-data.js
export const frames = {
  '0_3_01_0': '<svg>...</svg>',
  '0_3_30_0': '<svg>...</svg>',
  // ...
};
export const icons = {
  '01_110131': '<svg>...</svg>',
  '30_120103': '<svg>...</svg>',
  // ...
};
export const mod1s = { ... };
export const mod2s = { ... };
```
This avoids runtime fetching and works better with Vite bundling.

**OR Option C: Import SVGs directly with Vite's `?raw` suffix:**
```js
import frame_0_3_01_0 from '../assets/svg/Frames/0_3_01_0.svg?raw';
// etc.
```
This is the cleanest Vite approach — no build script needed.

---

## Step 4: Update entity-manager.js

In `cop/src/entity-manager.js`:

1. **Remove:** `import ms from 'milsymbol';`
2. **Add:** `import { renderSymbol } from './symbol-renderer.js';`
3. **Replace `getSymbolImage()`:**

```js
function getSymbolImage(entity) {
  const sidc = config.sidcMap[entity.entity_type] || config.defaultSidc;
  if (symbolCache.has(sidc)) return symbolCache.get(sidc);

  const url = renderSymbol(sidc, { size: 40 });
  symbolCache.set(sidc, url);
  return url;
}
```

4. **Remove the entire `shortTypeMap` object** and `getShortType()` function — no longer needed. The DISA SVGs contain the correct text/icons built-in.

5. **Remove milsymbol from `cop/package.json`:**
```bash
cd ~/edge_c2_sim/cop && npm uninstall milsymbol
```

---

## Step 5: Update SIDC codes in config.js

Now that we use DISA SVGs, we can use the CORRECT 2525D entity codes including
subtypes that milsymbol couldn't handle. Update `cop/src/config.js`:

```js
sidcMap: {
  // ===== MARITIME (Symbol Set 30) =====
  'MMEA_PATROL':          '10033000001204020000',  // Combatant, Patrol, Coastal, Station Ship
  'MMEA_FAST_INTERCEPT':  '10033000001204010000',  // Combatant, Patrol, Coastal, Patrol Craft
  'MIL_NAVAL':            '10033000001201030000',  // Combatant, Line, Corvette ← RESTORED
  'MIL_NAVAL_FIC':        '10033000001204010000',  // Patrol Coastal, Patrol Craft (G2000)
  'SUSPECT_VESSEL':       '10053000001400000000',  // Suspect, Non-Military
  'HOSTILE_VESSEL':       '10063000001400000000',  // Hostile, Non-Military
  'CIVILIAN_CARGO':       '10043000001401010000',  // Neutral, Merchant, Cargo
  'CIVILIAN_FISHING':     '10043000001402000000',  // Neutral, Fishing
  'CIVILIAN_TANKER':      '10043000001401020000',  // Neutral, Merchant, Tanker
  'CIVILIAN_PASSENGER':   '10043000001401030000',  // Neutral, Merchant, Passenger
  'CIVILIAN_BOAT':        '10043000001400000000',  // Neutral, Non-Military generic
  'RMP_PATROL_CAR':       '10033000001204020000',  // Patrol Coastal, Station Ship

  // ===== AIR (Symbol Set 01) =====
  'RMAF_FIGHTER':         '10030100001101020000',  // Fixed Wing, Fighter/Bomber
  'RMAF_HELICOPTER':      '10030100001102000000',  // Rotary Wing generic
  'RMAF_TRANSPORT':       '10030100001101310303',  // Fixed Wing, Passenger + C + L ← FROM SYMBOL BUILDER
  'RMAF_MPA':             '10030100001101040000',  // Fixed Wing, Patrol
  'RMP_HELICOPTER':       '10030100001102030000',  // Rotary Wing, Utility ← RESTORED
  'CIVILIAN_COMMERCIAL':  '10040100001200000000',  // Neutral, Civilian generic
  'CIVILIAN_LIGHT':       '10040100001201000000',  // Neutral, Civilian, Fixed Wing

  // ===== GROUND UNITS (Symbol Set 10) =====
  'RMP_TACTICAL_TEAM':    '10031000001211000000',  // SOF
  'MIL_INFANTRY_SQUAD':   '10031000001201000000',  // Infantry
  'RMP_OFFICER':          '10031000001400000000',  // Law Enforcement
  'HOSTILE_PERSONNEL':    '10061000001201000000',  // Hostile, Infantry
  'CIVILIAN_TOURIST':     '10041000001100000000',  // Neutral, Civilian

  // ===== GROUND EQUIPMENT (Symbol Set 15) =====
  'MIL_APC':              '10031500001201010000',  // APC
  'MIL_VEHICLE':          '10031500001202000000',  // Vehicle generic
  'CI_OFFICER':           '10031500001703000000',  // LE Customs Service
  'CI_IMMIGRATION_TEAM':  '10031500001703000000',  // LE Customs Service
},

defaultSidc: '10033000001100000000',  // Sea Surface, Military generic
```

Key changes from old milsymbol-compatible codes:
- `MIL_NAVAL`: `120100` → `120103` (Corvette subtype restored)
- `RMP_HELICOPTER`: `110200` → `110203` (Utility subtype restored)
- `RMAF_TRANSPORT`: `110106` → `110131` + mod1=03, mod2=03 (Passenger with C/L modifiers — matches symbol builder screenshot)

---

## Step 6: Identify ALL SVG files needed

### Frames (10 files):
```
Frames/0_3_01_0.svg    Friend, Air, Present
Frames/0_3_10_0.svg    Friend, Land Unit, Present
Frames/0_3_15_0.svg    Friend, Land Equipment, Present
Frames/0_3_30_0.svg    Friend, Sea Surface, Present
Frames/0_4_01_0.svg    Neutral, Air, Present
Frames/0_4_10_0.svg    Neutral, Land Unit, Present
Frames/0_4_30_0.svg    Neutral, Sea Surface, Present
Frames/0_5_30_0.svg    Suspect, Sea Surface, Present
Frames/0_6_10_0.svg    Hostile, Land Unit, Present
Frames/0_6_30_0.svg    Hostile, Sea Surface, Present
```

### Entity Icons (~20 unique files):
```
# Air (Appendices/Air/)
Air/01_110102.svg      Fixed Wing, Fighter/Bomber
Air/01_110104.svg      Fixed Wing, Patrol (MPA)
Air/01_110131.svg      Fixed Wing, Passenger (Transport → "PX")
Air/01_110200.svg      Rotary Wing generic (RMAF helicopters)
Air/01_110203.svg      Rotary Wing, Utility (RMP helicopter)
Air/01_120000.svg      Civilian generic
Air/01_120100.svg      Civilian, Fixed Wing

# Sea Surface (Appendices/SeaSurface/)
SeaSurface/30_110000.svg    Military generic (default fallback)
SeaSurface/30_120103.svg    Combatant, Line, Corvette (KD Keris)
SeaSurface/30_120401.svg    Patrol, Coastal, Patrol Craft
SeaSurface/30_120402.svg    Patrol, Coastal, Station Ship
SeaSurface/30_140000.svg    Non-Military generic (suspects, hostiles)
SeaSurface/30_140101.svg    Non-Military, Merchant, Cargo
SeaSurface/30_140102.svg    Non-Military, Merchant, Tanker
SeaSurface/30_140103.svg    Non-Military, Merchant, Passenger
SeaSurface/30_140200.svg    Non-Military, Fishing

# Land (Appendices/Land/)
Land/10_110000.svg     Civilian generic
Land/10_120100.svg     Infantry
Land/10_121100.svg     SOF
Land/10_140000.svg     Law Enforcement
Land/15_120100.svg     Armored Vehicle
Land/15_120101.svg     APC
Land/15_170300.svg     LE Customs Service
```

### Modifiers (2 files for RMAF_TRANSPORT):
```
Air/mod1/01_031.svg    Mod1 value 03 → "C"
Air/mod2/01_032.svg    Mod2 value 03 → "L"
```

**IMPORTANT:** Verify exact filenames by listing the actual directory contents.
Some files may use slightly different naming. `ls` the directories to confirm before
writing any code. The symbol set 15 (Land Equipment) icons may be in the `Land/`
folder with a `15_` prefix, or they may be in a separate folder.

---

## Step 7: Testing

After integration, verify these specific entities render correctly:

| Entity | Expected Appearance |
|--------|-------------------|
| KD Keris (`MIL_NAVAL`) | Cyan semicircle with corvette icon inside |
| TUDM MPA Beechcraft (`RMAF_MPA`) | Cyan half-oval with patrol aircraft icon, NOT "MIL" text |
| RMAF Transport (`RMAF_TRANSPORT`) | Cyan half-oval with "PX" + "C" (top) + "L" (bottom) |
| RMP Helicopter (`RMP_HELICOPTER`) | Cyan half-oval with utility helicopter icon |
| G2000 Alpha (`MIL_NAVAL_FIC`) | Cyan semicircle with patrol craft icon |
| KM Semporna (`MMEA_PATROL`) | Cyan semicircle with station ship icon |
| Customs Team (`CI_OFFICER`) | Cyan rectangle with customs badge |
| Unknown Trawler (`SUSPECT_VESSEL`) | Yellow diamond with generic ship |
| Nelayan 123 (`CIVILIAN_FISHING`) | Green square with fishing vessel |
| EC725 (`RMAF_HELICOPTER`) | Cyan half-oval with helicopter rotor icon |
| GOF Tactical (`RMP_TACTICAL_TEAM`) | Cyan rectangle with SOF icon |

Every symbol should look identical to what the symbol builder at
`~/joint-military-symbology-xml` produces for the same SIDC.

---

## Step 8: Docker rebuild

```bash
cd ~/edge_c2_sim
docker-compose down --timeout 5
docker-compose build cop
docker-compose up -d
```

Hard-refresh browser (Ctrl+Shift+R) to clear cached JS.

---

## Architecture Summary

```
BEFORE (broken):
  entity_type → sidcMap[type] → 20-digit SIDC → milsymbol 3.x (2525E only)
  → wrong icons / "MIL" fallback / upside-down ?

AFTER (correct):
  entity_type → sidcMap[type] → 20-digit SIDC → parse positions →
  → load DISA SVG (frame + icon + modifiers) → composite layers → data URL
  → correct 2525D symbol every time
```

The DISA SVGs are the authoritative 2525D source. They contain ALL the correct
icons, text, and symbology built into the SVG artwork itself. No runtime text
generation needed. No more fighting milsymbol's 2525E limitations.
