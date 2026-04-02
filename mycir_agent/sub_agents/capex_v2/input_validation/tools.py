import math
import re
from datetime import datetime, timezone

from google.adk.tools import ToolContext

# Size limits (MWp)
SIZE_LIMITS = {
    "GM": (0.3, 250.0),
    "RT": (0.1, 4.0),
    "CP": (0.1, 3.8),
}

# DC/AC ratio bounds
DC_AC_MIN = 1.05
DC_AC_MAX = 1.60

# COD lead-time minimums (months)
COD_MIN_MONTHS = {"GM": 18, "RT": 12, "CP": 12}

# POI voltage mismatch thresholds
POI_LOW_VOLTAGE_LARGE_PROJECT_MW = 20.0   # 12.47kV warning above this size
POI_HIGH_VOLTAGE_SMALL_PROJECT_MW = 5.0  # 132kV warning below this size


def _parse_cod_months_from_now(cod_str: str) -> float | None:
    """Parse 'Q2 2027' or '2027-06' style COD strings. Returns months from now."""
    now = datetime.now(timezone.utc)
    cod_str = cod_str.strip()
    # Handle "Q1 2027", "Q2 2027", etc.
    if cod_str.upper().startswith("Q"):
        parts = cod_str.upper().replace("'", " ").split()
        if len(parts) >= 2:
            quarter = int(parts[0][1])
            year = int(parts[1])
            month = (quarter - 1) * 3 + 2  # mid-quarter month
            target = datetime(year, month, 1, tzinfo=timezone.utc)
            diff = (target.year - now.year) * 12 + (target.month - now.month)
            return diff
    # Handle "2027-06" or "06/2027"
    for fmt in ("%Y-%m", "%m/%Y"):
        try:
            target = datetime.strptime(cod_str, fmt).replace(tzinfo=timezone.utc)
            return (target.year - now.year) * 12 + (target.month - now.month)
        except ValueError:
            continue
    return None


def _normalize_installation_type(value: str) -> str:
    """
    Normalize installation type to one of: GM, RT, CP.
    Accepts common long forms and punctuation variants.
    """
    cleaned = re.sub(r"[^a-z]", "", value.strip().lower())
    aliases = {
        "gm": "GM",
        "groundmount": "GM",
        "ground": "GM",
        "rt": "RT",
        "rooftop": "RT",
        "roof": "RT",
        "cp": "CP",
        "carport": "CP",
        "car": "CP",
    }
    return aliases.get(cleaned, value.strip().upper())


def _is_missing(value) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        v = value.strip().lower()
        return v in ("", "none", "null", "n/a", "na", "[blank]")
    return False


def validate_project_inputs(project: dict, tool_context: ToolContext) -> dict:
    """
    Validates project inputs for consistency and realism before any
    market research or engineering work is started.

    Args:
        project: The project dict from ctx.state['project'], containing:
            project_name, location_state, location_county, dc_mwp, ac_kw,
            installation_type, structure_type, poi_voltage, cod.
        tool_context: Injected by ADK — used to persist validation state.

    Returns:
        Dict with:
            status: "pass" | "warn" | "block"
            warnings: list of warning strings (for warn status)
            block_reason: str | None (for block status)
    """
    def _persist_and_return(result: dict) -> dict:
        tool_context.state["validation"] = result
        return result

    if not project or not isinstance(project, dict):
        return _persist_and_return({
            "status": "block",
            "warnings": [],
            "block_reason": (
                "No project data provided. Please supply: project_name, "
                "location_state, location_county, cod, dc_mwp, ac_kw, "
                "poi_voltage, installation_type."
            ),
        })

    warnings = []
    block_reason = None

    raw_installation_type = str(project.get("installation_type", ""))
    installation_type = _normalize_installation_type(raw_installation_type)
    project["installation_type"] = installation_type

    missing_fields = []
    required = {
        "project_name": project.get("project_name"),
        "location_state": project.get("location_state"),
        "location_county": project.get("location_county"),
        "cod": project.get("cod"),
        "dc_mwp": project.get("dc_mwp"),
        "ac_kw": project.get("ac_kw"),
        "poi_voltage": project.get("poi_voltage"),
        "installation_type": raw_installation_type,
    }
    for key, value in required.items():
        if _is_missing(value):
            if key == "location_county" and str(value).strip().lower() == "unspecified":
                continue
            missing_fields.append(key)
    if missing_fields:
        return _persist_and_return({
            "status": "block",
            "warnings": [],
            "block_reason": (
                "Missing required project inputs: "
                + ", ".join(missing_fields)
                + ". Please provide these fields before estimation."
            ),
        })

    dc_mwp = float(project.get("dc_mwp", 0))
    ac_kw = float(project.get("ac_kw", 0))
    poi_voltage = str(project.get("poi_voltage", "")).strip().lower()
    cod = str(project.get("cod", "")).strip()

    # ── BLOCK: unknown installation type ──────────────────────────────────────
    if installation_type not in SIZE_LIMITS:
        return _persist_and_return({
            "status": "block",
            "warnings": [],
            "block_reason": (
                f"Unknown installation type '{raw_installation_type}'. "
                "Must be GM (Ground Mount), RT (Rooftop), or CP (Carport)."
            ),
        })

    # ── BLOCK: size out of range ──────────────────────────────────────────────
    min_s, max_s = SIZE_LIMITS[installation_type]
    if dc_mwp < min_s or dc_mwp > max_s:
        return _persist_and_return({
            "status": "block",
            "warnings": [],
            "block_reason": (
                f"{installation_type} projects must be {min_s}–{max_s} MWp. "
                f"Requested size is {dc_mwp} MWp, which is outside V2 scope."
            ),
        })

    # ── BLOCK: AC capacity missing or zero ───────────────────────────────────
    if ac_kw <= 0:
        return _persist_and_return({
            "status": "block",
            "warnings": [],
            "block_reason": "AC capacity must be greater than zero.",
        })

    # ── DC/AC ratio check ─────────────────────────────────────────────────────
    dc_ac_ratio = dc_mwp / (ac_kw / 1000.0)
    if dc_ac_ratio < 1.0:
        return _persist_and_return({
            "status": "block",
            "warnings": [],
            "block_reason": (
                f"DC/AC ratio of {dc_ac_ratio:.2f} is less than 1.0. "
                "DC capacity must exceed AC capacity. Please check your inputs."
            ),
        })
    if dc_ac_ratio < DC_AC_MIN:
        warnings.append(
            f"DC/AC ratio {dc_ac_ratio:.2f} is below typical minimum ({DC_AC_MIN}). "
            "This may indicate undersized AC or oversized inverter."
        )
    if dc_ac_ratio > DC_AC_MAX:
        warnings.append(
            f"DC/AC ratio {dc_ac_ratio:.2f} is above typical maximum ({DC_AC_MAX}). "
            "High clipping losses expected. Please confirm."
        )

    # ── COD lead-time check ───────────────────────────────────────────────────
    if cod:
        months = _parse_cod_months_from_now(cod)
        min_months = COD_MIN_MONTHS.get(installation_type, 12)
        if months is not None and months < min_months:
            level = "block" if months < 6 else "warn"
            msg = (
                f"COD of '{cod}' is only {months} months from now. "
                f"{installation_type} projects typically require {min_months}+ months. "
                "This timeline may be unrealistic."
            )
            if level == "block":
                return _persist_and_return(
                    {"status": "block", "warnings": [], "block_reason": msg}
                )
            warnings.append(msg)

    # ── POI voltage mismatch warnings ─────────────────────────────────────────
    if "12.47" in poi_voltage and dc_mwp > POI_LOW_VOLTAGE_LARGE_PROJECT_MW:
        warnings.append(
            f"12.47kV POI for a {dc_mwp} MWp project is unusual. "
            "Projects above 20 MWp typically use 33kV or higher. "
            "Please confirm POI voltage with utility."
        )
    if "132" in poi_voltage and dc_mwp < POI_HIGH_VOLTAGE_SMALL_PROJECT_MW:
        warnings.append(
            f"132kV POI for a {dc_mwp} MWp project may be oversized. "
            "Confirm substation requirement with utility."
        )

    # ── Result ────────────────────────────────────────────────────────────────
    status = "warn" if warnings else "pass"
    return _persist_and_return({
        "status": status,
        "warnings": warnings,
        "block_reason": block_reason,
        "dc_ac_ratio": round(dc_ac_ratio, 3),
    })
