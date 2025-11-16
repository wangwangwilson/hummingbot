#!/usr/bin/env python3
"""
测试SOL回测，验证数据加载和回测是否正常
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime, date
from decimal import Decimal

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
tradingview_ai_path = Path("/Users/wilson/Desktop/tradingview-ai")
sys.path.insert(0, str(tradingview_ai_path))

# 临时禁用ccxt
class FakeCCXT:
    pass
sys.modules['ccxt'] = FakeCCXT()

from hummingbot.strategy_v2.backtesting.backtesting_engine_base import BacktestingEngineBase
from controllers.market_making.pmm_bar_portion import PMMBarPortionControllerConfig
from scripts.paper_replication.backtest_comparison_local import LocalBinanceDataProvider, LocalBacktestingDataProvider

async def test_sol_backtest():
    """测试SOL回测"""
    print("="*80)
    print("SOL-USDT 回测测试（使用本地数据）")
    print("="*80)
    
    # 初始化数据提供器
    local_data_provider = LocalBinanceDataProvider()
    local_backtesting_provider = LocalBacktestingDataProvider(local_data_provider)
    
    # 设置时间范围
    start_date = date(2024, 11, 11)
    end_date = date(2024, 11, 12)
    start_ts = int(datetime.combine(start_date, datetime.min.time()).timestamp())
    end_ts = int(datetime.combine(end_date, datetime.min.time()).timestamp())
    
    local_backtesting_provider.update_backtesting_time(start_ts, end_ts)
    
    # 验证数据加载
    print(f"\n1. 验证数据加载...")
    test_df = local_data_provider.get_historical_candles(
        symbol="SOL-USDT",
        start_ts=start_ts,
        end_ts=end_ts,
        interval="1m"
    )
    
    print(f"   数据量: {len(test_df)} 条K线")
    if len(test_df) == 0:
        print("   ✗ 数据加载失败")
        return False
    
    print(f"   ✓ 数据加载成功")
    if isinstance(test_df.index, pd.Index):
        print(f"   Timestamp索引范围: {test_df.index.min()} 至 {test_df.index.max()}")
    else:
        print(f"   Timestamp列范围: {test_df['timestamp'].min()} 至 {test_df['timestamp'].max()}")
    
    # 创建策略配置
    print(f"\n2. 创建策略配置...")
    config = PMMBarPortionControllerConfig(
        controller_name="pmm_bar_portion",
        connector_name="binance_perpetual",
        trading_pair="SOL-USDT",
        total_amount_quote=Decimal("1000"),
        buy_spreads=[0.01, 0.02],
        sell_spreads=[0.01, 0.02],
        buy_amounts_pct=[0.5, 0.5],
        sell_amounts_pct=[0.5, 0.5],
        candles_connector="binance_perpetual",
        candles_trading_pair="SOL-USDT",
        interval="1m",
        stop_loss=Decimal("0.03"),
        take_profit=Decimal("0.02"),
        time_limit=45 * 60,
    )
    print(f"   ✓ 配置创建成功")
    
    # 运行回测
    print(f"\n3. 运行回测...")
    engine = BacktestingEngineBase()
    engine.backtesting_data_provider = local_backtesting_provider
    
    try:
        results = await engine.run_backtesting(
            controller_config=config,
            start=start_ts,
            end=end_ts,
            backtesting_resolution="1m",
            trade_cost=0.0004
        )
        
        if not results:
            print("   ✗ 回测失败：无结果")
            return False
        
        executors = results.get('executors', [])
        print(f"   ✓ 回测完成，生成 {len(executors)} 个executor")
        
        # 检查成交情况
        filled = [e for e in executors if hasattr(e, 'filled_amount_quote') and float(e.filled_amount_quote) > 0]
        print(f"   成交executor: {len(filled)}/{len(executors)}")
        
        if len(filled) > 0:
            total_pnl = sum(float(e.net_pnl_quote) for e in filled)
            print(f"   总盈亏: ${total_pnl:.2f}")
            print(f"   ✓ 回测成功，有成交！")
            
            # 显示前3个成交的executor
            print(f"\n   前3个成交executor:")
            for i, e in enumerate(filled[:3], 1):
                print(f"     Executor {i}: PnL=${float(e.net_pnl_quote):.2f}, Amount=${float(e.filled_amount_quote):.2f}")
            
            return True
        else:
            print(f"   ⚠️  回测完成但无成交")
            return False
            
    except Exception as e:
        print(f"   ✗ 回测失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    import pandas as pd
    success = asyncio.run(test_sol_backtest())
    sys.exit(0 if success else 1)

