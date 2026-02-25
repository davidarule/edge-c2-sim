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
      'MMEA_PATROL':          '10033000001211040000',
      'MMEA_FAST_INTERCEPT':  '10033000001211040000',
      'MIL_NAVAL':            '10033000001211000000',
      'SUSPECT_VESSEL':       '10063000001211000000',
      'CIVILIAN_CARGO':       '10043000001213000000',
      'CIVILIAN_FISHING':     '10043000001215000000',
      'CIVILIAN_TANKER':      '10043000001214000000',
      'CIVILIAN_PASSENGER':   '10043000001213000000',
      'RMAF_FIGHTER':         '10031000001211040000',
      'RMAF_HELICOPTER':      '10031500001211000000',
      'RMAF_TRANSPORT':       '10031000001211050000',
      'RMP_HELICOPTER':       '10031500001211040000',
      'CIVILIAN_COMMERCIAL':  '10041000001213000000',
      'CIVILIAN_LIGHT':       '10041000001213000000',
      'RMP_PATROL_CAR':       '10031000001511040000',
      'RMP_TACTICAL_TEAM':    '10031000001511040000',
      'MIL_APC':              '10031000001512000000',
      'MIL_INFANTRY_SQUAD':   '10031000001211000000',
      'CI_OFFICER':           '10031000001511050000',
      'CI_IMMIGRATION_TEAM':  '10031000001511050000'
    },

    defaultSidc: '10030000001200000000',

    speeds: [1, 2, 5, 10, 60]
  };
}
