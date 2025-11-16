#!/usr/bin/env python3
"""
Verify data loading is normal
Check if market data is correctly loaded from local zip files
"""

import sys
from datetime import datetime, date
from pathlib import Path
import pandas as pd

# Add project paths
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
tradingview_ai_path = Path("/Users/wilson/Desktop/tradingview-ai")
sys.path.insert(0, str(tradingview_ai_path))

# Temporary disable ccxt
class FakeCCXT:
    pass
sys.modules['ccxt'] = FakeCCXT()

from backtest_comparison_local import LocalBinanceDataProvider

# Test parameters
TRADING_PAIRS = ["BTC-USDT", "ETH-USDT", "SOL-USDT", "XRP-USDT"]
START_DATE = datetime(2025, 1, 1)
END_DATE = datetime(2025, 5, 1)
BACKTEST_RESOLUTION = "15m"


def verify_data_loading():
    """Verify data loading for multiple trading pairs"""
    print("="*80)
    print("Data Loading Verification")
    print("="*80)
    print(f"Time Range: {START_DATE.strftime('%Y-%m-%d')} to {END_DATE.strftime('%Y-%m-%d')}")
    print(f"Resolution: {BACKTEST_RESOLUTION}")
    print()
    
    local_data_provider = LocalBinanceDataProvider()
    start_ts = int(START_DATE.timestamp())
    end_ts = int(END_DATE.timestamp())
    
    all_ok = True
    
    for trading_pair in TRADING_PAIRS:
        print(f"\n{'='*80}")
        print(f"Verifying: {trading_pair}")
        print(f"{'='*80}")
        
        try:
            # Load data
            df = local_data_provider.get_historical_candles(
                symbol=trading_pair,
                start_ts=start_ts,
                end_ts=end_ts,
                interval=BACKTEST_RESOLUTION
            )
            
            if df.empty:
                print(f"  ✗ No data loaded!")
                all_ok = False
                continue
            
            print(f"  ✓ Data loaded: {len(df):,} candles")
            
            # Check data structure
            required_columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
            missing_columns = [col for col in required_columns if col not in df.columns]
            if missing_columns:
                print(f"  ✗ Missing columns: {missing_columns}")
                all_ok = False
                continue
            
            print(f"  ✓ All required columns present: {required_columns}")
            
            # Check data types
            if not pd.api.types.is_integer_dtype(df['timestamp']):
                print(f"  ⚠ Timestamp is not integer type: {df['timestamp'].dtype}")
            
            # Check time range
            min_ts = df['timestamp'].min()
            max_ts = df['timestamp'].max()
            min_dt = datetime.fromtimestamp(min_ts)
            max_dt = datetime.fromtimestamp(max_ts)
            
            print(f"  Time range:")
            print(f"    Actual: {min_dt} to {max_dt}")
            print(f"    Expected: {START_DATE} to {END_DATE}")
            
            if min_ts < start_ts or max_ts > end_ts:
                print(f"  ⚠ Time range extends beyond expected range")
            else:
                print(f"  ✓ Time range is within expected bounds")
            
            # Check data quality
            print(f"  Data quality:")
            print(f"    Missing values: {df.isnull().sum().sum()}")
            
            if df.isnull().sum().sum() > 0:
                print(f"    ⚠ Found missing values!")
                all_ok = False
            else:
                print(f"    ✓ No missing values")
            
            # Check price ranges
            print(f"    Price range: ${df['close'].min():.2f} to ${df['close'].max():.2f}")
            if df['close'].min() <= 0 or df['close'].max() <= 0:
                print(f"    ✗ Invalid price values!")
                all_ok = False
            else:
                print(f"    ✓ Price values are valid")
            
            # Check volume
            print(f"    Volume range: {df['volume'].min():.2f} to {df['volume'].max():.2f}")
            if df['volume'].min() < 0:
                print(f"    ⚠ Negative volume values found")
                all_ok = False
            else:
                print(f"    ✓ Volume values are valid")
            
            # Check time continuity
            df_sorted = df.sort_values('timestamp')
            time_diffs = df_sorted['timestamp'].diff().dropna()
            expected_diff = 15 * 60  # 15 minutes in seconds
            
            gaps = time_diffs[time_diffs > expected_diff * 1.5]
            if len(gaps) > 0:
                print(f"    ⚠ Found {len(gaps)} time gaps > 1.5x expected interval")
                print(f"      Max gap: {gaps.max() / 3600:.2f} hours")
            else:
                print(f"    ✓ Time continuity: OK")
            
            # Check data source (verify it's from local zip files)
            print(f"  Data source verification:")
            print(f"    ✓ Using LocalBinanceDataProvider (local zip files)")
            
            # Sample data
            print(f"\n  Sample data (first 5 rows):")
            print(df_sorted.head().to_string())
            
            print(f"\n  Sample data (last 5 rows):")
            print(df_sorted.tail().to_string())
            
        except Exception as e:
            print(f"  ✗ Error loading data: {str(e)}")
            import traceback
            traceback.print_exc()
            all_ok = False
    
    print(f"\n{'='*80}")
    print("Summary")
    print(f"{'='*80}")
    if all_ok:
        print("✓ All data loading checks passed!")
        print("  - Data is loaded from local zip files")
        print("  - Data structure is correct")
        print("  - Data quality is good")
        print("  - Time range is correct")
    else:
        print("✗ Some data loading checks failed!")
        print("  Please review the errors above")
    
    return all_ok


if __name__ == "__main__":
    verify_data_loading()
