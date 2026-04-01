import os
from dotenv import load_dotenv

load_dotenv()

# ── Benchmark ─────────────────────────────────────────────────────────────────
# "auto"   → validate every V2 run silently (default during development)
# "manual" → only when user explicitly asks to compare
BENCHMARK_MODE: str = os.getenv("BENCHMARK_MODE", "auto")

# ── PostgreSQL ────────────────────────────────────────────────────────────────
_POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
_POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")
_POSTGRES_DB   = os.getenv("POSTGRES_DB", "mycir")
_POSTGRES_USER = os.getenv("POSTGRES_USER", "mycir_user")
_POSTGRES_PASS = os.getenv("POSTGRES_PASSWORD", "")

SESSION_DB_URL: str = (
    f"postgresql+psycopg2://{_POSTGRES_USER}:{_POSTGRES_PASS}"
    f"@{_POSTGRES_HOST}:{_POSTGRES_PORT}/{_POSTGRES_DB}"
)

# ── Safety ────────────────────────────────────────────────────────────────────
MAX_LLM_CALLS: int = 50

# ── Market research freshness ─────────────────────────────────────────────────
MAX_SOURCE_AGE_DAYS: int = 90

# ── Benchmark validation thresholds ──────────────────────────────────────────
BENCHMARK_FLAG_THRESHOLD_PCT:  float = 40.0   # V2 vs V1 delta triggers FLAG
BENCHMARK_WARN_THRESHOLD_PCT:  float = 15.0   # V2 vs V1 delta triggers WARN
BENCHMARK_BLOCK_TOTAL_LOW:     float = 0.50   # $/Wp below this → calculation error
BENCHMARK_BLOCK_TOTAL_HIGH:    float = 8.00   # $/Wp above this → calculation error

# ── Inverter sizing defaults ──────────────────────────────────────────────────
INVERTER_STRING_UNIT_KW:        int = 125   # distributed string default unit size
INVERTER_CENTRAL_STRING_UNIT_KW: int = 350  # central string default unit size (e.g. SG350HX)

# Threshold: below this → distributed string default; above → central string default
# In 1–5 MWp range the agent will evaluate both and ask user if no preference
INVERTER_CENTRAL_STRING_THRESHOLD_MWP: float = 3.0

# ── System voltage ────────────────────────────────────────────────────────────
SYSTEM_VOLTAGE_DC: int = 1500   # all project types (GM, RT, CP)

# ── String sizing (1500V, 580W module reference) ──────────────────────────────
DEFAULT_MODULE_WATTAGE_W:    int = 580
DEFAULT_STRING_LENGTH_PANELS: int = 27   # conservative design at 1500V
