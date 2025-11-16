#!/usr/bin/env python3
"""
全面诊断策略问题
检查：
1. 挂单价格计算逻辑（spread_multiplier、reference_price）
2. 盈亏计算逻辑（executor的entry/exit价格）
3. 策略执行逻辑（executor创建和成交逻辑）
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
from controllers.market_making.pmm_bar_portion import PMMBarPortionController, PMMBarPortionControllerConfig
from backtest_comparison_local import LocalBinanceDataProvider, LocalBacktestingDataProvider
from hummingbot.core.data_type.common import PriceType, TradeType

# 配置
SYMBOL = "SOL-USDT"
END_DATE = datetime(2025, 11, 1)
START_DATE = END_DATE - timedelta(days=1)  # 使用1天数据

async def diagnose_order_price_calculation():
    """诊断挂单价格计算逻辑"""
    print("="*80)
    print("【1. 挂单价格计算逻辑诊断】")
    print("="*80)
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
    
    # 创建controller（修复bug）
    controller = PMMBarPortionController(
        config=config,
        market_data_provider=local_backtesting_provider,
        actions_queue=None
    )
    
    # 初始化candles feed
    await local_backtesting_provider.initialize_candles_feed([config])
    
    # 获取数据
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
    
    # 分析前5个时间点的挂单价格
    print("分析前5个时间点的挂单价格计算:")
    print()
    
    for i in range(min(5, len(candles_df))):
        # 更新时间
        if i > 0:
            next_timestamp = int(candles_df.index[i]) if hasattr(candles_df.index, '__getitem__') else int(candles_df.iloc[i].name)
            local_backtesting_provider.update_backtesting_time(next_timestamp, end_ts)
        
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
        
        # 获取当前K线
        if i < len(candles_df):
            current_candle = candles_df.iloc[i]
            candle_low = float(current_candle["low"])
            candle_high = float(current_candle["high"])
            candle_close = float(current_candle["close"])
        else:
            candle_low = candle_high = candle_close = 0
        
        # 计算挂单价格（根据MarketMakingControllerBase的逻辑）
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
        
        print(f"时间点 {i+1}:")
        print(f"  市场价格: ${market_price:.4f}")
        print(f"  参考价格: ${reference_price:.4f} (偏移: {(float(reference_price)/float(market_price)-1)*100:.4f}%)")
        print(f"  价差倍数: {spread_multiplier:.6f} (NATR)")
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
            min_buy_gap = min(abs(p - float(market_price)) for p in buy_prices)
            min_buy_gap_pct = min_buy_gap / float(market_price) * 100
            print(f"  买单与市场价最小差距: ${min_buy_gap:.4f} ({min_buy_gap_pct:.2f}%)")
        
        if sell_prices:
            min_sell_gap = min(abs(p - float(market_price)) for p in sell_prices)
            min_sell_gap_pct = min_sell_gap / float(market_price) * 100
            print(f"  卖单与市场价最小差距: ${min_sell_gap:.4f} ({min_sell_gap_pct:.2f}%)")
        
        # 检查spread_multiplier是否合理
        if float(spread_multiplier) < 0.001:
            print(f"  ⚠️  警告: spread_multiplier过小 ({spread_multiplier:.6f})，可能导致价差过窄")
        elif float(spread_multiplier) > 0.1:
            print(f"  ⚠️  警告: spread_multiplier过大 ({spread_multiplier:.6f})，可能导致价差过宽")
        
        print()
    
    return controller

async def diagnose_pnl_calculation():
    """诊断盈亏计算逻辑"""
    print("="*80)
    print("【2. 盈亏计算逻辑诊断】")
    print("="*80)
    print()
    
    # 运行回测
    local_data_provider = LocalBinanceDataProvider()
    local_backtesting_provider = LocalBacktestingDataProvider(local_data_provider)
    
    start_ts = int(START_DATE.timestamp())
    end_ts = int(END_DATE.timestamp())
    local_backtesting_provider.update_backtesting_time(start_ts, end_ts)
    
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
    
    engine = BacktestingEngineBase()
    engine.backtesting_data_provider = local_backtesting_provider
    
    print("运行回测...")
    results = await engine.run_backtesting(
        controller_config=config,
        start=start_ts,
        end=end_ts,
        backtesting_resolution="1m",
        trade_cost=0.0004,
        show_progress=False
    )
    
    executors = results.get('executors', [])
    print(f"✓ 回测完成，生成 {len(executors)} 个executor")
    print()
    
    # 分析成交的executor
    filled = [e for e in executors if float(e.filled_amount_quote) > 0]
    print(f"成交Executor数: {len(filled)}")
    print()
    
    if len(filled) == 0:
        print("❌ 没有成交的executor，无法分析盈亏计算")
        return
    
    # 详细分析前5个成交的executor
    print("前5个成交Executor的盈亏分析:")
    print()
    
    for i, executor in enumerate(filled[:5], 1):
        print(f"Executor {i}:")
        print(f"  ID: {executor.id}")
        print(f"  方向: {executor.side}")
        print(f"  创建时间: {datetime.fromtimestamp(executor.timestamp)}")
        print(f"  关闭时间: {datetime.fromtimestamp(executor.close_timestamp) if executor.close_timestamp else '未关闭'}")
        print(f"  关闭类型: {executor.close_type}")
        print(f"  成交数量: ${float(executor.filled_amount_quote):.2f}")
        print(f"  盈亏: ${float(executor.net_pnl_quote):.2f} ({float(executor.net_pnl_pct)*100:.4f}%)")
        
        # 获取entry_price和exit_price
        if hasattr(executor, 'config') and executor.config:
            ec = executor.config
            entry_price = float(ec.entry_price)
            print(f"  挂单价格(entry_price): ${entry_price:.4f}")
            
            # 尝试获取实际成交价格和退出价格
            if executor.close_timestamp:
                # 从custom_info获取信息
                custom_info = executor.custom_info
                if 'close_price' in custom_info:
                    exit_price = custom_info['close_price']
                    print(f"  退出价格(close_price): ${exit_price:.4f}")
                    
                    # 计算理论盈亏
                    if executor.side == TradeType.BUY:
                        theoretical_pnl_pct = (exit_price - entry_price) / entry_price
                    else:
                        theoretical_pnl_pct = (entry_price - exit_price) / entry_price
                    
                    print(f"  理论盈亏%: {theoretical_pnl_pct*100:.4f}%")
                    print(f"  实际盈亏%: {float(executor.net_pnl_pct)*100:.4f}%")
                    
                    if abs(theoretical_pnl_pct - float(executor.net_pnl_pct)) > 0.001:
                        print(f"  ⚠️  警告: 理论盈亏与实际盈亏不一致！")
                        print(f"     差异: {(theoretical_pnl_pct - float(executor.net_pnl_pct))*100:.4f}%")
                
                if 'current_position_average_price' in custom_info:
                    avg_price = custom_info['current_position_average_price']
                    print(f"  平均持仓价格: ${avg_price:.4f}")
        
        print()

async def diagnose_executor_creation():
    """诊断Executor创建逻辑"""
    print("="*80)
    print("【3. Executor创建和成交逻辑诊断】")
    print("="*80)
    print()
    
    # 运行回测
    local_data_provider = LocalBinanceDataProvider()
    local_backtesting_provider = LocalBacktestingDataProvider(local_data_provider)
    
    start_ts = int(START_DATE.timestamp())
    end_ts = int(END_DATE.timestamp())
    local_backtesting_provider.update_backtesting_time(start_ts, end_ts)
    
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
    
    engine = BacktestingEngineBase()
    engine.backtesting_data_provider = local_backtesting_provider
    
    print("运行回测...")
    results = await engine.run_backtesting(
        controller_config=config,
        start=start_ts,
        end=end_ts,
        backtesting_resolution="1m",
        trade_cost=0.0004,
        show_progress=False
    )
    
    executors = results.get('executors', [])
    print(f"✓ 回测完成，生成 {len(executors)} 个executor")
    print()
    
    # 统计
    total = len(executors)
    filled = [e for e in executors if float(e.filled_amount_quote) > 0]
    not_filled = [e for e in executors if float(e.filled_amount_quote) == 0]
    
    print(f"总Executor数: {total}")
    print(f"成交Executor数: {len(filled)} ({len(filled)/total*100:.2f}%)")
    print(f"未成交Executor数: {len(not_filled)} ({len(not_filled)/total*100:.2f}%)")
    print()
    
    # 分析关闭类型
    print("关闭类型统计:")
    close_types = {}
    for executor in executors:
        ct = executor.close_type.name if executor.close_type else 'UNKNOWN'
        close_types[ct] = close_types.get(ct, 0) + 1
    
    for ct, count in sorted(close_types.items(), key=lambda x: x[1], reverse=True):
        print(f"  {ct}: {count} ({count/total*100:.2f}%)")
    print()
    
    # 分析未成交的原因
    print("未成交Executor分析（前10个）:")
    print()
    
    for i, executor in enumerate(not_filled[:10], 1):
        print(f"Executor {i}:")
        print(f"  方向: {executor.side}")
        print(f"  关闭类型: {executor.close_type}")
        
        if hasattr(executor, 'config') and executor.config:
            ec = executor.config
            entry_price = float(ec.entry_price)
            print(f"  挂单价格: ${entry_price:.4f}")
            
            # 检查挂单价格是否合理
            # 获取该时间点的市场价格
            exec_timestamp = executor.timestamp
            try:
                # 从candles获取价格
                local_backtesting_provider.update_backtesting_time(int(exec_timestamp), end_ts)
                market_price = float(local_backtesting_provider.get_price_by_type(
                    config.candles_connector,
                    config.candles_trading_pair,
                    PriceType.MidPrice
                ))
                
                price_gap = abs(entry_price - market_price)
                price_gap_pct = price_gap / market_price * 100
                
                print(f"  市场价格: ${market_price:.4f}")
                print(f"  价格差距: ${price_gap:.4f} ({price_gap_pct:.2f}%)")
                
                if price_gap_pct > 1.0:
                    print(f"  ⚠️  警告: 挂单价格与市场价格差距过大，可能导致无法成交")
            except Exception as e:
                print(f"  无法获取市场价格: {e}")
        
        print()

async def main():
    """主函数"""
    print("="*80)
    print("策略问题全面诊断")
    print("="*80)
    print()
    print(f"交易对: {SYMBOL}")
    print(f"时间区间: {START_DATE.strftime('%Y-%m-%d')} 至 {END_DATE.strftime('%Y-%m-%d')}")
    print()
    
    # 1. 诊断挂单价格计算
    await diagnose_order_price_calculation()
    
    # 2. 诊断盈亏计算
    await diagnose_pnl_calculation()
    
    # 3. 诊断Executor创建
    await diagnose_executor_creation()
    
    print("="*80)
    print("诊断完成")
    print("="*80)

if __name__ == "__main__":
    asyncio.run(main())

