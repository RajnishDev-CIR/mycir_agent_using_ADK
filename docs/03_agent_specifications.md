# Agent Specifications

Each agent's role, inputs, outputs, tools, and failure behaviour.

---

## 1. MyCIR Agent

**Type:** LlmAgent (root)
**Model:** Gemini 2.5 Flash
**Role:** Pure router. Zero domain knowledge.

**What it does:**
- Reads user message, identifies intent
- Routes to the correct specialist agent via `transfer_to_agent`
- Saves session state via DatabaseSessionService
- Maintains conversation tone and opening greeting

**What it does NOT do:**
- Ask for project details
- Interpret domain workflows beyond choosing which specialist handles the message
- Do any calculations or web searches

**Sub-agents (as AgentTools):**
- `capex_agent_v2` (active)

Additional specialists will be registered here as they are implemented per the CIR roadmap (Development, Engineering, Procurement, O&M — see [01_project_overview](01_project_overview.md)).

**Routing rules (today):**
```
"capex", "cost", "estimate", "budget", "$/Wp", "EPC", "price"  →  capex_agent_v2
"compare", "benchmark", "validate"                              →  capex_agent_v2
unclear                                                         →  ask one clarifying question
```

**Routing rules (future):** When new AgentTools exist, extend the table by intent (e.g. GIS / lead origination → Development agent; layout / EPSA / BESS → Engineering agent) without adding domain logic to MyCIR.

---

## 2. Capex Agent V2

**Type:** SequentialAgent (orchestrator)
**Role:** Manages the full CAPEX estimation pipeline.

Runs sub-agents in strict order:
1. Project Intake Agent
2. Input Validation Agent
3. Engineering / System Design Agent
4. ParallelAgent [Market Research V2 + Location Intel]
5. IRA / Incentive Agent
6. Cost Calculation Agent V2
7. Benchmark Validation Agent (if AUTO mode)
8. Scenario Agent (if user requested scenarios)
9. Export Agent (if user requested file)

Does not produce any output itself — it orchestrates and the final formatted
output comes from Cost Calculation Agent V2 + Benchmark Validation Agent.

---

## 3. Project Intake Agent

**Type:** LlmAgent
**Model:** Gemini 2.5 Flash
**Role:** Collect all project inputs and user preferences in one structured conversation.

**First message rule:** Always present ALL fields at once, never ask one-by-one.

**Mandatory fields:**
| Field | Notes |
|---|---|
| Project Name | Any string |
| Location | State + County (county can be "unspecified" if user declines) |
| DC Capacity | MWp — auto-convert from KWp if needed |
| AC Capacity | KW — auto-convert from MW if needed |
| Installation Type | GM / RT / CP |
| POI Voltage | e.g. 12.47kV, 33kV, 66kV, 132kV |
| Expected COD | Quarter + Year format e.g. Q2 2027 |

**Preference fields (always ask, mark as optional):**
| Field | Notes |
|---|---|
| Module manufacturer preference | e.g. "LONGi only", "no Chinese modules", "no preference" |
| Inverter manufacturer preference | e.g. "Sungrow", "SMA", "no preference" |
| Technology preference | Tracker vs fixed (GM only), bifacial vs monofacial |
| Budget orientation | Budget / Mid-range / Premium |
| FEOC compliance required | Yes / No — affects equipment selection |
| Prevailing wage / Davis-Bacon required | Yes / No — affects labour rates |
| IRA domestic content required | Yes / No — affects equipment sourcing |
| Known price overrides | Any specific $/Wp rates from vendor quotes |

**Context extraction rule:**
- If user already provided some details in their first message (e.g. "5 MWp, 4 MW, GM, CA, 12.47kV POI"),
  extract all of them before asking for missing fields.
- Do NOT ask for information already provided in the conversation.

**Output:** Stores structured dict in `ctx.state['project']` and `ctx.state['preferences']`.

---

## 4. Input Validation Agent

**Type:** LlmAgent + tools
**Model:** Gemini 2.5 Flash
**Role:** Validate inputs for consistency and realism before spending API calls on research.

**Validation checks:**

| Check | Threshold | Action |
|---|---|---|
| DC/AC ratio | Outside 1.05–1.6 | WARN with suggestion |
| GM project COD | < 18 months from today | FLAG as unrealistic timeline |
| RT project COD | < 12 months from today | WARN |
| RT size | > 4 MWp | BLOCK — out of V2 scope |
| CP size | > 3.8 MWp | BLOCK — out of V2 scope |
| GM size | > 250 MWp | FLAG — very large, confirm |
| POI voltage mismatch | 12.47kV for > 20 MWp | WARN — likely needs 33kV+ |
| POI voltage mismatch | 132kV for < 5 MWp | WARN — likely oversized POI |
| Location | Ambiguous or unrecognised state | Ask for clarification |
| COD format | Cannot be parsed | Ask for clarification |

**Outcomes:**
- `pass`: all good, proceed
- `warn`: proceed but add warning notes to output
- `block`: do not proceed, explain why to user and ask them to correct

**Output:** Stores `ctx.state['validation']` = `{status, warnings: [], block_reason}`

---

## 5. Engineering / System Design Agent

**Type:** LlmAgent + tools
**Model:** Gemini 2.5 Flash
**Role:** Apply engineering reasoning to determine system configuration.

**Tool: `design_system()`**

Logic executed by tool (not LLM):
- Inverter type selection (see doc 04 for full logic)
- Structure type selection (fixed tilt vs SAT)
- DC/AC ratio selection
- Module wattage class selection
- Panel count calculation
- Inverter count calculation
- String sizing
- Step-up transformer requirement
- Land area estimate

**Reads:** `ctx.state['project']`, `ctx.state['preferences']`
**Output:** `ctx.state['system_design']`

```python
# system_design structure
{
  "inverter_type": "string" | "central",
  "inverter_type_reason": "...",
  "structure_type": "fixed_tilt" | "SAT",
  "structure_type_reason": "...",
  "dc_ac_ratio": 1.25,
  "module_wattage_w": 580,
  "module_technology": "bifacial",
  "panel_count": 8621,
  "inverter_unit_size_kw": 125,
  "inverter_count": 32,
  "transformer_required": true,
  "transformer_mva": 5.5,
  "transformer_voltage": "12.47kV",
  "land_area_acres": 30,
  "preference_overrides": ["user requested Sungrow inverters — applied"],
  "preference_warnings": ["SAT selected per user preference; fixed tilt would save ~$0.09/Wp for this size"]
}
```

**Preference override handling:**
- If user preference conflicts with engineering best practice:
  - Apply the preference
  - Add a note in `preference_warnings` explaining the cost/risk delta
  - Never silently ignore a preference

---

## 6. Market Research Agent V2

**Type:** LlmAgent
**Model:** Gemini 2.5 Flash
**Tool:** `google_search`
**Role:** Find current wholesale market prices for equipment selected by System Design Agent.

**Searches performed (specific to equipment selected):**

| Component | Search pattern |
|---|---|
| Module | "[manufacturer] [wattage]W solar panel wholesale price 2025" |
| Inverter (string) | "[brand] [size]kW string inverter price per watt 2025" |
| Inverter (central) | "[brand] [size]kW central inverter $/kW price 2025" |
| SAT racking | "single axis tracker solar price per watt 2025 [manufacturer if preferred]" |
| Fixed tilt racking | "fixed tilt racking solar $/Wp 2025" |
| BOS | "solar BOS balance of system cost per watt [year]" |
| Transformer | "[MVA] MVA [voltage] solar step up transformer price 2025" |
| General EPC | "NREL solar installed cost benchmark [year] [type: utility/rooftop]" |

**Output structure per component:**
```python
{
  "component": "module",
  "manufacturer": "LONGi",
  "spec": "580W bifacial",
  "price_low": 0.17,
  "price_mid": 0.21,
  "price_high": 0.25,
  "unit": "$/Wp",
  "source_count": 3,
  "sources": ["url1", "url2", "url3"],
  "source_avg_age_days": 22,
  "confidence": "medium"   # low (<2 sources or >90 days old) / medium / high
}
```

**Fallback:** If fewer than 2 sources found for a component, marks confidence as "low"
and flags for Cost Calc Agent to use V1 CSV rate as fallback for that line item.

**Output:** `ctx.state['market_prices']`

---

## 7. Location Intel Agent

**Type:** LlmAgent
**Model:** Gemini 2.5 Flash
**Tool:** `google_search`
**Role:** Find location-specific cost factors.

**Searches performed:**

| Factor | Search pattern |
|---|---|
| Labour (standard) | "solar EPC labor cost per watt [state] 2025" |
| Labour (prevailing wage) | "Davis-Bacon prevailing wage solar construction [state] [county] 2025" |
| AHJ permitting | "solar permitting cost [county] [state] 2025 AHJ fees" |
| Utility interconnection | "[utility name] [state] solar interconnection queue timeline 2025" |
| State incentives | "[state] solar incentive SREC rebate 2025" |
| Civil / geotechnical | "solar grading civil cost [state] ground mount 2025" |

**Outputs:**
```python
{
  "state": "CA",
  "county": "Los Angeles",
  "labour_multiplier": 1.45,        # vs national average (1.0 = national avg)
  "labour_multiplier_source": "...",
  "prevailing_wage_applied": true,
  "prevailing_wage_premium_per_wp": 0.08,
  "permitting_cost_per_wp": 0.05,
  "permitting_source": "...",
  "utility_territory": "SCE",
  "interconnection_note": "SCE queue currently 18–24 months for new solar",
  "state_incentive_note": "CA Self-Generation Incentive Program — check eligibility",
  "civil_cost_note": "Seismic zone consideration — may increase civil 10-15%"
}
```

**Output:** `ctx.state['location_costs']`

---

## 8. IRA / Incentive Agent

**Type:** LlmAgent + tools
**Model:** Gemini 2.5 Flash
**Tool:** `google_search` (for current IRA guidance)
**Role:** Determine applicable tax incentives and their cost impact.

**Logic executed:**

| Check | Outcome |
|---|---|
| Base ITC | Always 30% for commercial solar |
| Domestic content adder | +10% if ≥55% US-manufactured steel/iron and ≥40% US-manufactured components |
| Energy community adder | +10% if project is in a qualifying energy community (check DOE map) |
| Low-income community adder | +10–20% additional (application required) |
| Prevailing wage + apprenticeship | Required to unlock base 30% (vs 6% without) — confirm compliance |

**Preference link:**
- If user set `ira_domestic_content = true`, equipment selection must have flagged US-made options
- If user set `feoc_compliance = true`, this agent confirms FEOC-excluded equipment was selected

**Output:**
```python
{
  "base_itc_pct": 30,
  "domestic_content_adder": 10,       # 0 if not applicable
  "energy_community_adder": 10,       # 0 if not applicable
  "total_itc_pct": 40,
  "estimated_itc_value_usd": 5680000,
  "net_capex_after_itc_usd": 8520000,
  "notes": ["Prevailing wage required to qualify for 30% base rate", ...]
}
```

**Output:** `ctx.state['ira_result']`

---

## 9. Cost Calculation Agent V2

**Type:** LlmAgent + tools
**Model:** Gemini 2.5 Flash
**Role:** Perform all arithmetic and produce the final estimate. Zero market research.

**Tool: `calculate_capex_v2()`**

Reads from `ctx.state`:
- `project` — sizes, type, name, location
- `system_design` — equipment type and counts
- `market_prices` — live rates per component
- `location_costs` — labour multiplier, prevailing wage premium, permitting
- `preferences` — any user override rates

Calculates for each of 3 scenarios (low/mid/high):

**Line items:**
1. Module supply — `panel_count × module_wattage × market_price_per_wp`
2. Inverter supply — `inverter_count × unit_cost` (from market research)
3. Racking / structure — `dc_watts × racking_rate` (SAT or fixed tilt specific)
4. Balance of system (BOS) — `dc_watts × bos_rate`
5. Mechanical installation — `dc_watts × labour_rate × location_multiplier`
6. Electrical installation — `dc_watts × elec_rate × location_multiplier`
7. Civil works — `dc_watts × civil_rate` (with seismic/terrain notes if applicable)
8. Engineering — `dc_watts × engineering_rate`
9. Permitting — `dc_watts × permitting_rate` (location-adjusted from Location Intel)
10. Transformer / step-up — fixed cost from market research (if required)
11. Prevailing wage premium — `(mechanical + electrical) × prevailing_wage_premium` (if required)
12. FEOC compliance premium — market-researched adder if FEOC-compliant equipment required
13. Overhead (SGA) — `subtotal × overhead_pct`
14. Contingency — `subtotal × contingency_pct`
15. Margin — `subtotal × margin_pct`

**Source tracking:** Every line item records whether rate came from:
- `live_market` — from Market Research Agent
- `location_intel` — from Location Intel Agent
- `user_override` — from user-provided quote
- `v1_fallback` — from V1 CSV (market research failed for this component)

**Output:** `ctx.state['estimate']` with low/mid/high bands.

---

## 10. Benchmark Validation Agent

**Type:** LlmAgent (orchestrator of V1 Runner + Comparison Report)
**Role:** Validate V2 output against V1 baseline. Acts as quality gate.

See [doc 06](06_benchmark_validation.md) for full specification.

---

## 11. Scenario Agent

**Type:** LlmAgent
**Model:** Gemini 2.5 Flash
**Role:** Run 2–3 variants of the same project and present side-by-side.

**Triggered when:**
- User asks "compare tracker vs fixed tilt"
- User asks "what if I use central inverters instead"
- User asks "show me budget vs premium module option"

**How it works:**
- Calls Cost Calculation Agent V2 two or three times with different system_design inputs
- Each variant runs through full pipeline (market research already cached in ctx.state)
- Produces a comparison table

---

## 12. Export Agent

**Type:** LlmAgent + tools
**Model:** Gemini 2.5 Flash
**Role:** Generate formatted output files.

**Triggered when:**
- User says "export", "download", "send me the file", "Excel", "PDF"

**Outputs:**
- Excel: line-item table, scenario tabs, benchmark tab, IRA summary tab
- PDF: one-page professional estimate summary with CIR branding

**Tool: `generate_excel()`, `generate_pdf()`**
