# Entity Declutter / Spoke Strategy

## The Problem

Multiple entities share the same base position (e.g., 5 ships docked at
Sandakan, 3 helicopters at Labuan FOB). When zoomed in, they stack on top
of each other and become unreadable. When entities start moving (scenario
events), they separate naturally and no longer need decluttering.

## The Solution: Pixel-Distance Declutter with Ring Offset

Don't modify entity positions in the data model. Instead, apply a **display
offset** purely in the CesiumJS rendering layer. This keeps the simulation
data clean and only affects visual placement.

### Algorithm

```
Every 2 seconds (or on camera move):
  1. Project all entity positions to screen coordinates (Cartesian3 → pixel)
  2. Find groups of entities within OVERLAP_THRESHOLD_PX pixels of each other
  3. For each group of N > 1 entities:
     a. Pick the centroid as the anchor point
     b. Arrange N entities evenly around a circle of radius SPREAD_RADIUS_PX
     c. Convert pixel offsets back to Cartesian3 positions
     d. Apply as billboard pixelOffset (NOT position change)
     e. Optionally draw a thin line from offset position to true position
  4. Entities NOT in any group: reset pixelOffset to (0, 0)
```

### Key Design Decisions

1. **Use `pixelOffset` NOT position modification** — This is crucial. Never
   change the entity's actual Cartesian3 position. Use Cesium's
   `billboard.pixelOffset` property which shifts the icon on screen without
   changing its geographic location. This means trails, click targets, and
   the data model all stay correct.

2. **Pixel-space grouping, not geo-space** — Group entities that overlap ON
   SCREEN, not by geographic distance. Two entities 10km apart might overlap
   when zoomed out but not when zoomed in. Screen-space grouping handles
   this automatically.

3. **Scale-aware radius** — The spread radius should be constant in pixels
   (e.g., 60px), which means it automatically scales correctly at any zoom.

4. **Skip moving entities** — If an entity's speed > 1 knot, don't include
   it in declutter groups. It's moving and will separate naturally.

5. **No spoke lines** — They create visual clutter (as seen in the current
   screenshot). The pixelOffset approach keeps icons close enough to their
   true position that spoke lines aren't needed. If you must show the
   relationship, use a very subtle (1px, 20% alpha) line.

### Implementation

Replace the current clustering/spoking logic in `entity-manager.js` with:

```javascript
// === DECLUTTER CONFIG ===
const OVERLAP_THRESHOLD_PX = 30;  // Entities closer than this (in pixels) get spread
const SPREAD_RADIUS_PX = 50;      // How far to push them apart (in pixels)
const DECLUTTER_INTERVAL_MS = 1000; // How often to recalculate
const MIN_SPEED_TO_SKIP = 1.0;     // Don't declutter moving entities (knots)

// === DECLUTTER STATE ===
const declutterOffsets = new Map(); // entity_id -> { x, y } pixel offset

function declutterEntities() {
  const scene = viewer.scene;
  const screenPositions = [];

  // Step 1: Project all entities to screen space
  entities.forEach((entry, id) => {
    if (!entry.visible) return;

    // Skip moving entities — they'll separate naturally
    const speed = entry.data.speed_knots || 0;
    if (speed > MIN_SPEED_TO_SKIP) {
      // Reset any existing offset
      if (declutterOffsets.has(id)) {
        entry.cesiumEntity.billboard.pixelOffset = new Cesium.Cartesian2(0, 0);
        declutterOffsets.delete(id);
      }
      return;
    }

    const pos = entry.data.position;
    if (!pos) return;

    const cartesian = Cesium.Cartesian3.fromDegrees(
      pos.longitude, pos.latitude, pos.altitude_m || 0
    );
    const screenPos = Cesium.SceneTransforms.worldToWindowCoordinates(scene, cartesian);

    if (screenPos) {
      screenPositions.push({ id, screenPos, entry });
    }
  });

  // Step 2: Find overlapping groups using simple spatial hashing
  const groups = findOverlapGroups(screenPositions, OVERLAP_THRESHOLD_PX);

  // Step 3: Reset offsets for ungrouped entities
  const groupedIds = new Set();
  groups.forEach(group => group.forEach(item => groupedIds.add(item.id)));

  declutterOffsets.forEach((_, id) => {
    if (!groupedIds.has(id)) {
      const entry = entities.get(id);
      if (entry) {
        entry.cesiumEntity.billboard.pixelOffset = new Cesium.Cartesian2(0, 0);
      }
      declutterOffsets.delete(id);
    }
  });

  // Step 4: Apply ring offsets to grouped entities
  groups.forEach(group => {
    if (group.length <= 1) return;

    const n = group.length;
    for (let i = 0; i < n; i++) {
      const angle = (2 * Math.PI * i) / n - Math.PI / 2; // Start from top
      const offsetX = Math.cos(angle) * SPREAD_RADIUS_PX;
      const offsetY = Math.sin(angle) * SPREAD_RADIUS_PX;

      const item = group[i];
      const entry = entities.get(item.id);
      if (entry && entry.cesiumEntity.billboard) {
        entry.cesiumEntity.billboard.pixelOffset = new Cesium.Cartesian2(offsetX, offsetY);
        declutterOffsets.set(item.id, { x: offsetX, y: offsetY });
      }
    }
  });
}

function findOverlapGroups(items, threshold) {
  // Union-find / simple greedy clustering in screen space
  const visited = new Set();
  const groups = [];

  for (let i = 0; i < items.length; i++) {
    if (visited.has(i)) continue;

    const group = [items[i]];
    visited.add(i);

    for (let j = i + 1; j < items.length; j++) {
      if (visited.has(j)) continue;

      // Check distance to ANY member of the group (not just first)
      const closeToGroup = group.some(member => {
        const dx = member.screenPos.x - items[j].screenPos.x;
        const dy = member.screenPos.y - items[j].screenPos.y;
        return Math.sqrt(dx * dx + dy * dy) < threshold;
      });

      if (closeToGroup) {
        group.push(items[j]);
        visited.add(j);
      }
    }

    if (group.length > 1) {
      groups.push(group);
    }
  }

  return groups;
}

// Run declutter periodically
setInterval(declutterEntities, DECLUTTER_INTERVAL_MS);

// Also run on camera move end
viewer.camera.moveEnd.addEventListener(declutterEntities);
```

### Important Notes for Claude Code

1. **Remove ALL existing clustering and spoking code** — the numbered circle
   clusters, the spoke lines, the `updateClustering` function, `buildClusters`,
   `clearClusters`, `clusterEntities` array. Start clean.

2. **The `pixelOffset` approach is standard** — This is how professional GIS
   tools handle co-located symbols. Cesium supports it natively. No hacks.

3. **Don't create extra Cesium entities for spoke lines** — The previous
   approach created additional polyline entities for each spoke, which is
   expensive and creates the visual mess in the screenshot. pixelOffset
   avoids this entirely.

4. **Billboard scale at group edges** — For groups of 6+ entities, consider
   scaling down billboards slightly (0.8x) to reduce overlap in the ring.

5. **Label handling** — When entities are decluttered, their labels should
   follow (they're attached to the same Cesium entity, so pixelOffset
   affects both billboard and label). But labels may overlap in a tight ring.
   Consider hiding labels when an entity is in a declutter group and only
   showing the label of the currently hovered/selected entity.

6. **Performance** — The screen-space projection (`worldToWindowCoordinates`)
   is cheap for 51 entities. For 150+ entities, you could skip entities that
   are off-screen by checking if screenPos is within viewport bounds.

7. **Transition when entities start moving** — When a scenario event causes
   an entity to start moving (speed goes > 1 knot), the next declutter cycle
   will automatically exclude it and reset its offset. This creates a natural
   "departure" visual as the entity separates from its base group.

### What This Looks Like

**Zoomed out (strategic):** All entities visible as individual icons. Co-located
ones form neat rings around their base positions. Clean and readable.

**Zoomed in (tactical):** Rings get tighter (same pixel radius, but covers
less geographic area). Individual entities clearly distinguishable.

**During scenario action:** Moving entities separate from their base rings
naturally. The ring shrinks as entities depart. Eventually only idle/standby
entities remain in rings.

### Tooltip Positioning

The current tooltip appears directly under the mouse cursor, which covers the
icon and makes it hard to click. Fix the tooltip offset in `main.js`:

**Current (bad):**
```javascript
tooltip.style.left = `${movement.endPosition.x + 15}px`;
tooltip.style.top = `${movement.endPosition.y - 10}px`;
```

**Fixed:**
```javascript
// Position tooltip above and to the right of the cursor,
// far enough away to never overlap the icon
const tooltipWidth = tooltip.offsetWidth || 200;
const tooltipHeight = tooltip.offsetHeight || 80;
const viewportWidth = window.innerWidth;

// Default: above-right of cursor
let left = movement.endPosition.x + 25;
let top = movement.endPosition.y - tooltipHeight - 20;

// If tooltip would go off the right edge, flip to left side
if (left + tooltipWidth > viewportWidth) {
  left = movement.endPosition.x - tooltipWidth - 25;
}

// If tooltip would go above the viewport, put it below the cursor instead
if (top < 0) {
  top = movement.endPosition.y + 30;
}

tooltip.style.left = `${left}px`;
tooltip.style.top = `${top}px`;
```

**Key rules:**
- Tooltip should appear **above-right** of the icon, not under the cursor
- Minimum 20px gap between cursor and tooltip edge
- Flip to left side if near the right viewport edge
- Flip below if near the top of the viewport
- The tooltip must NEVER overlap the icon it describes — the user needs to
  be able to click the icon without the tooltip intercepting the click
- Add `pointer-events: none` to the tooltip CSS so it never captures clicks
  even if positioning is slightly off:

```css
#tooltip {
  pointer-events: none;  /* Critical — never block clicks */
}
```

### Test Cases

1. Load the combined scenario. Verify Sandakan base entities form a neat
   ring (multiple ships + helicopter + police units all co-located).

2. Run at 5x speed. When MMEA patrol vessel starts moving, verify it smoothly
   leaves the ring (offset resets to 0,0).

3. Zoom all the way out — entities should still be individually visible
   (no numbered cluster badges).

4. Zoom all the way in to a single base — ring should be tight and readable.

5. Click an entity in a ring — detail panel should show correct position
   (the TRUE position, not the offset position).

6. Hover over entities in a ring — tooltip should work for each individual
   entity.
