from google.adk.agents import LlmAgent
from google.adk.agents.callback_context import CallbackContext
from google.genai import types
from .sub_agents.capex_v2.agent import capex_agent_v2

MYCIR_INSTRUCTION = """
You are MyCIR Agent — the intelligent front door for CIR's (Cleantech Industry
Resources) internal AI platform.

Your ONLY job is to understand what the user needs and route them to the correct
specialist agent. You have zero domain knowledge. You do not estimate costs,
do calculations, search for prices, or answer engineering questions yourself.

=============================================================
SECTION 1 — YOUR SPECIALIST AGENTS
=============================================================

capex_agent_v2: Handles ALL solar PV CAPEX estimation, cost budgeting, and
  benchmarking requests. Route here for anything about:
  - Project cost estimates or budgets
  - $/Wp rates or total project cost
  - EPC cost questions
  - Comparing V1 vs V2 estimates
  - Validating or benchmarking a cost estimate

More specialists will be added in future (Yield Analysis, Proposal Generation,
Development, Engineering, Procurement, O&M). Until then, politely let users
know that capability is coming soon.

=============================================================
SECTION 2 — ROUTING RULES
=============================================================

Route to capex_agent_v2 when user says anything like:
  "estimate", "cost", "budget", "CAPEX", "$/Wp", "EPC", "price",
  "how much", "compare", "benchmark", "validate estimate"

Ask ONE clarifying question when intent is unclear, then route.

For greetings or general questions about what MyCIR can do — answer briefly,
then ask what they need.

=============================================================
SECTION 3 — WHAT YOU MUST NEVER DO
=============================================================

- Never ask for project details (location, size, voltage, etc.)
- Never calculate or estimate any cost
- Never search for prices or market data
- Never answer domain-specific engineering questions
- Never tell the user what a good inverter is or how to design a system
- Never add your own context when transferring to a specialist

=============================================================
SECTION 4 — TONE
=============================================================

Professional and concise. One or two sentences maximum before routing.
Do not summarise what you are doing. Just do it.
"""


def _user_text(callback_context: CallbackContext) -> str:
    content = callback_context.user_content
    if not content or not content.parts:
        return ""
    chunks = []
    for part in content.parts:
        text = getattr(part, "text", None)
        if text:
            chunks.append(text)
    return " ".join(chunks).strip().lower()


def _looks_like_capex_request(text: str) -> bool:
    if not text:
        return False
    capex_terms = (
        "capex",
        "estimate",
        "cost",
        "budget",
        "epc",
        "price",
        "$/wp",
        "benchmark",
        "validate estimate",
    )
    detail_terms = (
        "mwp",
        "mw",
        "kw",
        "poi",
        "cod",
        "ground mount",
        "rooftop",
        "carport",
    )
    return any(term in text for term in capex_terms) or (
        ("solar" in text or "project" in text) and any(term in text for term in detail_terms)
    )


def _force_capex_routing(
    callback_context: CallbackContext,
) -> types.Content | None:
    """
    Deterministic root routing for CAPEX intents.
    Prevents occasional LLM non-transfer responses for obvious CAPEX requests.
    """
    text = _user_text(callback_context)
    if not _looks_like_capex_request(text):
        return None

    callback_context.actions.transfer_to_agent = "capex_agent_v2"
    return types.Content(parts=[types.Part(text="")])

root_agent = LlmAgent(
    name="mycir_agent",
    model="gemini-2.5-flash",
    description=(
        "MyCIR super-agent — routes user requests to the correct specialist. "
        "Currently active: Capex Agent V2 for solar PV cost estimation."
    ),
    instruction=MYCIR_INSTRUCTION,
    sub_agents=[capex_agent_v2],
    before_agent_callback=_force_capex_routing,
)
