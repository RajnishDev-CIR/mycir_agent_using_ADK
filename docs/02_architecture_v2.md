# V2 Architecture Design

## Agent Hierarchy (Full)

```
┌─────────────────────────────────────────────────────────────┐
│                      MyCIR Agent                            │
│         Super-agent · pure router · zero domain logic       │
│         Saves session · understands intent · delegates      │
└────────────────────────┬────────────────────────────────────┘
                         │
                          ▼
                   ┌─────────────┐
                   │ Capex Agent │
                   │     V2      │
                   │  (active)   │
                   └──────┬──────┘
          (Future: Development, Engineering, Procurement, O&M specialists —
           see docs/01_project_overview.md.)
          │
          │  SequentialAgent orchestration
          │
    ┌─────▼──────────────────────────────────────────┐
    │                Capex Agent V2                   │
    │  Orchestrates all sub-agents in order           │
    └─────┬───────────────────────────────────────────┘
          │
    ┌─────▼─────────────┐
    │  Project Intake   │  Collects all inputs + user preferences
    │      Agent        │  in a single structured conversation
    └─────┬─────────────┘
          │
    ┌─────▼─────────────┐
    │  Input Validation │  Catches bad inputs before any work starts
    │      Agent        │  Flags unrealistic COD, bad DC/AC ratio, etc.
    └─────┬─────────────┘
          │
    ┌─────▼─────────────┐
    │   Engineering /   │  Inverter type, structure type, panel count,
    │  System Design    │  inverter count, DC/AC ratio, land area, BOM
    │      Agent        │
    └─────┬─────────────┘
          │
    ┌─────▼──────────────────────────────────────┐
    │            ParallelAgent                    │
    │   (runs both simultaneously)                │
    │  ┌──────────────────┐  ┌──────────────────┐│
    │  │  Market Research │  │  Location Intel  ││
    │  │   Agent V2       │  │     Agent        ││
    │  │  (google search) │  │  (google search) ││
    │  └──────────────────┘  └──────────────────┘│
    └─────┬──────────────────────────────────────┘
          │
    ┌─────▼─────────────┐
    │  IRA / Incentive  │  ITC rate, domestic content adder,
    │      Agent        │  energy community adder, state incentives
    └─────┬─────────────┘
          │
    ┌─────▼─────────────┐
    │   Cost Calc V2    │  All arithmetic in tools · no LLM math
    │      Agent        │  Outputs low/mid/high confidence bands
    └─────┬─────────────┘
          │
    ┌─────▼─────────────┐
    │ Benchmark Valid.  │  Validation layer — runs V1 silently,
    │     Agent         │  flags outliers before user sees result
    │  ┌─────────────┐  │
    │  │  V1 Runner  │  │
    │  └─────────────┘  │
    │  ┌─────────────┐  │
    │  │ Comparison  │  │
    │  │   Report    │  │
    │  └─────────────┘  │
    └─────┬─────────────┘
          │
    ┌─────▼─────────────┐     ┌──────────────────┐
    │  Final Output     │────▶│  Export Agent    │
    │  (to user)        │     │  Excel / PDF     │
    └───────────────────┘     │  (on request)    │
                              └──────────────────┘
```

---

## MyCIR Agent — Routing Logic

MyCIR Agent's ONLY job is to understand intent and route.

| User says | Routes to |
|---|---|
| Anything about cost, price, budget, CAPEX, EPC, $/Wp | Capex Agent V2 |
| "compare", "benchmark", "validate" | Capex Agent V2 (handles internally) |
| Unclear intent | Asks one clarifying question, then routes |

When future specialists exist (lead origination / GIS, engineering layouts, procurement intel, O&M analytics — see [01_project_overview](01_project_overview.md)), MyCIR will route by intent to those agents using the same pattern: one row per specialist, no domain work in the router.

MyCIR never passes domain context downstream. It passes only the raw user message and
session ID. Each specialist agent manages its own context.

---

## Capex Agent V2 — Orchestration Order

The Capex Agent is a SequentialAgent. Sub-agents run in this strict order:

```
Step 1: Project Intake Agent
        → Output: structured project data + user preferences stored in ctx.state

Step 2: Input Validation Agent
        → Output: validation_result (pass / warn / block)
        → If BLOCK: return error to user, do not proceed

Step 3: Engineering / System Design Agent
        → Reads: ctx.state['project'] + ctx.state['preferences']
        → Output: system_design stored in ctx.state['system_design']

Step 4: ParallelAgent [Market Research V2 + Location Intel]
        → Both run simultaneously
        → Output: ctx.state['market_prices'] + ctx.state['location_costs']

Step 5: IRA / Incentive Agent
        → Reads: location + equipment selection
        → Output: ctx.state['ira_result']

Step 6: Cost Calculation Agent V2
        → Reads: all ctx.state values from steps 1–5
        → Output: ctx.state['estimate'] (low/mid/high bands)

Step 7: Benchmark Validation Agent  [AUTO mode only]
        → Reads: ctx.state['project'] + ctx.state['estimate']
        → Output: validation_status (pass / warn / flag)

Step 8: Format and return to user
        → Scenario Agent if user requested scenarios
        → Export Agent if user requested file
```

---

## Data Flow Through ctx.state

ADK session state is the shared data bus between all agents. No agent passes data
directly to another — everything flows through `ctx.state`.

```
ctx.state['project']          → set by Intake, read by all downstream agents
ctx.state['preferences']      → set by Intake, read by Engineering + Equipment selection
ctx.state['validation']       → set by Validation Agent
ctx.state['system_design']    → set by Engineering Agent
ctx.state['market_prices']    → set by Market Research Agent
ctx.state['location_costs']   → set by Location Intel Agent
ctx.state['ira_result']       → set by IRA Agent
ctx.state['estimate']         → set by Cost Calc Agent
ctx.state['benchmark']        → set by Benchmark Validation Agent
```

Ephemeral data within a single invocation uses `temp:` prefix (not persisted):
```
ctx.state['temp:search_query']
ctx.state['temp:raw_search_results']
```

---

## Fallback Chain

V2 never hard-fails. If a step fails, it falls back gracefully:

```
Market Research fails entirely
    → Use V1 CSV rates as fallback
    → Flag all rates as "fallback — market data unavailable"
    → Continue to Cost Calc

Market Research partially fails (some components found, some not)
    → Use live rates where found
    → Use V1 CSV rates for gaps
    → Flag each gap line item individually

Location Intel fails
    → Use national average rates
    → Flag as "location premium not applied — data unavailable"

IRA Agent fails
    → Note "IRA calculation unavailable — consult tax advisor"
    → Continue with base estimate

Benchmark Validation fails
    → Output estimate without validation note
    → Log the failure internally
```

---

## Benchmark Validation Modes

Controlled by a single config flag:

```python
# config.py
BENCHMARK_MODE = "auto"    # validates every V2 run silently
BENCHMARK_MODE = "manual"  # only when user explicitly asks
```

**AUTO mode:**
- PASS (V2 within ±15% of V1): user sees clean estimate only
- WARN (15–40% delta or low source quality): note appended to estimate
- FLAG (>40% delta or critical outlier): clear warning shown, manual review recommended

**MANUAL mode:**
- V2 estimate delivered immediately, no validation
- User says "compare" or "validate" → full comparison report

---

## Folder Structure (V2)

```
mycir_agent_ADK_v1/
├── capex_agent/                       ← V1 — DO NOT MODIFY
│   ├── __init__.py
│   ├── agent.py
│   ├── data/
│   │   └── system_price.csv
│   └── sub_agents/
│       ├── capex_estimation/
│       └── market_research/
│
├── mycir_agent/                       ← V2 — new package
│   ├── __init__.py
│   ├── agent.py                       ← MyCIR super agent (router)
│   ├── config.py                      ← BENCHMARK_MODE and other flags
│   └── sub_agents/
│       ├── capex_v2/
│       │   ├── __init__.py
│       │   ├── agent.py               ← Capex SequentialAgent orchestrator
│       │   ├── project_intake/
│       │   │   └── agent.py
│       │   ├── input_validation/
│       │   │   ├── agent.py
│       │   │   └── tools.py
│       │   ├── system_design/
│       │   │   ├── agent.py
│       │   │   └── tools.py           ← inverter logic, panel count, BOM
│       │   ├── market_research_v2/
│       │   │   └── agent.py
│       │   ├── location_intel/
│       │   │   └── agent.py
│       │   ├── ira_incentive/
│       │   │   ├── agent.py
│       │   │   └── tools.py
│       │   ├── cost_calculation_v2/
│       │   │   ├── agent.py
│       │   │   └── tools.py           ← all math, no CSV dependency
│       │   ├── scenario/
│       │   │   └── agent.py
│       │   ├── export/
│       │   │   ├── agent.py
│       │   │   └── tools.py           ← Excel, PDF generation
│       │   └── benchmark_validation/
│       │       ├── agent.py           ← orchestrator
│       │       ├── v1_runner/
│       │       │   └── agent.py       ← read-only wrapper for V1 tools
│       │       └── comparison_report/
│       │           └── agent.py
│       │
│       └── (future packages per service roadmap — e.g. development, engineering
│           layouts, procurement, o_and_m — see docs/01_project_overview.md)
│
├── docs/                              ← all project documentation
├── benchmark_log/                     ← append-only benchmark run history
│   └── benchmark_log.jsonl
├── export_data.py                     ← V1 utility, unchanged
├── main.py
└── pyproject.toml
```
