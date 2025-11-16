#!/usr/bin/env python3
"""
Check why there are no SELL executors or why positions are incorrect
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


async def check_executor_sides():
    """Check executor sides and why positions might be wrong"""
    print("="*80)
    print("Checking Executor Sides and Position Logic")
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
    
    # Analyze by side
    buy_executors = []
    sell_executors = []
    unknown_executors = []
    
    for executor in filled_executors:
        side = None
        if hasattr(executor, 'side'):
            side = executor.side
        elif hasattr(executor, 'config') and hasattr(executor.config, 'side'):
            side = executor.config.side
        elif hasattr(executor, 'custom_info') and 'side' in executor.custom_info:
            side = executor.custom_info['side']
        
        if side == TradeType.BUY:
            buy_executors.append(executor)
        elif side == TradeType.SELL:
            sell_executors.append(executor)
        else:
            unknown_executors.append(executor)
    
    print(f"\n{'='*80}")
    print("Executor Side Distribution")
    print(f"{'='*80}")
    print(f"  BUY executors: {len(buy_executors)}")
    print(f"  SELL executors: {len(sell_executors)}")
    print(f"  Unknown side: {len(unknown_executors)}")
    
    if len(sell_executors) == 0:
        print(f"\n  ⚠ WARNING: No SELL executors found!")
        print(f"     This could explain why positions are incorrect.")
        print(f"     Possible causes:")
        print(f"     1. Strategy only creates BUY orders")
        print(f"     2. SELL orders are not being filled")
        print(f"     3. SELL executors are not being created")
    
    # Check executor timestamps distribution
    print(f"\n{'='*80}")
    print("Executor Timestamp Distribution")
    print(f"{'='*80}")
    
    if buy_executors:
        buy_timestamps = [e.config.timestamp for e in buy_executors if hasattr(e, 'config') and hasattr(e.config, 'timestamp')]
        if buy_timestamps:
            print(f"  BUY executors:")
            print(f"    First: {datetime.fromtimestamp(min(buy_timestamps))}")
            print(f"    Last: {datetime.fromtimestamp(max(buy_timestamps))}")
            print(f"    Count: {len(buy_timestamps)}")
    
    if sell_executors:
        sell_timestamps = [e.config.timestamp for e in sell_executors if hasattr(e, 'config') and hasattr(e.config, 'timestamp')]
        if sell_timestamps:
            print(f"  SELL executors:")
            print(f"    First: {datetime.fromtimestamp(min(sell_timestamps))}")
            print(f"    Last: {datetime.fromtimestamp(max(sell_timestamps))}")
            print(f"    Count: {len(sell_timestamps)}")
    
    # Check if executors are clustered at the end
    all_timestamps = []
    for executor in filled_executors:
        if hasattr(executor, 'config') and hasattr(executor.config, 'timestamp'):
            all_timestamps.append(executor.config.timestamp)
    
    if all_timestamps:
        all_timestamps.sort()
        first_quarter_end = all_timestamps[len(all_timestamps)//4]
        last_quarter_start = all_timestamps[-len(all_timestamps)//4]
        
        first_quarter_count = sum(1 for ts in all_timestamps if ts <= first_quarter_end)
        last_quarter_count = sum(1 for ts in all_timestamps if ts >= last_quarter_start)
        
        print(f"\n  Timestamp distribution:")
        print(f"    First quarter: {first_quarter_count} executors")
        print(f"    Last quarter: {last_quarter_count} executors")
        
        if last_quarter_count > first_quarter_count * 3:
            print(f"    ⚠ Executors are clustered at the end!")
            print(f"       This could explain why positions only appear at the end.")
    
    # Check executor creation logic
    print(f"\n{'='*80}")
    print("Checking Strategy Logic")
    print(f"{'='*80}")
    
    # Check if strategy creates both buy and sell executors
    print(f"  Strategy config:")
    print(f"    Buy spreads: {config.buy_spreads}")
    print(f"    Sell spreads: {config.sell_spreads}")
    print(f"    Buy amounts: {config.buy_amounts_pct}")
    print(f"    Sell amounts: {config.sell_amounts_pct}")
    
    if len(config.buy_spreads) > 0 and len(config.sell_spreads) > 0:
        print(f"  ✓ Strategy should create both BUY and SELL executors")
    else:
        print(f"  ⚠ Strategy may not create both BUY and SELL executors")


if __name__ == "__main__":
    asyncio.run(check_executor_sides())

