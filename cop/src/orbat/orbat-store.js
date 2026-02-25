/**
 * ORBAT Store — persistence layer for ORBAT data.
 *
 * Manages ORBAT persistence via localStorage and JSON file I/O.
 * Falls back to the default ORBAT (extracted from scenario files) on first load.
 */

import { OrbatModel } from './orbat-model.js';
import defaultOrbatData from '../data/default-orbat.json';

const STORAGE_KEY = 'edge_c2_orbats';

/**
 * Internal storage schema (localStorage):
 * {
 *   "version": 1,
 *   "orbats": {
 *     "Malaysian ESSZONE Forces": {
 *       "name": "Malaysian ESSZONE Forces",
 *       "created": "...",
 *       "modified": "...",
 *       "organisations": [...]
 *     }
 *   }
 * }
 */

export class OrbatStore {
    constructor() {
        /** @type {{ version: number, orbats: Object.<string, Object> }} */
        this._store = null;
        this._load();
    }

    /**
     * Load store from localStorage, or initialize with default ORBAT.
     * @private
     */
    _load() {
        try {
            const raw = localStorage.getItem(STORAGE_KEY);
            if (raw) {
                const parsed = JSON.parse(raw);
                if (parsed && parsed.version === 1 && parsed.orbats) {
                    this._store = parsed;
                    return;
                }
            }
        } catch (e) {
            console.warn('OrbatStore: failed to load from localStorage, initializing with default', e);
        }

        // First load — initialize with default ORBAT
        this._store = {
            version: 1,
            orbats: {}
        };

        const defaultName = defaultOrbatData.name || 'Malaysian ESSZONE Forces';
        this._store.orbats[defaultName] = {
            name: defaultName,
            created: defaultOrbatData.created || new Date().toISOString(),
            modified: defaultOrbatData.modified || new Date().toISOString(),
            organisations: defaultOrbatData.organisations || []
        };

        this._persist();
    }

    /**
     * Write current store state to localStorage.
     * @private
     */
    _persist() {
        try {
            localStorage.setItem(STORAGE_KEY, JSON.stringify(this._store));
        } catch (e) {
            console.error('OrbatStore: failed to persist to localStorage', e);
        }
    }

    /**
     * Get list of all stored ORBATs.
     * @returns {{ name: string, created: string, modified: string }[]}
     */
    getOrbatList() {
        return Object.values(this._store.orbats).map(orbat => ({
            name: orbat.name,
            created: orbat.created,
            modified: orbat.modified
        }));
    }

    /**
     * Load an ORBAT by name.
     * @param {string} name
     * @returns {OrbatModel|null} OrbatModel instance, or null if not found
     */
    loadOrbat(name) {
        const data = this._store.orbats[name];
        if (!data) {
            return null;
        }
        return OrbatModel.fromJSON(data);
    }

    /**
     * Save an ORBAT by name with updated modified timestamp.
     * @param {string} name
     * @param {OrbatModel} orbatModel
     */
    saveOrbat(name, orbatModel) {
        const serialized = orbatModel.toJSON();
        const existing = this._store.orbats[name];

        this._store.orbats[name] = {
            name,
            created: existing ? existing.created : new Date().toISOString(),
            modified: new Date().toISOString(),
            organisations: serialized.organisations
        };

        this._persist();
    }

    /**
     * Delete an ORBAT by name.
     * @param {string} name
     * @returns {boolean} true if deleted, false if not found
     */
    deleteOrbat(name) {
        if (!this._store.orbats[name]) {
            return false;
        }
        delete this._store.orbats[name];
        this._persist();
        return true;
    }

    /**
     * Rename an ORBAT.
     * @param {string} oldName
     * @param {string} newName
     * @returns {boolean} true if renamed, false if oldName not found or newName already exists
     */
    renameOrbat(oldName, newName) {
        if (!this._store.orbats[oldName]) {
            return false;
        }
        if (oldName === newName) {
            return true;
        }
        if (this._store.orbats[newName]) {
            return false;
        }

        const orbat = this._store.orbats[oldName];
        orbat.name = newName;
        orbat.modified = new Date().toISOString();
        this._store.orbats[newName] = orbat;
        delete this._store.orbats[oldName];

        this._persist();
        return true;
    }

    /**
     * Export an ORBAT as a JSON string suitable for file download.
     * @param {string} name
     * @returns {string|null} JSON string, or null if not found
     */
    exportToJSON(name) {
        const data = this._store.orbats[name];
        if (!data) {
            return null;
        }
        return JSON.stringify({
            version: 1,
            name: data.name,
            created: data.created,
            modified: data.modified,
            organisations: data.organisations
        }, null, 2);
    }

    /**
     * Import an ORBAT from a JSON string and add to the store.
     * @param {string} jsonString
     * @returns {string} the name of the imported ORBAT
     * @throws {Error} if JSON is invalid or missing required fields
     */
    importFromJSON(jsonString) {
        let parsed;
        try {
            parsed = JSON.parse(jsonString);
        } catch (e) {
            throw new Error(`Invalid JSON: ${e.message}`);
        }

        if (!parsed || !Array.isArray(parsed.organisations)) {
            throw new Error('Invalid ORBAT format: missing organisations array');
        }

        let name = parsed.name || 'Imported ORBAT';

        // Deduplicate name if it already exists
        if (this._store.orbats[name]) {
            let counter = 2;
            while (this._store.orbats[`${name} (${counter})`]) {
                counter++;
            }
            name = `${name} (${counter})`;
        }

        this._store.orbats[name] = {
            name,
            created: parsed.created || new Date().toISOString(),
            modified: new Date().toISOString(),
            organisations: parsed.organisations
        };

        this._persist();
        return name;
    }

    /**
     * Get the default ORBAT as an OrbatModel (from the bundled JSON file).
     * This always returns a fresh instance from the static default data,
     * regardless of what is in localStorage.
     * @returns {OrbatModel}
     */
    getDefaultOrbat() {
        return OrbatModel.fromJSON(defaultOrbatData);
    }
}
