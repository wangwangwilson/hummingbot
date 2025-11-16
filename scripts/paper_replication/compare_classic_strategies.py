#!/usr/bin/env python3
"""
对比Hummingbot经典做市策略
包括：PMM Simple（经典做市）、PMM Bar Portion、PMM Dynamic
使用相同本地数据进行对比
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
from controllers.market_making.pmm_dynamic import PMMDynamicControllerConfig, PMMDynamicController
from hummingbot.strategy_v2.executors.position_executor.data_types import OrderType

# 导入本地数据管理器
from backtest_comparison_local import LocalBinanceDataProvider, LocalBacktestingDataProvider

# 测试参数
SYMBOL = "SOL-USDT"
START_DATE = datetime(2025, 10, 27)
END_DATE = datetime(2025, 11, 1)  # 5天数据用于快速测试

def create_pmm_simple_config(trading_pair: str, total_amount: Decimal) -> PMMSimpleConfig:
    """创建PMM Simple策略配置（经典做市策略）"""
    return PMMSimpleConfig(
        controller_name="pmm_simple",
        connector_name="binance_perpetual",
        trading_pair=trading_pair,
        total_amount_quote=total_amount,
        buy_spreads=[0.001, 0.002],  # 0.1%, 0.2% 固定价差
        sell_spreads=[0.001, 0.002],
        buy_amounts_pct=[Decimal("0.5"), Decimal("0.5")],
        sell_amounts_pct=[Decimal("0.5"), Decimal("0.5")],
        stop_loss=Decimal("0.01"),  # 1%止损
        take_profit=Decimal("0.005"),  # 0.5%止盈
        time_limit=3600,  # 1小时
        take_profit_order_type=OrderType.MARKET
    )

def create_pmm_bar_portion_config(trading_pair: str, total_amount: Decimal) -> PMMBarPortionControllerConfig:
    """创建PMM Bar Portion策略配置"""
    return PMMBarPortionControllerConfig(
        controller_name="pmm_bar_portion",
        connector_name="binance_perpetual",
        trading_pair=trading_pair,
        total_amount_quote=total_amount,
        buy_spreads=[1.0, 2.0],  # 以波动率单位
        sell_spreads=[1.0, 2.0],
        buy_amounts_pct=[Decimal("0.5"), Decimal("0.5")],
        sell_amounts_pct=[Decimal("0.5"), Decimal("0.5")],
        candles_connector="binance_perpetual",
        candles_trading_pair=trading_pair,
        interval="1m",
        stop_loss=Decimal("0.01"),
        take_profit=Decimal("0.005"),
        time_limit=3600,
        take_profit_order_type=OrderType.MARKET
    )

def create_pmm_dynamic_config(trading_pair: str, total_amount: Decimal) -> PMMDynamicControllerConfig:
    """创建PMM Dynamic (MACD)策略配置"""
    return PMMDynamicControllerConfig(
        controller_name="pmm_dynamic",
        connector_name="binance_perpetual",
        trading_pair=trading_pair,
        total_amount_quote=total_amount,
        buy_spreads=[1.0, 2.0],
        sell_spreads=[1.0, 2.0],
        buy_amounts_pct=[Decimal("0.5"), Decimal("0.5")],
        sell_amounts_pct=[Decimal("0.5"), Decimal("0.5")],
        candles_connector="binance_perpetual",
        candles_trading_pair=trading_pair,
        interval="1m",
        stop_loss=Decimal("0.01"),
        take_profit=Decimal("0.005"),
        time_limit=3600,
        take_profit_order_type=OrderType.MARKET
    )

async def run_backtest(controller_class, config, start_ts: int, end_ts: int, strategy_name: str) -> Dict:
    """运行单个策略回测"""
    try:
        # 初始化数据提供器
        local_data_provider = LocalBinanceDataProvider()
        local_backtesting_provider = LocalBacktestingDataProvider(local_data_provider)
        local_backtesting_provider.update_backtesting_time(start_ts, end_ts)
        
        # 创建控制器
        controller = controller_class(
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
            show_progress=True
        )
        
        return result
        
    except Exception as e:
        print(f"  ✗ {strategy_name} 回测失败: {e}")
        import traceback
        traceback.print_exc()
        return None

def analyze_results(executors: List, strategy_name: str) -> Dict:
    """分析回测结果"""
    if not executors:
        return {
            'strategy': strategy_name,
            'total_executors': 0,
            'filled_executors': 0,
            'fill_rate': 0.0,
            'total_volume': 0.0,
            'total_pnl': 0.0,
            'total_pnl_pct': 0.0,
            'winning_trades': 0,
            'losing_trades': 0,
            'break_even_trades': 0
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
    
    return {
        'strategy': strategy_name,
        'total_executors': total_executors,
        'filled_executors': filled_executors,
        'fill_rate': fill_rate * 100,
        'total_volume': total_volume,
        'total_pnl': total_pnl,
        'total_pnl_pct': total_pnl_pct,
        'winning_trades': winning_trades,
        'losing_trades': losing_trades,
        'break_even_trades': break_even_trades
    }

async def main():
    """主函数"""
    print("="*80)
    print("Hummingbot经典做市策略对比")
    print("="*80)
    print()
    print(f"交易对: {SYMBOL}")
    print(f"时间范围: {START_DATE.strftime('%Y-%m-%d')} 至 {END_DATE.strftime('%Y-%m-%d')}")
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
    
    # 定义策略配置
    strategies = [
        {
            'name': 'PMM Simple',
            'description': '经典做市策略（固定价差）',
            'controller_class': PMMSimpleController,
            'config_func': create_pmm_simple_config
        },
        {
            'name': 'PMM Bar Portion',
            'description': '基于Bar Portion信号的动态做市',
            'controller_class': PMMBarPortionController,
            'config_func': create_pmm_bar_portion_config
        },
        {
            'name': 'PMM Dynamic (MACD)',
            'description': '基于MACD信号的动态做市',
            'controller_class': PMMDynamicController,
            'config_func': create_pmm_dynamic_config
        }
    ]
    
    # 运行回测
    results = []
    
    for i, strategy in enumerate(strategies, 1):
        print(f"[{i}/{len(strategies)}] 运行 {strategy['name']} 策略回测...")
        print(f"  描述: {strategy['description']}")
        
        config = strategy['config_func'](SYMBOL, Decimal("10000"))
        result = await run_backtest(
            strategy['controller_class'],
            config,
            start_ts,
            end_ts,
            strategy['name']
        )
        
        if result and 'executors' in result:
            analysis = analyze_results(result['executors'], strategy['name'])
            results.append(analysis)
            print(f"  ✓ 完成: 总Executor={analysis['total_executors']}, 成交={analysis['filled_executors']}, 成交率={analysis['fill_rate']:.2f}%")
        else:
            print(f"  ✗ 回测失败或无结果")
        
        print()
    
    # 生成对比报告
    print("="*80)
    print("策略对比结果")
    print("="*80)
    print()
    
    if not results:
        print("✗ 没有有效的回测结果")
        return
    
    # 创建对比表格
    print(f"{'策略名称':<20} {'总Executor':<12} {'成交Executor':<12} {'成交率%':<12} {'总成交量$':<15} {'总盈亏$':<15} {'盈亏%':<12} {'盈利':<8} {'亏损':<8} {'持平':<8}")
    print("-" * 140)
    
    for r in results:
        print(f"{r['strategy']:<20} {r['total_executors']:<12} {r['filled_executors']:<12} {r['fill_rate']:<11.2f}% ${r['total_volume']:<14.2f} ${r['total_pnl']:<14.2f} {r['total_pnl_pct']:<11.2f}% {r['winning_trades']:<8} {r['losing_trades']:<8} {r['break_even_trades']:<8}")
    
    print()
    
    # 分析对比
    print("="*80)
    print("策略对比分析")
    print("="*80)
    print()
    
    # 成交率排名
    sorted_by_fill_rate = sorted(results, key=lambda x: x['fill_rate'], reverse=True)
    print("成交率排名（从高到低）:")
    for i, r in enumerate(sorted_by_fill_rate, 1):
        print(f"  {i}. {r['strategy']}: {r['fill_rate']:.2f}% (成交: {r['filled_executors']}/{r['total_executors']})")
    
    print()
    
    # 盈亏排名
    sorted_by_pnl = sorted(results, key=lambda x: x['total_pnl'], reverse=True)
    print("盈亏排名（从高到低）:")
    for i, r in enumerate(sorted_by_pnl, 1):
        print(f"  {i}. {r['strategy']}: ${r['total_pnl']:.2f} ({r['total_pnl_pct']:.2f}%)")
    
    print()
    
    # 成交量排名
    sorted_by_volume = sorted(results, key=lambda x: x['total_volume'], reverse=True)
    print("成交量排名（从高到低）:")
    for i, r in enumerate(sorted_by_volume, 1):
        print(f"  {i}. {r['strategy']}: ${r['total_volume']:.2f}")
    
    print()
    
    # 总结
    print("="*80)
    print("总结")
    print("="*80)
    print()
    
    best_fill_rate = max(results, key=lambda x: x['fill_rate'])
    best_pnl = max(results, key=lambda x: x['total_pnl'])
    best_volume = max(results, key=lambda x: x['total_volume'])
    
    print(f"最高成交率: {best_fill_rate['strategy']} ({best_fill_rate['fill_rate']:.2f}%)")
    print(f"最佳盈亏: {best_pnl['strategy']} (${best_pnl['total_pnl']:.2f}, {best_pnl['total_pnl_pct']:.2f}%)")
    print(f"最大成交量: {best_volume['strategy']} (${best_volume['total_volume']:.2f})")
    print()

if __name__ == "__main__":
    asyncio.run(main())

