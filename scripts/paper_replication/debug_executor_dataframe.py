#!/usr/bin/env python3
"""
详细调试executor_simulation DataFrame
直接检查net_pnl_pct的实际值
"""

import asyncio
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path
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
from controllers.market_making.pmm_bar_portion import PMMBarPortionControllerConfig
from hummingbot.strategy_v2.executors.position_executor.data_types import OrderType
from hummingbot.data_feed.candles_feed.data_types import CandlesConfig
from hummingbot.core.data_type.common import TradeType

# 导入本地数据管理器
from backtest_comparison_local import LocalBinanceDataProvider, LocalBacktestingDataProvider

# 测试参数
SYMBOL = "SOL-USDT"
START_DATE = datetime(2025, 10, 11)
END_DATE = datetime(2025, 10, 12)

async def debug_executor_dataframe():
    """调试executor_simulation DataFrame"""
    print("="*80)
    print("Executor Simulation DataFrame详细调试")
    print("="*80)
    print()
    
    start_ts = int(START_DATE.timestamp())
    end_ts = int(END_DATE.timestamp())
    
    # 初始化数据提供器
    local_data_provider = LocalBinanceDataProvider()
    local_backtesting_provider = LocalBacktestingDataProvider(local_data_provider)
    local_backtesting_provider.update_backtesting_time(start_ts, end_ts)
    
    # 创建策略配置
    config = PMMBarPortionControllerConfig(
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
    
    # 初始化candles feed
    candles_config = CandlesConfig(
        connector=config.candles_connector,
        trading_pair=config.candles_trading_pair,
        interval=config.interval,
        max_records=config.training_window + 1000
    )
    await local_backtesting_provider.initialize_candles_feed([candles_config])
    
    # 运行回测
    print("运行回测...")
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
    
    if not result or 'executors' not in result:
        print("✗ 回测失败")
        return
    
    executors = result['executors']
    filled_executors = [e for e in executors if hasattr(e, 'filled_amount_quote') and e.filled_amount_quote and float(e.filled_amount_quote) > 0]
    
    print(f"总Executor: {len(executors)}")
    print(f"已成交Executor: {len(filled_executors)}")
    print()
    
    # 访问active_executor_simulations来检查DataFrame
    print("="*80)
    print("检查Executor Simulation DataFrame")
    print("="*80)
    print()
    
    # 获取第一个已成交的executor的simulation
    if len(filled_executors) > 0:
        executor = filled_executors[0]
        print(f"分析Executor: {executor.id}")
        print(f"  Side: {executor.side}")
        print(f"  Entry Price (config): {executor.config.entry_price}")
        print(f"  Close Price: {executor.custom_info.get('close_price')}")
        print(f"  Net PnL %: {float(executor.net_pnl_pct)*100:.6f}%")
        print(f"  Net PnL Quote: ${float(executor.net_pnl_quote):.2f}")
        print(f"  Close Type: {executor.close_type}")
        print()
        
        # 尝试从engine中获取simulation
        # 注意：engine.active_executor_simulations可能已经被清空
        # 我们需要在回测过程中保存simulation
        
        # 检查是否有stopped_executors_info
        if hasattr(engine, 'stopped_executors_info'):
            print(f"Stopped Executors: {len(engine.stopped_executors_info)}")
            for i, stopped_executor in enumerate(engine.stopped_executors_info[:3], 1):
                if stopped_executor.config.id == executor.id:
                    print(f"  找到匹配的stopped executor {i}")
                    print(f"    Net PnL %: {float(stopped_executor.net_pnl_pct)*100:.6f}%")
                    print(f"    Net PnL Quote: ${float(stopped_executor.net_pnl_quote):.2f}")
                    break
        
        # 手动重新计算PnL来验证
        entry_price = float(executor.custom_info.get('current_position_average_price', executor.config.entry_price))
        exit_price = float(executor.custom_info.get('close_price', 0))
        side_multiplier = 1 if executor.side == TradeType.BUY else -1
        trade_cost = 0.0004
        
        if exit_price > 0:
            price_return = (exit_price - entry_price) / entry_price * side_multiplier
            net_return = price_return - (2 * trade_cost)
            expected_pnl = net_return * float(executor.filled_amount_quote)
            
            print(f"  手动验证:")
            print(f"    Entry: ${entry_price:.4f}")
            print(f"    Exit: ${exit_price:.4f}")
            print(f"    Price Return: {price_return*100:.4f}%")
            print(f"    Net Return (扣除成本): {net_return*100:.4f}%")
            print(f"    预期PnL: ${expected_pnl:.2f}")
            print(f"    实际PnL: ${float(executor.net_pnl_quote):.2f}")
            print(f"    差异: ${expected_pnl - float(executor.net_pnl_quote):.2f}")
            print()
            
            if abs(expected_pnl - float(executor.net_pnl_quote)) > 0.01:
                print(f"  ⚠ 发现不一致！预期PnL=${expected_pnl:.2f}，实际PnL=${float(executor.net_pnl_quote):.2f}")
                print(f"     这表明executor_simulation DataFrame中的net_pnl_pct可能不正确")
    
    # 检查所有filled executors的PnL分布
    print()
    print("="*80)
    print("所有已成交Executor的PnL分布")
    print("="*80)
    print()
    
    pnl_values = [float(e.net_pnl_quote) for e in filled_executors]
    zero_pnl_count = sum(1 for pnl in pnl_values if abs(pnl) < 0.01)
    positive_pnl_count = sum(1 for pnl in pnl_values if pnl > 0.01)
    negative_pnl_count = sum(1 for pnl in pnl_values if pnl < -0.01)
    
    print(f"总数量: {len(filled_executors)}")
    print(f"零盈亏: {zero_pnl_count}")
    print(f"正盈亏: {positive_pnl_count}")
    print(f"负盈亏: {negative_pnl_count}")
    print()
    
    if len(pnl_values) > 0:
        print(f"PnL统计:")
        print(f"  最小值: ${min(pnl_values):.2f}")
        print(f"  最大值: ${max(pnl_values):.2f}")
        print(f"  平均值: ${sum(pnl_values)/len(pnl_values):.2f}")
        print(f"  总和: ${sum(pnl_values):.2f}")
    
    print()
    print("="*80)
    print("结论")
    print("="*80)
    print()
    
    if zero_pnl_count == len(filled_executors):
        print("⚠ 所有executor的盈亏都是0")
        print("  可能原因:")
        print("    1. executor_simulation DataFrame中的net_pnl_pct在最后一行是0")
        print("    2. get_executor_info_at_timestamp没有正确获取最后一行")
        print("    3. net_pnl_pct的计算逻辑有问题")
        print()
        print("  建议:")
        print("    1. 在position_executor_simulator.py中添加调试日志")
        print("    2. 检查df_filtered在截断后的net_pnl_pct值")
        print("    3. 检查get_executor_info_at_timestamp返回的last_entry")
    else:
        print(f"✓ 发现{positive_pnl_count + negative_pnl_count}个executor有非零盈亏")
        print(f"  但仍有{zero_pnl_count}个executor的盈亏为0")

if __name__ == "__main__":
    asyncio.run(debug_executor_dataframe())

