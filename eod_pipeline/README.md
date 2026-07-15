# End-of-Day (EOD) Server Subsystem (Regime Path) 

## Prerequisites
Ensure you have Python 3.11+ installed and the required package dependencies configured inside your virtual environment:
```bash
pip install pandas numpy yfinance
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

---

## Downstream System Interface (Task A.4 Integration)
The terminal string output from this subsystem (`VOLATILE`, `TRENDING`, or `RANGING`) maps directly to the downstream integration thread.
