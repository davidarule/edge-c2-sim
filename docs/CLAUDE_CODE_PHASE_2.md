# Claude Code — Phase 2 Task Brief: Domain Simulators

## Context

Phase 1 gave us the movement engine (waypoint, patrol, intercept, noise), 
scenario loader, and event engine. Phase 2 builds domain-specific simulators 
that add realistic behavior on top of the movement primitives.

After Phase 2, each domain (maritime, aviation, ground vehicle, personnel) 
will generate entities that behave like their real-world counterparts — ships 
follow shipping lanes, aircraft climb and descend properly, vehicles drive at 
road-appropriate speeds, and personnel move in formations.

**Key principle:** Domain simulators are THIN WRAPPERS around the movement 
engine. They don't reinvent movement — they configure it with domain-appropriate 
parameters and generate domain-specific signal data (AIS, ADS-B).

---

## Task 1: Maritime Simulator (`simulator/domains/maritime.py`)

```python
"""
Maritime domain simulator.

Manages all maritime entities (ships, boats, vessels). Adds maritime-specific
behavior on top of the base movement engine: AIS message generation, TSS lane
following, vessel traffic patterns, and suspect vessel dark-running behavior.
"""

class MaritimeSimulator:
    def __init__(self, entity_store: EntityStore, clock: SimulationClock):
        pass
    
    def tick(self, sim_time: datetime):
        """
        Called each simulation tick for all maritime entities.
        1. (Movement already handled by main loop)
        2. Generate AIS messages for AIS-active vessels
        3. Update maritime-specific metadata (nav_status, etc.)
        4. Handle AIS on/off transitions
        """
    
    def generate_ais_for_entity(self, entity: Entity) -> list[str]:
        """
        Generate AIS NMEA sentences for this entity's current state.
        Returns list of NMEA strings.
        Only generates if entity.metadata.ais_active == True.
        """
```

### Maritime behavior rules:

1. **AIS generation rates** (per IMO requirements):
   - Ships at anchor or moored: every 3 minutes
   - Ships 0-14 knots: every 10 seconds
   - Ships 14-23 knots: every 6 seconds
   - Ships >23 knots: every 2 seconds
   - Ships changing course: every 3.3 seconds
   - Track the last AIS send time per entity, only generate when interval elapsed

2. **AIS message types:**
   - Position report (Type 1/2/3): every update cycle
   - Static/voyage data (Type 5): once on entity creation, then every 6 minutes
   - Use `pyais` library for NMEA encoding

3. **Navigation status** (AIS field, update based on entity behavior):
   - 0 = Under way using engine (moving entities)
   - 1 = At anchor (stationary patrol vessels on dwell)
   - 5 = Moored (entities at port)
   - 7 = Engaged in fishing (fishing vessels with speed <3 kts)
   - 8 = Under way sailing (not used)
   - 15 = Not defined (suspect vessels, AIS off)

4. **Dark targets** — When `ais_active: false`, generate NO AIS messages. The 
   entity still moves (radar can still detect it) but produces no AIS signal. 
   This is the key detection trigger in the IUU scenario.

5. **Metadata updates each tick:**
   ```python
   entity.metadata["nav_status"] = calculate_nav_status(entity)
   entity.metadata["last_ais_time"] = sim_time if ais_active else None
   ```

### Tests:

- AIS messages generated at correct intervals for different speeds
- No AIS generated when ais_active=false
- Nav status reflects entity behavior
- AIS Type 5 generated on creation

---

## Task 2: AIS Encoder (`simulator/signals/ais_encoder.py`)

```python
"""
AIS NMEA sentence generator.

Converts entity state into properly formatted AIS NMEA sentences
using the pyais library. Generates both position reports (Type 1/2/3)
and static data (Type 5).
"""

class AISEncoder:
    def encode_position_report(self, entity: Entity) -> str:
        """
        Generate AIS Type 1/2/3 position report NMEA sentence.
        
        Maps entity fields to AIS fields:
        - MMSI: entity.metadata["mmsi"]
        - Latitude: entity.position.latitude
        - Longitude: entity.position.longitude
        - SOG: entity.speed_knots * 10 (AIS uses 1/10 knot)
        - COG: entity.course_deg * 10 (AIS uses 1/10 degree)
        - True heading: entity.heading_deg
        - Navigation status: entity.metadata["nav_status"]
        - Rate of turn: 0 (or calculate from heading change rate)
        - Timestamp: seconds of UTC minute from entity.timestamp
        """
    
    def encode_static_data(self, entity: Entity) -> str:
        """
        Generate AIS Type 5 static and voyage data.
        
        Fields:
        - MMSI, IMO number, callsign
        - Vessel name, vessel type
        - Ship dimensions (generic defaults by type)
        - Draught
        - Destination, ETA
        """
    
    @staticmethod
    def generate_mmsi(entity_id: str, flag: str = "MYS") -> str:
        """
        Generate a plausible MMSI for an entity.
        Malaysia MID: 533
        Format: 533XXXXXX (9 digits)
        For foreign vessels: appropriate country MID
        Vietnam: 574
        Philippines: 548
        """
```

### Implementation notes:

- **pyais usage:** The `pyais` library is primarily for DECODING. For ENCODING, 
  you may need to construct the binary message payload manually and wrap it in 
  NMEA framing. Check if `pyais` has an encoding API. If not, implement the 
  bit-packing per ITU-R M.1371 specification:
  
  ```
  AIS Type 1 payload (168 bits):
  - Message type: 6 bits (1)
  - Repeat indicator: 2 bits (0)
  - MMSI: 30 bits
  - Nav status: 4 bits
  - Rate of turn: 8 bits
  - SOG: 10 bits (1/10 knot, 0-102.2)
  - Position accuracy: 1 bit
  - Longitude: 28 bits (1/10000 min, ±180°)
  - Latitude: 27 bits (1/10000 min, ±90°)
  - COG: 12 bits (1/10 degree)
  - True heading: 9 bits
  - Timestamp: 6 bits (second of UTC minute)
  - Maneuver indicator: 2 bits
  - Spare: 3 bits
  - RAIM: 1 bit
  - Communication state: 19 bits
  ```
  
  Wrap in NMEA: `!AIVDM,1,1,,A,<payload_armored>,0*<checksum>`

- **If pyais encoding proves too complex**, create a simplified AIS output that 
  produces a JSON-format "decoded AIS" message instead. The REST adapter can 
  send this to Edge C2 regardless. The NMEA encoding is a nice-to-have for 
  TAK integration but not critical.

### Tests:

- Position report encodes correct MMSI, position, speed
- Static data encodes vessel name and type
- MMSI generation produces valid 9-digit numbers with correct MID
- Round-trip: encode → decode (using pyais decode) → verify fields match

---

## Task 3: Aviation Simulator (`simulator/domains/aviation.py`)

```python
"""
Aviation domain simulator.

Manages aircraft entities with realistic flight profiles: takeoff,
climb, cruise, descent, and landing phases. Military aircraft can
scramble (rapid departure) and fly tactical profiles.
"""

class AviationSimulator:
    def __init__(self, entity_store: EntityStore, clock: SimulationClock):
        pass
    
    def tick(self, sim_time: datetime):
        """
        Called each tick for aviation entities.
        1. Update flight phase (climb/cruise/descend)
        2. Generate ADS-B messages if adsb_active
        3. Update aviation metadata (altitude, vertical rate, etc.)
        """
```

### Flight phase management:

Rather than manually coding altitude curves, use the waypoint system with 
altitude as a waypoint property. The aviation simulator's job is to add 
realistic vertical rates and speed profiles:

1. **Takeoff/Climb:**
   - Speed increases from 0 to climb speed over first 2 minutes
   - Altitude increases at type-appropriate climb rate:
     - Commercial: 1500-2500 fpm
     - Fighter: 5000-15000 fpm (scramble: 20000+ fpm)
     - Helicopter: 500-1500 fpm
     - Transport: 1000-2000 fpm
   - Entity starts `on_ground: true`, transitions to `on_ground: false`

2. **Cruise:**
   - Level flight at assigned altitude
   - Constant speed (within noise)
   - Vertical rate: ~0 fpm (slight oscillation OK)

3. **Descent:**
   - Speed decreases
   - Altitude decreases at 1000-2000 fpm (commercial), faster for military
   - Transitions to `on_ground: true` at end

4. **Helicopter hover:**
   - Speed can be 0
   - Altitude maintained
   - Position may drift slightly (realistic station-keeping)

5. **Scramble** (military, triggered by ORDER event):
   - Near-instant transition from standby to airborne
   - Maximum climb rate for type
   - Maximum speed to intercept area
   - Entity status: IDLE → RESPONDING

### ADS-B generation:

Only for aircraft with `adsb_active: true`. Military aircraft may not broadcast.

```python
def generate_adsb(self, entity: Entity) -> dict:
    """
    Generate SBS-format ADS-B message.
    
    SBS Message Types:
    MSG,1: ES Identification and Category
    MSG,3: ES Airborne Position
    MSG,4: ES Airborne Velocity
    
    Returns dict that can be serialized for Edge C2 /signals/adsb endpoint.
    """
```

### Tests:

- Aircraft at rest: on_ground=true, altitude=field_elevation
- Takeoff sequence: altitude increases, speed increases
- Cruise: altitude stable, speed stable
- Descent: altitude decreases
- Scramble: rapid climb rate for fighters
- Helicopter: can hover (speed=0, altitude maintained)
- No ADS-B when adsb_active=false

---

## Task 4: ADS-B Encoder (`simulator/signals/adsb_encoder.py`)

```python
"""
ADS-B message generator in SBS (BaseStation) format.

Generates SBS-format messages that match what a real ADS-B receiver
would output. This is the standard format for FlightRadar24, dump1090,
and most aviation tracking software.
"""

class ADSBEncoder:
    def encode_identification(self, entity: Entity) -> str:
        """
        SBS MSG Type 1 — Aircraft identification
        MSG,1,1,1,{icao},{id},{date},{time},{date},{time},{callsign},,,,,,,,,,
        """
    
    def encode_position(self, entity: Entity) -> str:
        """
        SBS MSG Type 3 — Airborne position
        MSG,3,1,1,{icao},{id},{date},{time},{date},{time},,{alt},,,{lat},{lon},,,,,,{is_ground}
        """
    
    def encode_velocity(self, entity: Entity) -> str:
        """
        SBS MSG Type 4 — Airborne velocity
        MSG,4,1,1,{icao},{id},{date},{time},{date},{time},,{speed},,{heading},,,{vrate},,,,
        """
    
    @staticmethod
    def generate_icao_hex(entity_id: str, country: str = "MYS") -> str:
        """
        Generate plausible ICAO 24-bit hex address.
        Malaysia: 750000-75FFFF range
        Deterministic from entity_id (same entity always gets same ICAO).
        """
    
    @staticmethod
    def generate_squawk(entity_type: str) -> str:
        """
        Generate appropriate transponder squawk code.
        - Civilian: 1200 (VFR) or assigned code
        - Military: typically 0000 or mil-specific
        - Emergency: 7700
        - Hijack: 7500
        """
```

### Tests:

- SBS format strings parseable by standard ADS-B decoders
- Position message contains correct lat/lon/altitude
- Velocity message contains correct speed/heading/vertical rate
- ICAO hex is deterministic (same entity → same ICAO)

---

## Task 5: Ground Vehicle Simulator (`simulator/domains/ground_vehicle.py`)

```python
"""
Ground vehicle domain simulator.

Manages vehicle entities. In Phase 2, vehicles follow waypoint routes
(road-aware routing is deferred to later enhancement). Emergency 
vehicles travel at higher speeds. Convoys maintain spacing.
"""

class GroundVehicleSimulator:
    def __init__(self, entity_store: EntityStore, clock: SimulationClock):
        pass
    
    def tick(self, sim_time: datetime):
        """
        1. (Movement handled by main loop)
        2. Update vehicle metadata (speed in km/h for display)
        3. Handle convoy spacing if multiple vehicles share a route
        """
```

### Vehicle behavior:

1. **Speed units** — Entity base uses knots. Ground vehicles are more naturally 
   km/h. Store speed_knots internally but also populate 
   `entity.metadata["speed_kmh"]` for display. Conversion: `kts * 1.852 = km/h`

2. **Emergency response** — When entity receives ORDER/deploy, speed increases 
   to 90% of type maximum (with speed variation).

3. **Convoy behavior** — When multiple vehicles have the same destination (e.g., 
   a military QRF with APC + infantry), maintain ~200m spacing on the route. 
   Simple implementation: second vehicle follows first with a time delay.

4. **Altitude** — Always 0 (ground level). Could be terrain-following with 
   elevation data in the future, but not for Phase 2.

### Tests:

- Vehicle speed within type limits
- Emergency response increases speed
- Speed displayed in both knots (base) and km/h (metadata)

---

## Task 6: Personnel Simulator (`simulator/domains/personnel.py`)

```python
"""
Personnel domain simulator.

Manages troop/officer entities. Personnel move slowly (walking speed),
can form formations (patrol, checkpoint, cordon), and groups move as
a unit with slight position spread.
"""

class PersonnelSimulator:
    def __init__(self, entity_store: EntityStore, clock: SimulationClock):
        pass
    
    def tick(self, sim_time: datetime):
        """
        1. (Movement handled by main loop)
        2. Update formation-specific positions
        3. Handle unit_size spread (individuals within group)
        """
```

### Personnel behavior:

1. **Group spread** — A personnel entity represents a group (unit_size > 1). 
   The entity position is the group centroid. For display purposes, optionally 
   generate "spread positions" in metadata:
   ```python
   entity.metadata["member_positions"] = [
       {"lat": center_lat + offset_i, "lon": center_lon + offset_j}
       for each member
   ]
   ```
   Offset: random within 10-30m radius of centroid.

2. **Formation types:**
   - `patrol`: Moving, single file or wedge. Members spread ~5m apart along 
     movement axis.
   - `checkpoint`: Stationary. Members spread across a ~20m area.
   - `cordon`: Stationary ring. Members evenly spaced on a circle (~50m radius).
   - `standby`: Clustered tightly (~5m radius).

3. **Speed** — Walking: 3-5 km/h. Running: 6-8 km/h. Personnel don't exceed 
   ~8 km/h unless in a vehicle (linked entity).

4. **Status display** — `entity.metadata["formation"]` should always reflect 
   current formation type.

### Tests:

- Personnel speed within walking/running limits
- Formation spread generates member_positions within expected radius
- Cordon formation creates ring-shaped distribution
- Unit size matches member_positions count

---

## Task 7: Simulation Orchestrator Update

Update `scripts/run_simulator.py` to initialize and tick all domain simulators:

```python
# In main loop, after movement update:
maritime_sim.tick(sim_time)
aviation_sim.tick(sim_time)
ground_sim.tick(sim_time)
personnel_sim.tick(sim_time)
```

Each domain simulator should:
1. Filter entities by domain from entity_store
2. Generate domain-specific data (AIS, ADS-B, etc.)
3. Update domain-specific metadata

The domain simulators do NOT handle movement — that's the main loop's job 
via the movement engine.

---

## Task 8: Full Integration Test

`tests/integration/test_full_scenario.py`:

```python
"""
End-to-end scenario test.

Loads a complete scenario, runs it at 60x speed, and verifies:
1. All entities spawned correctly
2. Maritime entities generate AIS data
3. Aviation entities have correct flight profiles  
4. Events fire and change entity behavior
5. Intercepts are detected
6. Scenario completes without errors
"""

async def test_sulu_sea_fishing_intercept():
    """Run full IUU fishing scenario and verify outcomes."""
    
    # Load scenario
    loader = ScenarioLoader()
    state = loader.load("config/scenarios/sulu_sea_fishing_intercept.yaml")
    
    # Init components
    clock = SimulationClock(state.start_time, speed=60.0)
    store = EntityStore()
    # ... init all simulators ...
    
    # Capture all transport output
    output_capture = []
    console = ConsoleAdapter()  # Capture output
    
    # Run for scenario duration
    clock.start()
    # ... run loop for state.duration ...
    
    # Verify outcomes
    assert len(store.get_all_entities()) > 20  # scenario + background
    assert len(event_engine.get_fired_events()) == 17  # all events fired
    
    # Check specific scenario outcomes
    suspect = store.get_entity("IFF-001")
    assert suspect.speed_knots == 0  # Should be stopped after intercept
    
    mmea = store.get_entity("MMEA-PV-102")
    assert mmea.status in [EntityStatus.INTERCEPTING, EntityStatus.ACTIVE]
    
    # Maritime entities should have AIS data
    for e in store.get_entities_by_domain(Domain.MARITIME):
        if e.metadata.get("ais_active", True):
            assert "nav_status" in e.metadata
```

---

## Definition of Done

Phase 2 is complete when:

1. Both scenarios run to completion at 10x speed with all domain simulators active
2. Maritime entities generate AIS NMEA sentences (or structured AIS data)
3. Aviation entities have realistic altitude and speed profiles
4. Personnel entities display formation information
5. Domain simulator ticks don't crash with any entity state
6. Full integration test passes
7. Console output clearly shows multi-domain activity with AIS/ADSB data
8. All unit tests pass with >80% coverage on domain modules
