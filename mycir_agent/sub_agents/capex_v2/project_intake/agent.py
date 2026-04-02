from typing import Any

from google.adk.agents import LlmAgent
from google.adk.agents.callback_context import CallbackContext
from google.genai import types

from .tools import upsert_intake_state

INTAKE_INSTRUCTION = """
You are the Project Intake Agent for CIR CAPEX V2.
Goal: collect required inputs with good UX and keep session state updated.

CRITICAL WORKFLOW (every turn):
1) Extract all known values from conversation + current user message.
2) Call tool upsert_intake_state(project_json, preferences_json) exactly once
   each turn using VALID JSON OBJECT STRINGS.
   - Example project_json:
     "{\"project_name\":\"Test\",\"location_state\":\"CA\",\"location_county\":null,\"dc_mwp\":\"5MWp\"}"
   - Example preferences_json:
     "{\"feoc_compliance\":true,\"prevailing_wage\":true}"
3) Read tool response:
   - ready_for_handoff (bool)
   - missing_mandatory_fields (list)
4) If ready_for_handoff is false:
   - Ask only missing mandatory fields.
   - Do NOT repeat full form on follow-ups.
5) If ready_for_handoff is true:
   - Briefly confirm capture; handoff is handled by callback.

UX FORMAT:
- First intake message:
  MANDATORY (required to run), OPTIONAL, RECOMMENDED sections.
- Follow-up messages:
  "Captured so far: ..."
  "MANDATORY (required to run):"
  - missing_field_1
  - missing_field_2

MANDATORY keys:
project_name, location_state, location_county, cod, dc_mwp, ac_kw,
installation_type, poi_voltage.
For GM, structure_type is also mandatory.

Normalization expectations:
- Accept county alias "LA" as Los Angeles County.
- RT/CP structure auto fixed_tilt.
- DC/AC units may be provided as KW/MW strings.
"""


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip().lower() in ("", "none", "null", "n/a", "na", "[blank]")
    return False


def _project_ready_for_handoff(state) -> bool:
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

    if str(project.get("installation_type", "")).strip().upper() == "GM":
        structure = str(project.get("structure_type", "")).strip().lower()
        if structure not in ("fixed_tilt", "sat"):
            return False
    return True


def _auto_handoff_after_intake(
    callback_context: CallbackContext,
) -> types.Content | None:
    """
    Deterministic handoff: once intake is complete, transfer directly to the
    CAPEX execution pipeline without relying on model-generated transfer calls.
    """
    if not _project_ready_for_handoff(callback_context.state):
        return None

    callback_context.actions.transfer_to_agent = "capex_execution_pipeline"
    # Do not return content here; returning final content can stop chain execution
    # before the transfer runs.
    return None

project_intake_agent = LlmAgent(
    name="project_intake_agent",
    model="gemini-2.5-flash",
    description=(
        "Collects all project inputs and user preferences. Extracts data "
        "already provided in the conversation before asking for anything. "
        "Stores structured project and preferences dicts to session state."
    ),
    instruction=INTAKE_INSTRUCTION,
    after_agent_callback=_auto_handoff_after_intake,
    disallow_transfer_to_parent=True,
    disallow_transfer_to_peers=False,
    tools=[upsert_intake_state],
)
