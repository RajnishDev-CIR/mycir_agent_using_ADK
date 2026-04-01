# MyCIR Agent — Project Overview

## What Is MyCIR Agent?

MyCIR Agent is a multi-agent AI platform built on Google's Agent Development Kit (ADK) for
CIR (Clean Infrastructure & Renewables) internal use. It provides intelligent, data-driven
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
├── Yield Analysis Agent     ←  future
└── Proposal Gen Agent       ←  future
```

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
| Yield Analysis Agent | Future |
| Proposal Gen Agent | Future |

---

## Key Principles

1. MyCIR Agent never does domain work — it only routes
2. All arithmetic happens in tools, never in LLM instructions
3. V1 code is never modified — it is the permanent benchmark baseline
4. Every rate in a V2 estimate cites its source
5. User preferences set in intake flow through every downstream agent
6. Agent never hard-fails — fallback chain ensures user always gets an estimate
