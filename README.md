# MyCIR Agent — ADK Multi-Agent Platform

AI-powered renewable energy project intelligence built on Google Agent Development Kit (ADK).

---

## Architecture

```
MyCIR Agent  (super-agent — routes to specialists)
│
├── Capex Agent V2            ← active
│   ├── Project Intake Agent
│   ├── Input Validation Agent
│   ├── Engineering / System Design Agent
│   ├── Market Research Agent V2   (parallel)
│   ├── Location Intel Agent       (parallel)
│   ├── IRA / Incentive Agent
│   ├── Cost Calculation Agent V2
│   ├── Scenario Agent
│   ├── Export Agent
│   └── Benchmark Validation Agent
│       ├── V1 Runner
│       └── Comparison Report Agent
│
└── (Future specialists — Development, Engineering, Procurement, O&M;
     see docs/01_project_overview.md)
```

V1 (`capex_agent/`) is preserved as the benchmark baseline — do not modify.

CIR’s broader **agentic AI** goals (autonomous capacity, five service scopes, APIs + search, self-correction, HITL, and planning expectations) are summarized in [docs/01_project_overview.md](docs/01_project_overview.md#roadmap-agentic-service-integration).

---

## Quick Start

```bash
# Install dependencies
uv sync

# Run MyCIR Agent V2 (web UI)
uv run adk web

# Run MyCIR Agent V2 (terminal)
uv run adk run mycir_agent

# Run V1 only (benchmark baseline)
uv run adk run capex_agent
```

---

## Benchmark Mode

Controls whether V2 validates against V1 on every run.

```python
# mycir_agent/config.py
BENCHMARK_MODE = "auto"    # validates every run silently (default during development)
BENCHMARK_MODE = "manual"  # only when user explicitly asks to compare
```

---

## Environment Setup

Create `.env` in the project root:

```
GOOGLE_GENAI_USE_VERTEXAI=FALSE
GOOGLE_API_KEY=your_gemini_api_key
```

---

## Package Management

```bash
# Add a new package
uv add package-name

# Remove a package
uv remove package-name

# Sync after pulling from git or pyproject.toml changes
uv sync
```

---

## Folder Structure

```
mycir_agent_ADK_v1/
├── capex_agent/                    ← V1 — DO NOT MODIFY (benchmark baseline)
│   ├── __init__.py
│   ├── agent.py
│   ├── data/
│   │   └── system_price.csv
│   └── sub_agents/
│       ├── capex_estimation/
│       │   ├── agent.py
│       │   └── tools.py
│       └── market_research/
│           └── agent.py
│
├── mycir_agent/                    ← V2
│   ├── __init__.py
│   ├── agent.py                    ← MyCIR super agent
│   ├── config.py                   ← BENCHMARK_MODE and other flags
│   └── sub_agents/
│       ├── capex_v2/
│       │   ├── agent.py
│       │   ├── project_intake/
│       │   ├── input_validation/
│       │   ├── system_design/
│       │   ├── market_research_v2/
│       │   ├── location_intel/
│       │   ├── ira_incentive/
│       │   ├── cost_calculation_v2/
│       │   ├── scenario/
│       │   ├── export/
│       │   └── benchmark_validation/
│       │       ├── v1_runner/
│       │       └── comparison_report/
│       └── (future packages per service roadmap — see docs/01_project_overview.md)
│
├── docs/                           ← all project documentation
│   ├── README.md                   ← docs index
│   ├── 01_project_overview.md
│   ├── 02_architecture_v2.md
│   ├── 03_agent_specifications.md
│   ├── 04_engineering_logic.md
│   ├── 05_v1_lessons_learned.md
│   ├── 06_benchmark_validation.md
│   ├── 07_adk_technical_design.md
│   └── 08_compliance_regulatory.md
│
├── benchmark_log/
│   └── benchmark_log.jsonl         ← append-only internal performance log
│
├── export_data.py                  ← V1 utility, unchanged
├── pyproject.toml
├── uv.lock
└── README.md
```

---

## Documentation

**GitHub repository:** [github.com/RajnishDev-CIR/mycir_agent_using_ADK](https://github.com/RajnishDev-CIR/mycir_agent_using_ADK)

Full design docs are in [docs/](docs/). Start with [docs/README.md](docs/README.md).

| Doc | Covers |
|---|---|
| [01 Project Overview](docs/01_project_overview.md) | Vision, V1 vs V2, tech stack |
| [02 Architecture](docs/02_architecture_v2.md) | Agent hierarchy, data flow, folder structure |
| [03 Agent Specs](docs/03_agent_specifications.md) | Every agent: role, inputs, outputs, tools |
| [04 Engineering Logic](docs/04_engineering_logic.md) | Inverter selection, 1500V DC, panel count, BOM |
| [05 V1 Lessons](docs/05_v1_lessons_learned.md) | V1 problems found and V2 fixes |
| [06 Benchmark](docs/06_benchmark_validation.md) | Validation layer design, flag/warn/pass logic |
| [07 ADK Technical](docs/07_adk_technical_design.md) | Session, parallel agents, error callbacks |
| [08 Compliance](docs/08_compliance_regulatory.md) | FEOC, prevailing wage, IRA credits, CA specifics |
| [09 Hosting & feedback](docs/09_hosting_and_feedback.md) | GitHub Pages, MkDocs, Giscus comments |

**Published doc site (optional):** after pushing to GitHub, use `uv sync --group docs` and `uv run mkdocs serve` locally, or enable the **Deploy documentation** workflow — see [09](docs/09_hosting_and_feedback.md).
