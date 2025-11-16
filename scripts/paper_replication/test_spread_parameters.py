#!/usr/bin/env python3
"""
测试不同价差参数对成交率的影响
调整挂单距离来调整成交率
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
from controllers.market_making.pmm_bar_portion import PMMBarPortionControllerConfig, PMMBarPortionController
from hummingbot.strategy_v2.executors.position_executor.data_types import OrderType

# 导入本地数据管理器
from backtest_comparison_local import LocalBinanceDataProvider, LocalBacktestingDataProvider

# 测试参数
SYMBOL = "SOL-USDT"
START_DATE = datetime(2025, 10, 27)
END_DATE = datetime(2025, 11, 1)  # 5天数据用于快速测试

# 不同的价差配置（以波动率单位）
SPREAD_CONFIGS = [
    {"name": "tight_0.5_1.0", "buy_spreads": [0.5, 1.0], "sell_spreads": [0.5, 1.0], "description": "紧密价差 (0.5, 1.0)"},
    {"name": "medium_1.0_2.0", "buy_spreads": [1.0, 2.0], "sell_spreads": [1.0, 2.0], "description": "中等价差 (1.0, 2.0)"},
    {"name": "wide_2.0_4.0", "buy_spreads": [2.0, 4.0], "sell_spreads": [2.0, 4.0], "description": "宽价差 (2.0, 4.0)"},
    {"name": "very_wide_4.0_8.0", "buy_spreads": [4.0, 8.0], "sell_spreads": [4.0, 8.0], "description": "很宽价差 (4.0, 8.0)"},
]

def create_config(spread_config: Dict, total_amount: Decimal) -> PMMBarPortionControllerConfig:
    """创建策略配置"""
    return PMMBarPortionControllerConfig(
        controller_name="pmm_bar_portion",
        connector_name="binance_perpetual",
        trading_pair=SYMBOL,
        total_amount_quote=total_amount,
        buy_spreads=spread_config["buy_spreads"],
        sell_spreads=spread_config["sell_spreads"],
        buy_amounts_pct=[Decimal("0.5"), Decimal("0.5")],
        sell_amounts_pct=[Decimal("0.5"), Decimal("0.5")],
        candles_connector="binance_perpetual",
        candles_trading_pair=SYMBOL,
        interval="1m",
        stop_loss=Decimal("0.01"),  # 1%止损
        take_profit=Decimal("0.005"),  # 0.5%止盈
        time_limit=3600,  # 1小时
        take_profit_order_type=OrderType.MARKET
    )

async def run_backtest(config: PMMBarPortionControllerConfig, start_ts: int, end_ts: int) -> Dict:
    """运行回测"""
    try:
        # 初始化数据提供器
        local_data_provider = LocalBinanceDataProvider()
        local_backtesting_provider = LocalBacktestingDataProvider(local_data_provider)
        local_backtesting_provider.update_backtesting_time(start_ts, end_ts)
        
        # 创建控制器
        controller = PMMBarPortionController(
            config=config,
            market_data_provider=local_backtesting_provider,
            actions_queue=None
        )
        
        # 运行回测
        engine = BacktestingEngineBase()
        engine.backtesting_data_provider = local_backtesting_provider
        
        result = await engine.run_backtesting(
            controller_config=config,
            start=start_ts,
            end=end_ts,
            backtesting_resolution="1m",
            trade_cost=Decimal("0.0004"),  # 0.04%
            show_progress=False  # 批量测试时不显示进度条
        )
        
        return result
        
    except Exception as e:
        print(f"  ✗ 回测失败: {e}")
        import traceback
        traceback.print_exc()
        return None

def analyze_results(executors: List, spread_config: Dict) -> Dict:
    """分析回测结果"""
    if not executors:
        return {
            'spread_config': spread_config['name'],
            'description': spread_config['description'],
            'total_executors': 0,
            'filled_executors': 0,
            'fill_rate': 0.0,
            'total_volume': 0.0,
            'total_pnl': 0.0,
            'total_pnl_pct': 0.0,
            'winning_trades': 0,
            'losing_trades': 0
        }
    
    total_executors = len(executors)
    filled_executors = sum(1 for e in executors if hasattr(e, 'filled_amount_quote') and e.filled_amount_quote and float(e.filled_amount_quote) > 0)
    fill_rate = filled_executors / total_executors if total_executors > 0 else 0.0
    
    total_volume = sum(float(e.filled_amount_quote) if hasattr(e, 'filled_amount_quote') and e.filled_amount_quote else 0.0 for e in executors)
    total_pnl = sum(float(e.net_pnl_quote) if hasattr(e, 'net_pnl_quote') and e.net_pnl_quote else 0.0 for e in executors)
    total_pnl_pct = (total_pnl / 10000) * 100 if total_pnl != 0 else 0.0
    
    winning_trades = sum(1 for e in executors if hasattr(e, 'net_pnl_quote') and e.net_pnl_quote and float(e.net_pnl_quote) > 0)
    losing_trades = sum(1 for e in executors if hasattr(e, 'net_pnl_quote') and e.net_pnl_quote and float(e.net_pnl_quote) < 0)
    
    return {
        'spread_config': spread_config['name'],
        'description': spread_config['description'],
        'total_executors': total_executors,
        'filled_executors': filled_executors,
        'fill_rate': fill_rate * 100,
        'total_volume': total_volume,
        'total_pnl': total_pnl,
        'total_pnl_pct': total_pnl_pct,
        'winning_trades': winning_trades,
        'losing_trades': losing_trades
    }

async def main():
    """主函数"""
    print("="*80)
    print("价差参数调整测试 - 验证成交率变化")
    print("="*80)
    print()
    print(f"交易对: {SYMBOL}")
    print(f"时间范围: {START_DATE.strftime('%Y-%m-%d')} 至 {END_DATE.strftime('%Y-%m-%d')}")
    print(f"测试配置数: {len(SPREAD_CONFIGS)}")
    print()
    
    # 转换时间戳
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
    
    # 运行不同价差配置的回测
    results = []
    
    for i, spread_config in enumerate(SPREAD_CONFIGS, 1):
        print(f"[{i}/{len(SPREAD_CONFIGS)}] 测试配置: {spread_config['description']}")
        print(f"  价差: {spread_config['buy_spreads']}")
        
        config = create_config(spread_config, Decimal("10000"))
        result = await run_backtest(config, start_ts, end_ts)
        
        if result and 'executors' in result:
            analysis = analyze_results(result['executors'], spread_config)
            results.append(analysis)
            print(f"  ✓ 完成: 总Executor={analysis['total_executors']}, 成交={analysis['filled_executors']}, 成交率={analysis['fill_rate']:.2f}%")
        else:
            print(f"  ✗ 回测失败或无结果")
        
        print()
    
    # 生成对比报告
    print("="*80)
    print("价差参数对比结果")
    print("="*80)
    print()
    
    if not results:
        print("✗ 没有有效的回测结果")
        return
    
    # 创建对比表格
    print(f"{'配置名称':<20} {'价差':<20} {'总Executor':<12} {'成交Executor':<12} {'成交率%':<12} {'总成交量$':<15} {'总盈亏$':<15} {'盈亏%':<12} {'盈利':<8} {'亏损':<8}")
    print("-" * 140)
    
    for r in results:
        spread_str = f"{r['description']}"
        print(f"{r['spread_config']:<20} {spread_str:<20} {r['total_executors']:<12} {r['filled_executors']:<12} {r['fill_rate']:<11.2f}% ${r['total_volume']:<14.2f} ${r['total_pnl']:<14.2f} {r['total_pnl_pct']:<11.2f}% {r['winning_trades']:<8} {r['losing_trades']:<8}")
    
    print()
    
    # 分析价差对成交率的影响
    print("="*80)
    print("价差对成交率的影响分析")
    print("="*80)
    print()
    
    # 按价差大小排序
    sorted_results = sorted(results, key=lambda x: x['fill_rate'], reverse=True)
    
    print("成交率排名（从高到低）:")
    for i, r in enumerate(sorted_results, 1):
        print(f"  {i}. {r['description']}: {r['fill_rate']:.2f}% (成交: {r['filled_executors']}/{r['total_executors']})")
    
    print()
    
    # 分析价差与成交率的关系
    print("价差与成交率关系:")
    for r in sorted(results, key=lambda x: sum([float(s) for s in r['description'].split('(')[1].split(')')[0].split(',')]) if '(' in r['description'] else 0):
        avg_spread = sum([float(s) for s in r['description'].split('(')[1].split(')')[0].split(',')]) / 2 if '(' in r['description'] else 0
        print(f"  平均价差: {avg_spread:.1f} -> 成交率: {r['fill_rate']:.2f}%")
    
    print()
    
    # 推荐配置
    print("="*80)
    print("推荐配置")
    print("="*80)
    print()
    
    # 找到成交率最高的配置
    best_fill_rate = max(results, key=lambda x: x['fill_rate'])
    print(f"最高成交率配置: {best_fill_rate['description']}")
    print(f"  成交率: {best_fill_rate['fill_rate']:.2f}%")
    print(f"  总盈亏: ${best_fill_rate['total_pnl']:.2f} ({best_fill_rate['total_pnl_pct']:.2f}%)")
    print()
    
    # 找到盈亏最好的配置（如果有盈利）
    profitable_configs = [r for r in results if r['total_pnl'] > 0]
    if profitable_configs:
        best_pnl = max(profitable_configs, key=lambda x: x['total_pnl'])
        print(f"最佳盈亏配置: {best_pnl['description']}")
        print(f"  总盈亏: ${best_pnl['total_pnl']:.2f} ({best_pnl['total_pnl_pct']:.2f}%)")
        print(f"  成交率: {best_pnl['fill_rate']:.2f}%")
    else:
        print("⚠ 所有配置均无盈利")
    
    print()

if __name__ == "__main__":
    asyncio.run(main())

