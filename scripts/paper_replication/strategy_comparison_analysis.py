#!/usr/bin/env python3
"""
策略对比分析 - 详细分析成交率和收益
包括参数调整测试
"""

import asyncio
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Dict, List
import pandas as pd

# 配置SSL证书
cert_file = Path.home() / ".hummingbot_certs.pem"
if cert_file.exists():
    import os
    os.environ['SSL_CERT_FILE'] = str(cert_file)
    os.environ['REQUESTS_CA_BUNDLE'] = str(cert_file)
    os.environ['CURL_CA_BUNDLE'] = str(cert_file)

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
tradingview_ai_path = Path("/Users/wilson/Desktop/tradingview-ai")
sys.path.insert(0, str(tradingview_ai_path))

# 临时禁用ccxt
class FakeCCXT:
    pass
sys.modules['ccxt'] = FakeCCXT()

from hummingbot.strategy_v2.backtesting.backtesting_engine_base import BacktestingEngineBase
from controllers.market_making.pmm_simple import PMMSimpleConfig, PMMSimpleController
from controllers.market_making.pmm_bar_portion import PMMBarPortionControllerConfig, PMMBarPortionController
from hummingbot.strategy_v2.executors.position_executor.data_types import OrderType

# 导入本地数据管理器
from backtest_comparison_local import LocalBinanceDataProvider, LocalBacktestingDataProvider

# 测试参数
SYMBOL = "SOL-USDT"
START_DATE = datetime(2025, 10, 27)
END_DATE = datetime(2025, 11, 1)  # 5天数据

# 不同的参数配置
PARAM_CONFIGS = [
    {
        'name': 'baseline',
        'description': '基准配置',
        'stop_loss': Decimal("0.01"),  # 1%
        'take_profit': Decimal("0.005"),  # 0.5%
        'buy_spreads': [0.001, 0.002],  # 0.1%, 0.2%
        'sell_spreads': [0.001, 0.002]
    },
    {
        'name': 'wider_tp_sl',
        'description': '更宽的止盈止损',
        'stop_loss': Decimal("0.02"),  # 2%
        'take_profit': Decimal("0.01"),  # 1%
        'buy_spreads': [0.001, 0.002],
        'sell_spreads': [0.001, 0.002]
    },
    {
        'name': 'tighter_spread',
        'description': '更紧密的价差',
        'stop_loss': Decimal("0.01"),
        'take_profit': Decimal("0.005"),
        'buy_spreads': [0.0005, 0.001],  # 0.05%, 0.1%
        'sell_spreads': [0.0005, 0.001]
    },
    {
        'name': 'aggressive',
        'description': '激进配置（紧密价差+宽止盈止损）',
        'stop_loss': Decimal("0.02"),
        'take_profit': Decimal("0.01"),
        'buy_spreads': [0.0005, 0.001],
        'sell_spreads': [0.0005, 0.001]
    }
]

def create_pmm_simple_config(trading_pair: str, total_amount: Decimal, param_config: Dict) -> PMMSimpleConfig:
    """创建PMM Simple策略配置"""
    return PMMSimpleConfig(
        controller_name="pmm_simple",
        connector_name="binance_perpetual",
        trading_pair=trading_pair,
        total_amount_quote=total_amount,
        buy_spreads=param_config['buy_spreads'],
        sell_spreads=param_config['sell_spreads'],
        buy_amounts_pct=[Decimal("0.5"), Decimal("0.5")],
        sell_amounts_pct=[Decimal("0.5"), Decimal("0.5")],
        stop_loss=param_config['stop_loss'],
        take_profit=param_config['take_profit'],
        time_limit=3600,
        take_profit_order_type=OrderType.MARKET
    )

async def run_backtest(controller_class, config, start_ts: int, end_ts: int, strategy_name: str) -> Dict:
    """运行单个策略回测"""
    try:
        local_data_provider = LocalBinanceDataProvider()
        local_backtesting_provider = LocalBacktestingDataProvider(local_data_provider)
        local_backtesting_provider.update_backtesting_time(start_ts, end_ts)
        
        controller = controller_class(
            config=config,
            market_data_provider=local_backtesting_provider,
            actions_queue=None
        )
        
        engine = BacktestingEngineBase()
        engine.backtesting_data_provider = local_backtesting_provider
        
        result = await engine.run_backtesting(
            controller_config=config,
            start=start_ts,
            end=end_ts,
            backtesting_resolution="1m",
            trade_cost=Decimal("0.0004"),
            show_progress=False
        )
        
        return result
        
    except Exception as e:
        print(f"  ✗ 回测失败: {e}")
        return None

def analyze_detailed_results(executors: List, strategy_name: str, param_name: str) -> Dict:
    """详细分析回测结果"""
    if not executors:
        return {
            'strategy': strategy_name,
            'param': param_name,
            'total_executors': 0,
            'filled_executors': 0,
            'fill_rate': 0.0,
            'total_volume': 0.0,
            'total_pnl': 0.0,
            'total_pnl_pct': 0.0,
            'winning_trades': 0,
            'losing_trades': 0,
            'break_even_trades': 0,
            'close_types': {}
        }
    
    total_executors = len(executors)
    filled_executors = sum(1 for e in executors if hasattr(e, 'filled_amount_quote') and e.filled_amount_quote and float(e.filled_amount_quote) > 0)
    fill_rate = filled_executors / total_executors if total_executors > 0 else 0.0
    
    total_volume = sum(float(e.filled_amount_quote) if hasattr(e, 'filled_amount_quote') and e.filled_amount_quote else 0.0 for e in executors)
    total_pnl = sum(float(e.net_pnl_quote) if hasattr(e, 'net_pnl_quote') and e.net_pnl_quote else 0.0 for e in executors)
    total_pnl_pct = (total_pnl / 10000) * 100 if total_pnl != 0 else 0.0
    
    winning_trades = sum(1 for e in executors if hasattr(e, 'net_pnl_quote') and e.net_pnl_quote and float(e.net_pnl_quote) > 0)
    losing_trades = sum(1 for e in executors if hasattr(e, 'net_pnl_quote') and e.net_pnl_quote and float(e.net_pnl_quote) < 0)
    break_even_trades = total_executors - winning_trades - losing_trades
    
    # 统计关闭类型
    close_types = {}
    for e in executors:
        if hasattr(e, 'close_type') and e.close_type:
            ct = str(e.close_type)
            close_types[ct] = close_types.get(ct, 0) + 1
    
    return {
        'strategy': strategy_name,
        'param': param_name,
        'total_executors': total_executors,
        'filled_executors': filled_executors,
        'fill_rate': fill_rate * 100,
        'total_volume': total_volume,
        'total_pnl': total_pnl,
        'total_pnl_pct': total_pnl_pct,
        'winning_trades': winning_trades,
        'losing_trades': losing_trades,
        'break_even_trades': break_even_trades,
        'close_types': close_types
    }

async def main():
    """主函数"""
    print("="*80)
    print("策略对比分析 - PMM Simple vs PMM Bar Portion")
    print("="*80)
    print()
    print(f"交易对: {SYMBOL}")
    print(f"时间范围: {START_DATE.strftime('%Y-%m-%d')} 至 {END_DATE.strftime('%Y-%m-%d')}")
    print()
    
    start_ts = int(START_DATE.timestamp())
    end_ts = int(END_DATE.timestamp())
    
    # 验证数据加载
    print("验证数据加载...")
    local_data_provider = LocalBinanceDataProvider()
    test_df = local_data_provider.get_historical_candles(
        symbol=SYMBOL,
        start_ts=start_ts,
        end_ts=end_ts,
        interval="1m"
    )
    print(f"✓ 数据量: {len(test_df):,} 条K线")
    print()
    
    if len(test_df) == 0:
        print("✗ 数据加载失败，退出")
        return
    
    # 测试PMM Simple不同参数配置
    print("="*80)
    print("测试PMM Simple不同参数配置")
    print("="*80)
    print()
    
    pmm_simple_results = []
    
    for i, param_config in enumerate(PARAM_CONFIGS, 1):
        print(f"[{i}/{len(PARAM_CONFIGS)}] 测试配置: {param_config['description']}")
        print(f"  止盈: {param_config['take_profit']*100:.1f}%, 止损: {param_config['stop_loss']*100:.1f}%")
        print(f"  价差: {param_config['buy_spreads']}")
        
        config = create_pmm_simple_config(SYMBOL, Decimal("10000"), param_config)
        result = await run_backtest(PMMSimpleController, config, start_ts, end_ts, "PMM Simple")
        
        if result and 'executors' in result:
            analysis = analyze_detailed_results(result['executors'], "PMM Simple", param_config['name'])
            pmm_simple_results.append(analysis)
            print(f"  ✓ 完成: 总Executor={analysis['total_executors']}, 成交={analysis['filled_executors']}, 成交率={analysis['fill_rate']:.2f}%")
        else:
            print(f"  ✗ 回测失败或无结果")
        
        print()
    
    # 测试PMM Bar Portion（基准配置）
    print("="*80)
    print("测试PMM Bar Portion（基准配置）")
    print("="*80)
    print()
    
    bp_config = PMMBarPortionControllerConfig(
        controller_name="pmm_bar_portion",
        connector_name="binance_perpetual",
        trading_pair=SYMBOL,
        total_amount_quote=Decimal("10000"),
        buy_spreads=[1.0, 2.0],
        sell_spreads=[1.0, 2.0],
        buy_amounts_pct=[Decimal("0.5"), Decimal("0.5")],
        sell_amounts_pct=[Decimal("0.5"), Decimal("0.5")],
        candles_connector="binance_perpetual",
        candles_trading_pair=SYMBOL,
        interval="1m",
        stop_loss=Decimal("0.01"),
        take_profit=Decimal("0.005"),
        time_limit=3600,
        take_profit_order_type=OrderType.MARKET
    )
    
    bp_result = await run_backtest(PMMBarPortionController, bp_config, start_ts, end_ts, "PMM Bar Portion")
    bp_analysis = None
    if bp_result and 'executors' in bp_result:
        bp_analysis = analyze_detailed_results(bp_result['executors'], "PMM Bar Portion", "baseline")
        print(f"  ✓ 完成: 总Executor={bp_analysis['total_executors']}, 成交={bp_analysis['filled_executors']}, 成交率={bp_analysis['fill_rate']:.2f}%")
    print()
    
    # 生成对比报告
    print("="*80)
    print("策略对比结果")
    print("="*80)
    print()
    
    all_results = pmm_simple_results.copy()
    if bp_analysis:
        all_results.append(bp_analysis)
    
    if not all_results:
        print("✗ 没有有效的回测结果")
        return
    
    # 创建对比表格
    print(f"{'策略':<20} {'参数配置':<15} {'总Executor':<12} {'成交Executor':<12} {'成交率%':<12} {'总成交量$':<15} {'总盈亏$':<15} {'盈亏%':<12} {'盈利':<8} {'亏损':<8}")
    print("-" * 140)
    
    for r in all_results:
        print(f"{r['strategy']:<20} {r['param']:<15} {r['total_executors']:<12} {r['filled_executors']:<12} {r['fill_rate']:<11.2f}% ${r['total_volume']:<14.2f} ${r['total_pnl']:<14.2f} {r['total_pnl_pct']:<11.2f}% {r['winning_trades']:<8} {r['losing_trades']:<8}")
    
    print()
    
    # 详细分析
    print("="*80)
    print("详细分析")
    print("="*80)
    print()
    
    # 成交率分析
    sorted_by_fill_rate = sorted(all_results, key=lambda x: x['fill_rate'], reverse=True)
    print("成交率排名:")
    for i, r in enumerate(sorted_by_fill_rate, 1):
        print(f"  {i}. {r['strategy']} ({r['param']}): {r['fill_rate']:.2f}%")
        print(f"     关闭类型分布: {r['close_types']}")
    
    print()
    
    # 盈亏分析
    print("盈亏分析:")
    for r in all_results:
        if r['filled_executors'] > 0:
            print(f"  {r['strategy']} ({r['param']}):")
            print(f"    成交Executor: {r['filled_executors']}")
            print(f"    总盈亏: ${r['total_pnl']:.2f} ({r['total_pnl_pct']:.2f}%)")
            print(f"    盈利交易: {r['winning_trades']}, 亏损交易: {r['losing_trades']}, 持平交易: {r['break_even_trades']}")
            if r['total_pnl'] == 0 and r['filled_executors'] > 0:
                print(f"    ⚠ 有成交但无盈亏 - 可能止盈止损设置不合理或成交价格计算有问题")
    
    print()
    
    # 总结
    print("="*80)
    print("总结与建议")
    print("="*80)
    print()
    
    best_fill_rate = max(all_results, key=lambda x: x['fill_rate'])
    print(f"最高成交率: {best_fill_rate['strategy']} ({best_fill_rate['param']}): {best_fill_rate['fill_rate']:.2f}%")
    
    profitable = [r for r in all_results if r['total_pnl'] > 0]
    if profitable:
        best_pnl = max(profitable, key=lambda x: x['total_pnl'])
        print(f"最佳盈亏: {best_pnl['strategy']} ({best_pnl['param']}): ${best_pnl['total_pnl']:.2f}")
    else:
        print("⚠ 所有配置均无盈利")
        print()
        print("可能的原因:")
        print("  1. 止盈止损设置过小，无法覆盖交易费用（0.04% × 2 = 0.08%）")
        print("  2. 成交价格计算可能存在问题（entry_price = exit_price）")
        print("  3. 需要进一步检查executor的entry_price和exit_price计算逻辑")
    
    print()

if __name__ == "__main__":
    asyncio.run(main())

