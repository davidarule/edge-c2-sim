/**
 * CSV Import/Export for ORBAT Data
 *
 * Handles CSV and JSON import/export of Order of Battle data
 * for the Edge C2 Scenario Builder.
 */

import Papa from 'papaparse';
import { OrbatModel, VALID_DOMAINS, VALID_AGENCIES, VALID_STATUSES } from './orbat-model.js';

// --- Constants ---

export const CSV_COLUMNS = [
    'id', 'callsign', 'organisation', 'agency', 'entity_type', 'domain', 'sidc',
    'home_base_name', 'home_base_lat', 'home_base_lon',
    'speed_min', 'speed_max', 'speed_cruise',
    'altitude_min', 'altitude_max', 'altitude_cruise',
    'sensors', 'personnel_count', 'status',
    'ais_active', 'adsb_active', 'flag', 'vessel_type', 'aircraft_type',
    'mmsi', 'icao_hex', 'notes'
];

const AGENCY_COLORS = {
    RMP: '#1B3A8C',
    MMEA: '#FF6600',
    CI: '#2E7D32',
    RMAF: '#5C6BC0',
    MIL: '#4E342E',
    CIVILIAN: '#78909C'
};

// --- Helpers ---

/**
 * Parse a boolean from various string representations.
 * @param {string} value
 * @returns {boolean}
 */
function parseBoolean(value) {
    if (value === undefined || value === null || value === '') return false;
    const v = String(value).trim().toLowerCase();
    return v === 'true' || v === 'yes' || v === '1';
}

/**
 * Parse a numeric value, returning undefined if empty or invalid.
 * @param {string} value
 * @returns {number|undefined}
 */
function parseNum(value) {
    if (value === undefined || value === null || value === '') return undefined;
    const n = parseFloat(value);
    return isNaN(n) ? undefined : n;
}

/**
 * Parse an integer value, returning undefined if empty or invalid.
 * @param {string} value
 * @returns {number|undefined}
 */
function parseInt_(value) {
    if (value === undefined || value === null || value === '') return undefined;
    const n = parseInt(value, 10);
    return isNaN(n) ? undefined : n;
}

/**
 * Parse a semicolon-delimited string into an array.
 * @param {string} value
 * @returns {string[]}
 */
function parseSensors(value) {
    if (!value || typeof value !== 'string' || value.trim() === '') return [];
    return value.split(';').map(s => s.trim()).filter(s => s.length > 0);
}

/**
 * Serialize an array to a semicolon-delimited string.
 * @param {string[]} arr
 * @returns {string}
 */
function sensorsToString(arr) {
    if (!Array.isArray(arr)) return '';
    return arr.join(';');
}

// --- Import CSV ---

/**
 * Import ORBAT data from a CSV string.
 * @param {string} csvString
 * @returns {{ organisations: Object[], errors: string[], warnings: string[] }}
 */
export function importCSV(csvString) {
    const errors = [];
    const warnings = [];

    const result = Papa.parse(csvString, {
        header: true,
        skipEmptyLines: true,
        dynamicTyping: false
    });

    if (result.errors && result.errors.length > 0) {
        for (const e of result.errors) {
            errors.push(`CSV parse error (row ${e.row}): ${e.message}`);
        }
    }

    const rows = result.data || [];
    const validUnits = []; // { unit, organisation }

    for (let i = 0; i < rows.length; i++) {
        const row = rows[i];
        const rowNum = i + 2; // 1-indexed, header is row 1
        const rowErrors = [];
        const rowWarnings = [];

        // Required: id
        const id = (row.id || '').trim();
        if (!id) {
            rowErrors.push(`Row ${rowNum}: id is required and must be non-empty`);
        }

        // Required: entity_type
        const entity_type = (row.entity_type || '').trim();
        if (!entity_type) {
            rowErrors.push(`Row ${rowNum}: entity_type is required and must be non-empty`);
        }

        // Required: domain
        const domain = (row.domain || '').trim();
        if (!VALID_DOMAINS.includes(domain)) {
            rowErrors.push(`Row ${rowNum}: domain must be one of: ${VALID_DOMAINS.join(', ')} (got "${domain}")`);
        }

        // Required: agency
        const agency = (row.agency || '').trim();
        if (!VALID_AGENCIES.includes(agency)) {
            rowErrors.push(`Row ${rowNum}: agency must be one of: ${VALID_AGENCIES.join(', ')} (got "${agency}")`);
        }

        // SIDC validation
        const sidc = (row.sidc || '').trim();
        if (sidc && !/^\d{20}$/.test(sidc)) {
            rowErrors.push(`Row ${rowNum}: sidc must be exactly 20 digits (got "${sidc}")`);
        }

        // home_base lat/lon validation
        const home_base_lat = parseNum(row.home_base_lat);
        const home_base_lon = parseNum(row.home_base_lon);

        if (row.home_base_lat !== undefined && row.home_base_lat !== '') {
            if (home_base_lat === undefined) {
                rowWarnings.push(`Row ${rowNum}: home_base_lat is not a valid number`);
            } else if (home_base_lat < -90 || home_base_lat > 90) {
                rowErrors.push(`Row ${rowNum}: home_base_lat must be between -90 and 90`);
            }
        }

        if (row.home_base_lon !== undefined && row.home_base_lon !== '') {
            if (home_base_lon === undefined) {
                rowWarnings.push(`Row ${rowNum}: home_base_lon is not a valid number`);
            } else if (home_base_lon < -180 || home_base_lon > 180) {
                rowErrors.push(`Row ${rowNum}: home_base_lon must be between -180 and 180`);
            }
        }

        // Speed validation
        const speed_min = parseNum(row.speed_min);
        const speed_max = parseNum(row.speed_max);
        const speed_cruise = parseNum(row.speed_cruise);

        for (const [name, val, raw] of [
            ['speed_min', speed_min, row.speed_min],
            ['speed_max', speed_max, row.speed_max],
            ['speed_cruise', speed_cruise, row.speed_cruise]
        ]) {
            if (raw !== undefined && raw !== '' && val === undefined) {
                rowWarnings.push(`Row ${rowNum}: ${name} is not a valid number`);
            } else if (val !== undefined && val < 0) {
                rowErrors.push(`Row ${rowNum}: ${name} must be non-negative`);
            }
        }

        // Altitude validation
        const altitude_min = parseNum(row.altitude_min);
        const altitude_max = parseNum(row.altitude_max);
        const altitude_cruise = parseNum(row.altitude_cruise);

        // Status validation
        const rawStatus = (row.status || '').trim();
        let status = 'OPERATIONAL';
        if (rawStatus) {
            if (VALID_STATUSES.includes(rawStatus)) {
                status = rawStatus;
            } else {
                rowWarnings.push(`Row ${rowNum}: status "${rawStatus}" is not valid, defaulting to OPERATIONAL`);
            }
        }

        // If there are required-field errors, skip this row
        if (rowErrors.length > 0) {
            errors.push(...rowErrors);
            warnings.push(...rowWarnings);
            continue;
        }

        // Collect warnings
        warnings.push(...rowWarnings);

        // Build unit object
        const unit = {
            id,
            callsign: (row.callsign || '').trim() || undefined,
            entity_type,
            domain,
            agency,
            sidc: sidc || undefined,
            home_base: {
                lat: home_base_lat !== undefined ? home_base_lat : undefined,
                lon: home_base_lon !== undefined ? home_base_lon : undefined,
                name: (row.home_base_name || '').trim() || undefined
            },
            speed_min,
            speed_max,
            speed_cruise,
            altitude_min,
            altitude_max,
            altitude_cruise,
            sensors: parseSensors(row.sensors),
            weapons: [],
            personnel_count: parseInt_(row.personnel_count),
            status,
            metadata: {
                ais_active: parseBoolean(row.ais_active),
                adsb_active: parseBoolean(row.adsb_active),
                flag: (row.flag || '').trim() || undefined,
                vessel_type: (row.vessel_type || '').trim() || undefined,
                aircraft_type: (row.aircraft_type || '').trim() || undefined,
                mmsi: (row.mmsi || '').trim() || undefined,
                icao_hex: (row.icao_hex || '').trim() || undefined
            },
            notes: (row.notes || '').trim() || undefined
        };

        const organisation = (row.organisation || '').trim() || 'Unknown';
        validUnits.push({ unit, organisation, agency });
    }

    // Group by organisation
    const orgMap = new Map();
    for (const { unit, organisation, agency } of validUnits) {
        if (!orgMap.has(organisation)) {
            orgMap.set(organisation, { agency, units: [] });
        }
        orgMap.get(organisation).units.push(unit);
    }

    // Build organisation objects
    const organisations = [];
    for (const [name, { agency, units }] of orgMap) {
        const abbreviation = agency;
        organisations.push({
            id: `org_${abbreviation.toLowerCase()}`,
            name,
            abbreviation,
            color: AGENCY_COLORS[agency] || '#78909C',
            standard_identity: 3,
            units
        });
    }

    return { organisations, errors, warnings };
}

// --- Export CSV ---

/**
 * Export ORBAT data to a CSV string.
 * @param {OrbatModel} orbatModel
 * @returns {string}
 */
export function exportCSV(orbatModel) {
    const rows = [];
    const orgs = orbatModel.getOrganisations();

    for (const org of orgs) {
        const orgName = org.name || '';
        const units = org.units || [];

        for (const unit of units) {
            const meta = unit.metadata || {};
            const homeBase = unit.home_base || {};

            const row = {
                id: unit.id || '',
                callsign: unit.callsign || '',
                organisation: orgName,
                agency: unit.agency || '',
                entity_type: unit.entity_type || '',
                domain: unit.domain || '',
                sidc: unit.sidc || '',
                home_base_name: homeBase.name || '',
                home_base_lat: homeBase.lat !== undefined && homeBase.lat !== null ? String(homeBase.lat) : '',
                home_base_lon: homeBase.lon !== undefined && homeBase.lon !== null ? String(homeBase.lon) : '',
                speed_min: unit.speed_min !== undefined && unit.speed_min !== null ? String(unit.speed_min) : '',
                speed_max: unit.speed_max !== undefined && unit.speed_max !== null ? String(unit.speed_max) : '',
                speed_cruise: unit.speed_cruise !== undefined && unit.speed_cruise !== null ? String(unit.speed_cruise) : '',
                altitude_min: unit.altitude_min !== undefined && unit.altitude_min !== null ? String(unit.altitude_min) : '',
                altitude_max: unit.altitude_max !== undefined && unit.altitude_max !== null ? String(unit.altitude_max) : '',
                altitude_cruise: unit.altitude_cruise !== undefined && unit.altitude_cruise !== null ? String(unit.altitude_cruise) : '',
                sensors: sensorsToString(unit.sensors),
                personnel_count: unit.personnel_count !== undefined && unit.personnel_count !== null ? String(unit.personnel_count) : '',
                status: unit.status || '',
                ais_active: meta.ais_active ? 'true' : 'false',
                adsb_active: meta.adsb_active ? 'true' : 'false',
                flag: meta.flag || '',
                vessel_type: meta.vessel_type || '',
                aircraft_type: meta.aircraft_type || '',
                mmsi: meta.mmsi || '',
                icao_hex: meta.icao_hex || '',
                notes: unit.notes || ''
            };

            rows.push(row);
        }
    }

    return Papa.unparse(rows, {
        header: true,
        columns: CSV_COLUMNS
    });
}

// --- Download Helper ---

/**
 * Trigger a CSV file download in the browser.
 * @param {string} csvString
 * @param {string} filename
 */
export function downloadCSV(csvString, filename) {
    const blob = new Blob([csvString], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename || 'orbat.csv';
    a.style.display = 'none';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
}

// --- JSON Import/Export ---

/**
 * Import ORBAT data from a JSON string.
 * @param {string} jsonString
 * @returns {{ organisations: Object[], errors: string[] }}
 */
export function importJSON(jsonString) {
    const errors = [];

    let data;
    try {
        data = JSON.parse(jsonString);
    } catch (e) {
        return { organisations: [], errors: [`Invalid JSON: ${e.message}`] };
    }

    if (!data || typeof data !== 'object') {
        return { organisations: [], errors: ['JSON must be an object'] };
    }

    const rawOrgs = Array.isArray(data.organisations) ? data.organisations : [];
    if (rawOrgs.length === 0) {
        errors.push('No organisations found in JSON');
    }

    const organisations = [];
    for (let i = 0; i < rawOrgs.length; i++) {
        const org = rawOrgs[i];
        if (!org || typeof org !== 'object') {
            errors.push(`Organisation at index ${i} is not a valid object`);
            continue;
        }

        const units = Array.isArray(org.units) ? org.units : [];
        organisations.push({
            id: org.id || `org_${i}`,
            name: org.name || '',
            abbreviation: org.abbreviation || '',
            color: org.color || '#78909C',
            standard_identity: org.standard_identity !== undefined ? org.standard_identity : 3,
            units: units.map(u => ({ ...u }))
        });
    }

    return { organisations, errors };
}

/**
 * Serialize an OrbatModel to a JSON string.
 * @param {OrbatModel} orbatModel
 * @returns {string}
 */
export function exportJSON(orbatModel) {
    return JSON.stringify(orbatModel.toJSON(), null, 2);
}
