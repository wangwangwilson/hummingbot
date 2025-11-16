#!/usr/bin/env python3
"""
Test BTC position and PnL curves for 2025-01-01 to 2025-05-01
Verify that positions change continuously with alternating long/short positions
"""

import asyncio
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

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
BACKTEST_RESOLUTION = "15m"
AGGREGATION_FREQUENCY = "15min"


def generate_position_curve_corrected(executors, start_ts: int, end_ts: int) -> pd.DataFrame:
    """
    Generate corrected position and equity curves
    Position should change continuously as executors open and close
    """
    if not executors:
        return pd.DataFrame()
    
    # Filter filled executors
    filled_executors = [
        e for e in executors 
        if hasattr(e, 'filled_amount_quote') and e.filled_amount_quote and float(e.filled_amount_quote) > 0
    ]
    
    if not filled_executors:
        return pd.DataFrame()
    
    # Create timeline with 15-minute frequency
    start_dt = datetime.fromtimestamp(start_ts)
    end_dt = datetime.fromtimestamp(end_ts)
    timestamps = pd.date_range(
        start=start_dt,
        end=end_dt,
        freq=AGGREGATION_FREQUENCY
    )
    
    # Initialize equity curve
    equity_curve = pd.DataFrame({
        'timestamp': timestamps,
        'equity': float(INITIAL_PORTFOLIO_USD),
        'position_value': 0.0,
        'cumulative_pnl': 0.0,
        'long_position': 0.0,
        'short_position': 0.0,
    })
    equity_curve.set_index('timestamp', inplace=True)
    
    # Create events: executor open and close
    events = []
    for executor in filled_executors:
        # Get side information - try multiple sources
        side = None
        if hasattr(executor, 'side'):
            side = executor.side
        elif hasattr(executor, 'config') and hasattr(executor.config, 'side'):
            side = executor.config.side
        elif hasattr(executor, 'custom_info') and 'side' in executor.custom_info:
            side = executor.custom_info['side']
        
        # Get open time (timestamp)
        if hasattr(executor, 'config') and hasattr(executor.config, 'timestamp'):
            open_time = datetime.fromtimestamp(executor.config.timestamp)
            position_value = float(executor.filled_amount_quote)
            
            # Add open event
            events.append({
                'timestamp': open_time,
                'type': 'open',
                'position_value': position_value,
                'side': side,
                'executor_id': executor.id if hasattr(executor, 'id') else None
            })
        
        # Get close time (close_timestamp)
        if hasattr(executor, 'close_timestamp') and executor.close_timestamp:
            close_time = datetime.fromtimestamp(executor.close_timestamp)
            pnl = float(executor.net_pnl_quote) if hasattr(executor, 'net_pnl_quote') else 0.0
            position_value = float(executor.filled_amount_quote)
            
            # Add close event
            events.append({
                'timestamp': close_time,
                'type': 'close',
                'position_value': position_value,
                'pnl': pnl,
                'side': side,  # Use same side as open
                'executor_id': executor.id if hasattr(executor, 'id') else None
            })
    
    # Sort events by timestamp
    events.sort(key=lambda x: x['timestamp'])
    
    # Process events to build position and PnL curves
    current_long_position = 0.0
    current_short_position = 0.0
    cumulative_pnl = 0.0
    event_idx = 0
    
    for idx, row in equity_curve.iterrows():
        # Process all events that occurred before or at this timestamp
        while event_idx < len(events):
            event = events[event_idx]
            if event['timestamp'] <= idx:
                if event['type'] == 'open':
                    # Open position: add to current position
                    if event['side'] == TradeType.BUY:
                        current_long_position += event['position_value']
                    elif event['side'] == TradeType.SELL:
                        current_short_position += event['position_value']
                    else:
                        # If side is unknown, assume it's a long position
                        current_long_position += event['position_value']
                elif event['type'] == 'close':
                    # Close position: remove from current position and add PnL
                    if event['side'] == TradeType.BUY:
                        current_long_position -= event['position_value']
                    elif event['side'] == TradeType.SELL:
                        current_short_position -= event['position_value']
                    else:
                        # If side is unknown, assume it's a long position
                        current_long_position -= event['position_value']
                    
                    cumulative_pnl += event.get('pnl', 0.0)
                
                event_idx += 1
            else:
                break
        
        # Update equity curve at this timestamp
        total_position = current_long_position - current_short_position  # Net position
        equity_curve.loc[idx, 'long_position'] = float(current_long_position)
        equity_curve.loc[idx, 'short_position'] = float(current_short_position)
        equity_curve.loc[idx, 'position_value'] = float(abs(total_position))  # Absolute value for display
        equity_curve.loc[idx, 'cumulative_pnl'] = float(cumulative_pnl)
        equity_curve.loc[idx, 'equity'] = float(INITIAL_PORTFOLIO_USD + cumulative_pnl)
    
    return equity_curve


async def test_btc_strategies():
    """Test all three strategies for BTC"""
    print("="*80)
    print("Testing BTC Position and PnL Curves")
    print("="*80)
    print(f"Trading Pair: {TRADING_PAIR}")
    print(f"Time Range: {START_DATE.strftime('%Y-%m-%d')} to {END_DATE.strftime('%Y-%m-%d')}")
    print()
    
    start_ts = int(START_DATE.timestamp())
    end_ts = int(END_DATE.timestamp())
    
    # Initialize data provider
    local_data_provider = LocalBinanceDataProvider()
    local_backtesting_provider = LocalBacktestingDataProvider(local_data_provider)
    local_backtesting_provider.update_backtesting_time(start_ts, end_ts)
    
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
    
    all_curves = {}
    
    for strategy_key, strategy_info in strategies.items():
        print(f"\n{'='*80}")
        print(f"Testing {strategy_info['name']}")
        print(f"{'='*80}")
        
        try:
            # Create config
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
            
            # Initialize candles feed
            if hasattr(config, 'candles_connector'):
                candles_config = CandlesConfig(
                    connector=config.candles_connector,
                    trading_pair=config.candles_trading_pair,
                    interval=config.interval,
                    max_records=10000
                )
            else:
                candles_config = CandlesConfig(
                    connector="binance_perpetual",
                    trading_pair=TRADING_PAIR,
                    interval=BACKTEST_RESOLUTION,
                    max_records=10000
                )
            await local_backtesting_provider.initialize_candles_feed([candles_config])
            
            # Run backtest
            engine = BacktestingEngineBase()
            engine.backtesting_data_provider = local_backtesting_provider
            
            result = await engine.run_backtesting(
                controller_config=config,
                start=start_ts,
                end=end_ts,
                backtesting_resolution=BACKTEST_RESOLUTION,
                trade_cost=Decimal(str(TRADING_FEE)),
                show_progress=True
            )
            
            if result and 'executors' in result:
                executors = result['executors']
                filled_count = sum(1 for e in executors if hasattr(e, 'filled_amount_quote') and e.filled_amount_quote and float(e.filled_amount_quote) > 0)
                print(f"  Total Executors: {len(executors)}")
                print(f"  Filled Executors: {filled_count}")
                
                # Generate corrected position curve
                curve = generate_position_curve_corrected(executors, start_ts, end_ts)
                if not curve.empty:
                    all_curves[strategy_info['name']] = curve
                    print(f"  ✓ Generated position curve: {len(curve)} data points")
                    print(f"    Time range: {curve.index.min()} to {curve.index.max()}")
                    print(f"    Max position value: ${curve['position_value'].max():,.2f}")
                    print(f"    Final PnL: ${curve['cumulative_pnl'].iloc[-1]:,.2f}")
                else:
                    print(f"  ✗ No position curve generated")
            else:
                print(f"  ✗ Backtest failed or no results")
                
        except Exception as e:
            print(f"  ✗ Error: {str(e)}")
            import traceback
            traceback.print_exc()
    
    # Generate plots
    if all_curves:
        print("\n" + "="*80)
        print("Generating Plots...")
        print("="*80)
        
        fig, axes = plt.subplots(3, 1, figsize=(16, 14))
        
        # Plot 1: Position Value
        ax1 = axes[0]
        for strategy_name, curve in all_curves.items():
            ax1.plot(curve.index, curve['position_value'].values, label=strategy_name, linewidth=2)
        ax1.set_xlabel('Time', fontsize=12, fontweight='bold')
        ax1.set_ylabel('Position Value ($)', fontsize=12, fontweight='bold')
        ax1.set_title('Position Value Over Time (BTC-USDT, 2025-01-01 to 2025-05-01)', fontsize=14, fontweight='bold')
        ax1.legend(fontsize=11)
        ax1.grid(True, alpha=0.3)
        ax1.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
        ax1.xaxis.set_major_locator(mdates.MonthLocator(interval=1))
        plt.setp(ax1.xaxis.get_majorticklabels(), rotation=45, ha='right')
        ax1.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'${x:,.0f}'))
        
        # Plot 2: Cumulative PnL
        ax2 = axes[1]
        for strategy_name, curve in all_curves.items():
            ax2.plot(curve.index, curve['cumulative_pnl'].values, label=strategy_name, linewidth=2)
        ax2.set_xlabel('Time', fontsize=12, fontweight='bold')
        ax2.set_ylabel('Cumulative PnL ($)', fontsize=12, fontweight='bold')
        ax2.set_title('Cumulative PnL Over Time (BTC-USDT, 2025-01-01 to 2025-05-01)', fontsize=14, fontweight='bold')
        ax2.legend(fontsize=11)
        ax2.grid(True, alpha=0.3)
        ax2.axhline(y=0, color='black', linestyle='-', linewidth=1, alpha=0.5)
        ax2.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
        ax2.xaxis.set_major_locator(mdates.MonthLocator(interval=1))
        plt.setp(ax2.xaxis.get_majorticklabels(), rotation=45, ha='right')
        ax2.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'${x:,.0f}'))
        
        # Plot 3: Long/Short Positions
        ax3 = axes[2]
        for strategy_name, curve in all_curves.items():
            ax3.plot(curve.index, curve['long_position'].values, label=f'{strategy_name} (Long)', linewidth=2, linestyle='-')
            ax3.plot(curve.index, curve['short_position'].values, label=f'{strategy_name} (Short)', linewidth=2, linestyle='--')
        ax3.set_xlabel('Time', fontsize=12, fontweight='bold')
        ax3.set_ylabel('Position Value ($)', fontsize=12, fontweight='bold')
        ax3.set_title('Long/Short Positions Over Time (BTC-USDT, 2025-01-01 to 2025-05-01)', fontsize=14, fontweight='bold')
        ax3.legend(fontsize=10, ncol=2)
        ax3.grid(True, alpha=0.3)
        ax3.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
        ax3.xaxis.set_major_locator(mdates.MonthLocator(interval=1))
        plt.setp(ax3.xaxis.get_majorticklabels(), rotation=45, ha='right')
        ax3.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'${x:,.0f}'))
        
        plt.tight_layout()
        output_dir = Path(__file__).parent
        plot_file = output_dir / f"btc_position_test_{START_DATE.strftime('%Y%m%d')}_{END_DATE.strftime('%Y%m%d')}.png"
        plt.savefig(plot_file, dpi=300, bbox_inches='tight')
        print(f"\n✓ Plot saved to: {plot_file}")
        plt.close()
        
        print("\n" + "="*80)
        print("Analysis Complete!")
        print("="*80)
        print("\nKey Observations:")
        for strategy_name, curve in all_curves.items():
            print(f"\n{strategy_name}:")
            print(f"  - Position changes: {sum(curve['position_value'].diff().abs() > 0.01)} times")
            print(f"  - Max position: ${curve['position_value'].max():,.2f}")
            print(f"  - Min position: ${curve['position_value'].min():,.2f}")
            print(f"  - Final PnL: ${curve['cumulative_pnl'].iloc[-1]:,.2f}")
            print(f"  - Data points: {len(curve)}")
            print(f"  - Time span: {(curve.index.max() - curve.index.min()).days} days")


if __name__ == "__main__":
    asyncio.run(test_btc_strategies())

