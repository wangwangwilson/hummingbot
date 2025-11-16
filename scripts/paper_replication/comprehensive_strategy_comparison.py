#!/usr/bin/env python3
"""
Comprehensive Strategy Comparison
Compare PMM Simple, PMM Dynamic (MACD), and PMM Bar Portion strategies
across multiple trading pairs
"""

import asyncio
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path
import pandas as pd
import numpy as np
from collections import defaultdict
import json
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from typing import Dict, List

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
from controllers.market_making.pmm_simple import PMMSimpleConfig
from controllers.market_making.pmm_dynamic import PMMDynamicControllerConfig
from controllers.market_making.pmm_bar_portion import PMMBarPortionControllerConfig
from hummingbot.strategy_v2.executors.position_executor.data_types import OrderType
from hummingbot.core.data_type.common import TradeType

# Import local data manager
from backtest_comparison_local import LocalBinanceDataProvider, LocalBacktestingDataProvider

# Configuration
TRADING_PAIRS = [
    "BTC-USDT", "ETH-USDT", "SOL-USDT", "XRP-USDT",
    "PEPE-USDT", "ASTER-USDT", "MYX-USDT", "PUMP-USDT",
    "XPL-USDT", "OM-USDT", "TRX-USDT", "UMA-USDT"
]
START_DATE = datetime(2025, 3, 1)
END_DATE = datetime(2025, 11, 9)
INITIAL_PORTFOLIO_USD = 10000
TRADING_FEE = 0.0004
BACKTEST_RESOLUTION = "1m"  # Load 1-minute data
AGGREGATION_FREQUENCY = "15min"  # Aggregate to 15-minute for analysis

# Strategy configurations
STRATEGY_CONFIGS = {
    "PMM_Simple": {
        "name": "PMM Simple (Classic)",
        "buy_spreads": [0.005, 0.01],
        "sell_spreads": [0.005, 0.01],
        "stop_loss": 0.01,
        "take_profit": 0.005,
        "time_limit": 900,  # 15 minutes
    },
    "PMM_Dynamic": {
        "name": "PMM Dynamic (MACD)",
        "buy_spreads": [0.005, 0.01],
        "sell_spreads": [0.005, 0.01],
        "macd_fast": 12,
        "macd_slow": 26,
        "macd_signal": 9,
        "natr_length": 100,
    },
    "PMM_Bar_Portion": {
        "name": "PMM Bar Portion (BP)",
        "buy_spreads": [0.005, 0.01],
        "sell_spreads": [0.005, 0.01],
        "stop_loss": 0.01,
        "take_profit": 0.005,
        "time_limit": 900,  # 15 minutes
        "bar_portion_threshold": 0.5,
    }
}


def create_strategy_config(strategy_name: str, trading_pair: str):
    """Create strategy configuration"""
    config_params = STRATEGY_CONFIGS[strategy_name]
    
    if strategy_name == "PMM_Simple":
        return PMMSimpleConfig(
            controller_name="pmm_simple",
            connector_name="binance_perpetual",
            trading_pair=trading_pair,
            total_amount_quote=Decimal(str(INITIAL_PORTFOLIO_USD)),
            buy_spreads=config_params["buy_spreads"],
            sell_spreads=config_params["sell_spreads"],
            buy_amounts_pct=[Decimal("0.5"), Decimal("0.5")],
            sell_amounts_pct=[Decimal("0.5"), Decimal("0.5")],
            executor_refresh_time=300,
        )
    elif strategy_name == "PMM_Dynamic":
        return PMMDynamicControllerConfig(
            controller_name="pmm_dynamic",
            connector_name="binance_perpetual",
            trading_pair=trading_pair,
            total_amount_quote=Decimal(str(INITIAL_PORTFOLIO_USD)),
            buy_spreads=config_params["buy_spreads"],
            sell_spreads=config_params["sell_spreads"],
            buy_amounts_pct=[Decimal("0.5"), Decimal("0.5")],
            sell_amounts_pct=[Decimal("0.5"), Decimal("0.5")],
            candles_connector="binance_perpetual",
            candles_trading_pair=trading_pair,
            interval="15m",
            macd_fast=config_params["macd_fast"],
            macd_slow=config_params["macd_slow"],
            macd_signal=config_params["macd_signal"],
            natr_length=config_params["natr_length"],
        )
    elif strategy_name == "PMM_Bar_Portion":
        return PMMBarPortionControllerConfig(
            controller_name="pmm_bar_portion",
            connector_name="binance_perpetual",
            trading_pair=trading_pair,
            total_amount_quote=Decimal(str(INITIAL_PORTFOLIO_USD)),
            buy_spreads=config_params["buy_spreads"],
            sell_spreads=config_params["sell_spreads"],
            buy_amounts_pct=[Decimal("0.5"), Decimal("0.5")],
            sell_amounts_pct=[Decimal("0.5"), Decimal("0.5")],
            stop_loss=Decimal(str(config_params["stop_loss"])),
            take_profit=Decimal(str(config_params["take_profit"])),
            time_limit=config_params["time_limit"],
            take_profit_order_type=OrderType.MARKET,
            candles_connector="binance_perpetual",
            candles_trading_pair=trading_pair,
            interval="15m",
        )


async def run_backtest(
    strategy_name: str,
    trading_pair: str,
    local_backtesting_provider,
    start_ts: int,
    end_ts: int
):
    """Run backtest for a single strategy and trading pair"""
    print(f"\n{'='*80}")
    print(f"Running: {strategy_name} - {trading_pair}")
    print(f"{'='*80}")
    
    try:
        # Create config
        config = create_strategy_config(strategy_name, trading_pair)
        
        # Initialize candles feed for strategies that need it
        if strategy_name in ["PMM_Dynamic", "PMM_Bar_Portion"]:
            candles_config = CandlesConfig(
                connector=config.candles_connector,
                trading_pair=config.candles_trading_pair,
                interval=config.interval,
                max_records=100000
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
        
        if not result or 'executors' not in result:
            print(f"✗ Backtest failed for {strategy_name} - {trading_pair}")
            return None
        
        executors = result['executors']
        print(f"✓ Completed: {len(executors)} executors generated")
        
        return executors
        
    except Exception as e:
        print(f"✗ Error in {strategy_name} - {trading_pair}: {str(e)}")
        import traceback
        traceback.print_exc()
        return None


def calculate_metrics(executors: List, trading_pair: str, strategy_name: str) -> Dict:
    """Calculate comprehensive metrics"""
    if not executors:
        return {
            "trading_pair": trading_pair,
            "strategy": strategy_name,
            "total_executors": 0,
            "filled_executors": 0,
            "total_pnl": 0,
            "total_volume": 0,
        }
    
    # Filter filled executors
    filled_executors = [
        e for e in executors
        if hasattr(e, 'filled_amount_quote') and e.filled_amount_quote and float(e.filled_amount_quote) > 0
    ]
    
    # Basic stats
    total_executors = len(executors)
    filled_count = len(filled_executors)
    fill_rate = filled_count / total_executors if total_executors > 0 else 0
    
    # Order statistics
    buy_orders = [e for e in filled_executors if e.side == TradeType.BUY]
    sell_orders = [e for e in filled_executors if e.side == TradeType.SELL]
    
    buy_filled = len(buy_orders)
    sell_filled = len(sell_orders)
    
    # Calculate total buy/sell from all executors (not just filled)
    total_buy_orders = sum(1 for e in executors if hasattr(e, 'side') and e.side == TradeType.BUY)
    total_sell_orders = sum(1 for e in executors if hasattr(e, 'side') and e.side == TradeType.SELL)
    
    buy_fill_rate = buy_filled / total_buy_orders if total_buy_orders > 0 else 0
    sell_fill_rate = sell_filled / total_sell_orders if total_sell_orders > 0 else 0
    
    # PnL and volume
    total_pnl = sum(float(e.net_pnl_quote) if hasattr(e, 'net_pnl_quote') and e.net_pnl_quote else 0 
                   for e in filled_executors)
    total_volume = sum(float(e.filled_amount_quote) for e in filled_executors)
    
    # Max position value (peak portfolio value)
    cumulative_pnl = 0
    max_position_value = INITIAL_PORTFOLIO_USD
    for e in sorted(filled_executors, key=lambda x: x.config.timestamp):
        pnl = float(e.net_pnl_quote) if hasattr(e, 'net_pnl_quote') and e.net_pnl_quote else 0
        cumulative_pnl += pnl
        current_value = INITIAL_PORTFOLIO_USD + cumulative_pnl
        max_position_value = max(max_position_value, current_value)
    
    # Time range for daily calculations
    if filled_executors:
        timestamps = [e.config.timestamp for e in filled_executors]
        time_range_days = (max(timestamps) - min(timestamps)) / 86400
        daily_volume = total_volume / time_range_days if time_range_days > 0 else 0
        daily_pnl = total_pnl / time_range_days if time_range_days > 0 else 0
    else:
        daily_volume = 0
        daily_pnl = 0
    
    # Turnover return (PnL / Total Volume)
    turnover_return = (total_pnl / total_volume * 100) if total_volume > 0 else 0
    
    return {
        "trading_pair": trading_pair,
        "strategy": strategy_name,
        "total_executors": total_executors,
        "filled_executors": filled_count,
        "fill_rate": fill_rate * 100,
        "buy_orders_total": total_buy_orders,
        "sell_orders_total": total_sell_orders,
        "buy_orders_filled": buy_filled,
        "sell_orders_filled": sell_filled,
        "buy_fill_rate": buy_fill_rate * 100,
        "sell_fill_rate": sell_fill_rate * 100,
        "total_pnl": total_pnl,
        "total_volume": total_volume,
        "max_position_value": max_position_value,
        "daily_volume": daily_volume,
        "daily_pnl": daily_pnl,
        "turnover_return": turnover_return,
        "return_pct": (total_pnl / INITIAL_PORTFOLIO_USD * 100),
    }


def generate_equity_curve(executors: List, trading_pair: str, strategy_name: str) -> pd.DataFrame:
    """Generate equity curve with 15-minute frequency"""
    if not executors:
        return pd.DataFrame()
    
    # Filter filled executors
    filled_executors = [
        e for e in executors
        if hasattr(e, 'filled_amount_quote') and e.filled_amount_quote and float(e.filled_amount_quote) > 0
    ]
    
    if not filled_executors:
        return pd.DataFrame()
    
    # Sort by timestamp
    sorted_executors = sorted(filled_executors, key=lambda e: e.config.timestamp)
    
    # Create time range
    start_ts = sorted_executors[0].config.timestamp
    end_ts = sorted_executors[-1].config.timestamp
    
    # Generate 15-minute intervals
    time_range = pd.date_range(
        start=datetime.fromtimestamp(start_ts),
        end=datetime.fromtimestamp(end_ts),
        freq=AGGREGATION_FREQUENCY
    )
    
    # Initialize equity curve
    equity_curve = pd.DataFrame(index=time_range)
    equity_curve['timestamp'] = equity_curve.index.astype('int64') // 10**9
    equity_curve['cumulative_pnl'] = 0.0
    equity_curve['position_value'] = float(INITIAL_PORTFOLIO_USD)
    equity_curve['equity'] = float(INITIAL_PORTFOLIO_USD)
    
    # Track positions
    cumulative_pnl = 0.0
    
    for executor in sorted_executors:
        exec_ts = executor.config.timestamp
        exec_dt = datetime.fromtimestamp(exec_ts)
        
        # Find nearest 15-minute timestamp
        nearest_idx = equity_curve.index.searchsorted(exec_dt)
        if nearest_idx >= len(equity_curve):
            nearest_idx = len(equity_curve) - 1
        
        # Update cumulative PnL
        pnl = float(executor.net_pnl_quote) if hasattr(executor, 'net_pnl_quote') and executor.net_pnl_quote else 0
        cumulative_pnl += pnl
        
        # Update from this point forward
        equity_curve.loc[equity_curve.index[nearest_idx]:, 'cumulative_pnl'] = cumulative_pnl
        equity_curve.loc[equity_curve.index[nearest_idx]:, 'equity'] = INITIAL_PORTFOLIO_USD + cumulative_pnl
    
    return equity_curve


def generate_plots(results: Dict, output_dir: Path):
    """Generate comparison plots with English annotations"""
    print(f"\n{'='*80}")
    print("Generating Comparison Plots...")
    print(f"{'='*80}")
    
    # Extract all trading pairs
    trading_pairs = sorted(set(m['trading_pair'] for m in results['metrics']))
    strategies = sorted(set(m['strategy'] for m in results['metrics']))
    
    for trading_pair in trading_pairs:
        print(f"\nGenerating plots for {trading_pair}...")
        
        # Filter metrics for this trading pair
        pair_metrics = [m for m in results['metrics'] if m['trading_pair'] == trading_pair]
        
        if not pair_metrics:
            continue
        
        # Create figure with subplots
        fig = plt.figure(figsize=(20, 12))
        gs = fig.add_gridspec(3, 3, hspace=0.3, wspace=0.3)
        
        fig.suptitle(
            f'{trading_pair} Strategy Comparison\n'
            f'Period: {START_DATE.strftime("%Y-%m-%d")} to {END_DATE.strftime("%Y-%m-%d")}',
            fontsize=16, fontweight='bold'
        )
        
        # 1. Cumulative PnL
        ax1 = fig.add_subplot(gs[0, :])
        for strategy in strategies:
            strategy_name = STRATEGY_CONFIGS[strategy]["name"]
            equity_data = results['equity_curves'].get(f"{trading_pair}_{strategy}")
            if equity_data is not None and not equity_data.empty:
                ax1.plot(equity_data.index, equity_data['cumulative_pnl'],
                        label=strategy_name, linewidth=2)
        ax1.set_title('Cumulative PnL ($)', fontweight='bold', fontsize=12)
        ax1.set_xlabel('Date')
        ax1.set_ylabel('PnL ($)')
        ax1.legend()
        ax1.grid(True, alpha=0.3)
        ax1.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
        ax1.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))
        
        # 2. Equity Curve
        ax2 = fig.add_subplot(gs[1, :])
        for strategy in strategies:
            strategy_name = STRATEGY_CONFIGS[strategy]["name"]
            equity_data = results['equity_curves'].get(f"{trading_pair}_{strategy}")
            if equity_data is not None and not equity_data.empty:
                ax2.plot(equity_data.index, equity_data['equity'],
                        label=strategy_name, linewidth=2)
        ax2.set_title('Portfolio Value ($)', fontweight='bold', fontsize=12)
        ax2.set_xlabel('Date')
        ax2.set_ylabel('Value ($)')
        ax2.legend()
        ax2.grid(True, alpha=0.3)
        ax2.axhline(y=INITIAL_PORTFOLIO_USD, color='black', linestyle='--', linewidth=1, alpha=0.5)
        ax2.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))
        
        # 3. Fill Rate Comparison
        ax3 = fig.add_subplot(gs[2, 0])
        x = np.arange(len(strategies))
        buy_rates = [next((m['buy_fill_rate'] for m in pair_metrics if m['strategy'] == s), 0) 
                    for s in strategies]
        sell_rates = [next((m['sell_fill_rate'] for m in pair_metrics if m['strategy'] == s), 0)
                     for s in strategies]
        width = 0.35
        ax3.bar(x - width/2, buy_rates, width, label='Buy Fill Rate', alpha=0.8)
        ax3.bar(x + width/2, sell_rates, width, label='Sell Fill Rate', alpha=0.8)
        ax3.set_xlabel('Strategy')
        ax3.set_ylabel('Fill Rate (%)')
        ax3.set_title('Order Fill Rates', fontweight='bold')
        ax3.set_xticks(x)
        ax3.set_xticklabels([STRATEGY_CONFIGS[s]["name"].split()[0] for s in strategies])
        ax3.legend()
        ax3.grid(True, alpha=0.3, axis='y')
        
        # 4. Total PnL Comparison
        ax4 = fig.add_subplot(gs[2, 1])
        pnls = [next((m['total_pnl'] for m in pair_metrics if m['strategy'] == s), 0) 
               for s in strategies]
        colors = ['green' if p > 0 else 'red' for p in pnls]
        ax4.bar(range(len(strategies)), pnls, color=colors, alpha=0.8)
        ax4.set_xlabel('Strategy')
        ax4.set_ylabel('Total PnL ($)')
        ax4.set_title('Total PnL Comparison', fontweight='bold')
        ax4.set_xticks(range(len(strategies)))
        ax4.set_xticklabels([STRATEGY_CONFIGS[s]["name"].split()[0] for s in strategies])
        ax4.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
        ax4.grid(True, alpha=0.3, axis='y')
        
        # 5. Turnover Return Comparison
        ax5 = fig.add_subplot(gs[2, 2])
        turnover_returns = [next((m['turnover_return'] for m in pair_metrics if m['strategy'] == s), 0)
                           for s in strategies]
        colors = ['green' if t > 0 else 'red' for t in turnover_returns]
        ax5.bar(range(len(strategies)), turnover_returns, color=colors, alpha=0.8)
        ax5.set_xlabel('Strategy')
        ax5.set_ylabel('Turnover Return (%)')
        ax5.set_title('Turnover Return (PnL/Volume)', fontweight='bold')
        ax5.set_xticks(range(len(strategies)))
        ax5.set_xticklabels([STRATEGY_CONFIGS[s]["name"].split()[0] for s in strategies])
        ax5.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
        ax5.grid(True, alpha=0.3, axis='y')
        
        # Save figure
        filename = f"strategy_comparison_{trading_pair.replace('-', '_')}_{START_DATE.strftime('%Y%m%d')}_{END_DATE.strftime('%Y%m%d')}.png"
        filepath = output_dir / filename
        plt.savefig(filepath, dpi=150, bbox_inches='tight')
        plt.close()
        print(f"✓ Saved: {filename}")


def generate_comparison_report(results: Dict, output_dir: Path):
    """Generate comparison report"""
    print(f"\n{'='*80}")
    print("COMPREHENSIVE STRATEGY COMPARISON REPORT")
    print(f"{'='*80}")
    print(f"Period: {START_DATE.strftime('%Y-%m-%d')} to {END_DATE.strftime('%Y-%m-%d')}")
    print(f"Trading Pairs: {', '.join(TRADING_PAIRS)}")
    print(f"Initial Portfolio: ${INITIAL_PORTFOLIO_USD:,.2f}")
    print()
    
    # Group by trading pair
    trading_pairs = sorted(set(m['trading_pair'] for m in results['metrics']))
    
    for trading_pair in trading_pairs:
        print(f"\n{'='*80}")
        print(f"{trading_pair}")
        print(f"{'='*80}")
        
        pair_metrics = [m for m in results['metrics'] if m['trading_pair'] == trading_pair]
        
        if not pair_metrics:
            print("No data available")
            continue
        
        # Print metrics table
        print(f"\n{'Strategy':<25} {'Total PnL':<12} {'Return %':<10} {'Fill Rate':<10} {'Turnover Ret%':<15}")
        print("-" * 80)
        for m in pair_metrics:
            strategy_name = STRATEGY_CONFIGS[m['strategy']]["name"]
            print(f"{strategy_name:<25} ${m['total_pnl']:<11,.2f} {m['return_pct']:<9.2f}% {m['fill_rate']:<9.1f}% {m['turnover_return']:<14.3f}%")
        
        # Detailed metrics
        print(f"\n{'Detailed Metrics'}")
        print("-" * 80)
        print(f"{'Strategy':<25} {'Buy Fill%':<12} {'Sell Fill%':<12} {'Max Pos Val':<15} {'Daily Vol':<15}")
        print("-" * 80)
        for m in pair_metrics:
            strategy_name = STRATEGY_CONFIGS[m['strategy']]["name"]
            print(f"{strategy_name:<25} {m['buy_fill_rate']:<11.1f}% {m['sell_fill_rate']:<11.1f}% "
                  f"${m['max_position_value']:<14,.2f} ${m['daily_volume']:<14,.2f}")
        
        # Order statistics
        print(f"\n{'Order Statistics'}")
        print("-" * 80)
        print(f"{'Strategy':<25} {'Total Orders':<15} {'Buy Orders':<12} {'Sell Orders':<12} {'Filled Orders':<15}")
        print("-" * 80)
        for m in pair_metrics:
            strategy_name = STRATEGY_CONFIGS[m['strategy']]["name"]
            print(f"{strategy_name:<25} {m['total_executors']:<15} {m['buy_orders_total']:<12} "
                  f"{m['sell_orders_total']:<12} {m['filled_executors']:<15}")
    
    # Save to JSON
    output_file = output_dir / f"comparison_results_{START_DATE.strftime('%Y%m%d')}_{END_DATE.strftime('%Y%m%d')}.json"
    with open(output_file, 'w') as f:
        # Convert equity curves to serializable format
        serializable_results = {
            'metrics': results['metrics'],
            'period': {
                'start': START_DATE.strftime('%Y-%m-%d'),
                'end': END_DATE.strftime('%Y-%m-%d')
            },
            'trading_pairs': TRADING_PAIRS,
            'strategy_configs': STRATEGY_CONFIGS
        }
        json.dump(serializable_results, f, indent=2)
    print(f"\n✓ Results saved to: {output_file}")


async def main():
    """Main execution function"""
    print(f"{'='*80}")
    print("COMPREHENSIVE STRATEGY COMPARISON")
    print(f"{'='*80}")
    print(f"Period: {START_DATE.strftime('%Y-%m-%d')} to {END_DATE.strftime('%Y-%m-%d')}")
    print(f"Trading Pairs: {len(TRADING_PAIRS)}")
    print(f"Strategies: {len(STRATEGY_CONFIGS)}")
    print(f"Total Backtests: {len(TRADING_PAIRS) * len(STRATEGY_CONFIGS)}")
    print()
    
    # Initialize data provider
    local_data_provider = LocalBinanceDataProvider()
    
    start_ts = int(START_DATE.timestamp())
    end_ts = int(END_DATE.timestamp())
    
    # Collect results
    results = {
        'metrics': [],
        'equity_curves': {}
    }
    
    # Run backtests
    for trading_pair in TRADING_PAIRS:
        print(f"\n{'='*80}")
        print(f"Processing: {trading_pair}")
        print(f"{'='*80}")
        
        # Create data provider for this pair
        local_backtesting_provider = LocalBacktestingDataProvider(local_data_provider)
        local_backtesting_provider.update_backtesting_time(start_ts, end_ts)
        
        for strategy_name in STRATEGY_CONFIGS.keys():
            # Run backtest
            executors = await run_backtest(
                strategy_name,
                trading_pair,
                local_backtesting_provider,
                start_ts,
                end_ts
            )
            
            if executors:
                # Calculate metrics
                metrics = calculate_metrics(executors, trading_pair, strategy_name)
                results['metrics'].append(metrics)
                
                # Generate equity curve
                equity_curve = generate_equity_curve(executors, trading_pair, strategy_name)
                if not equity_curve.empty:
                    results['equity_curves'][f"{trading_pair}_{strategy_name}"] = equity_curve
    
    # Generate output directory
    output_dir = Path(__file__).parent
    
    # Generate plots
    generate_plots(results, output_dir)
    
    # Generate report
    generate_comparison_report(results, output_dir)
    
    print(f"\n{'='*80}")
    print("BACKTEST COMPLETED")
    print(f"{'='*80}")


if __name__ == "__main__":
    asyncio.run(main())

