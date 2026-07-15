#!/usr/bin/env python3
"""
AQTA EOD Server Pipeline - Subsystem 3.3
Task A.1a: Data Ingestion & Validation (Yahoo Finance Daily OHLCV Ingest)
"""

import sys
import argparse
import pandas as pd
import yfinance as yf

def ingest_historical_ohlcv(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    """
    Downloads historical daily OHLCV data from Yahoo Finance.
    """
    print(f"[*] [A.1a] Fetching historical OHLCV data for '{symbol}' from {start_date} to {end_date}...")
    try:
        # Download historical daily bar data (interval="1d")
        # We explicitly request 'AAPL' (or your target symbol) as specified in the design doc
        ticker = yf.Ticker(symbol)
        df = ticker.history(start=start_date, end=end_date, interval="1d")
        
        if df.empty:
            print(f"[-] ERROR: Download returned an empty DataFrame. Check the ticker '{symbol}' or your date range.", file=sys.stderr)
            sys.exit(1)
            
        return df
    except Exception as e:
        print(f"[-] ERROR: Failed to communicate with Yahoo Finance: {e}", file=sys.stderr)
        sys.exit(1)

def validate_ohlcv_data(df: pd.DataFrame, calibration_window_days: int) -> pd.DataFrame:
    """
    Applies strict validation checks based on AQTA's Section 3.3.3.1 specifications:
    1. Schema validation (ensures Open, High, Low, Close, Volume exist).
    2. Monotonic, unique timestamp indexing.
    3. Minimum history window verification: Calibration Window + 126 trading days.
    """
    print("[*] [A.1a] Starting data validation checks...")

    # 1. Schema Check: Ensure exact expected columns exist
    required_cols = ['Open', 'High', 'Low', 'Close', 'Volume']
    missing_cols = [col for col in required_cols if col not in df.columns]
    
    if missing_cols:
        print(f"[-] VALIDATION FAILED: Missing required columns in downloaded data: {missing_cols}", file=sys.stderr)
        sys.exit(1)
        
    # Standardize schema (pruning extra yfinance tracking columns like Dividends/Splits)
    df_clean = df[required_cols].copy()

    # 2. Timestamp Constraints (Monotonic and Unique)
    # Convert index to DatetimeIndex if not already structured
    if not isinstance(df_clean.index, pd.DatetimeIndex):
        df_clean.index = pd.to_datetime(df_clean.index)
        
    # Ensure index dates are strictly ascending (monotonic)
    df_clean = df_clean.sort_index()
    if not df_clean.index.is_monotonic_increasing:
        print("[-] VALIDATION FAILED: Historical timestamps are not monotonic.", file=sys.stderr)
        sys.exit(1)
        
    # Ensure there are no duplicate dates
    if df_clean.index.duplicated().any():
        print("[-] VALIDATION FAILED: Duplicate timestamps detected in the history.", file=sys.stderr)
        sys.exit(1)

    # 3. History Window Validation (calibration_window + 126 trading days)
    # 126 trading days represent the required 6-month historical classification run
    min_required_days = calibration_window_days + 126
    actual_trading_days = len(df_clean)
    
    print(f"    - Configuration Calibration Window: {calibration_window_days} trading days")
    print(f"    - Calculated Minimum Required Trading Days: {min_required_days} days")
    print(f"    - Downloaded Trading Days count: {actual_trading_days} days")

    if actual_trading_days < min_required_days:
        print(
            f"[-] VALIDATION FAILED: Insufficient historical data depth.\n"
            f"    Expected at least {min_required_days} trading days (Calibration {calibration_window_days} + 126 evaluation days),\n"
            f"    but downloaded only {actual_trading_days} days. Please widen your start/end dates.", 
            file=sys.stderr
        )
        sys.exit(1)

    print("[+] [A.1a] Validation successful. Data is structurally sound.")
    return df_clean

def main():
    parser = argparse.ArgumentParser(description="AQTA Task A.1a - OHLCV Data Ingestion & Validation")
    parser.add_argument("--symbol", type=str, default="AAPL", help="Ticker symbol to download (default: AAPL)")
    parser.add_argument("--start", type=str, default="2025-06-01", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", type=str, default="2026-07-01", help="End date (YYYY-MM-DD)")
    parser.add_argument("--calibration_window", type=int, default=20, help="Volatility/Trend rolling lookback window (default: 20)")
    parser.add_argument("--output", type=str, default="validated_ohlcv.csv", help="Filename to output validated CSV")
    
    args = parser.parse_args()
    
    # Run pipeline stages
    raw_df = ingest_historical_ohlcv(args.symbol, args.start, args.end)
    validated_df = validate_ohlcv_data(raw_df, args.calibration_window)
    
    # Save the output CSV
    validated_df.to_csv(args.output)
    print(f"[+] [A.1a] Cleaned and validated dataset saved to: {args.output}\n")

if __name__ == "__main__":
    main()