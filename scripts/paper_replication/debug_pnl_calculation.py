#!/usr/bin/env python3
"""
调试盈亏计算 - 直接检查executor_simulation DataFrame
"""

import asyncio
import sys
from datetime import datetime, timedelta
from decimal import Decimal
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
from hummingbot.strategy_v2.backtesting.executors_simulator.position_executor_simulator import PositionExecutorSimulator
from hummingbot.strategy_v2.executors.position_executor.data_types import PositionExecutorConfig, TripleBarrierConfig
from hummingbot.strategy_v2.executors.position_executor.data_types import OrderType
from hummingbot.core.data_type.common import TradeType

# 配置
SYMBOL = "SOL-USDT"
END_DATE = datetime(2025, 11, 1)
START_DATE = END_DATE - timedelta(days=1)

async def debug_pnl():
    """调试盈亏计算"""
    print("="*80)
    print("调试盈亏计算")
    print("="*80)
    print()
    
    local_data_provider = LocalBinanceDataProvider()
    local_backtesting_provider = LocalBacktestingDataProvider(local_data_provider)
    
    start_ts = int(START_DATE.timestamp())
    end_ts = int(END_DATE.timestamp())
    local_backtesting_provider.update_backtesting_time(start_ts, end_ts)
    
    # 初始化candles feed
    from hummingbot.data_feed.candles_feed.data_types import CandlesConfig
    candles_config = CandlesConfig(
        connector="binance_perpetual",
        trading_pair=SYMBOL,
        interval="1m"
    )
    await local_backtesting_provider.initialize_candles_feed([candles_config])
    
    # 获取数据
    df = local_backtesting_provider.get_candles_df(
        connector_name="binance_perpetual",
        trading_pair=SYMBOL,
        interval="1m",
        max_records=1000
    )
    
    if len(df) == 0:
        print("❌ 无法获取数据")
        return
    
    print(f"✓ 获取到 {len(df)} 条K线数据")
    print()
    
    # 创建一个简单的executor config
    config = PositionExecutorConfig(
        timestamp=float(df.index[100]),
        connector_name="binance_perpetual",
        trading_pair=SYMBOL,
        side=TradeType.BUY,
        entry_price=Decimal("187.0"),
        amount=Decimal("50"),
        triple_barrier_config=TripleBarrierConfig(
            stop_loss=Decimal("0.03"),
            take_profit=Decimal("0.02"),
            time_limit=30 * 60,
            open_order_type=OrderType.LIMIT,
            take_profit_order_type=OrderType.MARKET,
            stop_loss_order_type=OrderType.MARKET,
        ),
        leverage=1,
    )
    
    # 运行simulator
    simulator = PositionExecutorSimulator()
    print("运行simulator...")
    simulation = simulator.simulate(df, config, trade_cost=0.0004)
    
    print(f"✓ Simulator完成")
    print(f"  关闭类型: {simulation.close_type}")
    print(f"  DataFrame行数: {len(simulation.executor_simulation)}")
    print()
    
    # 检查DataFrame中的盈亏数据
    sim_df = simulation.executor_simulation
    print("检查executor_simulation DataFrame:")
    print(f"  列: {list(sim_df.columns)}")
    print()
    
    # 检查有成交的行
    filled_rows = sim_df[sim_df['filled_amount_quote'] > 0]
    print(f"有成交的行数: {len(filled_rows)}")
    print()
    
    if len(filled_rows) > 0:
        print("前5行有成交的数据:")
        print(filled_rows[['close', 'net_pnl_pct', 'net_pnl_quote', 'filled_amount_quote']].head())
        print()
        
        print("最后5行数据:")
        print(sim_df[['close', 'net_pnl_pct', 'net_pnl_quote', 'filled_amount_quote']].tail())
        print()
        
        # 检查最后一行
        last_row = sim_df.iloc[-1]
        print("最后一行数据:")
        print(f"  timestamp: {last_row.name}")
        print(f"  close: {last_row['close']}")
        print(f"  net_pnl_pct: {last_row['net_pnl_pct']}")
        print(f"  net_pnl_quote: {last_row['net_pnl_quote']}")
        print(f"  filled_amount_quote: {last_row['filled_amount_quote']}")
        print()
        
        # 计算理论盈亏
        entry_price = float(config.entry_price)
        exit_price = float(last_row['close'])
        theoretical_pnl_pct = (exit_price - entry_price) / entry_price - (2 * 0.0004)
        theoretical_pnl_quote = theoretical_pnl_pct * float(last_row['filled_amount_quote'])
        
        print("理论盈亏:")
        print(f"  entry_price: ${entry_price:.4f}")
        print(f"  exit_price: ${exit_price:.4f}")
        print(f"  theoretical_pnl_pct: {theoretical_pnl_pct*100:.4f}%")
        print(f"  theoretical_pnl_quote: ${theoretical_pnl_quote:.2f}")
        print()
        
        print("实际盈亏:")
        print(f"  net_pnl_pct: {last_row['net_pnl_pct']*100:.4f}%")
        print(f"  net_pnl_quote: ${last_row['net_pnl_quote']:.2f}")
        print()
        
        if abs(last_row['net_pnl_pct'] - theoretical_pnl_pct) < 0.0001:
            print("✓ 盈亏计算正确")
        else:
            print(f"⚠️  盈亏计算错误，差异: {(last_row['net_pnl_pct'] - theoretical_pnl_pct)*100:.4f}%")
    else:
        print("❌ 没有成交的行")

if __name__ == "__main__":
    asyncio.run(debug_pnl())

