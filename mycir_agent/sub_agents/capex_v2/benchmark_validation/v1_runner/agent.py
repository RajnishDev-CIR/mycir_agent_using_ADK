import json
from google.adk.agents import LlmAgent

# Import V1 tools read-only — V1 code is never modified
from capex_agent.sub_agents.capex_estimation.tools import (
    get_pricing_rows,
    calculate_capex_estimate,
)


def run_v1_estimate(project: dict) -> dict:
    """
    Runs V1 estimation logic on the project using the same mandatory inputs.
    Uses V1's CSV database — no market research, no location adjustments.
    This produces the baseline for benchmark comparison.

    Args:
        project: dict with dc_mwp, ac_kw, installation_type,
                 project_name, location_state, location_county.

    Returns:
        V1 estimate result dict or error dict.
    """
    raw_installation_type = str(project.get("installation_type", "GM"))
    normalized = "".join(ch for ch in raw_installation_type.strip().lower() if ch.isalpha())
    installation_type = {
        "gm": "GM",
        "groundmount": "GM",
        "ground": "GM",
        "rt": "RT",
        "rooftop": "RT",
        "roof": "RT",
        "cp": "CP",
        "carport": "CP",
    }.get(normalized, raw_installation_type.strip().upper())
    dc_mwp = float(project.get("dc_mwp", 0))
    ac_kw = float(project.get("ac_kw", 0))
    project_name = str(project.get("project_name", "Benchmark Project"))
    location = f"{project.get('location_state', '')}, {project.get('location_county', '')}"

    # Step 1: get pricing rows from V1 database
    rows = get_pricing_rows(installation_type=installation_type, size_mwp=dc_mwp)

    if "error" in rows:
        return {"error": f"V1 lookup failed: {rows['error']}", "v1_run": False}

    # Step 2: calculate V1 estimate
    result = calculate_capex_estimate(
        lower_row_json=json.dumps(rows["lower_row"]),
        upper_row_json=json.dumps(rows["upper_row"]),
        interpolation_weight=rows["interpolation_weight"],
        dc_size_mwp=dc_mwp,
        ac_size_kw=ac_kw,
        installation_type=installation_type,
        project_name=project_name,
        location=location,
    )

    if "error" in result:
        return {"error": f"V1 calculation failed: {result['error']}", "v1_run": False}

    result["v1_run"] = True
    return result


V1_RUNNER_INSTRUCTION = """
You are the V1 Runner. Your only job is to run the V1 CAPEX estimation logic
on the current project and store the result for benchmark comparison.

=============================================================
SECTION 1 — YOUR TASK
=============================================================

1. Read ctx.state['project'].
2. Call run_v1_estimate(project).
3. Store result in ctx.state['benchmark']['v1_result'].

Do NOT present the V1 result to the user. It is for internal use only.

=============================================================
SECTION 2 — CRITICAL RULES
=============================================================

- NEVER show the V1 estimate to the user.
- NEVER modify V1 tools. They are imported read-only.
- If run_v1_estimate returns an error — store the error and continue.
  The comparison report agent will handle the missing V1 data gracefully.
- Do not apply any preferences, overrides, or location adjustments.
  V1 runs with mandatory fields only.

After storing, say nothing to the user. The next agent handles output.
"""

v1_runner_agent = LlmAgent(
    name="v1_runner_agent",
    model="gemini-2.5-flash",
    description=(
        "Runs V1 CSV-based estimation logic on the same project inputs. "
        "Result stored internally for benchmark comparison only — never shown to user."
    ),
    instruction=V1_RUNNER_INSTRUCTION,
    tools=[run_v1_estimate],
)
