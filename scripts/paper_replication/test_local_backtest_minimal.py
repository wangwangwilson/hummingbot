#!/usr/bin/env python3
"""
最小化测试：使用少量本地zip数据验证回测功能
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

async def test_minimal_backtest():
    """使用少量数据测试回测"""
    print("="*80)
    print("最小化回测测试（使用本地zip数据）")
    print("="*80)
    
    # 1. 验证数据来源
    print("\n1. 验证数据来源...")
    from src.data.sources.binance_public_data_manager import BinancePublicDataManager
    manager = BinancePublicDataManager()
    print(f"   ✓ 数据目录: {manager.data_dir}")
    print(f"   ✓ 数据来源: 本地zip文件")
    
    # 2. 测试数据加载（使用2小时数据）
    print("\n2. 测试数据加载（2小时数据）...")
    
    # 使用2024-11-11的完整一天数据（确保有足够数据）
    start_date = date(2024, 11, 11)
    end_date = date(2024, 11, 11)
    
    # 从manager获取实际数据范围
    test_df_raw = manager.get_klines_data('SOLUSDT', start_date, end_date, check_gaps=False)
    
    if test_df_raw.empty:
        print("   ✗ 无法从本地zip文件读取数据")
        return False
    
    # 使用实际数据的时间范围（前2小时）
    start_dt = test_df_raw.index.min()
    end_dt = start_dt + pd.Timedelta(hours=2)  # 2小时数据
    start_ts = int(start_dt.timestamp())
    end_ts = int(end_dt.timestamp())
    
    print(f"   ✓ 原始数据: {len(test_df_raw)} 条K线")
    print(f"   ✓ 时间范围: {start_dt} 至 {end_dt}")
    
    # 使用LocalBinanceDataProvider获取数据
    local_data_provider = LocalBinanceDataProvider()
    test_df = local_data_provider.get_historical_candles(
        symbol="SOL-USDT",
        start_ts=start_ts,
        end_ts=end_ts,
        interval="1m"
    )
    
    print(f"   ✓ 数据量: {len(test_df)} 条K线")
    if len(test_df) == 0:
        print("   ✗ 数据加载失败")
        return False
    
    print(f"   ✓ 时间范围: {datetime.fromtimestamp(test_df['timestamp'].min())} 至 {datetime.fromtimestamp(test_df['timestamp'].max())}")
    
    # 3. 初始化回测数据提供器
    print("\n3. 初始化回测数据提供器...")
    local_backtesting_provider = LocalBacktestingDataProvider(local_data_provider)
    local_backtesting_provider.update_backtesting_time(start_ts, end_ts)
    print("   ✓ 初始化完成")
    
    # 4. 创建策略配置
    print("\n4. 创建策略配置...")
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
        time_limit=30 * 60,  # 30分钟
    )
    print("   ✓ 配置创建成功")
    
    # 5. 运行回测
    print("\n5. 运行回测...")
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
        summary = results.get('summary', {})
        
        print(f"   ✓ 回测完成")
        print(f"   - 生成executor: {len(executors)} 个")
        
        # 检查成交情况
        filled = [e for e in executors if hasattr(e, 'filled_amount_quote') and float(e.filled_amount_quote) > 0]
        print(f"   - 成交executor: {len(filled)}/{len(executors)}")
        
        if summary:
            print(f"\n   回测摘要:")
            print(f"   - 总盈亏: ${summary.get('net_pnl_quote', 0):.2f}")
            print(f"   - 总盈亏%: {summary.get('net_pnl', 0)*100:.2f}%")
            print(f"   - Sharpe比率: {summary.get('sharpe_ratio', 0):.4f}")
            print(f"   - 最大回撤%: {summary.get('max_drawdown_pct', 0)*100:.2f}%")
            print(f"   - 胜率: {summary.get('accuracy', 0)*100:.2f}%")
        
        if len(filled) > 0:
            total_pnl = sum(float(e.net_pnl_quote) for e in filled)
            print(f"\n   ✓ 回测成功，有成交！")
            print(f"   - 总盈亏: ${total_pnl:.2f}")
            
            # 显示前3个成交的executor
            print(f"\n   前3个成交executor:")
            for i, e in enumerate(filled[:3], 1):
                print(f"     Executor {i}: PnL=${float(e.net_pnl_quote):.2f}, Amount=${float(e.filled_amount_quote):.2f}")
            
            return True
        else:
            print(f"   ⚠️  回测完成但无成交（可能是时间范围太短或价格未触发）")
            return len(executors) > 0  # 至少生成了executor
            
    except Exception as e:
        print(f"   ✗ 回测失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    import pandas as pd
    success = asyncio.run(test_minimal_backtest())
    print(f"\n{'='*80}")
    if success:
        print("✓ 测试通过！")
    else:
        print("✗ 测试失败")
    print(f"{'='*80}")
    sys.exit(0 if success else 1)

