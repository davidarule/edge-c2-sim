/**
 * Application configuration — agency colors, SIDC mappings, defaults.
 */

export function initConfig() {
  return {
    cesiumToken: import.meta.env.VITE_CESIUM_ION_TOKEN || '',
    wsUrl: import.meta.env.VITE_WS_URL || 'ws://localhost:8765',
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

    sidcMap: {
      // ===== MARITIME (Symbol Set 30) =====
      'MMEA_PATROL':          '10033000001204020000',  // Patrol Coastal, Station Ship
      'MMEA_FAST_INTERCEPT':  '10033000001204010000',  // Patrol Coastal, Patrol Craft
      'MIL_NAVAL':            '10033000001201000000',  // Combatant Line generic
      'MIL_NAVAL_FIC':        '10033000001204010000',  // Patrol Coastal (G2000 Fast Interceptor Craft)
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
      'RMAF_MPA':             '10030100001101040000',  // Fixed Wing, Patrol (Beechcraft MPA)
      'RMP_HELICOPTER':       '10030100001102000000',  // Rotary Wing
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
      'CI_OFFICER':           '10031500001703000000',  // LE Customs Service
      'CI_IMMIGRATION_TEAM':  '10031500001703000000',  // LE Customs Service
    },

    defaultSidc: '10033000001100000000',

    speeds: [1, 2, 5, 10, 60]
  };
}
