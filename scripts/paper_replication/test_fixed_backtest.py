#!/usr/bin/env python3
"""
测试修复后的回测
验证executors是否在整个时间范围内创建
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
from hummingbot.core.data_type.common import TradeType

# Import local data manager
from backtest_comparison_local import LocalBinanceDataProvider, LocalBacktestingDataProvider

# Test parameters
TRADING_PAIR = "BTC-USDT"
START_DATE = datetime(2025, 1, 1)
END_DATE = datetime(2025, 1, 10)  # 先测试10天
INITIAL_PORTFOLIO_USD = 10000
TRADING_FEE = 0.0004
BACKTEST_RESOLUTION = "1m"


async def test_fixed_backtest():
    """测试修复后的回测"""
    print("="*80)
    print("测试修复后的回测")
    print("="*80)
    print(f"交易对: {TRADING_PAIR}")
    print(f"时间范围: {START_DATE.strftime('%Y-%m-%d')} 到 {END_DATE.strftime('%Y-%m-%d')}")
    print(f"分辨率: {BACKTEST_RESOLUTION}")
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
    
    # Run backtest
    engine = BacktestingEngineBase()
    engine.backtesting_data_provider = local_backtesting_provider
    
    print("运行回测...")
    result = await engine.run_backtesting(
        controller_config=config,
        start=start_ts,
        end=end_ts,
        backtesting_resolution=BACKTEST_RESOLUTION,
        trade_cost=Decimal(str(TRADING_FEE)),
        show_progress=True
    )
    
    if not result or 'executors' not in result:
        print("✗ 回测失败")
        return
    
    executors = result['executors']
    filled_executors = [
        e for e in executors 
        if hasattr(e, 'filled_amount_quote') and e.filled_amount_quote and float(e.filled_amount_quote) > 0
    ]
    
    print(f"\n总Executors: {len(executors)}")
    print(f"已成交Executors: {len(filled_executors)}")
    
    # 分析executor的时间分布
    print(f"\n{'='*80}")
    print("Executor时间分布分析")
    print(f"{'='*80}")
    
    executor_timestamps = []
    for executor in filled_executors:
        if hasattr(executor, 'config') and hasattr(executor.config, 'timestamp'):
            ts = executor.config.timestamp
            executor_timestamps.append(ts)
    
    if executor_timestamps:
        executor_timestamps.sort()
        first_ts = min(executor_timestamps)
        last_ts = max(executor_timestamps)
        first_dt = datetime.fromtimestamp(first_ts)
        last_dt = datetime.fromtimestamp(last_ts)
        
        print(f"第一个executor: {first_dt}")
        print(f"最后一个executor: {last_dt}")
        print(f"时间跨度: {(last_ts - first_ts) / 86400:.1f} 天")
        print(f"预期时间跨度: {(end_ts - start_ts) / 86400:.1f} 天")
        
        # 检查是否分布在整个时间范围
        time_span_ratio = (last_ts - first_ts) / (end_ts - start_ts) if (end_ts - start_ts) > 0 else 0
        print(f"时间跨度比例: {time_span_ratio * 100:.1f}%")
        
        if time_span_ratio > 0.5:
            print(f"  ✓ Executors分布在整个时间范围内")
        else:
            print(f"  ⚠ Executors可能集中在部分时间")
        
        # 按天统计
        daily_counts = {}
        for ts in executor_timestamps:
            day = datetime.fromtimestamp(ts).date()
            daily_counts[day] = daily_counts.get(day, 0) + 1
        
        print(f"\n按天统计（前10天）:")
        for day, count in sorted(daily_counts.items())[:10]:
            print(f"  {day}: {count} 个executors")
        
        # 检查是否多空交替
        buy_count = sum(1 for e in filled_executors if (
            (hasattr(e, 'side') and e.side == TradeType.BUY) or
            (hasattr(e, 'config') and hasattr(e.config, 'side') and e.config.side == TradeType.BUY)
        ))
        sell_count = sum(1 for e in filled_executors if (
            (hasattr(e, 'side') and e.side == TradeType.SELL) or
            (hasattr(e, 'config') and hasattr(e.config, 'side') and e.config.side == TradeType.SELL)
        ))
        
        print(f"\n多空分布:")
        print(f"  BUY: {buy_count}")
        print(f"  SELL: {sell_count}")
        
        if buy_count > 0 and sell_count > 0:
            print(f"  ✓ 多空交替正常")
        else:
            print(f"  ⚠ 缺少多空交替")
    else:
        print("  ⚠ 没有已成交的executors")


if __name__ == "__main__":
    asyncio.run(test_fixed_backtest())
