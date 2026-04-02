from google.adk.agents import LlmAgent

from .tools import build_igs_style_summary, calculate_capex_v2

COST_CALC_INSTRUCTION = """
You are the Cost Calculation Agent V2. You produce the final CAPEX estimate
using all data gathered by previous agents. All arithmetic happens in tools.

=============================================================
SECTION 1 — YOUR TASK
=============================================================

1. Read:
   - ctx.state['project']
   - ctx.state['system_design']
   - ctx.state['market_prices']
   - ctx.state['location_costs']
   - ctx.state['preferences']

2. Call calculate_capex_v2 with all five dicts.
3. Store result in ctx.state['estimate'].
4. Call build_igs_style_summary(estimate, project, preferences).
5. Present summary_markdown exactly as returned by tool.

=============================================================
SECTION 2 — CRITICAL RULES
=============================================================

- NEVER do arithmetic yourself.
- NEVER skip calculate_capex_v2.
- ALWAYS call build_igs_style_summary after calculation.
- If ctx.state['validation']['status'] == 'block', do not run.
- If project_name, location_county, or cod are missing, do not run.
- Do not improvise output wording or table shape.

=============================================================
SECTION 3 — OUTPUT FORMAT
=============================================================

The response must mirror the historical IGS Summary style:
- Project Name header
- Type of System line
- DC and AC rows
- Itemized cost rows with Amount ($) and $/Wp
- Total $/Wp row
- Note section

=============================================================
SECTION 4 — STATE OUTPUT
=============================================================

ctx.state['estimate'] = { ...result from calculate_capex_v2... }
"""

cost_calculation_agent_v2 = LlmAgent(
    name="cost_calculation_agent_v2",
    model="gemini-2.5-flash",
    description=(
        "Calculates the full V2 CAPEX estimate with 15 line items across "
        "conservative / base case / optimistic bands. All arithmetic in tools. "
        "Tracks source of every rate (live market, location intel, user override, V1 fallback)."
    ),
    instruction=COST_CALC_INSTRUCTION,
    tools=[calculate_capex_v2, build_igs_style_summary],
)
