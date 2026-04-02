from __future__ import annotations

import json
from typing import Any

from google.adk.tools import ToolContext


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip().lower() in ("", "none", "null", "n/a", "na", "[blank]")
    return False


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().lower().replace(",", "")
    if not text:
        return None
    multiplier = 1.0
    if text.endswith("mwp"):
        multiplier = 1.0
        text = text[:-3]
    elif text.endswith("kwp"):
        multiplier = 1.0 / 1000.0
        text = text[:-3]
    elif text.endswith("mw"):
        multiplier = 1000.0
        text = text[:-2]
    elif text.endswith("kw"):
        multiplier = 1.0
        text = text[:-2]
    try:
        return float(text.strip()) * multiplier
    except ValueError:
        return None


def _normalize_installation_type(value: Any) -> str | None:
    if value is None:
        return None
    cleaned = "".join(ch for ch in str(value).strip().lower() if ch.isalpha())
    mapping = {
        "gm": "GM",
        "groundmount": "GM",
        "ground": "GM",
        "rt": "RT",
        "rooftop": "RT",
        "roof": "RT",
        "cp": "CP",
        "carport": "CP",
    }
    if not cleaned:
        return None
    return mapping.get(cleaned, str(value).strip().upper())


def _normalize_county(value: Any) -> str | None:
    if value is None:
        return None
    county = str(value).strip()
    if not county:
        return None
    if county.lower() in ("la", "los angeles", "los angeles county"):
        return "Los Angeles County"
    return county


def _normalize_structure_type(value: Any, installation_type: str | None) -> str | None:
    if installation_type in ("RT", "CP"):
        return "fixed_tilt"
    if value is None:
        return None
    text = str(value).strip().lower().replace("-", "_").replace(" ", "_")
    if text in ("sat", "single_axis_tracker", "tracker"):
        return "sat"
    if text in ("fixed_tilt", "fixed", "tilt"):
        return "fixed_tilt"
    return None


def _required_missing(project: dict[str, Any]) -> list[str]:
    required = [
        "project_name",
        "location_state",
        "location_county",
        "cod",
        "dc_mwp",
        "ac_kw",
        "poi_voltage",
        "installation_type",
    ]
    missing = []
    for key in required:
        value = project.get(key)
        if key == "location_county" and isinstance(value, str) and value.strip().lower() == "unspecified":
            continue
        if _is_missing(value):
            missing.append(key)
    if str(project.get("installation_type", "")).upper() == "GM":
        if _is_missing(project.get("structure_type")):
            missing.append("structure_type")
    return missing


def _parse_json_object(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _normalized_key(key: str) -> str:
    return "".join(ch for ch in key.strip().lower() if ch.isalnum() or ch == "_")


def _canonicalize_project_input(project_in: dict[str, Any]) -> dict[str, Any]:
    """
    Accept checklist-style intake keys and map them to canonical project fields.
    """
    key_map = {
        "projectname": "project_name",
        "location": "site_address",
        "dccapacitymwp": "dc_mwp",
        "dccapacitymw": "dc_mwp",
        "accapacitymwac": "ac_kw",
        "accapacitymw": "ac_kw",
        "accapacitykw": "ac_kw",
        "typeofstructure": "structure_type",
        "pointofinterconnectionpoivoltage": "poi_voltage",
        "poivoltage": "poi_voltage",
        "typeofinstallation": "installation_type",
        "expectedcodprojecttimeline": "cod",
        "expectedcod": "cod",
        "additionalnotesrisks": "project_notes",
        "additionalnotes": "project_notes",
        "modulemakemodel": "module_make_model",
        "invertermakemodel": "inverter_make_model",
        "structuremakesupplier": "structure_make_supplier",
    }

    out: dict[str, Any] = {}
    for raw_k, v in project_in.items():
        if not isinstance(raw_k, str):
            continue
        norm_k = _normalized_key(raw_k)
        canonical = key_map.get(norm_k, raw_k)

        # AC capacity values from checklist are often MWac numbers without unit.
        if canonical == "ac_kw" and norm_k in ("accapacitymwac", "accapacitymw"):
            parsed = _to_float(v)
            if parsed is not None:
                out[canonical] = parsed * 1000.0
                continue

        out[canonical] = v
    return out


def _canonicalize_preferences_input(pref_in: dict[str, Any]) -> dict[str, Any]:
    key_map = {
        "modulemakemodel": "module_manufacturer",
        "invertermakemodel": "inverter_manufacturer",
        "structuremakesupplier": "structure_supplier",
        "typeofstructure": "structure_preference",
    }
    out: dict[str, Any] = {}
    for raw_k, v in pref_in.items():
        if not isinstance(raw_k, str):
            continue
        canonical = key_map.get(_normalized_key(raw_k), raw_k)
        out[canonical] = v
    return out


def upsert_intake_state(
    project_json: str,
    tool_context: ToolContext,
    preferences_json: str = "{}",
) -> dict:
    """
    Persist intake data every turn so routing can be deterministic.

    The intake agent should call this tool on every user turn with best-known
    values (use null for unknown fields). This function merges with existing
    session state, normalizes core fields, and returns missing mandatory fields.
    """
    project_in = _canonicalize_project_input(_parse_json_object(project_json))
    pref_in = _canonicalize_preferences_input(_parse_json_object(preferences_json))

    existing_project = tool_context.state.get("project")
    existing_pref = tool_context.state.get("preferences")

    merged_project: dict[str, Any] = dict(existing_project) if isinstance(existing_project, dict) else {}
    merged_pref: dict[str, Any] = dict(existing_pref) if isinstance(existing_pref, dict) else {}

    # Merge project values (ignore explicit None to preserve known data).
    for k, v in project_in.items():
        if v is not None:
            merged_project[k] = v

    # Normalize project fields.
    if "dc_mwp" in merged_project:
        parsed = _to_float(merged_project.get("dc_mwp"))
        if parsed is not None:
            merged_project["dc_mwp"] = parsed
    if "ac_kw" in merged_project:
        parsed = _to_float(merged_project.get("ac_kw"))
        if parsed is not None:
            merged_project["ac_kw"] = parsed
    if "installation_type" in merged_project:
        norm = _normalize_installation_type(merged_project.get("installation_type"))
        if norm:
            merged_project["installation_type"] = norm
    if "location_county" in merged_project:
        norm = _normalize_county(merged_project.get("location_county"))
        if norm:
            merged_project["location_county"] = norm
    if "structure_type" in merged_project or "installation_type" in merged_project:
        norm = _normalize_structure_type(
            merged_project.get("structure_type"),
            _normalize_installation_type(merged_project.get("installation_type")),
        )
        if norm:
            merged_project["structure_type"] = norm

    # If state known and county provided without state in this turn, keep state.
    if _is_missing(merged_project.get("location_state")):
        prior_state = None
        if isinstance(existing_project, dict):
            prior_state = existing_project.get("location_state")
        if prior_state:
            merged_project["location_state"] = prior_state

    # Merge preferences.
    for k, v in pref_in.items():
        if v is not None:
            merged_pref[k] = v

    # Promote checklist equipment fields into preferences when not explicitly set.
    if _is_missing(merged_pref.get("module_manufacturer")) and not _is_missing(
        merged_project.get("module_make_model")
    ):
        merged_pref["module_manufacturer"] = merged_project.get("module_make_model")
    if _is_missing(merged_pref.get("inverter_manufacturer")) and not _is_missing(
        merged_project.get("inverter_make_model")
    ):
        merged_pref["inverter_manufacturer"] = merged_project.get("inverter_make_model")
    if _is_missing(merged_pref.get("structure_supplier")) and not _is_missing(
        merged_project.get("structure_make_supplier")
    ):
        merged_pref["structure_supplier"] = merged_project.get("structure_make_supplier")

    merged_pref.setdefault("prevailing_wage", False)
    merged_pref.setdefault("ira_domestic_content", False)
    merged_pref.setdefault("price_overrides", {})

    tool_context.state["project"] = merged_project
    tool_context.state["preferences"] = merged_pref

    missing = _required_missing(merged_project)
    ready = len(missing) == 0
    return {
        "ready_for_handoff": ready,
        "missing_mandatory_fields": missing,
        "project": merged_project,
        "preferences": merged_pref,
    }

