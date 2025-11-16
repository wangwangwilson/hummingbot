#!/usr/bin/env python3
"""
详细调试executor simulation
检查net_pnl_pct在close_timestamp时的值
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
from controllers.market_making.pmm_bar_portion import PMMBarPortionControllerConfig, PMMBarPortionController
from hummingbot.strategy_v2.executors.position_executor.data_types import OrderType
from hummingbot.data_feed.candles_feed.data_types import CandlesConfig
from hummingbot.core.data_type.common import TradeType

# 导入本地数据管理器
from backtest_comparison_local import LocalBinanceDataProvider, LocalBacktestingDataProvider

# 测试参数
SYMBOL = "SOL-USDT"
START_DATE = datetime(2025, 10, 11)
END_DATE = datetime(2025, 10, 12)

async def debug_executor_simulation():
    """调试executor simulation"""
    print("="*80)
    print("Executor Simulation详细调试")
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
    
    # 获取executor simulation的详细信息
    from hummingbot.strategy_v2.backtesting.backtesting_engine_base import BacktestingEngineBase
    
    # 我们需要访问executor_simulations
    # 但BacktestingEngineBase可能没有直接暴露这个
    # 让我们通过executor的custom_info来推断
    
    for i, executor in enumerate(filled_executors[:2], 1):
        print(f"Executor {i} 详细分析:")
        print(f"  Side: {executor.side}")
        print(f"  Entry Price (config): {executor.config.entry_price}")
        print(f"  Close Price: {executor.custom_info.get('close_price')}")
        print(f"  Net PnL %: {float(executor.net_pnl_pct)*100:.6f}%")
        print(f"  Net PnL Quote: ${float(executor.net_pnl_quote):.2f}")
        print(f"  Close Type: {executor.close_type}")
        print(f"  Close Timestamp: {executor.close_timestamp}")
        print()
        
        # 手动计算应该的PnL
        entry_price = float(executor.custom_info.get('current_position_average_price', executor.config.entry_price))
        exit_price = float(executor.custom_info.get('close_price', 0))
        side_multiplier = 1 if executor.side == TradeType.BUY else -1
        trade_cost = 0.0004
        
        if exit_price > 0:
            price_return = (exit_price - entry_price) / entry_price * side_multiplier
            net_return = price_return - (2 * trade_cost)
            expected_pnl = net_return * float(executor.filled_amount_quote)
            
            print(f"  手动计算:")
            print(f"    Entry: ${entry_price:.4f}")
            print(f"    Exit: ${exit_price:.4f}")
            print(f"    Price Return: {price_return*100:.4f}%")
            print(f"    Net Return (扣除成本): {net_return*100:.4f}%")
            print(f"    预期PnL: ${expected_pnl:.2f}")
            print(f"    实际PnL: ${float(executor.net_pnl_quote):.2f}")
            print(f"    差异: ${expected_pnl - float(executor.net_pnl_quote):.2f}")
            print()

if __name__ == "__main__":
    asyncio.run(debug_executor_simulation())

