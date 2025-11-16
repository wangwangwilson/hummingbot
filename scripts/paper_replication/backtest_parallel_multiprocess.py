#!/usr/bin/env python3
"""
多进程并行回测脚本
支持多个品种、多个策略的并行回测
使用joblib的multiprocessing backend实现真正的并行
"""

import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from typing import Dict, List, Optional, Tuple
import time
from joblib import Parallel, delayed
import multiprocessing
import pickle

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

# Test parameters
TRADING_PAIRS = ["PUMP-USDT"]  # 支持多个品种
START_DATE = datetime(2025, 10, 25)  # 测试5天数据（使用有数据的日期）
END_DATE = datetime(2025, 10, 31)
INITIAL_PORTFOLIO_USD = 10000
TRADING_FEE = 0.0004
BACKTEST_RESOLUTION = "1m"  # 基础数据：1分钟
RESAMPLE_INTERVAL: Optional[str] = "15m"  # 15分钟采样
USE_MULTIPROCESSING = True  # 使用joblib多进程并行
N_JOBS = -1  # -1表示使用所有CPU核心


def prepare_data_for_symbol(trading_pair: str, start_ts: int, end_ts: int, 
                            backtest_resolution: str) -> Tuple[Optional[pd.DataFrame], Dict]:
    """
    为单个品种准备数据（在主进程中执行，避免重复加载）
    
    Returns:
        (data_df, data_info): 数据DataFrame和数据信息字典
    """
    try:
        print(f"[Data Prep] Preparing data for {trading_pair}...")
        
        local_data_provider = LocalBinanceDataProvider()
        
        # 加载数据
        df = local_data_provider.get_historical_candles(
            symbol=trading_pair,
            start_ts=start_ts,
            end_ts=end_ts,
            interval=backtest_resolution
        )
        
        if df.empty:
            print(f"[Data Prep] ⚠ No data for {trading_pair}")
            return None, {}
        
        # 数据信息
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
    """
    同步包装函数：运行单个策略的回测（用于多进程）
    
    Args:
        trading_pair: 交易对
        strategy_key: 策略键
        strategy_name: 策略名称
        strategy_config_class_name: 策略配置类名（字符串，用于动态导入）
        strategy_params_dict: 策略参数字典（可序列化）
        start_ts: 开始时间戳
        end_ts: 结束时间戳
        backtest_resolution: 回测分辨率
        initial_portfolio: 初始资金
        trading_fee: 交易手续费
    
    Returns:
        回测结果字典
    """
    try:
        # 在新进程中重新导入（避免序列化问题）
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
        
        # 动态获取配置类
        config_class_map = {
            'PMMSimpleConfig': PMMSimpleConfig,
            'PMMDynamicControllerConfig': PMMDynamicControllerConfig,
            'PMMBarPortionControllerConfig': PMMBarPortionControllerConfig,
        }
        config_class = config_class_map.get(strategy_config_class_name)
        if not config_class:
            raise ValueError(f"Unknown config class: {strategy_config_class_name}")
        
        # 重建策略参数字典
        params = {}
        for k, v in strategy_params_dict.items():
            # 只对amount和pct相关的参数转换为Decimal，spreads保持为float
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
        
        # 运行异步回测
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
    """
    try:
        strategy_name = strategy_params.get('name', strategy_key)
        print(f"[{strategy_name}] Starting backtest for {trading_pair}...")
        
        # 创建独立的数据提供器实例
        local_data_provider = LocalBinanceDataProvider()
        local_backtesting_provider = LocalBacktestingDataProvider(local_data_provider)
        local_backtesting_provider.update_backtesting_time(start_ts, end_ts)
        
        # 创建策略配置
        from decimal import Decimal
        config_class = strategy_params["config_class"]
        params = strategy_params["params"].copy()
        
        # 转换字符串回Decimal和其他类型
        for k, v in params.items():
            if isinstance(v, str):
                # 检查是否是Decimal字符串
                if any(keyword in k.lower() for keyword in ['amount', 'pct', 'loss', 'profit']):
                    try:
                        params[k] = Decimal(v)
                    except:
                        pass
                # 检查是否是OrderType字符串
                elif 'order_type' in k.lower() and v.startswith('OrderType.'):
                    from hummingbot.strategy_v2.executors.position_executor.data_types import OrderType
                    if 'MARKET' in v:
                        params[k] = OrderType.MARKET
                    elif 'LIMIT' in v:
                        params[k] = OrderType.LIMIT
            elif isinstance(v, list) and len(v) > 0:
                if isinstance(v[0], str):
                    # 检查是否是Decimal列表
                    if any(keyword in k.lower() for keyword in ['amount', 'pct']):
                        try:
                            params[k] = [Decimal(x) for x in v]
                        except:
                            pass
                    else:
                        # 保持原样（可能是其他类型）
                        pass
                elif isinstance(v[0], (int, float)):
                    # spreads等保持为float列表（不需要Decimal）
                    pass
        
        common_params = {
            "controller_name": strategy_key.lower(),
            "connector_name": "binance_perpetual",
            "trading_pair": trading_pair,
            "total_amount_quote": Decimal(str(initial_portfolio)),
        }
        
        if strategy_key != "PMM_Simple":
            common_params.update({
                "candles_connector": "binance_perpetual",
                "candles_trading_pair": trading_pair,
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
                trading_pair=trading_pair,
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
            trade_cost=Decimal(str(trading_fee)),
            show_progress=False  # 多进程时关闭进度条
        )
        elapsed_time = time.time() - start_time
        
        print(f"[{strategy_name}] ✓ Completed in {elapsed_time:.1f}s ({elapsed_time/60:.1f}min)")
        
        # 处理结果
        if result and 'executors' in result:
            executors = result['executors']
            filled_executors = [e for e in executors 
                              if hasattr(e, 'filled_amount_quote') and e.filled_amount_quote 
                              and float(e.filled_amount_quote) > 0]
            
            # 统计订单
            buy_orders = [e for e in executors if hasattr(e, 'side') and e.side == TradeType.BUY]
            sell_orders = [e for e in executors if hasattr(e, 'side') and e.side == TradeType.SELL]
            buy_filled = sum(1 for e in buy_orders if e in filled_executors)
            sell_filled = sum(1 for e in sell_orders if e in filled_executors)
            
            # 计算PnL和指标
            total_pnl = sum(float(e.net_pnl_quote) if hasattr(e, 'net_pnl_quote') and e.net_pnl_quote else 0 
                          for e in filled_executors)
            total_volume = sum(float(e.filled_amount_quote) for e in filled_executors)
            turnover_return = (total_pnl / total_volume * 100) if total_volume > 0 else 0
            
            # 计算多空订单盈亏
            buy_pnl = sum(float(e.net_pnl_quote) if hasattr(e, 'net_pnl_quote') and e.net_pnl_quote else 0 
                         for e in filled_executors if hasattr(e, 'side') and e.side == TradeType.BUY)
            sell_pnl = sum(float(e.net_pnl_quote) if hasattr(e, 'net_pnl_quote') and e.net_pnl_quote else 0 
                          for e in filled_executors if hasattr(e, 'side') and e.side == TradeType.SELL)
            
            # 计算挂撤单数量
            total_orders = len(executors)
            cancelled_orders = total_orders - len(filled_executors)
            
            # 计算日均交易额和日均收益
            duration_days = (end_ts - start_ts) / 86400
            daily_volume = total_volume / duration_days if duration_days > 0 else 0
            daily_return = total_pnl / duration_days if duration_days > 0 else 0
            
            # 计算最大持仓价值
            max_position_value = 0.0
            for executor in filled_executors:
                if hasattr(executor, 'filled_amount_quote') and executor.filled_amount_quote:
                    position_value = float(executor.filled_amount_quote)
                    max_position_value = max(max_position_value, position_value)
            
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
                'daily_return': daily_return,
                'max_position_value': max_position_value,
                'executors': executors,  # 保留executors用于后续分析
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


def generate_comprehensive_report(all_results: List[Dict], data_info_dict: Dict[str, Dict]) -> str:
    """生成综合报告"""
    report = []
    report.append("="*80)
    report.append("Backtest Results Summary")
    report.append("="*80)
    report.append("")
    
    # 数据信息
    report.append("Data Information:")
    report.append("-"*80)
    for trading_pair, info in data_info_dict.items():
        report.append(f"  {trading_pair}:")
        report.append(f"    Data Points: {info['data_points']:,}")
        report.append(f"    Time Range: {info['actual_start']} to {info['actual_end']}")
        report.append(f"    Resolution: {info['backtest_resolution']}")
    report.append("")
    
    # 结果汇总
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
    
    # 详细指标
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
        report.append(f"  Daily Return: ${result['daily_return']:,.2f}")
        report.append(f"  Max Position Value: ${result['max_position_value']:,.2f}")
        report.append(f"  Backtest Time: {result['elapsed_time']:.1f}s ({result['elapsed_time']/60:.1f}min)")
    
    report.append("")
    report.append("="*80)
    
    return "\n".join(report)


def main():
    """主函数"""
    print("="*80)
    print("Multi-Process Parallel Backtest")
    print("="*80)
    print(f"Trading Pairs: {', '.join(TRADING_PAIRS)}")
    print(f"Time Range: {START_DATE.strftime('%Y-%m-%d')} to {END_DATE.strftime('%Y-%m-%d')}")
    print(f"Base Resolution: {BACKTEST_RESOLUTION}")
    print(f"Backtest Resolution: {RESAMPLE_INTERVAL if RESAMPLE_INTERVAL else BACKTEST_RESOLUTION}")
    print(f"Multiprocessing: {USE_MULTIPROCESSING} (Jobs: {N_JOBS})")
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
                "candles_trading_pair": None,  # 将在运行时设置
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
                "candles_trading_pair": None,  # 将在运行时设置
                "interval": actual_resolution,
                "take_profit_order_type": OrderType.MARKET,
                "training_window": 60,
                "natr_length": 14,
                "atr_length": 10,
            }
        }
    }
    
    # 步骤1: 为每个品种准备数据（在主进程中）
    print("Step 1: Preparing data for all symbols...")
    print("-"*80)
    data_info_dict = {}
    for trading_pair in TRADING_PAIRS:
        df, info = prepare_data_for_symbol(trading_pair, start_ts, end_ts, actual_resolution)
        if df is not None:
            data_info_dict[trading_pair] = info
    print()
    
    if not data_info_dict:
        print("✗ No data available, exiting...")
        return
    
    # 步骤2: 生成所有回测任务（品种 × 策略）
    print("Step 2: Generating backtest tasks...")
    print("-"*80)
    tasks = []
    for trading_pair in TRADING_PAIRS:
        if trading_pair not in data_info_dict:
            continue
        for strategy_key, strategy_info in strategies.items():
            # 准备可序列化的参数
            params_dict = strategy_info['params'].copy()
            # 更新trading_pair参数
            if 'candles_trading_pair' in params_dict and params_dict['candles_trading_pair'] is None:
                params_dict['candles_trading_pair'] = trading_pair
            
            # 转换Decimal为字符串以便序列化
            serializable_params = {}
            for k, v in params_dict.items():
                if isinstance(v, Decimal):
                    serializable_params[k] = str(v)
                elif isinstance(v, list) and len(v) > 0:
                    if isinstance(v[0], Decimal):
                        serializable_params[k] = [str(x) for x in v]
                    elif isinstance(v[0], (int, float)):
                        # 保持原样（spreads等）
                        serializable_params[k] = v
                    else:
                        serializable_params[k] = v
                elif hasattr(v, 'name') and hasattr(v, 'value'):  # 枚举类型
                    # OrderType等枚举需要特殊处理
                    serializable_params[k] = f"{type(v).__name__}.{v.name}"
                else:
                    serializable_params[k] = v
            
            # 获取配置类名
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
                TRADING_FEE
            ))
            print(f"  Task: {trading_pair} - {strategy_info['name']}")
    print(f"Total tasks: {len(tasks)}")
    print()
    
    # 步骤3: 并行运行所有回测
    print("Step 3: Running backtests in parallel...")
    print("-"*80)
    start_time = time.time()
    
    if USE_MULTIPROCESSING and len(tasks) > 1:
        # 使用joblib多进程并行
        results = Parallel(n_jobs=N_JOBS, backend='multiprocessing', verbose=10)(
            delayed(run_single_backtest_sync)(*task) for task in tasks
        )
    else:
        # 串行运行（用于调试）
        results = [run_single_backtest_sync(*task) for task in tasks]
    
    total_time = time.time() - start_time
    print(f"\n✓ All backtests completed in {total_time:.1f}s ({total_time/60:.1f}min)")
    print()
    
    # 步骤4: 生成报告
    print("Step 4: Generating report...")
    print("-"*80)
    report = generate_comprehensive_report(results, data_info_dict)
    print(report)
    
    # 保存报告
    report_file = Path(__file__).parent / f"backtest_report_{START_DATE.strftime('%Y%m%d')}_{END_DATE.strftime('%Y%m%d')}.txt"
    report_file.write_text(report, encoding='utf-8')
    print(f"\n✓ Report saved to: {report_file}")
    
    # 保存详细结果（JSON）
    import json
    json_file = Path(__file__).parent / f"backtest_results_{START_DATE.strftime('%Y%m%d')}_{END_DATE.strftime('%Y%m%d')}.json"
    
    # 序列化结果（移除executors，因为不能序列化）
    serializable_results = []
    for result in results:
        serializable_result = {k: v for k, v in result.items() if k != 'executors'}
        serializable_results.append(serializable_result)
    
    json_data = {
        'start_date': START_DATE.strftime('%Y-%m-%d'),
        'end_date': END_DATE.strftime('%Y-%m-%d'),
        'trading_pairs': TRADING_PAIRS,
        'backtest_resolution': actual_resolution,
        'data_info': data_info_dict,
        'results': serializable_results,
        'total_time': total_time
    }
    
    json_file.write_text(json.dumps(json_data, indent=2, default=str), encoding='utf-8')
    print(f"✓ Detailed results saved to: {json_file}")


if __name__ == "__main__":
    # 设置multiprocessing启动方法（macOS需要）
    if sys.platform == 'darwin':
        multiprocessing.set_start_method('spawn', force=True)
    
    main()

