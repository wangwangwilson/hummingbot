#!/usr/bin/env python3
"""
ETH-USDT反向策略回测脚本
将MACD和BP策略的方向反转，验证是否能够改善收益
"""

import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
from typing import Dict, List, Optional, Tuple
from collections import defaultdict
import time
import json
import os

# Configure SSL certificates
cert_file = Path.home() / ".hummingbot_certs.pem"
if cert_file.exists():
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

import asyncio
from hummingbot.strategy_v2.backtesting.backtesting_engine_base import BacktestingEngineBase
from hummingbot.data_feed.candles_feed.data_types import CandlesConfig
from controllers.market_making.pmm_bar_portion import PMMBarPortionControllerConfig, PMMBarPortionController
from controllers.market_making.pmm_dynamic import PMMDynamicControllerConfig, PMMDynamicController
from controllers.market_making.pmm_simple import PMMSimpleConfig
from hummingbot.strategy_v2.executors.position_executor.data_types import OrderType
from hummingbot.core.data_type.common import TradeType

# Import local data manager
from backtest_comparison_local import LocalBinanceDataProvider, LocalBacktestingDataProvider

# 回测参数
TRADING_PAIR = "ETH-USDT"
START_DATE = datetime(2025, 1, 1)
END_DATE = datetime(2025, 11, 9)
INITIAL_PORTFOLIO_USD = 10000
MAKER_FEE = 0.0
TAKER_FEE = 0.0002
BACKTEST_RESOLUTION = "1m"
RESAMPLE_INTERVAL: Optional[str] = "15m"
PLOT_FREQUENCY = "3min"
ENVIRONMENT = "prod_reversed"


# 创建反向策略控制器（通过monkey patching）
class ReversedPMMBarPortionController(PMMBarPortionController):
    """反向BP策略：反转价格调整方向"""
    
    async def update_processed_data(self):
        # 调用父类方法
        await super().update_processed_data()
        
        # 反转价格调整
        if "reference_price" in self.processed_data:
            current_price = self.processed_data.get("reference_price", Decimal("0"))
            # 获取原始价格（从market_data_provider）
            from hummingbot.core.data_type.common import PriceType
            try:
                current_market_price = self.market_data_provider.get_price_by_type(
                    connector_name=self.config.connector_name,
                    trading_pair=self.config.trading_pair,
                    price_type=PriceType.MidPrice
                )
                if current_market_price and current_market_price > 0:
                    base_price = float(current_market_price)
                else:
                    base_price = float(current_price)
            except:
                base_price = float(current_price)
            
            # 计算原始的价格偏移
            original_shift = (float(current_price) / base_price) - 1.0 if base_price > 0 else 0.0
            
            # 反转偏移方向
            reversed_shift = -original_shift
            reversed_price = base_price * (1 + reversed_shift)
            
            # 更新processed_data
            self.processed_data["reference_price"] = Decimal(str(reversed_price))
            
            # 更新features DataFrame中的reference_price
            if "features" in self.processed_data and not self.processed_data["features"].empty:
                self.processed_data["features"]["reference_price"] = float(reversed_price)


class ReversedPMMDynamicController(PMMDynamicController):
    """反向MACD策略：反转价格调整方向"""
    
    async def update_processed_data(self):
        # 调用父类方法
        await super().update_processed_data()
        
        # 反转价格调整
        if "reference_price" in self.processed_data:
            current_price = self.processed_data.get("reference_price", Decimal("0"))
            # 获取原始价格（从market_data_provider）
            from hummingbot.core.data_type.common import PriceType
            try:
                current_market_price = self.market_data_provider.get_price_by_type(
                    connector_name=self.config.connector_name,
                    trading_pair=self.config.trading_pair,
                    price_type=PriceType.MidPrice
                )
                if current_market_price and current_market_price > 0:
                    base_price = float(current_market_price)
                else:
                    base_price = float(current_price)
            except:
                base_price = float(current_price)
            
            # 计算原始的价格偏移
            original_shift = (float(current_price) / base_price) - 1.0 if base_price > 0 else 0.0
            
            # 反转偏移方向
            reversed_shift = -original_shift
            reversed_price = base_price * (1 + reversed_shift)
            
            # 更新processed_data
            self.processed_data["reference_price"] = Decimal(str(reversed_price))
            
            # 更新features DataFrame中的reference_price
            if "features" in self.processed_data and not self.processed_data["features"].empty:
                self.processed_data["features"]["reference_price"] = float(reversed_price)


# 导入回测相关函数
from backtest_with_plots_and_structure import (
    create_output_directory,
    generate_equity_curve,
    generate_plots,
    generate_comprehensive_report,
    run_single_backtest_async
)


async def main():
    """主函数：运行ETH-USDT的反向策略回测"""
    print("=" * 80)
    print("ETH-USDT 反向策略回测")
    print("=" * 80)
    print(f"交易对: {TRADING_PAIR}")
    print(f"回测区间: {START_DATE.date()} 到 {END_DATE.date()}")
    print(f"基础数据: {BACKTEST_RESOLUTION}")
    print(f"回测分辨率: {RESAMPLE_INTERVAL}")
    print(f"画图频率: {PLOT_FREQUENCY}")
    print(f"环境: {ENVIRONMENT}")
    print()
    
    # 创建输出目录
    output_dir = create_output_directory(ENVIRONMENT)
    symbol_dir = output_dir / TRADING_PAIR.replace("-", "_")
    symbol_dir.mkdir(parents=True, exist_ok=True)
    
    # 准备数据
    print("准备数据...")
    data_provider = LocalBinanceDataProvider()
    backtesting_data_provider = LocalBacktestingDataProvider(data_provider)
    
    # 获取数据
    start_ts = int(START_DATE.timestamp())
    end_ts = int(END_DATE.timestamp())
    
    candles_df = data_provider.get_historical_candles(
        symbol=TRADING_PAIR,
        start_ts=start_ts,
        end_ts=end_ts,
        interval=RESAMPLE_INTERVAL if RESAMPLE_INTERVAL else BACKTEST_RESOLUTION
    )
    
    if candles_df.empty:
        print(f"❌ 无法获取 {TRADING_PAIR} 的数据")
        return
    
    print(f"✓ 数据准备完成: {len(candles_df)} 根K线")
    print(f"  时间范围: {pd.to_datetime(candles_df['timestamp'].min(), unit='s')} 到 {pd.to_datetime(candles_df['timestamp'].max(), unit='s')}")
    print()
    
    # 运行3种策略的回测
    strategies = [
        ("PMM_Simple", "PMM Simple", PMMSimpleConfig, None),
        ("PMM_Dynamic_MACD_Reversed", "PMM Dynamic (MACD) Reversed", PMMDynamicControllerConfig, ReversedPMMDynamicController),
        ("PMM_Bar_Portion_Reversed", "PMM Bar Portion Reversed", PMMBarPortionControllerConfig, ReversedPMMBarPortionController),
    ]
    
    results = []
    
    for strategy_key, strategy_name, config_class, controller_class in strategies:
        print(f"运行回测: {strategy_name}...")
        
        try:
            # 创建策略配置
            if strategy_key == "PMM_Simple":
                strategy_config = config_class(
                    connector_name="binance",
                    trading_pair=TRADING_PAIR,
                    candles_config=[],
                    buy_spreads=[1.0, 2.0, 4.0],
                    sell_spreads=[1.0, 2.0, 4.0],
                    buy_amounts_pct=[Decimal("0.5"), Decimal("0.5")],
                    sell_amounts_pct=[Decimal("0.5"), Decimal("0.5")],
                )
            elif strategy_key == "PMM_Dynamic_MACD_Reversed":
                strategy_config = config_class(
                    connector_name="binance",
                    trading_pair=TRADING_PAIR,
                    candles_config=[],
                    buy_spreads=[1.0, 2.0, 4.0],
                    sell_spreads=[1.0, 2.0, 4.0],
                    buy_amounts_pct=[Decimal("0.5"), Decimal("0.5")],
                    sell_amounts_pct=[Decimal("0.5"), Decimal("0.5")],
                    interval="15m",
                    macd_fast=21,
                    macd_slow=42,
                    macd_signal=9,
                    natr_length=14,
                )
            else:  # PMM_Bar_Portion_Reversed
                strategy_config = config_class(
                    connector_name="binance",
                    trading_pair=TRADING_PAIR,
                    candles_config=[],
                    buy_spreads=[1.0, 2.0, 4.0],
                    sell_spreads=[1.0, 2.0, 4.0],
                    buy_amounts_pct=[Decimal("0.5"), Decimal("0.5")],
                    sell_amounts_pct=[Decimal("0.5"), Decimal("0.5")],
                    interval="15m",
                    natr_length=14,
                    training_window=51840,
                    atr_length=10,
                )
            
            # 运行回测
            result = await run_single_backtest_async(
                trading_pair=TRADING_PAIR,
                strategy_config=strategy_config,
                strategy_key=strategy_key,
                strategy_name=strategy_name,
                start_date=START_DATE,
                end_date=END_DATE,
                initial_portfolio_usd=INITIAL_PORTFOLIO_USD,
                maker_fee=MAKER_FEE,
                taker_fee=TAKER_FEE,
                backtest_resolution=RESAMPLE_INTERVAL if RESAMPLE_INTERVAL else BACKTEST_RESOLUTION,
                plot_frequency=PLOT_FREQUENCY,
                data_provider=data_provider,
                backtesting_data_provider=backtesting_data_provider,
                controller_class=controller_class,  # 传入自定义控制器类
            )
            
            results.append(result)
            print(f"✓ {strategy_name} 回测完成")
            print()
            
        except Exception as e:
            print(f"❌ {strategy_name} 回测失败: {e}")
            import traceback
            traceback.print_exc()
            print()
    
    # 生成报告和图表
    print("生成报告和图表...")
    
    for result in results:
        if result.get("success", False):
            strategy_name = result["strategy_name"]
            strategy_key = result["strategy_key"]
            
            # 生成图表
            equity_curve = result.get("equity_curve")
            if equity_curve is not None and not equity_curve.empty:
                generate_plots(
                    equity_curve=equity_curve,
                    trading_pair=TRADING_PAIR,
                    strategy_name=strategy_name,
                    strategy_key=strategy_key,
                    environment=ENVIRONMENT,
                    output_dir=symbol_dir,
                    plot_frequency=PLOT_FREQUENCY,
                )
    
    # 生成综合报告
    report = generate_comprehensive_report(
        results=results,
        trading_pair=TRADING_PAIR,
        start_date=START_DATE,
        end_date=END_DATE,
        backtest_resolution=RESAMPLE_INTERVAL if RESAMPLE_INTERVAL else BACKTEST_RESOLUTION,
        plot_frequency=PLOT_FREQUENCY,
        environment=ENVIRONMENT,
        maker_fee=MAKER_FEE,
        taker_fee=TAKER_FEE,
    )
    
    # 保存JSON结果
    json_data = {
        "start_date": START_DATE.strftime("%Y-%m-%d"),
        "end_date": END_DATE.strftime("%Y-%m-%d"),
        "trading_pair": TRADING_PAIR,
        "backtest_resolution": RESAMPLE_INTERVAL if RESAMPLE_INTERVAL else BACKTEST_RESOLUTION,
        "plot_frequency": PLOT_FREQUENCY,
        "environment": ENVIRONMENT,
        "trading_fees": {
            "maker_fee": MAKER_FEE,
            "taker_fee": TAKER_FEE,
            "maker_fee_pct": MAKER_FEE * 100,
            "taker_fee_pct": TAKER_FEE * 100,
            "maker_fee_wan": MAKER_FEE * 10000,
            "taker_fee_wan": TAKER_FEE * 10000,
        },
        "data_info": {
            "trading_pair": TRADING_PAIR,
            "data_points": len(candles_df),
            "actual_start": pd.to_datetime(candles_df['timestamp'].min(), unit='s').strftime("%Y-%m-%d %H:%M:%S"),
            "actual_end": pd.to_datetime(candles_df['timestamp'].max(), unit='s').strftime("%Y-%m-%d %H:%M:%S"),
            "backtest_resolution": RESAMPLE_INTERVAL if RESAMPLE_INTERVAL else BACKTEST_RESOLUTION,
        },
        "results": [r for r in results if r.get("success", False)],
    }
    
    json_file = symbol_dir / f"{TRADING_PAIR.replace('-', '_')}_{ENVIRONMENT}.json"
    with open(json_file, 'w') as f:
        json.dump(json_data, f, indent=2, default=str)
    
    print(f"✓ 结果已保存到: {json_file}")
    print()
    print("=" * 80)
    print("回测完成")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())

