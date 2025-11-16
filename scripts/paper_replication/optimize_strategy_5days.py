#!/usr/bin/env python3
"""
优化策略参数 - 使用5天数据回测验证
参考paper_info.md优化参数
"""

import asyncio
import sys
import json
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List
import pandas as pd

sys.path.insert(0, '/Users/wilson/Desktop/tradingview-ai')

class FakeCCXT:
    pass
sys.modules['ccxt'] = FakeCCXT()

from src.data.sources.binance_public_data_manager import BinancePublicDataManager

sys.path.insert(0, '/Users/wilson/Desktop/mm_research/hummingbot')

from hummingbot.strategy_v2.backtesting.backtesting_engine_base import BacktestingEngineBase
from controllers.market_making.pmm_bar_portion import PMMBarPortionControllerConfig
from backtest_comparison_local import LocalBinanceDataProvider, LocalBacktestingDataProvider

# 回测配置 - 使用5天数据
SYMBOL = "SOL-USDT"
END_DATE = datetime(2025, 11, 1)
START_DATE = END_DATE - timedelta(days=5)  # 5天数据

# 参数优化空间（基于论文）
# 论文提到：价差约等于月度波动率的4-5倍
# 对于SOL，假设月度波动率约2-3%，则价差应该在0.08-0.15之间
# 但buy_spreads/sell_spreads是以波动率单位表示的，所以应该用1-5

PARAM_GRID = [
    {
        "name": "baseline",
        "buy_spreads": [1.0, 2.0],
        "sell_spreads": [1.0, 2.0],
        "stop_loss": Decimal("0.03"),
        "take_profit": Decimal("0.02"),
        "time_limit": 30 * 60,  # 30分钟
        "executor_refresh_time": 300,
    },
    {
        "name": "wider_spread",
        "buy_spreads": [2.0, 4.0],
        "sell_spreads": [2.0, 4.0],
        "stop_loss": Decimal("0.03"),
        "take_profit": Decimal("0.02"),
        "time_limit": 30 * 60,
        "executor_refresh_time": 300,
    },
    {
        "name": "tighter_spread",
        "buy_spreads": [0.5, 1.0],
        "sell_spreads": [0.5, 1.0],
        "stop_loss": Decimal("0.03"),
        "take_profit": Decimal("0.02"),
        "time_limit": 30 * 60,
        "executor_refresh_time": 300,
    },
    {
        "name": "aggressive_tp",
        "buy_spreads": [1.0, 2.0],
        "sell_spreads": [1.0, 2.0],
        "stop_loss": Decimal("0.02"),
        "take_profit": Decimal("0.03"),
        "time_limit": 30 * 60,
        "executor_refresh_time": 300,
    },
    {
        "name": "conservative_sl",
        "buy_spreads": [1.0, 2.0],
        "sell_spreads": [1.0, 2.0],
        "stop_loss": Decimal("0.05"),
        "take_profit": Decimal("0.02"),
        "time_limit": 30 * 60,
        "executor_refresh_time": 300,
    },
    {
        "name": "longer_time",
        "buy_spreads": [1.0, 2.0],
        "sell_spreads": [1.0, 2.0],
        "stop_loss": Decimal("0.03"),
        "take_profit": Decimal("0.02"),
        "time_limit": 60 * 60,  # 60分钟
        "executor_refresh_time": 300,
    },
    {
        "name": "paper_optimized",
        # 论文优化结果：价差约等于月度波动率的4-5倍
        # 对于SOL，使用更宽的价差以提高成交率
        "buy_spreads": [3.0, 5.0],
        "sell_spreads": [3.0, 5.0],
        "stop_loss": Decimal("0.04"),
        "take_profit": Decimal("0.025"),
        "time_limit": 45 * 60,  # 45分钟（论文中Time Limit重要性最高）
        "executor_refresh_time": 300,
    },
]

def verify_data_loading(data_provider: LocalBinanceDataProvider, symbol: str, start: datetime, end: datetime):
    """验证数据加载是否符合预期"""
    print("="*80)
    print("数据加载验证")
    print("="*80)
    print()
    
    start_ts = int(start.timestamp())
    end_ts = int(end.timestamp())
    
    # 获取数据
    df = data_provider.get_historical_candles(
        symbol=symbol,
        start_ts=start_ts,
        end_ts=end_ts,
        interval="1m"
    )
    
    if df is None or len(df) == 0:
        print("❌ 数据加载失败：未获取到数据")
        return False
    
    print(f"✓ 数据加载成功")
    print(f"  交易对: {symbol}")
    print(f"  时间范围: {start.strftime('%Y-%m-%d %H:%M:%S')} 至 {end.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  数据行数: {len(df)}")
    print(f"  预期行数: {(end - start).total_seconds() / 60:.0f} (分钟K线)")
    print()
    
    # 检查数据完整性
    if 'timestamp' in df.columns:
        df['datetime'] = pd.to_datetime(df['timestamp'], unit='s')
        actual_start = df['datetime'].min()
        actual_end = df['datetime'].max()
        print(f"  实际开始时间: {actual_start}")
        print(f"  实际结束时间: {actual_end}")
        print()
        
        # 检查缺失值
        missing = df[['open', 'high', 'low', 'close', 'volume']].isna().sum()
        if missing.sum() > 0:
            print(f"⚠️  发现缺失值:")
            print(missing)
            print()
        else:
            print(f"✓ 无缺失值")
            print()
        
        # 检查数据连续性
        expected_minutes = (actual_end - actual_start).total_seconds() / 60
        continuity = len(df) / expected_minutes if expected_minutes > 0 else 0
        print(f"  数据连续性: {continuity*100:.2f}%")
        if continuity < 0.95:
            print(f"⚠️  数据连续性较低，可能存在缺失")
        else:
            print(f"✓ 数据连续性良好")
        print()
    
    # 检查数据质量
    print("数据质量检查:")
    print(f"  价格范围: ${df['close'].min():.4f} - ${df['close'].max():.4f}")
    print(f"  平均价格: ${df['close'].mean():.4f}")
    print(f"  价格波动率: {df['close'].pct_change().std()*100:.4f}%")
    print(f"  平均成交量: {df['volume'].mean():.2f}")
    print()
    
    return True

def create_bp_config(trading_pair: str, total_amount: Decimal, params: Dict) -> PMMBarPortionControllerConfig:
    """创建PMM Bar Portion策略配置"""
    return PMMBarPortionControllerConfig(
        controller_name="pmm_bar_portion",
        connector_name="binance_perpetual",
        trading_pair=trading_pair,
        total_amount_quote=total_amount,
        buy_spreads=params["buy_spreads"],
        sell_spreads=params["sell_spreads"],
        buy_amounts_pct=[0.5, 0.5],
        sell_amounts_pct=[0.5, 0.5],
        candles_connector="binance_perpetual",
        candles_trading_pair=trading_pair,
        interval="1m",
        stop_loss=params["stop_loss"],
        take_profit=params["take_profit"],
        time_limit=params["time_limit"],
        executor_refresh_time=params["executor_refresh_time"],
    )

async def run_backtest(config_name: str, params: Dict, data_provider: LocalBinanceDataProvider, 
                       backtesting_provider: LocalBacktestingDataProvider, 
                       start_ts: int, end_ts: int) -> Dict:
    """运行单个回测"""
    print(f"运行回测: {config_name}")
    print(f"  参数: spreads={params['buy_spreads']}, SL={params['stop_loss']}, TP={params['take_profit']}, TL={params['time_limit']//60}min")
    
    config = create_bp_config(SYMBOL, Decimal("10000"), params)
    
    engine = BacktestingEngineBase()
    engine.backtesting_data_provider = backtesting_provider
    
    results = await engine.run_backtesting(
        controller_config=config,
        start=start_ts,
        end=end_ts,
        backtesting_resolution="1m",
        trade_cost=0.0004,
        show_progress=False  # 批量回测时不显示进度条
    )
    
    executors = results.get('executors', [])
    summary = engine.summarize_results(executors, total_amount_quote=10000)
    
    # 计算额外指标
    filled = [e for e in executors if float(e.filled_amount_quote) > 0]
    fill_rate = len(filled) / len(executors) * 100 if len(executors) > 0 else 0
    
    result = {
        "config_name": config_name,
        "params": params,
        "summary": summary,
        "total_executors": len(executors),
        "filled_executors": len(filled),
        "fill_rate": fill_rate,
    }
    
    print(f"  ✓ 完成: Executors={len(executors)}, 成交={len(filled)}, 成交率={fill_rate:.2f}%, 盈亏=${summary['net_pnl_quote']:.2f}")
    print()
    
    return result

async def main():
    """主函数"""
    print("="*80)
    print("策略参数优化 - 5天数据回测")
    print("="*80)
    print()
    print(f"交易对: {SYMBOL}")
    print(f"时间区间: {START_DATE.strftime('%Y-%m-%d')} 至 {END_DATE.strftime('%Y-%m-%d')} (5天)")
    print()
    
    # 初始化数据提供者
    local_data_provider = LocalBinanceDataProvider()
    local_backtesting_provider = LocalBacktestingDataProvider(local_data_provider)
    
    # 验证数据加载
    if not verify_data_loading(local_data_provider, SYMBOL, START_DATE, END_DATE):
        print("❌ 数据加载验证失败，退出")
        return
    
    start_ts = int(START_DATE.timestamp())
    end_ts = int(END_DATE.timestamp())
    local_backtesting_provider.update_backtesting_time(start_ts, end_ts)
    
    # 运行所有参数组合的回测
    print("="*80)
    print("开始参数优化回测")
    print("="*80)
    print()
    
    all_results = []
    for param_set in PARAM_GRID:
        result = await run_backtest(
            param_set["name"],
            param_set,
            local_data_provider,
            local_backtesting_provider,
            start_ts,
            end_ts
        )
        all_results.append(result)
    
    # 汇总结果
    print("="*80)
    print("参数优化结果汇总")
    print("="*80)
    print()
    
    # 创建对比表
    comparison_data = []
    for result in all_results:
        s = result["summary"]
        comparison_data.append({
            "配置名称": result["config_name"],
            "总Executor": result["total_executors"],
            "成交Executor": result["filled_executors"],
            "成交率%": f"{result['fill_rate']:.2f}",
            "总成交量": f"${s['total_volume']:.2f}",
            "总盈亏": f"${s['net_pnl_quote']:.2f}",
            "盈亏%": f"{s['net_pnl']*100:.2f}",
            "胜率%": f"{s['accuracy']*100:.2f}",
            "Sharpe": f"{s['sharpe_ratio']:.4f}",
            "最大回撤%": f"{s['max_drawdown_pct']*100:.2f}",
        })
    
    df_comparison = pd.DataFrame(comparison_data)
    print(df_comparison.to_string(index=False))
    print()
    
    # 找出最佳配置
    print("="*80)
    print("最佳配置推荐")
    print("="*80)
    print()
    
    # 按Sharpe比率排序
    best_sharpe = max(all_results, key=lambda x: x["summary"]["sharpe_ratio"])
    print(f"最佳Sharpe比率: {best_sharpe['config_name']}")
    print(f"  Sharpe: {best_sharpe['summary']['sharpe_ratio']:.4f}")
    print(f"  盈亏: ${best_sharpe['summary']['net_pnl_quote']:.2f} ({best_sharpe['summary']['net_pnl']*100:.2f}%)")
    print(f"  成交率: {best_sharpe['fill_rate']:.2f}%")
    print()
    
    # 按成交率排序
    best_fill = max(all_results, key=lambda x: x["fill_rate"])
    print(f"最高成交率: {best_fill['config_name']}")
    print(f"  成交率: {best_fill['fill_rate']:.2f}%")
    print(f"  盈亏: ${best_fill['summary']['net_pnl_quote']:.2f} ({best_fill['summary']['net_pnl']*100:.2f}%)")
    print()
    
    # 按盈亏排序
    best_pnl = max(all_results, key=lambda x: x["summary"]["net_pnl_quote"])
    print(f"最高盈亏: {best_pnl['config_name']}")
    print(f"  盈亏: ${best_pnl['summary']['net_pnl_quote']:.2f} ({best_pnl['summary']['net_pnl']*100:.2f}%)")
    print(f"  成交率: {best_pnl['fill_rate']:.2f}%")
    print()
    
    # 保存结果
    output_file = f"optimization_results_{SYMBOL.replace('-', '_')}_{START_DATE.strftime('%Y%m%d')}.json"
    with open(output_file, 'w') as f:
        # 转换Decimal为字符串以便JSON序列化
        json_results = []
        for r in all_results:
            json_r = {
                "config_name": r["config_name"],
                "params": {
                    "buy_spreads": r["params"]["buy_spreads"],
                    "sell_spreads": r["params"]["sell_spreads"],
                    "stop_loss": str(r["params"]["stop_loss"]),
                    "take_profit": str(r["params"]["take_profit"]),
                    "time_limit": r["params"]["time_limit"],
                },
                "total_executors": r["total_executors"],
                "filled_executors": r["filled_executors"],
                "fill_rate": r["fill_rate"],
                "summary": {
                    k: (str(v) if isinstance(v, Decimal) else v) 
                    for k, v in r["summary"].items()
                }
            }
            json_results.append(json_r)
        json.dump(json_results, f, indent=2)
    
    print(f"✓ 结果已保存到: {output_file}")
    print()

if __name__ == "__main__":
    asyncio.run(main())

