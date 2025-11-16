#!/usr/bin/env python3
"""
调试executor创建问题
详细打印每次迭代的状态，检查为什么executors只在最后创建
"""

import asyncio
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path
import pandas as pd

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

# Import local data manager
from backtest_comparison_local import LocalBinanceDataProvider, LocalBacktestingDataProvider

# Test parameters
TRADING_PAIR = "BTC-USDT"
START_DATE = datetime(2025, 1, 1)
END_DATE = datetime(2025, 1, 3)  # 只测试2天
INITIAL_PORTFOLIO_USD = 10000
TRADING_FEE = 0.0004
BACKTEST_RESOLUTION = "1m"


# 创建一个自定义的BacktestingEngineBase来添加调试信息
class DebugBacktestingEngine(BacktestingEngineBase):
    """带调试信息的回测引擎"""
    
    async def simulate_execution(self, trade_cost: float, show_progress: bool = False) -> list:
        from hummingbot.strategy_v2.models.executor_actions import CreateExecutorAction, StopExecutorAction
        from hummingbot.strategy_v2.models.executors_info import ExecutorInfo
        from hummingbot.strategy_v2.backtesting.executor_simulator_base import ExecutorSimulation
        from hummingbot.strategy_v2.models.executors import CloseType
        from typing import List
        """重写simulate_execution以添加调试信息"""
        processed_features = self.prepare_market_data()
        self.active_executor_simulations: List[ExecutorSimulation] = []
        self.stopped_executors_info: List[ExecutorInfo] = []
        
        total_rows = len(processed_features)
        print(f"总数据行数: {total_rows}")
        print(f"数据时间范围: {datetime.fromtimestamp(processed_features.index.min())} 到 {datetime.fromtimestamp(processed_features.index.max())}")
        print()
        
        # 统计信息
        executor_creation_count = 0
        executor_creation_timestamps = []
        no_action_count = 0
        
        iterator = processed_features.iterrows()
        
        # 每1000行打印一次状态
        check_interval = max(100, total_rows // 20)
        
        for pos_idx, (i, row) in enumerate(iterator):
            await self.update_state(row)
            
            # 检查processed_data是否更新
            has_features = "features" in self.controller.processed_data and not self.controller.processed_data["features"].empty
            has_reference_price = "reference_price" in self.controller.processed_data
            
            # 获取actions
            actions = self.controller.determine_executor_actions()
            
            if len(actions) > 0:
                executor_creation_count += len([a for a in actions if hasattr(a, 'executor_config')])
                if executor_creation_count <= 5:  # 只打印前5个
                    current_dt = datetime.fromtimestamp(row["timestamp"])
                    print(f"  [{pos_idx}] {current_dt}: 创建 {len(actions)} 个actions")
                    if has_reference_price:
                        ref_price = self.controller.processed_data.get("reference_price", "N/A")
                        print(f"      reference_price: {ref_price}")
            
            if len(actions) == 0:
                no_action_count += 1
            
            # 每check_interval行打印一次状态
            if pos_idx > 0 and pos_idx % check_interval == 0:
                current_dt = datetime.fromtimestamp(row["timestamp"])
                print(f"  进度: {pos_idx}/{total_rows} ({pos_idx/total_rows*100:.1f}%) - {current_dt}")
                print(f"    已创建executors: {executor_creation_count}")
                print(f"    无actions次数: {no_action_count}")
                print(f"    has_features: {has_features}")
                print(f"    has_reference_price: {has_reference_price}")
                if has_reference_price:
                    ref_price = self.controller.processed_data.get("reference_price", "N/A")
                    print(f"    reference_price: {ref_price}")
                print()
            
            for action in actions:
                if isinstance(action, CreateExecutorAction):
                    executor_simulation = self.simulate_executor(action.executor_config, processed_features.loc[i:], trade_cost)
                    if executor_simulation is not None and executor_simulation.close_type != CloseType.FAILED:
                        executor_creation_timestamps.append(row["timestamp"])
                        self.manage_active_executors(executor_simulation)
                elif isinstance(action, StopExecutorAction):
                    self.handle_stop_action(action, row["timestamp"])
        
        print(f"\n总结:")
        print(f"  总迭代次数: {total_rows}")
        print(f"  创建executors次数: {executor_creation_count}")
        print(f"  无actions次数: {no_action_count} ({no_action_count/total_rows*100:.1f}%)")
        
        if executor_creation_timestamps:
            first_ts = min(executor_creation_timestamps)
            last_ts = max(executor_creation_timestamps)
            print(f"  第一个executor创建时间: {datetime.fromtimestamp(first_ts)}")
            print(f"  最后一个executor创建时间: {datetime.fromtimestamp(last_ts)}")
            print(f"  时间跨度: {(last_ts - first_ts) / 86400:.2f} 天")
        
        return self.controller.executors_info


async def debug_executor_creation():
    """调试executor创建"""
    print("="*80)
    print("调试Executor创建问题")
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
    
    # Create config
    config = PMMBarPortionControllerConfig(
        controller_name="pmm_bar_portion",
        connector_name="binance_perpetual",
        trading_pair=TRADING_PAIR,
        total_amount_quote=Decimal(str(INITIAL_PORTFOLIO_USD)),
        buy_spreads=[0.01, 0.02],
        sell_spreads=[0.01, 0.02],
        buy_amounts_pct=[Decimal("0.5"), Decimal("0.5")],
        sell_amounts_pct=[Decimal("0.5"), Decimal("0.5")],
        stop_loss=Decimal("0.01"),
        take_profit=Decimal("0.005"),
        time_limit=3600,
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
    
    # Run backtest with debug engine
    engine = DebugBacktestingEngine()
    engine.backtesting_data_provider = local_backtesting_provider
    
    print("运行回测（带调试信息）...")
    result = await engine.run_backtesting(
        controller_config=config,
        start=start_ts,
        end=end_ts,
        backtesting_resolution=BACKTEST_RESOLUTION,
        trade_cost=Decimal(str(TRADING_FEE)),
        show_progress=False
    )


if __name__ == "__main__":
    # 需要导入必要的类
    from hummingbot.strategy_v2.models.executor_actions import CreateExecutorAction, StopExecutorAction
    from hummingbot.strategy_v2.models.executors_info import ExecutorInfo
    from hummingbot.strategy_v2.backtesting.executor_simulator_base import ExecutorSimulation
    from hummingbot.strategy_v2.models.executors import CloseType
    from typing import List
    
    asyncio.run(debug_executor_creation())

