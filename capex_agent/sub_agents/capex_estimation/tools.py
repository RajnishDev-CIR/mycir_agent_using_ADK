import json
import pandas as pd
from pathlib import Path

_DATA_PATH = Path(__file__).parent.parent.parent / "data" / "system_price.csv"

VALID_RANGES = {
    "GM": (0.3, 250.0),
    "RT": (0.1, 4.0),
    "CP": (0.1, 3.8),
}

LINE_ITEM_LABELS = {
    "module_rate":      "Module supply",
    "inverter_rate":    "Inverter supply",
    "racking_rate":     "Racking / structure",
    "bos_rate":         "Balance of system (BOS)",
    "mechanical_rate":  "Mechanical installation",
    "electrical_rate":  "Electrical installation",
    "civil_rate":       "Civil works",
    "engineering_rate": "Engineering",
    "permitting_rate":  "Permitting",
    "overhead_rate":    "Overhead (SGA)",
    "margin_rate":      "Margin",
}

STANDARD_EXCLUSIONS = [
    "Bonding and sales & use tax excluded — available on request",
    "Permitting costs subject to actual AHJ requirements",
    "Utility application fees, impact studies, and upgrades excluded",
    "No third-party external study costs included",
    "Stamping: additional $500 per set",
    "Includes one mobilization and one demobilization",
    "POI location at inverter level only",
]

def _load_db() -> pd.DataFrame:
    if not _DATA_PATH.exists():
        raise FileNotFoundError(
            f"Pricing database not found at {_DATA_PATH}. "
            "Please run the data export script first."
        )
    return pd.read_csv(_DATA_PATH)


def get_pricing_rows(installation_type: str, size_mwp: float) -> dict:
    """
    Looks up the two nearest pricing rows from the internal database for a
    given installation type and system size, ready for linear interpolation.

    Args:
        installation_type: One of 'GM' (Ground Mount), 'RT' (Rooftop),
                           or 'CP' (Carport).
        size_mwp: DC system size in megawatts-peak. Convert KWp to MWp
                  by dividing by 1000. Example: 720 KWp = 0.72 MWp.

    Returns:
        Dict with lower_row, upper_row, exact flag, interpolation_weight.
        Returns error key if validation fails.
    """
    installation_type = installation_type.strip().upper()

    if installation_type not in VALID_RANGES:
        return {"error": f"Invalid type '{installation_type}'. Must be GM, RT, or CP."}

    min_s, max_s = VALID_RANGES[installation_type]
    if size_mwp < min_s or size_mwp > max_s:
        return {
            "error": (
                f"{installation_type} pricing only available for "
                f"{min_s}–{max_s} MWp. You entered {size_mwp} MWp."
            )
        }

    db = _load_db()
    rows = db[db["type"] == installation_type].sort_values("size_mwp")

    exact = rows[rows["size_mwp"] == size_mwp]
    if not exact.empty:
        r = exact.iloc[0].to_dict()
        return {"lower_row": r, "upper_row": r, "exact": True,
                "interpolation_weight": 0.0}

    lower_rows = rows[rows["size_mwp"] < size_mwp]
    upper_rows = rows[rows["size_mwp"] > size_mwp]

    if lower_rows.empty or upper_rows.empty:
        return {"error": f"Cannot bracket {size_mwp} MWp. Out of database range."}

    lower = lower_rows.iloc[-1].to_dict()
    upper = upper_rows.iloc[0].to_dict()
    weight = (size_mwp - lower["size_mwp"]) / (upper["size_mwp"] - lower["size_mwp"])

    return {
        "lower_row": lower,
        "upper_row": upper,
        "exact": False,
        "interpolation_weight": round(weight, 6),
    }


def calculate_capex_estimate(
    lower_row_json: str,
    upper_row_json: str,
    interpolation_weight: float,
    dc_size_mwp: float,
    ac_size_kw: float,
    installation_type: str,
    project_name: str,
    location: str,
    module_price_override: float = None,
    racking_price_override: float = None,
    inverter_price_override: float = None,
    bos_price_override: float = None,
    civil_price_override: float = None,
    mechanical_price_override: float = None,
    electrical_price_override: float = None,
    engineering_price_override: float = None,
    permitting_price_override: float = None,
    overhead_price_override: float = None,
    contingency_pct_override: float = None,
    margin_pct_override: float = None,
) -> dict:
    """
    Calculates the complete CAPEX estimate. ALL arithmetic happens here.
    The LLM must never do multiplication or cost calculations itself.

    Args:
        lower_row_json: JSON string of the lower_row object from get_pricing_rows.
        upper_row_json: JSON string of the upper_row object from get_pricing_rows.
        interpolation_weight: Fractional weight between the two rows (0.0 to 1.0).
        dc_size_mwp: DC capacity in MWp (e.g. 0.72 for 720 KWp).
        ac_size_kw: AC capacity in KW (e.g. 600).
        installation_type: GM, RT, or CP.
        project_name: Name of the project for the output header.
        location: Project location state or city.
        module_price_override: Optional $/Wp to replace the database module
                               rate (e.g. 0.27 for Longi Hi-MO X6 current price).
        mechanical_price_override: Optional $/Wp for mechanical installation.
        electrical_price_override: Optional $/Wp for electrical installation.
        engineering_price_override: Optional $/Wp for engineering.
        permitting_price_override: Optional $/Wp for permitting.
        overhead_price_override: Optional $/Wp for overhead (SGA).

    Returns:
        Dict with project header, ordered line_items list (label/rate/amount),
        totals, interpolation flag, and standard exclusion notes.
    """
    try:
        lower_d = json.loads(lower_row_json)
        upper_d = json.loads(upper_row_json)
    except json.JSONDecodeError as e:
        return {"error": f"Invalid row JSON: {e}"}
    if not isinstance(lower_d, dict) or not isinstance(upper_d, dict):
        return {"error": "lower_row_json and upper_row_json must be JSON objects."}

    dc_watts = dc_size_mwp * 1_000_000

    def interp(col: str) -> float:
        lo = float(lower_d.get(col) or 0)
        hi = float(upper_d.get(col) or 0)
        return lo + interpolation_weight * (hi - lo)

    contingency_pct = (
        float(contingency_pct_override)
        if contingency_pct_override is not None
        else interp("contingency_pct")
    )

    OVERRIDE_MAP = {
        "module_rate":      module_price_override,
        "inverter_rate":    inverter_price_override,
        "racking_rate":     racking_price_override,
        "bos_rate":         bos_price_override,
        "mechanical_rate":  mechanical_price_override,
        "electrical_rate":  electrical_price_override,
        "civil_rate":       civil_price_override,
        "engineering_rate": engineering_price_override,
        "permitting_rate":  permitting_price_override,
        "overhead_rate":    overhead_price_override,
        "margin_rate":      margin_pct_override,
    }

    line_items = []
    subtotal = 0.0

    for col, label in LINE_ITEM_LABELS.items():
        rate = interp(col)
        override_val = OVERRIDE_MAP.get(col)
        if override_val is not None:
            rate = float(override_val)
        amount = rate * dc_watts
        subtotal += amount
        line_items.append({
            "label": label,
            "rate_per_wp": round(rate, 4),
            "amount_usd": round(amount, 2),
        })

    contingency_usd = subtotal * contingency_pct
    line_items.append({
        "label": f"Contingency ({contingency_pct * 100:.0f}%)",
        "rate_per_wp": round(contingency_usd / dc_watts, 4),
        "amount_usd": round(contingency_usd, 2),
    })

    total_usd = subtotal + contingency_usd
    total_per_wp = total_usd / dc_watts

    overrides_applied = []
    for col, val in OVERRIDE_MAP.items():
        if val is not None:
            label = LINE_ITEM_LABELS.get(col, col)
            db_val = interp(col)
            overrides_applied.append({
                "field": label,
                "override_value": round(float(val), 4),
                "db_default": round(db_val, 4),
            })
    if contingency_pct_override is not None:
        overrides_applied.append({
            "field": "Contingency %",
            "override_value": round(float(contingency_pct_override) * 100, 1),
            "db_default": round(interp("contingency_pct") * 100, 1),
        })

    type_labels = {"GM": "Ground Mount", "RT": "Rooftop", "CP": "Carport"}

    return {
        "project_name": project_name,
        "location": location,
        "installation_type": type_labels.get(installation_type, installation_type),
        "dc_size_kwp": round(dc_size_mwp * 1000, 2),
        "ac_size_kw": ac_size_kw,
        "line_items": line_items,
        "total_usd": round(total_usd, 2),
        "total_per_wp": round(total_per_wp, 4),
        "interpolated": interpolation_weight != 0.0,
        "module_override_applied": module_price_override is not None,
        "overrides_applied": overrides_applied,
        "standard_exclusions": STANDARD_EXCLUSIONS,
    }
