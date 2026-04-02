-- MyCIR Agent — PostgreSQL initialisation
-- Runs once when the container is first created

-- ─────────────────────────────────────────────────────────────────────────────
-- ADK session tables are created automatically by DatabaseSessionService
-- ─────────────────────────────────────────────────────────────────────────────

-- ─────────────────────────────────────────────────────────────────────────────
-- BENCHMARK LOG
-- ─────────────────────────────────────────────────────────────────────────────
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
    flags           TEXT[],
    v2_source_count INT,
    v2_source_avg_age_days INT,
    confidence      TEXT               -- low | medium | high
);

CREATE INDEX IF NOT EXISTS idx_benchmark_log_created_at ON benchmark_log (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_benchmark_log_result ON benchmark_log (validation_result);


-- ─────────────────────────────────────────────────────────────────────────────
-- PRICING: SYSTEM RATES
-- Size-tiered $/Wp rates by installation type and DC size band.
-- Source: 250630_Database of Indicative System Prices_V2_SS_GB.xlsx — System Price sheet
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS pricing_system_rates (
    id                  SERIAL PRIMARY KEY,
    system_type         TEXT NOT NULL,
    size_min_mwp        NUMERIC(8,3) NOT NULL,
    size_max_mwp        NUMERIC(8,3) NOT NULL,
    module_per_wp       NUMERIC(6,4) NOT NULL,
    inverter_per_wp     NUMERIC(6,4) NOT NULL,
    racking_per_wp      NUMERIC(6,4) NOT NULL,
    racking_sat_per_wp  NUMERIC(6,4),
    bos_per_wp          NUMERIC(6,4) NOT NULL,
    mechanical_per_wp   NUMERIC(6,4) NOT NULL,
    electrical_per_wp   NUMERIC(6,4) NOT NULL,
    civil_per_wp        NUMERIC(6,4) NOT NULL,
    overhead_per_wp     NUMERIC(6,4) NOT NULL,
    sga_per_wp          NUMERIC(6,4) NOT NULL,
    contingency_pct     NUMERIC(6,4) NOT NULL,
    margin_pct          NUMERIC(6,4) NOT NULL,
    source              TEXT DEFAULT 'excel_seed',
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pricing_rates_lookup
    ON pricing_system_rates (system_type, size_min_mwp, size_max_mwp);

-- GM (Ground Mount) — 7 size bands
-- Rates extracted from System Price sheet; BOS, mech, elec from Sheet1 historical averages
INSERT INTO pricing_system_rates
    (system_type, size_min_mwp, size_max_mwp,
     module_per_wp, inverter_per_wp, racking_per_wp, racking_sat_per_wp, bos_per_wp,
     mechanical_per_wp, electrical_per_wp, civil_per_wp,
     overhead_per_wp, sga_per_wp, contingency_pct, margin_pct)
VALUES
-- 0–0.5 MWp (small GM — string inverters, higher unit costs)
('GM', 0.000, 0.500,  0.3200, 0.0900, 0.2100, 0.2700, 0.3500, 0.1700, 0.2000, 0.1200, 0.0500, 0.1400, 0.1000, 0.1800),
-- 0.5–1 MWp
('GM', 0.500, 1.000,  0.2800, 0.0900, 0.2100, 0.2600, 0.3500, 0.1700, 0.2000, 0.1200, 0.0500, 0.1400, 0.0500, 0.1500),
-- 1–3 MWp (standard commercial-scale GM)
('GM', 1.000, 3.000,  0.2400, 0.0900, 0.2100, 0.2500, 0.3200, 0.1700, 0.2000, 0.1200, 0.0500, 0.1400, 0.0500, 0.1200),
-- 3–5 MWp (central string default; rates from Excel GM 5 MW row)
('GM', 3.000, 5.000,  0.2200, 0.0700, 0.1800, 0.2400, 0.3000, 0.1700, 0.2000, 0.1200, 0.0400, 0.1400, 0.0300, 0.1000),
-- 5–20 MWp
('GM', 5.000, 20.000, 0.2200, 0.0700, 0.1800, 0.2300, 0.3000, 0.1700, 0.2000, 0.1200, 0.0400, 0.1400, 0.0250, 0.1000),
-- 20–50 MWp (larger utility — reduced inverter cost, efficiency gains)
('GM', 20.000, 50.000, 0.2200, 0.0500, 0.1600, 0.2200, 0.2800, 0.1500, 0.1800, 0.1000, 0.0400, 0.1200, 0.0250, 0.1000),
-- 50+ MWp (utility scale)
('GM', 50.000, 9999.000, 0.2200, 0.0400, 0.1600, 0.2000, 0.2500, 0.1500, 0.1800, 0.0800, 0.0400, 0.1200, 0.0200, 0.1000),

-- RT (Rooftop) — 4 size bands
-- Source: project files River Valley, Mansfield, Marengo; System Price RT rows
-- 0–0.5 MWp
('RT', 0.000, 0.500,  0.4300, 0.0960, 0.3500, NULL, 0.4500, 0.2500, 0.4500, 0.0500, 0.0500, 0.1400, 0.1000, 0.2000),
-- 0.5–2 MWp (most RT commercial projects fall here)
('RT', 0.500, 2.000,  0.4300, 0.0960, 0.3500, NULL, 0.4400, 0.2500, 0.4500, 0.0500, 0.0500, 0.1400, 0.0500, 0.1500),
-- 2–4 MWp
('RT', 2.000, 4.000,  0.3800, 0.0900, 0.3000, NULL, 0.4000, 0.2500, 0.4500, 0.0500, 0.0500, 0.1400, 0.0500, 0.1500),
-- 4+ MWp (large RT — rare)
('RT', 4.000, 9999.000, 0.3500, 0.0870, 0.2800, NULL, 0.3500, 0.2200, 0.4000, 0.0500, 0.0400, 0.1200, 0.0300, 0.1200),

-- CP (Carport) — 3 size bands
-- Higher racking cost than RT; similar labour
-- 0–0.5 MWp
('CP', 0.000, 0.500,  0.4300, 0.0960, 0.4500, NULL, 0.4500, 0.3000, 0.4500, 0.0800, 0.0500, 0.1400, 0.1000, 0.2000),
-- 0.5–2 MWp
('CP', 0.500, 2.000,  0.4000, 0.0960, 0.4000, NULL, 0.4400, 0.2800, 0.4500, 0.0800, 0.0500, 0.1400, 0.0500, 0.1500),
-- 2+ MWp
('CP', 2.000, 9999.000, 0.3800, 0.0900, 0.3800, NULL, 0.4000, 0.2500, 0.4000, 0.0800, 0.0400, 0.1200, 0.0500, 0.1200);


-- ─────────────────────────────────────────────────────────────────────────────
-- PRICING: ENGINEERING FIXED COSTS
-- Fixed USD per MW band — NOT $/Wp. Extracted from Engineering sheet.
-- Components: Electrical BOP design, Civil BOP design, Substation design
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS pricing_engineering_fixed (
    id                  SERIAL PRIMARY KEY,
    size_min_mwp        NUMERIC(8,3) NOT NULL,
    size_max_mwp        NUMERIC(8,3) NOT NULL,
    electrical_usd      NUMERIC(12,2) NOT NULL,
    civil_usd           NUMERIC(12,2) NOT NULL,
    substation_usd      NUMERIC(12,2) NOT NULL,
    source              TEXT DEFAULT 'excel_seed',
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

INSERT INTO pricing_engineering_fixed
    (size_min_mwp, size_max_mwp, electrical_usd, civil_usd, substation_usd)
VALUES
(0.000,   1.000,   12000,  12000,  20000),
(1.000,   2.000,   18000,  18000,  20000),
(2.000,   3.000,   24000,  28000,  20000),
(3.000,   5.000,   30000,  35000,  20000),
(5.000,   7.000,   40000,  45000,  35000),
(7.000,  10.000,   50000,  55000,  50000),
(10.000, 20.000,   60000,  70000, 115000),
(20.000, 40.000,   80000,  90000, 160000),
(40.000, 60.000,  100000, 110000, 200000),
(60.000, 100.000, 110000, 120000, 235000),
(100.000, 9999.000, 120000, 130000, 270000);


-- ─────────────────────────────────────────────────────────────────────────────
-- PRICING: PERMITTING FIXED COSTS
-- Fixed USD per MW band. Source: Permitting sheet.
-- Includes: local counsel, Phase I ESA, ALTA survey, geotechnical, SWPPP,
--           biological/cultural studies, permit facilitation.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS pricing_permitting_fixed (
    id                  SERIAL PRIMARY KEY,
    size_min_mwp        NUMERIC(8,3) NOT NULL,
    size_max_mwp        NUMERIC(8,3) NOT NULL,
    total_usd           NUMERIC(12,2) NOT NULL,
    local_counsel_usd   NUMERIC(12,2),
    environmental_usd   NUMERIC(12,2),
    civil_survey_usd    NUMERIC(12,2),
    facilitation_usd    NUMERIC(12,2),
    source              TEXT DEFAULT 'excel_seed',
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

INSERT INTO pricing_permitting_fixed
    (size_min_mwp, size_max_mwp, total_usd, local_counsel_usd, environmental_usd, civil_survey_usd, facilitation_usd)
VALUES
(0.000,  1.000,   45000,  3000,  8000,  25000,  9000),
(1.000,  2.000,   65000,  4000, 10000,  38000, 13000),
(2.000,  3.000,   99000,  5000, 12000,  60000, 22000),
(3.000,  5.000,  130000,  6000, 15000,  78000, 31000),
(5.000,  7.000,  160000,  7000, 18000,  96000, 39000),
(7.000, 10.000,  200000,  8000, 22000, 122000, 48000),
(10.000, 20.000, 280000, 10000, 30000, 170000, 70000),
(20.000, 9999.000, 400000, 12000, 45000, 250000, 93000);


-- ─────────────────────────────────────────────────────────────────────────────
-- PRICING: BONDING
-- Performance bond rates. Source: Bonding sheet.
-- Applied to total project cost (after contingency, before margin).
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS pricing_bonding (
    id                  SERIAL PRIMARY KEY,
    size_min_mwp        NUMERIC(8,3) NOT NULL,
    size_max_mwp        NUMERIC(8,3) NOT NULL,
    rate_pct            NUMERIC(6,4) NOT NULL,   -- decimal: 0.013 = 1.3%
    source              TEXT DEFAULT 'excel_seed',
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

INSERT INTO pricing_bonding (size_min_mwp, size_max_mwp, rate_pct) VALUES
(0.000,   1.000,   0.0150),
(1.000,  50.000,   0.0130),
(50.000, 150.000,  0.0125),
(150.000, 9999.000, 0.0100);


-- ─────────────────────────────────────────────────────────────────────────────
-- PRICING: STATE SALES & USE TAX
-- Source: Sales & Use Tax sheet.
-- solar_exempt = TRUE where state/county provides full exemption for solar equipment.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS pricing_state_tax (
    id              SERIAL PRIMARY KEY,
    state_code      CHAR(2) NOT NULL UNIQUE,
    state_name      TEXT NOT NULL,
    base_rate_pct   NUMERIC(6,4) NOT NULL,
    solar_exempt    BOOLEAN DEFAULT FALSE,
    notes           TEXT,
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

INSERT INTO pricing_state_tax (state_code, state_name, base_rate_pct, solar_exempt, notes) VALUES
('AL', 'Alabama',       0.0400, FALSE, '4% state; county rates vary 0–5%. No blanket solar exemption.'),
('AZ', 'Arizona',       0.0560, TRUE,  'Solar equipment fully exempt from sales tax (ARS 42-5061).'),
('CA', 'California',    0.0725, FALSE, '7.25% state + district taxes; most commercial solar is exempt from use tax.'),
('CO', 'Colorado',      0.0290, TRUE,  'State sales tax exempt for solar energy equipment (C.R.S. 39-26-723).'),
('CT', 'Connecticut',   0.0635, TRUE,  'Solar energy equipment exempt.'),
('FL', 'Florida',       0.0600, TRUE,  'Residential solar exempt; commercial solar — check county rules.'),
('GA', 'Georgia',       0.0400, FALSE, '4% state; county varies. No blanket solar exemption.'),
('IL', 'Illinois',      0.0625, FALSE, '6.25% state; county/city additions common.'),
('MA', 'Massachusetts', 0.0625, TRUE,  'Solar energy equipment exempt from sales tax (G.L. c. 64H §6(dd)).'),
('MD', 'Maryland',      0.0600, TRUE,  'Solar energy property exempt.'),
('MN', 'Minnesota',     0.0688, TRUE,  'Solar energy equipment exempt from sales tax.'),
('NC', 'North Carolina',0.0475, FALSE, '4.75% state; county varies up to 2.75%.'),
('NJ', 'New Jersey',    0.0663, TRUE,  'Solar energy equipment exempt from sales tax.'),
('NM', 'New Mexico',    0.0513, TRUE,  'Receipts from solar energy systems exempt.'),
('NV', 'Nevada',        0.0685, TRUE,  'Solar energy systems partially or fully exempt depending on use.'),
('NY', 'New York',      0.0400, TRUE,  'Commercial solar equipment eligible for sales tax exemption (Form ST-121).'),
('OH', 'Ohio',          0.0575, FALSE, '5.75% state rate; county varies.'),
('PA', 'Pennsylvania',  0.0600, FALSE, '6% state. Solar systems generally taxable.'),
('SC', 'South Carolina',0.0600, FALSE, '6% state; county surcharge varies.'),
('TN', 'Tennessee',     0.0700, FALSE, '7% state; county varies. Limited exemptions.'),
('TX', 'Texas',         0.0625, TRUE,  'Solar energy devices exempt from sales and use tax (Tax Code §151.317).'),
('VA', 'Virginia',      0.0530, FALSE, '5.3% state; locality may add up to 1%.'),
('VT', 'Vermont',       0.0600, FALSE, '6% state; 1% county option. Solar — check utility-scale rules.'),
('WA', 'Washington',    0.0650, TRUE,  'Solar energy systems primarily used for on-site generation partially exempt.');
