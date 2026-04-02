import json
from typing import Any

from google.adk.tools import ToolContext


_CORE_COMPONENTS = ("module", "inverter", "racking", "bos")
_ALL_COMPONENTS = _CORE_COMPONENTS + ("transformer",)


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _parse_json_object(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def normalize_market_prices(raw_market_prices_json: str, tool_context: ToolContext) -> dict:
    """
    Normalize market research output into a deterministic schema for cost tools.

    Input:
      raw_market_prices_json: JSON object keyed by component name.

    Behavior:
      - Enforces low/mid/high keys for each present component
      - Normalizes units:
          $/kW -> $/Wp (divide by 1000)
          $/Wp -> $/Wp
          $/unit -> allowed only for transformer
      - Marks invalid/missing records as fallback=true with confidence=low
      - Persists normalized output to tool_context.state['market_prices']
    """
    incoming = _parse_json_object(raw_market_prices_json)
    normalized: dict[str, dict[str, Any]] = {}
    notes: list[str] = []

    for component in _ALL_COMPONENTS:
        record_in = incoming.get(component)
        if not isinstance(record_in, dict):
            if component in _CORE_COMPONENTS:
                normalized[component] = {
                    "low": 0.0,
                    "mid": 0.0,
                    "high": 0.0,
                    "unit": "$/Wp",
                    "confidence": "low",
                    "fallback": True,
                    "notes": f"{component}: missing record; fallback to pricing DB.",
                }
                notes.append(f"{component}: missing -> fallback")
            continue

        unit_raw = str(record_in.get("unit", "$/Wp")).strip().lower()
        low = _to_float(record_in.get("low"))
        mid = _to_float(record_in.get("mid"))
        high = _to_float(record_in.get("high"))
        confidence = str(record_in.get("confidence", "low")).strip().lower()
        if confidence not in ("low", "medium", "high"):
            confidence = "low"

        fallback = bool(record_in.get("fallback", False))
        source_note = str(record_in.get("notes", "")).strip()

        if low is None or mid is None or high is None:
            fallback = True
            low = low or 0.0
            mid = mid or 0.0
            high = high or 0.0
            notes.append(f"{component}: one or more bands missing -> fallback")

        # Unit normalization
        if component == "transformer":
            # Transformer is handled as per-unit USD in cost tool.
            if unit_raw in ("$/unit", "usd/unit", "per unit", "unit"):
                unit_out = "$/unit"
            elif unit_raw in ("$/kw", "usd/kw", "per kw"):
                # Keep numeric values but flag fallback because cost tool expects $/unit.
                fallback = True
                unit_out = "$/unit"
                notes.append("transformer: $/kW provided but $/unit required -> fallback")
            else:
                unit_out = "$/unit"
                fallback = True
                notes.append("transformer: unknown unit -> fallback")
        else:
            # Core components must be in $/Wp for cost tool.
            if unit_raw in ("$/wp", "usd/wp", "per wp"):
                unit_out = "$/Wp"
            elif unit_raw in ("$/kw", "usd/kw", "per kw"):
                low, mid, high = low / 1000.0, mid / 1000.0, high / 1000.0
                unit_out = "$/Wp"
                notes.append(f"{component}: converted $/kW to $/Wp")
            else:
                # Unknown unit, keep values but mark fallback so DB rates are used.
                unit_out = "$/Wp"
                fallback = True
                notes.append(f"{component}: unknown unit '{unit_raw}' -> fallback")

        normalized_record = {
            "low": round(low, 6),
            "mid": round(mid, 6),
            "high": round(high, 6),
            "unit": unit_out,
            "confidence": confidence,
            "fallback": fallback,
            "notes": source_note,
        }

        # Keep metadata if provided.
        if "sources" in record_in:
            normalized_record["sources"] = record_in["sources"]
        if "source_count" in record_in:
            normalized_record["source_count"] = record_in["source_count"]
        if "source_avg_age_days" in record_in:
            normalized_record["source_avg_age_days"] = record_in["source_avg_age_days"]

        normalized[component] = normalized_record

    # Preserve optional benchmark payload without strict validation.
    if isinstance(incoming.get("nrel_benchmark"), dict):
        normalized["nrel_benchmark"] = incoming["nrel_benchmark"]

    tool_context.state["market_prices"] = normalized

    return {
        "market_prices": normalized,
        "normalization_notes": notes,
    }

