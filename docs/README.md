# MyCIR Agent — Documentation Index

This folder contains all design and technical documentation for the MyCIR Agent project.

---

## Documents

| # | Document | What it covers |
|---|---|---|
| 01 | [Project Overview](01_project_overview.md) | What MyCIR is, why we built it, V1 vs V2 scope, agent hierarchy, tech stack |
| 02 | [Architecture V2](02_architecture_v2.md) | Full agent hierarchy diagram, orchestration order, data flow, folder structure |
| 03 | [Agent Specifications](03_agent_specifications.md) | Every agent: role, inputs, outputs, tools, failure behaviour |
| 04 | [Engineering Logic](04_engineering_logic.md) | Inverter type selection, structure type, DC/AC ratio, panel count, transformer, BOM |
| 05 | [V1 Lessons Learned](05_v1_lessons_learned.md) | All V1 problems found in real sessions and exact V2 fixes |
| 06 | [Benchmark Validation](06_benchmark_validation.md) | How V1 vs V2 comparison works, flag/warn/pass logic, benchmark log format |
| 07 | [ADK Technical Design](07_adk_technical_design.md) | Session persistence, parallel agents, error callbacks, observability, build order |
| 08 | [Compliance & Regulatory](08_compliance_regulatory.md) | FEOC, prevailing wage, IRA tax credits, CA-specific, tariffs, interconnection |

---

## Quick Reference

### Key Design Decisions

| Decision | Rationale |
|---|---|
| MyCIR Agent has zero domain knowledge | Clean separation — adding future agents requires only a routing rule |
| Benchmark inside Capex, not under MyCIR | It is a quality gate for Capex output, not a standalone feature |
| All arithmetic in tools, never LLM | Accuracy, auditability, determinism |
| V1 code never modified | Permanent stable baseline for benchmark |
| Parallel agents for Market Research + Location Intel | No dependency between them — run simultaneously to cut latency |
| DatabaseSessionService | Session state persists across turns — no re-asking for known data |
| Confidence bands (low/mid/high) | Point estimates imply false precision — ranges are industry standard |

### V1 Problems Fixed in V2

| V1 Problem | Doc |
|---|---|
| FEOC compliance ignored | [05](05_v1_lessons_learned.md), [08](08_compliance_regulatory.md) |
| Prevailing wage not quantified | [05](05_v1_lessons_learned.md), [08](08_compliance_regulatory.md) |
| SAT same racking rate as fixed tilt | [05](05_v1_lessons_learned.md), [04](04_engineering_logic.md) |
| POI transformer not costed | [05](05_v1_lessons_learned.md), [04](04_engineering_logic.md) |
| Context re-asked each turn | [05](05_v1_lessons_learned.md), [07](07_adk_technical_design.md) |
| Market research never called for gaps | [05](05_v1_lessons_learned.md), [03](03_agent_specifications.md) |

### Agent Responsibilities at a Glance

```
MyCIR Agent            →  route only
Project Intake         →  collect all inputs + preferences
Input Validation       →  catch bad inputs early
Engineering Agent      →  inverter type, structure, panel count, BOM
Market Research V2     →  live equipment prices (parallel)
Location Intel         →  labour rates, AHJ, incentives (parallel)
IRA / Incentive        →  ITC rate, domestic content, energy community
Cost Calc V2           →  all arithmetic → low/mid/high output
Benchmark Validation   →  quality gate → flag/warn/pass
Scenario Agent         →  compare 2-3 options side by side
Export Agent           →  Excel / PDF on request
```

---

## Status

| Component | Status |
|---|---|
| V1 CAPEX Agent | Complete — do not modify |
| Documentation (this folder) | Complete |
| MyCIR Agent V2 code | To build — see [07](07_adk_technical_design.md) for build order |
