# End-of-Day (EOD) Server Subsystem (Regime Path) 

## Prerequisites
Ensure you have Python 3.11+ installed and the required package dependencies configured inside your virtual environment:
```bash
python -m pip install -r eod_pipeline/requirements.txt
python -m pip install yfinance
```

---

## Pipeline Execution

### Step 1: Data Ingestion & Validation (Task A.1a)
The `ingest_validate_eod.py` script pulls historical daily OHLCV data from the Yahoo Finance API for a reference equity symbol. It applies strict architectural guardrails to verify schema correctness, monotonic timestamps, and a minimum history window constraint (Calibration Window + 126 trading days).

To run a standard successful verification data pull:
```bash
python ingest_validate_eod.py --symbol AAPL --start 2025-06-01 --end 2026-07-01 --calibration_window 20
```
* **Output Artifact:** Validates the structural integrity of the downloaded arrays and serializes the clean data to disk as `validated_ohlcv.csv`.

### Step 2: Percentile Regime Classifier (Task A.2)
The `percentile_classifier.py` script takes the validated historical daily data, extracts localized realized volatility and trend strength features using rolling window bounds, and dynamically categorizes the market environment.

To run the live classification matrix demonstration for the reference target date `2026-06-30`:
```bash
python percentile_classifier.py --input validated_ohlcv.csv --target_date 2026-06-30
```

## Automated Unit Testing & Non-Degeneracy Verification (Task A.2)
The subsystem includes an automated test runner (`test_regime_classifier.py`) that evaluates the pipeline's stability and distribution across a continuous 6-month tracking slice (126 trading days)[cite: 8].

### How to Run the Verification Test Suite
```bash
python test_regime_classifier.py
```

---

## Backtest Data Health Check

After the Exchange Simulator generates `expected_book.csv` and
`frame_timings.csv`, inspect whether the configured grids are suitable for the
data:

```bash
.venv/bin/python -m eod_pipeline.tools.data_health_check
```

The report is written to `eod_pipeline/reports/data_health_check.md`.

## Configuration

`eod_pipeline/config/eod_settings.json` defines the strategy grids, `base_lot`,
risk limits, and operator-review thresholds. JSON may tighten the compile-time
PS risk ceilings, but cannot raise them.

## Backtest and Parameter Sweep

Run a deterministic sweep from the repository root:

```bash
.venv/bin/python -m eod_pipeline.run_sweep \
  --regime trending \
  --expected-book Exchange_simulator/build/expected_book.csv \
  --timing Exchange_simulator/build/frame_timings.csv \
  --output eod_pipeline/output/sweep_result.json \
  --print-winner
```

Regime mapping:

- `trending` → Momentum, 27 candidates
- `ranging` → Mean Reversion, 27 candidates
- `volatile` → Defensive, 9 candidates; currently HOLD-only and
  `NOT_OPTIMIZED`

The sweep ranks candidates by annualized Sharpe and also reports total P&L,
tick-level maximum drawdown, trade activity, and risk checks. Internal P&L uses
exact half-cent integers; readable CAD values are included in the winner.
Identical inputs and pinned dependencies produce identical output.

## Risk Review and Human Approval

Review the sweep winner and generate a PS-compatible candidate:

```bash
.venv/bin/python -m eod_pipeline.run_approval \
  --operator-id hanyu \
  --sweep-result eod_pipeline/output/sweep_result.json \
  --settings eod_pipeline/config/eod_settings.json
```

Optional per-run review thresholds:

```bash
  --max-drawdown-warning-cad 20000 --min-trades 20
```

Approval rules:

- warnings: `ACKNOWLEDGE WARNINGS`, then `APPROVE`
- `NOT_OPTIMIZED`: `OVERRIDE NOT_OPTIMIZED`, then `APPROVE`
- rejection: `REJECT`, followed by a non-empty reason

Artifacts are retained under
`eod_pipeline/output/approval_runs/<UTC-run-id>/`. Each run contains the
candidate, operator reports, stage log, and either an approved config or a
rejection record. The CLI only writes local files; real `scp` is not enabled.

## Tests

```bash
.venv/bin/python -m unittest discover -s eod_pipeline -p 'test_*.py'
```
