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
      // ===== MARITIME (Symbol Set 30 = Sea Surface) =====
      'MMEA_PATROL':          '10033000001204020000',  // friend patrol boat
      'MMEA_FAST_INTERCEPT':  '10033000001204010000',  // friend patrol coastal
      'MIL_NAVAL':            '10033000001201030000',  // friend corvette
      'SUSPECT_VESSEL':       '10053000001400000000',  // suspect civilian vessel
      'HOSTILE_VESSEL':       '10063000001400000000',  // hostile civilian vessel
      'CIVILIAN_CARGO':       '10043000001401010000',  // neutral cargo
      'CIVILIAN_FISHING':     '10043000001402000000',  // neutral fishing
      'CIVILIAN_TANKER':      '10043000001401020000',  // neutral tanker
      'CIVILIAN_PASSENGER':   '10043000001401030000',  // neutral passenger
      'CIVILIAN_BOAT':        '10043000001400000000',  // neutral generic civilian vessel
      'RMP_PATROL_CAR':       '10033000001204020000',  // friend patrol boat (RMP Marine Police)

      // ===== AIR (Symbol Set 01 = Air) =====
      'RMAF_FIGHTER':         '10030100001101020000',  // friend fighter
      'RMAF_HELICOPTER':      '10030100001102000000',  // friend rotary wing
      'RMAF_TRANSPORT':       '10030100001101060000',  // friend cargo/transport
      'RMP_HELICOPTER':       '10030100001102030000',  // friend utility helicopter
      'CIVILIAN_COMMERCIAL':  '10040100001200000000',  // neutral civilian air
      'CIVILIAN_LIGHT':       '10040100001201000000',  // neutral civilian fixed wing

      // ===== GROUND UNITS (Symbol Set 10 = Land Unit) =====
      'RMP_TACTICAL_TEAM':    '10031000001211000000',  // friend special operations forces
      'MIL_INFANTRY_SQUAD':   '10031000001201000000',  // friend infantry
      'CI_OFFICER':           '10031000001400000000',  // friend law enforcement
      'CI_IMMIGRATION_TEAM':  '10031000001400000000',  // friend law enforcement
      'RMP_OFFICER':          '10031000001400000000',  // friend law enforcement
      'HOSTILE_PERSONNEL':    '10061000001201000000',  // hostile infantry
      'CIVILIAN_TOURIST':     '10041000001100000000',  // neutral civilian

      // ===== GROUND EQUIPMENT (Symbol Set 15 = Land Equipment) =====
      'MIL_APC':              '10031500001201010000',  // friend APC
      'MIL_VEHICLE':          '10031500001202000000'   // friend wheeled vehicle
    },

    defaultSidc: '10033000001100000000',

    speeds: [1, 2, 5, 10, 60]
  };
}
