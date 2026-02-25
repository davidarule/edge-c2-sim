/**
 * YAML Import/Export Engine for the Edge C2 Scenario Builder.
 *
 * Converts between the in-memory scenario state (JavaScript objects) and
 * valid YAML matching the scenario format defined in docs/SCENARIO_AUTHORING.md.
 *
 * Uses js-yaml for serialization/deserialization.
 */

import jsyaml from 'js-yaml';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const VALID_AGENCIES = ['RMP', 'MMEA', 'CI', 'RMAF', 'MIL', 'CIVILIAN'];
const VALID_DOMAINS = ['MARITIME', 'AIR', 'GROUND_VEHICLE', 'PERSONNEL'];
const VALID_SEVERITIES = ['INFO', 'WARNING', 'CRITICAL'];
const VALID_BEHAVIORS = ['patrol', 'standby', 'stationary'];
const VALID_EVENT_TYPES = [
    'DETECTION', 'ALERT', 'ORDER', 'INCIDENT', 'ARRIVAL',
    'INTERCEPT', 'BOARDING', 'RESOLUTION', 'AIS_LOSS',
];
const VALID_ACTIONS = [
    'intercept', 'deploy', 'search_area', 'patrol', 'respond',
    'lockdown', 'escort_to_port', 'activate', 'process', 'secure', 'airlift',
];

// Time regex: "MM:SS"
const TIME_RE = /^\d{2,}:\d{2}$/;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Format a number for YAML output: strip trailing zeros but keep enough
 * precision that round-trip doesn't alter the value.
 */
function cleanNumber(v) {
    if (typeof v !== 'number' || !isFinite(v)) return v;
    return v;
}

/**
 * Return a shallow plain-object copy with undefined/null values removed and
 * empty objects/arrays removed when requested.
 */
function compactObject(obj, removeEmpty = false) {
    const out = {};
    for (const [k, v] of Object.entries(obj)) {
        if (v === undefined || v === null) continue;
        if (removeEmpty && Array.isArray(v) && v.length === 0) continue;
        if (removeEmpty && typeof v === 'object' && !Array.isArray(v) && Object.keys(v).length === 0) continue;
        out[k] = v;
    }
    return out;
}

/**
 * Convert builder waypoint to YAML waypoint format.
 * Builder: { latitude, longitude, altitude_m, speed_knots, timestamp_offset }
 * YAML:    { lat, lon, speed, time, alt (optional) }
 */
function waypointToYAML(wp) {
    const out = {
        lat: cleanNumber(wp.latitude),
        lon: cleanNumber(wp.longitude),
        speed: cleanNumber(wp.speed_knots != null ? wp.speed_knots : wp.speed),
        time: wp.timestamp_offset != null ? wp.timestamp_offset : wp.time,
    };
    if (wp.altitude_m != null && wp.altitude_m !== 0) {
        out.alt = cleanNumber(wp.altitude_m);
    }
    return out;
}

/**
 * Convert YAML waypoint to builder waypoint format.
 */
function waypointFromYAML(wp) {
    return {
        latitude: wp.lat,
        longitude: wp.lon,
        altitude_m: wp.alt != null ? wp.alt : 0,
        speed_knots: wp.speed != null ? wp.speed : 0,
        timestamp_offset: wp.time || '00:00',
    };
}

/**
 * Convert a scenario entity from builder state to YAML entity format.
 */
function entityToYAML(entity) {
    const out = {};

    // Ordered fields for readability
    out.id = entity.id;
    out.type = entity.entity_type;
    if (entity.callsign) out.callsign = entity.callsign;
    if (entity.agency) out.agency = entity.agency;

    // Initial position
    if (entity.initial_position) {
        const pos = { lat: cleanNumber(entity.initial_position.latitude), lon: cleanNumber(entity.initial_position.longitude) };
        if (entity.initial_position.altitude_m != null && entity.initial_position.altitude_m !== 0) {
            pos.alt = cleanNumber(entity.initial_position.altitude_m);
        }
        out.initial_position = pos;
    }

    // Behavior
    if (entity.behavior) {
        if (typeof entity.behavior === 'object') {
            out.behavior = entity.behavior.type || 'standby';
            // Flatten behavior params into entity level (matching YAML format)
            if (entity.behavior.patrol_area) out.patrol_area = entity.behavior.patrol_area;
            if (entity.behavior.area) out.patrol_area = entity.behavior.area;
        } else {
            out.behavior = entity.behavior;
        }
    }

    // patrol_area at entity level (may already be set from behavior)
    if (entity.patrol_area && !out.patrol_area) {
        out.patrol_area = entity.patrol_area;
    }

    // Waypoints
    if (entity.waypoints && entity.waypoints.length > 0) {
        out.waypoints = entity.waypoints.map(waypointToYAML);
    }

    // Speed and heading (only if explicitly set and not zero)
    if (entity.speed_knots != null && entity.speed_knots !== 0) {
        out.speed_knots = cleanNumber(entity.speed_knots);
    }
    if (entity.heading_deg != null && entity.heading_deg !== 0) {
        out.heading_deg = cleanNumber(entity.heading_deg);
    }

    // SIDC
    if (entity.sidc) {
        out.sidc = entity.sidc;
    }

    // Metadata
    if (entity.metadata && Object.keys(entity.metadata).length > 0) {
        out.metadata = { ...entity.metadata };
    }

    // Intentionally omit builder-only fields: placed, domain, status
    return out;
}

/**
 * Convert a YAML entity to builder state format.
 */
function entityFromYAML(yamlEntity) {
    const entity = {
        id: yamlEntity.id || '',
        callsign: yamlEntity.callsign || '',
        entity_type: yamlEntity.type || '',
        agency: yamlEntity.agency || '',
        domain: inferDomain(yamlEntity.type),
        sidc: yamlEntity.sidc || '',
        initial_position: null,
        speed_knots: yamlEntity.speed_knots || 0,
        heading_deg: yamlEntity.heading_deg || 0,
        status: 'ACTIVE',
        waypoints: [],
        behavior: null,
        metadata: yamlEntity.metadata ? { ...yamlEntity.metadata } : {},
        placed: false,
    };

    // Position
    if (yamlEntity.initial_position) {
        const pos = yamlEntity.initial_position;
        entity.initial_position = {
            latitude: pos.lat,
            longitude: pos.lon,
            altitude_m: pos.alt || 0,
        };
        entity.placed = true;
    }

    // Behavior — rebuild as structured object
    if (yamlEntity.behavior) {
        entity.behavior = { type: yamlEntity.behavior };
        if (yamlEntity.patrol_area) {
            entity.behavior.patrol_area = yamlEntity.patrol_area;
        }
    }

    // Waypoints
    if (Array.isArray(yamlEntity.waypoints)) {
        entity.waypoints = yamlEntity.waypoints.map(waypointFromYAML);
    }

    return entity;
}

/**
 * Infer domain from entity type string.
 */
function inferDomain(entityType) {
    if (!entityType) return '';
    const t = entityType.toUpperCase();
    if (t.includes('FISHING') || t.includes('CARGO') || t.includes('TANKER') ||
        t.includes('PASSENGER') || t.includes('PATROL') && (t.includes('MMEA') || t.includes('NAVAL')) ||
        t.includes('VESSEL') || t.includes('FAST_INTERCEPT') || t.includes('NAVAL')) {
        return 'MARITIME';
    }
    if (t.includes('FIGHTER') || t.includes('TRANSPORT') && t.includes('RMAF') ||
        t.includes('HELICOPTER') || t.includes('MPA') || t.includes('COMMERCIAL') ||
        t.includes('LIGHT') && t.includes('CIVILIAN')) {
        return 'AIR';
    }
    if (t.includes('CAR') || t.includes('TACTICAL') && t.includes('RMP') ||
        t.includes('APC') || t.includes('COMMAND') || t.includes('CHECKPOINT') ||
        t.includes('MOBILE_UNIT')) {
        return 'GROUND_VEHICLE';
    }
    if (t.includes('OFFICER') || t.includes('TEAM') || t.includes('SQUAD') ||
        t.includes('FORCES') || t.includes('INFANTRY') || t.includes('IMMIGRATION')) {
        return 'PERSONNEL';
    }
    return '';
}

/**
 * Convert a background entity from builder state to YAML format.
 */
function backgroundToYAML(bg) {
    const out = {};
    out.type = bg.entity_type || bg.type;
    out.count = bg.count;

    // Area: can be a string (reference) or GeoJSON polygon object
    if (bg.area) {
        out.area = bg.area;
    }
    if (bg.route) {
        out.route = bg.route;
    }

    // Speed range → speed_variation (approximate)
    if (bg.speed_range && Array.isArray(bg.speed_range) && bg.speed_range.length === 2) {
        const [min, max] = bg.speed_range;
        if (min > 0 && max > min) {
            const mid = (min + max) / 2;
            out.speed_variation = cleanNumber(parseFloat(((max - mid) / mid).toFixed(2)));
        }
    }
    if (bg.speed_variation != null) {
        out.speed_variation = bg.speed_variation;
    }

    if (bg.metadata && Object.keys(bg.metadata).length > 0) {
        out.metadata = { ...bg.metadata };
    }

    return compactObject(out);
}

/**
 * Convert a YAML background entity to builder state format.
 */
function backgroundFromYAML(yamlBg) {
    const bg = {
        entity_type: yamlBg.type || '',
        count: yamlBg.count || 1,
        area: yamlBg.area || yamlBg.route || '',
        metadata: yamlBg.metadata ? { ...yamlBg.metadata } : {},
    };

    // Reconstruct speed_range from speed_variation if present
    if (yamlBg.speed_variation != null) {
        bg.speed_variation = yamlBg.speed_variation;
    }

    // Keep route separately if present
    if (yamlBg.route) {
        bg.area = yamlBg.route;
    }

    return bg;
}

/**
 * Convert an event from builder state to YAML format.
 */
function eventToYAML(evt) {
    const out = {};

    out.time = evt.time;
    out.type = evt.type;
    if (evt.description) out.description = evt.description;

    // Severity
    if (evt.severity) out.severity = evt.severity;

    // Target(s)
    if (evt.targets && evt.targets.length > 0) {
        if (evt.targets.length === 1) {
            out.target = evt.targets[0];
        } else {
            out.targets = [...evt.targets];
        }
    }

    // Actions — flatten first action into event level for standard YAML format
    if (evt.actions && evt.actions.length > 0) {
        const primary = evt.actions[0];
        if (primary.action) out.action = primary.action;
        if (primary.intercept_target) out.intercept_target = primary.intercept_target;
        if (primary.destination) {
            out.destination = {
                lat: cleanNumber(primary.destination.latitude != null ? primary.destination.latitude : primary.destination.lat),
                lon: cleanNumber(primary.destination.longitude != null ? primary.destination.longitude : primary.destination.lon),
            };
        }
        if (primary.area) out.area = primary.area;
        if (primary.escort) out.escort = [...primary.escort];
    } else if (evt.action) {
        // Direct action field (already flat)
        out.action = evt.action;
        if (evt.intercept_target) out.intercept_target = evt.intercept_target;
        if (evt.destination) out.destination = evt.destination;
        if (evt.area) out.area = evt.area;
        if (evt.escort) out.escort = evt.escort;
    }

    // Source
    if (evt.source) out.source = evt.source;

    // Position
    if (evt.position) {
        out.position = {
            lat: cleanNumber(evt.position.latitude != null ? evt.position.latitude : evt.position.lat),
            lon: cleanNumber(evt.position.longitude != null ? evt.position.longitude : evt.position.lon),
        };
    }

    // Alert agencies
    if (evt.alert_agencies && evt.alert_agencies.length > 0) {
        out.alert_agencies = [...evt.alert_agencies];
    }

    return compactObject(out);
}

/**
 * Convert a YAML event to builder state format.
 */
function eventFromYAML(yamlEvt) {
    const evt = {
        time: yamlEvt.time || '00:00',
        type: yamlEvt.type || '',
        severity: yamlEvt.severity || '',
        description: yamlEvt.description || '',
        targets: [],
        actions: [],
        alert_agencies: yamlEvt.alert_agencies ? [...yamlEvt.alert_agencies] : [],
        position: null,
        source: yamlEvt.source || null,
    };

    // Targets — normalize single target to array
    if (yamlEvt.targets && Array.isArray(yamlEvt.targets)) {
        evt.targets = [...yamlEvt.targets];
    } else if (yamlEvt.target) {
        evt.targets = [yamlEvt.target];
    }

    // Position
    if (yamlEvt.position) {
        evt.position = {
            latitude: yamlEvt.position.lat,
            longitude: yamlEvt.position.lon,
        };
    }

    // Actions — reconstruct structured action from flat YAML fields
    if (yamlEvt.action) {
        const action = { action: yamlEvt.action };
        if (yamlEvt.intercept_target) action.intercept_target = yamlEvt.intercept_target;
        if (yamlEvt.destination) {
            action.destination = {
                latitude: yamlEvt.destination.lat,
                longitude: yamlEvt.destination.lon,
            };
        }
        if (yamlEvt.area) action.area = yamlEvt.area;
        if (yamlEvt.escort) action.escort = [...yamlEvt.escort];
        evt.actions = [action];
    }

    return evt;
}

// ---------------------------------------------------------------------------
// Validation helpers
// ---------------------------------------------------------------------------

/**
 * Validate the parsed YAML structure and collect errors/warnings.
 * @param {Object} raw - Raw parsed YAML root
 * @returns {{ errors: string[], warnings: string[] }}
 */
function validateStructure(raw) {
    const errors = [];
    const warnings = [];

    if (!raw || typeof raw !== 'object') {
        errors.push('YAML root must be an object');
        return { errors, warnings };
    }

    // Accept both { scenario: { ... } } and bare { name: ..., ... } forms
    const sc = raw.scenario || raw;

    if (!sc.name && !sc.scenario_entities && !sc.events) {
        errors.push('YAML does not appear to contain a valid scenario (missing name, scenario_entities, or events)');
        return { errors, warnings };
    }

    // Metadata
    if (!sc.name) warnings.push('Scenario name is missing');
    if (!sc.duration_minutes) warnings.push('duration_minutes is missing; defaulting to 60');

    // Entities
    const entityIds = new Set();
    if (sc.scenario_entities && Array.isArray(sc.scenario_entities)) {
        for (let i = 0; i < sc.scenario_entities.length; i++) {
            const e = sc.scenario_entities[i];
            const prefix = `scenario_entities[${i}]`;
            if (!e.id) errors.push(`${prefix}: missing id`);
            if (!e.type) errors.push(`${prefix}: missing type`);
            if (e.id && entityIds.has(e.id)) {
                errors.push(`${prefix}: duplicate entity id "${e.id}"`);
            }
            if (e.id) entityIds.add(e.id);
            if (e.agency && !VALID_AGENCIES.includes(e.agency)) {
                warnings.push(`${prefix}: unknown agency "${e.agency}"`);
            }
            if (e.behavior && typeof e.behavior === 'string' && !VALID_BEHAVIORS.includes(e.behavior)) {
                warnings.push(`${prefix}: unknown behavior "${e.behavior}"`);
            }
            if (e.waypoints && Array.isArray(e.waypoints)) {
                for (let w = 0; w < e.waypoints.length; w++) {
                    const wp = e.waypoints[w];
                    if (wp.lat == null || wp.lon == null) {
                        errors.push(`${prefix}.waypoints[${w}]: missing lat/lon`);
                    }
                    if (wp.lat != null && (wp.lat < -90 || wp.lat > 90)) {
                        errors.push(`${prefix}.waypoints[${w}]: lat out of range`);
                    }
                    if (wp.lon != null && (wp.lon < -180 || wp.lon > 180)) {
                        errors.push(`${prefix}.waypoints[${w}]: lon out of range`);
                    }
                }
            }
        }
    }

    // Events
    if (sc.events && Array.isArray(sc.events)) {
        let lastMinutes = -1;
        for (let i = 0; i < sc.events.length; i++) {
            const ev = sc.events[i];
            const prefix = `events[${i}]`;
            if (!ev.time) {
                errors.push(`${prefix}: missing time`);
            } else if (!TIME_RE.test(ev.time)) {
                errors.push(`${prefix}: invalid time format "${ev.time}" (expected MM:SS)`);
            } else {
                const [mm, ss] = ev.time.split(':').map(Number);
                const totalSec = mm * 60 + ss;
                if (totalSec < lastMinutes) {
                    warnings.push(`${prefix}: event time "${ev.time}" is not in chronological order`);
                }
                lastMinutes = totalSec;
            }
            if (!ev.type) {
                errors.push(`${prefix}: missing type`);
            } else if (!VALID_EVENT_TYPES.includes(ev.type)) {
                warnings.push(`${prefix}: unknown event type "${ev.type}"`);
            }
            // Validate target references
            const targets = ev.targets
                ? (Array.isArray(ev.targets) ? ev.targets : [ev.targets])
                : (ev.target ? [ev.target] : []);
            for (const tid of targets) {
                if (tid && !entityIds.has(tid)) {
                    warnings.push(`${prefix}: target "${tid}" not found in scenario_entities`);
                }
            }
            if (ev.action && !VALID_ACTIONS.includes(ev.action)) {
                warnings.push(`${prefix}: unknown action "${ev.action}"`);
            }
        }
    }

    // Background entities
    if (sc.background_entities && Array.isArray(sc.background_entities)) {
        for (let i = 0; i < sc.background_entities.length; i++) {
            const bg = sc.background_entities[i];
            const prefix = `background_entities[${i}]`;
            if (!bg.type) errors.push(`${prefix}: missing type`);
            if (!bg.count || bg.count < 1) warnings.push(`${prefix}: count should be >= 1`);
            if (!bg.area && !bg.route) warnings.push(`${prefix}: no area or route specified`);
        }
    }

    return { errors, warnings };
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Export a builder scenario state to a YAML string matching the
 * SCENARIO_AUTHORING.md format.
 *
 * @param {Object} scenarioState - The in-memory scenario state
 * @returns {string} Valid YAML string
 */
export function exportScenarioYAML(scenarioState) {
    if (!scenarioState) {
        throw new Error('scenarioState is required');
    }

    const meta = scenarioState.metadata || {};

    // Build the YAML structure
    const scenario = {};
    scenario.name = meta.name || 'Untitled Scenario';
    if (meta.description) scenario.description = meta.description;
    scenario.duration_minutes = meta.duration_minutes || 60;
    if (meta.area_of_operations) scenario.area_of_operations = meta.area_of_operations;
    if (meta.classification) scenario.classification = meta.classification;
    if (meta.center) scenario.center = meta.center;
    if (meta.zoom) scenario.zoom = meta.zoom;

    // Background entities
    if (scenarioState.background_entities && scenarioState.background_entities.length > 0) {
        scenario.background_entities = scenarioState.background_entities.map(backgroundToYAML);
    }

    // Scenario entities
    if (scenarioState.entities && scenarioState.entities.length > 0) {
        scenario.scenario_entities = scenarioState.entities.map(entityToYAML);
    }

    // Events
    if (scenarioState.events && scenarioState.events.length > 0) {
        // Sort events chronologically before export
        const sorted = [...scenarioState.events].sort((a, b) => {
            return timeToSeconds(a.time) - timeToSeconds(b.time);
        });
        scenario.events = sorted.map(eventToYAML);
    }

    const root = { scenario };

    // Dump with custom options for clean output
    return jsyaml.dump(root, {
        indent: 2,
        lineWidth: 120,
        noRefs: true,
        sortKeys: false,
        quotingType: '"',
        forceQuotes: false,
        flowLevel: -1,
        styles: {},
    });
}

/**
 * Convert "MM:SS" time string to total seconds for sorting.
 */
function timeToSeconds(time) {
    if (!time || typeof time !== 'string') return 0;
    const parts = time.split(':');
    if (parts.length !== 2) return 0;
    return parseInt(parts[0], 10) * 60 + parseInt(parts[1], 10);
}

/**
 * Import a YAML string and parse it into the builder scenario state.
 *
 * @param {string} yamlString - Raw YAML content
 * @returns {{ scenario: Object|null, errors: string[], warnings: string[] }}
 */
export function importScenarioYAML(yamlString) {
    const result = { scenario: null, errors: [], warnings: [] };

    if (!yamlString || typeof yamlString !== 'string' || yamlString.trim() === '') {
        result.errors.push('YAML input is empty');
        return result;
    }

    // Parse YAML
    let raw;
    try {
        raw = jsyaml.load(yamlString);
    } catch (e) {
        result.errors.push(`YAML parse error: ${e.message}`);
        return result;
    }

    // Validate structure
    const validation = validateStructure(raw);
    result.errors.push(...validation.errors);
    result.warnings.push(...validation.warnings);

    // If critical errors, stop
    if (result.errors.length > 0) {
        return result;
    }

    // Extract scenario root (support both wrapped and bare forms)
    const sc = raw.scenario || raw;

    // Build scenario state
    const state = createEmptyScenario();

    // Metadata
    state.metadata.name = sc.name || '';
    state.metadata.description = sc.description || '';
    state.metadata.duration_minutes = sc.duration_minutes || 60;
    state.metadata.area_of_operations = sc.area_of_operations || '';
    state.metadata.classification = sc.classification || '';
    if (sc.center) state.metadata.center = sc.center;
    if (sc.zoom) state.metadata.zoom = sc.zoom;

    // Scenario entities
    if (Array.isArray(sc.scenario_entities)) {
        state.entities = sc.scenario_entities.map(entityFromYAML);
    }

    // Background entities
    if (Array.isArray(sc.background_entities)) {
        state.background_entities = sc.background_entities.map(backgroundFromYAML);
    }

    // Events
    if (Array.isArray(sc.events)) {
        state.events = sc.events.map(eventFromYAML);
    }

    result.scenario = state;
    return result;
}

/**
 * Trigger a browser file download of a YAML string.
 *
 * @param {string} yamlString - The YAML content
 * @param {string} [filename='scenario.yaml'] - Download filename
 */
export function downloadYAML(yamlString, filename = 'scenario.yaml') {
    if (typeof document === 'undefined') {
        throw new Error('downloadYAML requires a browser environment');
    }

    const blob = new Blob([yamlString], { type: 'application/x-yaml;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.style.display = 'none';
    document.body.appendChild(a);
    a.click();

    // Cleanup
    setTimeout(() => {
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    }, 100);
}

/**
 * Open a file picker dialog and load a YAML scenario file.
 *
 * @returns {Promise<{ scenario: Object|null, errors: string[], warnings: string[] }>}
 */
export function pickAndLoadYAML() {
    if (typeof document === 'undefined') {
        return Promise.reject(new Error('pickAndLoadYAML requires a browser environment'));
    }

    return new Promise((resolve, reject) => {
        const input = document.createElement('input');
        input.type = 'file';
        input.accept = '.yaml,.yml';
        input.style.display = 'none';

        input.addEventListener('change', () => {
            const file = input.files && input.files[0];
            if (!file) {
                resolve({ scenario: null, errors: ['No file selected'], warnings: [] });
                cleanup();
                return;
            }

            const reader = new FileReader();
            reader.onload = () => {
                const result = importScenarioYAML(reader.result);
                resolve(result);
                cleanup();
            };
            reader.onerror = () => {
                resolve({ scenario: null, errors: [`Failed to read file: ${reader.error}`], warnings: [] });
                cleanup();
            };
            reader.readAsText(file);
        });

        // Handle cancel — the change event doesn't fire, so use focus as fallback
        const handleFocus = () => {
            setTimeout(() => {
                if (!input.files || input.files.length === 0) {
                    resolve({ scenario: null, errors: ['File selection cancelled'], warnings: [] });
                    cleanup();
                }
            }, 500);
        };

        function cleanup() {
            window.removeEventListener('focus', handleFocus);
            if (input.parentNode) {
                document.body.removeChild(input);
            }
        }

        window.addEventListener('focus', handleFocus, { once: true });
        document.body.appendChild(input);
        input.click();
    });
}

/**
 * Create a blank scenario state with all required fields.
 *
 * @returns {Object} Empty scenario state matching the builder data model
 */
export function createEmptyScenario() {
    return {
        metadata: {
            name: '',
            description: '',
            duration_minutes: 60,
            area_of_operations: '',
            classification: '',
        },
        entities: [],
        background_entities: [],
        events: [],
    };
}
