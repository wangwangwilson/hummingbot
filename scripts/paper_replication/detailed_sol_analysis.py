#!/usr/bin/env python3
"""
SOL详细回测分析脚本
时间区间: 2025-09-01 至 2025-11-01
分析内容:
1. 数据准备检查
2. 因子生成检查
3. 挂单价格检查
4. 成交条件检查
5. Executor创建和关闭逻辑
"""

import asyncio
import sys
import time
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Dict, List

import pandas as pd
import numpy as np

# 添加路径
sys.path.insert(0, '/Users/wilson/Desktop/tradingview-ai')

class FakeCCXT:
    pass
sys.modules['ccxt'] = FakeCCXT()

from src.data.sources.binance_public_data_manager import BinancePublicDataManager

sys.path.insert(0, '/Users/wilson/Desktop/mm_research/hummingbot')

from hummingbot.strategy_v2.backtesting.backtesting_engine_base import BacktestingEngineBase
from controllers.market_making.pmm_bar_portion import PMMBarPortionControllerConfig, PMMBarPortionController
from controllers.market_making.pmm_dynamic import PMMDynamicControllerConfig, PMMDynamicController
from hummingbot.core.data_type.common import TradeType
from hummingbot.strategy_v2.executors.position_executor.data_types import OrderType
from backtest_comparison_local import LocalBinanceDataProvider, LocalBacktestingDataProvider

# 回测配置
SYMBOL = "SOL-USDT"
START_DATE = datetime(2025, 9, 1)
END_DATE = datetime(2025, 11, 1)

def create_bp_config(trading_pair: str, total_amount: Decimal) -> PMMBarPortionControllerConfig:
    """创建PMM Bar Portion策略配置"""
    return PMMBarPortionControllerConfig(
        controller_name="pmm_bar_portion",
        connector_name="binance_perpetual",
        trading_pair=trading_pair,
        total_amount_quote=total_amount,
        buy_spreads=[0.01, 0.02],
        sell_spreads=[0.01, 0.02],
        buy_amounts_pct=[0.5, 0.5],
        sell_amounts_pct=[0.5, 0.5],
        candles_connector="binance_perpetual",
        candles_trading_pair=trading_pair,
        interval="1m",
        stop_loss=Decimal("0.03"),
        take_profit=Decimal("0.02"),
        time_limit=45 * 60,
    )

async def analyze_data_preparation():
    """分析数据准备"""
    print("="*80)
    print("【1. 数据准备分析】")
    print("="*80)
    print()
    
    # 初始化数据提供器
    local_data_provider = LocalBinanceDataProvider()
    
    start_ts = int(START_DATE.timestamp())
    end_ts = int(END_DATE.timestamp())
    
    print(f"时间范围: {START_DATE.strftime('%Y-%m-%d')} 至 {END_DATE.strftime('%Y-%m-%d')}")
    print(f"时间戳: {start_ts} 至 {end_ts}")
    print()
    
    # 获取数据
    print("加载K线数据...")
    data_start = time.time()
    candles_df = local_data_provider.get_historical_candles(
        symbol=SYMBOL,
        start_ts=start_ts,
        end_ts=end_ts,
        interval="1m"
    )
    data_elapsed = time.time() - data_start
    
    print(f"✓ 数据量: {len(candles_df):,} 条K线")
    print(f"✓ 加载时间: {data_elapsed:.2f}秒")
    print()
    
    if len(candles_df) == 0:
        print("✗ 数据为空！")
        return None
    
    # 检查数据质量
    print("数据质量检查:")
    print(f"  时间范围: {datetime.fromtimestamp(candles_df['timestamp'].min())} 至 {datetime.fromtimestamp(candles_df['timestamp'].max())}")
    print(f"  缺失值: {candles_df.isnull().sum().sum()}")
    print(f"  价格范围: ${candles_df['close'].min():.4f} - ${candles_df['close'].max():.4f}")
    print(f"  平均价格: ${candles_df['close'].mean():.4f}")
    print(f"  价格波动: {candles_df['close'].std():.4f}")
    print()
    
    # 检查数据连续性
    print("数据连续性检查:")
    timestamps = candles_df['timestamp'].values
    expected_interval = 60  # 1分钟 = 60秒
    gaps = []
    for i in range(1, len(timestamps)):
        diff = timestamps[i] - timestamps[i-1]
        if diff > expected_interval * 1.5:  # 允许50%的误差
            gaps.append((i, diff))
    
    if gaps:
        print(f"  ⚠️  发现 {len(gaps)} 个时间间隔异常")
        for idx, diff in gaps[:5]:  # 只显示前5个
            print(f"    位置 {idx}: 间隔 {diff}秒 (预期 {expected_interval}秒)")
    else:
        print("  ✓ 数据连续性正常")
    print()
    
    return candles_df

async def analyze_feature_generation(candles_df: pd.DataFrame):
    """分析因子生成"""
    print("="*80)
    print("【2. 因子生成分析】")
    print("="*80)
    print()
    
    # 初始化控制器
    config = create_bp_config(SYMBOL, Decimal("10000"))
    local_data_provider = LocalBinanceDataProvider()
    local_backtesting_provider = LocalBacktestingDataProvider(local_data_provider)
    
    # 设置回测时间范围
    start_ts = int(START_DATE.timestamp())
    end_ts = int(END_DATE.timestamp())
    local_backtesting_provider.update_backtesting_time(start_ts, end_ts)
    
    controller = PMMBarPortionController(
        config=config,
        market_data_provider=local_backtesting_provider,
        actions_queue=None
    )
    
    # 初始化candles feed（确保数据可用）
    print("初始化candles feed...")
    from hummingbot.data_feed.candles_feed.data_types import CandlesConfig
    candles_config = CandlesConfig(
        connector=config.candles_connector,
        trading_pair=config.candles_trading_pair,
        interval=config.interval
    )
    await local_backtesting_provider.initialize_candles_feed(candles_config)
    
    # 更新processed_data
    print("生成因子...")
    await controller.update_processed_data()
    
    processed_data = controller.processed_data
    print(f"✓ 因子生成完成")
    print()
    
    # 检查因子
    print("因子检查:")
    if 'features' in processed_data:
        features = processed_data['features']
        if isinstance(features, pd.DataFrame):
            print(f"  特征数据量: {len(features)} 行")
            print(f"  特征列: {list(features.columns)}")
            
            if len(features) > 0:
                print(f"  最新特征:")
                if isinstance(features.index, pd.DatetimeIndex):
                    print(f"    timestamp: {features.index[-1]}")
                elif 'timestamp' in features.columns:
                    print(f"    timestamp: {features['timestamp'].iloc[-1]}")
                else:
                    print(f"    timestamp: {features.index[-1] if hasattr(features.index, '__getitem__') else 'N/A'}")
                if 'close' in features.columns:
                    print(f"    close: ${features['close'].iloc[-1]:.4f}")
                if 'bar_portion' in features.columns:
                    print(f"    bar_portion: {features['bar_portion'].iloc[-1]:.4f}")
        else:
            print("  ⚠️  features不是DataFrame")
    else:
        print("  ⚠️  没有features")
    
    if 'reference_price' in processed_data:
        ref_price = float(processed_data['reference_price'])
        print(f"  reference_price: ${ref_price:.4f}")
        if ref_price == 0:
            print("  ⚠️  警告: reference_price为0，可能数据未正确加载")
    if 'spread_multiplier' in processed_data:
        print(f"  spread_multiplier: {float(processed_data['spread_multiplier']):.4f}")
    print()
    
    return controller

async def analyze_order_placement(controller: PMMBarPortionController, candles_df: pd.DataFrame):
    """分析挂单逻辑"""
    print("="*80)
    print("【3. 挂单逻辑分析】")
    print("="*80)
    print()
    
    # 获取当前价格
    ref_price = controller.processed_data.get('reference_price', Decimal(0))
    if ref_price == 0 or float(ref_price) == 0:
        # 如果reference_price为0，使用最新K线价格
        current_price = float(candles_df['close'].iloc[-1])
        print(f"⚠️  reference_price为0，使用最新K线价格: ${current_price:.4f}")
    else:
        current_price = float(ref_price)
        print(f"当前参考价格: ${current_price:.4f}")
    print()
    
    # 分析挂单价格
    print("挂单价格分析:")
    config = controller.config
    
    # 买单价
    buy_spreads = config.buy_spreads
    buy_amounts_pct = config.buy_amounts_pct
    print(f"  买单配置:")
    for i, (spread, amount_pct) in enumerate(zip(buy_spreads, buy_amounts_pct)):
        buy_price = current_price * (1 - float(spread))
        buy_amount = float(config.total_amount_quote) * float(amount_pct)
        print(f"    买单{i+1}: 价格 ${buy_price:.4f} (spread: {float(spread)*100:.2f}%), 数量: ${buy_amount:.2f}")
    
    # 卖单价
    sell_spreads = config.sell_spreads
    sell_amounts_pct = config.sell_amounts_pct
    print(f"  卖单配置:")
    for i, (spread, amount_pct) in enumerate(zip(sell_spreads, sell_amounts_pct)):
        sell_price = current_price * (1 + float(spread))
        sell_amount = float(config.total_amount_quote) * float(amount_pct)
        print(f"    卖单{i+1}: 价格 ${sell_price:.4f} (spread: {float(spread)*100:.2f}%), 数量: ${sell_amount:.2f}")
    print()
    
    # 检查市场价格是否在挂单范围内
    print("市场价格与挂单价格对比:")
    sample_prices = candles_df['close'].tail(100)  # 最近100个价格
    min_price = sample_prices.min()
    max_price = sample_prices.max()
    
    lowest_buy = current_price * (1 - max([float(s) for s in buy_spreads]))
    highest_sell = current_price * (1 + max([float(s) for s in sell_spreads]))
    highest_buy = current_price * (1 - min([float(s) for s in buy_spreads]))
    lowest_sell = current_price * (1 + min([float(s) for s in sell_spreads]))
    
    print(f"  最近100个K线的价格范围: ${min_price:.4f} - ${max_price:.4f}")
    print(f"  最低买单价: ${lowest_buy:.4f}")
    print(f"  最高卖单价: ${highest_sell:.4f}")
    print()
    
    # 检查是否有价格触及挂单
    buy_touches = ((sample_prices <= highest_buy) & (sample_prices >= lowest_buy)).sum()
    sell_touches = ((sample_prices >= lowest_sell) & (sample_prices <= highest_sell)).sum()
    
    print(f"  价格触及买单范围: {buy_touches} 次")
    print(f"  价格触及卖单范围: {sell_touches} 次")
    print()
    
    if buy_touches == 0 and sell_touches == 0:
        print("  ⚠️  警告: 市场价格从未触及挂单范围！")
        print("  可能原因:")
        print("    - 挂单价格设置不合理（spread太小或太大）")
        print("    - 市场价格波动不够")
        print("    - 参考价格计算有问题")
    print()

async def analyze_executor_creation(controller: PMMBarPortionController):
    """分析Executor创建逻辑"""
    print("="*80)
    print("【4. Executor创建逻辑分析】")
    print("="*80)
    print()
    
    print("Executor概念说明:")
    print("  - Executor是策略执行单元，代表一个订单的执行")
    print("  - 每个Executor包含: 方向(买/卖)、价格、数量、止损/止盈、时间限制")
    print("  - Executor会在满足条件时创建，在达到止损/止盈/时间限制时关闭")
    print("  - 在回测中，Executor会模拟订单执行，计算盈亏")
    print()
    
    # 检查processed_data
    print("检查processed_data:")
    ref_price = controller.processed_data.get('reference_price', Decimal(0))
    print(f"  reference_price: ${float(ref_price):.4f}")
    if ref_price == 0 or float(ref_price) == 0:
        print("  ⚠️  警告: reference_price为0，无法创建executor")
        print("  原因: get_price_and_amount会计算order_price = reference_price * (1 + spread)")
        print("  如果reference_price为0，order_price也会是0，导致除零错误")
        print()
        return
    
    # 获取executor actions
    print("检查executor创建逻辑...")
    try:
        actions = controller.determine_executor_actions()
        print(f"  当前executor actions数量: {len(actions)}")
        
        if len(actions) > 0:
            print("  创建的executor:")
            for i, action in enumerate(actions[:5], 1):  # 只显示前5个
                if hasattr(action, 'executor_config'):
                    config = action.executor_config
                    print(f"    Executor {i}:")
                    print(f"      方向: {config.side}")
                    print(f"      价格: ${float(config.entry_price):.4f}")
                    print(f"      数量: {float(config.amount):.6f}")
                    if hasattr(config, 'triple_barrier_config'):
                        tbc = config.triple_barrier_config
                        print(f"      止损: {tbc.stop_loss}")
                        print(f"      止盈: {tbc.take_profit}")
                        print(f"      时间限制: {tbc.time_limit}秒")
        else:
            print("  ⚠️  没有创建executor")
            print("  可能原因:")
            print("    - 所有level都有活跃的executor")
            print("    - 策略条件不满足")
    except Exception as e:
        print(f"  ✗ 创建executor时出错: {e}")
        import traceback
        traceback.print_exc()
    print()

async def run_detailed_backtest():
    """运行详细回测并分析"""
    print("="*80)
    print("【5. 详细回测分析】")
    print("="*80)
    print()
    
    # 初始化
    local_data_provider = LocalBinanceDataProvider()
    local_backtesting_provider = LocalBacktestingDataProvider(local_data_provider)
    
    start_ts = int(START_DATE.timestamp())
    end_ts = int(END_DATE.timestamp())
    local_backtesting_provider.update_backtesting_time(start_ts, end_ts)
    
    config = create_bp_config(SYMBOL, Decimal("10000"))
    
    # 创建引擎
    engine = BacktestingEngineBase()
    engine.backtesting_data_provider = local_backtesting_provider
    
    print("运行回测...")
    results = await engine.run_backtesting(
        controller_config=config,
        start=start_ts,
        end=end_ts,
        backtesting_resolution="1m",
        trade_cost=0.0004,
        show_progress=True
    )
    
    executors = results.get('executors', [])
    print()
    print(f"✓ 回测完成，生成 {len(executors)} 个executor")
    print()
    
    # 详细分析executor
    print("Executor详细分析:")
    print("-" * 80)
    
    if len(executors) == 0:
        print("  ⚠️  没有生成任何executor！")
        return
    
    # 统计信息
    filled = [e for e in executors if hasattr(e, 'filled_amount_quote') and float(e.filled_amount_quote) > 0]
    print(f"  总executor数: {len(executors)}")
    print(f"  成交executor数: {len(filled)} ({len(filled)/len(executors)*100:.2f}%)")
    print()
    
    # 分析前10个executor
    print("前10个executor详情:")
    for i, executor in enumerate(executors[:10], 1):
        print(f"  Executor {i}:")
        print(f"    ID: {executor.id}")
        print(f"    方向: {executor.side}")
        print(f"    创建时间: {datetime.fromtimestamp(executor.timestamp)}")
        print(f"    关闭时间: {datetime.fromtimestamp(executor.close_timestamp) if executor.close_timestamp else '未关闭'}")
        print(f"    关闭类型: {executor.close_type}")
        print(f"    成交数量: ${float(executor.filled_amount_quote):.2f}")
        print(f"    盈亏: ${float(executor.net_pnl_quote):.2f} ({float(executor.net_pnl_pct)*100:.2f}%)")
        print(f"    是否活跃: {executor.is_active}")
        print(f"    是否交易: {executor.is_trading}")
        
        if hasattr(executor, 'config') and executor.config:
            ec = executor.config
            print(f"    挂单价格: ${float(ec.entry_price):.4f}")
            if hasattr(ec, 'triple_barrier_config'):
                tbc = ec.triple_barrier_config
                print(f"    止损: {tbc.stop_loss}, 止盈: {tbc.take_profit}, 时间限制: {tbc.time_limit}秒")
        print()
    
    # 分析关闭类型
    print("关闭类型统计:")
    close_types = {}
    for executor in executors:
        ct = executor.close_type.name if executor.close_type else 'UNKNOWN'
        close_types[ct] = close_types.get(ct, 0) + 1
    
    for ct, count in close_types.items():
        print(f"  {ct}: {count} ({count/len(executors)*100:.2f}%)")
    print()
    
    # 分析为什么没有成交
    print("未成交原因分析:")
    not_filled = [e for e in executors if not (hasattr(e, 'filled_amount_quote') and float(e.filled_amount_quote) > 0)]
    print(f"  未成交executor数: {len(not_filled)}")
    
    if len(not_filled) > 0:
        # 分析未成交的关闭类型
        not_filled_close_types = {}
        for executor in not_filled:
            ct = executor.close_type.name if executor.close_type else 'UNKNOWN'
            not_filled_close_types[ct] = not_filled_close_types.get(ct, 0) + 1
        
        print("  未成交executor的关闭类型:")
        for ct, count in not_filled_close_types.items():
            print(f"    {ct}: {count}")
        
        # 检查挂单价格
        print("  未成交executor的挂单价格分析:")
        buy_prices = []
        sell_prices = []
        for executor in not_filled[:20]:  # 分析前20个
            if hasattr(executor, 'config') and executor.config:
                price = float(executor.config.entry_price)
                if executor.side == TradeType.BUY:
                    buy_prices.append(price)
                else:
                    sell_prices.append(price)
        
        if buy_prices:
            print(f"    买单价范围: ${min(buy_prices):.4f} - ${max(buy_prices):.4f}")
        if sell_prices:
            print(f"    卖单价范围: ${min(sell_prices):.4f} - ${max(sell_prices):.4f}")
    print()

async def main():
    """主函数"""
    print("="*80)
    print(f"SOL详细回测分析")
    print(f"时间区间: {START_DATE.strftime('%Y-%m-%d')} 至 {END_DATE.strftime('%Y-%m-%d')}")
    print("="*80)
    print()
    
    # 1. 数据准备分析
    candles_df = await analyze_data_preparation()
    if candles_df is None:
        return
    
    # 2. 因子生成分析
    controller = await analyze_feature_generation(candles_df)
    
    # 3. 挂单逻辑分析
    await analyze_order_placement(controller, candles_df)
    
    # 4. Executor创建逻辑分析
    await analyze_executor_creation(controller)
    
    # 5. 详细回测分析
    await run_detailed_backtest()
    
    print("="*80)
    print("分析完成")
    print("="*80)

if __name__ == "__main__":
    asyncio.run(main())

