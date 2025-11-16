#!/usr/bin/env python3
"""
多品种回测脚本
回测区间: 2025-06-01 至 2025-11-09
品种: BTC, SOL, ETH, XRP, AVAX, DOT, MYX
"""

import asyncio
import sys
import time
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Dict, List

import pandas as pd

# 添加路径
sys.path.insert(0, '/Users/wilson/Desktop/tradingview-ai')

# 临时替换ccxt以支持本地数据
class FakeCCXT:
    pass
sys.modules['ccxt'] = FakeCCXT()

from src.data.sources.binance_public_data_manager import BinancePublicDataManager

# 添加hummingbot路径
sys.path.insert(0, '/Users/wilson/Desktop/mm_research/hummingbot')

from hummingbot.strategy_v2.backtesting.backtesting_engine_base import BacktestingEngineBase
from controllers.market_making.pmm_bar_portion import PMMBarPortionControllerConfig
from controllers.market_making.pmm_dynamic import PMMDynamicControllerConfig
from hummingbot.core.data_type.common import TradeType
from hummingbot.strategy_v2.executors.position_executor.data_types import OrderType, TripleBarrierConfig

# 导入本地数据提供器（需要从当前目录导入）
import importlib.util
backtest_local_path = Path(__file__).parent / "backtest_comparison_local.py"
spec = importlib.util.spec_from_file_location("backtest_comparison_local", backtest_local_path)
backtest_comparison_local = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backtest_comparison_local)
LocalBinanceDataProvider = backtest_comparison_local.LocalBinanceDataProvider
LocalBacktestingDataProvider = backtest_comparison_local.LocalBacktestingDataProvider

# 交易对列表
TRADING_PAIRS = [
    "BTC-USDT",
    "SOL-USDT", 
    "ETH-USDT",
    "XRP-USDT",
    "AVAX-USDT",
    "DOT-USDT",
    "MYX-USDT"
]

# 回测时间范围
START_DATE = datetime(2025, 6, 1)
END_DATE = datetime(2025, 11, 9)

def create_bp_config(trading_pair: str, total_amount: Decimal) -> PMMBarPortionControllerConfig:
    """创建PMM Bar Portion策略配置"""
    return PMMBarPortionControllerConfig(
        controller_name="pmm_bar_portion",
        connector_name="binance_perpetual",
        trading_pair=trading_pair,
        total_amount_quote=total_amount,
        buy_spreads=[0.01, 0.02],
        sell_spreads=[0.01, 0.02],
        buy_amounts_pct=[0.5, 0.5],
        sell_amounts_pct=[0.5, 0.5],
        candles_connector="binance_perpetual",
        candles_trading_pair=trading_pair,
        interval="1m",
        stop_loss=Decimal("0.03"),
        take_profit=Decimal("0.02"),
        time_limit=45 * 60,
    )

def create_macd_config(trading_pair: str, total_amount: Decimal) -> PMMDynamicControllerConfig:
    """创建PMM Dynamic (MACD)策略配置"""
    return PMMDynamicControllerConfig(
        controller_name="pmm_dynamic",
        connector_name="binance_perpetual",
        trading_pair=trading_pair,
        total_amount_quote=total_amount,
        buy_spreads=[0.01, 0.02],
        sell_spreads=[0.01, 0.02],
        buy_amounts_pct=[0.5, 0.5],
        sell_amounts_pct=[0.5, 0.5],
        candles_connector="binance_perpetual",
        candles_trading_pair=trading_pair,
        interval="1m",
        stop_loss=Decimal("0.03"),
        take_profit=Decimal("0.02"),
        time_limit=45 * 60,
    )

async def run_backtest(engine: BacktestingEngineBase, config, start_ts: int, end_ts: int, 
                      strategy_name: str, symbol: str) -> Dict:
    """运行单个策略的回测"""
    start_time = time.time()
    print(f"  [{symbol}] 开始回测 {strategy_name}...", flush=True)
    
    try:
        results = await engine.run_backtesting(
            controller_config=config,
            start=start_ts,
            end=end_ts,
            backtesting_resolution="1m",
            trade_cost=0.0004,
            show_progress=True  # 启用进度条
        )
        
        elapsed_time = time.time() - start_time
        
        if not results:
            print(f"  [{symbol}] ⚠️  {strategy_name} 无结果", flush=True)
            return None
        
        executors = results.get('executors', [])
        summary = results.get('results', {})
        
        filled = [e for e in executors if hasattr(e, 'filled_amount_quote') and float(e.filled_amount_quote) > 0]
        print(f"  [{symbol}] ✓ {strategy_name} 完成: {len(executors)} 个executor (成交: {len(filled)}) 耗时: {elapsed_time:.1f}秒", flush=True)
        
        return {
            'symbol': symbol,
            'strategy': strategy_name,
            'executors': executors,
            'summary': summary,
            'elapsed_time': elapsed_time,
        }
        
    except Exception as e:
        elapsed_time = time.time() - start_time
        print(f"  [{symbol}] ✗ {strategy_name} 回测失败: {e}", flush=True)
        import traceback
        traceback.print_exc()
        return None

async def run_symbol_backtest(symbol: str, start_date: datetime, end_date: datetime) -> Dict:
    """运行单个品种的回测"""
    print(f"\n{'='*80}")
    print(f"回测品种: {symbol}")
    print(f"时间范围: {start_date.strftime('%Y-%m-%d')} 至 {end_date.strftime('%Y-%m-%d')}")
    print(f"{'='*80}")
    
    # 转换时间戳
    start_ts = int(start_date.timestamp())
    end_ts = int(end_date.timestamp())
    
    # 初始化数据提供器
    print(f"\n[{symbol}] 初始化数据提供器...", flush=True)
    local_data_provider = LocalBinanceDataProvider()
    local_backtesting_provider = LocalBacktestingDataProvider(local_data_provider)
    local_backtesting_provider.update_backtesting_time(start_ts, end_ts)
    
    # 验证数据加载
    print(f"[{symbol}] 验证数据加载...", flush=True)
    data_start = time.time()
    test_df = local_data_provider.get_historical_candles(
        symbol=symbol,
        start_ts=start_ts,
        end_ts=end_ts,
        interval="1m"
    )
    data_elapsed = time.time() - data_start
    print(f"[{symbol}] ✓ 数据量: {len(test_df):,} 条K线 (加载耗时: {data_elapsed:.2f}秒)", flush=True)
    
    if len(test_df) == 0:
        print(f"[{symbol}] ✗ 数据加载失败，跳过", flush=True)
        return None
    
    # 创建策略配置
    print(f"[{symbol}] 创建策略配置...", flush=True)
    bp_config = create_bp_config(symbol, Decimal("10000"))
    macd_config = create_macd_config(symbol, Decimal("10000"))
    
    # 运行回测
    results = {}
    
    # PMM Bar Portion策略
    print(f"\n[{symbol}] [1/2] 运行PMM Bar Portion策略回测...", flush=True)
    engine_bp = BacktestingEngineBase()
    engine_bp.backtesting_data_provider = local_backtesting_provider
    bp_result = await run_backtest(engine_bp, bp_config, start_ts, end_ts, "PMM Bar Portion", symbol)
    if bp_result:
        results['bp'] = bp_result
    
    # PMM Dynamic (MACD)策略
    print(f"\n[{symbol}] [2/2] 运行PMM Dynamic (MACD)策略回测...", flush=True)
    engine_macd = BacktestingEngineBase()
    engine_macd.backtesting_data_provider = local_backtesting_provider
    macd_result = await run_backtest(engine_macd, macd_config, start_ts, end_ts, "PMM Dynamic", symbol)
    if macd_result:
        results['macd'] = macd_result
    
    return results

async def main():
    """主函数"""
    print("="*80)
    print("多品种回测分析")
    print(f"时间范围: {START_DATE.strftime('%Y-%m-%d')} 至 {END_DATE.strftime('%Y-%m-%d')}")
    print(f"品种: {', '.join(TRADING_PAIRS)}")
    print("="*80)
    
    all_results = {}
    total_start_time = time.time()
    
    # 逐个品种回测
    for symbol in TRADING_PAIRS:
        try:
            symbol_results = await run_symbol_backtest(symbol, START_DATE, END_DATE)
            if symbol_results:
                all_results[symbol] = symbol_results
        except Exception as e:
            print(f"\n[{symbol}] ✗ 回测过程出错: {e}", flush=True)
            import traceback
            traceback.print_exc()
            continue
    
    total_elapsed_time = time.time() - total_start_time
    
    # 保存结果
    print(f"\n{'='*80}")
    print("回测完成")
    print(f"总耗时: {total_elapsed_time/60:.1f} 分钟")
    print(f"成功回测品种数: {len(all_results)}")
    print("="*80)
    
    # 保存结果到文件
    output_file = Path(__file__).parent / f"multi_symbol_backtest_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    import json
    
    # 转换结果以便JSON序列化
    serializable_results = {}
    for symbol, results in all_results.items():
        serializable_results[symbol] = {}
        for strategy_key, result in results.items():
            if result:
                serializable_results[symbol][strategy_key] = {
                    'symbol': result.get('symbol'),
                    'strategy': result.get('strategy'),
                    'executor_count': len(result.get('executors', [])),
                    'filled_count': len([e for e in result.get('executors', []) 
                                       if hasattr(e, 'filled_amount_quote') and float(e.filled_amount_quote) > 0]),
                    'elapsed_time': result.get('elapsed_time'),
                    'summary': result.get('summary', {}),
                }
    
    with open(output_file, 'w') as f:
        json.dump(serializable_results, f, indent=2, default=str)
    
    print(f"\n结果已保存到: {output_file}")
    
    # 打印简要统计
    print("\n简要统计:")
    for symbol, results in all_results.items():
        print(f"\n{symbol}:")
        for strategy_key, result in results.items():
            if result:
                executors = result.get('executors', [])
                filled = [e for e in executors if hasattr(e, 'filled_amount_quote') and float(e.filled_amount_quote) > 0]
                print(f"  {result.get('strategy')}: {len(executors)} executors, {len(filled)} 成交, 耗时: {result.get('elapsed_time', 0):.1f}秒")

if __name__ == "__main__":
    asyncio.run(main())

