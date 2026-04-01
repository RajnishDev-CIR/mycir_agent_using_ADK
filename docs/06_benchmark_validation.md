# Benchmark Validation Agent

The Benchmark Validation Agent is a **quality gate inside Capex Agent V2**.
It is not a user-facing feature. Its purpose is to catch bad V2 outputs
before the user sees them, and to build an internal performance log over time.

---

## Position in Architecture

```
Capex Agent V2 (SequentialAgent)
    ...
    ├── Cost Calculation Agent V2   ← produces estimate
    └── Benchmark Validation Agent  ← validates estimate  ← YOU ARE HERE
            ├── V1 Runner           ← re-runs V1 on same inputs
            └── Comparison Report   ← produces diff + verdict
```

Benchmark Validation Agent runs **after** Cost Calc Agent V2 and **before**
the estimate is returned to the user.

---

## Trigger Modes

Controlled by `BENCHMARK_MODE` in `mycir_agent/config.py`:

```python
BENCHMARK_MODE = "auto"    # default — validates every V2 run silently
BENCHMARK_MODE = "manual"  # only runs when user explicitly asks
```

**When to use AUTO:**
- During V2 development and initial rollout
- Internal use where quality assurance is priority
- When you want to build the benchmark log quickly

**When to use MANUAL:**
- After V2 is validated and trusted
- When speed is more important than internal QA
- When running benchmark adds too much latency for user experience

---

## V1 Runner Sub-Agent

**What it does:**
- Takes the same mandatory project inputs from `ctx.state['project']`
- Calls V1 tools directly: `get_pricing_rows()` then `calculate_capex_estimate()`
- Returns V1 estimate as a dict — does NOT present it to the user

**What it does NOT do:**
- Modify any V1 code
- Apply V2 features (no market research, no location intel, no preferences)
- Show the user anything

**V1 inputs used (mandatory fields only — same as V1 required):**
- `installation_type` (GM / RT / CP)
- `dc_size_mwp`
- `ac_size_kw`
- `location` (state + county)
- `project_name`

V1 cannot receive FEOC, prevailing wage, SAT flag, or user overrides —
that is expected and is the point. V1 is a static baseline.

---

## Comparison Report Agent

Receives V1 result and V2 result, produces the comparison.

### Validation Rules

**BLOCK (do not return estimate — something is critically wrong):**
- V2 total is negative (calculation error)
- Any line item is negative (data error)
- Total $/Wp < $0.50 (implausibly cheap — likely calculation bug)
- Total $/Wp > $8.00 (implausibly expensive — likely calculation bug)

**FLAG (return estimate with prominent warning — human review recommended):**
- V2 total differs from V1 total by > 40%
- Any single line item differs by > 60% AND cannot be explained by known
  adjustments (prevailing wage, SAT, FEOC, transformer)
- All market research rates are from sources > 90 days old
- Fewer than 2 market research sources found for any major component

**WARN (return estimate with note — informational):**
- V2 total differs from V1 total by 15–40%
- One or more market research sources are 60–90 days old
- Location Intel could not find prevailing wage data (national average used)
- IRA calculation could not be completed

**PASS (return estimate cleanly — no annotation):**
- V2 within ±15% of V1 total
- All major components have 2+ sources < 60 days old
- No calculation anomalies detected

### Known Explainable Deltas

These deltas should NOT trigger FLAG even if > 40%, because they have
legitimate reasons. The Comparison Report Agent checks for these first:

| Reason | Expected Delta |
|---|---|
| Prevailing wage applied (CA) | +$0.06–0.12/Wp |
| SAT vs fixed tilt | +$0.08–0.12/Wp racking |
| FEOC compliance premium | +$0.03–0.08/Wp module |
| POI transformer added | +$0.05–0.12/Wp |
| California labour premium | +$0.05–0.10/Wp labour |
| Current module spot price higher than V1 DB | +$0.02–0.06/Wp |

If the total V2 delta can be explained by the sum of applicable known reasons,
downgrade from FLAG to WARN.

---

## Benchmark Report Format

Shown to user only when:
- Validation is WARN or FLAG (summary version)
- User explicitly requests comparison (full version)

**Summary version (WARN/FLAG):**
```
Validation note: V2 estimate is X% above CIR benchmark baseline.
Primary drivers: California prevailing wage (+$0.08/Wp), SAT racking
vs fixed-tilt benchmark (+$0.10/Wp), current module spot prices
(+$0.03/Wp). Adjusted for these factors, V2 is within 4% of baseline.
```

**Full comparison (user requests "compare" or "benchmark"):**
```
Project: xyz | CA, Los Angeles | 5 MWp GM | SAT | Prevailing wage

                        V1 Baseline    V2 Live        Delta
Module supply           $0.22/Wp      $0.25/Wp       +13.6%  ← live market
Inverter supply         $0.07/Wp      $0.09/Wp       +28.6%  ← live market
Racking / structure     $0.18/Wp      $0.19/Wp       +5.6%   ← SAT rate
BOS                     $0.38/Wp      $0.40/Wp       +5.3%
Mechanical install      $0.17/Wp      $0.22/Wp       +29.4%  ← CA prevailing wage
Electrical install      $0.20/Wp      $0.26/Wp       +30.0%  ← CA prevailing wage
Civil works             $0.14/Wp      $0.15/Wp       +7.1%
Engineering             $0.01/Wp      $0.01/Wp       0.0%
Permitting              $0.03/Wp      $0.05/Wp       +66.7%  ← LA AHJ
Transformer (new)       $0.00/Wp      $0.09/Wp       NEW LINE ITEM
FEOC premium (new)      $0.00/Wp      $0.05/Wp       NEW LINE ITEM
Prevailing wage (new)   $0.00/Wp      $0.08/Wp       NEW LINE ITEM
Overhead                $0.08/Wp      $0.08/Wp       0.0%
Contingency             $0.04/Wp      $0.05/Wp       +14.0%
Margin                  $0.12/Wp      $0.13/Wp       +7.2%
──────────────────────────────────────────────────────────────
TOTAL                   $1.65/Wp      $2.10/Wp       +27.3%

V1 source: CIR benchmark DB (static)
V2 sources: 6 market research results, avg 18 days old, confidence: HIGH

Explanation: $0.45/Wp delta is explained by:
  • Prevailing wage premium:    +$0.08/Wp (confirmed CA requirement)
  • POI transformer:            +$0.09/Wp (V1 excluded by design)
  • FEOC compliance premium:    +$0.05/Wp (user requirement)
  • Live module/inverter prices: +$0.05/Wp (market moved since DB date)
  • CA labour premium:          +$0.10/Wp (above national benchmark)
  • LA AHJ permitting:          +$0.02/Wp (above benchmark)
  Unexplained residual:         +$0.06/Wp (within normal market variation)

Validation: PASS (all major deltas explained)
```

---

## Benchmark Log (Internal)

Every run appends one record to `benchmark_log/benchmark_log.jsonl`:

```json
{
  "timestamp": "2026-04-01T10:23:00Z",
  "session_id": "6762b113-...",
  "project_name": "xyz",
  "location": "CA, Los Angeles",
  "type": "GM",
  "structure": "SAT",
  "size_mwp": 5.0,
  "v1_total_per_wp": 1.65,
  "v2_total_per_wp": 2.10,
  "delta_pct": 27.3,
  "validation_result": "pass",
  "explained_delta_per_wp": 0.39,
  "unexplained_delta_per_wp": 0.06,
  "flags": ["prevailing_wage", "feoc", "sat", "transformer", "ca_labour"],
  "v2_source_count": 6,
  "v2_source_avg_age_days": 18,
  "confidence": "high"
}
```

**Log is append-only. Never overwrite or delete records.**

This log enables:
- "Is V2 consistently higher or lower than V1?"
- "Which line items diverge most over time?"
- "Is market research quality improving?"
- "What % of our estimates required human review (FLAG)?"

---

## Performance Targets

Over time, use the benchmark log to track:

| Metric | Target |
|---|---|
| PASS rate | > 80% of runs |
| WARN rate | < 15% of runs |
| FLAG rate | < 5% of runs |
| BLOCK rate | 0% (calculation bugs — must be zero) |
| Avg source age | < 45 days |
| Avg source count per component | ≥ 3 |
