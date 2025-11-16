#!/usr/bin/env python3
"""
Comprehensive Backtest Comparison Script
Compare PMM Simple, PMM Dynamic (MACD), and PMM Bar Portion strategies
"""

import asyncio
import sys
import json
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Optional
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from collections import defaultdict

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

# Trading pairs
TRADING_PAIRS = ["BTC-USDT", "ETH-USDT", "SOL-USDT", "XRP-USDT", "PEPE-USDT", 
                 "ASTER-USDT", "MYX-USDT", "PUMP-USDT", "XPL-USDT", "OM-USDT", 
                 "TRX-USDT", "UMA-USDT"]

# Time range
START_DATE = datetime(2025, 3, 1)
END_DATE = datetime(2025, 11, 9)

# Backtest parameters
INITIAL_PORTFOLIO_USD = 10000
TRADING_FEE = 0.0004  # 0.04%
BACKTEST_RESOLUTION = "15m"  # 15 minutes
AGGREGATION_FREQUENCY = "15min"  # For plotting

# Strategy configurations
STRATEGY_CONFIGS = {
    "PMM_Simple": {
        "name": "PMM Simple",
        "config_class": PMMSimpleConfig,
        "params": {
            "buy_spreads": [0.005, 0.01, 0.02],  # 0.5%, 1%, 2%
            "sell_spreads": [0.005, 0.01, 0.02],
            "buy_amounts_pct": [Decimal("0.33"), Decimal("0.33"), Decimal("0.34")],
            "sell_amounts_pct": [Decimal("0.33"), Decimal("0.33"), Decimal("0.34")],
            "stop_loss": Decimal("0.01"),  # 1%
            "take_profit": Decimal("0.005"),  # 0.5%
            "time_limit": 3600,  # 1 hour
            "candles_config": [],  # PMM Simple doesn't use candles
        }
    },
    "PMM_Dynamic": {
        "name": "PMM Dynamic (MACD)",
        "config_class": PMMDynamicControllerConfig,
        "params": {
            "buy_spreads": [0.01, 0.02, 0.04],  # 1%, 2%, 4%
            "sell_spreads": [0.01, 0.02, 0.04],
            "buy_amounts_pct": [0.33, 0.33, 0.34],
            "sell_amounts_pct": [0.33, 0.33, 0.34],
            "stop_loss": Decimal("0.01"),  # 1%
            "take_profit": Decimal("0.005"),  # 0.5%
            "time_limit": 3600,  # 1 hour
        }
    },
    "PMM_Bar_Portion": {
        "name": "PMM Bar Portion",
        "config_class": PMMBarPortionControllerConfig,
        "params": {
            "buy_spreads": [0.01, 0.02],  # 1%, 2%
            "sell_spreads": [0.01, 0.02],
            "buy_amounts_pct": [0.5, 0.5],
            "sell_amounts_pct": [0.5, 0.5],
            "stop_loss": Decimal("0.01"),  # 1%
            "take_profit": Decimal("0.005"),  # 0.5%
            "time_limit": 3600,  # 1 hour
            "take_profit_order_type": OrderType.MARKET,
        }
    }
}


def create_strategy_config(strategy_key: str, trading_pair: str) -> Dict:
    """Create strategy configuration"""
    strategy_info = STRATEGY_CONFIGS[strategy_key]
    config_class = strategy_info["config_class"]
    params = strategy_info["params"].copy()
    
    # Common parameters
    common_params = {
        "controller_name": strategy_key.lower(),
        "connector_name": "binance_perpetual",
        "trading_pair": trading_pair,
        "total_amount_quote": Decimal(str(INITIAL_PORTFOLIO_USD)),
    }
    
    # Add candles parameters only for strategies that use candles
    if strategy_key != "PMM_Simple":
        common_params.update({
            "candles_connector": "binance_perpetual",
            "candles_trading_pair": trading_pair,
            "interval": BACKTEST_RESOLUTION,
        })
    
    # Convert amounts_pct to Decimal if they are not already
    if "buy_amounts_pct" in params:
        if params["buy_amounts_pct"] and not isinstance(params["buy_amounts_pct"][0], Decimal):
            params["buy_amounts_pct"] = [Decimal(str(x)) for x in params["buy_amounts_pct"]]
    if "sell_amounts_pct" in params:
        if params["sell_amounts_pct"] and not isinstance(params["sell_amounts_pct"][0], Decimal):
            params["sell_amounts_pct"] = [Decimal(str(x)) for x in params["sell_amounts_pct"]]
    
    # Merge parameters
    all_params = {**common_params, **params}
    
    return config_class(**all_params)


async def run_backtest(
    strategy_key: str,
    trading_pair: str,
    local_backtesting_provider: LocalBacktestingDataProvider,
    start_ts: int,
    end_ts: int
) -> Optional[Dict]:
    """Run backtest for a single strategy"""
    try:
        config = create_strategy_config(strategy_key, trading_pair)
        
        # Initialize candles feed (only for strategies that use candles)
        if hasattr(config, 'candles_connector') and hasattr(config, 'candles_trading_pair') and hasattr(config, 'interval'):
            candles_config = CandlesConfig(
                connector=config.candles_connector,
                trading_pair=config.candles_trading_pair,
                interval=config.interval,
                max_records=10000
            )
            await local_backtesting_provider.initialize_candles_feed([candles_config])
        else:
            # For PMM Simple, initialize with basic candles for backtesting
            candles_config = CandlesConfig(
                connector="binance_perpetual",
                trading_pair=trading_pair,
                interval=BACKTEST_RESOLUTION,
                max_records=10000
            )
            await local_backtesting_provider.initialize_candles_feed([candles_config])
        
        # Create backtesting engine
        engine = BacktestingEngineBase()
        engine.backtesting_data_provider = local_backtesting_provider
        
        # Run backtest
        result = await engine.run_backtesting(
            controller_config=config,
            start=start_ts,
            end=end_ts,
            backtesting_resolution=BACKTEST_RESOLUTION,
            trade_cost=Decimal(str(TRADING_FEE)),
            show_progress=True
        )
        
        if result and 'executors' in result:
            return result
        return None
        
    except Exception as e:
        print(f"  ✗ Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return None


def calculate_metrics(executors: List, strategy_name: str) -> Dict:
    """Calculate comprehensive metrics"""
    if not executors:
        return {
            "strategy": strategy_name,
            "total_executors": 0,
            "filled_executors": 0,
            "total_volume": 0.0,
            "total_pnl": 0.0,
            "total_pnl_pct": 0.0,
            "sharpe_ratio": 0.0,
            "max_drawdown": 0.0,
            "max_drawdown_pct": 0.0,
            "win_rate": 0.0,
            "total_trades": 0,
            "winning_trades": 0,
            "losing_trades": 0,
            "avg_trade_pnl": 0.0,
            "buy_fill_rate": 0.0,
            "sell_fill_rate": 0.0,
            "max_position_value": 0.0,
            "turnover_return": 0.0,
        }
    
    # Filter filled executors
    filled_executors = [
        e for e in executors 
        if hasattr(e, 'filled_amount_quote') and e.filled_amount_quote and float(e.filled_amount_quote) > 0
    ]
    
    if not filled_executors:
        return {
            "strategy": strategy_name,
            "total_executors": len(executors),
            "filled_executors": 0,
            "total_volume": 0.0,
            "total_pnl": 0.0,
            "total_pnl_pct": 0.0,
            "sharpe_ratio": 0.0,
            "max_drawdown": 0.0,
            "max_drawdown_pct": 0.0,
            "win_rate": 0.0,
            "total_trades": 0,
            "winning_trades": 0,
            "losing_trades": 0,
            "avg_trade_pnl": 0.0,
            "buy_fill_rate": 0.0,
            "sell_fill_rate": 0.0,
            "max_position_value": 0.0,
            "turnover_return": 0.0,
        }
    
    # Basic metrics
    total_executors = len(executors)
    filled_count = len(filled_executors)
    total_volume = sum(float(e.filled_amount_quote) for e in filled_executors)
    total_pnl = sum(float(e.net_pnl_quote) for e in filled_executors)
    total_pnl_pct = (total_pnl / INITIAL_PORTFOLIO_USD) * 100
    
    # Fill rates by side
    buy_executors = [e for e in executors if hasattr(e, 'side') and e.side == TradeType.BUY]
    sell_executors = [e for e in executors if hasattr(e, 'side') and e.side == TradeType.SELL]
    buy_filled = [e for e in buy_executors if hasattr(e, 'filled_amount_quote') and e.filled_amount_quote and float(e.filled_amount_quote) > 0]
    sell_filled = [e for e in sell_executors if hasattr(e, 'filled_amount_quote') and e.filled_amount_quote and float(e.filled_amount_quote) > 0]
    
    buy_fill_rate = (len(buy_filled) / len(buy_executors) * 100) if len(buy_executors) > 0 else 0.0
    sell_fill_rate = (len(sell_filled) / len(sell_executors) * 100) if len(sell_executors) > 0 else 0.0
    
    # Max position value
    max_position_value = max(
        [float(e.filled_amount_quote) for e in filled_executors] + [0.0]
    )
    
    # Turnover return (PnL / Total Volume)
    turnover_return = (total_pnl / total_volume * 100) if total_volume > 0 else 0.0
    
    # Sharpe ratio
    pnls = [float(e.net_pnl_quote) for e in filled_executors]
    if len(pnls) > 1 and np.std(pnls) > 0:
        sharpe_ratio = np.mean(pnls) / np.std(pnls) * np.sqrt(len(pnls))
    else:
        sharpe_ratio = 0.0
    
    # Max drawdown
    cumulative_pnl = np.cumsum(pnls)
    running_max = np.maximum.accumulate(cumulative_pnl)
    drawdown = cumulative_pnl - running_max
    max_drawdown = abs(np.min(drawdown)) if len(drawdown) > 0 else 0.0
    max_drawdown_pct = (max_drawdown / INITIAL_PORTFOLIO_USD) * 100
    
    # Win rate
    winning_trades = sum(1 for e in filled_executors if float(e.net_pnl_quote) > 0)
    losing_trades = sum(1 for e in filled_executors if float(e.net_pnl_quote) < 0)
    total_trades = len(filled_executors)
    win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0.0
    
    # Average trade PnL
    avg_trade_pnl = np.mean(pnls) if pnls else 0.0
    
    return {
        "strategy": strategy_name,
        "total_executors": total_executors,
        "filled_executors": filled_count,
        "total_volume": total_volume,
        "total_pnl": total_pnl,
        "total_pnl_pct": total_pnl_pct,
        "sharpe_ratio": sharpe_ratio,
        "max_drawdown": max_drawdown,
        "max_drawdown_pct": max_drawdown_pct,
        "win_rate": win_rate,
        "total_trades": total_trades,
        "winning_trades": winning_trades,
        "losing_trades": losing_trades,
        "avg_trade_pnl": avg_trade_pnl,
        "buy_fill_rate": buy_fill_rate,
        "sell_fill_rate": sell_fill_rate,
        "max_position_value": max_position_value,
        "turnover_return": turnover_return,
    }


def generate_equity_curve(executors: List, strategy_name: str, start_ts: int, end_ts: int) -> pd.DataFrame:
    """
    Generate corrected equity curve from executors
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
        
        # Get open time (timestamp from config)
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
            
            # Add close event (use same side as open)
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
                        current_long_position = max(0.0, current_long_position - event['position_value'])
                    elif event['side'] == TradeType.SELL:
                        current_short_position = max(0.0, current_short_position - event['position_value'])
                    else:
                        # If side is unknown, assume it's a long position
                        current_long_position = max(0.0, current_long_position - event['position_value'])
                    
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


async def run_comprehensive_backtest():
    """Run comprehensive backtest comparison"""
    print("="*80)
    print("Comprehensive Backtest Comparison")
    print("="*80)
    print()
    print(f"Trading Pairs: {', '.join(TRADING_PAIRS)}")
    print(f"Time Range: {START_DATE.strftime('%Y-%m-%d')} to {END_DATE.strftime('%Y-%m-%d')}")
    print(f"Strategies: {', '.join([s['name'] for s in STRATEGY_CONFIGS.values()])}")
    print(f"Backtest Resolution: {BACKTEST_RESOLUTION}")
    print(f"Initial Portfolio: ${INITIAL_PORTFOLIO_USD:,.2f}")
    print(f"Trading Fee: {TRADING_FEE*100:.2f}%")
    print()
    print("="*80)
    print()
    
    start_ts = int(START_DATE.timestamp())
    end_ts = int(END_DATE.timestamp())
    
    # Initialize data provider
    local_data_provider = LocalBinanceDataProvider()
    local_backtesting_provider = LocalBacktestingDataProvider(local_data_provider)
    local_backtesting_provider.update_backtesting_time(start_ts, end_ts)
    
    # Store results
    all_results = defaultdict(dict)
    all_equity_curves = defaultdict(dict)
    
    # Run backtests for each trading pair and strategy
    total_tasks = len(TRADING_PAIRS) * len(STRATEGY_CONFIGS)
    current_task = 0
    
    for trading_pair in TRADING_PAIRS:
        print(f"\n{'='*80}")
        print(f"Processing: {trading_pair}")
        print(f"{'='*80}")
        
        # Verify data availability
        test_df = local_data_provider.get_historical_candles(
            symbol=trading_pair,
            start_ts=start_ts,
            end_ts=end_ts,
            interval=BACKTEST_RESOLUTION
        )
        
        if len(test_df) == 0:
            print(f"  ⚠ No data available for {trading_pair}, skipping...")
            continue
        
        print(f"  ✓ Data available: {len(test_df):,} candles")
        
        for strategy_key in STRATEGY_CONFIGS.keys():
            current_task += 1
            strategy_name = STRATEGY_CONFIGS[strategy_key]["name"]
            print(f"\n  [{current_task}/{total_tasks}] Running {strategy_name} for {trading_pair}...")
            
            result = await run_backtest(
                strategy_key=strategy_key,
                trading_pair=trading_pair,
                local_backtesting_provider=local_backtesting_provider,
                start_ts=start_ts,
                end_ts=end_ts
            )
            
            if result and 'executors' in result:
                executors = result['executors']
                metrics = calculate_metrics(executors, strategy_name)
                all_results[trading_pair][strategy_key] = metrics
                
                # Generate equity curve
                equity_curve = generate_equity_curve(executors, strategy_name, start_ts, end_ts)
                if not equity_curve.empty:
                    all_equity_curves[trading_pair][strategy_key] = equity_curve
                
                print(f"    ✓ Completed: {metrics['filled_executors']} filled executors, PnL: ${metrics['total_pnl']:.2f}")
            else:
                print(f"    ✗ Failed or no results")
    
    # Generate comparison report
    print("\n" + "="*80)
    print("Generating Comparison Report...")
    print("="*80)
    
    generate_comparison_report(all_results, all_equity_curves)
    
    print("\n" + "="*80)
    print("Backtest Comparison Completed!")
    print("="*80)


def generate_comparison_report(all_results: Dict, all_equity_curves: Dict):
    """Generate comprehensive comparison report"""
    # Aggregate metrics across all trading pairs
    aggregated_metrics = defaultdict(lambda: {
        "total_pnl": 0.0,
        "total_volume": 0.0,
        "total_executors": 0,
        "filled_executors": 0,
        "winning_trades": 0,
        "losing_trades": 0,
        "max_position_value": 0.0,
        "buy_fill_rate_sum": 0.0,
        "sell_fill_rate_sum": 0.0,
        "pair_count": 0,
    })
    
    for trading_pair, strategies in all_results.items():
        for strategy_key, metrics in strategies.items():
            agg = aggregated_metrics[strategy_key]
            agg["total_pnl"] += metrics["total_pnl"]
            agg["total_volume"] += metrics["total_volume"]
            agg["total_executors"] += metrics["total_executors"]
            agg["filled_executors"] += metrics["filled_executors"]
            agg["winning_trades"] += metrics["winning_trades"]
            agg["losing_trades"] += metrics["losing_trades"]
            agg["max_position_value"] = max(agg["max_position_value"], metrics["max_position_value"])
            agg["buy_fill_rate_sum"] += metrics["buy_fill_rate"]
            agg["sell_fill_rate_sum"] += metrics["sell_fill_rate"]
            agg["pair_count"] += 1
    
    # Calculate aggregated metrics
    comparison_data = []
    for strategy_key, agg in aggregated_metrics.items():
        strategy_name = STRATEGY_CONFIGS[strategy_key]["name"]
        total_trades = agg["winning_trades"] + agg["losing_trades"]
        win_rate = (agg["winning_trades"] / total_trades * 100) if total_trades > 0 else 0.0
        buy_fill_rate = agg["buy_fill_rate_sum"] / agg["pair_count"] if agg["pair_count"] > 0 else 0.0
        sell_fill_rate = agg["sell_fill_rate_sum"] / agg["pair_count"] if agg["pair_count"] > 0 else 0.0
        turnover_return = (agg["total_pnl"] / agg["total_volume"] * 100) if agg["total_volume"] > 0 else 0.0
        total_pnl_pct = (agg["total_pnl"] / (INITIAL_PORTFOLIO_USD * len(TRADING_PAIRS))) * 100
        
        comparison_data.append({
            "Strategy": strategy_name,
            "Total PnL ($)": agg["total_pnl"],
            "Total PnL (%)": total_pnl_pct,
            "Total Volume ($)": agg["total_volume"],
            "Turnover Return (%)": turnover_return,
            "Total Executors": agg["total_executors"],
            "Filled Executors": agg["filled_executors"],
            "Fill Rate (%)": (agg["filled_executors"] / agg["total_executors"] * 100) if agg["total_executors"] > 0 else 0.0,
            "Buy Fill Rate (%)": buy_fill_rate,
            "Sell Fill Rate (%)": sell_fill_rate,
            "Max Position Value ($)": agg["max_position_value"],
            "Win Rate (%)": win_rate,
            "Winning Trades": agg["winning_trades"],
            "Losing Trades": agg["losing_trades"],
        })
    
    # Print comparison table
    print("\n" + "="*120)
    print("Strategy Comparison Summary")
    print("="*120)
    comparison_df = pd.DataFrame(comparison_data)
    print(comparison_df.to_string(index=False))
    print("="*120)
    
    # Print strategy parameters
    print("\n" + "="*120)
    print("Strategy Parameters")
    print("="*120)
    for strategy_key, strategy_info in STRATEGY_CONFIGS.items():
        print(f"\n{strategy_info['name']}:")
        params = strategy_info['params']
        for key, value in params.items():
            if isinstance(value, Decimal):
                print(f"  {key}: {float(value)*100:.2f}%" if key in ['stop_loss', 'take_profit'] else f"  {key}: {value}")
            elif isinstance(value, list) and len(value) > 0 and isinstance(value[0], Decimal):
                print(f"  {key}: {[float(v)*100 for v in value]}%")
            else:
                print(f"  {key}: {value}")
    
    # Save results to JSON
    output_dir = Path(__file__).parent
    results_file = output_dir / f"backtest_comparison_results_{START_DATE.strftime('%Y%m%d')}_{END_DATE.strftime('%Y%m%d')}.json"
    
    # Prepare JSON data
    json_data = {
        "time_range": {
            "start": START_DATE.strftime("%Y-%m-%d"),
            "end": END_DATE.strftime("%Y-%m-%d"),
        },
        "trading_pairs": TRADING_PAIRS,
        "strategies": {k: s["name"] for k, s in STRATEGY_CONFIGS.items()},
        "parameters": {
            "initial_portfolio": INITIAL_PORTFOLIO_USD,
            "trading_fee": TRADING_FEE,
            "backtest_resolution": BACKTEST_RESOLUTION,
        },
        "comparison": comparison_data,
        "detailed_results": {
            pair: {
                strategy: {
                    k: float(v) if isinstance(v, (np.integer, np.floating)) else v
                    for k, v in metrics.items()
                }
                for strategy, metrics in strategies.items()
            }
            for pair, strategies in all_results.items()
        }
    }
    
    with open(results_file, 'w') as f:
        json.dump(json_data, f, indent=2, default=str)
    
    print(f"\n✓ Results saved to: {results_file}")
    
    # Generate plots
    print("\nGenerating plots...")
    generate_plots(all_equity_curves, comparison_data)
    
    print("\n✓ All reports and plots generated!")


def generate_plots(all_equity_curves: Dict, comparison_data: List[Dict]):
    """Generate equity and position value plots"""
    output_dir = Path(__file__).parent
    
    # Aggregate equity curves across all trading pairs
    aggregated_equity = {}
    for strategy_key in STRATEGY_CONFIGS.keys():
        strategy_name = STRATEGY_CONFIGS[strategy_key]["name"]
        all_equity_series = []
        all_position_series = []
        all_pnl_series = []
        
        for trading_pair, strategies in all_equity_curves.items():
            if strategy_key in strategies:
                curve = strategies[strategy_key]
                if not curve.empty:
                    all_equity_series.append(curve['equity'])
                    all_position_series.append(curve['position_value'])
                    all_pnl_series.append(curve['cumulative_pnl'])
        
        if all_equity_series:
            # Align all series to the same index and sum
            # Find common time range
            all_indices = set()
            for series in all_equity_series:
                all_indices.update(series.index)
            common_index = pd.Index(sorted(all_indices))
            
            # Reindex and sum
            equity_sum = pd.Series(0.0, index=common_index)
            position_sum = pd.Series(0.0, index=common_index)
            pnl_sum = pd.Series(0.0, index=common_index)
            
            for series in all_equity_series:
                equity_sum = equity_sum.add(series.reindex(common_index, fill_value=0.0), fill_value=0.0)
            for series in all_position_series:
                position_sum = position_sum.add(series.reindex(common_index, fill_value=0.0), fill_value=0.0)
            for series in all_pnl_series:
                pnl_sum = pnl_sum.add(series.reindex(common_index, fill_value=0.0), fill_value=0.0)
            
            aggregated_equity[strategy_name] = {
                'equity': equity_sum,
                'position_value': position_sum,
                'cumulative_pnl': pnl_sum,
            }
    
    if not aggregated_equity:
        print("⚠ No equity curve data available for plotting")
        return
    
    # Plot 1: Equity curves for each strategy (aggregated)
    fig, axes = plt.subplots(2, 1, figsize=(16, 12))
    
    # Plot equity curves
    ax1 = axes[0]
    for strategy_name, data in aggregated_equity.items():
        if not data['equity'].empty:
            ax1.plot(data['equity'].index, data['equity'].values, label=strategy_name, linewidth=2.5)
    ax1.set_xlabel('Time', fontsize=12, fontweight='bold')
    ax1.set_ylabel('Equity ($)', fontsize=12, fontweight='bold')
    ax1.set_title('Equity Curves Comparison (Aggregated Across All Trading Pairs)', fontsize=14, fontweight='bold')
    ax1.legend(fontsize=11, loc='best')
    ax1.grid(True, alpha=0.3, linestyle='--')
    ax1.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
    ax1.xaxis.set_major_locator(mdates.MonthLocator(interval=1))
    plt.setp(ax1.xaxis.get_majorticklabels(), rotation=45, ha='right')
    ax1.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'${x:,.0f}'))
    
    # Plot position value curves
    ax2 = axes[1]
    for strategy_name, data in aggregated_equity.items():
        if not data['position_value'].empty:
            ax2.plot(data['position_value'].index, data['position_value'].values, label=strategy_name, linewidth=2.5)
    ax2.set_xlabel('Time', fontsize=12, fontweight='bold')
    ax2.set_ylabel('Position Value ($)', fontsize=12, fontweight='bold')
    ax2.set_title('Position Value Curves Comparison (Aggregated Across All Trading Pairs)', fontsize=14, fontweight='bold')
    ax2.legend(fontsize=11, loc='best')
    ax2.grid(True, alpha=0.3, linestyle='--')
    ax2.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
    ax2.xaxis.set_major_locator(mdates.MonthLocator(interval=1))
    plt.setp(ax2.xaxis.get_majorticklabels(), rotation=45, ha='right')
    ax2.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'${x:,.0f}'))
    
    plt.tight_layout()
    plot_file = output_dir / f"backtest_comparison_plots_{START_DATE.strftime('%Y%m%d')}_{END_DATE.strftime('%Y%m%d')}.png"
    plt.savefig(plot_file, dpi=300, bbox_inches='tight')
    print(f"✓ Plot saved to: {plot_file}")
    plt.close()
    
    # Plot 2: Cumulative PnL curves
    fig, ax = plt.subplots(1, 1, figsize=(16, 8))
    for strategy_name, data in aggregated_equity.items():
        if not data['cumulative_pnl'].empty:
            ax.plot(data['cumulative_pnl'].index, data['cumulative_pnl'].values, label=strategy_name, linewidth=2.5)
    ax.set_xlabel('Time', fontsize=12, fontweight='bold')
    ax.set_ylabel('Cumulative PnL ($)', fontsize=12, fontweight='bold')
    ax.set_title('Cumulative PnL Curves Comparison (Aggregated Across All Trading Pairs)', fontsize=14, fontweight='bold')
    ax.legend(fontsize=11, loc='best')
    ax.grid(True, alpha=0.3, linestyle='--')
    ax.axhline(y=0, color='black', linestyle='-', linewidth=1, alpha=0.5)
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=1))
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha='right')
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'${x:,.0f}'))
    plt.tight_layout()
    pnl_plot_file = output_dir / f"backtest_cumulative_pnl_{START_DATE.strftime('%Y%m%d')}_{END_DATE.strftime('%Y%m%d')}.png"
    plt.savefig(pnl_plot_file, dpi=300, bbox_inches='tight')
    print(f"✓ Cumulative PnL plot saved to: {pnl_plot_file}")
    plt.close()


if __name__ == "__main__":
    asyncio.run(run_comprehensive_backtest())

