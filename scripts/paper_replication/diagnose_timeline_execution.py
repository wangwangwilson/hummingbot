#!/usr/bin/env python3
"""
诊断时序执行问题
检查数据连续性、executor创建时间、成交情况、仓位变化
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
from controllers.market_making.pmm_dynamic import PMMDynamicControllerConfig
from controllers.market_making.pmm_simple import PMMSimpleConfig
from hummingbot.strategy_v2.executors.position_executor.data_types import OrderType
from hummingbot.core.data_type.common import TradeType

# Import local data manager
from backtest_comparison_local import LocalBinanceDataProvider, LocalBacktestingDataProvider

# Test parameters
TRADING_PAIR = "BTC-USDT"
START_DATE = datetime(2025, 1, 1)
END_DATE = datetime(2025, 5, 1)
INITIAL_PORTFOLIO_USD = 10000
TRADING_FEE = 0.0004
BACKTEST_RESOLUTION = "1m"


async def diagnose_data_timeline():
    """诊断数据时间序列"""
    print("="*80)
    print("1. Data Timeline Diagnosis")
    print("="*80)
    
    start_ts = int(START_DATE.timestamp())
    end_ts = int(END_DATE.timestamp())
    
    local_data_provider = LocalBinanceDataProvider()
    
    # Load data
    df = local_data_provider.get_historical_candles(
        symbol=TRADING_PAIR,
        start_ts=start_ts,
        end_ts=end_ts,
        interval=BACKTEST_RESOLUTION
    )
    
    print(f"Data loaded: {len(df):,} candles")
    print(f"Time range: {datetime.fromtimestamp(df['timestamp'].min())} to {datetime.fromtimestamp(df['timestamp'].max())}")
    print(f"Expected range: {START_DATE} to {END_DATE}")
    
    # Check for gaps
    df_sorted = df.sort_values('timestamp')
    time_diffs = df_sorted['timestamp'].diff().dropna()
    expected_diff = 60  # 1 minute in seconds
    
    gaps = time_diffs[time_diffs > expected_diff * 1.5]
    print(f"\nTime gaps (>1.5x expected): {len(gaps)}")
    if len(gaps) > 0:
        print(f"  Max gap: {gaps.max() / 60:.1f} minutes")
        print(f"  Gap locations (first 10):")
        for idx in gaps.head(10).index:
            gap_ts = df_sorted.iloc[idx]['timestamp']
            gap_dt = datetime.fromtimestamp(gap_ts)
            print(f"    {gap_dt}: {gaps.loc[idx] / 60:.1f} minutes")
    
    # Check data distribution by month
    df_sorted['month'] = pd.to_datetime(df_sorted['timestamp'], unit='s').dt.to_period('M')
    monthly_counts = df_sorted['month'].value_counts().sort_index()
    print(f"\nData distribution by month:")
    for month, count in monthly_counts.items():
        print(f"  {month}: {count:,} candles")
    
    return df_sorted


async def diagnose_executor_timeline(strategy_name: str, config):
    """诊断executor的时间序列和成交情况"""
    print(f"\n{'='*80}")
    print(f"2. Executor Timeline Diagnosis: {strategy_name}")
    print(f"{'='*80}")
    
    start_ts = int(START_DATE.timestamp())
    end_ts = int(END_DATE.timestamp())
    
    # Initialize data provider
    local_data_provider = LocalBinanceDataProvider()
    local_backtesting_provider = LocalBacktestingDataProvider(local_data_provider)
    local_backtesting_provider.update_backtesting_time(start_ts, end_ts)
    
    # Initialize candles feed
    if hasattr(config, 'candles_connector'):
        candles_config = CandlesConfig(
            connector=config.candles_connector,
            trading_pair=config.candles_trading_pair,
            interval=config.interval,
            max_records=100000
        )
    else:
        candles_config = CandlesConfig(
            connector="binance_perpetual",
            trading_pair=TRADING_PAIR,
            interval=BACKTEST_RESOLUTION,
            max_records=100000
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
        print("  ✗ Backtest failed")
        return
    
    executors = result['executors']
    print(f"\nTotal Executors: {len(executors)}")
    
    # Analyze executors by timeline
    executor_timeline = []
    
    for i, executor in enumerate(executors):
        # Get side
        side = None
        if hasattr(executor, 'side'):
            side = executor.side
        elif hasattr(executor, 'config') and hasattr(executor.config, 'side'):
            side = executor.config.side
        elif hasattr(executor, 'custom_info') and 'side' in executor.custom_info:
            side = executor.custom_info['side']
        
        # Get timestamps
        open_ts = None
        close_ts = None
        
        if hasattr(executor, 'config') and hasattr(executor.config, 'timestamp'):
            open_ts = executor.config.timestamp
        if hasattr(executor, 'close_timestamp'):
            close_ts = executor.close_timestamp
        elif hasattr(executor, 'config') and hasattr(executor.config, 'close_timestamp'):
            close_ts = executor.config.close_timestamp
        
        # Get filled status
        filled = False
        filled_amount = 0.0
        if hasattr(executor, 'filled_amount_quote') and executor.filled_amount_quote:
            filled_amount = float(executor.filled_amount_quote)
            filled = filled_amount > 0
        
        # Get PnL
        pnl = 0.0
        if hasattr(executor, 'net_pnl_quote') and executor.net_pnl_quote:
            pnl = float(executor.net_pnl_quote)
        
        # Get entry price
        entry_price = None
        if hasattr(executor, 'entry_price'):
            entry_price = float(executor.entry_price)
        elif hasattr(executor, 'config') and hasattr(executor.config, 'entry_price'):
            entry_price = float(executor.config.entry_price)
        
        executor_timeline.append({
            'index': i,
            'side': side,
            'open_ts': open_ts,
            'close_ts': close_ts,
            'open_dt': datetime.fromtimestamp(open_ts) if open_ts else None,
            'close_dt': datetime.fromtimestamp(close_ts) if close_ts else None,
            'filled': filled,
            'filled_amount': filled_amount,
            'pnl': pnl,
            'entry_price': entry_price,
        })
    
    # Sort by open timestamp
    executor_timeline.sort(key=lambda x: x['open_ts'] or 0)
    
    # Print timeline
    print(f"\nExecutor Timeline (first 50):")
    print(f"{'Index':<6} {'Side':<6} {'Open Time':<20} {'Close Time':<20} {'Filled':<8} {'Amount':<12} {'PnL':<12}")
    print("-" * 100)
    
    filled_count = 0
    for e in executor_timeline[:50]:
        side_str = str(e['side']).split('.')[-1] if e['side'] else 'N/A'
        open_str = e['open_dt'].strftime('%Y-%m-%d %H:%M:%S') if e['open_dt'] else 'N/A'
        close_str = e['close_dt'].strftime('%Y-%m-%d %H:%M:%S') if e['close_dt'] else 'N/A'
        filled_str = 'Yes' if e['filled'] else 'No'
        amount_str = f"${e['filled_amount']:,.2f}" if e['filled_amount'] > 0 else "N/A"
        pnl_str = f"${e['pnl']:,.2f}" if e['pnl'] != 0 else "$0.00"
        
        print(f"{e['index']:<6} {side_str:<6} {open_str:<20} {close_str:<20} {filled_str:<8} {amount_str:<12} {pnl_str:<12}")
        
        if e['filled']:
            filled_count += 1
    
    if len(executor_timeline) > 50:
        print(f"... ({len(executor_timeline) - 50} more executors)")
    
    # Analyze filled executors
    filled_executors = [e for e in executor_timeline if e['filled']]
    print(f"\nFilled Executors: {len(filled_executors)}")
    
    if len(filled_executors) > 0:
        print(f"\nFilled Executor Timeline:")
        print(f"{'Index':<6} {'Side':<6} {'Open Time':<20} {'Close Time':<20} {'Amount':<12} {'PnL':<12}")
        print("-" * 100)
        
        for e in filled_executors:
            side_str = str(e['side']).split('.')[-1] if e['side'] else 'N/A'
            open_str = e['open_dt'].strftime('%Y-%m-%d %H:%M:%S') if e['open_dt'] else 'N/A'
            close_str = e['close_dt'].strftime('%Y-%m-%d %H:%M:%S') if e['close_dt'] else 'N/A'
            amount_str = f"${e['filled_amount']:,.2f}"
            pnl_str = f"${e['pnl']:,.2f}"
            
            print(f"{e['index']:<6} {side_str:<6} {open_str:<20} {close_str:<20} {amount_str:<12} {pnl_str:<12}")
        
        # Check time distribution
        if len(filled_executors) > 0:
            open_times = [e['open_ts'] for e in filled_executors if e['open_ts']]
            if open_times:
                first_open = datetime.fromtimestamp(min(open_times))
                last_open = datetime.fromtimestamp(max(open_times))
                print(f"\nFilled Executor Time Distribution:")
                print(f"  First filled: {first_open}")
                print(f"  Last filled: {last_open}")
                print(f"  Time span: {(max(open_times) - min(open_times)) / 86400:.1f} days")
                
                # Check if clustered at the end
                time_span = end_ts - start_ts
                last_week_start = end_ts - 7 * 86400
                last_week_count = sum(1 for ts in open_times if ts >= last_week_start)
                print(f"  Executors in last week: {last_week_count} / {len(open_times)} ({last_week_count/len(open_times)*100:.1f}%)")
                
                if last_week_count / len(open_times) > 0.5:
                    print(f"  ⚠ WARNING: Most executors are clustered at the end!")
    
    # Analyze by side
    buy_executors = [e for e in executor_timeline if e['side'] == TradeType.BUY]
    sell_executors = [e for e in executor_timeline if e['side'] == TradeType.SELL]
    filled_buy = [e for e in buy_executors if e['filled']]
    filled_sell = [e for e in sell_executors if e['filled']]
    
    print(f"\nExecutor Distribution by Side:")
    print(f"  BUY executors: {len(buy_executors)} (filled: {len(filled_buy)})")
    print(f"  SELL executors: {len(sell_executors)} (filled: {len(filled_sell)})")
    
    # Check position changes
    print(f"\nPosition Changes Analysis:")
    if len(filled_executors) > 0:
        # Sort by open time
        filled_sorted = sorted(filled_executors, key=lambda x: x['open_ts'] or 0)
        
        current_long = 0.0
        current_short = 0.0
        position_changes = []
        
        for e in filled_sorted:
            if e['side'] == TradeType.BUY:
                current_long += e['filled_amount']
                position_changes.append({
                    'time': e['open_dt'],
                    'type': 'open_long',
                    'amount': e['filled_amount'],
                    'long': current_long,
                    'short': current_short
                })
            elif e['side'] == TradeType.SELL:
                current_short += e['filled_amount']
                position_changes.append({
                    'time': e['open_dt'],
                    'type': 'open_short',
                    'amount': e['filled_amount'],
                    'long': current_long,
                    'short': current_short
                })
            
            if e['close_dt']:
                if e['side'] == TradeType.BUY:
                    current_long -= e['filled_amount']
                    position_changes.append({
                        'time': e['close_dt'],
                        'type': 'close_long',
                        'amount': e['filled_amount'],
                        'long': current_long,
                        'short': current_short
                    })
                elif e['side'] == TradeType.SELL:
                    current_short -= e['filled_amount']
                    position_changes.append({
                        'time': e['close_dt'],
                        'type': 'close_short',
                        'amount': e['filled_amount'],
                        'long': current_long,
                        'short': current_short
                    })
        
        print(f"  Total position changes: {len(position_changes)}")
        if len(position_changes) > 0:
            print(f"  First change: {position_changes[0]['time']}")
            print(f"  Last change: {position_changes[-1]['time']}")
            print(f"\n  Position Changes Timeline (first 20):")
            print(f"  {'Time':<20} {'Type':<12} {'Amount':<12} {'Long':<12} {'Short':<12}")
            print("  " + "-" * 80)
            for pc in position_changes[:20]:
                print(f"  {pc['time'].strftime('%Y-%m-%d %H:%M:%S'):<20} {pc['type']:<12} ${pc['amount']:>10,.2f} ${pc['long']:>10,.2f} ${pc['short']:>10,.2f}")


async def main():
    """主诊断函数"""
    # 1. Check data timeline
    df = await diagnose_data_timeline()
    
    # 2. Diagnose each strategy
    strategies = {
        "PMM_Simple": {
            "name": "PMM Simple",
            "config_class": PMMSimpleConfig,
            "params": {
                "buy_spreads": [0.005, 0.01, 0.02],
                "sell_spreads": [0.005, 0.01, 0.02],
                "buy_amounts_pct": [Decimal("0.33"), Decimal("0.33"), Decimal("0.34")],
                "sell_amounts_pct": [Decimal("0.33"), Decimal("0.33"), Decimal("0.34")],
                "stop_loss": Decimal("0.01"),
                "take_profit": Decimal("0.005"),
                "time_limit": 3600,
            }
        },
        "PMM_Dynamic": {
            "name": "PMM Dynamic (MACD)",
            "config_class": PMMDynamicControllerConfig,
            "params": {
                "buy_spreads": [0.01, 0.02, 0.04],
                "sell_spreads": [0.01, 0.02, 0.04],
                "buy_amounts_pct": [Decimal("0.33"), Decimal("0.33"), Decimal("0.34")],
                "sell_amounts_pct": [Decimal("0.33"), Decimal("0.33"), Decimal("0.34")],
                "stop_loss": Decimal("0.01"),
                "take_profit": Decimal("0.005"),
                "time_limit": 3600,
                "candles_connector": "binance_perpetual",
                "candles_trading_pair": TRADING_PAIR,
                "interval": BACKTEST_RESOLUTION,
            }
        },
        "PMM_Bar_Portion": {
            "name": "PMM Bar Portion",
            "config_class": PMMBarPortionControllerConfig,
            "params": {
                "buy_spreads": [0.01, 0.02],
                "sell_spreads": [0.01, 0.02],
                "buy_amounts_pct": [Decimal("0.5"), Decimal("0.5")],
                "sell_amounts_pct": [Decimal("0.5"), Decimal("0.5")],
                "stop_loss": Decimal("0.01"),
                "take_profit": Decimal("0.005"),
                "time_limit": 3600,
                "take_profit_order_type": OrderType.MARKET,
                "candles_connector": "binance_perpetual",
                "candles_trading_pair": TRADING_PAIR,
                "interval": BACKTEST_RESOLUTION,
            }
        }
    }
    
    for strategy_key, strategy_info in strategies.items():
        try:
            config_class = strategy_info["config_class"]
            params = strategy_info["params"].copy()
            common_params = {
                "controller_name": strategy_key.lower(),
                "connector_name": "binance_perpetual",
                "trading_pair": TRADING_PAIR,
                "total_amount_quote": Decimal(str(INITIAL_PORTFOLIO_USD)),
            }
            
            if strategy_key != "PMM_Simple":
                common_params.update({
                    "candles_connector": "binance_perpetual",
                    "candles_trading_pair": TRADING_PAIR,
                    "interval": BACKTEST_RESOLUTION,
                })
            
            all_params = {**common_params, **params}
            config = config_class(**all_params)
            
            await diagnose_executor_timeline(strategy_info['name'], config)
        except Exception as e:
            print(f"\n✗ Error diagnosing {strategy_info['name']}: {str(e)}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())

