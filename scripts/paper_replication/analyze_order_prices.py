#!/usr/bin/env python3
"""
分析挂单价格与市场价格的关系
检查为什么成交率低和盈亏为0
"""

import asyncio
import sys
from datetime import datetime, timedelta
from decimal import Decimal

sys.path.insert(0, '/Users/wilson/Desktop/tradingview-ai')

class FakeCCXT:
    pass
sys.modules['ccxt'] = FakeCCXT()

from src.data.sources.binance_public_data_manager import BinancePublicDataManager

sys.path.insert(0, '/Users/wilson/Desktop/mm_research/hummingbot')

from controllers.market_making.pmm_bar_portion import PMMBarPortionController, PMMBarPortionControllerConfig
from backtest_comparison_local import LocalBinanceDataProvider, LocalBacktestingDataProvider
from hummingbot.core.data_type.common import PriceType

# 配置
SYMBOL = "SOL-USDT"
END_DATE = datetime(2025, 11, 1)
START_DATE = END_DATE - timedelta(days=1)  # 使用1天数据进行分析

async def analyze_order_prices():
    """分析挂单价格"""
    print("="*80)
    print("挂单价格分析")
    print("="*80)
    print()
    print(f"交易对: {SYMBOL}")
    print(f"时间区间: {START_DATE.strftime('%Y-%m-%d')} 至 {END_DATE.strftime('%Y-%m-%d')}")
    print()
    
    # 初始化
    local_data_provider = LocalBinanceDataProvider()
    local_backtesting_provider = LocalBacktestingDataProvider(local_data_provider)
    
    start_ts = int(START_DATE.timestamp())
    end_ts = int(END_DATE.timestamp())
    local_backtesting_provider.update_backtesting_time(start_ts, end_ts)
    
    # 创建配置
    config = PMMBarPortionControllerConfig(
        controller_name="pmm_bar_portion",
        connector_name="binance_perpetual",
        trading_pair=SYMBOL,
        total_amount_quote=Decimal("10000"),
        buy_spreads=[1.0, 2.0],
        sell_spreads=[1.0, 2.0],
        buy_amounts_pct=[0.5, 0.5],
        sell_amounts_pct=[0.5, 0.5],
        candles_connector="binance_perpetual",
        candles_trading_pair=SYMBOL,
        interval="1m",
        stop_loss=Decimal("0.03"),
        take_profit=Decimal("0.02"),
        time_limit=30 * 60,
        executor_refresh_time=300,
    )
    
    # 创建控制器
    controller = PMMBarPortionController(config)
    controller.market_data_provider = local_backtesting_provider
    
    # 初始化candles feed
    await local_backtesting_provider.initialize_candles_feed([config])
    
    # 获取数据
    print("获取市场数据...")
    candles_df = local_backtesting_provider.get_candles_df(
        connector_name=config.candles_connector,
        trading_pair=config.candles_trading_pair,
        interval=config.interval,
        max_records=1000
    )
    
    if len(candles_df) == 0:
        print("❌ 无法获取数据")
        return
    
    print(f"✓ 获取到 {len(candles_df)} 条K线数据")
    print()
    
    # 分析前10个时间点的挂单价格
    print("="*80)
    print("挂单价格分析（前10个时间点）")
    print("="*80)
    print()
    
    for i in range(min(10, len(candles_df))):
        # 更新processed_data
        await controller.update_processed_data()
        
        processed_data = controller.processed_data
        reference_price = processed_data.get("reference_price", Decimal("0"))
        spread_multiplier = processed_data.get("spread_multiplier", Decimal("0.01"))
        
        # 获取当前市场价格
        try:
            market_price = Decimal(local_backtesting_provider.get_price_by_type(
                config.candles_connector,
                config.candles_trading_pair,
                PriceType.MidPrice
            ))
        except:
            market_price = Decimal(candles_df["close"].iloc[i]) if i < len(candles_df) else Decimal("0")
        
        # 计算挂单价格
        buy_spreads = config.buy_spreads
        sell_spreads = config.sell_spreads
        
        buy_prices = []
        sell_prices = []
        
        for spread in buy_spreads:
            # spread是波动率单位，需要乘以spread_multiplier
            price_offset = float(spread_multiplier) * spread
            buy_price = float(reference_price) * (1 - price_offset)
            buy_prices.append(buy_price)
        
        for spread in sell_spreads:
            price_offset = float(spread_multiplier) * spread
            sell_price = float(reference_price) * (1 + price_offset)
            sell_prices.append(sell_price)
        
        # 获取当前K线的价格范围
        if i < len(candles_df):
            current_candle = candles_df.iloc[i]
            candle_low = float(current_candle["low"])
            candle_high = float(current_candle["high"])
            candle_close = float(current_candle["close"])
        else:
            candle_low = candle_high = candle_close = 0
        
        print(f"时间点 {i+1}:")
        print(f"  市场价格: ${market_price:.4f}")
        print(f"  参考价格: ${reference_price:.4f}")
        print(f"  价差倍数: {spread_multiplier:.6f}")
        print(f"  K线范围: ${candle_low:.4f} - ${candle_high:.4f} (收盘: ${candle_close:.4f})")
        print(f"  买单价格: {[f'${p:.4f}' for p in buy_prices]}")
        print(f"  卖单价格: {[f'${p:.4f}' for p in sell_prices]}")
        
        # 检查是否可能成交
        buy_fillable = any(candle_low <= p <= candle_high for p in buy_prices)
        sell_fillable = any(candle_low <= p <= candle_high for p in sell_prices)
        
        print(f"  买单可成交: {'✓' if buy_fillable else '✗'}")
        print(f"  卖单可成交: {'✓' if sell_fillable else '✗'}")
        
        # 计算价格差距
        if buy_prices:
            min_buy_gap = min(abs(p - market_price) for p in buy_prices)
            print(f"  买单与市场价最小差距: ${min_buy_gap:.4f} ({min_buy_gap/market_price*100:.2f}%)")
        
        if sell_prices:
            min_sell_gap = min(abs(p - market_price) for p in sell_prices)
            print(f"  卖单与市场价最小差距: ${min_sell_gap:.4f} ({min_sell_gap/market_price*100:.2f}%)")
        
        print()
        
        # 更新时间（模拟回测过程）
        if i < len(candles_df) - 1:
            next_timestamp = int(candles_df.index[i+1]) if hasattr(candles_df.index, '__getitem__') else int(candles_df.iloc[i+1].name)
            local_backtesting_provider.update_backtesting_time(next_timestamp, end_ts)
    
    print("="*80)
    print("分析总结")
    print("="*80)
    print()
    print("如果挂单价格与市场价格差距过大，可能导致：")
    print("1. 成交率低：订单无法成交")
    print("2. 盈亏为0：即使成交，价格可能回到entry_price")
    print()
    print("建议检查：")
    print("1. spread_multiplier计算是否正确（应该基于NATR）")
    print("2. reference_price计算是否正确（应该基于BP信号调整）")
    print("3. buy_spreads/sell_spreads的单位是否正确（应该是波动率单位）")
    print()

if __name__ == "__main__":
    asyncio.run(analyze_order_prices())

