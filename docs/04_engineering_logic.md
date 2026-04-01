# Engineering Logic — System Design Agent

All rules below are executed in the `design_system()` tool. The LLM never
makes these decisions — it only passes parameters and formats the output.

---

## 1. Inverter Type Selection

### Terminology — CIR Definition

CIR uses two inverter types:

| CIR Term | What it means | Typical unit size |
|---|---|---|
| **String Inverters** | Distributed string inverters, mounted close to the array, short DC runs | 50–250 kW |
| **Central String Inverters** | Large string inverters mounted centrally (inverter station), longer DC cable runs from array to central point | 250–350 kW |

> "Central String Inverter" is NOT a traditional large central inverter (e.g. TMEIC 2500 kW).
> It is a high-capacity string inverter (e.g. Sungrow SG350HX, Huawei SUN2000-350KTL)
> deployed in a centralised inverter station. DC cables run from the array to the station.
> This is the standard CIR approach for utility-scale GM projects above 1 MWp.

### System Voltage

**Standard: 1500V DC system for ALL project types (GM, RT, CP).**

1500V DC enables:
- Longer string lengths (more panels per string → fewer strings → lower BOS cost)
- Typical string length at 1500V with 580W module: 26–30 panels per string
- Reduced DC combiner count
- Lower DC current → smaller cable cross-section → cable cost saving

### Decision Tree (CIR Flow)

```
Is installation type RT (Rooftop)?
  → String inverters, 1500V DC (always)
  → Reason: shading, roof segmentation, NEC requirements, safety

Is installation type CP (Carport)?
  → String inverters, 1500V DC (always)
  → Reason: distributed loads, partial shading, aesthetic requirements

Is installation type GM (Ground Mount)?
  → System voltage: 1500V DC
  → Apply size-based logic:

  DC size < 1 MWp
    → String inverters (distributed)
    → Reason: centralising at this scale adds cable cost with no benefit

  1 MWp ≤ DC size < 3 MWp
    → Distributed String inverters (default)
    → Reason: compact site, short AC runs outweigh DC cable savings at this scale
    → User can override to Central String; agent shows cost delta

  3 MWp ≤ DC size ≤ 5 MWp
    → Central String inverters (default)
    → Reason: AC cable savings and lower unit count begin to outweigh DC cable cost
    → User can override to distributed string; agent shows cost delta
    → Cable cost is a key factor here (see Cable Cost section below)

  DC size > 5 MWp
    → Central String inverters (CIR standard)
    → Reason: fewer units, centralised maintenance, better monitoring,
      lower $/Wp at scale despite longer DC cable runs

User preference override:
  → Apply always
  → If user requests distributed string on a >5 MWp GM project, add note:
    "Distributed string inverters will reduce DC cable runs but increase
     inverter unit count and AC wiring complexity at this scale"
```

### Cable Cost as a Decision Factor (1–5 MWp GM)

For projects in the 1–5 MWp range, the inverter type choice is partly
a cable cost trade-off:

| | Distributed String | Central String |
|---|---|---|
| DC cable runs | Short (inverter near array) | Long (array to central station) |
| AC cable runs | Long (many inverters → POI) | Short (few units → POI) |
| DC cable cost | Low | Higher (longer runs, larger cross-section) |
| AC cable cost | Higher (many long runs) | Lower |
| Inverter unit count | High | Low |
| Installed $/Wp inverter | Higher (more units) | Lower |

**Rule of thumb for 1–5 MWp decision:**
- If site is compact (RT-like, dense): distributed string saves DC cable
- If site is spread out (long string rows, large area): central string
  saves AC cable and inverter count more than DC cable cost adds

For V2, the System Design Agent flags this trade-off and asks user to decide
if project is in the 1–5 MWp range.

### Typical Inverter Unit Sizes (CIR)

| Type | Common Unit Sizes | 1500V capable |
|---|---|---|
| String (distributed) | 50 kW, 75 kW, 100 kW, 125 kW | Some models |
| String (utility, distributed) | 150 kW, 200 kW, 250 kW | Yes |
| Central String | 250 kW, 320 kW, 350 kW | Yes (standard) |

Common Central String models used in industry:
- Sungrow SG350HX (350 kW, 1500V)
- Huawei SUN2000-350KTL (350 kW, 1500V)
- SMA SC Pro 2500 (large string station)

**Inverter count calculation:**
```
For distributed string (< 1 MWp):
  unit_size_kw = 125   # default; override if user specifies brand
  inverter_count = ceil(ac_capacity_kw / unit_size_kw)

For central string (> 5 MWp, or user choice in 1–5 MWp):
  unit_size_kw = 350   # default (350 kW central string)
  inverter_count = ceil(ac_capacity_kw / unit_size_kw)
  # Each central string inverter typically serves 1–2 rows of combiners

For 1–5 MWp (agent presents both):
  option_a: distributed string, unit_size_kw = 125
  option_b: central string, unit_size_kw = 350
  present cost delta to user
```

---

## 2. Structure Type Selection

```
RT (Rooftop):
  → Fixed tilt (always — defined by roof angle)
  → No tracker consideration

CP (Carport):
  → Fixed tilt (always — structural constraints)
  → No tracker consideration

GM (Ground Mount):
  DC size ≤ 5 MWp:
    → Fixed tilt (default)
    → User can override to SAT with cost note

  5 MWp < DC size ≤ 20 MWp:
    → Fixed tilt (default)
    → Present SAT as option: "+$0.08–0.12/Wp installed cost, +15–25% energy yield"
    → User decides

  DC size > 20 MWp:
    → SAT (default — industry standard at utility scale)
    → User can override to fixed tilt with note

User preference override:
  → Always apply
  → Add note if choice is non-standard
```

### SAT vs Fixed Tilt Cost Delta
| Component | Fixed Tilt ($/Wp) | SAT ($/Wp) | Delta |
|---|---|---|---|
| Racking / structure | ~$0.08–0.12 | ~$0.16–0.22 | +$0.08–0.12 |
| Civil works | ~$0.05–0.08 | ~$0.06–0.10 | +$0.01–0.02 |
| O&M (annual) | ~$7–10/kW | ~$10–14/kW | +$3–4/kW |
| Energy yield | baseline | +15–25% | — |

---

## 3. DC/AC Ratio

```
GM Fixed Tilt:        default 1.25  (range 1.15–1.35)
GM SAT:               default 1.30  (range 1.20–1.40)
RT Fixed Tilt:        default 1.15  (range 1.05–1.25)
CP Fixed Tilt:        default 1.10  (range 1.05–1.20)
```

**User-supplied DC/AC ratio:**
- If outside range for type → WARN but use the value provided
- If < 1.0 → BLOCK (physically impossible — DC must exceed AC for inverter loading)
- If > 1.6 → FLAG (very high clipping losses, confirm with user)

**If user gives DC and AC separately, calculate and validate:**
```
dc_ac_ratio = dc_mwp / (ac_kw / 1000)
```

---

## 4. Module Wattage Class Selection

Based on project type, system voltage, and technology preference:

| Installation Type | System Voltage | Default Wattage | Technology |
|---|---|---|---|
| GM utility (≥ 1 MWp) | 1500V DC | 580–640 W | Bifacial monocrystalline |
| GM small (< 1 MWp) | 1500V DC | 480–580 W | Bifacial or monofacial |
| RT commercial | 1500V DC | 420–480 W | Monofacial or bifacial |
| CP | 1500V DC | 400–440 W | Monofacial or bifacial |

**String length at 1500V (GM, 580W module example):**
```
Max string voltage = 1500V
Module Voc (STC) ≈ 49–51V for typical 580W module
Temperature-corrected Voc (cold morning) ≈ 53–55V
Max panels per string = floor(1500 / 55) = 27 panels
Typical design string length: 26–28 panels per string
```

**String count (feeds into cable and BOM sizing):**
```
total_strings = ceil(panel_count / string_length)
```

**Budget orientation override:**
- Budget: lower wattage class, lower efficiency, lower cost/W
- Premium: higher wattage, higher efficiency, US-manufactured or Tier-1 non-FEOC

**FEOC compliance override:**
- Restricts module selection to non-FEOC manufacturers (see doc 08)
- Typically Qcells (US-manufactured), REC, Silfab, Heliene, Mission Solar

**Panel count calculation:**
```
dc_watts = dc_mwp × 1,000,000
panel_count = ceil(dc_watts / module_wattage_w)
```

---

## 5. Step-Up Transformer Requirement

```
POI voltage = inverter output voltage?
  → No transformer required (rare for utility projects)

POI voltage > inverter output voltage?
  → Transformer required
  → Transformer MVA = ac_capacity_kw / 1000 × 1.1 (10% oversize factor)
  → Transformer voltage = inverter_output_kv / POI_voltage_kv (e.g. 0.6kV / 12.47kV)

Common inverter output voltages:
  String inverters: 0.480 kV (480V), 0.600 kV (600V), 0.800 kV (800V)
  Central inverters: 0.600 kV (600V), 0.800 kV (800V)

Common POI voltages and transformer sizing:
  12.47 kV → 480V–12.47kV padmount transformer (each inverter block)
  33 kV    → 600V–33kV medium voltage transformer
  66 kV    → station transformer or multiple MV transformers
  132 kV   → large station transformer
```

**Cost note:**
- Each padmount transformer for 12.47kV: ~$80K–150K (market-researched)
- Medium voltage switchgear for 33kV+: ~$200K–500K
- High voltage substation for 132kV: ~$1M–3M+ (flagged as major variable)

---

## 6. Land Area Estimate

```
GM Fixed Tilt:
  land_acres = dc_mwp × 5.5   (range 4.5–7.0 acres/MWdc depending on tilt and row spacing)

GM SAT:
  land_acres = dc_mwp × 6.5   (SAT requires wider east-west row spacing)

RT:
  roof_sqft = (dc_watts / module_wattage_w) × module_area_sqft × 1.15  (15% packing factor)

CP:
  parking_spaces = ceil(panel_count / 4)   (typically 4 panels per parking space)
  land_acres = parking_spaces × 0.009       (approx per space)
```

---

## 7. BOM Summary Output

The `design_system()` tool returns a complete BOM for transparency:

```python
{
  "panels": {
    "manufacturer": "LONGi (or user preference)",
    "model_class": "580W bifacial",
    "quantity": 8621,
    "total_dc_watts": 5000180
  },
  "inverters": {
    "type": "string",
    "manufacturer": "Sungrow (user preference)",
    "unit_model_class": "SG125HX 125kW",
    "quantity": 32,
    "total_ac_kw": 4000
  },
  "racking": {
    "type": "SAT",
    "manufacturer": "nextracker (market default) or user preference",
    "quantity": "per system design"
  },
  "transformer": {
    "required": true,
    "quantity": 4,
    "mva_each": 1.1,
    "voltage": "480V / 12.47kV"
  },
  "land_area_acres": 32.5
}
```
