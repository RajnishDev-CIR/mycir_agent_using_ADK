# MyCIR Agent — Project Overview

## What Is MyCIR Agent?

MyCIR Agent is a multi-agent AI platform built on Google's Agent Development Kit (ADK) for
CIR (Cleantech Industry Resources) internal use. It provides intelligent, data-driven
decision support for renewable energy project development.

MyCIR is a **super-agent** — a top-level orchestrator that routes user requests to the
correct specialist agent. It has no domain knowledge of its own. It exists only to understand
user intent and delegate.

---

## Why We Built This

**Problem with manual estimation:**
- Engineers spend hours producing CAPEX estimates using Excel lookups
- Static CSV/Excel databases go stale — prices change quarterly
- Manual estimates miss location-specific costs (California prevailing wage,
  high-cost AHJ permitting, regional labour premiums)
- No systematic way to handle user preferences (specific manufacturers, FEOC compliance,
  IRA domestic content requirements)
- No record of how estimates were derived or what assumptions were made

**What MyCIR solves:**
- Live market research replaces static CSV rates
- Engineering logic built in — agent reasons about inverter type, tracker vs fixed, panel count
- Location intelligence — state labour premiums, AHJ costs, utility interconnection context
- User preferences propagated through the entire estimate
- Full audit trail on every output
- Benchmark validation catches outlier estimates before the user sees them

---

## Scope of V1 (Current — Reference Only)

V1 is the original CAPEX estimation agent. It:
- Uses a static CSV database of 32 pricing points
- Interpolates between points for project sizes not in the DB
- Has no live market research integration (market research sub-agent exists but was rarely used)
- Cannot handle FEOC compliance, prevailing wage, SAT vs fixed-tilt cost delta,
  or POI transformer costs
- No session persistence — every conversation starts from zero

V1 remains untouched and serves as the **baseline for benchmark validation**.

---

## Scope of V2 (This Design)

V2 replaces the CSV-lookup model with full live reasoning. It:
- Uses market research (Google Search) for all equipment prices
- Uses location intelligence for labour, permitting, and interconnection costs
- Applies engineering logic for system design decisions
- Handles user preferences (manufacturer, technology, budget orientation, compliance requirements)
- Produces confidence bands (low/mid/high) instead of false-precision point estimates
- Validates its own output against V1 baseline via Benchmark Validation Agent
- Persists session state across turns via ADK DatabaseSessionService

---

## Agent Hierarchy

```
MyCIR Agent  ←  super-agent, pure router
│
├── Capex Agent V2           ←  specialist: full cost estimation with live reasoning
│   ├── Project Intake Agent
│   ├── Input Validation Agent
│   ├── Engineering / System Design Agent
│   ├── Market Research Agent V2      (parallel)
│   ├── Location Intel Agent          (parallel)
│   ├── IRA / Incentive Agent
│   ├── Cost Calculation Agent V2
│   ├── Scenario Agent                (optional)
│   ├── Export Agent                  (optional)
│   └── Benchmark Validation Agent   ←  validation layer inside Capex
│       ├── V1 Runner
│       └── Comparison Report Agent
│
└── (Future specialists — see **Roadmap: agentic service integration** below)
```

---

## Roadmap: agentic service integration

This section reflects CIR automation leadership’s direction: evolve from **standard, linear workflows** toward **Agentic AI** — agents that reason, call tools, and make data-driven decisions throughout the renewable project lifecycle. The aim is not only to “automate tasks” but to build **autonomous capacity** that can compete in renewable energy services.

### Core objective

Develop a **suite of specialized agents** embedded in real service delivery. Each agent should:

- Take **high-level objectives** (example: *prepare a bid-ready estimate for a 50 MW site in Texas*) and break them into actionable sub-tasks.
- **Execute** those sub-tasks using internal systems and external information.
- **Verify** results against **historical data** and benchmarks where CIR has them (e.g. estimation vs past estimates and V1 baseline).

### Cross-cutting expectations (every agent)

| Theme | Expectation |
| --- | --- |
| **Tooling** | Agents are **expertly calibrated** to **internal APIs** — implement APIs where they do not exist yet — and to **external search** (and other retrieval) where market or regulatory facts are required. |
| **Quality** | **Reasoning loops** and **self-correction**: the agent should **audit its own output** for logical inconsistencies before presenting results. |
| **Governance** | **Human-in-the-loop (HITL)**: specialists can **approve or adjust** agent-generated data before it reaches a **client-facing** deliverable. |

### Service integration scopes

Priority and sequencing are for Automation, Operations, and leadership to confirm. **Autonomous preliminary CAPEX / estimation** is a natural first bet alongside this repo; **Development** or **Engineering** are equally valid starting points if resourcing and dependencies favor them.

#### Development (lead origination)

- Pull **GIS**, **ownership**, **capacity estimates**, and related inputs autonomously.
- Assess **site feasibility** against the parameters CIR already uses for **lead origination**.
- Produce a **compiled spreadsheet** (or equivalent) in **predefined formats** the business already expects.
- CIR already has a **documented lead-origination workflow**; the goal is to **reimplement that path as an agentic process**, not to reinvent the process from scratch.

#### Engineering (layouts and design support)

- Use **EPSA** (and existing engineering capabilities) to help **generate or initiate layouts** for **PV**, including **at least on the order of ~1 MW** projects and scaling up as the toolchain allows.
- Extend to **BESS** layout where the stack can support it; the **BESS layout tool developed for Fluence** is a practical reference for which components and patterns to expose to an agent.

#### Estimation (CAPEX and budgets)

- Move **beyond static spreadsheets** toward budgets built from **live market signals** plus CIR’s own discipline.
- **Coordinate with Operations** to obtain **preliminary CAPEX** and **detailed CAPEX** spreadsheets in current use, plus the **standard operating procedure (SoP)** for preparing them.
- Enrich that baseline with **validated datasets** available online.
- Deliver **at least preliminary estimation** in an **automated** way, with HITL review — **Capex Agent V2** in this codebase is the technical anchor for the estimation track.

#### Procurement (sourcing intelligence)

- Monitor **global supply chains** and **module / inverter price** movements.
- Track **tariffs** and related **regulatory or legal** changes that affect buying.
- **Flag opportunistic buying windows** that the team can **relay to customers**.
- Leadership expects this may require **substantial new work** but is **feasible** as a dedicated agent effort.

#### Operations & maintenance

Two complementary directions:

1. **Performance analytics** — Agents that ingest **SCADA / DAS** data, analyze performance, and produce **automated reports**. Depth of agentic automation can mirror lessons from prior **dashboard-style** client work (e.g. Participate-style engagements): the team decides how far to push autonomy vs assisted analysis.
2. **Field robotics (longer term)** — Use planned **quadruped** and **drone** capabilities for **performance assessment** and **active site reviews**, then turn assessments into **reports** and **equipment deficiency** signals at the back end.

### Planning and stakeholders

- Roadmap execution is intentionally **cross-functional**: touchpoints across **Automation**, **Operations**, **Engineering**, and service lines.
- Expect a **written plan of action** from automation leadership, discussion in the **regular automation forum** (e.g. weekly huddle), and — once the internal plan is stable — **review with broader leadership** as CIR’s process defines.

---

## Technology Stack

| Component | Technology |
|---|---|
| Agent framework | Google Agent Development Kit (ADK) v1.28+ |
| LLM | Gemini 2.5 Flash |
| Session persistence | ADK DatabaseSessionService (SQLite → upgrade to Cloud SQL in prod) |
| Market research | Google Search via ADK built-in tool |
| Package manager | uv |
| Language | Python 3.13 |
| Export | openpyxl (Excel), reportlab or weasyprint (PDF) |

---

## Project Status

| Component | Status |
|---|---|
| V1 CAPEX Agent | Complete — do not modify |
| MyCIR Super Agent | To build |
| Capex Agent V2 | To build |
| Benchmark Validation Agent | To build |
| Future specialists (Development, Engineering, Procurement, O&M) | Roadmap — see above |

---

## Key Principles

1. MyCIR Agent never does domain work — it only routes
2. All arithmetic happens in tools, never in LLM instructions
3. V1 code is never modified — it is the permanent benchmark baseline
4. Every rate in a V2 estimate cites its source
5. User preferences set in intake flow through every downstream agent
6. Agent never hard-fails — fallback chain ensures user always gets an estimate
