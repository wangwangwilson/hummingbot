#!/usr/bin/env python3
"""
BTC回测分析脚本
时间区间: 2025-01-01 至 2025-11-08
分析内容:
1. 多空订单成交情况
2. 指标统计对比
3. 仓位分布
4. 回测耗时评估
"""

import asyncio
import sys
import time
from pathlib import Path
from datetime import datetime, date
from decimal import Decimal
from typing import Dict, List
import pandas as pd
import numpy as np

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
from controllers.market_making.pmm_dynamic import PMMDynamicControllerConfig
from scripts.paper_replication.backtest_comparison_local import LocalBinanceDataProvider, LocalBacktestingDataProvider
from hummingbot.core.data_type.common import TradeType

def create_bp_config(trading_pair: str, total_amount: Decimal = Decimal("10000")) -> PMMBarPortionControllerConfig:
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

def create_macd_config(trading_pair: str, total_amount: Decimal = Decimal("10000")) -> PMMDynamicControllerConfig:
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

def analyze_executors(executors: List, strategy_name: str) -> Dict:
    """分析executor的详细情况"""
    if not executors:
        return {
            'total': 0,
            'filled': 0,
            'long': 0,
            'short': 0,
            'long_filled': 0,
            'short_filled': 0,
            'long_pnl': 0.0,
            'short_pnl': 0.0,
            'total_pnl': 0.0,
            'long_volume': 0.0,
            'short_volume': 0.0,
            'total_volume': 0.0,
        }
    
    filled = [e for e in executors if hasattr(e, 'filled_amount_quote') and float(e.filled_amount_quote) > 0]
    
    long_executors = [e for e in filled if hasattr(e, 'side') and e.side == TradeType.BUY]
    short_executors = [e for e in filled if hasattr(e, 'side') and e.side == TradeType.SELL]
    
    long_pnl = sum(float(e.net_pnl_quote) for e in long_executors)
    short_pnl = sum(float(e.net_pnl_quote) for e in short_executors)
    
    long_volume = sum(float(e.filled_amount_quote) for e in long_executors)
    short_volume = sum(float(e.filled_amount_quote) for e in short_executors)
    
    return {
        'total': len(executors),
        'filled': len(filled),
        'long': len([e for e in executors if hasattr(e, 'side') and e.side == TradeType.BUY]),
        'short': len([e for e in executors if hasattr(e, 'side') and e.side == TradeType.SELL]),
        'long_filled': len(long_executors),
        'short_filled': len(short_executors),
        'long_pnl': long_pnl,
        'short_pnl': short_pnl,
        'total_pnl': long_pnl + short_pnl,
        'long_volume': long_volume,
        'short_volume': short_volume,
        'total_volume': long_volume + short_volume,
    }

def analyze_position_distribution(executors: List) -> Dict:
    """分析仓位分布"""
    if not executors:
        return {}
    
    filled = [e for e in executors if hasattr(e, 'filled_amount_quote') and float(e.filled_amount_quote) > 0]
    
    if not filled:
        return {}
    
    # 按时间戳分组，统计每个时间点的仓位
    positions = []
    for e in filled:
        if hasattr(e, 'timestamp') and hasattr(e, 'filled_amount_quote'):
            side_multiplier = 1 if (hasattr(e, 'side') and e.side == TradeType.BUY) else -1
            positions.append({
                'timestamp': e.timestamp,
                'amount': float(e.filled_amount_quote) * side_multiplier,
                'pnl': float(e.net_pnl_quote) if hasattr(e, 'net_pnl_quote') else 0.0,
            })
    
    if not positions:
        return {}
    
    df = pd.DataFrame(positions)
    df = df.sort_values('timestamp')
    df['cumulative_position'] = df['amount'].cumsum()
    df['cumulative_pnl'] = df['pnl'].cumsum()
    
    return {
        'max_long_position': df['cumulative_position'].max() if len(df) > 0 else 0.0,
        'max_short_position': abs(df['cumulative_position'].min()) if len(df) > 0 else 0.0,
        'avg_position': df['cumulative_position'].mean() if len(df) > 0 else 0.0,
        'position_std': df['cumulative_position'].std() if len(df) > 0 else 0.0,
        'total_position_changes': len(df),
    }

async def run_backtest(engine: BacktestingEngineBase, config, start_ts: int, end_ts: int, strategy_name: str):
    """运行单个策略的回测"""
    start_time = time.time()
    print(f"  开始回测 {strategy_name}...", flush=True)
    
    try:
        print(f"  初始化数据提供器和控制器...", flush=True)
        init_start = time.time()
        results = await engine.run_backtesting(
            controller_config=config,
            start=start_ts,
            end=end_ts,
            backtesting_resolution="1m",
            trade_cost=0.0004,
            show_progress=True  # 启用进度条
        )
        init_time = time.time() - init_start
        
        elapsed_time = time.time() - start_time
        print(f"  ✓ {strategy_name} 回测完成，总耗时: {elapsed_time:.1f}秒 (初始化: {init_time:.1f}秒)", flush=True)
        
        if not results:
            print(f"  ⚠️  {strategy_name} 无结果", flush=True)
            return None, elapsed_time
        
        executors = results.get('executors', [])
        summary = results.get('summary', {})
        
        filled = [e for e in executors if hasattr(e, 'filled_amount_quote') and float(e.filled_amount_quote) > 0]
        print(f"  ✓ {strategy_name} 生成 {len(executors)} 个executor (成交: {len(filled)})", flush=True)
        
        return {
            'executors': executors,
            'summary': summary,
            'elapsed_time': elapsed_time,
        }, elapsed_time
        
    except Exception as e:
        elapsed_time = time.time() - start_time
        print(f"  ✗ {strategy_name} 回测失败: {e}", flush=True)
        import traceback
        traceback.print_exc()
        return None, elapsed_time

async def main():
    """主函数"""
    print("="*80)
    print("BTC回测分析 - 2025-01-01 至 2025-11-08")
    print("="*80)
    
    # 1. 设置时间范围
    start_date = date(2025, 1, 1)
    end_date = date(2025, 11, 8)
    start_ts = int(datetime.combine(start_date, datetime.min.time()).timestamp())
    end_ts = int(datetime.combine(end_date, datetime.min.time()).timestamp())
    
    print(f"\n时间范围: {start_date} 至 {end_date}")
    print(f"时间戳: {start_ts} 至 {end_ts}")
    
    # 2. 初始化数据提供器
    print("\n初始化数据提供器...")
    local_data_provider = LocalBinanceDataProvider()
    local_backtesting_provider = LocalBacktestingDataProvider(local_data_provider)
    local_backtesting_provider.update_backtesting_time(start_ts, end_ts)
    
    # 验证数据加载
    print("验证数据加载...", flush=True)
    data_start = time.time()
    test_df = local_data_provider.get_historical_candles(
        symbol="BTC-USDT",
        start_ts=start_ts,
        end_ts=end_ts,
        interval="1m"
    )
    data_elapsed = time.time() - data_start
    print(f"✓ 数据量: {len(test_df):,} 条K线 (加载耗时: {data_elapsed:.2f}秒)", flush=True)
    if len(test_df) == 0:
        print("✗ 数据加载失败，请检查数据文件", flush=True)
        return
    print(f"✓ 数据时间范围: {datetime.fromtimestamp(test_df['timestamp'].min())} 至 {datetime.fromtimestamp(test_df['timestamp'].max())}", flush=True)
    
    # 3. 创建策略配置
    print("\n创建策略配置...")
    bp_config = create_bp_config("BTC-USDT", Decimal("10000"))
    macd_config = create_macd_config("BTC-USDT", Decimal("10000"))
    print("✓ 配置创建完成")
    
    # 4. 运行回测
    print("\n" + "="*80)
    print("开始回测...")
    print("="*80)
    
    total_start_time = time.time()
    
    # 4.1 PMM Bar Portion策略
    print("\n[1/2] 运行PMM Bar Portion策略回测...", flush=True)
    print("  注意: 进度条会显示在下方，预计需要较长时间", flush=True)
    engine_bp = BacktestingEngineBase()
    engine_bp.backtesting_data_provider = local_backtesting_provider
    bp_results, bp_time = await run_backtest(engine_bp, bp_config, start_ts, end_ts, "PMM Bar Portion")
    
    # 4.2 PMM Dynamic (MACD)策略
    print("\n[2/2] 运行PMM Dynamic (MACD)策略回测...", flush=True)
    print("  注意: 进度条会显示在下方，预计需要较长时间", flush=True)
    engine_macd = BacktestingEngineBase()
    engine_macd.backtesting_data_provider = local_backtesting_provider
    macd_results, macd_time = await run_backtest(engine_macd, macd_config, start_ts, end_ts, "PMM Dynamic")
    
    total_elapsed_time = time.time() - total_start_time
    
    # 5. 分析结果
    print("\n" + "="*80)
    print("回测结果分析")
    print("="*80)
    
    if bp_results and macd_results:
        bp_executors = bp_results['executors']
        macd_executors = macd_results['executors']
        bp_summary = bp_results['summary']
        macd_summary = macd_results['summary']
        
        # 5.1 多空订单成交情况
        print("\n【1. 多空订单成交情况】")
        print("-" * 80)
        
        bp_analysis = analyze_executors(bp_executors, "PMM Bar Portion")
        macd_analysis = analyze_executors(macd_executors, "PMM Dynamic")
        
        print(f"\nPMM Bar Portion:")
        print(f"  总Executor: {bp_analysis['total']}")
        print(f"  成交Executor: {bp_analysis['filled']} ({bp_analysis['filled']/bp_analysis['total']*100:.1f}%)" if bp_analysis['total'] > 0 else "  成交Executor: 0")
        print(f"  多单: {bp_analysis['long']} (成交: {bp_analysis['long_filled']})")
        print(f"  空单: {bp_analysis['short']} (成交: {bp_analysis['short_filled']})")
        print(f"  多单盈亏: ${bp_analysis['long_pnl']:.2f}")
        print(f"  空单盈亏: ${bp_analysis['short_pnl']:.2f}")
        print(f"  多单成交量: ${bp_analysis['long_volume']:.2f}")
        print(f"  空单成交量: ${bp_analysis['short_volume']:.2f}")
        
        print(f"\nPMM Dynamic (MACD):")
        print(f"  总Executor: {macd_analysis['total']}")
        print(f"  成交Executor: {macd_analysis['filled']} ({macd_analysis['filled']/macd_analysis['total']*100:.1f}%)" if macd_analysis['total'] > 0 else "  成交Executor: 0")
        print(f"  多单: {macd_analysis['long']} (成交: {macd_analysis['long_filled']})")
        print(f"  空单: {macd_analysis['short']} (成交: {macd_analysis['short_filled']})")
        print(f"  多单盈亏: ${macd_analysis['long_pnl']:.2f}")
        print(f"  空单盈亏: ${macd_analysis['short_pnl']:.2f}")
        print(f"  多单成交量: ${macd_analysis['long_volume']:.2f}")
        print(f"  空单成交量: ${macd_analysis['short_volume']:.2f}")
        
        # 5.2 指标统计对比
        print("\n【2. 指标统计对比】")
        print("-" * 80)
        
        metrics = [
            ('总盈亏 ($)', 'net_pnl_quote', '${:.2f}'),
            ('总盈亏 (%)', 'net_pnl', '{:.2%}'),
            ('Sharpe比率', 'sharpe_ratio', '{:.4f}'),
            ('最大回撤 (%)', 'max_drawdown_pct', '{:.2%}'),
            ('胜率 (%)', 'accuracy', '{:.2%}'),
            ('总交易次数', 'total_executors_with_position', '{:d}'),
            ('总成交量', 'total_volume', '${:.2f}'),
        ]
        
        print(f"\n{'指标':<20} {'PMM Bar Portion':<20} {'PMM Dynamic':<20}")
        print("-" * 60)
        for metric_name, metric_key, format_str in metrics:
            bp_value = bp_summary.get(metric_key, 0)
            macd_value = macd_summary.get(metric_key, 0)
            print(f"{metric_name:<20} {format_str.format(bp_value):<20} {format_str.format(macd_value):<20}")
        
        # 5.3 仓位分布
        print("\n【3. 仓位分布】")
        print("-" * 80)
        
        bp_position = analyze_position_distribution(bp_executors)
        macd_position = analyze_position_distribution(macd_executors)
        
        print(f"\nPMM Bar Portion:")
        if bp_position:
            print(f"  最大多仓: ${bp_position['max_long_position']:.2f}")
            print(f"  最大空仓: ${bp_position['max_short_position']:.2f}")
            print(f"  平均仓位: ${bp_position['avg_position']:.2f}")
            print(f"  仓位标准差: ${bp_position['position_std']:.2f}")
            print(f"  仓位变化次数: {bp_position['total_position_changes']}")
        else:
            print("  无仓位数据")
        
        print(f"\nPMM Dynamic (MACD):")
        if macd_position:
            print(f"  最大多仓: ${macd_position['max_long_position']:.2f}")
            print(f"  最大空仓: ${macd_position['max_short_position']:.2f}")
            print(f"  平均仓位: ${macd_position['avg_position']:.2f}")
            print(f"  仓位标准差: ${macd_position['position_std']:.2f}")
            print(f"  仓位变化次数: {macd_position['total_position_changes']}")
        else:
            print("  无仓位数据")
        
        # 5.4 回测耗时
        print("\n【4. 回测耗时评估】")
        print("-" * 80)
        print(f"PMM Bar Portion: {bp_time:.2f}秒 ({bp_time/60:.2f}分钟)")
        print(f"PMM Dynamic: {macd_time:.2f}秒 ({macd_time/60:.2f}分钟)")
        print(f"总耗时: {total_elapsed_time:.2f}秒 ({total_elapsed_time/60:.2f}分钟)")
        print(f"平均每个策略: {total_elapsed_time/2:.2f}秒 ({total_elapsed_time/2/60:.2f}分钟)")
        
        # 计算数据量
        data_points = len(test_df)
        time_per_point = total_elapsed_time / 2 / data_points if data_points > 0 else 0
        print(f"\n数据量: {data_points:,} 条K线")
        print(f"每条K线处理时间: {time_per_point*1000:.2f}毫秒")
        
    else:
        print("✗ 回测失败，无法进行分析")
        if not bp_results:
            print("  - PMM Bar Portion回测失败")
        if not macd_results:
            print("  - PMM Dynamic回测失败")

if __name__ == "__main__":
    asyncio.run(main())

