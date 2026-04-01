# ADK Technical Design

Implementation decisions specific to Google Agent Development Kit (ADK) v1.28+.

---

## Session Persistence

### Problem with V1
V1 uses in-memory session (`InMemorySessionService` — ADK default).
Every conversation starts from zero. No state persists between turns
or across browser refreshes.

### V2 Solution: DatabaseSessionService

```python
# mycir_agent/config.py
from google.adk.sessions import DatabaseSessionService

session_service = DatabaseSessionService(
    db_url="sqlite:///mycir_sessions.db"    # local dev
    # db_url="postgresql://..."             # production
)
```

**What this gives us:**
- Project data survives across multiple user turns
- User can say "re-run Solar Farm ABC with updated module price" — agent loads the project
- Agent resumes from exact state if a call times out or fails
- All `ctx.state` changes are persisted automatically via event delta tracking

**State scoping:**
```
app_name:  "mycir_agent"
user_id:   "user"  (expand to real user IDs in multi-user production)
session_id: auto-generated UUID per conversation
```

---

## Agent Communication Pattern

All inter-agent data flows through `ctx.state`. Never pass data directly
between agents via function arguments.

```python
# Intake Agent sets project data
ctx.state['project'] = {
    "name": "xyz",
    "location": "CA, Los Angeles",
    "dc_mwp": 5.0,
    ...
}

# Engineering Agent reads it
project = ctx.state['project']

# Engineering Agent writes its output
ctx.state['system_design'] = design_system(project, preferences)
```

**Temp state (within-invocation only, not persisted):**
```python
ctx.state['temp:raw_search_result'] = search_output
# temp: prefix is automatically stripped after invocation ends
```

---

## Parallel Agent for Market Research + Location Intel

Market Research and Location Intel have no dependency on each other.
They should run simultaneously using ADK's `ParallelAgent`.

```python
from google.adk import ParallelAgent

parallel_research = ParallelAgent(
    name="parallel_research",
    sub_agents=[
        market_research_agent_v2,
        location_intel_agent,
    ]
)
```

Each sub-agent in a `ParallelAgent` receives an isolated branch context.
Their outputs are merged into the parent `ctx.state` when both complete.

**Expected latency improvement:**
- Sequential: ~20–30 seconds (2 × google search + processing)
- Parallel: ~12–18 seconds (run simultaneously)

---

## Sequential Agent for Capex Pipeline

```python
from google.adk import SequentialAgent

capex_agent_v2 = SequentialAgent(
    name="capex_agent_v2",
    sub_agents=[
        project_intake_agent,
        input_validation_agent,
        system_design_agent,
        parallel_research,          # ParallelAgent (market research + location intel)
        ira_incentive_agent,
        cost_calculation_agent_v2,
        benchmark_validation_agent, # conditional on BENCHMARK_MODE
    ]
)
```

**Resumability:** If the pipeline is interrupted mid-way (e.g. timeout during
market research), ADK's `DatabaseSessionService` tracks `current_sub_agent`
state and resumes from the correct step on the next call.

---

## Error Callbacks

### Tool Error Fallback

```python
def on_tool_error_fallback(tool, args, ctx, error):
    """
    Called when any tool raises an exception.
    Returns a fallback result instead of propagating the error.
    """
    if tool.name == "google_search":
        # Market research failed — return empty result, Cost Calc will use V1 fallback
        return {
            "results": [],
            "error": str(error),
            "fallback": True
        }
    if tool.name in ["get_pricing_rows", "calculate_capex_estimate"]:
        # V1 tools failed in Benchmark — skip benchmark, don't block estimate
        return {
            "error": str(error),
            "benchmark_skipped": True
        }
    # All other tools: re-raise
    raise error
```

Applied to all agents:
```python
agent = LlmAgent(
    ...
    on_tool_error_callback=on_tool_error_fallback,
)
```

### Model Error Fallback

```python
def on_model_error(callback_context, llm_request, error):
    """
    Called if the LLM call itself fails (rate limit, timeout, etc.)
    Returns a minimal LlmResponse to keep the pipeline going.
    """
    # Log the error
    print(f"Model error in {callback_context.agent_name}: {error}")
    # Return a safe fallback response
    from google.adk.models import LlmResponse
    return LlmResponse(
        content=f"Agent {callback_context.agent_name} encountered an error. "
                f"Proceeding with available data."
    )
```

---

## Safety: max_llm_calls

Prevent runaway agent loops by setting a hard cap on LLM calls per invocation:

```python
from google.adk.runners import RunConfig

run_config = RunConfig(
    max_llm_calls=50    # hard stop — prevents infinite loops
)
```

This is especially important during development when agent instructions
may accidentally cause the agent to loop (e.g. repeatedly calling a sub-agent).

---

## AgentTool Pattern

Sub-agents are exposed to parent agents as tools using `AgentTool`.
This is the correct ADK pattern — do not call `agent.run_async()` directly.

```python
from google.adk.tools import agent_tool

# In MyCIR Agent definition
capex_tool = agent_tool.AgentTool(agent=capex_agent_v2)
mycir_agent = LlmAgent(
    name="mycir_agent",
    tools=[capex_tool],    # capex_agent is callable as a tool
    ...
)
```

`AgentTool` automatically:
- Extracts input/output schemas from the sub-agent
- Propagates session context and state
- Handles the transfer_to_agent mechanism

---

## Observability: OpenTelemetry Tracing

ADK instruments all agent invocations automatically with OpenTelemetry.
Every run has:
- `invocation_id` — unique per conversation turn
- `branch` — tracks which sub-agent path was taken
- Tool call timing — shows how long each search or calculation took

**Export traces for monitoring (add to app startup):**
```python
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

# Send to any OTLP-compatible backend (Grafana, Jaeger, Cloud Trace, etc.)
provider = TracerProvider()
provider.add_span_processor(
    SimpleSpanProcessor(OTLPSpanExporter(endpoint="http://localhost:4317"))
)
trace.set_tracer_provider(provider)
```

This gives full visibility into:
- Which agents ran and in what order
- How long each market research call took
- Where the pipeline is slowest
- Which tool calls fail most often

---

## Config File Structure

```python
# mycir_agent/config.py

# Benchmark behaviour
BENCHMARK_MODE = "auto"   # "auto" | "manual"

# Session storage
SESSION_DB_URL = "sqlite:///mycir_sessions.db"   # override with env var in prod

# Safety caps
MAX_LLM_CALLS = 50

# Market research freshness threshold (days)
MAX_SOURCE_AGE_DAYS = 90

# Validation thresholds
BENCHMARK_FLAG_THRESHOLD_PCT = 40    # flag if V2 differs from V1 by more than this
BENCHMARK_WARN_THRESHOLD_PCT = 15    # warn if V2 differs from V1 by more than this
BENCHMARK_BLOCK_TOTAL_LOW = 0.50     # $/Wp below this is a calculation error
BENCHMARK_BLOCK_TOTAL_HIGH = 8.00    # $/Wp above this is a calculation error
```

All thresholds in one place — easy to tune as V2 matures.

---

## Build Order for Implementation

Follow this order to enable testing at each step:

1. `mycir_agent/config.py` — config first
2. `mycir_agent/agent.py` — MyCIR router (can test routing immediately)
3. `capex_v2/project_intake/agent.py` — test intake collection
4. `capex_v2/input_validation/agent.py + tools.py` — test validation rules
5. `capex_v2/system_design/agent.py + tools.py` — test all engineering logic
6. `capex_v2/market_research_v2/agent.py` — test search + structured output
7. `capex_v2/location_intel/agent.py` — test location-specific searches
8. `capex_v2/ira_incentive/agent.py + tools.py` — test IRA calculation
9. `capex_v2/cost_calculation_v2/agent.py + tools.py` — test full arithmetic
10. `capex_v2/benchmark_validation/v1_runner/agent.py` — test V1 wrapper
11. `capex_v2/benchmark_validation/comparison_report/agent.py` — test diff logic
12. `capex_v2/benchmark_validation/agent.py` — wire benchmark orchestrator
13. `capex_v2/agent.py` — wire full SequentialAgent
14. Run end-to-end test with session from doc 05 (the V1 problem session)
15. `capex_v2/scenario/agent.py` — add scenario comparison
16. `capex_v2/export/agent.py + tools.py` — add export
