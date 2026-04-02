import math
from mycir_agent.config import (
    INVERTER_STRING_UNIT_KW,
    INVERTER_CENTRAL_STRING_UNIT_KW,
    INVERTER_CENTRAL_STRING_THRESHOLD_MWP,
    SYSTEM_VOLTAGE_DC,
    DEFAULT_MODULE_WATTAGE_W,
    DEFAULT_STRING_LENGTH_PANELS,
)

# Inverter output voltage (V) — used to determine if step-up transformer is needed
INVERTER_OUTPUT_VOLTAGE_V = 800  # modern 1500V-DC string/central string inverters

# Structure type defaults by size (GM only)
GM_SAT_DEFAULT_THRESHOLD_MWP = 5.0   # GM > 5 MWp → SAT default

# DC/AC ratio defaults
DC_AC_DEFAULTS = {
    ("GM", "fixed_tilt"): 1.25,
    ("GM", "SAT"):        1.30,
    ("RT", "fixed_tilt"): 1.15,
    ("CP", "fixed_tilt"): 1.10,
}

# Land area factors (acres per MWdc)
LAND_ACRES_PER_MWP = {
    ("GM", "fixed_tilt"): 5.5,
    ("GM", "SAT"):        6.5,
}

# POI voltage string to numeric (kV)
POI_VOLTAGE_KV_MAP = {
    "12.47kv": 12.47, "12.47": 12.47,
    "33kv": 33.0,  "33": 33.0,
    "66kv": 66.0,  "66": 66.0,
    "132kv": 132.0, "132": 132.0,
    "230kv": 230.0, "230": 230.0,
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


def _parse_poi_kv(poi_voltage: str) -> float:
    key = poi_voltage.lower().replace(" ", "").replace("kv", "") + "kv"
    for k, v in POI_VOLTAGE_KV_MAP.items():
        if poi_voltage.lower().replace(" ", "") in k or k in poi_voltage.lower().replace(" ", ""):
            return v
    try:
        return float(poi_voltage.lower().replace("kv", "").strip())
    except ValueError:
        return 33.0  # safe default


def design_system(project: dict, preferences: dict) -> dict:
    """
    Determines full system design configuration using CIR engineering logic.
    All decisions are made here — the LLM formats and presents results only.

    Args:
        project: ctx.state['project'] dict with dc_mwp, ac_kw, installation_type,
                 structure_type, poi_voltage.
        preferences: ctx.state['preferences'] dict with inverter_manufacturer,
                     module_manufacturer, budget_orientation, feoc_compliance.

    Returns:
        Full system design dict to store in ctx.state['system_design'].
    """
    installation_type = _normalize_installation_type(str(project.get("installation_type", "GM")))
    dc_mwp = float(project.get("dc_mwp", 0))
    ac_kw = float(project.get("ac_kw", 0))
    poi_voltage_str = str(project.get("poi_voltage", "33kv"))
    structure_type = str(project.get("structure_type", "")).lower()

    pref_inverter = preferences.get("inverter_manufacturer")
    pref_module = preferences.get("module_manufacturer")
    budget = preferences.get("budget_orientation", "midrange")
    feoc = _to_bool(preferences.get("feoc_compliance", None))

    dc_watts = dc_mwp * 1_000_000
    preference_warnings = []
    preference_notes = []

    # ── Structure type ────────────────────────────────────────────────────────
    if installation_type in ("RT", "CP"):
        structure_type = "fixed_tilt"
        structure_reason = f"{installation_type} always uses fixed tilt."
    elif structure_type not in ("fixed_tilt", "sat"):
        # GM — apply default based on size
        if dc_mwp > GM_SAT_DEFAULT_THRESHOLD_MWP:
            structure_type = "SAT"
            structure_reason = f"GM > {GM_SAT_DEFAULT_THRESHOLD_MWP} MWp — SAT is CIR standard at utility scale."
        else:
            structure_type = "fixed_tilt"
            structure_reason = f"GM ≤ {GM_SAT_DEFAULT_THRESHOLD_MWP} MWp — fixed tilt default."
    else:
        structure_reason = "User specified."

    # Normalise
    structure_type = structure_type.lower().replace("-", "_")

    # ── Inverter type ─────────────────────────────────────────────────────────
    if installation_type in ("RT", "CP"):
        inverter_type = "string"
        inverter_unit_kw = INVERTER_STRING_UNIT_KW
        inverter_reason = f"{installation_type} always uses distributed string inverters."
    elif dc_mwp < 1.0:
        inverter_type = "string"
        inverter_unit_kw = INVERTER_STRING_UNIT_KW
        inverter_reason = "< 1 MWp — distributed string inverters."
    elif dc_mwp < INVERTER_CENTRAL_STRING_THRESHOLD_MWP:
        inverter_type = "string"
        inverter_unit_kw = INVERTER_STRING_UNIT_KW
        inverter_reason = f"1–{INVERTER_CENTRAL_STRING_THRESHOLD_MWP} MWp — distributed string default."
    elif dc_mwp <= 5.0:
        inverter_type = "central_string"
        inverter_unit_kw = INVERTER_CENTRAL_STRING_UNIT_KW
        inverter_reason = f"{INVERTER_CENTRAL_STRING_THRESHOLD_MWP}–5 MWp — central string default."
    else:
        inverter_type = "central_string"
        inverter_unit_kw = INVERTER_CENTRAL_STRING_UNIT_KW
        inverter_reason = "> 5 MWp — central string (CIR standard)."

    # User inverter preference override
    if pref_inverter:
        # Known central string brands
        central_brands = ["sungrow sg350", "huawei sun2000-350", "sma sc pro"]
        # Known distributed string brands (smaller units)
        string_brands = ["sma sunny tripower", "fronius", "solaredge", "enphase"]
        pref_lower = pref_inverter.lower()

        if any(b in pref_lower for b in central_brands) and inverter_type == "string":
            if dc_mwp < 1.0:
                preference_warnings.append(
                    f"Central string inverter requested ({pref_inverter}) for "
                    f"{dc_mwp} MWp project. This adds unnecessary complexity at this scale."
                )
            inverter_type = "central_string"
            inverter_unit_kw = INVERTER_CENTRAL_STRING_UNIT_KW
        preference_notes.append(f"Inverter manufacturer preference: {pref_inverter}")

    # ── Module wattage ────────────────────────────────────────────────────────
    if installation_type == "GM" and dc_mwp >= 1.0:
        module_wattage_w = 620 if budget == "premium" else 580
        module_tech = "bifacial monocrystalline"
    elif installation_type == "GM":
        module_wattage_w = 500
        module_tech = "bifacial monocrystalline"
    elif installation_type == "RT":
        module_wattage_w = 450
        module_tech = "monofacial or bifacial"
    else:  # CP
        module_wattage_w = 420
        module_tech = "monofacial or bifacial"

    if feoc:
        preference_notes.append(
            "FEOC compliance required — equipment selection restricted to "
            "non-FEOC manufacturers (Qcells, First Solar, Silfab, REC, Maxeon)."
        )

    # ── Counts ────────────────────────────────────────────────────────────────
    panel_count = math.ceil(dc_watts / module_wattage_w)
    string_length = DEFAULT_STRING_LENGTH_PANELS  # at 1500V
    string_count = math.ceil(panel_count / string_length)
    inverter_count = math.ceil(ac_kw / inverter_unit_kw)

    # ── Transformer ───────────────────────────────────────────────────────────
    poi_kv = _parse_poi_kv(poi_voltage_str)
    inverter_output_kv = INVERTER_OUTPUT_VOLTAGE_V / 1000.0  # 0.8 kV

    transformer_required = poi_kv > inverter_output_kv
    transformer_count = 0
    transformer_mva_each = 0.0
    transformer_voltage_ratio = ""

    if transformer_required:
        # One transformer per ~1 MW AC block (padmount for MV, station for HV)
        transformer_mva_each = round(math.ceil(ac_kw / 1000 / inverter_count * inverter_unit_kw / 1000 * 1.1), 1)
        transformer_mva_each = max(transformer_mva_each, 1.0)
        transformer_count = inverter_count  # one per inverter station
        if poi_kv >= 66:
            # For large projects, group inverters under fewer transformers
            transformer_count = math.ceil(ac_kw / 5000)  # ~5 MW per transformer
            transformer_mva_each = round(ac_kw / transformer_count / 1000 * 1.1, 1)
        transformer_voltage_ratio = f"{INVERTER_OUTPUT_VOLTAGE_V}V / {poi_voltage_str}"

    # ── DC/AC ratio ───────────────────────────────────────────────────────────
    dc_ac_ratio = round(dc_mwp / (ac_kw / 1000.0), 3)
    default_ratio = DC_AC_DEFAULTS.get((installation_type, structure_type), 1.25)

    # ── Land area (GM only) ───────────────────────────────────────────────────
    land_key = ("GM", structure_type) if installation_type == "GM" else None
    land_area_acres = round(dc_mwp * LAND_ACRES_PER_MWP.get(land_key, 5.5), 1) if land_key else None

    return {
        "system_voltage_dc_v": SYSTEM_VOLTAGE_DC,
        "inverter_type": inverter_type,
        "inverter_type_reason": inverter_reason,
        "inverter_unit_kw": inverter_unit_kw,
        "inverter_count": inverter_count,
        "inverter_manufacturer_preference": pref_inverter,
        "structure_type": structure_type,
        "structure_reason": structure_reason,
        "dc_ac_ratio": dc_ac_ratio,
        "dc_ac_default": default_ratio,
        "module_wattage_w": module_wattage_w,
        "module_technology": module_tech,
        "module_manufacturer_preference": pref_module,
        "panel_count": panel_count,
        "string_length_panels": string_length,
        "string_count": string_count,
        "transformer_required": transformer_required,
        "transformer_count": transformer_count,
        "transformer_mva_each": transformer_mva_each,
        "transformer_voltage_ratio": transformer_voltage_ratio,
        "poi_voltage_kv": poi_kv,
        "land_area_acres": land_area_acres,
        "preference_notes": preference_notes,
        "preference_warnings": preference_warnings,
    }
