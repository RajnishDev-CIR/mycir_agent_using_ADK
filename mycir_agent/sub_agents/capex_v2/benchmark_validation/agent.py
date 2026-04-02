from google.adk.agents import SequentialAgent, LlmAgent
from mycir_agent.config import BENCHMARK_MODE
from .v1_runner.agent import v1_runner_agent
from .comparison_report.agent import comparison_report_agent

BENCHMARK_SKIP_INSTRUCTION = """
Benchmark validation is set to MANUAL mode.
Do nothing. Do not output anything to the user.
The estimate has already been presented by the Cost Calculation Agent.

If the user explicitly asks to "compare", "benchmark", or "validate"
the estimate, tell them:
"To run a benchmark comparison against V1, please mention 'compare with V1'
at the start of your next request and I will run both and show the difference."
"""

if BENCHMARK_MODE == "auto":
    benchmark_validation_agent = SequentialAgent(
        name="benchmark_validation_agent",
        description=(
            "Validation layer — runs V1 silently, compares with V2, "
            "appends pass/warn/flag note to estimate output."
        ),
        sub_agents=[v1_runner_agent, comparison_report_agent],
    )
else:
    # Manual mode — skip validation silently
    benchmark_validation_agent = LlmAgent(
        name="benchmark_validation_agent",
        model="gemini-2.5-flash",
        description="Benchmark validation in MANUAL mode — inactive unless user requests comparison.",
        instruction=BENCHMARK_SKIP_INSTRUCTION,
    )
