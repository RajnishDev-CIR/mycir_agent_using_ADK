"""
pricing_db.py — Database-backed pricing lookups for CAPEX V2.

All functions query the pricing_* tables in PostgreSQL.
If the DB is unavailable, they return hardcoded fallback rates that match
the seed data in docker/init.sql so behaviour is identical either way.

Usage:
    from .pricing_db import get_system_rates, get_engineering_cost, \
        get_permitting_cost, get_bonding_rate, get_state_tax
"""
import logging
from typing import Optional

log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# HARDCODED FALLBACKS — mirrors docker/init.sql seed data exactly.
# Used when Postgres is unreachable (dev without Docker, CI, etc.)
# ─────────────────────────────────────────────────────────────────────────────

# (system_type, size_min, size_max) → rate dict
_SYSTEM_RATE_FALLBACK = {
    # Ground Mount
    ("GM", 0.000,  0.500): dict(module=0.32, inverter=0.09, racking=0.21, racking_sat=0.27, bos=0.35, mechanical=0.17, electrical=0.20, civil=0.12, overhead=0.05, sga=0.14, contingency=0.10, margin=0.18),
    ("GM", 0.500,  1.000): dict(module=0.28, inverter=0.09, racking=0.21, racking_sat=0.26, bos=0.35, mechanical=0.17, electrical=0.20, civil=0.12, overhead=0.05, sga=0.14, contingency=0.05, margin=0.15),
    ("GM", 1.000,  3.000): dict(module=0.24, inverter=0.09, racking=0.21, racking_sat=0.25, bos=0.32, mechanical=0.17, electrical=0.20, civil=0.12, overhead=0.05, sga=0.14, contingency=0.05, margin=0.12),
    ("GM", 3.000,  5.000): dict(module=0.22, inverter=0.07, racking=0.18, racking_sat=0.24, bos=0.30, mechanical=0.17, electrical=0.20, civil=0.12, overhead=0.04, sga=0.14, contingency=0.03, margin=0.10),
    ("GM", 5.000, 20.000): dict(module=0.22, inverter=0.07, racking=0.18, racking_sat=0.23, bos=0.30, mechanical=0.17, electrical=0.20, civil=0.12, overhead=0.04, sga=0.14, contingency=0.025, margin=0.10),
    ("GM",20.000, 50.000): dict(module=0.22, inverter=0.05, racking=0.16, racking_sat=0.22, bos=0.28, mechanical=0.15, electrical=0.18, civil=0.10, overhead=0.04, sga=0.12, contingency=0.025, margin=0.10),
    ("GM",50.000,9999.00): dict(module=0.22, inverter=0.04, racking=0.16, racking_sat=0.20, bos=0.25, mechanical=0.15, electrical=0.18, civil=0.08, overhead=0.04, sga=0.12, contingency=0.02,  margin=0.10),
    # Rooftop
    ("RT", 0.000,  0.500): dict(module=0.43, inverter=0.096, racking=0.35, racking_sat=None, bos=0.45, mechanical=0.25, electrical=0.45, civil=0.05, overhead=0.05, sga=0.14, contingency=0.10, margin=0.20),
    ("RT", 0.500,  2.000): dict(module=0.43, inverter=0.096, racking=0.35, racking_sat=None, bos=0.44, mechanical=0.25, electrical=0.45, civil=0.05, overhead=0.05, sga=0.14, contingency=0.05, margin=0.15),
    ("RT", 2.000,  4.000): dict(module=0.38, inverter=0.09,  racking=0.30, racking_sat=None, bos=0.40, mechanical=0.25, electrical=0.45, civil=0.05, overhead=0.05, sga=0.14, contingency=0.05, margin=0.15),
    ("RT", 4.000,9999.00): dict(module=0.35, inverter=0.087, racking=0.28, racking_sat=None, bos=0.35, mechanical=0.22, electrical=0.40, civil=0.05, overhead=0.04, sga=0.12, contingency=0.03, margin=0.12),
    # Carport
    ("CP", 0.000,  0.500): dict(module=0.43, inverter=0.096, racking=0.45, racking_sat=None, bos=0.45, mechanical=0.30, electrical=0.45, civil=0.08, overhead=0.05, sga=0.14, contingency=0.10, margin=0.20),
    ("CP", 0.500,  2.000): dict(module=0.40, inverter=0.096, racking=0.40, racking_sat=None, bos=0.44, mechanical=0.28, electrical=0.45, civil=0.08, overhead=0.05, sga=0.14, contingency=0.05, margin=0.15),
    ("CP", 2.000,9999.00): dict(module=0.38, inverter=0.09,  racking=0.38, racking_sat=None, bos=0.40, mechanical=0.25, electrical=0.40, civil=0.08, overhead=0.04, sga=0.12, contingency=0.05, margin=0.12),
}

_ENGINEERING_FALLBACK = [
    (0,    1,    44000),
    (1,    2,    56000),
    (2,    3,    72000),
    (3,    5,    85000),
    (5,    7,   120000),
    (7,   10,   155000),
    (10,  20,   245000),
    (20,  40,   330000),
    (40,  60,   410000),
    (60, 100,   465000),
    (100, 9999, 520000),
]

_PERMITTING_FALLBACK = [
    (0,    1,    45000),
    (1,    2,    65000),
    (2,    3,    99000),
    (3,    5,   130000),
    (5,    7,   160000),
    (7,   10,   200000),
    (10,  20,   280000),
    (20, 9999,  400000),
]

_BONDING_FALLBACK = [
    (0,    1,    0.0150),
    (1,   50,    0.0130),
    (50, 150,    0.0125),
    (150, 9999,  0.0100),
]

_STATE_TAX_FALLBACK = {
    "AL": (0.0400, False), "AZ": (0.0560, True),  "CA": (0.0725, False),
    "CO": (0.0290, True),  "CT": (0.0635, True),  "FL": (0.0600, True),
    "GA": (0.0400, False), "IL": (0.0625, False),  "MA": (0.0625, True),
    "MD": (0.0600, True),  "MN": (0.0688, True),  "NC": (0.0475, False),
    "NJ": (0.0663, True),  "NM": (0.0513, True),  "NV": (0.0685, True),
    "NY": (0.0400, True),  "OH": (0.0575, False),  "PA": (0.0600, False),
    "SC": (0.0600, False), "TN": (0.0700, False),  "TX": (0.0625, True),
    "VA": (0.0530, False), "VT": (0.0600, False),  "WA": (0.0650, True),
}


def _get_connection():
    """Returns a psycopg2 connection using config.SESSION_DB_URL. Raises on failure."""
    import re
    import psycopg2
    from mycir_agent.config import SESSION_DB_URL
    # Parse postgresql+psycopg2://user:pass@host:port/db
    m = re.match(
        r"postgresql\+psycopg2://([^:]+):([^@]*)@([^:/]+):(\d+)/(.+)",
        SESSION_DB_URL,
    )
    if not m:
        raise ValueError(f"Cannot parse SESSION_DB_URL: {SESSION_DB_URL}")
    user, password, host, port, dbname = m.groups()
    return psycopg2.connect(
        host=host, port=int(port), dbname=dbname,
        user=user, password=password, connect_timeout=3,
    )


def _band_lookup(table: list[tuple], dc_mwp: float) -> float | None:
    """Find value in a (min, max, value) band list."""
    for lo, hi, val in table:
        if lo <= dc_mwp < hi:
            return val
    return table[-1][2]  # use last band as catch-all


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC API
# ─────────────────────────────────────────────────────────────────────────────

def get_system_rates(system_type: str, dc_mwp: float) -> dict:
    """
    Returns $/Wp rates and contingency/margin % for the given system type and size.
    Tries DB first; falls back to hardcoded defaults on any error.

    Returns dict with keys:
        module, inverter, racking, racking_sat, bos,
        mechanical, electrical, civil, overhead, sga,
        contingency, margin, source
    """
    try:
        conn = _get_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT module_per_wp, inverter_per_wp, racking_per_wp, racking_sat_per_wp,
                   bos_per_wp, mechanical_per_wp, electrical_per_wp, civil_per_wp,
                   overhead_per_wp, sga_per_wp, contingency_pct, margin_pct
            FROM pricing_system_rates
            WHERE system_type = %s AND size_min_mwp <= %s AND %s < size_max_mwp
            ORDER BY size_min_mwp DESC LIMIT 1
        """, (system_type, dc_mwp, dc_mwp))
        row = cur.fetchone()
        cur.close()
        conn.close()
        if row:
            keys = ["module", "inverter", "racking", "racking_sat", "bos",
                    "mechanical", "electrical", "civil", "overhead", "sga",
                    "contingency", "margin"]
            result = {k: (float(v) if v is not None else None) for k, v in zip(keys, row)}
            result["source"] = "db"
            return result
    except Exception as e:
        log.warning("pricing_db.get_system_rates DB error — using fallback: %s", e)

    # Fallback: find matching band in hardcoded dict
    stype = system_type.upper()
    for (t, lo, hi), rates in _SYSTEM_RATE_FALLBACK.items():
        if t == stype and lo <= dc_mwp < hi:
            return {**rates, "source": "fallback"}
    # Last band catch-all
    last = {k: v for (t, lo, hi), v_dict in _SYSTEM_RATE_FALLBACK.items()
            if t == stype for k, v in v_dict.items()}
    return {**last, "source": "fallback"}


def get_engineering_cost(dc_mwp: float) -> dict:
    """
    Returns fixed engineering cost in USD for the given project size.
    Returns dict: {electrical_usd, civil_usd, substation_usd, total_usd, source}
    """
    try:
        conn = _get_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT electrical_usd, civil_usd, substation_usd
            FROM pricing_engineering_fixed
            WHERE size_min_mwp <= %s AND %s < size_max_mwp
            ORDER BY size_min_mwp DESC LIMIT 1
        """, (dc_mwp, dc_mwp))
        row = cur.fetchone()
        cur.close()
        conn.close()
        if row:
            elec, civil, sub = [float(v) for v in row]
            return {"electrical_usd": elec, "civil_usd": civil,
                    "substation_usd": sub, "total_usd": elec + civil + sub,
                    "source": "db"}
    except Exception as e:
        log.warning("pricing_db.get_engineering_cost DB error — using fallback: %s", e)

    # Fallback
    for lo, hi, total in _ENGINEERING_FALLBACK:
        if lo <= dc_mwp < hi:
            return {"total_usd": float(total), "source": "fallback"}
    return {"total_usd": float(_ENGINEERING_FALLBACK[-1][2]), "source": "fallback"}


def get_permitting_cost(dc_mwp: float) -> dict:
    """
    Returns fixed permitting cost in USD for the given project size.
    Returns dict: {total_usd, source}
    """
    try:
        conn = _get_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT total_usd
            FROM pricing_permitting_fixed
            WHERE size_min_mwp <= %s AND %s < size_max_mwp
            ORDER BY size_min_mwp DESC LIMIT 1
        """, (dc_mwp, dc_mwp))
        row = cur.fetchone()
        cur.close()
        conn.close()
        if row:
            return {"total_usd": float(row[0]), "source": "db"}
    except Exception as e:
        log.warning("pricing_db.get_permitting_cost DB error — using fallback: %s", e)

    for lo, hi, total in _PERMITTING_FALLBACK:
        if lo <= dc_mwp < hi:
            return {"total_usd": float(total), "source": "fallback"}
    return {"total_usd": float(_PERMITTING_FALLBACK[-1][2]), "source": "fallback"}


def get_bonding_rate(dc_mwp: float) -> dict:
    """
    Returns bonding rate as a decimal (0.013 = 1.3%) for the given project size.
    Returns dict: {rate_pct, source}
    """
    try:
        conn = _get_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT rate_pct FROM pricing_bonding
            WHERE size_min_mwp <= %s AND %s < size_max_mwp
            ORDER BY size_min_mwp DESC LIMIT 1
        """, (dc_mwp, dc_mwp))
        row = cur.fetchone()
        cur.close()
        conn.close()
        if row:
            return {"rate_pct": float(row[0]), "source": "db"}
    except Exception as e:
        log.warning("pricing_db.get_bonding_rate DB error — using fallback: %s", e)

    rate = _band_lookup(_BONDING_FALLBACK, dc_mwp)
    return {"rate_pct": float(rate), "source": "fallback"}


def get_state_tax(state_code: str) -> dict:
    """
    Returns state sales/use tax info for the given two-letter state code.
    Returns dict: {base_rate_pct, solar_exempt, notes, source}
    Returns None if state not found.
    """
    code = state_code.upper().strip()
    try:
        conn = _get_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT base_rate_pct, solar_exempt, notes
            FROM pricing_state_tax WHERE state_code = %s
        """, (code,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        if row:
            return {"base_rate_pct": float(row[0]), "solar_exempt": bool(row[1]),
                    "notes": row[2], "source": "db"}
    except Exception as e:
        log.warning("pricing_db.get_state_tax DB error — using fallback: %s", e)

    if code in _STATE_TAX_FALLBACK:
        rate, exempt = _STATE_TAX_FALLBACK[code]
        return {"base_rate_pct": rate, "solar_exempt": exempt,
                "notes": None, "source": "fallback"}
    return None
