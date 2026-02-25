/**
 * JMSML SVG Symbol Renderer — replaces milsymbol.
 *
 * Composites MIL-STD-2525D symbols from official DISA SVG files:
 *   Frame (affiliation shape) + Entity Icon + optional Modifier 1/2
 *
 * All DISA SVGs share viewBox="0 0 612 792". Layers are stacked in a
 * single SVG to produce a correct composite symbol.
 */

// Caches: raw SVG text keyed by path, and rendered data-URLs keyed by SIDC+size
const svgTextCache = new Map();
const symbolCache = new Map();

// Symbol set → appendix folder name
const SYMBOL_SET_FOLDER = {
  '01': 'Air',
  '02': 'Air',
  '05': 'Space',
  '10': 'Land',
  '15': 'Land',
  '20': 'Land',
  '30': 'SeaSurface',
  '35': 'SeaSubsurface',
};

// Full-frame icons: these have _0/_1/_2/_3 suffixes for each affiliation shape.
// Key = 8-digit base code (symbolSet + entity6), checked by stripping to 6-digit
// parent if subtype doesn't have a full-frame variant.
const FULL_FRAME_CODES = new Set([
  '10120100', // Infantry
  '10121100', // SOF
  // Add more as needed
]);

// Standard identity → full-frame suffix
//   _0 = Unknown frame, _1 = Friend, _2 = Neutral, _3 = Hostile
const IDENTITY_SUFFIX = {
  '0': '_0', '1': '_1', '2': '_1', '3': '_1',
  '4': '_2', '5': '_3', '6': '_3',
};

/**
 * Preload all SVG files the app will need. Call once at startup before
 * any renderSymbol() calls. Fetches from /svg/ (cop/public/svg/).
 */
export async function preloadSymbols() {
  const base = '/svg';

  // Discover which files we actually have by trying known paths.
  // Build list of URLs to fetch.
  const urls = [];

  // Frames
  const frameIds = [
    // Unknown (identity 0)
    '0_001_0', '0_010_0', '0_015_0', '0_030_0',
    // Assumed Friend (identity 1)
    '0_101_0', '0_110_0', '0_115_0', '0_130_0',
    // Friend (identity 2)
    '0_201_0', '0_210_0', '0_215_0', '0_230_0',
    // Friend (identity 3)
    '0_301_0', '0_310_0', '0_315_0', '0_330_0',
    // Neutral (identity 4)
    '0_401_0', '0_410_0', '0_430_0',
    // Suspect (identity 5)
    '0_530_0',
    // Hostile (identity 6)
    '0_610_0', '0_630_0',
  ];
  for (const id of frameIds) {
    urls.push(`${base}/Frames/${id}.svg`);
  }

  // Entity icons
  const iconFiles = {
    Air: [
      '01110102', '01110104', '01110131', '01110200',
      '01120000', '01120100',
    ],
    SeaSurface: [
      '30110000', '30120100', '30120200', '30120206',
      '30120401', '30120402', '30120500',
      '30140000', '30140101', '30140102', '30140103', '30140200', '30140300',
    ],
    Land: [
      '10110000', '10121800', '10140100',
      '10120100_0', '10120100_1', '10120100_2', '10120100_3',
      '10121100_0', '10121100_1', '10121100_2', '10121100_3',
      '15120100', '15120101', '15120200', '15170300',
    ],
  };
  for (const [folder, files] of Object.entries(iconFiles)) {
    for (const name of files) {
      urls.push(`${base}/Appendices/${folder}/${name}.svg`);
    }
  }

  // Modifiers
  urls.push(`${base}/Appendices/Air/mod1/01031.svg`);
  urls.push(`${base}/Appendices/Air/mod2/01032.svg`);

  // Fetch all in parallel
  const results = await Promise.allSettled(
    urls.map(async (url) => {
      const res = await fetch(url);
      if (!res.ok) return;
      const text = await res.text();
      svgTextCache.set(url, text);
    })
  );

  console.log(`[symbol-renderer] Preloaded ${svgTextCache.size}/${urls.length} SVG files`);
}

/**
 * Extract the inner content of an SVG (everything inside the <svg> root element).
 */
function extractSvgInner(svgText) {
  const open = svgText.indexOf('>', svgText.indexOf('<svg'));
  const close = svgText.lastIndexOf('</svg>');
  if (open < 0 || close < 0) return '';
  return svgText.slice(open + 1, close);
}

/**
 * Look up a cached SVG by its /svg/... path.
 */
function getSvg(path) {
  return svgTextCache.get(path) || null;
}

/**
 * Resolve the frame SVG path for a parsed SIDC.
 * Frame filename: {context}_{identity}{symbolSet}_{status}.svg
 */
function resolveFramePath(context, identity, symbolSet, status) {
  return `/svg/Frames/${context}_${identity}${symbolSet}_${status}.svg`;
}

/**
 * Resolve the entity icon SVG path. Handles full-frame icons and fallback.
 *
 * Icon filename: {symbolSet}{entity6}.svg  (or {symbolSet}{entity6}_{suffix}.svg for full-frame)
 *
 * Fallback chain: exact subtype → parent type (subtype=00) → parent entity (type=00, subtype=00)
 */
function resolveIconPath(identity, symbolSet, entity6) {
  const folder = SYMBOL_SET_FOLDER[symbolSet] || 'Land';
  const code8 = `${symbolSet}${entity6}`;
  const suffix = IDENTITY_SUFFIX[identity] || '_1';

  // Check if this is a known full-frame icon
  if (FULL_FRAME_CODES.has(code8)) {
    const path = `/svg/Appendices/${folder}/${code8}${suffix}.svg`;
    if (getSvg(path)) return path;
  }

  // Also check if the parent (subtype=00) is full-frame
  const parentCode = `${symbolSet}${entity6.slice(0, 4)}00`;
  if (FULL_FRAME_CODES.has(parentCode)) {
    const path = `/svg/Appendices/${folder}/${parentCode}${suffix}.svg`;
    if (getSvg(path)) return path;
  }

  // Standard (non-full-frame) lookup with fallback
  const exact = `/svg/Appendices/${folder}/${code8}.svg`;
  if (getSvg(exact)) return exact;

  // Drop subtype (last 2 digits → 00)
  const noSubtype = `/svg/Appendices/${folder}/${symbolSet}${entity6.slice(0, 4)}00.svg`;
  if (getSvg(noSubtype)) return noSubtype;

  // Drop type + subtype (last 4 digits → 0000)
  const noType = `/svg/Appendices/${folder}/${symbolSet}${entity6.slice(0, 2)}0000.svg`;
  if (getSvg(noType)) return noType;

  return null;
}

/**
 * Resolve modifier SVG path.
 * Mod1 filename: {symbolSet}{modCode}1.svg  in mod1/ subfolder
 * Mod2 filename: {symbolSet}{modCode}2.svg  in mod2/ subfolder
 */
function resolveModPath(symbolSet, modCode, modNum) {
  if (modCode === '00') return null;
  const folder = SYMBOL_SET_FOLDER[symbolSet] || 'Land';
  const dir = modNum === 1 ? 'mod1' : 'mod2';
  const filename = `${symbolSet}${modCode}${modNum}`;
  return `/svg/Appendices/${folder}/${dir}/${filename}.svg`;
}

/**
 * Composite frame + icon + modifiers into a single SVG data URL.
 */
function composite(frameSvg, iconSvg, mod1Svg, mod2Svg, size) {
  const layers = [];

  if (frameSvg) layers.push(`<g>${extractSvgInner(frameSvg)}</g>`);
  if (iconSvg) layers.push(`<g>${extractSvgInner(iconSvg)}</g>`);
  if (mod1Svg) layers.push(`<g>${extractSvgInner(mod1Svg)}</g>`);
  if (mod2Svg) layers.push(`<g>${extractSvgInner(mod2Svg)}</g>`);

  if (layers.length === 0) {
    // Return a simple fallback — gray circle with "?"
    return makeFallback(size);
  }

  // Compute height proportional to 612:792 aspect ratio
  const height = Math.round(size * (792 / 612));
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 612 792" width="${size}" height="${height}">${layers.join('')}</svg>`;

  return 'data:image/svg+xml,' + encodeURIComponent(svg);
}

/**
 * Fallback symbol when no SVGs are found.
 */
function makeFallback(size) {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" width="${size}" height="${size}">
    <circle cx="50" cy="50" r="40" fill="none" stroke="#888" stroke-width="3"/>
    <text x="50" y="58" text-anchor="middle" font-size="30" fill="#888">?</text>
  </svg>`;
  return 'data:image/svg+xml,' + encodeURIComponent(svg);
}

/**
 * Render a MIL-STD-2525D symbol from a 20-digit SIDC.
 *
 * @param {string} sidc  20-character SIDC string
 * @param {object} opts  { size: number } — pixel width of output (default 40)
 * @returns {string}     data:image/svg+xml;base64,... URL
 */
export function renderSymbol(sidc, opts = {}) {
  const size = opts.size || 40;
  const cacheKey = `${sidc}_${size}`;
  if (symbolCache.has(cacheKey)) return symbolCache.get(cacheKey);

  // Parse SIDC positions (1-indexed in spec, 0-indexed here)
  const context   = sidc[2];       // Position 3
  const identity  = sidc[3];       // Position 4
  const symbolSet = sidc.slice(4, 6);  // Positions 5-6
  const status    = sidc[6];       // Position 7
  const entity6   = sidc.slice(10, 16); // Positions 11-16
  const mod1Code  = sidc.slice(16, 18); // Positions 17-18
  const mod2Code  = sidc.slice(18, 20); // Positions 19-20

  // Resolve SVG paths
  const framePath = resolveFramePath(context, identity, symbolSet, status);
  const iconPath  = resolveIconPath(identity, symbolSet, entity6);
  const mod1Path  = resolveModPath(symbolSet, mod1Code, 1);
  const mod2Path  = resolveModPath(symbolSet, mod2Code, 2);

  // Get SVG text from cache
  const frameSvg = getSvg(framePath);
  const iconSvg  = iconPath ? getSvg(iconPath) : null;
  const mod1Svg  = mod1Path ? getSvg(mod1Path) : null;
  const mod2Svg  = mod2Path ? getSvg(mod2Path) : null;

  const url = composite(frameSvg, iconSvg, mod1Svg, mod2Svg, size);
  symbolCache.set(cacheKey, url);
  return url;
}

/**
 * Clear the rendered symbol cache (call after SIDC map changes).
 */
export function clearSymbolCache() {
  symbolCache.clear();
}
