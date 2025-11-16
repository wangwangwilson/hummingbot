#!/usr/bin/env python3
"""
Debug executor timestamps to understand why positions only appear at the end
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
from controllers.market_making.pmm_bar_portion import PMMBarPortionControllerConfig
from hummingbot.strategy_v2.executors.position_executor.data_types import OrderType
from hummingbot.core.data_type.common import TradeType

# Import local data manager
from backtest_comparison_local import LocalBinanceDataProvider, LocalBacktestingDataProvider

# Test parameters
TRADING_PAIR = "BTC-USDT"
START_DATE = datetime(2025, 1, 1)
END_DATE = datetime(2025, 1, 5)  # 4 days
INITIAL_PORTFOLIO_USD = 10000
TRADING_FEE = 0.0004
BACKTEST_RESOLUTION = "15m"


async def debug_executor_timestamps():
    """Debug executor timestamps"""
    print("="*80)
    print("Debugging Executor Timestamps")
    print("="*80)
    print(f"Trading Pair: {TRADING_PAIR}")
    print(f"Time Range: {START_DATE} to {END_DATE}")
    print()
    
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
    
    print("Running backtest...")
    result = await engine.run_backtesting(
        controller_config=config,
        start=start_ts,
        end=end_ts,
        backtesting_resolution=BACKTEST_RESOLUTION,
        trade_cost=Decimal(str(TRADING_FEE)),
        show_progress=False
    )
    
    if not result or 'executors' not in result:
        print("✗ Backtest failed")
        return
    
    executors = result['executors']
    filled_executors = [
        e for e in executors 
        if hasattr(e, 'filled_amount_quote') and e.filled_amount_quote and float(e.filled_amount_quote) > 0
    ]
    
    print(f"\nTotal Executors: {len(executors)}")
    print(f"Filled Executors: {len(filled_executors)}")
    
    if len(filled_executors) == 0:
        print("⚠ No filled executors!")
        return
    
    # Analyze timestamps
    print(f"\n{'='*80}")
    print("Executor Timestamp Analysis")
    print(f"{'='*80}")
    
    timestamps = []
    close_timestamps = []
    
    for i, executor in enumerate(filled_executors[:50]):  # Check first 50
        timestamp = None
        close_timestamp = None
        
        if hasattr(executor, 'config') and hasattr(executor.config, 'timestamp'):
            timestamp = executor.config.timestamp
            timestamps.append(timestamp)
        
        if hasattr(executor, 'close_timestamp') and executor.close_timestamp:
            close_timestamp = executor.close_timestamp
            close_timestamps.append(close_timestamp)
        
        if i < 10:  # Print first 10
            print(f"\nExecutor {i}:")
            print(f"  ID: {executor.id if hasattr(executor, 'id') else 'N/A'}")
            print(f"  Side: {executor.side if hasattr(executor, 'side') else 'N/A'}")
            if timestamp:
                print(f"  Timestamp (open): {datetime.fromtimestamp(timestamp)} ({timestamp})")
                print(f"    Expected range: {START_DATE} ({start_ts}) to {END_DATE} ({end_ts})")
                if timestamp < start_ts or timestamp > end_ts:
                    print(f"    ⚠ OUT OF RANGE!")
            else:
                print(f"  Timestamp (open): N/A")
            
            if close_timestamp:
                print(f"  Close timestamp: {datetime.fromtimestamp(close_timestamp)} ({close_timestamp})")
            else:
                print(f"  Close timestamp: N/A")
            
            print(f"  Filled amount: ${float(executor.filled_amount_quote):.2f}")
            print(f"  PnL: ${float(executor.net_pnl_quote):.2f}")
    
    if timestamps:
        print(f"\n{'='*80}")
        print("Timestamp Statistics")
        print(f"{'='*80}")
        print(f"Total executors with timestamp: {len(timestamps)}")
        print(f"Min timestamp: {datetime.fromtimestamp(min(timestamps))} ({min(timestamps)})")
        print(f"Max timestamp: {datetime.fromtimestamp(max(timestamps))} ({max(timestamps)})")
        print(f"Expected range: {START_DATE} ({start_ts}) to {END_DATE} ({end_ts})")
        
        # Check if timestamps are in range
        out_of_range = [ts for ts in timestamps if ts < start_ts or ts > end_ts]
        if out_of_range:
            print(f"\n⚠ Found {len(out_of_range)} executors with timestamps outside expected range!")
            print(f"  Out of range timestamps: {[datetime.fromtimestamp(ts) for ts in out_of_range[:5]]}")
        else:
            print(f"\n✓ All timestamps are within expected range")
        
        # Check timestamp distribution
        timestamps_sorted = sorted(timestamps)
        if len(timestamps_sorted) > 1:
            time_diffs = [timestamps_sorted[i+1] - timestamps_sorted[i] for i in range(len(timestamps_sorted)-1)]
            print(f"\nTimestamp intervals:")
            print(f"  Min interval: {min(time_diffs)/3600:.2f} hours")
            print(f"  Max interval: {max(time_diffs)/3600:.2f} hours")
            print(f"  Avg interval: {sum(time_diffs)/len(time_diffs)/3600:.2f} hours")
            
            # Check if timestamps are clustered at the end
            first_quarter = timestamps_sorted[:len(timestamps_sorted)//4]
            last_quarter = timestamps_sorted[-len(timestamps_sorted)//4:]
            
            first_quarter_span = (max(first_quarter) - min(first_quarter)) / 3600 if len(first_quarter) > 1 else 0
            last_quarter_span = (max(last_quarter) - min(last_quarter)) / 3600 if len(last_quarter) > 1 else 0
            
            print(f"\nTimestamp distribution:")
            print(f"  First quarter span: {first_quarter_span:.2f} hours")
            print(f"  Last quarter span: {last_quarter_span:.2f} hours")
            
            if last_quarter_span < first_quarter_span * 0.1:
                print(f"  ⚠ Timestamps are clustered at the end!")
    
    if close_timestamps:
        print(f"\n{'='*80}")
        print("Close Timestamp Statistics")
        print(f"{'='*80}")
        print(f"Total executors with close_timestamp: {len(close_timestamps)}")
        print(f"Min close_timestamp: {datetime.fromtimestamp(min(close_timestamps))} ({min(close_timestamps)})")
        print(f"Max close_timestamp: {datetime.fromtimestamp(max(close_timestamps))} ({max(close_timestamps)})")


if __name__ == "__main__":
    asyncio.run(debug_executor_timestamps())

