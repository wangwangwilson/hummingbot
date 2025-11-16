#!/usr/bin/env python3
"""
测试修复后的仓位分布
使用更长时间（1个月）验证executors是否均匀分布
"""

import asyncio
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path
import pandas as pd
from collections import defaultdict
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

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
START_DATE = datetime(2025, 10, 1)
END_DATE = datetime(2025, 11, 1)  # 1个月
INITIAL_PORTFOLIO_USD = 10000
TRADING_FEE = 0.0004
BACKTEST_RESOLUTION = "1m"


async def test_position_distribution():
    """测试仓位分布"""
    print("="*80)
    print("测试修复后的仓位分布（1个月）")
    print("="*80)
    print(f"交易对: {TRADING_PAIR}")
    print(f"时间范围: {START_DATE.strftime('%Y-%m-%d')} 到 {END_DATE.strftime('%Y-%m-%d')}")
    print()
    
    start_ts = int(START_DATE.timestamp())
    end_ts = int(END_DATE.timestamp())
    
    # Initialize data provider
    local_data_provider = LocalBinanceDataProvider()
    local_backtesting_provider = LocalBacktestingDataProvider(local_data_provider)
    local_backtesting_provider.update_backtesting_time(start_ts, end_ts)
    
    # Create config with shorter lifecycle
    config = PMMBarPortionControllerConfig(
        controller_name="pmm_bar_portion",
        connector_name="binance_perpetual",
        trading_pair=TRADING_PAIR,
        total_amount_quote=Decimal(str(INITIAL_PORTFOLIO_USD)),
        buy_spreads=[0.003, 0.006],  # 更小的spread
        sell_spreads=[0.003, 0.006],
        buy_amounts_pct=[Decimal("0.5"), Decimal("0.5")],
        sell_amounts_pct=[Decimal("0.5"), Decimal("0.5")],
        stop_loss=Decimal("0.01"),
        take_profit=Decimal("0.005"),
        time_limit=600,  # 10分钟
        executor_refresh_time=300,  # 5分钟
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
    filled_executors = [
        e for e in executors 
        if hasattr(e, 'filled_amount_quote') and e.filled_amount_quote and float(e.filled_amount_quote) > 0
    ]
    
    print(f"\n{'='*80}")
    print("回测结果统计")
    print(f"{'='*80}")
    print(f"总Executors: {len(executors):,}")
    print(f"已成交Executors: {len(filled_executors):,} ({len(filled_executors)/len(executors)*100:.1f}%)")
    
    # 按天统计
    executor_by_day = defaultdict(lambda: {'total': 0, 'filled': 0, 'buy': 0, 'sell': 0})
    
    for executor in executors:
        if hasattr(executor, 'config') and hasattr(executor.config, 'timestamp'):
            ts = executor.config.timestamp
            dt = datetime.fromtimestamp(ts)
            day_key = dt.strftime('%Y-%m-%d')
            
            executor_by_day[day_key]['total'] += 1
            
            is_filled = (
                hasattr(executor, 'filled_amount_quote') and 
                executor.filled_amount_quote and 
                float(executor.filled_amount_quote) > 0
            )
            
            if is_filled:
                executor_by_day[day_key]['filled'] += 1
                
                side = None
                if hasattr(executor, 'side'):
                    side = executor.side
                elif hasattr(executor, 'config') and hasattr(executor.config, 'side'):
                    side = executor.config.side
                
                if side == TradeType.BUY:
                    executor_by_day[day_key]['buy'] += 1
                elif side == TradeType.SELL:
                    executor_by_day[day_key]['sell'] += 1
    
    print(f"\n按天统计:")
    print(f"{'日期':<12} {'总数':<8} {'成交':<8} {'Buy':<6} {'Sell':<6} {'成交率':<8}")
    print("-" * 60)
    for day_key in sorted(executor_by_day.keys()):
        stats = executor_by_day[day_key]
        fill_rate = stats['filled'] / stats['total'] * 100 if stats['total'] > 0 else 0
        print(f"{day_key:<12} {stats['total']:<8} {stats['filled']:<8} {stats['buy']:<6} {stats['sell']:<6} {fill_rate:<8.1f}%")
    
    # 计算PnL
    total_pnl = sum(
        float(e.net_pnl_quote) if hasattr(e, 'net_pnl_quote') and e.net_pnl_quote else 0 
        for e in filled_executors
    )
    total_buy = sum(1 for e in filled_executors if e.side == TradeType.BUY)
    total_sell = sum(1 for e in filled_executors if e.side == TradeType.SELL)
    
    print(f"\n累计统计:")
    print(f"  BUY订单: {total_buy:,}")
    print(f"  SELL订单: {total_sell:,}")
    print(f"  总PnL: ${total_pnl:,.2f}")
    print(f"  收益率: {total_pnl/INITIAL_PORTFOLIO_USD*100:.2f}%")
    
    # 绘制时间分布图
    print(f"\n{'='*80}")
    print("生成可视化图表...")
    print(f"{'='*80}")
    
    # 准备数据
    days = sorted(executor_by_day.keys())
    total_counts = [executor_by_day[day]['total'] for day in days]
    filled_counts = [executor_by_day[day]['filled'] for day in days]
    buy_counts = [executor_by_day[day]['buy'] for day in days]
    sell_counts = [executor_by_day[day]['sell'] for day in days]
    
    # 创建图表
    fig, axes = plt.subplots(2, 2, figsize=(16, 10))
    fig.suptitle(f'{TRADING_PAIR} Position Distribution Analysis\n{START_DATE.strftime("%Y-%m-%d")} to {END_DATE.strftime("%Y-%m-%d")}', 
                 fontsize=14, fontweight='bold')
    
    # 1. Executor创建数量
    ax1 = axes[0, 0]
    ax1.bar(range(len(days)), total_counts, alpha=0.7, label='Total')
    ax1.bar(range(len(days)), filled_counts, alpha=0.7, label='Filled')
    ax1.set_title('Daily Executor Count', fontweight='bold')
    ax1.set_xlabel('Date')
    ax1.set_ylabel('Count')
    ax1.set_xticks(range(0, len(days), max(1, len(days)//10)))
    ax1.set_xticklabels([days[i] for i in range(0, len(days), max(1, len(days)//10))], rotation=45)
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    
    # 2. 成交率
    ax2 = axes[0, 1]
    fill_rates = [(executor_by_day[day]['filled'] / executor_by_day[day]['total'] * 100) if executor_by_day[day]['total'] > 0 else 0 for day in days]
    ax2.plot(range(len(days)), fill_rates, marker='o', linewidth=2, markersize=4)
    ax2.set_title('Daily Fill Rate', fontweight='bold')
    ax2.set_xlabel('Date')
    ax2.set_ylabel('Fill Rate (%)')
    ax2.set_xticks(range(0, len(days), max(1, len(days)//10)))
    ax2.set_xticklabels([days[i] for i in range(0, len(days), max(1, len(days)//10))], rotation=45)
    ax2.grid(True, alpha=0.3)
    ax2.axhline(y=50, color='r', linestyle='--', alpha=0.5, label='50% Reference')
    ax2.legend()
    
    # 3. Buy vs Sell分布
    ax3 = axes[1, 0]
    x = range(len(days))
    ax3.bar(x, buy_counts, alpha=0.7, label='Buy', color='green')
    ax3.bar(x, sell_counts, bottom=buy_counts, alpha=0.7, label='Sell', color='red')
    ax3.set_title('Daily Buy/Sell Distribution', fontweight='bold')
    ax3.set_xlabel('Date')
    ax3.set_ylabel('Count')
    ax3.set_xticks(range(0, len(days), max(1, len(days)//10)))
    ax3.set_xticklabels([days[i] for i in range(0, len(days), max(1, len(days)//10))], rotation=45)
    ax3.legend()
    ax3.grid(True, alpha=0.3)
    
    # 4. 累计PnL
    ax4 = axes[1, 1]
    # 按时间排序的executors
    sorted_filled = sorted(filled_executors, key=lambda e: e.config.timestamp)
    cumulative_pnl = []
    cum_pnl = 0
    for e in sorted_filled:
        pnl = float(e.net_pnl_quote) if hasattr(e, 'net_pnl_quote') and e.net_pnl_quote else 0
        cum_pnl += pnl
        cumulative_pnl.append((datetime.fromtimestamp(e.config.timestamp), cum_pnl))
    
    if cumulative_pnl:
        timestamps, pnls = zip(*cumulative_pnl)
        ax4.plot(timestamps, pnls, linewidth=2)
        ax4.set_title('Cumulative PnL', fontweight='bold')
        ax4.set_xlabel('Date')
        ax4.set_ylabel('PnL ($)')
        ax4.grid(True, alpha=0.3)
        ax4.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
        ax4.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))
        ax4.xaxis.set_major_locator(mdates.DayLocator(interval=max(1, len(days)//10)))
        plt.setp(ax4.xaxis.get_majorticklabels(), rotation=45)
    
    plt.tight_layout()
    
    # 保存图表
    output_file = f"position_distribution_{TRADING_PAIR.replace('-', '_')}_{START_DATE.strftime('%Y%m%d')}_{END_DATE.strftime('%Y%m%d')}.png"
    plt.savefig(output_file, dpi=150, bbox_inches='tight')
    print(f"✓ 图表已保存: {output_file}")
    
    print(f"\n{'='*80}")
    print("测试完成")
    print(f"{'='*80}")
    
    # 验证分布均匀性
    if len(executor_by_day) > 0:
        avg_per_day = len(filled_executors) / len(executor_by_day)
        print(f"\n分布均匀性分析:")
        print(f"  总天数: {len(executor_by_day)}")
        print(f"  平均每天成交: {avg_per_day:.1f} 个executors")
        
        # 计算标准差
        import numpy as np
        daily_filled = [executor_by_day[day]['filled'] for day in sorted(executor_by_day.keys())]
        std_dev = np.std(daily_filled)
        cv = std_dev / avg_per_day if avg_per_day > 0 else 0
        
        print(f"  标准差: {std_dev:.1f}")
        print(f"  变异系数: {cv:.2f}")
        
        if cv < 0.3:
            print(f"  ✓ 分布非常均匀 (CV < 0.3)")
        elif cv < 0.5:
            print(f"  ✓ 分布较均匀 (CV < 0.5)")
        else:
            print(f"  ⚠ 分布不均匀 (CV >= 0.5)")


if __name__ == "__main__":
    asyncio.run(test_position_distribution())

