#!/usr/bin/env python3
"""
EOD Server Pipeline - Subsystem 3.3
Rule-Based Percentile Regime Classifier
"""

import sys
import argparse
import pandas as pd
import numpy as np

def calculate_market_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Computes Realized Volatility and Trend Strength metrics from validated OHLCV close data.
    """
    print("[*] Processing mathematical feature extraction arrays...")
    
    # Ensure sorting order is safe
    df = df.sort_index()

    # 1. Log Returns
    df['Log_Return'] = np.log(df['Close'] / df['Close'].shift(1))

    # 2. Annualized Realized Volatility (20-day rolling lookback window)
    # Volatility window matches the SMA20 framework
    df['Realized_Vol'] = df['Log_Return'].rolling(window=20).std() * np.sqrt(252)

    # 3. Simple Moving Averages for Trend Generation
    df['SMA5'] = df['Close'].rolling(window=5).mean()
    df['SMA20'] = df['Close'].rolling(window=20).mean()

    # 4. Normalized Trend Strength Metric (T)
    df['Trend_Strength'] = (df['SMA5'] - df['SMA20']) / df['SMA20']
    
    # Drop rows that don't have enough data to fulfill the 20-day rolling lookback
    return df.dropna().copy()


def classify_market_regime(df: pd.DataFrame, target_date_str: str) -> str:
    """
    Executes rule-based percentile lookup.
    Uses the context history up to target_date to evaluate target_date's current regime.
    """
    target_date = pd.to_datetime(target_date_str).date()
    
    # Format the index to date type to strip time-zone complexities if present
    df.index = pd.to_datetime(df.index, utc=True).date
    
    if target_date not in df.index:
        available_dates = list(df.index)
        print(f"[-] ERROR: Requested classification target date ({target_date}) missing from processed dataset.", file=sys.stderr)
        print(f"    Available data boundaries: {available_dates[0]} to {available_dates[-1]}", file=sys.stderr)
        sys.exit(1)

    # Slice out historical memory up to (and including) today
    history_df = df[df.index <= target_date]
    
    # Extract current parameters evaluated at the target date row boundary
    current_row = history_df.loc[target_date]
    sigma_today = current_row['Realized_Vol']
    t_today_abs = abs(current_row['Trend_Strength'])

    # Determine dynamic calibration thresholds across our total perceived history
    vol_threshold = np.percentile(history_df['Realized_Vol'], 75)
    trend_threshold = np.percentile(history_df['Trend_Strength'].abs(), 60)

    print(f"\n[*] Running classification matrix for date: {target_date}")
    print(f"    - Current Volatility: {sigma_today:.4f} (Threshold 75th: {vol_threshold:.4f})")
    print(f"    - Current Absolute Trend: {t_today_abs:.4f} (Threshold 60th: {trend_threshold:.4f})")

    # Sequential evaluation loop (Tie-breakers resolve toward safer Volatile/Defensive branch)
    if sigma_today >= vol_threshold:
        regime = "VOLATILE"
    elif t_today_abs >= trend_threshold:
        regime = "TRENDING"
    else:
        regime = "RANGING"

    print(f"[+] Identified Market Regime Allocation: {regime}")
    return regime


def main():
    parser = argparse.ArgumentParser(description="Percentile Regime Classifier")
    parser.add_argument("--input", type=str, default="validated_ohlcv.csv", help="Input path of validated daily bars")
    parser.add_argument("--target_date", type=str, required=True, help="The session day to evaluate (YYYY-MM-DD)")
    
    args = parser.parse_args()

    # Load file
    try:
        raw_data = pd.read_csv(args.input, index_col=0)
        raw_data.index = pd.to_datetime(raw_data.index, utc=True)
    except FileNotFoundError:
        print(f"[-] ERROR: Could not locate ingestion file '{args.input}'. Run ingest_validate_eod.py first.", file=sys.stderr)
        sys.exit(1)

    # Calculate indicators
    feature_df = calculate_market_features(raw_data)
    
    # Classify specific day
    regime = classify_market_regime(feature_df, args.target_date)


if __name__ == "__main__":
    main()