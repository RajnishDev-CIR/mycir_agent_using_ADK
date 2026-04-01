# V1 Lessons Learned — Problems Found and V2 Solutions

Source: Analysis of session `6762b113-b6fa-4451-ae16-8f1d1efe19ee`

This document records every problem observed in V1 operation and the specific
V2 design decision that prevents it from recurring.

---

## Problem 1 — FEOC Compliance Completely Ignored

### What happened in V1
User explicitly requested: *"FEOC compliance system"*

V1 response:
> "Currently, the CAPEX estimation agent focuses on the core equipment and installation
> costs based on the provided specifications and benchmark rates. The available tools do
> not have specific fields or rate adjustments to directly factor in the cost implications
> of 'FEOC compliance' into the numerical estimate."

When user pushed back and asked it to do market research:
> "My existing tools do not have specific parameters to incorporate these types of costs
> as direct overrides or separate line items."

**Result:** A mandatory user requirement was silently dropped from the estimate.
The estimate was produced without reflecting one of the user's explicit constraints.

### Why it happened in V1
V1's `calculate_capex_estimate()` tool had fixed line items from the CSV.
It had no way to add new line items. The agent correctly identified the gap
but had no fallback and gave up.

### V2 Solution
1. **Project Intake Agent** explicitly asks for FEOC compliance requirement as a preference field
2. **Equipment Selection** (inside Engineering Agent) restricts module/inverter manufacturers
   to FEOC-excluded list when `feoc_compliance = true`
3. **Market Research Agent V2** searches for FEOC-compliant equipment pricing specifically:
   - "FEOC compliant solar panels price per watt 2025"
   - "US manufactured solar modules wholesale cost 2025"
4. **Cost Calculation Agent V2** includes a `feoc_compliance_premium` line item:
   - FEOC-compliant modules typically cost $0.03–0.08/Wp more than standard
   - This is a named, quantified line item in the output
5. **Never says "I can't"** — if market research cannot find FEOC pricing,
   it uses a documented range estimate with a note

---

## Problem 2 — Prevailing Wage Labour Ignored

### What happened in V1
User explicitly requested: *"prevailing wage labour"* (Davis-Bacon Act rates, CA site)

V1 produced the estimate with standard benchmark labour rates and mentioned
prevailing wage only as a disclaimer note — not quantified in the cost.

California prevailing wage for solar installation is typically **40–60% above**
national average benchmark rates. For a 5 MWp project, this represents
approximately **$150K–300K in additional cost** — not a negligible omission.

### Why it happened in V1
V1's CSV had a single `mechanical_rate` and `electrical_rate` with no location
multiplier and no prevailing wage adjustment. The tool had no way to modify
these rates based on user requirements.

### V2 Solution
1. **Project Intake Agent** explicitly asks: "Is prevailing wage / Davis-Bacon required?"
2. **Location Intel Agent** searches for state + county specific prevailing wage rates:
   - "Davis-Bacon prevailing wage solar construction California Los Angeles 2025"
   - Returns both the multiplier and the $/Wp premium
3. **Cost Calculation Agent V2** adds a separate `prevailing_wage_premium` line item:
   ```
   Prevailing wage premium (CA, Davis-Bacon)   +$0.08/Wp   +$400,000
   ```
4. The line item is clearly labelled, quantified, and sourced
5. If prevailing wage data not found via search: uses documented state wage survey
   data as fallback with a note

---

## Problem 3 — SAT Racking Rate Not Adjusted

### What happened in V1
User specified Single-Axis Tracker (SAT). V1 produced the estimate and
even wrote "Structure: Single-Axis Tracker" in the output header.

However, the racking rate used was `$0.18/Wp` — this is the same rate
used for fixed-tilt ground mount in the CSV. The CSV has no SAT-specific
rates.

SAT racking actually costs `$0.16–0.22/Wp` vs `$0.08–0.12/Wp` for fixed tilt.
The estimate was understated by approximately **$0.06–0.10/Wp on racking alone**,
or ~$300K–500K on a 5 MWp project.

### Why it happened in V1
V1's CSV had a single `racking_rate` per row, no distinction between structure types.
V1 noted the structure type in the header but the tool had no branching logic for it.

### V2 Solution
1. **Engineering Agent** determines structure type and stores it in `ctx.state['system_design']`
2. **Market Research Agent V2** searches specifically for SAT or fixed-tilt pricing:
   - SAT: "single axis tracker solar cost per watt 2025 nextracker array technologies"
   - Fixed: "solar fixed tilt racking $/Wp 2025"
3. **Cost Calculation Agent V2** uses the correct rate for the structure type selected
4. If user changes from fixed to SAT (or vice versa), the Scenario Agent shows
   the cost delta explicitly

---

## Problem 4 — 12.47kV POI Step-Up Transformer Not Costed

### What happened in V1
User specified 12.47kV POI. V1's output stated:
> "POI location is at inverter level only"

A 5 MWp / 4 MW AC project with string inverters at 480V output feeding
a 12.47kV grid requires step-up transformers (likely 4 × ~1 MVA padmount
transformers). This cost was entirely excluded.

Typical cost: $80K–150K per transformer × 4 units = **$320K–600K excluded**.

### Why it happened in V1
V1 had no transformer logic. POI voltage was collected as a mandatory field
but used only for the output header — no calculation was tied to it.

### V2 Solution
1. **Engineering Agent `design_system()` tool** determines transformer requirement:
   - Compares inverter output voltage to POI voltage
   - Calculates number and size of transformers needed
2. **Market Research Agent V2** searches for current transformer pricing
3. **Cost Calculation Agent V2** includes transformer as a named line item:
   ```
   Step-up transformers (4 × 1.1 MVA, 480V/12.47kV)   $0.09/Wp   $450,000
   ```
4. For high-voltage POI (66kV+), the agent flags that a full substation
   may be required and that cost is indicative only

---

## Problem 5 — Context Lost Between Turns (Re-asking Known Information)

### What happened in V1
User provided full project details in message 1:
> "5MWp 4MW ground mount 12.47KV POI EPC cost of the system with FEOC compliance
> system and prevailing wage labour for site in CA, USA"

Agent asked for them again after transfer to sub-agent:
> "Please fill in: Project Name, Location (State / County), DC Capacity..."

User then said: "please pull up the details from the chat"

Agent still re-asked for county and structure type — information already in the
conversation history.

This creates friction and erodes trust in the agent.

### Why it happened in V1
V1's `capex_estimation_agent` instruction said "present ALL required fields at once"
but did not instruct the agent to first extract already-provided values from context.
Each invocation started fresh because there was no session state persistence.

### V2 Solution
1. **Project Intake Agent** instruction explicitly states:
   - "Before presenting the intake form, first extract ALL details already provided
     in the conversation. Pre-fill extracted values. Only ask for genuinely missing fields."
2. **ADK DatabaseSessionService** persists session state across turns and invocations —
   values stored in `ctx.state` survive across multiple user messages
3. **Input Validation Agent** works on what was collected, not re-collected
4. If a field is truly ambiguous (e.g. "CA" without county), agent asks once
   for clarification — not as part of a full re-intake

---

## Problem 6 — Market Research Agent Never Called Despite Clear Need

### What happened in V1
When V1 was told it couldn't handle FEOC or prevailing wage, and user
explicitly said "I think you can do market research and get it done if
it's not in our CSV," V1 still declined:
> "While the market_research_agent can search... it's not designed to
> quantify the specific cost implications..."

The market research agent was available and capable but the main agent
refused to use it creatively.

### Why it happened in V1
V1's agent instructions gave market research a narrow, predefined role
(current component prices only). The agent interpreted its instructions
too literally and did not attempt to use the tool for adjacent problems.

### V2 Solution
1. Each specialist agent (Location Intel, IRA Agent) has market research
   **built in** as a core tool — they are not optional extras
2. The **fallback chain** explicitly mandates: if data is not in CSV,
   search for it before giving up
3. Agent instructions explicitly state: "If you cannot find the exact data
   requested, search for the closest available data, document what you found
   and what assumptions you made, and proceed — never decline to estimate
   because a specific data point is missing"

---

## Summary Table

| # | V1 Problem | V2 Fix |
|---|---|---|
| 1 | FEOC compliance ignored | Intake asks for it; Equipment Selection enforces it; Market Research prices it; Cost Calc shows it as line item |
| 2 | Prevailing wage not quantified | Intake asks for it; Location Intel searches for rates; Cost Calc adds named line item |
| 3 | SAT racking same rate as fixed tilt | Engineering Agent determines structure type; Market Research searches SAT-specific; Cost Calc uses correct rate |
| 4 | POI transformer not costed | Engineering Agent calculates transformer requirement; Market Research prices it; Cost Calc includes it |
| 5 | Context re-asked each turn | Intake extracts from context first; ADK DatabaseSessionService persists state |
| 6 | Market research never used for gaps | All sub-agents have market research built in; fallback chain mandates search before giving up |
