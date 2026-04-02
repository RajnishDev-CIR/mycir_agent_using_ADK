"""
tools.py — CAPEX V2 cost calculation tool.

All arithmetic lives here. The LLM passes state dicts in and receives a
structured estimate dict back. No rounding happens at the LLM layer.

Key improvements vs V1:
  - Size-tiered rates from PostgreSQL pricing tables (not flat hardcoded values)
  - Engineering and permitting are FIXED USD costs by MW band, not $/Wp
  - Contingency and margin are size-tiered
  - 3 new line items: Step-up transformer, Prevailing wage premium, FEOC premium
  - Bonding added as line item 16
  - Three bands: conservative / base_case / optimistic
  - Every line item carries a source field: live_market | location_intel | db_rates | fallback
"""
import math

from .pricing_db import (
    get_system_rates,
    get_engineering_cost,
    get_permitting_cost,
    get_bonding_rate,
)

# FEOC compliance premium — mid-range estimate from Excel Ad Ons sheet
FEOC_PREMIUM_PER_WP = 0.055   # $0.03–0.08/Wp range; 0.055 mid

# Standard exclusions — consistent across V1 and V2
STANDARD_EXCLUSIONS = [
    "Bonding and sales & use tax shown as separate indicative lines",
    "Permitting costs subject to actual AHJ requirements; fixed estimate shown",
    "Utility application fees, impact studies, and interconnection upgrade costs excluded",
    "No third-party external study costs included",
    "Stamping: additional $500 per set",
    "Includes one mobilisation and one demobilisation",
    "POI location at inverter level only",
    "IRA tax credit value shown separately — not deducted from CAPEX",
    "All costs in USD; excludes import duties and tariffs unless noted",
]


def _normalize_installation_type(value: str) -> str:
    cleaned = "".join(ch for ch in value.strip().lower() if ch.isalpha())
    aliases = {
        "gm": "GM",
        "groundmount": "GM",
        "ground": "GM",
        "rt": "RT",
        "rooftop": "RT",
        "roof": "RT",
        "cp": "CP",
        "carport": "CP",
    }
    return aliases.get(cleaned, value.strip().upper())


def _to_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("true", "yes", "y", "1")
    if isinstance(value, (int, float)):
        return value != 0
    return False


def _get_market_price(market_prices: dict, component: str, band: str,
                      fallback_rate: float, structure_type: str = None,
                      fallback_rates: dict = None) -> tuple[float, str]:
    """
    Returns (price_per_wp, source) from market research or DB/fallback rates.
    band: 'low' | 'mid' | 'high'
    """
    record = market_prices.get(component, {})
    if record and not record.get("fallback", True) and record.get("confidence") in ("medium", "high"):
        val = record.get(band)
        if val and float(val) > 0:
            return float(val), "live_market"

    # DB/fallback rate — use SAT-specific racking if applicable
    if component == "racking" and structure_type == "SAT" and fallback_rates:
        sat_rate = fallback_rates.get("racking_sat")
        if sat_rate:
            return float(sat_rate), "db_rates"

    return float(fallback_rate), "db_rates" if fallback_rate else "fallback"


def calculate_capex_v2(
    project: dict,
    system_design: dict,
    market_prices: dict,
    location_costs: dict,
    preferences: dict,
) -> dict:
    """
    Calculates the full V2 CAPEX estimate with 16 line items, low/mid/high bands,
    and source tracking. All arithmetic happens here — the LLM does none of it.

    Line items:
      1.  Module supply
      2.  Inverter supply
      3.  Racking / structure
      4.  Balance of system (BOS)
      5.  Mechanical installation  (location-adjusted)
      6.  Electrical installation  (location-adjusted)
      7.  Civil works
      8.  Engineering              (fixed USD by MW band — NOT $/Wp)
      9.  Permitting               (fixed USD by MW band — NOT $/Wp)
      10. Step-up transformer      (new — V1 excluded)
      11. Prevailing wage premium  (new — V1 excluded)
      12. FEOC compliance premium  (new — V1 excluded)
      13. Overhead (SGA)
      14. Bonding                  (new — V1 excluded)
      15. Contingency              (size-tiered %)
      16. Margin                   (size-tiered %)

    Args:
        project:        ctx.state['project']
        system_design:  ctx.state['system_design']
        market_prices:  ctx.state['market_prices']
        location_costs: ctx.state['location_costs']
        preferences:    ctx.state['preferences']

    Returns:
        Full estimate dict for ctx.state['estimate'].
    """
    dc_mwp    = float(project.get("dc_mwp", 0))
    ac_kw     = float(project.get("ac_kw", 0))
    dc_watts  = dc_mwp * 1_000_000
    state     = project.get("location_state", "").upper()

    installation_type = _normalize_installation_type(str(project.get("installation_type", "GM")))
    structure_type    = system_design.get("structure_type", "fixed_tilt")
    inverter_type     = system_design.get("inverter_type", "string")
    inverter_count    = int(system_design.get("inverter_count", 0))
    panel_count       = int(system_design.get("panel_count", 0))
    transformer_req   = system_design.get("transformer_required", False)
    transformer_count = int(system_design.get("transformer_count", 0))
    transformer_ratio = system_design.get("transformer_voltage_ratio", "")

    labour_mult        = float(location_costs.get("labour_multiplier", 1.0))
    pw_premium_per_wp  = float(location_costs.get("prevailing_wage_premium_per_wp", 0.0))
    feoc_required      = _to_bool(preferences.get("feoc_compliance", False))
    pw_required        = _to_bool(
        preferences.get("prevailing_wage", preferences.get("prevailing_wage_required", False))
    )
    price_overrides    = preferences.get("price_overrides", {})

    # ── Pull size-tiered rates from DB (or fallback) ─────────────────────────
    rates = get_system_rates(installation_type, dc_mwp)
    eng   = get_engineering_cost(dc_mwp)
    perm  = get_permitting_cost(dc_mwp)
    bond  = get_bonding_rate(dc_mwp)

    rate_source_tag = "db_rates" if rates.get("source") == "db" else "fallback"

    results = {}

    for band in ("low", "mid", "high"):

        line_items:     list[dict] = []
        overrides_applied: list[str] = []
        fallbacks_used:    list[str] = []

        def _rate(component: str, base_rate: float, struct=None) -> tuple[float, str]:
            if component in price_overrides:
                overrides_applied.append(f"{component}: user override ${price_overrides[component]}/Wp")
                return float(price_overrides[component]), "user_override"
            return _get_market_price(market_prices, component, band, base_rate,
                                     struct, fallback_rates=rates)

        def _add(label: str, rate_wp: float, amount: float, source: str):
            line_items.append({
                "label":        label,
                "rate_per_wp":  round(rate_wp, 4),
                "amount_usd":   round(amount, 2),
                "source":       source,
            })

        # ── 1. Module supply ─────────────────────────────────────────────────
        mod_rate, mod_src = _rate("module", rates["module"])
        if mod_src == "db_rates": fallbacks_used.append("module")
        _add("Module supply", mod_rate, mod_rate * dc_watts, mod_src)

        # ── 2. Inverter supply ───────────────────────────────────────────────
        inv_rate, inv_src = _rate("inverter", rates["inverter"])
        if inv_src == "db_rates": fallbacks_used.append("inverter")
        _add(f"Inverter supply ({inverter_type.replace('_', ' ')})",
             inv_rate, inv_rate * dc_watts, inv_src)

        # ── 3. Racking / structure ───────────────────────────────────────────
        rack_base = (rates.get("racking_sat") or rates["racking"]) \
                    if structure_type == "SAT" else rates["racking"]
        rack_rate, rack_src = _rate("racking", rack_base, struct=structure_type)
        if rack_src == "db_rates": fallbacks_used.append("racking")
        struct_label = "Racking / structure (SAT)" if structure_type == "SAT" \
                       else "Racking / structure (fixed tilt)"
        _add(struct_label, rack_rate, rack_rate * dc_watts, rack_src)

        # ── 4. Balance of system (BOS) ───────────────────────────────────────
        bos_rate, bos_src = _rate("bos", rates["bos"])
        if bos_src == "db_rates": fallbacks_used.append("bos")
        _add("Balance of system (BOS)", bos_rate, bos_rate * dc_watts, bos_src)

        # ── 5. Mechanical installation (location-adjusted) ───────────────────
        mech_rate   = rates["mechanical"] * labour_mult
        mech_amount = mech_rate * dc_watts
        _add("Mechanical installation", mech_rate, mech_amount, "location_intel")

        # ── 6. Electrical installation (location-adjusted) ───────────────────
        elec_rate   = rates["electrical"] * labour_mult
        elec_amount = elec_rate * dc_watts
        _add("Electrical installation", elec_rate, elec_amount, "location_intel")

        # ── 7. Civil works ───────────────────────────────────────────────────
        civil_rate   = rates["civil"]
        civil_amount = civil_rate * dc_watts
        _add("Civil works", civil_rate, civil_amount, rate_source_tag)

        # ── 8. Engineering (FIXED USD by MW band — not $/Wp) ─────────────────
        eng_usd    = eng["total_usd"]
        eng_rate   = eng_usd / dc_watts if dc_watts else 0
        eng_source = "db_rates" if eng.get("source") == "db" else "fallback"
        _add("Engineering (design + substation)", eng_rate, eng_usd, eng_source)

        # ── 9. Permitting (FIXED USD by MW band — not $/Wp) ──────────────────
        # If location intel provided a specific figure, prefer it
        perm_intel = location_costs.get("permitting_cost_usd") or \
                     (location_costs.get("permitting_cost_per_wp", 0) * dc_watts
                      if location_costs.get("permitting_cost_per_wp") else 0)
        if perm_intel and float(perm_intel) > 0:
            perm_usd    = float(perm_intel)
            perm_source = "location_intel"
        else:
            perm_usd    = perm["total_usd"]
            perm_source = "db_rates" if perm.get("source") == "db" else "fallback"
        perm_rate = perm_usd / dc_watts if dc_watts else 0
        _add("Permitting (3rd party + AHJ)", perm_rate, perm_usd, perm_source)

        # ── 10. Step-up transformer (NEW — V1 excluded) ──────────────────────
        if transformer_req and transformer_count > 0:
            trans_record = market_prices.get("transformer", {})
            if trans_record and not trans_record.get("fallback", True):
                unit_cost = float(trans_record.get(band, 0))
                trans_src = "live_market"
            else:
                unit_cost = 120_000   # fallback: ~$120K per padmount unit
                trans_src = "fallback"
            trans_usd  = unit_cost * transformer_count
            trans_rate = trans_usd / dc_watts if dc_watts else 0
            _add(f"Step-up transformers ({transformer_count} units, {transformer_ratio})",
                 trans_rate, trans_usd, trans_src)

        # ── 11. Prevailing wage premium (NEW — V1 excluded) ──────────────────
        if pw_required and pw_premium_per_wp > 0:
            pw_amount = pw_premium_per_wp * dc_watts
            _add("Prevailing wage premium (Davis-Bacon)",
                 pw_premium_per_wp, pw_amount, "location_intel")

        # ── 12. FEOC compliance premium (NEW — V1 excluded) ──────────────────
        if feoc_required:
            feoc_amount = FEOC_PREMIUM_PER_WP * dc_watts
            _add("FEOC compliance premium (non-FEOC module adder)",
                 FEOC_PREMIUM_PER_WP, feoc_amount, "db_rates")

        # ── 13. Overhead / SGA ───────────────────────────────────────────────
        overhead_rate   = rates["overhead"] + rates["sga"]
        overhead_amount = overhead_rate * dc_watts
        _add("Overhead and SGA", overhead_rate, overhead_amount, rate_source_tag)

        # ── Subtotal before bonding, contingency, margin ─────────────────────
        subtotal = sum(item["amount_usd"] for item in line_items)

        # ── 14. Bonding ──────────────────────────────────────────────────────
        bond_rate_pct = bond["rate_pct"]
        bond_usd      = subtotal * bond_rate_pct
        bond_rate_wp  = bond_usd / dc_watts if dc_watts else 0
        bond_src      = "db_rates" if bond.get("source") == "db" else "fallback"
        _add(f"Bonding ({bond_rate_pct * 100:.2f}%)", bond_rate_wp, bond_usd, bond_src)

        subtotal_with_bond = subtotal + bond_usd

        # ── 15. Contingency (size-tiered %) ──────────────────────────────────
        contingency_pct = rates["contingency"]
        contingency_usd = subtotal_with_bond * contingency_pct
        contingency_wp  = contingency_usd / dc_watts if dc_watts else 0
        _add(f"Contingency ({contingency_pct * 100:.0f}%)",
             contingency_wp, contingency_usd, rate_source_tag)

        subtotal_with_contingency = subtotal_with_bond + contingency_usd

        # ── 16. Margin (size-tiered %) ────────────────────────────────────────
        margin_pct = rates["margin"]
        margin_usd = subtotal_with_contingency * margin_pct
        margin_wp  = margin_usd / dc_watts if dc_watts else 0
        _add(f"Margin ({margin_pct * 100:.0f}%)",
             margin_wp, margin_usd, rate_source_tag)

        total_usd    = subtotal_with_contingency + margin_usd
        total_per_wp = total_usd / dc_watts if dc_watts else 0

        results[band] = {
            "line_items":       line_items,
            "total_usd":        round(total_usd, 2),
            "total_per_wp":     round(total_per_wp, 4),
            "overrides_applied": overrides_applied,
            "fallbacks_used":   fallbacks_used,
        }

    return {
        "project_name":     project.get("project_name"),
        "location":         f"{project.get('location_state')}, {project.get('location_county')}",
        "installation_type": installation_type,
        "structure_type":   structure_type,
        "dc_size_kwp":      round(dc_mwp * 1000, 2),
        "ac_size_kw":       ac_kw,
        "dc_ac_ratio":      round(dc_mwp / (ac_kw / 1000), 3) if ac_kw else None,
        "panel_count":      panel_count,
        "inverter_type":    inverter_type,
        "inverter_count":   inverter_count,
        "system_voltage_dc_v": system_design.get("system_voltage_dc_v", 1500),
        "conservative":     results["low"],
        "base_case":        results["mid"],
        "optimistic":       results["high"],
        "rates_source":     rate_source_tag,
        "standard_exclusions": STANDARD_EXCLUSIONS,
        "prepared_by":      "CIR CAPEX Estimation Agent V2",
    }
