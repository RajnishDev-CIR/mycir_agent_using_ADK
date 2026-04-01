# Compliance & Regulatory Considerations

This document covers the compliance-related cost factors that V2 must handle
and V1 could not. These are real cost drivers on US solar projects.

---

## 1. FEOC Compliance (Foreign Entity of Concern)

### What it is
The Inflation Reduction Act (IRA) and related guidance define "Foreign Entities
of Concern" (FEOC) as entities connected to China, Russia, North Korea, or Iran.

Solar modules and batteries sourced from FEOC-connected manufacturers will
**not qualify** for IRA domestic content bonus adders and may face tariff risk.

For projects requiring IRA tax credit optimisation or government/federal
procurement, FEOC-compliant equipment is mandatory.

### Cost Impact
FEOC-compliant modules (non-Chinese manufacturers) typically cost:
- +$0.03–0.08/Wp above comparable Chinese-manufactured modules
- Higher end for fully US-manufactured (Qcells Georgia, Silfab Ontario/US, First Solar US)
- Lower end for non-Chinese but non-US (REC Norway, Maxeon Philippines)

### FEOC-Excluded Manufacturers (as of 2025)
These are commonly considered FEOC-free:
| Manufacturer | Origin | Notes |
|---|---|---|
| Qcells | Korea (US factory in GA) | Preferred for IRA domestic content |
| First Solar | USA | CdTe technology, high efficiency |
| Silfab | Canada / USA | Monocrystalline |
| Mission Solar | USA (San Antonio TX) | Monocrystalline |
| REC Group | Norway | Not FEOC, but not US-made |
| Maxeon | Singapore / Philippines | Not FEOC |
| Heliene | Canada | Not FEOC |

### FEOC-Affected Manufacturers (cannot use for FEOC-compliant projects)
LONGi, JA Solar, Trina Solar, Canadian Solar (Chinese-owned), Jinko Solar,
JinkoSolar, Risen Energy, GCL, Seraphim

### V2 Implementation
1. Project Intake Agent asks: "Is FEOC compliance required? (Yes/No)"
2. If Yes:
   - Equipment Selection restricts module manufacturers to FEOC-excluded list
   - Market Research searches specifically for FEOC-compliant pricing
   - Cost Calc adds `feoc_compliance_premium` line item
   - IRA Agent confirms FEOC compliance enables domestic content adder
3. If No:
   - Standard manufacturer selection (best value from all tier-1 options)

---

## 2. Prevailing Wage / Davis-Bacon Act

### What it is
The Davis-Bacon and Related Acts require contractors on federally assisted
construction projects to pay workers the locally prevailing wages and fringe
benefits for the type of work performed.

For IRA tax credits (Investment Tax Credit), the **Prevailing Wage and
Apprenticeship (PWA)** requirements must be met to access the full 30% ITC.
Without PWA compliance, the base ITC drops from 30% to **6%**.

### Cost Impact by State
Prevailing wages vary significantly by state and county:

| Region | Labour Multiplier vs National Avg |
|---|---|
| California (most counties) | 1.40–1.60× |
| New York (NYC area) | 1.50–1.70× |
| Massachusetts | 1.35–1.50× |
| Illinois (Chicago) | 1.40–1.55× |
| Texas | 1.00–1.10× |
| Arizona | 1.00–1.05× |
| Nevada | 1.10–1.20× |
| Florida | 0.95–1.05× |

**Example impact for 5 MWp CA project:**
- Standard labour (mechanical + electrical): ~$0.37/Wp → ~$1.85M
- CA prevailing wage (1.45×): ~$0.54/Wp → ~$2.70M
- **Delta: ~$0.17/Wp, ~$850K additional cost**

### V2 Implementation
1. Project Intake Agent asks: "Is prevailing wage / Davis-Bacon compliance required?"
2. Location Intel Agent searches for state + county prevailing wage rates:
   - "Davis-Bacon prevailing wage solar [state] [county] [year]"
   - Returns the multiplier and $/hr rates for relevant trades
3. Cost Calc Agent applies multiplier to mechanical and electrical labour lines
4. Separate `prevailing_wage_premium` line item shows the delta vs standard rates
5. IRA Agent confirms PWA compliance enables full 30% ITC (vs 6%)

---

## 3. IRA Tax Credits — Full Detail

### Investment Tax Credit (ITC) Structure

| Credit Component | Rate | Requirement |
|---|---|---|
| Base ITC | 6% | Default without PWA |
| Base ITC with PWA | 30% | Prevailing wage + apprenticeship met |
| Domestic Content Adder | +10% | ≥55% US iron/steel, ≥40% US components |
| Energy Community Adder | +10% | Project in qualifying energy community |
| Low-Income Community (LIC) | +10% | Direct allocation program — application required |
| Low-Income Bonus (housing) | +20% | Qualifying low-income residential — application required |
| Maximum possible | 50% | All adders + PWA |

### Energy Community Definition
A location qualifies as an energy community if it is:
- A brownfield site, OR
- A metropolitan or non-metropolitan statistical area that has 0.17% or greater
  direct employment or 25% or greater local tax revenues related to extraction,
  processing, transport, or storage of coal, oil, or natural gas, AND has 17%
  or greater unemployment rate (above national average), OR
- A census tract in which a coal mine has closed after 1999, OR a census tract
  adjacent to such a tract, OR a census tract in which a coal-fired electric
  generating unit has been retired after 2009

**How to check:** DOE Energy Communities map at energycommunities.gov

### Domestic Content Requirements (2025)
For the +10% domestic content adder:
- Steel and iron: 100% US manufactured
- Manufactured products:
  - 2025: ≥40% US manufactured
  - 2026: ≥45%
  - 2027+: ≥50%
  - 2028+: ≥55%

Modules from Qcells (Georgia facility) and First Solar (Ohio facility) typically
qualify. String inverters: SMA (limited US content), Sungrow (does not qualify),
ABB/Fimer (varies). Check manufacturer certificates.

### V2 IRA Agent Output Example

```
IRA / Incentive Analysis
─────────────────────────
Base ITC:                     30%   (PWA compliance confirmed)
Domestic content adder:       10%   (Qcells modules + US racking qualify)
Energy community adder:        0%   (Kern County, CA — does not qualify)
Total ITC rate:               40%

Gross CAPEX:            $10,500,000   ($2.10/Wp)
Estimated ITC value:    -$4,200,000   (40% × gross CAPEX)
Net CAPEX after ITC:     $6,300,000   ($1.26/Wp)

Notes:
- PWA compliance requires certified payroll records for all subcontractors
- Domestic content certification must be obtained from Qcells and racking supplier
- ITC value is an estimate — actual value determined at tax filing
- Consult tax advisor to confirm eligibility
```

---

## 4. California-Specific Considerations

When Location Intel detects California as the project state:

### CPUC / CAISO Interconnection
- California Independent System Operator (CAISO) interconnection queue is
  among the longest in the US — 3–5+ years for large projects
- Search for current queue status and estimated timeline
- Flag if COD is unrealistic given queue length

### AB 2316 (Community Solar)
- California community solar program — may affect project structure
- Note if project could qualify

### CEC Listing Requirements
- California Energy Commission (CEC) requires listed equipment for rebate programs
- Check if selected modules are CEC-listed (most tier-1 are)

### Seismic Zone Considerations
- California is Seismic Design Category D or higher in most areas
- Racking and foundation design must meet IBC seismic requirements
- May add 5–15% to civil/structural costs in high-seismic zones
- Location Intel should flag if county is in Seismic Zone 3 or 4

### SGIP (Self-Generation Incentive Program)
- California rebate for storage and certain generation technologies
- Note eligibility if battery storage is added in future

---

## 5. Tariffs and Trade Considerations

### Section 201 / 301 Tariffs on Solar Modules
- US imposes tariffs on imported solar modules
- Bifacial modules had tariff exemptions that have been contested
- Current tariff rates (check for updates — these change):
  - Crystalline silicon modules: 14.25% (Section 201) as of 2024
  - Additional Section 301 tariffs on Chinese products
  - AD/CVD (anti-dumping / countervailing duties) on Chinese-manufactured
    panels via third-country routes

**V2 handling:**
- Market Research Agent should note if prices it finds are tariff-inclusive or exclusive
- Search query: "solar panel price US tariff inclusive 2025"
- Flag in output: "Module prices reflect current US tariff environment"

### USMCA (US-Mexico-Canada Agreement)
- Equipment manufactured in Mexico or Canada may qualify for preferential treatment
- Relevant for inverter and racking manufacturers with North American facilities

---

## 6. Interconnection Costs

These are frequently the largest variable cost on solar projects and must be
flagged clearly in V2 output.

**What is typically excluded from CAPEX estimates (V1 and V2):**
- Utility interconnection application fees
- System impact studies ($50K–$500K)
- Facility studies
- Network upgrade costs (can be $0 to millions depending on grid capacity)
- Line extension costs

**What V2 Location Intel Agent should research:**
- "CPUC CAISO interconnection queue [county] solar 2025"
- "[utility name] distribution interconnection timeline solar [state] 2025"
- Recent reports of network upgrade costs in the area

**V2 output should include:**
- Utility territory identified (e.g. SCE, PG&E, SDG&E for California)
- Current interconnection queue status (months)
- Note: "Interconnection upgrade costs are excluded from this estimate and
  are determined by utility study. These can range from $0 to $X/Wp
  depending on local grid capacity."
