#!/usr/bin/env python3
"""
Diagnose backtest issues:
1. Data loading verification
2. Strategy logic and signal generation
3. Executor creation and position storage
"""

import asyncio
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path
import pandas as pd

# Configure SSL certificates
cert_file = Path.home() / ".hummingbot_certs.pem"
if cert_file.exists():
    import os
    os.environ['SSL_CERT_FILE'] = str(cert_file)
    os.environ['REQUESTS_CA_BUNDLE'] = str(cert_file)
    os.environ['CURL_CA_BUNDLE'] = str(cert_file)

# Add project paths
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
tradingview_ai_path = Path("/Users/wilson/Desktop/tradingview-ai")
sys.path.insert(0, str(tradingview_ai_path))

# Temporary disable ccxt
class FakeCCXT:
    pass
sys.modules['ccxt'] = FakeCCXT()

from hummingbot.strategy_v2.backtesting.backtesting_engine_base import BacktestingEngineBase
from hummingbot.data_feed.candles_feed.data_types import CandlesConfig
from controllers.market_making.pmm_bar_portion import PMMBarPortionControllerConfig, PMMBarPortionController
from hummingbot.strategy_v2.executors.position_executor.data_types import OrderType
from hummingbot.core.data_type.common import TradeType

# Import local data manager
from backtest_comparison_local import LocalBinanceDataProvider, LocalBacktestingDataProvider

# Test parameters
TRADING_PAIR = "BTC-USDT"
START_DATE = datetime(2025, 1, 1)
END_DATE = datetime(2025, 1, 5)  # 4 days for quick test
INITIAL_PORTFOLIO_USD = 10000
TRADING_FEE = 0.0004
BACKTEST_RESOLUTION = "15m"


async def diagnose_data_loading():
    """Diagnose data loading issues"""
    print("="*80)
    print("1. Data Loading Diagnosis")
    print("="*80)
    
    local_data_provider = LocalBinanceDataProvider()
    start_ts = int(START_DATE.timestamp())
    end_ts = int(END_DATE.timestamp())
    
    # Test data loading
    print(f"\nLoading data for {TRADING_PAIR}...")
    print(f"Time range: {START_DATE} to {END_DATE}")
    
    df = local_data_provider.get_historical_candles(
        symbol=TRADING_PAIR,
        start_ts=start_ts,
        end_ts=end_ts,
        interval=BACKTEST_RESOLUTION
    )
    
    if df.empty:
        print("✗ No data loaded!")
        return False
    
    print(f"✓ Data loaded: {len(df)} candles")
    print(f"  Columns: {list(df.columns)}")
    print(f"  Time range: {datetime.fromtimestamp(df['timestamp'].min())} to {datetime.fromtimestamp(df['timestamp'].max())}")
    print(f"  Expected time range: {START_DATE} to {END_DATE}")
    
    # Check data quality
    print(f"\nData Quality:")
    print(f"  - Missing values: {df.isnull().sum().sum()}")
    print(f"  - Price range: ${df['close'].min():.2f} to ${df['close'].max():.2f}")
    print(f"  - Volume range: {df['volume'].min():.2f} to {df['volume'].max():.2f}")
    
    # Check time continuity
    df_sorted = df.sort_values('timestamp')
    time_diffs = df_sorted['timestamp'].diff()
    expected_diff = 15 * 60  # 15 minutes in seconds
    gaps = time_diffs[time_diffs > expected_diff * 1.5]
    
    if len(gaps) > 0:
        print(f"  ⚠ Found {len(gaps)} time gaps > 1.5x expected interval")
        print(f"    Max gap: {gaps.max() / 60:.1f} minutes")
    else:
        print(f"  ✓ Time continuity: OK")
    
    return True


async def diagnose_strategy_signals():
    """Diagnose strategy signal generation"""
    print("\n" + "="*80)
    print("2. Strategy Signal Generation Diagnosis")
    print("="*80)
    
    start_ts = int(START_DATE.timestamp())
    end_ts = int(END_DATE.timestamp())
    
    # Initialize data provider
    local_data_provider = LocalBinanceDataProvider()
    local_backtesting_provider = LocalBacktestingDataProvider(local_data_provider)
    local_backtesting_provider.update_backtesting_time(start_ts, end_ts)
    
    # Create controller config
    config = PMMBarPortionControllerConfig(
        controller_name="pmm_bar_portion",
        connector_name="binance_perpetual",
        trading_pair=TRADING_PAIR,
        total_amount_quote=Decimal(str(INITIAL_PORTFOLIO_USD)),
        buy_spreads=[0.01, 0.02],
        sell_spreads=[0.01, 0.02],
        buy_amounts_pct=[Decimal("0.5"), Decimal("0.5")],
        sell_amounts_pct=[Decimal("0.5"), Decimal("0.5")],
        stop_loss=Decimal("0.01"),
        take_profit=Decimal("0.005"),
        time_limit=3600,
        take_profit_order_type=OrderType.MARKET,
        candles_connector="binance_perpetual",
        candles_trading_pair=TRADING_PAIR,
        interval=BACKTEST_RESOLUTION,
    )
    
    # Initialize candles feed
    candles_config = CandlesConfig(
        connector=config.candles_connector,
        trading_pair=config.candles_trading_pair,
        interval=config.interval,
        max_records=10000
    )
    await local_backtesting_provider.initialize_candles_feed([candles_config])
    
    # Create controller
    controller = PMMBarPortionController(
        config=config,
        market_data_provider=local_backtesting_provider,
        actions_queue=None
    )
    
    # Get candles data
    candles_df = local_backtesting_provider.get_candles_df(
        connector_name=config.candles_connector,
        trading_pair=config.candles_trading_pair,
        interval=config.interval
    )
    
    print(f"\nCandles data: {len(candles_df)} rows")
    print(f"  Time range: {datetime.fromtimestamp(candles_df.index.min())} to {datetime.fromtimestamp(candles_df.index.max())}")
    
    # Check processed_data updates
    print(f"\nChecking processed_data updates...")
    sample_size = min(100, len(candles_df))
    updates_with_data = 0
    updates_with_features = 0
    
    for i in range(sample_size):
        row = candles_df.iloc[i]
        timestamp = row.name if hasattr(row, 'name') else candles_df.index[i]
        
        # Update processed data
        controller.update_processed_data(row)
        
        # Check if processed_data has data
        if hasattr(controller, 'processed_data') and controller.processed_data:
            updates_with_data += 1
            
            # Check for features
            if 'features' in controller.processed_data:
                features = controller.processed_data['features']
                if not features.empty:
                    updates_with_features += 1
    
    print(f"  Updates with processed_data: {updates_with_data}/{sample_size}")
    print(f"  Updates with features: {updates_with_features}/{sample_size}")
    
    # Check reference_price and spread_multiplier
    if hasattr(controller, 'processed_data') and 'reference_price' in controller.processed_data:
        ref_price = controller.processed_data['reference_price']
        print(f"  Current reference_price: {ref_price}")
    
    if hasattr(controller, 'processed_data') and 'spread_multiplier' in controller.processed_data:
        spread_mult = controller.processed_data['spread_multiplier']
        print(f"  Current spread_multiplier: {spread_mult}")
    
    return True


async def diagnose_executor_creation():
    """Diagnose executor creation and storage"""
    print("\n" + "="*80)
    print("3. Executor Creation and Storage Diagnosis")
    print("="*80)
    
    start_ts = int(START_DATE.timestamp())
    end_ts = int(END_DATE.timestamp())
    
    # Initialize data provider
    local_data_provider = LocalBinanceDataProvider()
    local_backtesting_provider = LocalBacktestingDataProvider(local_data_provider)
    local_backtesting_provider.update_backtesting_time(start_ts, end_ts)
    
    # Create config
    config = PMMBarPortionControllerConfig(
        controller_name="pmm_bar_portion",
        connector_name="binance_perpetual",
        trading_pair=TRADING_PAIR,
        total_amount_quote=Decimal(str(INITIAL_PORTFOLIO_USD)),
        buy_spreads=[0.01, 0.02],
        sell_spreads=[0.01, 0.02],
        buy_amounts_pct=[Decimal("0.5"), Decimal("0.5")],
        sell_amounts_pct=[Decimal("0.5"), Decimal("0.5")],
        stop_loss=Decimal("0.01"),
        take_profit=Decimal("0.005"),
        time_limit=3600,
        take_profit_order_type=OrderType.MARKET,
        candles_connector="binance_perpetual",
        candles_trading_pair=TRADING_PAIR,
        interval=BACKTEST_RESOLUTION,
    )
    
    # Initialize candles feed
    candles_config = CandlesConfig(
        connector=config.candles_connector,
        trading_pair=config.candles_trading_pair,
        interval=config.interval,
        max_records=10000
    )
    await local_backtesting_provider.initialize_candles_feed([candles_config])
    
    # Run backtest
    engine = BacktestingEngineBase()
    engine.backtesting_data_provider = local_backtesting_provider
    
    print(f"\nRunning backtest...")
    result = await engine.run_backtesting(
        controller_config=config,
        start=start_ts,
        end=end_ts,
        backtesting_resolution=BACKTEST_RESOLUTION,
        trade_cost=Decimal(str(TRADING_FEE)),
        show_progress=False
    )
    
    if not result or 'executors' not in result:
        print("✗ Backtest failed or no executors returned")
        return False
    
    executors = result['executors']
    print(f"✓ Backtest completed: {len(executors)} executors")
    
    # Analyze executors
    filled_executors = [
        e for e in executors 
        if hasattr(e, 'filled_amount_quote') and e.filled_amount_quote and float(e.filled_amount_quote) > 0
    ]
    
    print(f"\nExecutor Analysis:")
    print(f"  Total executors: {len(executors)}")
    print(f"  Filled executors: {len(filled_executors)}")
    
    if len(filled_executors) == 0:
        print("  ⚠ No filled executors!")
        return False
    
    # Check executor timestamps
    print(f"\nChecking executor timestamps...")
    executors_with_timestamp = 0
    executors_with_close_timestamp = 0
    timestamp_issues = []
    
    for i, executor in enumerate(filled_executors[:20]):  # Check first 20
        has_timestamp = False
        has_close_timestamp = False
        timestamp_value = None
        close_timestamp_value = None
        
        # Check config.timestamp (open time)
        if hasattr(executor, 'config') and hasattr(executor.config, 'timestamp'):
            has_timestamp = True
            timestamp_value = executor.config.timestamp
            executors_with_timestamp += 1
        
        # Check close_timestamp
        if hasattr(executor, 'close_timestamp') and executor.close_timestamp:
            has_close_timestamp = True
            close_timestamp_value = executor.close_timestamp
            executors_with_close_timestamp += 1
        
        # Check if timestamps are valid
        if has_timestamp and has_close_timestamp:
            if close_timestamp_value <= timestamp_value:
                timestamp_issues.append(f"Executor {i}: close_timestamp ({close_timestamp_value}) <= timestamp ({timestamp_value})")
        
        if i < 5:  # Print first 5
            print(f"  Executor {i}:")
            print(f"    ID: {executor.id if hasattr(executor, 'id') else 'N/A'}")
            print(f"    Side: {executor.side if hasattr(executor, 'side') else 'N/A'}")
            print(f"    Timestamp (open): {datetime.fromtimestamp(timestamp_value) if timestamp_value else 'N/A'}")
            print(f"    Close timestamp: {datetime.fromtimestamp(close_timestamp_value) if close_timestamp_value else 'N/A'}")
            print(f"    Filled amount: ${float(executor.filled_amount_quote):.2f}" if hasattr(executor, 'filled_amount_quote') else "    Filled amount: N/A")
            print(f"    PnL: ${float(executor.net_pnl_quote):.2f}" if hasattr(executor, 'net_pnl_quote') else "    PnL: N/A")
    
    print(f"\n  Executors with timestamp: {executors_with_timestamp}/{len(filled_executors)}")
    print(f"  Executors with close_timestamp: {executors_with_close_timestamp}/{len(filled_executors)}")
    
    if timestamp_issues:
        print(f"\n  ⚠ Found {len(timestamp_issues)} timestamp issues:")
        for issue in timestamp_issues[:5]:
            print(f"    - {issue}")
    
    # Check timestamp distribution
    if executors_with_timestamp > 0:
        timestamps = [
            datetime.fromtimestamp(e.config.timestamp) 
            for e in filled_executors 
            if hasattr(e, 'config') and hasattr(e.config, 'timestamp')
        ]
        
        if timestamps:
            print(f"\n  Timestamp distribution:")
            print(f"    First executor: {min(timestamps)}")
            print(f"    Last executor: {max(timestamps)}")
            print(f"    Expected range: {START_DATE} to {END_DATE}")
            
            # Check if timestamps are within expected range
            if min(timestamps) < START_DATE or max(timestamps) > END_DATE:
                print(f"    ⚠ Some timestamps are outside expected range!")
    
    return True


async def main():
    """Run all diagnostics"""
    print("="*80)
    print("Backtest Issues Diagnosis")
    print("="*80)
    print(f"Trading Pair: {TRADING_PAIR}")
    print(f"Time Range: {START_DATE} to {END_DATE}")
    print(f"Resolution: {BACKTEST_RESOLUTION}")
    print()
    
    # Run diagnostics
    data_ok = await diagnose_data_loading()
    if not data_ok:
        print("\n✗ Data loading failed, stopping diagnosis")
        return
    
    await diagnose_strategy_signals()
    await diagnose_executor_creation()
    
    print("\n" + "="*80)
    print("Diagnosis Complete")
    print("="*80)


if __name__ == "__main__":
    asyncio.run(main())

