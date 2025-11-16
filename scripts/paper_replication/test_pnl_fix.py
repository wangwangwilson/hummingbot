#!/usr/bin/env python3
"""
测试盈亏计算修复
验证修复后的盈亏计算是否正确
"""

import asyncio
import sys
from datetime import datetime, timedelta
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

# 配置 - 使用1天数据快速测试
SYMBOL = "SOL-USDT"
END_DATE = datetime(2025, 11, 1)
START_DATE = END_DATE - timedelta(days=1)

async def test_pnl_calculation():
    """测试盈亏计算"""
    print("="*80)
    print("测试盈亏计算修复")
    print("="*80)
    print()
    
    local_data_provider = LocalBinanceDataProvider()
    local_backtesting_provider = LocalBacktestingDataProvider(local_data_provider)
    
    start_ts = int(START_DATE.timestamp())
    end_ts = int(END_DATE.timestamp())
    local_backtesting_provider.update_backtesting_time(start_ts, end_ts)
    
    config = PMMBarPortionControllerConfig(
        controller_name="pmm_bar_portion",
        connector_name="binance_perpetual",
        trading_pair=SYMBOL,
        total_amount_quote=Decimal("10000"),
        buy_spreads=[1.0, 2.0],
        sell_spreads=[1.0, 2.0],
        buy_amounts_pct=[0.5, 0.5],
        sell_amounts_pct=[0.5, 0.5],
        candles_connector="binance_perpetual",
        candles_trading_pair=SYMBOL,
        interval="1m",
        stop_loss=Decimal("0.03"),
        take_profit=Decimal("0.02"),
        time_limit=30 * 60,
        executor_refresh_time=300,
    )
    
    engine = BacktestingEngineBase()
    engine.backtesting_data_provider = local_backtesting_provider
    
    print("运行回测...")
    results = await engine.run_backtesting(
        controller_config=config,
        start=start_ts,
        end=end_ts,
        backtesting_resolution="1m",
        trade_cost=0.0004,
        show_progress=False
    )
    
    executors = results.get('executors', [])
    print(f"✓ 回测完成，生成 {len(executors)} 个executor")
    print()
    
    # 分析成交的executor
    filled = [e for e in executors if float(e.filled_amount_quote) > 0]
    print(f"成交Executor数: {len(filled)}")
    print()
    
    if len(filled) == 0:
        print("❌ 没有成交的executor")
        return
    
    # 详细分析每个成交的executor
    print("="*80)
    print("成交Executor盈亏分析")
    print("="*80)
    print()
    
    total_pnl = 0.0
    for i, executor in enumerate(filled, 1):
        print(f"Executor {i}:")
        print(f"  方向: {executor.side}")
        print(f"  成交数量: ${float(executor.filled_amount_quote):.2f}")
        print(f"  盈亏: ${float(executor.net_pnl_quote):.2f} ({float(executor.net_pnl_pct)*100:.4f}%)")
        
        # 获取entry_price和exit_price
        if hasattr(executor, 'config') and executor.config:
            ec = executor.config
            entry_price = float(ec.entry_price)
            print(f"  挂单价格(entry_price): ${entry_price:.4f}")
            
            # 从custom_info获取退出价格
            custom_info = executor.custom_info
            if 'close_price' in custom_info:
                exit_price = custom_info['close_price']
                print(f"  退出价格(close_price): ${exit_price:.4f}")
                
                # 计算理论盈亏（不考虑交易成本）
                if executor.side.name == 'BUY':
                    theoretical_pnl_pct = (exit_price - entry_price) / entry_price
                else:
                    theoretical_pnl_pct = (entry_price - exit_price) / entry_price
                
                # 扣除交易成本（开仓和平仓各一次）
                trade_cost = 0.0004
                net_theoretical_pnl_pct = theoretical_pnl_pct - (2 * trade_cost)
                
                print(f"  理论盈亏% (不含成本): {theoretical_pnl_pct*100:.4f}%")
                print(f"  理论盈亏% (含成本): {net_theoretical_pnl_pct*100:.4f}%")
                print(f"  实际盈亏%: {float(executor.net_pnl_pct)*100:.4f}%")
                
                diff = abs(net_theoretical_pnl_pct - float(executor.net_pnl_pct))
                if diff < 0.0001:  # 允许小的浮点误差
                    print(f"  ✓ 盈亏计算正确（差异: {diff*100:.4f}%）")
                else:
                    print(f"  ⚠️  盈亏计算可能有问题（差异: {diff*100:.4f}%）")
                    print(f"     理论: {net_theoretical_pnl_pct*100:.4f}%, 实际: {float(executor.net_pnl_pct)*100:.4f}%")
        
        total_pnl += float(executor.net_pnl_quote)
        print()
    
    print("="*80)
    print("总结")
    print("="*80)
    print(f"总盈亏: ${total_pnl:.2f}")
    if abs(total_pnl) < 0.01:
        print("⚠️  总盈亏接近0，可能仍有问题")
    else:
        print("✓ 总盈亏不为0，修复可能生效")
    print()

if __name__ == "__main__":
    asyncio.run(test_pnl_calculation())

