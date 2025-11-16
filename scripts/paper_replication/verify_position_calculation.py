#!/usr/bin/env python3
"""
Verify position calculation logic
Check if executor side information is correctly retrieved
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
END_DATE = datetime(2025, 1, 3)  # 2 days
INITIAL_PORTFOLIO_USD = 10000
TRADING_FEE = 0.0004
BACKTEST_RESOLUTION = "15m"


async def verify_position_calculation():
    """Verify position calculation logic"""
    print("="*80)
    print("Verifying Position Calculation Logic")
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
    
    # Check side information
    print(f"\n{'='*80}")
    print("Checking Executor Side Information")
    print(f"{'='*80}")
    
    buy_count = 0
    sell_count = 0
    none_count = 0
    
    for i, executor in enumerate(filled_executors[:20]):
        # Try to get side from multiple sources
        side = None
        side_source = None
        
        if hasattr(executor, 'side'):
            side = executor.side
            side_source = "executor.side"
        elif hasattr(executor, 'config') and hasattr(executor.config, 'side'):
            side = executor.config.side
            side_source = "executor.config.side"
        elif hasattr(executor, 'custom_info') and 'side' in executor.custom_info:
            side = executor.custom_info['side']
            side_source = "executor.custom_info['side']"
        
        if side == TradeType.BUY:
            buy_count += 1
        elif side == TradeType.SELL:
            sell_count += 1
        else:
            none_count += 1
        
        if i < 10:
            print(f"\nExecutor {i}:")
            print(f"  ID: {executor.id if hasattr(executor, 'id') else 'N/A'}")
            print(f"  Side: {side} (from {side_source})")
            print(f"  Timestamp: {datetime.fromtimestamp(executor.config.timestamp) if hasattr(executor, 'config') and hasattr(executor.config, 'timestamp') else 'N/A'}")
            print(f"  Close timestamp: {datetime.fromtimestamp(executor.close_timestamp) if hasattr(executor, 'close_timestamp') and executor.close_timestamp else 'N/A'}")
            print(f"  Filled amount: ${float(executor.filled_amount_quote):.2f}")
    
    print(f"\n{'='*80}")
    print("Side Distribution")
    print(f"{'='*80}")
    print(f"  BUY executors: {buy_count}")
    print(f"  SELL executors: {sell_count}")
    print(f"  None/Unknown: {none_count}")
    
    if none_count > 0:
        print(f"\n  ⚠ Found {none_count} executors with unknown side!")
    
    # Simulate position calculation
    print(f"\n{'='*80}")
    print("Simulating Position Calculation")
    print(f"{'='*80}")
    
    current_long = 0.0
    current_short = 0.0
    
    # Create timeline
    timestamps = pd.date_range(
        start=datetime.fromtimestamp(start_ts),
        end=datetime.fromtimestamp(end_ts),
        freq="15min"
    )
    
    # Process executors
    for executor in filled_executors:
        # Get side
        side = None
        if hasattr(executor, 'side'):
            side = executor.side
        elif hasattr(executor, 'config') and hasattr(executor.config, 'side'):
            side = executor.config.side
        elif hasattr(executor, 'custom_info') and 'side' in executor.custom_info:
            side = executor.custom_info['side']
        
        if side is None:
            continue
        
        # Get timestamps
        if hasattr(executor, 'config') and hasattr(executor.config, 'timestamp'):
            open_time = datetime.fromtimestamp(executor.config.timestamp)
            position_value = float(executor.filled_amount_quote)
            
            # Find closest timestamp in timeline
            closest_idx = timestamps.get_indexer([open_time], method='nearest')[0]
            if closest_idx >= 0:
                # Open position
                if side == TradeType.BUY:
                    current_long += position_value
                elif side == TradeType.SELL:
                    current_short += position_value
        
        if hasattr(executor, 'close_timestamp') and executor.close_timestamp:
            close_time = datetime.fromtimestamp(executor.close_timestamp)
            position_value = float(executor.filled_amount_quote)
            
            # Find closest timestamp in timeline
            closest_idx = timestamps.get_indexer([close_time], method='nearest')[0]
            if closest_idx >= 0:
                # Close position
                if side == TradeType.BUY:
                    current_long = max(0.0, current_long - position_value)
                elif side == TradeType.SELL:
                    current_short = max(0.0, current_short - position_value)
    
    print(f"\nFinal positions:")
    print(f"  Long: ${current_long:,.2f}")
    print(f"  Short: ${current_short:,.2f}")
    print(f"  Net: ${current_long - current_short:,.2f}")
    
    if current_long > 0 and current_short > 0:
        print(f"\n  ⚠ Both long and short positions exist simultaneously!")
        print(f"     This might indicate an issue with position calculation logic.")


if __name__ == "__main__":
    asyncio.run(verify_position_calculation())

