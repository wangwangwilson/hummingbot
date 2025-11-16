#!/usr/bin/env python3
"""
回测脚本 - 使用1分钟数据
生成仓位曲线和PnL曲线，验证做市策略的多空交替仓位
"""

import asyncio
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from typing import Dict, List, Optional, Tuple
import psutil
import os
import time
import multiprocessing
from joblib import Parallel, delayed
import io
import contextlib

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
TRADING_PAIRS = ["PUMP-USDT"]  # 支持多个品种
START_DATE = datetime(2025, 11, 4)  # 测试5天数据
END_DATE = datetime(2025, 11, 9)
INITIAL_PORTFOLIO_USD = 10000
TRADING_FEE = 0.0004
BACKTEST_RESOLUTION = "1m"  # 基础数据：1分钟
# 可选重采样间隔：None表示使用原始1分钟数据，或选择 "5m", "15m", "30m", "1h"
RESAMPLE_INTERVAL: Optional[str] = "15m"  # 设置为 "15m" 可大幅加速回测（约15倍速度提升）
USE_MULTIPROCESSING = True  # 使用joblib多进程并行
N_JOBS = -1  # -1表示使用所有CPU核心，或指定数量如4


def generate_equity_curve(executors: List, start_ts: int, end_ts: int, 
                          initial_portfolio: float, resolution: str = "1m") -> pd.DataFrame:
    """
    生成权益曲线、仓位曲线和PnL曲线
    
    Args:
        executors: ExecutorInfo列表
        start_ts: 开始时间戳（秒）
        end_ts: 结束时间戳（秒）
        initial_portfolio: 初始资金
        resolution: 时间分辨率（用于生成时间序列）
    
    Returns:
        DataFrame with columns: timestamp, long_position, short_position, 
                               position_value, cumulative_pnl, equity
    """
    # 只处理已成交的executors
    filled_executors = [
        e for e in executors 
        if hasattr(e, 'filled_amount_quote') and e.filled_amount_quote and float(e.filled_amount_quote) > 0
    ]
    
    if len(filled_executors) == 0:
        print("  ⚠ No filled executors, returning empty curve")
        return pd.DataFrame()
    
    # 收集所有事件（开仓和平仓）
    events = []
    for executor in filled_executors:
        # 获取side信息
        side = None
        if hasattr(executor, 'side'):
            side = executor.side
        elif hasattr(executor, 'config') and hasattr(executor.config, 'side'):
            side = executor.config.side
        elif hasattr(executor, 'custom_info') and 'side' in executor.custom_info:
            side = executor.custom_info['side']
        
        if side is None:
            continue
        
        # 获取时间戳
        open_ts = None
        close_ts = None
        
        if hasattr(executor, 'config') and hasattr(executor.config, 'timestamp'):
            open_ts = executor.config.timestamp
        if hasattr(executor, 'close_timestamp'):
            close_ts = executor.close_timestamp
        elif hasattr(executor, 'config') and hasattr(executor.config, 'close_timestamp'):
            close_ts = executor.config.close_timestamp
        
        if open_ts is None:
            continue
        
        # 获取价格和数量
        entry_price = None
        close_price = None
        amount = None
        
        if hasattr(executor, 'entry_price'):
            entry_price = float(executor.entry_price)
        elif hasattr(executor, 'config') and hasattr(executor.config, 'entry_price'):
            entry_price = float(executor.config.entry_price)
        
        if hasattr(executor, 'close_price'):
            close_price = float(executor.close_price)
        elif hasattr(executor, 'net_pnl_quote') and hasattr(executor, 'filled_amount_quote'):
            # 从PnL反推close_price
            if entry_price and executor.filled_amount_quote:
                filled_amount = float(executor.filled_amount_quote)
                net_pnl = float(executor.net_pnl_quote) if executor.net_pnl_quote else 0.0
                # PnL = (close_price - entry_price) / entry_price * filled_amount * side_multiplier
                # side_multiplier: BUY=1, SELL=-1
                side_multiplier = 1.0 if side == TradeType.BUY else -1.0
                if filled_amount > 0:
                    pnl_pct = net_pnl / filled_amount
                    close_price = entry_price * (1 + pnl_pct / side_multiplier)
        
        if hasattr(executor, 'filled_amount_quote') and executor.filled_amount_quote:
            # filled_amount_quote 已经是USD金额，不需要再乘以价格
            position_value = float(executor.filled_amount_quote)
        else:
            continue
        
        if entry_price is None:
            continue
        
        # 开仓事件
        events.append({
            'timestamp': open_ts,
            'type': 'open',
            'side': side,
            'price': entry_price,
            'position_value': position_value,
        })
        
        # 平仓事件
        if close_ts and close_ts > open_ts:
            # 使用executor的net_pnl_quote作为PnL
            pnl = 0.0
            if hasattr(executor, 'net_pnl_quote') and executor.net_pnl_quote:
                pnl = float(executor.net_pnl_quote)
            elif close_price and entry_price:
                # 如果没有net_pnl_quote，则计算
                side_multiplier = 1.0 if side == TradeType.BUY else -1.0
                price_change = (close_price - entry_price) / entry_price
                pnl = price_change * side_multiplier * position_value
            
            events.append({
                'timestamp': close_ts,
                'type': 'close',
                'side': side,
                'price': close_price or entry_price,
                'position_value': position_value,
                'pnl': pnl,
            })
    
    if len(events) == 0:
        print("  ⚠ No events collected, returning empty curve")
        return pd.DataFrame()
    
    # 按时间排序
    events.sort(key=lambda x: x['timestamp'])
    
    # 生成时间序列（1分钟频率）
    resolution_seconds = 60  # 1分钟
    timestamps = list(range(start_ts, end_ts + 1, resolution_seconds))
    
    equity_curve = pd.DataFrame({
        'timestamp': timestamps
    })
    equity_curve.set_index('timestamp', inplace=True)
    
    # 初始化列
    equity_curve['long_position'] = 0.0
    equity_curve['short_position'] = 0.0
    equity_curve['position_value'] = 0.0
    equity_curve['cumulative_pnl'] = 0.0
    equity_curve['equity'] = float(initial_portfolio)
    
    # 处理事件以构建仓位和PnL曲线
    current_long_position = 0.0
    current_short_position = 0.0
    cumulative_pnl = 0.0
    event_idx = 0
    
    for idx in equity_curve.index:
        # 处理所有发生在此时间戳之前或等于此时间戳的事件
        while event_idx < len(events):
            event = events[event_idx]
            if event['timestamp'] <= idx:
                if event['type'] == 'open':
                    # 开仓：添加到当前仓位
                    if event['side'] == TradeType.BUY:
                        current_long_position += event['position_value']
                    elif event['side'] == TradeType.SELL:
                        current_short_position += event['position_value']
                elif event['type'] == 'close':
                    # 平仓：从当前仓位移除并添加PnL
                    if event['side'] == TradeType.BUY:
                        current_long_position -= event['position_value']
                    elif event['side'] == TradeType.SELL:
                        current_short_position -= event['position_value']
                    
                    cumulative_pnl += event.get('pnl', 0.0)
                
                event_idx += 1
            else:
                break
        
        # 更新此时间戳的权益曲线
        total_position = current_long_position - current_short_position  # 净仓位
        equity_curve.loc[idx, 'long_position'] = float(current_long_position)
        equity_curve.loc[idx, 'short_position'] = float(current_short_position)
        equity_curve.loc[idx, 'position_value'] = float(abs(total_position))  # 绝对值用于显示
        equity_curve.loc[idx, 'cumulative_pnl'] = float(cumulative_pnl)
        equity_curve.loc[idx, 'equity'] = float(initial_portfolio + cumulative_pnl)
    
    return equity_curve


def generate_order_curves(executors: List, start_ts: int, end_ts: int) -> pd.DataFrame:
    """生成挂单曲线（订单价格曲线）"""
    all_executors = executors  # 包括未成交的
    
    if len(all_executors) == 0:
        return pd.DataFrame()
    
    # 收集所有订单（包括未成交的）
    orders = []
    for executor in all_executors:
        side = None
        if hasattr(executor, 'side'):
            side = executor.side
        elif hasattr(executor, 'config') and hasattr(executor.config, 'side'):
            side = executor.config.side
        
        if side is None:
            continue
        
        # 获取时间戳和价格
        timestamp = None
        price = None
        
        if hasattr(executor, 'config') and hasattr(executor.config, 'timestamp'):
            timestamp = executor.config.timestamp
        
        if hasattr(executor, 'entry_price'):
            price = float(executor.entry_price)
        elif hasattr(executor, 'config') and hasattr(executor.config, 'entry_price'):
            price = float(executor.config.entry_price)
        
        if timestamp and price:
            orders.append({
                'timestamp': timestamp,
                'side': side,
                'price': price,
                'filled': hasattr(executor, 'filled_amount_quote') and executor.filled_amount_quote and float(executor.filled_amount_quote) > 0
            })
    
    if len(orders) == 0:
        return pd.DataFrame()
    
    # 转换为DataFrame
    orders_df = pd.DataFrame(orders)
    orders_df = orders_df.sort_values('timestamp')
    
    return orders_df


def generate_plots(equity_curves: Dict[str, pd.DataFrame], order_curves: Dict[str, pd.DataFrame], 
                   output_path: str):
    """生成仓位、PnL和挂单图表"""
    fig, axes = plt.subplots(4, 1, figsize=(16, 16))
    fig.suptitle(f'Backtest Results: {TRADING_PAIR} ({START_DATE.strftime("%Y-%m-%d")} to {END_DATE.strftime("%Y-%m-%d")})', 
                 fontsize=16, fontweight='bold')
    
    colors = {
        'PMM_Simple': '#1f77b4',
        'PMM_Dynamic': '#ff7f0e',
        'PMM_Bar_Portion': '#2ca02c'
    }
    
    for strategy_name, curve in equity_curves.items():
        if curve.empty:
            continue
        
        # 转换为datetime索引用于绘图
        curve_dt = curve.copy()
        curve_dt.index = pd.to_datetime(curve_dt.index, unit='s')
        
        color = colors.get(strategy_name, '#1f77b4')
        label = strategy_name.replace('_', ' ')
        
        # Plot 1: Position Value
        ax1 = axes[0]
        ax1.plot(curve_dt.index, curve_dt['position_value'], label=label, color=color, linewidth=1.5, alpha=0.8)
        ax1.set_ylabel('Position Value (USD)', fontsize=12)
        ax1.set_title('Position Value Over Time', fontsize=14, fontweight='bold')
        ax1.legend(loc='upper left')
        ax1.grid(True, alpha=0.3)
        ax1.xaxis.set_major_locator(mdates.MonthLocator(interval=1))
        ax1.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
        ax1.xaxis.set_minor_locator(mdates.WeekdayLocator())
        
        # Plot 2: Long/Short Positions
        ax2 = axes[1]
        ax2.plot(curve_dt.index, curve_dt['long_position'], label=f'{label} - Long', 
                color=color, linewidth=1.5, alpha=0.8, linestyle='-')
        ax2.plot(curve_dt.index, curve_dt['short_position'], label=f'{label} - Short', 
                color=color, linewidth=1.5, alpha=0.8, linestyle='--')
        ax2.set_ylabel('Position Value (USD)', fontsize=12)
        ax2.set_title('Long/Short Positions Over Time', fontsize=14, fontweight='bold')
        ax2.legend(loc='upper left')
        ax2.grid(True, alpha=0.3)
        ax2.xaxis.set_major_locator(mdates.MonthLocator(interval=1))
        ax2.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
        ax2.xaxis.set_minor_locator(mdates.WeekdayLocator())
        
        # Plot 3: Cumulative PnL
        ax3 = axes[2]
        ax3.plot(curve_dt.index, curve_dt['cumulative_pnl'], label=label, color=color, linewidth=1.5, alpha=0.8)
        ax3.axhline(y=0, color='black', linestyle='--', linewidth=1, alpha=0.5)
        ax3.set_ylabel('Cumulative PnL (USD)', fontsize=12)
        ax3.set_xlabel('Time', fontsize=12)
        ax3.set_title('Cumulative PnL Over Time', fontsize=14, fontweight='bold')
        ax3.legend(loc='upper left')
        ax3.grid(True, alpha=0.3)
        ax3.xaxis.set_major_locator(mdates.MonthLocator(interval=1))
        ax3.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
        ax3.xaxis.set_minor_locator(mdates.WeekdayLocator())
        
        # Plot 4: Order Prices (Buy/Sell Orders)
        if strategy_name in order_curves and not order_curves[strategy_name].empty:
            ax4 = axes[3]
            orders_df = order_curves[strategy_name]
            orders_df['datetime'] = pd.to_datetime(orders_df['timestamp'], unit='s')
            
            buy_orders = orders_df[orders_df['side'] == TradeType.BUY]
            sell_orders = orders_df[orders_df['side'] == TradeType.SELL]
            
            if len(buy_orders) > 0:
                ax4.scatter(buy_orders['datetime'], buy_orders['price'], 
                           label=f'{label} - Buy Orders', color='green', alpha=0.6, s=10, marker='^')
            if len(sell_orders) > 0:
                ax4.scatter(sell_orders['datetime'], sell_orders['price'], 
                           label=f'{label} - Sell Orders', color='red', alpha=0.6, s=10, marker='v')
            
            ax4.set_ylabel('Order Price (USD)', fontsize=12)
            ax4.set_xlabel('Time', fontsize=12)
            ax4.set_title('Order Prices Over Time', fontsize=14, fontweight='bold')
            ax4.legend(loc='upper left')
            ax4.grid(True, alpha=0.3)
            ax4.xaxis.set_major_locator(mdates.MonthLocator(interval=1))
            ax4.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
            ax4.xaxis.set_minor_locator(mdates.WeekdayLocator())
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"  ✓ Plot saved to: {output_path}")
    plt.close()


def monitor_cpu_usage():
    """监控CPU使用率"""
    try:
        process = psutil.Process(os.getpid())
        # 使用interval=None来获取非阻塞的CPU使用率
        cpu = process.cpu_percent(interval=None)
        return cpu if cpu > 0 else process.cpu_percent(interval=0.1)
    except:
        return 0.0


async def check_data_continuity(data_provider, trading_pair: str, start_ts: int, end_ts: int):
    """检查数据连续性"""
    print("  Checking data continuity...")
    
    # 获取数据
    df = data_provider.get_candles_df(
        connector_name="binance_perpetual",
        trading_pair=trading_pair,
        interval="1m",
        max_records=None
    )
    
    if df.empty:
        print("  ⚠ No data available")
        return False
    
    # 检查时间戳连续性
    if 'timestamp' not in df.columns:
        if df.index.name == 'timestamp':
            df = df.reset_index()
        else:
            print("  ⚠ Cannot find timestamp column")
            return False
    
    df = df.sort_values('timestamp')
    df = df[(df['timestamp'] >= start_ts) & (df['timestamp'] <= end_ts)]
    
    if len(df) == 0:
        print("  ⚠ No data in specified time range")
        return False
    
    # 检查时间间隔
    time_diffs = df['timestamp'].diff().dropna()
    expected_interval = 60  # 1分钟 = 60秒
    
    # 允许5秒的误差
    gaps = time_diffs[(time_diffs > expected_interval + 5) | (time_diffs < expected_interval - 5)]
    
    if len(gaps) > 0:
        print(f"  ⚠ Found {len(gaps)} time gaps:")
        print(f"    Min gap: {gaps.min()}s, Max gap: {gaps.max()}s")
        print(f"    First gap at: {datetime.fromtimestamp(df.iloc[gaps.index[0]]['timestamp'])}")
        return False
    else:
        print(f"  ✓ Data is continuous: {len(df):,} data points")
        print(f"    Time range: {datetime.fromtimestamp(df['timestamp'].min())} to {datetime.fromtimestamp(df['timestamp'].max())}")
        return True


async def run_single_strategy_backtest(strategy_key: str, strategy_info: dict, 
                                       start_ts: int, end_ts: int, 
                                       backtest_resolution: str) -> tuple:
    """运行单个策略的回测（用于并行处理，每个策略使用独立的数据提供器）"""
    try:
        print(f"[{strategy_info['name']}] Starting backtest...")
        
        # 为每个策略创建独立的数据提供器实例（避免数据竞争）
        local_data_provider = LocalBinanceDataProvider()
        local_backtesting_provider = LocalBacktestingDataProvider(local_data_provider)
        local_backtesting_provider.update_backtesting_time(start_ts, end_ts)
        
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
                "interval": backtest_resolution,
            })
        
        all_params = {**common_params, **params}
        config = config_class(**all_params)
        
        # Initialize candles feed
        if hasattr(config, 'candles_connector'):
            candles_config = CandlesConfig(
                connector=config.candles_connector,
                trading_pair=config.candles_trading_pair,
                interval=backtest_resolution,
                max_records=100000
            )
        else:
            candles_config = CandlesConfig(
                connector="binance_perpetual",
                trading_pair=TRADING_PAIR,
                interval=backtest_resolution,
                max_records=100000
            )
        await local_backtesting_provider.initialize_candles_feed([candles_config])
        
        # Run backtest
        engine = BacktestingEngineBase()
        engine.backtesting_data_provider = local_backtesting_provider
        
        start_time = time.time()
        result = await engine.run_backtesting(
            controller_config=config,
            start=start_ts,
            end=end_ts,
            backtesting_resolution=backtest_resolution,
            trade_cost=Decimal(str(TRADING_FEE)),
            show_progress=True
        )
        elapsed_time = time.time() - start_time
        
        print(f"[{strategy_info['name']}] Backtest completed in {elapsed_time:.1f}s ({elapsed_time/60:.1f}min)")
        
        return (strategy_key, result, elapsed_time)
    except Exception as e:
        print(f"[{strategy_info['name']}] ✗ Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return (strategy_key, None, 0)


async def run_backtest_with_positions():
    """运行回测并生成仓位图"""
    print("="*80)
    print("Backtest with Position Curves - Optimized Version")
    print("="*80)
    print(f"Trading Pair: {TRADING_PAIR}")
    print(f"Time Range: {START_DATE.strftime('%Y-%m-%d')} to {END_DATE.strftime('%Y-%m-%d')}")
    print(f"Base Resolution: {BACKTEST_RESOLUTION}")
    
    # 确定实际使用的回测分辨率
    actual_resolution = RESAMPLE_INTERVAL if RESAMPLE_INTERVAL else BACKTEST_RESOLUTION
    print(f"Backtest Resolution: {actual_resolution}")
    if RESAMPLE_INTERVAL:
        print(f"  ⚠ Using resampled data: {BACKTEST_RESOLUTION} -> {RESAMPLE_INTERVAL}")
    
    print(f"Parallel Processing: {PARALLEL_STRATEGIES}")
    print()
    
    start_ts = int(START_DATE.timestamp())
    end_ts = int(END_DATE.timestamp())
    
    # Initialize data provider
    local_data_provider = LocalBinanceDataProvider()
    local_backtesting_provider = LocalBacktestingDataProvider(local_data_provider)
    local_backtesting_provider.update_backtesting_time(start_ts, end_ts)
    
    # Check data continuity (使用实际分辨率)
    print("Checking data continuity...")
    test_df = local_data_provider.get_historical_candles(
        symbol=TRADING_PAIR,
        start_ts=start_ts,
        end_ts=end_ts,
        interval=actual_resolution
    )
    
    # 输出详细的数据信息
    print(f"\n{'='*80}")
    print("Data Loading Summary")
    print(f"{'='*80}")
    print(f"Trading Pair: {TRADING_PAIR}")
    print(f"Requested Time Range: {START_DATE.strftime('%Y-%m-%d %H:%M:%S')} to {END_DATE.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Base Resolution: {BACKTEST_RESOLUTION}")
    print(f"Backtest Resolution: {actual_resolution}")
    print(f"Total Data Points: {len(test_df):,} candles")
    
    if len(test_df) > 0:
        actual_start = datetime.fromtimestamp(test_df['timestamp'].min())
        actual_end = datetime.fromtimestamp(test_df['timestamp'].max())
        print(f"Actual Data Range: {actual_start.strftime('%Y-%m-%d %H:%M:%S')} to {actual_end.strftime('%Y-%m-%d %H:%M:%S')}")
        
        # 计算数据覆盖率
        requested_duration = (END_DATE - START_DATE).total_seconds()
        actual_duration = (actual_end - actual_start).total_seconds()
        coverage = (actual_duration / requested_duration * 100) if requested_duration > 0 else 0
        print(f"Data Coverage: {coverage:.1f}%")
        
        # 计算预期数据点数量
        if actual_resolution == "1m":
            expected_points = requested_duration / 60
        elif actual_resolution == "5m":
            expected_points = requested_duration / 300
        elif actual_resolution == "15m":
            expected_points = requested_duration / 900
        elif actual_resolution == "30m":
            expected_points = requested_duration / 1800
        elif actual_resolution == "1h":
            expected_points = requested_duration / 3600
        else:
            expected_points = 0
        
        if expected_points > 0:
            completeness = (len(test_df) / expected_points * 100) if expected_points > 0 else 0
            print(f"Data Completeness: {completeness:.1f}% ({len(test_df):,} / {int(expected_points):,} expected)")
    else:
        print("⚠ No data loaded!")
    print(f"{'='*80}\n")
    
    # 对比3种策略
    strategies = {
        "PMM_Simple": {
            "name": "PMM Simple",
            "config_class": PMMSimpleConfig,
            "params": {
                "buy_spreads": [0.005, 0.01],
                "sell_spreads": [0.005, 0.01],
                "buy_amounts_pct": [Decimal("0.5"), Decimal("0.5")],
                "sell_amounts_pct": [Decimal("0.5"), Decimal("0.5")],
                "executor_refresh_time": 300,
            }
        },
        "PMM_Dynamic": {
            "name": "PMM Dynamic (MACD)",
            "config_class": PMMDynamicControllerConfig,
            "params": {
                "buy_spreads": [0.01, 0.02],
                "sell_spreads": [0.01, 0.02],
                "buy_amounts_pct": [Decimal("0.5"), Decimal("0.5")],
                "sell_amounts_pct": [Decimal("0.5"), Decimal("0.5")],
                "executor_refresh_time": 300,
                "candles_connector": "binance_perpetual",
                "candles_trading_pair": TRADING_PAIR,
                "interval": BACKTEST_RESOLUTION,
                "macd_fast": 12,
                "macd_slow": 26,
                "macd_signal": 9,
                "natr_length": 14,
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
                "executor_refresh_time": 300,
                "candles_connector": "binance_perpetual",
                "candles_trading_pair": TRADING_PAIR,
                "interval": BACKTEST_RESOLUTION,
                "take_profit_order_type": OrderType.MARKET,
                "training_window": 60,
                "natr_length": 14,
                "atr_length": 10,
            }
        }
    }
    
    all_curves = {}
    all_order_curves = {}
    all_results = {}
    
    # 运行回测（使用asyncio.gather实现并行）
    if PARALLEL_STRATEGIES and len(strategies) > 1:
        print(f"Running {len(strategies)} strategies in parallel...")
        print()
        
        # 创建任务列表（每个策略使用独立的数据提供器）
        tasks = [
            run_single_strategy_backtest(
                strategy_key, strategy_info,
                start_ts, end_ts, actual_resolution
            )
            for strategy_key, strategy_info in strategies.items()
        ]
        
        # 并行运行所有策略
        results = await asyncio.gather(*tasks)
        for strategy_key, result, elapsed in results:
            all_results[strategy_key] = (result, elapsed)
    else:
        # 串行运行
        for strategy_key, strategy_info in strategies.items():
            print(f"\n{'='*80}")
            print(f"Testing {strategy_info['name']}")
            print(f"{'='*80}")
            
            strategy_key, result, elapsed = await run_single_strategy_backtest(
                strategy_key, strategy_info,
                start_ts, end_ts, actual_resolution
            )
            all_results[strategy_key] = (result, elapsed)
    
    # 处理结果
    for strategy_key, (result, elapsed_time) in all_results.items():
        strategy_info = strategies[strategy_key]
        print(f"\n{'='*80}")
        print(f"Processing Results: {strategy_info['name']}")
        print(f"{'='*80}")
            
        if result and 'executors' in result:
            executors = result['executors']
            filled_executors = [e for e in executors if hasattr(e, 'filled_amount_quote') and e.filled_amount_quote and float(e.filled_amount_quote) > 0]
            filled_count = len(filled_executors)
            
            # 统计订单
            buy_orders = [e for e in executors if hasattr(e, 'side') and e.side == TradeType.BUY]
            sell_orders = [e for e in executors if hasattr(e, 'side') and e.side == TradeType.SELL]
            buy_filled = sum(1 for e in buy_orders if e in filled_executors)
            sell_filled = sum(1 for e in sell_orders if e in filled_executors)
            
            print(f"  Total Executors: {len(executors)}")
            print(f"  Filled Executors: {filled_count} ({filled_count/len(executors)*100:.1f}%)")
            print(f"  Buy Orders: {len(buy_orders)} (Filled: {buy_filled}, Fill Rate: {buy_filled/len(buy_orders)*100:.1f}%)")
            print(f"  Sell Orders: {len(sell_orders)} (Filled: {sell_filled}, Fill Rate: {sell_filled/len(sell_orders)*100:.1f}%)")
            
            # 计算PnL和指标
            total_pnl = sum(float(e.net_pnl_quote) if hasattr(e, 'net_pnl_quote') and e.net_pnl_quote else 0 for e in filled_executors)
            total_volume = sum(float(e.filled_amount_quote) for e in filled_executors)
            turnover_return = (total_pnl / total_volume * 100) if total_volume > 0 else 0
            
            print(f"  Total PnL: ${total_pnl:,.2f}")
            print(f"  Total Volume: ${total_volume:,.2f}")
            print(f"  Turnover Return: {turnover_return:.3f}%")
            print(f"  Return %: {(total_pnl / INITIAL_PORTFOLIO_USD * 100):.2f}%")
            
            # Generate equity curve
            print("  Generating position curve...")
            curve = generate_equity_curve(executors, start_ts, end_ts, INITIAL_PORTFOLIO_USD, actual_resolution)
            
            # Generate order curve
            print("  Generating order curve...")
            order_curve = generate_order_curves(executors, start_ts, end_ts)
            
            if not curve.empty:
                all_curves[strategy_key] = curve
                
                # Count position changes
                position_changes = (curve['position_value'].diff().abs() > 0.01).sum()
                max_position = curve['position_value'].max()
                final_pnl = curve['cumulative_pnl'].iloc[-1]
                
                print(f"  ✓ Generated position curve: {len(curve):,} data points")
                print(f"    Time range: {datetime.fromtimestamp(curve.index.min())} to {datetime.fromtimestamp(curve.index.max())}")
                print(f"    Position changes: {position_changes} times")
                print(f"    Max position value: ${max_position:,.2f}")
                print(f"    Final PnL: ${final_pnl:,.2f}")
                
                # Check for alternating long/short positions
                long_changes = (curve['long_position'].diff().abs() > 0.01).sum()
                short_changes = (curve['short_position'].diff().abs() > 0.01).sum()
                print(f"    Long position changes: {long_changes}")
                print(f"    Short position changes: {short_changes}")
                
                # Check if positions alternate
                has_long = (curve['long_position'] > 0.01).any()
                has_short = (curve['short_position'] > 0.01).any()
                print(f"    Has long positions: {has_long}")
                print(f"    Has short positions: {has_short}")
                
                if has_long and has_short:
                    print(f"    ✓ Both long and short positions exist (market making behavior)")
                else:
                    print(f"    ⚠ Missing long or short positions (may not be alternating)")
                
                # 检查数据连续性
                time_diffs = pd.Series(curve.index).diff().dropna()
                expected_interval = 60 if actual_resolution == "1m" else (300 if actual_resolution == "5m" else (900 if actual_resolution == "15m" else (1800 if actual_resolution == "30m" else 3600)))
                if (time_diffs == expected_interval).all():
                    print(f"    ✓ Position curve data is continuous (no gaps)")
                else:
                    gaps = time_diffs[time_diffs != expected_interval]
                    print(f"    ⚠ Found {len(gaps)} gaps in position curve")
            else:
                print(f"  ⚠ Failed to generate position curve")
            
            if not order_curve.empty:
                all_order_curves[strategy_key] = order_curve
                print(f"  ✓ Generated order curve: {len(order_curve):,} orders")
                print(f"    Buy orders: {len(order_curve[order_curve['side'] == TradeType.BUY])}")
                print(f"    Sell orders: {len(order_curve[order_curve['side'] == TradeType.SELL])}")
            else:
                print(f"  ⚠ Failed to generate order curve")
        else:
            print(f"  ✗ Backtest failed")
    
    # Generate plots
    if all_curves:
        print(f"\n{'='*80}")
        print("Generating Plots...")
        print(f"{'='*80}")
        
        output_path = f"backtest_1m_positions_{TRADING_PAIR.replace('-', '_')}_{START_DATE.strftime('%Y%m%d')}_{END_DATE.strftime('%Y%m%d')}.png"
        generate_plots(all_curves, all_order_curves, output_path)
        
        print(f"\n{'='*80}")
        print("Analysis Complete!")
        print(f"{'='*80}")
        print(f"Output file: {output_path}")
    else:
        print("\n  ⚠ No curves generated, skipping plot generation")


if __name__ == "__main__":
    asyncio.run(run_backtest_with_positions())

