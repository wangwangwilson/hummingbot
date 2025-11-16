#!/usr/bin/env python3
"""
BTC回测快速测试（使用1个月数据验证功能）
"""

import asyncio
import sys
import time
from pathlib import Path
from datetime import datetime, date
from decimal import Decimal

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
tradingview_ai_path = Path("/Users/wilson/Desktop/tradingview-ai")
sys.path.insert(0, str(tradingview_ai_path))

class FakeCCXT:
    pass
sys.modules['ccxt'] = FakeCCXT()

# 导入test_btc_backtest_analysis.py中的函数
from test_btc_backtest_analysis import (
    create_bp_config, create_macd_config, 
    analyze_executors, analyze_position_distribution,
    run_backtest
)
from hummingbot.strategy_v2.backtesting.backtesting_engine_base import BacktestingEngineBase
from scripts.paper_replication.backtest_comparison_local import LocalBinanceDataProvider, LocalBacktestingDataProvider

async def main():
    """快速测试（1个月数据）"""
    print("="*80)
    print("BTC回测快速测试 - 2025-01-01 至 2025-01-31 (1个月)")
    print("="*80)
    
    # 使用1个月数据
    start_date = date(2025, 1, 1)
    end_date = date(2025, 1, 31)
    start_ts = int(datetime.combine(start_date, datetime.min.time()).timestamp())
    end_ts = int(datetime.combine(end_date, datetime.min.time()).timestamp())
    
    print(f"\n时间范围: {start_date} 至 {end_date}")
    
    # 初始化
    local_data_provider = LocalBinanceDataProvider()
    local_backtesting_provider = LocalBacktestingDataProvider(local_data_provider)
    local_backtesting_provider.update_backtesting_time(start_ts, end_ts)
    
    # 验证数据
    test_df = local_data_provider.get_historical_candles(
        symbol="BTC-USDT",
        start_ts=start_ts,
        end_ts=end_ts,
        interval="1m"
    )
    print(f"✓ 数据量: {len(test_df):,} 条K线")
    
    if len(test_df) == 0:
        print("✗ 数据加载失败")
        return
    
    # 创建配置
    bp_config = create_bp_config("BTC-USDT", Decimal("10000"))
    macd_config = create_macd_config("BTC-USDT", Decimal("10000"))
    
    # 运行回测
    print("\n开始回测...")
    total_start = time.time()
    
    print("\n[1/2] PMM Bar Portion...")
    engine_bp = BacktestingEngineBase()
    engine_bp.backtesting_data_provider = local_backtesting_provider
    bp_results, bp_time = await run_backtest(engine_bp, bp_config, start_ts, end_ts, "BP")
    
    print("\n[2/2] PMM Dynamic...")
    engine_macd = BacktestingEngineBase()
    engine_macd.backtesting_data_provider = local_backtesting_provider
    macd_results, macd_time = await run_backtest(engine_macd, macd_config, start_ts, end_ts, "MACD")
    
    total_time = time.time() - total_start
    
    # 分析结果
    if bp_results and macd_results:
        print("\n" + "="*80)
        print("快速测试结果")
        print("="*80)
        
        bp_analysis = analyze_executors(bp_results['executors'], "BP")
        macd_analysis = analyze_executors(macd_results['executors'], "MACD")
        
        print(f"\nPMM Bar Portion:")
        print(f"  总Executor: {bp_analysis['total']}")
        print(f"  成交: {bp_analysis['filled']}")
        print(f"  多单盈亏: ${bp_analysis['long_pnl']:.2f}")
        print(f"  空单盈亏: ${bp_analysis['short_pnl']:.2f}")
        
        print(f"\nPMM Dynamic:")
        print(f"  总Executor: {macd_analysis['total']}")
        print(f"  成交: {macd_analysis['filled']}")
        print(f"  多单盈亏: ${macd_analysis['long_pnl']:.2f}")
        print(f"  空单盈亏: ${macd_analysis['short_pnl']:.2f}")
        
        print(f"\n耗时:")
        print(f"  BP: {bp_time:.1f}秒")
        print(f"  MACD: {macd_time:.1f}秒")
        print(f"  总计: {total_time:.1f}秒")
        
        # 估算完整回测时间
        data_points = len(test_df)
        time_per_point = total_time / 2 / data_points
        full_data_points = 449280  # 完整数据量
        estimated_full_time = time_per_point * full_data_points * 2
        print(f"\n估算完整回测时间:")
        print(f"  当前数据: {data_points:,} 条K线")
        print(f"  完整数据: {full_data_points:,} 条K线")
        print(f"  预计时间: {estimated_full_time/60:.1f}分钟 ({estimated_full_time/3600:.1f}小时)")

if __name__ == "__main__":
    asyncio.run(main())

