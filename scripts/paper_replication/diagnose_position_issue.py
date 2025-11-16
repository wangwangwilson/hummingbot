#!/usr/bin/env python3
"""
全面诊断仓位更新问题
1. 检查数据加载是否完整
2. 检查executor创建是否分布均匀
3. 检查executor成交情况
4. 检查仓位变化
"""

import asyncio
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path
import pandas as pd
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
from hummingbot.strategy_v2.executors.position_executor.data_types import OrderType
from hummingbot.core.data_type.common import TradeType

# Import local data manager
from backtest_comparison_local import LocalBinanceDataProvider, LocalBacktestingDataProvider

# Test parameters
TRADING_PAIR = "BTC-USDT"
START_DATE = datetime(2025, 1, 1)
END_DATE = datetime(2025, 1, 5)  # 测试5天
INITIAL_PORTFOLIO_USD = 10000
TRADING_FEE = 0.0004
BACKTEST_RESOLUTION = "1m"


async def diagnose_all():
    """全面诊断"""
    print("="*80)
    print("全面诊断仓位更新问题")
    print("="*80)
    print(f"交易对: {TRADING_PAIR}")
    print(f"时间范围: {START_DATE.strftime('%Y-%m-%d')} 到 {END_DATE.strftime('%Y-%m-%d')}")
    print()
    
    start_ts = int(START_DATE.timestamp())
    end_ts = int(END_DATE.timestamp())
    
    # ========== 1. 检查数据加载 ==========
    print("="*80)
    print("1. 检查数据加载")
    print("="*80)
    
    local_data_provider = LocalBinanceDataProvider()
    df = local_data_provider.get_historical_candles(
        symbol=TRADING_PAIR,
        start_ts=start_ts,
        end_ts=end_ts,
        interval=BACKTEST_RESOLUTION
    )
    
    print(f"请求时间范围: {START_DATE} 到 {END_DATE}")
    print(f"预期时长: {(end_ts - start_ts) / 86400:.1f} 天")
    print(f"预期数据量: {(end_ts - start_ts) / 60:.0f} 条 (1分钟)")
    print()
    print(f"实际数据量: {len(df):,} 条")
    if len(df) > 0:
        first_ts = df['timestamp'].iloc[0]
        last_ts = df['timestamp'].iloc[-1]
        first_dt = datetime.fromtimestamp(first_ts)
        last_dt = datetime.fromtimestamp(last_ts)
        print(f"实际时间范围: {first_dt} 到 {last_dt}")
        print(f"实际时长: {(last_ts - first_ts) / 86400:.1f} 天")
        print()
        
        # 检查数据连续性
        time_diff = df['timestamp'].diff()
        gaps = time_diff[time_diff > 120]  # 超过2分钟的间隔
        if len(gaps) > 0:
            print(f"⚠ 发现 {len(gaps)} 个数据间隔 > 2分钟")
            for idx in gaps.index[:5]:  # 只显示前5个
                gap_time = datetime.fromtimestamp(df.loc[idx, 'timestamp'])
                print(f"  {gap_time}: 间隔 {time_diff.loc[idx]:.0f} 秒")
        else:
            print(f"✓ 数据连续，无明显间隔")
        print()
        
        # 数据覆盖率
        coverage = (last_ts - first_ts) / (end_ts - start_ts) * 100
        print(f"数据覆盖率: {coverage:.1f}%")
        if coverage < 90:
            print(f"  ⚠ 数据覆盖率不足90%，可能影响回测结果")
        print()
    else:
        print("✗ 未加载到数据！")
        return
    
    # ========== 2. 运行回测 ==========
    print("="*80)
    print("2. 运行回测")
    print("="*80)
    
    local_backtesting_provider = LocalBacktestingDataProvider(local_data_provider)
    local_backtesting_provider.update_backtesting_time(start_ts, end_ts)
    
    # 缩短executor生命周期，让它们更频繁地创建
    config = PMMBarPortionControllerConfig(
        controller_name="pmm_bar_portion",
        connector_name="binance_perpetual",
        trading_pair=TRADING_PAIR,
        total_amount_quote=Decimal(str(INITIAL_PORTFOLIO_USD)),
        buy_spreads=[0.005, 0.01],  # 更小的spread，增加成交概率
        sell_spreads=[0.005, 0.01],
        buy_amounts_pct=[Decimal("0.5"), Decimal("0.5")],
        sell_amounts_pct=[Decimal("0.5"), Decimal("0.5")],
        stop_loss=Decimal("0.01"),
        take_profit=Decimal("0.005"),
        time_limit=600,  # 缩短到10分钟
        executor_refresh_time=300,  # 5分钟refresh
        take_profit_order_type=OrderType.MARKET,
        candles_connector="binance_perpetual",
        candles_trading_pair=TRADING_PAIR,
        interval=BACKTEST_RESOLUTION,
    )
    
    # Initialize candles feed
    candles_config = CandlesConfig(
        connector=config.candles_connector,
        trading_pair=config.candles_trading_pair,
        interval=config.interval,
        max_records=100000
    )
    await local_backtesting_provider.initialize_candles_feed([candles_config])
    
    # Run backtest
    engine = BacktestingEngineBase()
    engine.backtesting_data_provider = local_backtesting_provider
    
    print("运行回测...")
    result = await engine.run_backtesting(
        controller_config=config,
        start=start_ts,
        end=end_ts,
        backtesting_resolution=BACKTEST_RESOLUTION,
        trade_cost=Decimal(str(TRADING_FEE)),
        show_progress=True
    )
    
    if not result or 'executors' not in result:
        print("✗ 回测失败")
        return
    
    executors = result['executors']
    print(f"\n总Executors: {len(executors)}")
    
    # ========== 3. 分析Executor分布 ==========
    print("\n" + "="*80)
    print("3. 分析Executor时间分布")
    print("="*80)
    
    # 按创建时间分组
    executor_by_hour = defaultdict(lambda: {'total': 0, 'filled': 0, 'buy': 0, 'sell': 0})
    filled_executors = []
    
    for executor in executors:
        if hasattr(executor, 'config') and hasattr(executor.config, 'timestamp'):
            ts = executor.config.timestamp
            dt = datetime.fromtimestamp(ts)
            hour_key = dt.strftime('%Y-%m-%d %H:00')
            
            executor_by_hour[hour_key]['total'] += 1
            
            # 检查是否成交
            is_filled = (
                hasattr(executor, 'filled_amount_quote') and 
                executor.filled_amount_quote and 
                float(executor.filled_amount_quote) > 0
            )
            
            if is_filled:
                executor_by_hour[hour_key]['filled'] += 1
                filled_executors.append(executor)
                
                # 统计多空
                side = None
                if hasattr(executor, 'side'):
                    side = executor.side
                elif hasattr(executor, 'config') and hasattr(executor.config, 'side'):
                    side = executor.config.side
                
                if side == TradeType.BUY:
                    executor_by_hour[hour_key]['buy'] += 1
                elif side == TradeType.SELL:
                    executor_by_hour[hour_key]['sell'] += 1
    
    print(f"总Executors: {len(executors)}")
    print(f"已成交Executors: {len(filled_executors)} ({len(filled_executors)/len(executors)*100:.1f}%)")
    print()
    
    # 按小时显示分布
    print("按小时分布:")
    print(f"{'时间':<18} {'总数':<8} {'成交':<8} {'Buy':<6} {'Sell':<6} {'成交率':<8}")
    print("-" * 60)
    for hour_key in sorted(executor_by_hour.keys()):
        stats = executor_by_hour[hour_key]
        fill_rate = stats['filled'] / stats['total'] * 100 if stats['total'] > 0 else 0
        print(f"{hour_key:<18} {stats['total']:<8} {stats['filled']:<8} {stats['buy']:<6} {stats['sell']:<6} {fill_rate:<8.1f}%")
    
    # ========== 4. 分析仓位变化 ==========
    print("\n" + "="*80)
    print("4. 分析仓位变化")
    print("="*80)
    
    if len(filled_executors) == 0:
        print("⚠ 没有已成交的executors，无法分析仓位")
        return
    
    # 按时间排序
    filled_executors_sorted = sorted(
        filled_executors,
        key=lambda e: e.config.timestamp if hasattr(e, 'config') else 0
    )
    
    print(f"\n前10个成交的executors:")
    print(f"{'时间':<20} {'方向':<6} {'成交额':<15} {'PnL':<15}")
    print("-" * 60)
    
    for i, executor in enumerate(filled_executors_sorted[:10]):
        dt = datetime.fromtimestamp(executor.config.timestamp)
        side = 'BUY' if executor.side == TradeType.BUY else 'SELL'
        filled_amt = float(executor.filled_amount_quote) if executor.filled_amount_quote else 0
        pnl = float(executor.net_pnl_quote) if hasattr(executor, 'net_pnl_quote') and executor.net_pnl_quote else 0
        print(f"{dt.strftime('%Y-%m-%d %H:%M:%S'):<20} {side:<6} ${filled_amt:<14.2f} ${pnl:<14.2f}")
    
    # 计算累计仓位
    print(f"\n累计统计:")
    total_buy = sum(1 for e in filled_executors if e.side == TradeType.BUY)
    total_sell = sum(1 for e in filled_executors if e.side == TradeType.SELL)
    total_pnl = sum(float(e.net_pnl_quote) if hasattr(e, 'net_pnl_quote') and e.net_pnl_quote else 0 for e in filled_executors)
    
    print(f"  BUY订单: {total_buy}")
    print(f"  SELL订单: {total_sell}")
    print(f"  总PnL: ${total_pnl:.2f}")
    print()
    
    # 检查多空是否交替
    if total_buy > 0 and total_sell > 0:
        print(f"✓ 多空交替正常 (Buy: {total_buy}, Sell: {total_sell})")
    else:
        print(f"⚠ 缺少多空交替 (Buy: {total_buy}, Sell: {total_sell})")


if __name__ == "__main__":
    asyncio.run(diagnose_all())

