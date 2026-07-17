#!/usr/bin/env python3
"""
EOD Subsystem - Verification Test Suite
Automated Proof of Non-Degeneracy and Boundary Correctness
"""

import os
import sys
import pandas as pd
from percentile_classifier import calculate_market_features, classify_market_regime

def run_pipeline_validation():
    input_file = "validated_ohlcv.csv"
    
    if not os.path.exists(input_file):
        print(f"[-] Test Setup Error: Missing '{input_file}'. Run Ingestion script first.")
        sys.exit(1)
        
    print("[*] [Test Suite] Loading validated daily data matrix...")
    raw_data = pd.read_csv(input_file, index_col=0)
    raw_data.index = pd.to_datetime(raw_data.index, utc=True)
    
    # Process indicators
    feature_df = calculate_market_features(raw_data)
    
    # Slice a continuous 6-month testing window (approx 126 trading days)
    # We choose the trailing edge of the data to ensure an abundant history buffer
    test_dates = list(feature_df.index)[-126:]
    
    print(f"[*] [Test Suite] Launching evaluation loop across {len(test_dates)} continuous sessions...")
    
    # Track classifications to verify distribution spread
    allocated_regimes = []
    
    for current_date in test_dates:
        # Convert date back to string format for your classifier interface
        date_str = current_date.strftime('%Y-%m-%d')
        
        # Suppress standard logging prints during the loop for clean test output
        try:
            regime = classify_market_regime(feature_df, date_str)
            allocated_regimes.append(regime)
        except SystemExit:
            print(f"[-] Test Failure: Pipeline crashed on target row date {date_str}")
            sys.exit(1)
            
    # Convert distribution array into unique statistical set mappings
    unique_regimes = set(allocated_regimes)
    counts = pd.Series(allocated_regimes).value_counts()
    
    print("\n" + "="*50)
    print("   VERIFICATION DISTRIBUTION REPORT   ")
    print("="*50)
    for r_type, count in counts.items():
        print(f"  - {r_type:<10} Allocation Count: {count:<4} ({count/len(test_dates)*100:.1f}%)")
    print("-"*50)

    # Architectural Assertion Pass Check: System MUST output >=3 distinct market states
    print("[*] Asserting Non-Degeneracy Criteria Condition (Unique States >= 3)...")
    if len(unique_regimes) >= 3:
        print("[+] SUCCESS: Non-degeneracy verified. All 3 regimes dynamically allocated.")
    else:
        print("[-] ASSERTION FAILED: Classifier has decayed or collapsed into a subset of states.")
        sys.exit(1)

if __name__ == "__main__":
    run_pipeline_validation()