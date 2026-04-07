/**
 * JMSML SVG Symbol Renderer — composites MIL-STD-2525D symbols from official
 * DISA SVG files: Frame + Entity Icon + optional Modifier 1/2.
 *
 * All DISA SVGs share viewBox="0 0 612 792". Layers are stacked in a single
 * SVG element to produce a correct composite symbol.
 *
 * Rendering is synchronous (cache-first). Missing SVG layers are fetched in the
 * background on first use; when they arrive the `symbols-updated` CustomEvent
 * fires on `window` so listeners can refresh affected entities.
 */

// Caches: raw SVG text keyed by path, rendered data-URLs keyed by SIDC+size
const svgTextCache = new Map();
const symbolCache  = new Map();

// Deduplicate in-flight fetches so the same file isn't fetched twice concurrently
const pendingFetches = new Map();

// Symbol set → Appendices subfolder name
const SYMBOL_SET_FOLDER = {
  '01': 'Air',
  '02': 'Air',
  '05': 'Space',
  '10': 'Land',
  '15': 'Land',
  '20': 'Land',
  '25': 'ControlMeasures',
  '30': 'SeaSurface',
  '35': 'SeaSubsurface',
  '40': 'Activities',
  '45': 'METOC',
  '50': 'SigInt',
  '60': 'Cyberspace',
};

// Full-frame icons: these have _0/_1/_2/_3 suffixes for each affiliation shape.
const FULL_FRAME_CODES = new Set([
  '10120100', // Infantry
  '10121100', // SOF
]);

// Standard identity → full-frame suffix
//   _0 = Unknown, _1 = Friend, _2 = Neutral, _3 = Hostile
const IDENTITY_SUFFIX = {
  '0': '_0', '1': '_1', '2': '_1', '3': '_1',
  '4': '_2', '5': '_3', '6': '_3',
};

// ─── Fetch helpers ────────────────────────────────────────────────────────────

/**
 * Fetch an SVG file and store it in svgTextCache.
 * Deduplicates concurrent requests for the same path.
 * Returns the SVG text, or null on failure.
 */
async function fetchSvg(path) {
  if (svgTextCache.has(path)) return svgTextCache.get(path);
  if (pendingFetches.has(path)) return pendingFetches.get(path);

  const promise = fetch(path)
    .then(res => {
      if (!res.ok) return null;
      return res.text();
    })
    .then(text => {
      pendingFetches.delete(path);
      if (text) svgTextCache.set(path, text);
      return text || null;
    })
    .catch(() => {
      pendingFetches.delete(path);
      return null;
    });

  pendingFetches.set(path, promise);
  return promise;
}

// ─── Path resolution ──────────────────────────────────────────────────────────

function resolveFramePath(context, identity, symbolSet, status) {
  return `/svg/Frames/${context}_${identity}${symbolSet}_${status}.svg`;
}

function resolveIconPath(identity, symbolSet, entity6) {
  const folder = SYMBOL_SET_FOLDER[symbolSet] || 'Land';
  const code8  = `${symbolSet}${entity6}`;
  const suffix = IDENTITY_SUFFIX[identity] || '_1';

  // Full-frame icon — exact match
  if (FULL_FRAME_CODES.has(code8)) {
    const path = `/svg/Appendices/${folder}/${code8}${suffix}.svg`;
    if (svgTextCache.has(path)) return path;
  }

  // Full-frame icon — parent (subtype = 00)
  const parentCode = `${symbolSet}${entity6.slice(0, 4)}00`;
  if (FULL_FRAME_CODES.has(parentCode)) {
    const path = `/svg/Appendices/${folder}/${parentCode}${suffix}.svg`;
    if (svgTextCache.has(path)) return path;
  }

  // Standard icon — exact subtype
  const exact = `/svg/Appendices/${folder}/${code8}.svg`;
  if (svgTextCache.has(exact)) return exact;

  // Drop subtype (last 2 digits → 00)
  const noSubtype = `/svg/Appendices/${folder}/${symbolSet}${entity6.slice(0, 4)}00.svg`;
  if (svgTextCache.has(noSubtype)) return noSubtype;

  // Drop type + subtype (last 4 digits → 0000)
  const noType = `/svg/Appendices/${folder}/${symbolSet}${entity6.slice(0, 2)}0000.svg`;
  if (svgTextCache.has(noType)) return noType;

  // Return exact path even if not cached — fetchSvg will try it
  return exact;
}

function resolveModPath(symbolSet, modCode, modNum) {
  if (!modCode || modCode === '00') return null;
  const folder = SYMBOL_SET_FOLDER[symbolSet] || 'Land';
  const dir    = modNum === 1 ? 'mod1' : 'mod2';
  return `/svg/Appendices/${folder}/${dir}/${symbolSet}${modCode}${modNum}.svg`;
}

// ─── Compositing ──────────────────────────────────────────────────────────────

function extractSvgInner(svgText) {
  const open  = svgText.indexOf('>', svgText.indexOf('<svg'));
  const close = svgText.lastIndexOf('</svg>');
  if (open < 0 || close < 0) return '';
  return svgText.slice(open + 1, close);
}

function composite(frameSvg, iconSvg, mod1Svg, mod2Svg, size) {
  const layers = [];
  if (frameSvg) layers.push(`<g>${extractSvgInner(frameSvg)}</g>`);
  if (iconSvg)  layers.push(`<g>${extractSvgInner(iconSvg)}</g>`);
  if (mod1Svg)  layers.push(`<g>${extractSvgInner(mod1Svg)}</g>`);
  if (mod2Svg)  layers.push(`<g>${extractSvgInner(mod2Svg)}</g>`);

  if (layers.length === 0) return makeFallback(size);

  const height = Math.round(size * (792 / 612));
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 612 792" width="${size}" height="${height}">${layers.join('')}</svg>`;
  return 'data:image/svg+xml,' + encodeURIComponent(svg);
}

function makeFallback(size) {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" width="${size}" height="${size}">
    <circle cx="50" cy="50" r="40" fill="none" stroke="#888" stroke-width="3"/>
    <text x="50" y="58" text-anchor="middle" font-size="30" fill="#888">?</text>
  </svg>`;
  return 'data:image/svg+xml,' + encodeURIComponent(svg);
}

// ─── Background fetch + refresh ───────────────────────────────────────────────

/**
 * Fetch all missing layers for a SIDC in the background.
 * When any arrive, invalidate the symbol cache entry and fire `symbols-updated`
 * so the UI can refresh the affected entity/billboard.
 */
function backgroundFetch(sidc, size, framePath, iconPath, mod1Path, mod2Path) {
  const missing = [framePath, iconPath, mod1Path, mod2Path]
    .filter(p => p && !svgTextCache.has(p) && !pendingFetches.has(p));

  if (missing.length === 0) return;

  Promise.all(missing.map(fetchSvg)).then(results => {
    if (results.some(r => r != null)) {
      // Invalidate so next renderSymbol() call re-composites with real layers
      symbolCache.delete(`${sidc}_${size}`);
      window.dispatchEvent(new CustomEvent('symbols-updated', {
        detail: { sidc },
      }));
    }
  });
}

// ─── Public API ───────────────────────────────────────────────────────────────

/**
 * Warm up the symbol renderer.
 *
 * With 4,554 SVG files we can't preload everything. This function is kept for
 * API compatibility but is now a no-op — symbols are fetched on first use.
 */
export async function preloadSymbols() {
  // no-op: on-demand fetch handles this transparently
  console.log('[symbol-renderer] On-demand mode — symbols loaded on first use');
}

/**
 * Render a MIL-STD-2525D symbol from a 20-digit SIDC.
 *
 * Returns a data:image/svg+xml URL synchronously from cache.
 * If any SVG layer is not yet cached a background fetch is started; when the
 * fetch completes a `symbols-updated` event fires on `window`.
 *
 * @param {string} sidc  20-character SIDC string
 * @param {object} opts  { size: number } pixel width (default 40)
 * @returns {string}     data:image/svg+xml,... URL
 */
export function renderSymbol(sidc, opts = {}) {
  const size     = opts.size || 40;
  const cacheKey = `${sidc}_${size}`;
  if (symbolCache.has(cacheKey)) return symbolCache.get(cacheKey);

  // Parse SIDC (0-indexed)
  const context   = sidc[2];
  const identity  = sidc[3];
  const symbolSet = sidc.slice(4, 6);
  const status    = sidc[6];
  const entity6   = sidc.slice(10, 16);
  const mod1Code  = sidc.slice(16, 18);
  const mod2Code  = sidc.slice(18, 20);

  const framePath = resolveFramePath(context, identity, symbolSet, status);
  const iconPath  = resolveIconPath(identity, symbolSet, entity6);
  const mod1Path  = resolveModPath(symbolSet, mod1Code, 1);
  const mod2Path  = resolveModPath(symbolSet, mod2Code, 2);

  const frameSvg = svgTextCache.get(framePath) || null;
  const iconSvg  = iconPath ? (svgTextCache.get(iconPath) || null) : null;
  const mod1Svg  = mod1Path ? (svgTextCache.get(mod1Path) || null) : null;
  const mod2Svg  = mod2Path ? (svgTextCache.get(mod2Path) || null) : null;

  const url = composite(frameSvg, iconSvg, mod1Svg, mod2Svg, size);
  symbolCache.set(cacheKey, url);

  // Kick off background fetch for any missing layers
  backgroundFetch(sidc, size, framePath, iconPath, mod1Path, mod2Path);

  return url;
}

/**
 * Clear the rendered symbol cache (call after SIDC map changes).
 */
export function clearSymbolCache() {
  symbolCache.clear();
}
