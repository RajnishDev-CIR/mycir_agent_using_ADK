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

# Band variance for supply-chain components when using db_rates fallback.
# Applies only to module, inverter, racking, bos — not to labour/fixed costs.
# conservative (low band) = +10%; base_case (mid) = flat; optimistic (high) = -10%
_BAND_VARIANCE = {"low": 1.10, "mid": 1.00, "high": 0.90}

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


def _fmt_usd(value: float) -> str:
    return f"{value:,.2f}"


def _fmt_wp(value: float) -> str:
    return f"{value:.2f}"


def _system_label(installation_type: str) -> str:
    mapping = {"GM": "Ground Mount", "RT": "Rooftop", "CP": "Carport"}
    return mapping.get(installation_type, installation_type)


def _line_index_by_label(line_items: list[dict]) -> dict[str, dict]:
    return {str(item.get("label", "")).lower(): item for item in line_items}


def build_igs_style_summary(
    estimate: dict,
    project: dict,
    preferences: dict,
) -> dict:
    """
    Build a deterministic IGS-style summary block using base-case estimate values.

    Returns:
        {
          "summary_markdown": "<markdown text>",
          "rows": [...],
          "project_name": "...",
        }
    """
    base_case = estimate.get("base_case", {}) if isinstance(estimate, dict) else {}
    line_items = base_case.get("line_items", []) if isinstance(base_case, dict) else []
    idx = _line_index_by_label(line_items)

    def pick(*candidates: str) -> dict | None:
        for key in candidates:
            item = idx.get(key.lower())
            if item:
                return item
        for candidate in candidates:
            c = candidate.lower()
            for lbl, itm in idx.items():
                if lbl.startswith(c):
                    return itm
        return None

    # Canonical rows to match the historical IGS "Summary" sheet look.
    rows: list[tuple[str, float, float]] = []

    def add_row(title: str, item: dict | None):
        if not item:
            return
        rows.append(
            (
                title,
                float(item.get("amount_usd", 0.0)),
                float(item.get("rate_per_wp", 0.0)),
            )
        )

    add_row("Module Price", pick("Module supply"))
    add_row("Inverter Price", pick("Inverter supply (string)", "Inverter supply (central string)"))
    add_row("Structure Price", pick("Racking / structure (fixed tilt)", "Racking / structure (SAT)"))
    add_row("BOS", pick("Balance of system (BOS)"))
    add_row("Mechanical installation", pick("Mechanical installation"))
    add_row("Electrical Installation", pick("Electrical installation"))
    add_row("Civil", pick("Civil works"))
    add_row("Engineering", pick("Engineering"))
    add_row("Permitting", pick("Permitting"))
    add_row("Overhead", pick("Overhead"))
    add_row("Margin", pick("Margin"))
    add_row("Contingency Amount", pick("Contingency"))

    total_usd = float(base_case.get("total_usd", 0.0))
    total_wp = float(base_case.get("total_per_wp", 0.0))

    project_name = estimate.get("project_name") or project.get("project_name") or "Project"
    installation_type = str(estimate.get("installation_type") or project.get("installation_type") or "GM")
    system_name = _system_label(installation_type)
    dc_kwp = float(estimate.get("dc_size_kwp", 0.0))
    ac_kw = float(estimate.get("ac_size_kw", 0.0))

    module_pref = preferences.get("module_manufacturer") if isinstance(preferences, dict) else None
    module_note = (
        f"Currently, we have used a module price of ${rows[0][2]:.2f}/Wp for {module_pref}. "
        "Please let us know if this needs to be updated."
        if rows and module_pref
        else ""
    )

    table_lines = [
        f"**Project Name : {project_name}**",
        "",
        f"**Type of System - {system_name}**",
        "",
        "| Item | Amount ($) | $/Wp |",
        "|:---|---:|---:|",
        f"| DC | {dc_kwp:,.0f} KWp |  |",
        f"| AC | {ac_kw:,.0f} KW |  |",
    ]
    for name, amount, per_wp in rows:
        table_lines.append(f"| {name} | {_fmt_usd(amount)} | {_fmt_wp(per_wp)} |")
    table_lines.append(f"| **Total $/Wp** | **{_fmt_usd(total_usd)}** | **{_fmt_wp(total_wp)}** |")

    notes = []
    if module_note:
        notes.append(module_note)
    notes.extend([
        "Bonding, sales and use tax is not included in the offer but can be made available upon request.",
        "Permitting costs will be determined based on actual requirements and are excluded from this cost estimate.",
        "Any cost related Utility application fees, impact studies, and utility upgrades are excluded.",
        "No cost for third Party External Study is considered.",
        "The cost of stamping is not covered within the design set and will incur an additional charge of $500 per set.",
        "Includes one mobilization and one demobilization.",
        "POI location is at inverter level only.",
    ])

    summary_markdown = "\n".join(table_lines + ["", "**Note-**"] + [f"- {n}" for n in notes])
    return {
        "summary_markdown": summary_markdown,
        "rows": rows,
        "project_name": project_name,
    }


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


def _market_band_to_wp(record: dict, band: str) -> float | None:
    """Convert market record band value to $/Wp for core components."""
    raw = record.get(band)
    if raw is None:
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    unit = str(record.get("unit", "$/Wp")).strip().lower()
    if unit in ("$/wp", "usd/wp", "per wp", "wp"):
        return value
    if unit in ("$/kw", "usd/kw", "per kw", "kw"):
        return value / 1000.0
    # Unknown unit for supply-chain components: treat as unusable.
    return None


def _get_market_price(market_prices: dict, component: str, band: str,
                      fallback_rate: float, structure_type: str = None,
                      fallback_rates: dict = None) -> tuple[float, str]:
    """
    Returns (price_per_wp, source) from market research or DB/fallback rates.
    band: 'low' | 'mid' | 'high'

    When live market data is unavailable, applies ±10% band variance to
    supply-chain components so conservative/optimistic bands differ meaningfully:
      conservative (low)  = db_rate × 1.10
      base_case   (mid)   = db_rate × 1.00
      optimistic  (high)  = db_rate × 0.90
    """
    record = market_prices.get(component, {})
    if record and not record.get("fallback", True) and record.get("confidence") in ("medium", "high"):
        if component == "transformer":
            # Transformer is expected in $/unit and is handled separately later.
            val = record.get(band)
            try:
                if val and float(val) > 0:
                    return float(val), "live_market"
            except (TypeError, ValueError):
                pass
        else:
            val_wp = _market_band_to_wp(record, band)
            if val_wp and val_wp > 0:
                return float(val_wp), "live_market"

    variance = _BAND_VARIANCE.get(band, 1.0)

    # DB/fallback rate — use SAT-specific racking if applicable
    if component == "racking" and structure_type == "SAT" and fallback_rates:
        sat_rate = fallback_rates.get("racking_sat")
        if sat_rate:
            return float(sat_rate) * variance, "db_rates"

    return float(fallback_rate) * variance, "db_rates" if fallback_rate else "fallback"


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
        _add("Engineering", eng_rate, eng_usd, eng_source)

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
        _add("Permitting", perm_rate, perm_usd, perm_source)

        # ── 10. Step-up transformer (NEW — V1 excluded) ──────────────────────
        if transformer_req and transformer_count > 0:
            trans_record = market_prices.get("transformer", {})
            trans_unit = str(trans_record.get("unit", "$/unit")).strip().lower() if trans_record else ""
            if trans_record and not trans_record.get("fallback", True) and trans_unit in ("$/unit", "usd/unit", "per unit", "unit"):
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

        # ── 13. Overhead (includes SGA / indirect costs) ──────────────────────
        # Historical data: overhead already includes all indirect costs.
        # The Excel template has a single "Overhead" line item.
        overhead_rate   = rates["overhead"] + rates.get("sga", 0.0)
        overhead_amount = overhead_rate * dc_watts
        _add("Overhead", overhead_rate, overhead_amount, rate_source_tag)

        # ── Subtotal (items 1–13, before margin and contingency) ─────────────
        # This is the base for margin and contingency as per the Excel template.
        subtotal = sum(item["amount_usd"] for item in line_items)

        # ── 14. Margin (10% of subtotal) ──────────────────────────────────────
        # Excel formula: Margin = 10% × subtotal
        # NOTE: margin is added BEFORE contingency (per CIR Excel template notes).
        margin_pct = rates["margin"]   # 0.10
        margin_usd = subtotal * margin_pct
        margin_wp  = margin_usd / dc_watts if dc_watts else 0
        _add(f"Margin ({margin_pct * 100:.0f}%)",
             margin_wp, margin_usd, rate_source_tag)

        # ── 15. Contingency (3% of subtotal + margin) ────────────────────────
        # Excel formula: Contingency = 3% × (subtotal + margin)
        # Verified against Mansfield actual: (1,595,540 + 159,554) × 3% = $52,653 ✓
        contingency_pct = rates["contingency"]   # 0.03
        contingency_usd = (subtotal + margin_usd) * contingency_pct
        contingency_wp  = contingency_usd / dc_watts if dc_watts else 0
        _add(f"Contingency ({contingency_pct * 100:.0f}%)",
             contingency_wp, contingency_usd, rate_source_tag)

        total_usd    = subtotal + margin_usd + contingency_usd
        total_per_wp = total_usd / dc_watts if dc_watts else 0

        # ── Bonding (indicative — shown separately, NOT in EPC total) ────────
        # Per CIR notes: "Bonding not included in offer, available upon request."
        bond_rate_pct = bond["rate_pct"]
        bond_usd_indicative = total_usd * bond_rate_pct
        bond_rate_wp  = bond_usd_indicative / dc_watts if dc_watts else 0
        bond_src      = "db_rates" if bond.get("source") == "db" else "fallback"

        results[band] = {
            "line_items":       line_items,
            "total_usd":        round(total_usd, 2),
            "total_per_wp":     round(total_per_wp, 4),
            "bonding_indicative_usd":   round(bond_usd_indicative, 2),
            "bonding_indicative_per_wp": round(bond_rate_wp, 4),
            "bonding_rate_pct": round(bond_rate_pct * 100, 2),
            "bonding_source":   bond_src,
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
