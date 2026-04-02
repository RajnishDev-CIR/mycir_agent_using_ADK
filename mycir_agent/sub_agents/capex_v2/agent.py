from typing import Optional

from google.adk.agents import LlmAgent, ParallelAgent, SequentialAgent
from google.adk.agents.callback_context import CallbackContext
from google.genai import types
from google.adk.tools import BaseTool, ToolContext

from .project_intake.agent import project_intake_agent
from .input_validation.agent import input_validation_agent
from .system_design.agent import system_design_agent
from .market_research_v2.agent import market_research_v2_agent
from .location_intel.agent import location_intel_agent
from .ira_incentive.agent import ira_incentive_agent
from .cost_calculation_v2.agent import cost_calculation_agent_v2
from .benchmark_validation.agent import benchmark_validation_agent


# ---------------------------------------------------------------------------
# Pipeline gates
# ---------------------------------------------------------------------------

def _silent_skip_content() -> types.Content:
    """Return an effectively empty response when skipping an agent."""
    return types.Content(parts=[types.Part(text="")])


def _is_missing(value) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip().lower() in ("", "none", "null", "n/a", "na", "[blank]")
    return False


def _project_ready_for_validation(state) -> bool:
    """Whether intake has enough fields for validation to run."""
    project = state.get("project")
    if not isinstance(project, dict):
        return False

    required = (
        "project_name",
        "location_state",
        "location_county",
        "cod",
        "dc_mwp",
        "ac_kw",
        "poi_voltage",
        "installation_type",
    )
    for key in required:
        value = project.get(key)
        if key == "location_county" and isinstance(value, str) and value.strip().lower() == "unspecified":
            continue
        if _is_missing(value):
            return False
    if str(project.get("installation_type", "")).upper() == "GM":
        structure = str(project.get("structure_type", "")).strip().lower()
        if structure not in ("fixed_tilt", "sat"):
            return False
    return True


def _skip_until_project_ready(
    callback_context: CallbackContext,
) -> Optional[types.Content]:
    """Pause execution pipeline until intake has mandatory project fields."""
    if not _project_ready_for_validation(callback_context.state):
        # Set a sentinel block so downstream agents never run on partial intake.
        callback_context.state["validation"] = {
            "status": "block",
            "warnings": [],
            "block_reason": "Waiting for mandatory intake fields before validation.",
        }
        callback_context.actions.skip_summarization = True
        return _silent_skip_content()
    return None


def _skip_if_validation_blocked(
    callback_context: CallbackContext,
) -> Optional[types.Content]:
    """Skip the agent unless validation explicitly passed or warned.

    Three scenarios that block:
      1. state['validation'] does not exist  → tool was never called
      2. state['validation'] is not a dict   → unexpected value
      3. status is 'block'                   → tool returned a block
    Only 'pass' and 'warn' allow the agent to proceed.
    """
    validation = callback_context.state.get("validation")
    if not isinstance(validation, dict) or validation.get("status") not in ("pass", "warn"):
        callback_context.actions.skip_summarization = True
        return _silent_skip_content()
    return None


# Apply the gate to every agent that should NOT run when inputs are missing.
for _agent in [
    system_design_agent,
    market_research_v2_agent,
    location_intel_agent,
    ira_incentive_agent,
    cost_calculation_agent_v2,
    benchmark_validation_agent,
]:
    _agent.before_agent_callback = _skip_if_validation_blocked


# Market research and location intel have no dependency on each other.
# Run them in parallel to cut latency (~12–18s vs ~25–35s sequential).
parallel_research = ParallelAgent(
    name="parallel_research",
    description="Runs market research and location intel simultaneously.",
    sub_agents=[
        market_research_v2_agent,
        location_intel_agent,
    ],
    before_agent_callback=_skip_if_validation_blocked,
)

# Full Capex V2 execution pipeline (runs only after intake is complete)
capex_execution_pipeline = SequentialAgent(
    name="capex_execution_pipeline",
    description=(
        "Executes CAPEX estimation after intake data is complete: validation, "
        "design, research, incentives, costing, and benchmark."
    ),
    before_agent_callback=_skip_until_project_ready,
    sub_agents=[
        input_validation_agent,      # 1. validate before spending API calls
        system_design_agent,         # 2. inverter type, panel count, transformer
        parallel_research,           # 3. market prices + location costs (parallel)
        cost_calculation_agent_v2,   # 4. all arithmetic → 15 line items, 3 bands
        ira_incentive_agent,         # 5. ITC based on final base-case CAPEX
        benchmark_validation_agent,  # 6. quality gate — pass/warn/flag vs V1
    ],
)

CAPEX_ORCHESTRATOR_INSTRUCTION = """
You orchestrate the CAPEX V2 flow in phases.

Agents:
- project_intake_agent: collect/confirm project inputs and preferences.
- capex_execution_pipeline: run full estimation after intake is complete.

Rules:
1) First, check whether project intake is complete using these mandatory fields:
   project_name, location_state, location_county, cod, dc_mwp, ac_kw,
   poi_voltage, installation_type.
2) If ANY mandatory field is missing, delegate ONLY to project_intake_agent.
3) Call capex_execution_pipeline ONLY when all mandatory fields are present.
4) Never run both phases in parallel.
5) Do not do CAPEX work yourself; only orchestrate delegation.
6) Keep responses user-friendly and transparent:
   - Briefly tell user which phase is running (intake or estimation).
   - Use simple progress wording like "collecting inputs", "running cost model",
     "finalizing summary".
"""


def _enforce_orchestrator_routing(
    tool: BaseTool, args: dict, tool_context: ToolContext
) -> dict | None:
    """
    Deterministically route transfer_to_agent based on session state.
    This prevents LLM mis-routing (e.g., sending incomplete intake to execution).
    """
    if tool.name != "transfer_to_agent":
        return None
    desired = (
        "capex_execution_pipeline"
        if _project_ready_for_validation(tool_context.state)
        else "project_intake_agent"
    )
    args["agent_name"] = desired
    return None

capex_agent_v2 = LlmAgent(
    name="capex_agent_v2",
    description=(
        "CAPEX V2 orchestrator. Runs intake first, then executes full estimation "
        "pipeline only after required inputs are collected."
    ),
    model="gemini-2.5-flash",
    instruction=CAPEX_ORCHESTRATOR_INSTRUCTION,
    sub_agents=[project_intake_agent, capex_execution_pipeline],
    before_tool_callback=_enforce_orchestrator_routing,
)
