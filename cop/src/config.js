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

    // SIDC codes verified against JMSML Sea_Surface.xml, Air.xml, Land_Unit.xml, Land_Equipment.xml
    // Graphic filename encodes Symbol Set (2) + Entity (2) + Type (2) + Subtype (2)
    // SIDC positions: 1-2=Version, 3=Context, 4=Identity, 5-6=SymbolSet, 7=Status,
    //   8=HQ/TF, 9-10=Echelon, 11-12=Entity, 13-14=Type, 15-16=Subtype, 17-18=Mod1, 19-20=Mod2
    sidcMap: {
      // ===== MARITIME (Symbol Set 30 — Sea Surface) =====
      // JMSML graphic filenames: 30EETTSS.svg
      'MMEA_PATROL':          '10033000001205020000',  // 30120502 = Patrol Boat > Patrol Ship, General
      'MMEA_FAST_INTERCEPT':  '10033000001205010000',  // 30120501 = Patrol Boat > Patrol Craft
      'MIL_NAVAL':            '10033000001202000000',  // 30120200 = Surface Combatant, Line (generic)
      'MIL_NAVAL_FIC':        '10033000001205000009',  // 30120500 = Patrol Boat + Mod2=09(Fast)
      'SUSPECT_VESSEL':       '10053000001400000000',  // 30140000 = Civilian (suspect identity)
      'HOSTILE_VESSEL':       '10063000001400000000',  // 30140000 = Civilian (hostile identity)
      'CIVILIAN_CARGO':       '10043000001401010000',  // 30140101 = Merchant > Cargo, General
      'CIVILIAN_FISHING':     '10043000001402000000',  // 30140200 = Fishing Vessel
      'CIVILIAN_TANKER':      '10043000001401090000',  // 30140109 = Merchant > Oiler/Tanker
      'CIVILIAN_PASSENGER':   '10043000001401100000',  // 30140110 = Merchant > Passenger
      'CIVILIAN_BOAT':        '10043000001400000000',  // 30140000 = Civilian (generic)
      'RMP_PATROL_CAR':       '10033000001403000000',  // 30140300 = Law Enforcement Vessel

      // ===== AIR (Symbol Set 01) =====
      // JMSML graphic filenames: 01EETTSS.svg
      'RMAF_FIGHTER':         '10030100001101040000',  // 01110104 = Military > Fixed-Wing > Fighter
      'RMAF_HELICOPTER':      '10030100001102000000',  // 01110200 = Military > Rotary-Wing
      'RMAF_TRANSPORT':       '10030100001101070000',  // 01110107 = Military > Fixed-Wing > Cargo
      'RMAF_MPA':             '10030100001101100000',  // 01110110 = Military > Fixed-Wing > Patrol
      'RMP_HELICOPTER':       '10030100001102000000',  // 01110200 = Military > Rotary-Wing
      'CIVILIAN_COMMERCIAL':  '10040100001200000000',  // 01120000 = Civilian (generic)
      'CIVILIAN_LIGHT':       '10040100001201000000',  // 01120100 = Civilian > Fixed Wing

      // ===== GROUND UNITS (Symbol Set 10 — Land Unit) =====
      // JMSML graphic filenames: 10EETTSS.svg
      'RMP_TACTICAL_TEAM':    '10031000001218000000',  // 10121800 = Special Operations Forces (SOF)
      'MIL_INFANTRY_SQUAD':   '10031000001211000000',  // 10121100 = Infantry
      'RMP_OFFICER':          '10031000001400000000',  // 10140000 = Law Enforcement
      'HOSTILE_PERSONNEL':    '10061000001211000000',  // 10121100 = Infantry (hostile identity)
      'CIVILIAN_TOURIST':     '10041000001100000000',  // 10110000 = Civilian

      // ===== GROUND EQUIPMENT (Symbol Set 15 — Land Equipment) =====
      // JMSML graphic filenames: 15EETTSS.svg
      'MIL_APC':              '10031500001201010000',  // 15120101 = Armored Vehicle > APC
      'MIL_VEHICLE':          '10031500001201000000',  // 15120100 = Armored Vehicle (generic)
      'CI_OFFICER':           '10031500001703000000',  // 15170300 = Law Enforcement > Customs Service
      'CI_IMMIGRATION_TEAM':  '10031500001703000000',  // 15170300 = Law Enforcement > Customs Service
    },

    defaultSidc: '10033000001202000000',  // Friend, Sea Surface, Surface Combatant Line

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
