#!/usr/bin/env python3
"""
多进程并行回测脚本 - 增强版
支持多个品种、多个策略的并行回测
包含画图功能（仓位价值、累积盈亏、挂单曲线、仓位价值分布）
使用joblib的multiprocessing backend实现真正的并行
自动管理回测结果目录结构
"""

import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
from typing import Dict, List, Optional, Tuple
from collections import defaultdict
import time
from joblib import Parallel, delayed
import multiprocessing
import json
import os

# Configure SSL certificates
cert_file = Path.home() / ".hummingbot_certs.pem"
if cert_file.exists():
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

import asyncio
from hummingbot.strategy_v2.backtesting.backtesting_engine_base import BacktestingEngineBase
from hummingbot.data_feed.candles_feed.data_types import CandlesConfig
from controllers.market_making.pmm_bar_portion import PMMBarPortionControllerConfig
from controllers.market_making.pmm_dynamic import PMMDynamicControllerConfig
from controllers.market_making.pmm_simple import PMMSimpleConfig
from hummingbot.strategy_v2.executors.position_executor.data_types import OrderType
from hummingbot.core.data_type.common import TradeType

# Import local data manager
from backtest_comparison_local import LocalBinanceDataProvider, LocalBacktestingDataProvider

# Production run parameters
TRADING_PAIRS = ["BTC-USDT", "ETH-USDT", "PUMP-USDT"]
START_DATE = datetime(2025, 9, 1)
END_DATE = datetime(2025, 9, 21)
INITIAL_PORTFOLIO_USD = 10000
MAKER_FEE = 0.0  # Maker手续费：0（免手续费）
TAKER_FEE = 0.0002  # Taker手续费：万2（0.02%）
BACKTEST_RESOLUTION = "1m"  # 基础数据：1分钟
RESAMPLE_INTERVAL: Optional[str] = None  # 不重采样，直接使用1分钟数据
PLOT_FREQUENCY = "3min"  # 画图频率：3分钟
USE_MULTIPROCESSING = True  # 使用joblib多进程并行
N_JOBS = -1  # -1表示使用所有CPU核心
ENVIRONMENT = "prod"  # 正式输出


def create_output_directory(environment: str = "test") -> Path:
    """
    创建输出目录结构
    
    backtest_results/
      test/ 或 prod/
        2025_11_14_17_10/
          PUMP-USDT/
            PUMP-USDT_test_PMM_Simple_params.png
            PUMP-USDT_test_PMM_Simple_params.csv
            ...
    """
    base_dir = Path(__file__).parent / "backtest_results"
    env_dir = base_dir / environment
    
    # 创建时间戳目录（格式：YYYY_MM_DD_HH_MM）
    now = datetime.now()
    timestamp_dir = env_dir / now.strftime("%Y_%m_%d_%H_%M")
    timestamp_dir.mkdir(parents=True, exist_ok=True)
    
    return timestamp_dir


def generate_equity_curve(executors: List, start_ts: int, end_ts: int, 
                          initial_portfolio: float, frequency: str = "3min",
                          filled_executors: Optional[List] = None) -> pd.DataFrame:
    """
    生成权益曲线、仓位曲线和PnL曲线（指定频率）
    """
    # 只处理已成交的executors
    if filled_executors is None:
        filled_executors = [
            e for e in executors 
            if hasattr(e, 'filled_amount_quote') and e.filled_amount_quote and float(e.filled_amount_quote) > 0
        ]
    
    if len(filled_executors) == 0:
        return pd.DataFrame()
    
    # 收集所有事件（开仓和平仓）
    events = []
    for executor in filled_executors:
        side = None
        if hasattr(executor, 'side'):
            side = executor.side
        elif hasattr(executor, 'config') and hasattr(executor.config, 'side'):
            side = executor.config.side
        
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
        if hasattr(executor, 'entry_price'):
            entry_price = float(executor.entry_price)
        elif hasattr(executor, 'config') and hasattr(executor.config, 'entry_price'):
            entry_price = float(executor.config.entry_price)
        
        if hasattr(executor, 'filled_amount_quote') and executor.filled_amount_quote:
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
            pnl = 0.0
            if hasattr(executor, 'net_pnl_quote') and executor.net_pnl_quote:
                pnl = float(executor.net_pnl_quote)
            
            events.append({
                'timestamp': close_ts,
                'type': 'close',
                'side': side,
                'price': entry_price,
                'position_value': position_value,
                'pnl': pnl,
            })
    
    if len(events) == 0:
        return pd.DataFrame()
    
    # 按时间排序
    events.sort(key=lambda x: x['timestamp'])
    
    # 生成时间序列（指定频率）
    start_dt = datetime.fromtimestamp(start_ts)
    end_dt = datetime.fromtimestamp(end_ts)
    timestamps = pd.date_range(start=start_dt, end=end_dt, freq=frequency)
    
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
        idx_ts = int(idx.timestamp())
        # 处理所有发生在此时间戳之前或等于此时间戳的事件
        while event_idx < len(events):
            event = events[event_idx]
            if event['timestamp'] <= idx_ts:
                if event['type'] == 'open':
                    if event['side'] == TradeType.BUY:
                        current_long_position += event['position_value']
                    elif event['side'] == TradeType.SELL:
                        current_short_position += event['position_value']
                elif event['type'] == 'close':
                    if event['side'] == TradeType.BUY:
                        current_long_position -= event['position_value']
                    elif event['side'] == TradeType.SELL:
                        current_short_position -= event['position_value']
                    cumulative_pnl += event.get('pnl', 0.0)
                event_idx += 1
            else:
                break
        
        # 更新此时间戳的权益曲线
        # 保留正负号：正数表示多头，负数表示空头
        total_position = current_long_position - current_short_position
        equity_curve.loc[idx, 'long_position'] = float(current_long_position)
        equity_curve.loc[idx, 'short_position'] = float(current_short_position)
        equity_curve.loc[idx, 'position_value'] = float(total_position)  # 保留正负号，不再使用绝对值
        equity_curve.loc[idx, 'cumulative_pnl'] = float(cumulative_pnl)
        equity_curve.loc[idx, 'equity'] = float(initial_portfolio + cumulative_pnl)
    
    return equity_curve


def generate_order_curves(executors: List) -> pd.DataFrame:
    """生成挂单曲线（订单价格曲线）"""
    orders = []
    for executor in executors:
        side = None
        if hasattr(executor, 'side'):
            side = executor.side
        elif hasattr(executor, 'config') and hasattr(executor.config, 'side'):
            side = executor.config.side
        
        if side is None:
            continue
        
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
                'datetime': datetime.fromtimestamp(timestamp),
                'side': side,
                'price': price,
                'filled': hasattr(executor, 'filled_amount_quote') and executor.filled_amount_quote and float(executor.filled_amount_quote) > 0
            })
    
    if len(orders) == 0:
        return pd.DataFrame()
    
    return pd.DataFrame(orders).sort_values('timestamp')


def generate_plots(result: Dict, output_dir: Path, trading_pair: str, strategy_name: str, 
                   environment: str, start_ts: int, end_ts: int, initial_portfolio: float,
                   price_df: Optional[pd.DataFrame] = None):
    """
    生成所有图表：仓位价值、累积盈亏、挂单曲线、仓位价值分布
    """
    if not result.get('success', False) or 'executors' not in result:
        print(f"  ⚠ Skipping plots for {strategy_name} (no executors)")
        return
    
    executors = result['executors']
    filled_executors = [
        e for e in executors 
        if hasattr(e, 'filled_amount_quote') and e.filled_amount_quote and float(e.filled_amount_quote) > 0
    ]
    
    # 生成权益曲线（3分钟频率）
    equity_curve = generate_equity_curve(
        executors, start_ts, end_ts, initial_portfolio, PLOT_FREQUENCY, filled_executors=filled_executors)
    
    # 生成挂单曲线
    order_curve = generate_order_curves(executors)

    # 计算价格波动率与盈亏收益率的分布
    volatility_summary = None
    if price_df is not None and not price_df.empty and len(filled_executors) > 0:
        try:
            price_temp = price_df[['timestamp', 'close']].dropna().copy()
            if not price_temp.empty:
                price_temp['datetime'] = pd.to_datetime(price_temp['timestamp'], unit='s')
                price_temp.sort_values('datetime', inplace=True)
                price_temp.set_index('datetime', inplace=True)
                price_returns = price_temp['close'].pct_change().dropna()
                if not price_returns.empty:
                    daily_vol = price_returns.groupby(price_returns.index.date).std().dropna()
                    if not daily_vol.empty:
                        vol_df = pd.DataFrame({
                            'date': [pd.Timestamp(d) for d in daily_vol.index],
                            'volatility': daily_vol.values
                        })
                        metric_rows = []
                        for executor in filled_executors:
                            ts = getattr(executor, 'close_timestamp', None)
                            if ts is None:
                                ts = getattr(executor.config, 'timestamp', None)
                            if ts is None:
                                continue
                            volume = float(executor.filled_amount_quote) if hasattr(executor, 'filled_amount_quote') and executor.filled_amount_quote else 0.0
                            if volume <= 0:
                                continue
                            pnl = float(executor.net_pnl_quote) if hasattr(executor, 'net_pnl_quote') and executor.net_pnl_quote else 0.0
                            metric_rows.append({
                                'date': pd.Timestamp(datetime.utcfromtimestamp(int(ts)).date()),
                                'volume': volume,
                                'pnl': pnl,
                            })
                        if metric_rows:
                            metrics_df = pd.DataFrame(metric_rows)
                            metrics_df = metrics_df.groupby('date').sum().reset_index()
                            metrics_df = metrics_df[metrics_df['volume'] > 0]
                            if not metrics_df.empty:
                                metrics_df['turnover_return'] = metrics_df['pnl'] / metrics_df['volume']
                                merged = pd.merge(vol_df, metrics_df[['date', 'turnover_return']], on='date', how='inner')
                                merged = merged.dropna()
                                if not merged.empty:
                                    unique_vols = merged['volatility'].nunique()
                                    bins_to_use = min(8, len(merged)) if unique_vols > 1 else 1
                                    if bins_to_use > 1:
                                        try:
                                            merged['vol_bin'] = pd.qcut(merged['volatility'], q=bins_to_use, duplicates='drop')
                                        except ValueError:
                                            merged['vol_bin'] = pd.cut(merged['volatility'], bins=bins_to_use, include_lowest=True)
                                    else:
                                        merged['vol_bin'] = pd.cut(merged['volatility'], bins=1, include_lowest=True)
                                    bin_summary = merged.groupby('vol_bin').agg(
                                        volatility_pct=('volatility', lambda x: np.mean(x) * 100),
                                        turnover_return_wan=('turnover_return', lambda x: np.mean(x) * 10000)
                                    ).reset_index()
                                    if not bin_summary.empty:
                                        def format_interval(interval):
                                            if isinstance(interval, pd.Interval):
                                                return f"{interval.left*100:.2f}%-{interval.right*100:.2f}%"
                                            return str(interval)
                                        bin_summary['label'] = bin_summary['vol_bin'].apply(format_interval)
                                        volatility_summary = bin_summary
        except Exception as exc:
            print(f"  ⚠ Failed to compute volatility summary for {trading_pair} - {strategy_name}: {exc}")
    
    # 创建图表
    fig = plt.figure(figsize=(20, 16))
    gs = fig.add_gridspec(4, 2, hspace=0.3, wspace=0.3)
    
    # 1. 仓位价值曲线（保留正负号）
    ax1 = fig.add_subplot(gs[0, :])
    if not equity_curve.empty:
        ax1.plot(equity_curve.index, equity_curve['position_value'], 
                label='Position Value (Long=+, Short=-)', color='#1f77b4', linewidth=1.5)
        ax1.axhline(y=0, color='black', linestyle='--', linewidth=1, alpha=0.5)
        ax1.set_ylabel('Position Value (USD)', fontsize=12)
        ax1.set_title('Position Value Over Time (Positive=Long, Negative=Short)', fontsize=14, fontweight='bold')
        ax1.legend(loc='upper left')
        ax1.grid(True, alpha=0.3)
        ax1.xaxis.set_major_locator(mdates.DayLocator(interval=1))
        ax1.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
    
    # 2. 累积盈亏曲线
    ax2 = fig.add_subplot(gs[1, :])
    if not equity_curve.empty:
        ax2.plot(equity_curve.index, equity_curve['cumulative_pnl'], 
                label='Cumulative PnL', color='#2ca02c', linewidth=1.5)
        ax2.axhline(y=0, color='black', linestyle='--', linewidth=1, alpha=0.5)
        ax2.set_ylabel('Cumulative PnL (USD)', fontsize=12)
        ax2.set_title('Cumulative PnL Over Time', fontsize=14, fontweight='bold')
        ax2.legend(loc='upper left')
        ax2.grid(True, alpha=0.3)
        ax2.xaxis.set_major_locator(mdates.DayLocator(interval=1))
        ax2.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
    
    # 3. 挂单曲线（买入/卖出）
    ax3 = fig.add_subplot(gs[2, :])
    if not order_curve.empty:
        buy_orders = order_curve[order_curve['side'] == TradeType.BUY]
        sell_orders = order_curve[order_curve['side'] == TradeType.SELL]
        
        if len(buy_orders) > 0:
            ax3.scatter(buy_orders['datetime'], buy_orders['price'], 
                       label='Buy Orders', color='green', alpha=0.6, s=10, marker='^')
        if len(sell_orders) > 0:
            ax3.scatter(sell_orders['datetime'], sell_orders['price'], 
                       label='Sell Orders', color='red', alpha=0.6, s=10, marker='v')
        
        ax3.set_ylabel('Order Price (USD)', fontsize=12)
        ax3.set_title('Order Prices Over Time', fontsize=14, fontweight='bold')
        ax3.legend(loc='upper left')
        ax3.grid(True, alpha=0.3)
        ax3.xaxis.set_major_locator(mdates.DayLocator(interval=1))
        ax3.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
    
    # 4. 仓位价值分布（直方图，包含正负值）
    ax4 = fig.add_subplot(gs[3, 0])
    if not equity_curve.empty:
        position_values = equity_curve['position_value'][equity_curve['position_value'] != 0]
        if len(position_values) > 0:
            ax4.hist(position_values, bins=50, color='#ff7f0e', alpha=0.7, edgecolor='black')
            ax4.axvline(x=0, color='black', linestyle='--', linewidth=1, alpha=0.5)
            ax4.set_xlabel('Position Value (USD, Positive=Long, Negative=Short)', fontsize=12)
            ax4.set_ylabel('Frequency', fontsize=12)
            ax4.set_title('Position Value Distribution', fontsize=14, fontweight='bold')
            ax4.grid(True, alpha=0.3)
    
    # 5. 波动率 vs. 盈亏收益率柱状图
    ax5 = fig.add_subplot(gs[3, 1])
    if volatility_summary is not None and not volatility_summary.empty:
        x = np.arange(len(volatility_summary))
        width = 0.35
        ax5.bar(x - width / 2, volatility_summary['volatility_pct'], width,
                label='Volatility (%)', color='#1f77b4', alpha=0.8)
        ax5.set_ylabel('Volatility (%)', fontsize=12, color='#1f77b4')
        ax5.tick_params(axis='y', labelcolor='#1f77b4')
        
        ax5b = ax5.twinx()
        ax5b.bar(x + width / 2, volatility_summary['turnover_return_wan'], width,
                 label='PnL/Volume (wan)', color='#ff7f0e', alpha=0.8)
        ax5b.set_ylabel('PnL/Volume (wan)', fontsize=12, color='#ff7f0e')
        ax5b.tick_params(axis='y', labelcolor='#ff7f0e')
        
        ax5.set_xticks(x)
        ax5.set_xticklabels(volatility_summary['label'], rotation=30, ha='right')
        ax5.set_xlabel('Volatility bins', fontsize=12)
        ax5.set_title('Volatility vs. Turnover Return', fontsize=14, fontweight='bold')
        ax5.grid(True, axis='y', alpha=0.3)
        ax5.legend(loc='upper left')
        ax5b.legend(loc='upper right')
    else:
        ax5.set_title('Volatility vs. Turnover Return', fontsize=14, fontweight='bold')
        ax5.text(0.5, 0.5, 'Insufficient data for volatility bins', ha='center', va='center', fontsize=12)
        ax5.axis('off')
    
    # 设置总标题
    fig.suptitle(f'{trading_pair} - {strategy_name} Backtest Results\n'
                 f'{datetime.fromtimestamp(start_ts).strftime("%Y-%m-%d")} to {datetime.fromtimestamp(end_ts).strftime("%Y-%m-%d")}',
                 fontsize=16, fontweight='bold', y=0.995)
    
    # 保存图表
    symbol_clean = trading_pair.replace('-', '_')
    strategy_clean = strategy_name.replace(' ', '_').replace('(', '').replace(')', '')
    filename = f"{symbol_clean}_{environment}_{strategy_clean}_plots.png"
    filepath = output_dir / filename
    plt.savefig(filepath, dpi=300, bbox_inches='tight')
    plt.close()
    
    print(f"  ✓ Plot saved: {filepath.name}")
    
    # 保存CSV数据
    if not equity_curve.empty:
        csv_filename = f"{symbol_clean}_{environment}_{strategy_clean}_data.csv"
        csv_filepath = output_dir / csv_filename
        equity_curve.to_csv(csv_filepath)
        print(f"  ✓ CSV saved: {csv_filepath.name}")


def prepare_data_for_symbol(trading_pair: str, start_ts: int, end_ts: int, 
                            backtest_resolution: str) -> Tuple[Optional[pd.DataFrame], Dict]:
    """为单个品种准备数据"""
    try:
        print(f"[Data Prep] Preparing data for {trading_pair}...")
        local_data_provider = LocalBinanceDataProvider()
        df = local_data_provider.get_historical_candles(
            symbol=trading_pair, start_ts=start_ts, end_ts=end_ts, interval=backtest_resolution
        )
        if df.empty:
            print(f"[Data Prep] ⚠ No data for {trading_pair}")
            return None, {}
        actual_start = datetime.fromtimestamp(df['timestamp'].min())
        actual_end = datetime.fromtimestamp(df['timestamp'].max())
        data_info = {
            'trading_pair': trading_pair,
            'data_points': len(df),
            'actual_start': actual_start,
            'actual_end': actual_end,
            'backtest_resolution': backtest_resolution,
        }
        print(f"[Data Prep] ✓ {trading_pair}: {len(df):,} candles ({actual_start} to {actual_end})")
        return df, data_info
    except Exception as e:
        print(f"[Data Prep] ✗ Error preparing data for {trading_pair}: {e}")
        import traceback
        traceback.print_exc()
        return None, {}


def run_single_backtest_sync(trading_pair: str, strategy_key: str, strategy_name: str,
                             strategy_config_class_name: str, strategy_params_dict: dict,
                             start_ts: int, end_ts: int, backtest_resolution: str,
                             initial_portfolio: float, trading_fee: float) -> Dict:
    """同步包装函数：运行单个策略的回测（用于多进程）"""
    try:
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).parent.parent.parent))
        tradingview_ai_path = Path("/Users/wilson/Desktop/tradingview-ai")
        sys.path.insert(0, str(tradingview_ai_path))
        
        class FakeCCXT:
            pass
        sys.modules['ccxt'] = FakeCCXT()
        
        import asyncio
        from decimal import Decimal
        from hummingbot.strategy_v2.backtesting.backtesting_engine_base import BacktestingEngineBase
        from hummingbot.data_feed.candles_feed.data_types import CandlesConfig
        from controllers.market_making.pmm_bar_portion import PMMBarPortionControllerConfig
        from controllers.market_making.pmm_dynamic import PMMDynamicControllerConfig
        from controllers.market_making.pmm_simple import PMMSimpleConfig
        from backtest_comparison_local import LocalBinanceDataProvider, LocalBacktestingDataProvider
        
        config_class_map = {
            'PMMSimpleConfig': PMMSimpleConfig,
            'PMMDynamicControllerConfig': PMMDynamicControllerConfig,
            'PMMBarPortionControllerConfig': PMMBarPortionControllerConfig,
        }
        config_class = config_class_map.get(strategy_config_class_name)
        if not config_class:
            raise ValueError(f"Unknown config class: {strategy_config_class_name}")
        
        params = {}
        for k, v in strategy_params_dict.items():
            if isinstance(v, str):
                if any(keyword in k.lower() for keyword in ['amount', 'pct']):
                    try:
                        params[k] = Decimal(v)
                    except:
                        params[k] = v
                else:
                    params[k] = v
            elif isinstance(v, list) and len(v) > 0:
                if isinstance(v[0], str):
                    if any(keyword in k.lower() for keyword in ['amount', 'pct']):
                        try:
                            params[k] = [Decimal(x) for x in v]
                        except:
                            params[k] = v
                    else:
                        params[k] = v
                else:
                    params[k] = v
            else:
                params[k] = v
        
        strategy_params = {
            'name': strategy_name,
            'config_class': config_class,
            'params': params
        }
        
        result = asyncio.run(run_single_backtest_async(
            trading_pair, strategy_key, strategy_params,
            start_ts, end_ts, backtest_resolution,
            initial_portfolio, trading_fee
        ))
        
        return result
    except Exception as e:
        print(f"[{strategy_key}] ✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return {
            'trading_pair': trading_pair,
            'strategy_key': strategy_key,
            'success': False,
            'error': str(e)
        }


async def run_single_backtest_async(trading_pair: str, strategy_key: str, 
                                   strategy_params: dict,
                                   start_ts: int, end_ts: int, backtest_resolution: str,
                                   initial_portfolio: float, trading_fee: float) -> Dict:
    """
    异步函数：运行单个策略的回测
    
    注意：需要导入generate_equity_curve函数来计算仓位价值
    """
    """异步函数：运行单个策略的回测"""
    try:
        strategy_name = strategy_params.get('name', strategy_key)
        print(f"[{strategy_name}] Starting backtest for {trading_pair}...")
        
        local_data_provider = LocalBinanceDataProvider()
        local_backtesting_provider = LocalBacktestingDataProvider(local_data_provider)
        local_backtesting_provider.update_backtesting_time(start_ts, end_ts)
        
        from decimal import Decimal
        config_class = strategy_params["config_class"]
        params = strategy_params["params"].copy()
        
        for k, v in params.items():
            if isinstance(v, str):
                if any(keyword in k.lower() for keyword in ['amount', 'pct', 'loss', 'profit']):
                    try:
                        params[k] = Decimal(v)
                    except:
                        pass
                elif 'order_type' in k.lower() and v.startswith('OrderType.'):
                    from hummingbot.strategy_v2.executors.position_executor.data_types import OrderType
                    if 'MARKET' in v:
                        params[k] = OrderType.MARKET
                    elif 'LIMIT' in v:
                        params[k] = OrderType.LIMIT
            elif isinstance(v, list) and len(v) > 0:
                if isinstance(v[0], str):
                    if any(keyword in k.lower() for keyword in ['amount', 'pct']):
                        try:
                            params[k] = [Decimal(x) for x in v]
                        except:
                            pass
        
        common_params = {
            "controller_name": strategy_key.lower(),
            "connector_name": "binance_perpetual",
            "trading_pair": trading_pair,
            "total_amount_quote": Decimal(str(initial_portfolio)),
        }
        
        if strategy_key not in ["PMM_Simple", "PMM_Simple_Future"]:
            common_params.update({
                "candles_connector": "binance_perpetual",
                "candles_trading_pair": trading_pair,
                "interval": backtest_resolution,
            })
        
        all_params = {**common_params, **params}
        config = config_class(**all_params)
        
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
                trading_pair=trading_pair,
                interval=backtest_resolution,
                max_records=100000
            )
        await local_backtesting_provider.initialize_candles_feed([candles_config])
        
        engine = BacktestingEngineBase()
        engine.backtesting_data_provider = local_backtesting_provider
        
        start_time = time.time()
        result = await engine.run_backtesting(
            controller_config=config,
            start=start_ts,
            end=end_ts,
            backtesting_resolution=backtest_resolution,
            # 使用taker_fee作为交易成本（因为回测中订单可能被taker成交）
            trade_cost=Decimal(str(trading_fee)),
            show_progress=False
        )
        elapsed_time = time.time() - start_time
        
        print(f"[{strategy_name}] ✓ Completed in {elapsed_time:.1f}s ({elapsed_time/60:.1f}min)")
        
        if result and 'executors' in result:
            executors = result['executors']
            filled_executors = [e for e in executors 
                              if hasattr(e, 'filled_amount_quote') and e.filled_amount_quote 
                              and float(e.filled_amount_quote) > 0]
            
            buy_orders = [e for e in executors if hasattr(e, 'side') and e.side == TradeType.BUY]
            sell_orders = [e for e in executors if hasattr(e, 'side') and e.side == TradeType.SELL]
            buy_filled = sum(1 for e in buy_orders if e in filled_executors)
            sell_filled = sum(1 for e in sell_orders if e in filled_executors)
            
            total_pnl = sum(float(e.net_pnl_quote) if hasattr(e, 'net_pnl_quote') and e.net_pnl_quote else 0 
                          for e in filled_executors)
            total_volume = sum(float(e.filled_amount_quote) for e in filled_executors)
            turnover_return = (total_pnl / total_volume * 100) if total_volume > 0 else 0
            
            buy_pnl = sum(float(e.net_pnl_quote) if hasattr(e, 'net_pnl_quote') and e.net_pnl_quote else 0 
                         for e in filled_executors if hasattr(e, 'side') and e.side == TradeType.BUY)
            sell_pnl = sum(float(e.net_pnl_quote) if hasattr(e, 'net_pnl_quote') and e.net_pnl_quote else 0 
                          for e in filled_executors if hasattr(e, 'side') and e.side == TradeType.SELL)
            
            total_orders = len(executors)
            cancelled_orders = total_orders - len(filled_executors)
            
            duration_days = (end_ts - start_ts) / 86400
            daily_volume = total_volume / duration_days if duration_days > 0 else 0
            daily_pnl = total_pnl / duration_days if duration_days > 0 else 0
            # daily_return应该是日均盈亏/日均交易额，采用"万{ratio}"格式（万分之几）
            # 例如：daily_return = 0.5 表示万0.5（即0.05%）
            daily_return = (daily_pnl / daily_volume * 10000) if daily_volume > 0 else 0
            
            # 计算最大多仓价值和最大空仓价值（从executors直接计算）
            max_long_position_value = 0.0
            max_short_position_value = 0.0
            
            # 从executors直接计算最大仓位价值
            for executor in filled_executors:
                if not hasattr(executor, 'filled_amount_quote') or not executor.filled_amount_quote:
                    continue
                
                position_value = float(executor.filled_amount_quote)
                side = None
                if hasattr(executor, 'side'):
                    side = executor.side
                elif hasattr(executor, 'config') and hasattr(executor.config, 'side'):
                    side = executor.config.side
                
                if side == TradeType.BUY:
                    max_long_position_value = max(max_long_position_value, position_value)
                elif side == TradeType.SELL:
                    max_short_position_value = max(max_short_position_value, position_value)
            
            # 如果从executors计算失败，尝试从equity_curve计算
            if max_long_position_value == 0.0 and max_short_position_value == 0.0:
                equity_curve = generate_equity_curve(
                    executors, start_ts, end_ts, initial_portfolio, "15m", filled_executors=filled_executors)
                if not equity_curve.empty:
                    # 最大多仓价值（正数）
                    long_positions = equity_curve['long_position']
                    if len(long_positions) > 0 and long_positions.max() > 0:
                        max_long_position_value = float(long_positions.max())
                    
                    # 最大空仓价值（绝对值，因为short_position是正数）
                    short_positions = equity_curve['short_position']
                    if len(short_positions) > 0 and short_positions.max() > 0:
                        max_short_position_value = float(short_positions.max())
            
            # 兼容性：保留max_position_value（取两者最大值）
            max_position_value = max(max_long_position_value, max_short_position_value)
            
            maker_fee_paid = total_volume * MAKER_FEE
            taker_fee_paid = total_volume * TAKER_FEE
            return {
                'trading_pair': trading_pair,
                'strategy_key': strategy_key,
                'strategy_name': strategy_name,
                'success': True,
                'elapsed_time': elapsed_time,
                'total_executors': len(executors),
                'filled_executors': len(filled_executors),
                'fill_rate': len(filled_executors) / len(executors) if len(executors) > 0 else 0,
                'buy_orders': len(buy_orders),
                'sell_orders': len(sell_orders),
                'buy_filled': buy_filled,
                'sell_filled': sell_filled,
                'buy_fill_rate': buy_filled / len(buy_orders) if len(buy_orders) > 0 else 0,
                'sell_fill_rate': sell_filled / len(sell_orders) if len(sell_orders) > 0 else 0,
                'total_pnl': total_pnl,
                'total_volume': total_volume,
                'turnover_return': turnover_return,
                'return_pct': (total_pnl / initial_portfolio * 100),
                'buy_pnl': buy_pnl,
                'sell_pnl': sell_pnl,
                'total_orders': total_orders,
                'cancelled_orders': cancelled_orders,
                'daily_volume': daily_volume,
                'daily_pnl': daily_pnl,
                'daily_return': daily_return,  # 万分之几格式
                'max_position_value': max_position_value,
                'max_long_position_value': max_long_position_value,
                'max_short_position_value': max_short_position_value,
                'maker_fee_paid': maker_fee_paid,
                'taker_fee_paid': taker_fee_paid,
                'executors': executors,
            }
        else:
            return {
                'trading_pair': trading_pair,
                'strategy_key': strategy_key,
                'strategy_name': strategy_name,
                'success': False,
                'error': 'No executors returned'
            }
    except Exception as e:
        print(f"[{strategy_params.get('name', strategy_key)}] ✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return {
            'trading_pair': trading_pair,
            'strategy_key': strategy_key,
            'strategy_name': strategy_params.get('name', strategy_key),
            'success': False,
            'error': str(e)
        }


def generate_comprehensive_report(all_results: List[Dict], data_info_dict: Dict[str, Dict], 
                                  maker_fee: float, taker_fee: float) -> str:
    """生成综合报告"""
    report = []
    report.append("="*80)
    report.append("Backtest Results Summary")
    report.append("="*80)
    report.append("")
    
    report.append("Trading Fee Configuration:")
    report.append("-"*80)
    report.append(f"  Maker Fee: {maker_fee*100:.4f}%")
    report.append(f"  Taker Fee: {taker_fee*100:.4f}%")
    report.append("")
    
    report.append("Data Information:")
    report.append("-"*80)
    for trading_pair, info in data_info_dict.items():
        report.append(f"  {trading_pair}:")
        report.append(f"    Data Points: {info['data_points']:,}")
        report.append(f"    Time Range: {info['actual_start']} to {info['actual_end']}")
        report.append(f"    Resolution: {info['backtest_resolution']}")
    report.append("")
    
    report.append("Backtest Results:")
    report.append("-"*80)
    report.append(f"{'Symbol':<12} {'Strategy':<20} {'Executors':<12} {'Filled':<10} {'Fill Rate':<12} "
                  f"{'Buy Fill':<12} {'Sell Fill':<12} {'PnL ($)':<12} {'Return %':<12}")
    report.append("-"*80)
    
    for result in all_results:
        if not result.get('success', False):
            continue
        report.append(f"{result['trading_pair']:<12} {result['strategy_name']:<20} "
                      f"{result['total_executors']:<12} {result['filled_executors']:<10} "
                      f"{result['fill_rate']*100:<11.2f}% {result['buy_fill_rate']*100:<11.2f}% "
                      f"{result['sell_fill_rate']*100:<11.2f}% ${result['total_pnl']:<11.2f} "
                      f"{result['return_pct']:<11.2f}%")
    
    report.append("")
    report.append("Detailed Metrics:")
    report.append("-"*80)
    for result in all_results:
        if not result.get('success', False):
            continue
        report.append(f"\n{result['trading_pair']} - {result['strategy_name']}:")
        report.append(f"  Total Executors: {result['total_executors']}")
        report.append(f"  Filled Executors: {result['filled_executors']} ({result['fill_rate']*100:.2f}%)")
        report.append(f"  Buy Orders: {result['buy_orders']} (Filled: {result['buy_filled']}, "
                      f"Fill Rate: {result['buy_fill_rate']*100:.2f}%)")
        report.append(f"  Sell Orders: {result['sell_orders']} (Filled: {result['sell_filled']}, "
                      f"Fill Rate: {result['sell_fill_rate']*100:.2f}%)")
        report.append(f"  Total PnL: ${result['total_pnl']:,.2f}")
        report.append(f"  Total Volume: ${result['total_volume']:,.2f}")
        report.append(f"  Turnover Return: {result['turnover_return']:.3f}%")
        report.append(f"  Return %: {result['return_pct']:.2f}%")
        report.append(f"  Buy PnL: ${result['buy_pnl']:,.2f}")
        report.append(f"  Sell PnL: ${result['sell_pnl']:,.2f}")
        report.append(f"  Total Orders: {result['total_orders']}")
        report.append(f"  Cancelled Orders: {result['cancelled_orders']}")
        report.append(f"  Daily Volume: ${result['daily_volume']:,.2f}")
        report.append(f"  Daily PnL: ${result.get('daily_pnl', 0):,.2f}")
        report.append(f"  Daily Return: 万{result['daily_return']:.4f} (Daily PnL / Daily Volume)")
        report.append(f"  Max Long Position Value: ${result.get('max_long_position_value', 0):,.2f}")
        report.append(f"  Max Short Position Value: ${result.get('max_short_position_value', 0):,.2f}")
        report.append(f"  Max Position Value: ${result['max_position_value']:,.2f}")
        report.append(f"  Maker Fee Paid: ${result.get('maker_fee_paid', 0):,.2f}")
        report.append(f"  Taker Fee Paid: ${result.get('taker_fee_paid', 0):,.2f}")
        report.append(f"  Backtest Time: {result['elapsed_time']:.1f}s ({result['elapsed_time']/60:.1f}min)")
    
    report.append("")
    report.append("="*80)
    
    return "\n".join(report)


def main():
    """主函数"""
    print("="*80)
    print("Multi-Process Parallel Backtest with Plots")
    print("="*80)
    print(f"Trading Pairs: {', '.join(TRADING_PAIRS)}")
    print(f"Time Range: {START_DATE.strftime('%Y-%m-%d')} to {END_DATE.strftime('%Y-%m-%d')}")
    print(f"Base Resolution: {BACKTEST_RESOLUTION}")
    print(f"Backtest Resolution: {RESAMPLE_INTERVAL if RESAMPLE_INTERVAL else BACKTEST_RESOLUTION}")
    print(f"Plot Frequency: {PLOT_FREQUENCY}")
    print(f"Environment: {ENVIRONMENT}")
    print(f"Multiprocessing: {USE_MULTIPROCESSING} (Jobs: {N_JOBS})")
    print()
    
    # 创建输出目录
    output_base_dir = create_output_directory(ENVIRONMENT)
    print(f"Output Directory: {output_base_dir}")
    print()
    
    start_ts = int(START_DATE.timestamp())
    end_ts = int(END_DATE.timestamp())
    actual_resolution = RESAMPLE_INTERVAL if RESAMPLE_INTERVAL else BACKTEST_RESOLUTION
    
    # 策略配置
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
                "candles_trading_pair": None,
                "interval": actual_resolution,
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
                "candles_trading_pair": None,
                "interval": actual_resolution,
                "take_profit_order_type": OrderType.MARKET,
                "training_window": 60,
                "natr_length": 14,
                "atr_length": 10,
            }
        },
        "PMM_Simple_Future": {
            "name": "PMM Simple (Future Data)",
            "config_class": PMMSimpleConfig,
            "params": {
                "buy_spreads": [0.005, 0.01],
                "sell_spreads": [0.005, 0.01],
                "buy_amounts_pct": [Decimal("0.5"), Decimal("0.5")],
                "sell_amounts_pct": [Decimal("0.5"), Decimal("0.5")],
                "executor_refresh_time": 300,
                "use_future_data": True,
            }
        },
        "PMM_Dynamic_Future": {
            "name": "PMM Dynamic (MACD) Future Data",
            "config_class": PMMDynamicControllerConfig,
            "params": {
                "buy_spreads": [0.01, 0.02],
                "sell_spreads": [0.01, 0.02],
                "buy_amounts_pct": [Decimal("0.5"), Decimal("0.5")],
                "sell_amounts_pct": [Decimal("0.5"), Decimal("0.5")],
                "executor_refresh_time": 300,
                "candles_connector": "binance_perpetual",
                "candles_trading_pair": None,
                "interval": actual_resolution,
                "macd_fast": 12,
                "macd_slow": 26,
                "macd_signal": 9,
                "natr_length": 14,
                "use_future_data": True,
            }
        },
        "PMM_Bar_Portion_Future": {
            "name": "PMM Bar Portion (Future Data)",
            "config_class": PMMBarPortionControllerConfig,
            "params": {
                "buy_spreads": [0.01, 0.02],
                "sell_spreads": [0.01, 0.02],
                "buy_amounts_pct": [Decimal("0.5"), Decimal("0.5")],
                "sell_amounts_pct": [Decimal("0.5"), Decimal("0.5")],
                "executor_refresh_time": 300,
                "candles_connector": "binance_perpetual",
                "candles_trading_pair": None,
                "interval": actual_resolution,
                "take_profit_order_type": OrderType.MARKET,
                "training_window": 60,
                "natr_length": 14,
                "atr_length": 10,
                "use_future_data": True,
            }
        }
    }
    
    # 步骤1: 准备数据
    print("Step 1: Preparing data for all symbols...")
    print("-"*80)
    data_info_dict = {}
    price_data_dict = {}
    for trading_pair in TRADING_PAIRS:
        df, info = prepare_data_for_symbol(trading_pair, start_ts, end_ts, actual_resolution)
        if df is not None:
            data_info_dict[trading_pair] = info
            price_data_dict[trading_pair] = df
    print()
    
    if not data_info_dict:
        print("✗ No data available, exiting...")
        return
    
    # 步骤2: 生成回测任务
    print("Step 2: Generating backtest tasks...")
    print("-"*80)
    tasks = []
    for trading_pair in TRADING_PAIRS:
        if trading_pair not in data_info_dict:
            continue
        for strategy_key, strategy_info in strategies.items():
            params_dict = strategy_info['params'].copy()
            if 'candles_trading_pair' in params_dict and params_dict['candles_trading_pair'] is None:
                params_dict['candles_trading_pair'] = trading_pair
            
            serializable_params = {}
            for k, v in params_dict.items():
                if isinstance(v, Decimal):
                    serializable_params[k] = str(v)
                elif isinstance(v, list) and len(v) > 0:
                    if isinstance(v[0], Decimal):
                        serializable_params[k] = [str(x) for x in v]
                    elif isinstance(v[0], (int, float)):
                        serializable_params[k] = v
                    else:
                        serializable_params[k] = v
                elif hasattr(v, 'name') and hasattr(v, 'value'):
                    serializable_params[k] = f"{type(v).__name__}.{v.name}"
                else:
                    serializable_params[k] = v
            
            config_class = strategy_info['config_class']
            config_class_name = config_class.__name__
            
            tasks.append((
                trading_pair,
                strategy_key,
                strategy_info['name'],
                config_class_name,
                serializable_params,
                start_ts,
                end_ts,
                actual_resolution,
                INITIAL_PORTFOLIO_USD,
                TAKER_FEE  # 使用TAKER_FEE作为交易成本
            ))
            print(f"  Task: {trading_pair} - {strategy_info['name']}")
    print(f"Total tasks: {len(tasks)}")
    print()
    
    # 步骤3: 并行运行回测
    print("Step 3: Running backtests in parallel...")
    print("-"*80)
    start_time = time.time()
    
    if USE_MULTIPROCESSING and len(tasks) > 1:
        results = Parallel(n_jobs=N_JOBS, backend='multiprocessing', verbose=10)(
            delayed(run_single_backtest_sync)(*task) for task in tasks
        )
    else:
        results = [run_single_backtest_sync(*task) for task in tasks]
    
    total_time = time.time() - start_time
    print(f"\n✓ All backtests completed in {total_time:.1f}s ({total_time/60:.1f}min)")
    print()
    
    # 步骤4: 生成图表和保存结果
    print("Step 4: Generating plots and saving results...")
    print("-"*80)
    
    for result in results:
        if not result.get('success', False):
            continue
        
        trading_pair = result['trading_pair']
        strategy_name = result['strategy_name']
        
        # 为每个品种创建目录
        symbol_dir = output_base_dir / trading_pair.replace('-', '_')
        symbol_dir.mkdir(exist_ok=True)
        
        # 生成图表
        print(f"Generating plots for {trading_pair} - {strategy_name}...")
        generate_plots(result, symbol_dir, trading_pair, strategy_name, 
                      ENVIRONMENT, start_ts, end_ts, INITIAL_PORTFOLIO_USD,
                      price_df=price_data_dict.get(trading_pair))
    
    # 步骤5: 生成报告并保存JSON（每个品种单独保存）
    print("\nStep 5: Generating reports and saving results...")
    print("-"*80)
    report = generate_comprehensive_report(results, data_info_dict, MAKER_FEE, TAKER_FEE)
    print(report)
    
    # 为每个品种保存JSON文件（不保存TXT报告）
    for trading_pair in TRADING_PAIRS:
        if trading_pair not in data_info_dict:
            continue
        
        symbol_dir = output_base_dir / trading_pair.replace('-', '_')
        symbol_dir.mkdir(exist_ok=True)
        
        # 只保存该品种的结果
        symbol_results = [r for r in results if r.get('trading_pair') == trading_pair]
        serializable_results = []
        for result in symbol_results:
            serializable_result = {k: v for k, v in result.items() if k != 'executors'}
            serializable_results.append(serializable_result)
        
        json_data = {
            'start_date': START_DATE.strftime('%Y-%m-%d'),
            'end_date': END_DATE.strftime('%Y-%m-%d'),
            'trading_pair': trading_pair,
            'backtest_resolution': actual_resolution,
            'plot_frequency': PLOT_FREQUENCY,
            'environment': ENVIRONMENT,
            'trading_fees': {
                'maker_fee': MAKER_FEE,
                'taker_fee': TAKER_FEE,
                'maker_fee_pct': MAKER_FEE * 100,  # 百分比形式（0%）
                'taker_fee_pct': TAKER_FEE * 100,  # 百分比形式（0.02%）
                'maker_fee_wan': MAKER_FEE * 10000,  # 万分之几形式（0）
                'taker_fee_wan': TAKER_FEE * 10000   # 万分之几形式（2）
            },
            'data_info': data_info_dict.get(trading_pair, {}),
            'results': serializable_results,
            'total_time': total_time
        }
        
        symbol_clean = trading_pair.replace('-', '_')
        json_filename = f"{symbol_clean}_{ENVIRONMENT}.json"
        json_file = symbol_dir / json_filename
        json_file.write_text(json.dumps(json_data, indent=2, default=str), encoding='utf-8')
        print(f"✓ JSON saved: {json_file}")
    
    print(f"\n{'='*80}")
    print("Backtest Complete!")
    print(f"{'='*80}")
    print(f"Output directory: {output_base_dir}")


if __name__ == "__main__":
    if sys.platform == 'darwin':
        multiprocessing.set_start_method('spawn', force=True)
    
    main()

