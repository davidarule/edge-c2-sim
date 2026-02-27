/**
 * Application configuration — agency colors, SIDC mappings, defaults.
 */

/**
 * Determine WebSocket URL based on current page location.
 *
 * In production (served through Nginx proxy):
 *   wss://ec2sim.brumbiesoft.org/ws
 *
 * In development (direct connection):
 *   ws://localhost:8765
 */
function getWebSocketUrl() {
  if (window.location.protocol === 'https:') {
    return `wss://${window.location.host}/ws`;
  }
  // Fall back to env variable or default for dev
  return import.meta.env.VITE_WS_URL || 'ws://localhost:8765';
}

export function initConfig() {
  const config = {
    cesiumToken: import.meta.env.VITE_CESIUM_ION_TOKEN || '',
    wsUrl: getWebSocketUrl(),
    defaultSpeed: parseInt(import.meta.env.VITE_SIM_DEFAULT_SPEED || '1', 10),

    initialCenter: { lat: 5.00, lon: 118.50 },
    initialAltitude: 300000,

    agencyColors: {
      RMP:      '#1B3A8C',
      MMEA:     '#FF6600',
      CI:       '#2E7D32',
      RMAF:     '#5C6BC0',
      MIL:      '#4E342E',
      CIVILIAN: '#78909C',
      UNKNOWN:  '#78909C'
    },

    agencyLabels: {
      RMP:      'Royal Malaysia Police',
      MMEA:     'Maritime Enforcement',
      CI:       'Customs & Immigration',
      RMAF:     'Air Force',
      MIL:      'Military',
      CIVILIAN: 'Civilian'
    },

    domainLabels: {
      MARITIME:       'Maritime',
      AIR:            'Air',
      GROUND_VEHICLE: 'Ground',
      PERSONNEL:      'Personnel'
    },

    domainIcons: {
      MARITIME:       '\u2693',
      AIR:            '\u2708',
      GROUND_VEHICLE: '\u{1F697}',
      PERSONNEL:      '\u{1F464}'
    },

    statusColors: {
      ACTIVE:        '#3FB950',
      INTERCEPTING:  '#F85149',
      RESPONDING:    '#D29922',
      IDLE:          '#8B949E',
      RTB:           '#58A6FF',
      STOPPED:       '#F85149'
    },

    // SIDC codes using DISA JMSML SVGs (MIL-STD-2525D)
    // Positions: 1-2=Version, 3=Context, 4=Identity, 5-6=SymbolSet, 7=Status,
    //   8=HQ/TF, 9-10=Echelon, 11-16=Entity/Type/Subtype, 17-18=Mod1, 19-20=Mod2
    sidcMap: {
      // ===== MARITIME (Symbol Set 30 — Sea Surface) =====
      'MMEA_PATROL':          '10033000001204020000',  // Patrol Coastal, Station Ship
      'MMEA_FAST_INTERCEPT':  '10033000001204010000',  // Patrol Coastal, Patrol Craft
      'MIL_NAVAL':            '10033000001202060000',  // Combatant, Cruiser (30120206.svg)
      'MIL_NAVAL_FIC':        '10033000001204010000',  // Patrol Coastal, Patrol Craft
      'SUSPECT_VESSEL':       '10053000001400000000',  // Suspect, Non-Military
      'HOSTILE_VESSEL':       '10063000001400000000',  // Hostile, Non-Military
      'CIVILIAN_CARGO':       '10043000001401010000',  // Neutral, Merchant, Cargo
      'CIVILIAN_FISHING':     '10043000001402000000',  // Neutral, Fishing
      'CIVILIAN_TANKER':      '10043000001401020000',  // Neutral, Merchant, Tanker
      'CIVILIAN_PASSENGER':   '10043000001401030000',  // Neutral, Merchant, Passenger
      'CIVILIAN_BOAT':        '10043000001400000000',  // Neutral, Non-Military generic
      'RMP_PATROL_CAR':       '10031500001707000000',  // Land Equipment, LE Police
      'RMP_PATROL_BOAT':      '10033000001403000000',  // Law Enforcement Vessel
      'RMP_MARINE_PATROL':    '10033000001403000000',  // Law Enforcement Vessel (Marine Police)

      // ===== AIR (Symbol Set 01) =====
      'RMAF_FIGHTER':         '10030100001101020000',  // Fixed Wing, Fighter/Bomber
      'RMAF_HELICOPTER':      '10030100001102000000',  // Rotary Wing
      'RMAF_TRANSPORT':       '10030100001101310303',  // Fixed Wing, Passenger + C + L modifiers
      'RMAF_MPA':             '10030100001101040000',  // Fixed Wing, Patrol
      'RMP_HELICOPTER':       '10030100001102000000',  // Rotary Wing
      'CIVILIAN_COMMERCIAL':  '10040100001200000000',  // Neutral, Civilian generic
      'CIVILIAN_LIGHT':       '10040100001201000000',  // Neutral, Civilian, Fixed Wing

      // ===== GROUND UNITS (Symbol Set 10 — Land Unit) =====
      'RMP_TACTICAL_TEAM':    '10031000001211000000',  // SOF (full-frame icon)
      'MIL_INFANTRY_SQUAD':   '10031000001201000000',  // Infantry (full-frame icon)
      'RMP_OFFICER':          '10031000001401000000',  // Law Enforcement, Police
      'HOSTILE_PERSONNEL':    '10061000001201000000',  // Hostile, Infantry (full-frame)
      'CIVILIAN_TOURIST':     '10041000001100000000',  // Neutral, Civilian

      // ===== GROUND EQUIPMENT (Symbol Set 15 — Land Equipment) =====
      'MIL_APC':              '10031500001201010000',  // APC
      'MIL_VEHICLE':          '10031500001202000000',  // Vehicle generic
      'CI_OFFICER':           '10031500001703000000',  // LE Customs Service
      'CI_IMMIGRATION_TEAM':  '10031500001703000000',  // LE Customs Service
    },

    defaultSidc: '10033000001100000000',  // Sea Surface, Military generic

    speeds: [1, 2, 5, 10, 60]
  };

  // Load SIDC overrides from localStorage (saved by operator edits)
  try {
    const saved = localStorage.getItem('sidc_overrides');
    if (saved) {
      const overrides = JSON.parse(saved);
      Object.assign(config.sidcMap, overrides);
      console.log(`Loaded ${Object.keys(overrides).length} SIDC overrides from localStorage`);
    }
  } catch (e) { /* ignore */ }

  return config;
}
