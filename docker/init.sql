-- MyCIR Agent — PostgreSQL initialisation
-- Runs once when the container is first created

-- ADK session tables are created automatically by DatabaseSessionService
-- This script creates the benchmark log table

CREATE TABLE IF NOT EXISTS benchmark_log (
    id              SERIAL PRIMARY KEY,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    session_id      TEXT,
    project_name    TEXT,
    location        TEXT,
    installation_type   TEXT,
    structure_type  TEXT,
    size_mwp        NUMERIC(10, 3),
    v1_total_per_wp NUMERIC(10, 4),
    v2_total_per_wp NUMERIC(10, 4),
    delta_pct       NUMERIC(8, 2),
    validation_result   TEXT,          -- pass | warn | flag | block
    explained_delta_per_wp  NUMERIC(10, 4),
    unexplained_delta_per_wp NUMERIC(10, 4),
    flags           TEXT[],            -- array of flag names
    v2_source_count INT,
    v2_source_avg_age_days INT,
    confidence      TEXT               -- low | medium | high
);

-- Index for querying by date and validation result
CREATE INDEX IF NOT EXISTS idx_benchmark_log_created_at ON benchmark_log (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_benchmark_log_result ON benchmark_log (validation_result);
