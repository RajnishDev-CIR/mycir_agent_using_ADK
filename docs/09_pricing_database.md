# Pricing Database — Design, Schema, and Excel Import Strategy

## Overview

The MyCIR Agent reads all cost rates from PostgreSQL (same instance used for ADK
session state). The Excel file is the team's editing surface — the DB is the
agent's operational data store. When the team updates the Excel, they run one
command to sync:

```bash
uv run python scripts/import_pricing_from_excel.py
```

**Why PostgreSQL, not Excel at runtime:**
- DB queries are instant; file I/O + openpyxl parse on every estimate adds latency
- Rates are versioned — `updated_at` column on every table
- Agent is self-contained: no file-path dependency
- Team can track "what rates were used on estimate X" via the benchmark log

**Why keep Excel:**
- Team's existing workflow unchanged
- Excel is the single source of truth — edit there, import to DB
- Non-technical team members can update rates without touching code

---

## Source Excel

**File:** `cir_old_manual_flow_docs/capex/250630_Database of Indicative System Prices_V2_SS_GB.xlsx`

Key sheets consumed by the import script:

| Sheet | Table | Description |
|---|---|---|
| System Price | `pricing_system_rates` | Size-tiered $/Wp rates by type and MWp |
| Engineering | `pricing_engineering_fixed` | Fixed engineering USD by MW band |
| Permitting | `pricing_permitting_fixed` | Fixed permitting USD by MW band |
| Bonding | `pricing_bonding` | Bonding rate % by size |
| Sales & Use Tax | `pricing_state_tax` | State sales/use tax rates |
| Sheet1 | `pricing_benchmark_projects` | 56 historical projects (read-only reference) |

---

## Database Schema

### Table: `pricing_system_rates`

Size-tiered $/Wp rates for each line item. The agent calls
`get_system_rates(system_type, dc_mwp)` which returns the matching row.

```sql
CREATE TABLE pricing_system_rates (
    id                  SERIAL PRIMARY KEY,
    system_type         TEXT NOT NULL,       -- GM | RT | CP
    size_min_mwp        NUMERIC(8,3) NOT NULL,
    size_max_mwp        NUMERIC(8,3) NOT NULL,
    -- Supply chain $/Wp
    module_per_wp       NUMERIC(6,4) NOT NULL,
    inverter_per_wp     NUMERIC(6,4) NOT NULL,
    racking_per_wp      NUMERIC(6,4) NOT NULL,
    racking_sat_per_wp  NUMERIC(6,4),        -- SAT override (GM only)
    bos_per_wp          NUMERIC(6,4) NOT NULL,
    -- Labour $/Wp (national baseline — multiplied by location_costs.labour_multiplier)
    mechanical_per_wp   NUMERIC(6,4) NOT NULL,
    electrical_per_wp   NUMERIC(6,4) NOT NULL,
    civil_per_wp        NUMERIC(6,4) NOT NULL,
    -- Soft costs $/Wp
    overhead_per_wp     NUMERIC(6,4) NOT NULL,
    sga_per_wp          NUMERIC(6,4) NOT NULL,
    -- Percentage adders (stored as decimals: 0.05 = 5%)
    contingency_pct     NUMERIC(6,4) NOT NULL,
    margin_pct          NUMERIC(6,4) NOT NULL,
    -- Metadata
    source              TEXT DEFAULT 'excel_import',
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);
```

### Table: `pricing_engineering_fixed`

Engineering design is a fixed USD cost per MW band, NOT a $/Wp rate.
The three sub-components allow itemized presentation.

```sql
CREATE TABLE pricing_engineering_fixed (
    id                  SERIAL PRIMARY KEY,
    size_min_mwp        NUMERIC(8,3) NOT NULL,
    size_max_mwp        NUMERIC(8,3) NOT NULL,
    electrical_usd      NUMERIC(12,2) NOT NULL,  -- Electrical BOP design
    civil_usd           NUMERIC(12,2) NOT NULL,  -- Civil BOP design
    substation_usd      NUMERIC(12,2) NOT NULL,  -- Substation design
    source              TEXT DEFAULT 'excel_import',
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);
```

### Table: `pricing_permitting_fixed`

Third-party permitting costs. Fixed USD by MW band.
Includes: Phase I ESA, biological, cultural, ALTA survey, geotechnical, SWPPP,
permit facilitation, local counsel.

```sql
CREATE TABLE pricing_permitting_fixed (
    id                  SERIAL PRIMARY KEY,
    size_min_mwp        NUMERIC(8,3) NOT NULL,
    size_max_mwp        NUMERIC(8,3) NOT NULL,
    total_usd           NUMERIC(12,2) NOT NULL,
    -- Itemised breakdown (informational — for detailed estimates)
    local_counsel_usd   NUMERIC(12,2),
    environmental_usd   NUMERIC(12,2),
    civil_survey_usd    NUMERIC(12,2),
    facilitation_usd    NUMERIC(12,2),
    source              TEXT DEFAULT 'excel_import',
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);
```

### Table: `pricing_bonding`

Performance bond rates as a decimal (1.3% = 0.013).

```sql
CREATE TABLE pricing_bonding (
    id                  SERIAL PRIMARY KEY,
    size_min_mwp        NUMERIC(8,3) NOT NULL,
    size_max_mwp        NUMERIC(8,3) NOT NULL,
    rate_pct            NUMERIC(6,4) NOT NULL,
    source              TEXT DEFAULT 'excel_import',
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);
```

### Table: `pricing_state_tax`

State sales & use tax base rates. Actual applied rate may vary by county.
Some states have full or partial exemptions for solar equipment — see notes column.

```sql
CREATE TABLE pricing_state_tax (
    id                  SERIAL PRIMARY KEY,
    state_code          CHAR(2) NOT NULL UNIQUE,
    state_name          TEXT NOT NULL,
    base_rate_pct       NUMERIC(6,4) NOT NULL,   -- 0.0625 = 6.25%
    solar_exempt        BOOLEAN DEFAULT FALSE,
    notes               TEXT,
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);
```

---

## Rate Lookup Logic (in `pricing_db.py`)

```
get_system_rates(system_type, dc_mwp):
    SELECT * FROM pricing_system_rates
    WHERE system_type = $1
    AND size_min_mwp <= $2 AND $2 < size_max_mwp
    LIMIT 1

get_engineering_cost(dc_mwp):
    SELECT electrical_usd + civil_usd + substation_usd AS total_usd
    FROM pricing_engineering_fixed
    WHERE size_min_mwp <= $1 AND $1 < size_max_mwp

get_permitting_cost(dc_mwp):
    SELECT total_usd FROM pricing_permitting_fixed
    WHERE size_min_mwp <= $1 AND $1 < size_max_mwp

get_bonding_rate(dc_mwp):
    SELECT rate_pct FROM pricing_bonding
    WHERE size_min_mwp <= $1 AND $1 < size_max_mwp

get_state_tax(state_code):
    SELECT base_rate_pct, solar_exempt, notes
    FROM pricing_state_tax WHERE state_code = $1
```

---

## Updating Rates

When the cost estimation team updates the Excel file:

```bash
# From the project root
uv run python scripts/import_pricing_from_excel.py

# This will:
# 1. Read cir_old_manual_flow_docs/250630_Database of Indicative System Prices_V2_SS_GB.xlsx
# 2. Parse System Price, Engineering, Permitting, Bonding, Sales & Use Tax sheets
# 3. TRUNCATE + INSERT (full refresh) for all pricing tables
# 4. Print a summary of rows loaded per table
# 5. Leave benchmark_log and session tables untouched
```

The import script is idempotent — safe to run multiple times.

---

## Fallback Behaviour

If the PostgreSQL connection fails (e.g. Docker not running), `pricing_db.py`
returns hardcoded fallback rates baked into the module. This ensures the agent
never crashes due to a DB issue — it just logs a warning and uses the defaults.

Priority order:
1. **DB rates** (live, size-tiered from pricing tables)
2. **Hardcoded defaults** in `pricing_db.py` (matches seed data — same rates)

---

## Excel File Coverage vs Current Agent

| Line Item | V1 Agent | Before Excel | After Excel |
|---|---|---|---|
| Module | flat $0.22/Wp all sizes | flat $0.22/Wp | size-tiered (0.22–0.43) |
| Inverter | flat $0.07/Wp | flat $0.07/Wp | size-tiered (0.04–0.096) |
| Racking | flat $0.14/Wp | flat $0.14/Wp | size-tiered + type-specific |
| BOS | flat $0.32/Wp | flat $0.32/Wp | size-tiered (0.25–0.45) |
| Engineering | $0.013/Wp flat | $0.013/Wp flat | **fixed USD by MW band** |
| Permitting | $0.03–0.04/Wp flat | $0.04/Wp flat | **fixed USD by MW band** |
| Contingency | flat 3% | flat 3% | **size-tiered (2–15%)** |
| Margin | flat 8% | flat 8% | **size-tiered (10–20%)** |
| Bonding | excluded | excluded | **new: 1.0–1.5%** |
| Sales tax | excluded | excluded | state lookup available |
