import json
import math
from datetime import datetime, timezone
from pathlib import Path

from mycir_agent.config import (
    BENCHMARK_FLAG_THRESHOLD_PCT,
    BENCHMARK_WARN_THRESHOLD_PCT,
    BENCHMARK_BLOCK_TOTAL_LOW,
    BENCHMARK_BLOCK_TOTAL_HIGH,
)

BENCHMARK_LOG_PATH = Path(__file__).parent.parent.parent.parent.parent.parent / "benchmark_log" / "benchmark_log.jsonl"

# Known explainable delta factors ($/Wp ranges)
EXPLAINABLE_FACTORS = {
    "prevailing_wage":  (0.06, 0.12),
    "sat_racking":      (0.05, 0.12),
    "feoc_premium":     (0.03, 0.08),
    "transformer":      (0.05, 0.12),
    "ca_labour":        (0.05, 0.10),
    "ny_labour":        (0.06, 0.12),
    "ma_labour":        (0.04, 0.09),
}


def _normalize_installation_type(value: str) -> str:
    cleaned = "".join(ch for ch in str(value).strip().lower() if ch.isalpha())
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
    return aliases.get(cleaned, str(value).strip().upper())


def compare_estimates(
    v1_result: dict,
    v2_estimate: dict,
    project: dict,
    preferences: dict,
    location_costs: dict,
) -> dict:
    """
    Compares V2 base-case estimate against V1 baseline. Determines
    pass/warn/flag/block status and appends to benchmark log.

    Args:
        v1_result: Output from run_v1_estimate.
        v2_estimate: ctx.state['estimate'] (full V2 result).
        project: ctx.state['project'].
        preferences: ctx.state['preferences'].
        location_costs: ctx.state['location_costs'].

    Returns:
        Comparison dict with status, delta, explanation, and log record.
    """
    # ── Extract totals ────────────────────────────────────────────────────────
    v1_per_wp = float(v1_result.get("total_per_wp", 0))
    v2_base = v2_estimate.get("base_case", {})
    v2_per_wp = float(v2_base.get("total_per_wp", 0))

    # ── BLOCK: calculation errors ─────────────────────────────────────────────
    if v2_per_wp < BENCHMARK_BLOCK_TOTAL_LOW:
        return _build_result("block", v1_per_wp, v2_per_wp, project, preferences,
                             location_costs, v2_base,
                             f"V2 total of ${v2_per_wp:.2f}/Wp is implausibly low (< ${BENCHMARK_BLOCK_TOTAL_LOW}/Wp). "
                             "Likely a calculation error.")

    if v2_per_wp > BENCHMARK_BLOCK_TOTAL_HIGH:
        return _build_result("block", v1_per_wp, v2_per_wp, project, preferences,
                             location_costs, v2_base,
                             f"V2 total of ${v2_per_wp:.2f}/Wp is implausibly high (> ${BENCHMARK_BLOCK_TOTAL_HIGH}/Wp). "
                             "Likely a calculation error.")

    if v1_per_wp == 0:
        return _build_result("warn", v1_per_wp, v2_per_wp, project, preferences,
                             location_costs, v2_base,
                             "V1 baseline run failed — benchmark comparison not available. "
                             "V2 estimate shown without validation.")

    # ── Calculate delta ───────────────────────────────────────────────────────
    delta_pct = ((v2_per_wp - v1_per_wp) / v1_per_wp) * 100
    delta_per_wp = v2_per_wp - v1_per_wp

    # ── Identify explainable factors ─────────────────────────────────────────
    explained_per_wp = 0.0
    applied_factors = []

    if preferences.get("prevailing_wage"):
        mid = sum(EXPLAINABLE_FACTORS["prevailing_wage"]) / 2
        explained_per_wp += mid
        applied_factors.append(f"Prevailing wage: +~${mid:.2f}/Wp")

    if _normalize_installation_type(project.get("installation_type", "GM")) == "GM" and v2_estimate.get("structure_type") == "SAT":
        mid = sum(EXPLAINABLE_FACTORS["sat_racking"]) / 2
        explained_per_wp += mid
        applied_factors.append(f"SAT vs fixed-tilt racking: +~${mid:.2f}/Wp")

    if preferences.get("feoc_compliance"):
        mid = sum(EXPLAINABLE_FACTORS["feoc_premium"]) / 2
        explained_per_wp += mid
        applied_factors.append(f"FEOC compliance premium: +~${mid:.2f}/Wp")

    if v2_estimate.get("transformer_required"):
        mid = sum(EXPLAINABLE_FACTORS["transformer"]) / 2
        explained_per_wp += mid
        applied_factors.append(f"POI step-up transformer (excluded in V1): +~${mid:.2f}/Wp")

    state = project.get("location_state", "").upper()
    state_factor_key = f"{state.lower()}_labour"
    if state_factor_key in EXPLAINABLE_FACTORS:
        mid = sum(EXPLAINABLE_FACTORS[state_factor_key]) / 2
        explained_per_wp += mid
        applied_factors.append(f"{state} labour premium: +~${mid:.2f}/Wp")

    unexplained_per_wp = delta_per_wp - explained_per_wp
    unexplained_pct = (unexplained_per_wp / v1_per_wp * 100) if v1_per_wp else 0

    # ── Determine status ──────────────────────────────────────────────────────
    abs_delta = abs(delta_pct)
    abs_unexplained = abs(unexplained_pct)

    if abs_delta > BENCHMARK_FLAG_THRESHOLD_PCT and abs_unexplained > 15:
        status = "flag"
        block_reason = (
            f"V2 is {delta_pct:+.1f}% vs V1 with ${unexplained_per_wp:+.2f}/Wp unexplained. "
            "Manual review recommended before using this estimate."
        )
    elif abs_delta > BENCHMARK_WARN_THRESHOLD_PCT:
        status = "warn"
        block_reason = None
    else:
        status = "pass"
        block_reason = None

    return _build_result(status, v1_per_wp, v2_per_wp, project, preferences,
                         location_costs, v2_base, block_reason,
                         delta_pct, explained_per_wp, unexplained_per_wp, applied_factors,
                         v2_base.get("line_items", []), v1_result.get("line_items", []))


def _build_result(status, v1_per_wp, v2_per_wp, project, preferences,
                  location_costs, v2_base, block_reason=None,
                  delta_pct=0, explained_per_wp=0, unexplained_per_wp=0,
                  applied_factors=None, v2_items=None, v1_items=None) -> dict:

    log_record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "project_name": project.get("project_name"),
        "location": f"{project.get('location_state')}, {project.get('location_county')}",
        "installation_type": project.get("installation_type"),
        "structure_type": project.get("structure_type"),
        "size_mwp": project.get("dc_mwp"),
        "v1_total_per_wp": round(v1_per_wp, 4),
        "v2_total_per_wp": round(v2_per_wp, 4),
        "delta_pct": round(delta_pct, 2),
        "validation_result": status,
        "explained_delta_per_wp": round(explained_per_wp, 4),
        "unexplained_delta_per_wp": round(unexplained_per_wp, 4),
        "flags": [k for k in ["prevailing_wage", "feoc", "sat", "transformer"]
                  if preferences.get(k.replace("feoc", "feoc_compliance").replace("sat", "structure_type"))],
        "v2_source_count": 0,
        "confidence": "medium",
    }

    # Append to benchmark log
    try:
        BENCHMARK_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(BENCHMARK_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_record) + "\n")
    except Exception:
        pass  # Never block the estimate due to log failure

    return {
        "status": status,
        "v1_total_per_wp": round(v1_per_wp, 4),
        "v2_total_per_wp": round(v2_per_wp, 4),
        "delta_pct": round(delta_pct, 2),
        "block_reason": block_reason,
        "applied_factors": applied_factors or [],
        "explained_per_wp": round(explained_per_wp, 4),
        "unexplained_per_wp": round(unexplained_per_wp, 4),
        "log_record": log_record,
    }
