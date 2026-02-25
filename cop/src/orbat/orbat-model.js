/**
 * ORBAT (Order of Battle) Data Model
 *
 * Defines data structures for organisations and their units/assets
 * used in the Edge C2 Scenario Builder.
 */

// --- Constants ---

export const VALID_DOMAINS = ['MARITIME', 'AIR', 'GROUND_VEHICLE', 'PERSONNEL'];
export const VALID_AGENCIES = ['RMP', 'MMEA', 'CI', 'RMAF', 'MIL', 'CIVILIAN'];
export const VALID_STATUSES = ['OPERATIONAL', 'MAINTENANCE', 'RESERVE'];
export const VALID_SENSORS = ['radar', 'ais_receiver', 'eo_ir', 'esm', 'sonar', 'adsb_receiver'];

// --- ID Generation ---

function generateId(prefix) {
    return `${prefix}_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`;
}

// --- Validation ---

/**
 * Validate a unit object.
 * @param {Object} unit
 * @returns {{ valid: boolean, errors: string[] }}
 */
export function validateUnit(unit) {
    const errors = [];

    if (!unit || typeof unit !== 'object') {
        return { valid: false, errors: ['Unit must be a non-null object'] };
    }

    // id
    if (!unit.id || typeof unit.id !== 'string' || unit.id.trim() === '') {
        errors.push('id is required and must be a non-empty string');
    }

    // entity_type
    if (!unit.entity_type || typeof unit.entity_type !== 'string') {
        errors.push('entity_type is required and must be a string');
    }

    // domain
    if (!VALID_DOMAINS.includes(unit.domain)) {
        errors.push(`domain must be one of: ${VALID_DOMAINS.join(', ')}`);
    }

    // agency
    if (!VALID_AGENCIES.includes(unit.agency)) {
        errors.push(`agency must be one of: ${VALID_AGENCIES.join(', ')}`);
    }

    // sidc — 20 digits
    if (unit.sidc !== undefined && unit.sidc !== null && unit.sidc !== '') {
        if (typeof unit.sidc !== 'string' || !/^\d{20}$/.test(unit.sidc)) {
            errors.push('sidc must be exactly 20 digits');
        }
    }

    // home_base lat/lon
    if (unit.home_base && typeof unit.home_base === 'object') {
        const { lat, lon } = unit.home_base;
        if (lat !== undefined && (typeof lat !== 'number' || lat < -90 || lat > 90)) {
            errors.push('home_base.lat must be a number between -90 and 90');
        }
        if (lon !== undefined && (typeof lon !== 'number' || lon < -180 || lon > 180)) {
            errors.push('home_base.lon must be a number between -180 and 180');
        }
    }

    // speeds — non-negative
    for (const field of ['speed_min', 'speed_max', 'speed_cruise']) {
        if (unit[field] !== undefined && unit[field] !== null) {
            if (typeof unit[field] !== 'number' || unit[field] < 0) {
                errors.push(`${field} must be a non-negative number`);
            }
        }
    }

    // altitudes — non-negative (AIR domain)
    for (const field of ['altitude_min', 'altitude_max', 'altitude_cruise']) {
        if (unit[field] !== undefined && unit[field] !== null) {
            if (typeof unit[field] !== 'number' || unit[field] < 0) {
                errors.push(`${field} must be a non-negative number`);
            }
        }
    }

    // status
    if (unit.status !== undefined && unit.status !== null) {
        if (!VALID_STATUSES.includes(unit.status)) {
            errors.push(`status must be one of: ${VALID_STATUSES.join(', ')}`);
        }
    }

    return { valid: errors.length === 0, errors };
}

// --- OrbatModel ---

export class OrbatModel {
    constructor() {
        /** @type {Object[]} */
        this._organisations = [];
    }

    /**
     * Add an organisation. Generates an id if missing.
     * @param {Object} org
     * @returns {Object} the added organisation
     */
    addOrganisation(org) {
        if (!org.id) {
            org.id = generateId('org');
        }
        if (!Array.isArray(org.units)) {
            org.units = [];
        }
        this._organisations.push(org);
        return org;
    }

    /**
     * Remove an organisation by id.
     * @param {string} orgId
     */
    removeOrganisation(orgId) {
        const idx = this._organisations.findIndex(o => o.id === orgId);
        if (idx !== -1) {
            this._organisations.splice(idx, 1);
        }
    }

    /**
     * Get an organisation by id.
     * @param {string} orgId
     * @returns {Object|undefined}
     */
    getOrganisation(orgId) {
        return this._organisations.find(o => o.id === orgId);
    }

    /**
     * Get all organisations.
     * @returns {Object[]}
     */
    getOrganisations() {
        return [...this._organisations];
    }

    /**
     * Add a unit to an organisation. Generates an id if missing.
     * @param {string} orgId
     * @param {Object} unit
     * @returns {Object} the added unit
     * @throws {Error} if organisation not found
     */
    addUnit(orgId, unit) {
        const org = this.getOrganisation(orgId);
        if (!org) {
            throw new Error(`Organisation not found: ${orgId}`);
        }
        if (!unit.id) {
            unit.id = generateId('unit');
        }
        // Apply defaults for optional array/object fields
        if (!Array.isArray(unit.sensors)) {
            unit.sensors = [];
        }
        if (!Array.isArray(unit.weapons)) {
            unit.weapons = [];
        }
        if (unit.metadata === undefined || unit.metadata === null) {
            unit.metadata = {};
        }
        if (unit.status === undefined) {
            unit.status = 'OPERATIONAL';
        }
        org.units.push(unit);
        return unit;
    }

    /**
     * Remove a unit from an organisation.
     * @param {string} orgId
     * @param {string} unitId
     */
    removeUnit(orgId, unitId) {
        const org = this.getOrganisation(orgId);
        if (!org) return;
        const idx = org.units.findIndex(u => u.id === unitId);
        if (idx !== -1) {
            org.units.splice(idx, 1);
        }
    }

    /**
     * Find a unit by id across all organisations.
     * @param {string} unitId
     * @returns {Object|undefined}
     */
    getUnit(unitId) {
        for (const org of this._organisations) {
            const unit = org.units.find(u => u.id === unitId);
            if (unit) return unit;
        }
        return undefined;
    }

    /**
     * Get a flat array of all units from all organisations.
     * @returns {Object[]}
     */
    getAllUnits() {
        const units = [];
        for (const org of this._organisations) {
            units.push(...org.units);
        }
        return units;
    }

    /**
     * Filter units by agency.
     * @param {string} agency
     * @returns {Object[]}
     */
    findUnitsByAgency(agency) {
        return this.getAllUnits().filter(u => u.agency === agency);
    }

    /**
     * Filter units by domain.
     * @param {string} domain
     * @returns {Object[]}
     */
    findUnitsByDomain(domain) {
        return this.getAllUnits().filter(u => u.domain === domain);
    }

    /**
     * Filter units by entity type.
     * @param {string} entityType
     * @returns {Object[]}
     */
    findUnitsByType(entityType) {
        return this.getAllUnits().filter(u => u.entity_type === entityType);
    }

    /**
     * Search units by callsign, id, or entity_type (case-insensitive).
     * @param {string} query
     * @returns {Object[]}
     */
    searchUnits(query) {
        const q = query.toLowerCase();
        return this.getAllUnits().filter(u => {
            const callsign = (u.callsign || u.name || '').toLowerCase();
            const id = (u.id || '').toLowerCase();
            const type = (u.entity_type || '').toLowerCase();
            return callsign.includes(q) || id.includes(q) || type.includes(q);
        });
    }

    /**
     * Serialize the entire ORBAT to a plain JSON-serializable object.
     * @returns {Object}
     */
    toJSON() {
        return {
            organisations: this._organisations.map(org => ({
                ...org,
                units: org.units.map(u => ({ ...u }))
            }))
        };
    }

    /**
     * Deserialize an ORBAT from a plain object.
     * @param {Object} data
     * @returns {OrbatModel}
     */
    static fromJSON(data) {
        const model = new OrbatModel();
        if (data && Array.isArray(data.organisations)) {
            for (const orgData of data.organisations) {
                const units = orgData.units || [];
                const org = { ...orgData, units: [] };
                model._organisations.push(org);
                for (const unitData of units) {
                    org.units.push({ ...unitData });
                }
            }
        }
        return model;
    }

    /**
     * Create a deep copy of this ORBAT.
     * @returns {OrbatModel}
     */
    clone() {
        return OrbatModel.fromJSON(JSON.parse(JSON.stringify(this.toJSON())));
    }
}
