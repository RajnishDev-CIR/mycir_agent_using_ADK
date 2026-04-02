from google.adk.tools import ToolContext


def calculate_ira(
    project: dict,
    preferences: dict,
    system_design: dict,
    tool_context: ToolContext,
) -> dict:
    """
    Calculates applicable IRA (Inflation Reduction Act) tax credit components
    for the project. All logic is deterministic — no LLM arithmetic.

    Args:
        project: ctx.state['project'] — location, installation type, size.
        preferences: ctx.state['preferences'] — prevailing_wage, feoc_compliance,
                     ira_domestic_content.
        system_design: ctx.state['system_design'] — used for equipment context.

    Returns:
        Dict with ITC rate components, estimated value, and notes.
        Stored in ctx.state['ira_result'].
    """
    def _to_bool(value) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in ("true", "yes", "y", "1")
        if isinstance(value, (int, float)):
            return value != 0
        return False

    prevailing_wage = _to_bool(
        preferences.get("prevailing_wage", preferences.get("prevailing_wage_required", False))
    )
    feoc_compliance = _to_bool(preferences.get("feoc_compliance", False))
    ira_domestic_content = _to_bool(preferences.get("ira_domestic_content", False))
    dc_mwp = float(project.get("dc_mwp", 0))
    state = str(project.get("location_state", "")).upper()

    notes = []
    adder_notes = []

    # ── Base ITC ──────────────────────────────────────────────────────────────
    # 30% with prevailing wage + apprenticeship compliance
    # 6% without (base unbonus rate)
    if prevailing_wage:
        base_itc_pct = 30
        notes.append(
            "Base ITC: 30% — prevailing wage and apprenticeship requirements met."
        )
    else:
        base_itc_pct = 6
        notes.append(
            "Base ITC: 6% — prevailing wage NOT confirmed. "
            "To qualify for 30%, prevailing wage and apprenticeship requirements must be met. "
            "This reduces the credit significantly — confirm with tax advisor."
        )

    # ── Domestic content adder (+10%) ─────────────────────────────────────────
    domestic_content_adder = 0
    if ira_domestic_content and feoc_compliance:
        domestic_content_adder = 10
        adder_notes.append(
            "Domestic content adder: +10% — FEOC-compliant equipment selected "
            "and domestic content requirement confirmed. "
            "Verify manufacturer certificates before claiming."
        )
    elif ira_domestic_content and not feoc_compliance:
        adder_notes.append(
            "Domestic content adder: NOT applied — domestic content requested "
            "but FEOC compliance not confirmed. US-manufactured equipment "
            "(Qcells GA, First Solar OH) typically qualifies. Confirm with procurement."
        )
    elif feoc_compliance and not ira_domestic_content:
        adder_notes.append(
            "Note: FEOC-compliant equipment selected. You may also qualify for "
            "the +10% domestic content adder — confirm with tax advisor."
        )

    # ── Energy community adder (+10%) ─────────────────────────────────────────
    # This requires checking the DOE energy communities map — flagged for agent to search
    energy_community_adder = 0
    energy_community_note = (
        "Energy community adder: requires manual check at energycommunities.gov. "
        "If the project site qualifies (brownfield, coal community, or high fossil fuel "
        "employment area), an additional +10% ITC applies. "
        "Not included in this estimate — confirm separately."
    )
    adder_notes.append(energy_community_note)

    # ── Total ITC ─────────────────────────────────────────────────────────────
    total_itc_pct = base_itc_pct + domestic_content_adder + energy_community_adder

    # ── Estimated ITC value ───────────────────────────────────────────────────
    # Prefer actual base-case CAPEX from cost calculation when available.
    estimate = tool_context.state.get("estimate")
    base_case_total_usd = None
    base_case_per_wp = None
    if isinstance(estimate, dict):
        base_case = estimate.get("base_case")
        if isinstance(base_case, dict):
            total_usd = base_case.get("total_usd")
            per_wp = base_case.get("total_per_wp")
            if isinstance(total_usd, (int, float)):
                base_case_total_usd = float(total_usd)
            if isinstance(per_wp, (int, float)):
                base_case_per_wp = float(per_wp)

    if base_case_total_usd is not None and base_case_per_wp is not None:
        gross_capex_usd = base_case_total_usd
        gross_capex_per_wp = base_case_per_wp
        capex_source = "base_case_estimate"
        capex_note = "ITC estimate uses calculated base-case CAPEX."
    else:
        # Fallback when estimate is not yet available.
        gross_capex_per_wp = 1.80
        gross_capex_usd = gross_capex_per_wp * dc_mwp * 1_000_000
        capex_source = "rough_placeholder"
        capex_note = (
            "ITC estimate uses rough CAPEX placeholder. Recompute after final CAPEX."
        )

    estimated_itc_usd = gross_capex_usd * (total_itc_pct / 100)
    estimated_net_per_wp = gross_capex_per_wp * (1 - total_itc_pct / 100)

    # ── State-specific notes ──────────────────────────────────────────────────
    state_note = ""
    if state == "CA":
        state_note = (
            "California: No additional state ITC. "
            "Self-Generation Incentive Program (SGIP) available for storage. "
            "Check CPUC programs for project-specific incentives."
        )
    elif state == "NY":
        state_note = (
            "New York: NY-Sun incentive program available. "
            "Check NYSERDA for current commercial solar incentives."
        )
    elif state == "MA":
        state_note = (
            "Massachusetts: SMART program (Solar Massachusetts Renewable Target) "
            "provides production incentives. Check Eversource/National Grid territories."
        )

    return {
        "base_itc_pct": base_itc_pct,
        "domestic_content_adder_pct": domestic_content_adder,
        "energy_community_adder_pct": energy_community_adder,
        "total_itc_pct": total_itc_pct,
        "prevailing_wage_confirmed": prevailing_wage,
        "domestic_content_confirmed": ira_domestic_content and feoc_compliance,
        "estimated_gross_capex_usd": round(gross_capex_usd),
        "estimated_itc_value_usd": round(estimated_itc_usd),
        "estimated_net_per_wp_after_itc": round(estimated_net_per_wp, 3),
        "capex_basis": capex_source,
        "capex_basis_note": capex_note,
        "notes": notes + adder_notes,
        "state_incentive_note": state_note,
        "disclaimer": (
            "ITC estimate is preliminary and policy-dependent. "
            "Verify final eligibility and filing treatment with a qualified tax advisor. "
            "Consult a qualified tax advisor to confirm eligibility and amounts."
        ),
    }
