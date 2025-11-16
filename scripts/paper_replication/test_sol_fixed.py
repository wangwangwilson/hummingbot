#!/usr/bin/env python3
"""
测试修复后的SOL回测
时间区间: 2025-09-01 至 2025-11-01
"""

import asyncio
import sys
from datetime import datetime
from decimal import Decimal

sys.path.insert(0, '/Users/wilson/Desktop/tradingview-ai')

class FakeCCXT:
    pass
sys.modules['ccxt'] = FakeCCXT()

from src.data.sources.binance_public_data_manager import BinancePublicDataManager

sys.path.insert(0, '/Users/wilson/Desktop/mm_research/hummingbot')

from hummingbot.strategy_v2.backtesting.backtesting_engine_base import BacktestingEngineBase
from controllers.market_making.pmm_bar_portion import PMMBarPortionControllerConfig
from backtest_comparison_local import LocalBinanceDataProvider, LocalBacktestingDataProvider

# 回测配置
SYMBOL = "SOL-USDT"
START_DATE = datetime(2025, 9, 1)
END_DATE = datetime(2025, 11, 1)

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
        executor_refresh_time=300,  # 5分钟，给更多时间成交
    )

async def main():
    """主函数"""
    print("="*80)
    print(f"SOL回测测试 - 修复后")
    print(f"时间区间: {START_DATE.strftime('%Y-%m-%d')} 至 {END_DATE.strftime('%Y-%m-%d')}")
    print("="*80)
    print()
    
    # 初始化
    local_data_provider = LocalBinanceDataProvider()
    local_backtesting_provider = LocalBacktestingDataProvider(local_data_provider)
    
    start_ts = int(START_DATE.timestamp())
    end_ts = int(END_DATE.timestamp())
    local_backtesting_provider.update_backtesting_time(start_ts, end_ts)
    
    config = create_bp_config(SYMBOL, Decimal("10000"))
    
    # 创建引擎
    engine = BacktestingEngineBase()
    engine.backtesting_data_provider = local_backtesting_provider
    
    print("运行回测...")
    results = await engine.run_backtesting(
        controller_config=config,
        start=start_ts,
        end=end_ts,
        backtesting_resolution="1m",
        trade_cost=0.0004,
        show_progress=True
    )
    
    executors = results.get('executors', [])
    print()
    print(f"✓ 回测完成，生成 {len(executors)} 个executor")
    print()
    
    # 分析结果
    summary = engine.summarize_results(executors, total_amount_quote=10000)
    
    print("="*80)
    print("回测结果汇总")
    print("="*80)
    print()
    print(f"总Executor数: {summary['total_executors']}")
    print(f"有持仓Executor数: {summary['total_executors_with_position']}")
    print(f"成交Executor数: {summary['total_executors_with_position']}")
    print(f"总成交量: ${summary['total_volume']:.2f}")
    print(f"总盈亏: ${summary['net_pnl_quote']:.2f} ({summary['net_pnl']*100:.2f}%)")
    print(f"多单数: {summary['total_long']}")
    print(f"空单数: {summary['total_short']}")
    print(f"关闭类型: {summary['close_types']}")
    print(f"胜率: {summary['accuracy']*100:.2f}%")
    print(f"Sharpe比率: {summary['sharpe_ratio']:.4f}")
    print(f"最大回撤: ${summary['max_drawdown_usd']:.2f} ({summary['max_drawdown_pct']*100:.2f}%)")
    print()
    
    # 详细分析
    filled = [e for e in executors if float(e.filled_amount_quote) > 0]
    print(f"成交Executor详情:")
    print(f"  成交数量: {len(filled)}")
    if len(filled) > 0:
        print(f"  平均盈亏: ${sum(float(e.net_pnl_quote) for e in filled) / len(filled):.2f}")
        print(f"  平均盈亏%: {sum(float(e.net_pnl_pct) for e in filled) / len(filled)*100:.2f}%")
        print(f"  总成交量: ${sum(float(e.filled_amount_quote) for e in filled):.2f}")
        
        # 分析前5个成交的executor
        print()
        print("前5个成交Executor:")
        for i, executor in enumerate(filled[:5], 1):
            print(f"  Executor {i}:")
            print(f"    方向: {executor.side}")
            print(f"    成交数量: ${float(executor.filled_amount_quote):.2f}")
            print(f"    盈亏: ${float(executor.net_pnl_quote):.2f} ({float(executor.net_pnl_pct)*100:.2f}%)")
            print(f"    关闭类型: {executor.close_type}")
    print()

if __name__ == "__main__":
    asyncio.run(main())

