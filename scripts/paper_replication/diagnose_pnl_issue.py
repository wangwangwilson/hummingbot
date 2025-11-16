#!/usr/bin/env python3
"""
诊断盈亏为0的问题
检查executor的entry_price、exit_price、PnL计算
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
END_DATE = datetime(2025, 10, 12)  # 1天数据用于快速验证

async def diagnose_pnl_issue():
    """诊断盈亏问题"""
    print("="*80)
    print("盈亏问题诊断")
    print("="*80)
    print()
    print(f"交易对: {SYMBOL}")
    print(f"时间范围: {START_DATE.strftime('%Y-%m-%d')} 至 {END_DATE.strftime('%Y-%m-%d')}")
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
        stop_loss=Decimal("0.01"),  # 1%止损
        take_profit=Decimal("0.005"),  # 0.5%止盈
        time_limit=3600,  # 1小时
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
        print("✗ 回测失败或无结果")
        return
    
    executors = result['executors']
    filled_executors = [e for e in executors if hasattr(e, 'filled_amount_quote') and e.filled_amount_quote and float(e.filled_amount_quote) > 0]
    
    print()
    print("="*80)
    print("已成交Executor详细分析")
    print("="*80)
    print()
    print(f"总Executor: {len(executors)}")
    print(f"已成交Executor: {len(filled_executors)}")
    print()
    
    if len(filled_executors) == 0:
        print("⚠ 没有已成交的executor")
        return
    
    # 分析每个已成交的executor
    for i, executor in enumerate(filled_executors[:5], 1):  # 只分析前5个
        print(f"Executor {i}:")
        print(f"  ID: {executor.id}")
        print(f"  Side: {executor.side}")
        print(f"  Entry Price (config): {executor.config.entry_price}")
        
        # 获取custom_info
        custom_info = executor.custom_info
        close_price = custom_info.get('close_price', None)
        current_position_average_price = custom_info.get('current_position_average_price', None)
        
        print(f"  Close Price: {close_price}")
        print(f"  Current Position Average Price: {current_position_average_price}")
        print(f"  Filled Amount Quote: ${float(executor.filled_amount_quote):.2f}")
        print(f"  Net PnL %: {float(executor.net_pnl_pct)*100:.4f}%")
        print(f"  Net PnL Quote: ${float(executor.net_pnl_quote):.2f}")
        print(f"  Cum Fees Quote: ${float(executor.cum_fees_quote):.2f}")
        print(f"  Close Type: {executor.close_type}")
        print(f"  Is Active: {executor.is_active}")
        
        # 手动计算理论盈亏
        if close_price and current_position_average_price:
            entry_price = float(current_position_average_price)
            exit_price = float(close_price)
            side_multiplier = 1 if executor.side == TradeType.BUY else -1
            
            # 理论收益率
            theoretical_return_pct = (exit_price - entry_price) / entry_price * side_multiplier
            # 扣除交易成本（0.04% × 2 = 0.08%）
            theoretical_net_return_pct = theoretical_return_pct - (2 * 0.0004)
            # 理论盈亏
            theoretical_pnl_quote = theoretical_net_return_pct * float(executor.filled_amount_quote)
            
            print(f"  理论计算:")
            print(f"    Entry Price: ${entry_price:.4f}")
            print(f"    Exit Price: ${exit_price:.4f}")
            print(f"    理论收益率: {theoretical_return_pct*100:.4f}%")
            print(f"    扣除交易成本后: {theoretical_net_return_pct*100:.4f}%")
            print(f"    理论盈亏: ${theoretical_pnl_quote:.2f}")
            print(f"    实际盈亏: ${float(executor.net_pnl_quote):.2f}")
            print(f"    差异: ${theoretical_pnl_quote - float(executor.net_pnl_quote):.2f}")
        
        print()
    
    # 分析问题
    print("="*80)
    print("问题分析")
    print("="*80)
    print()
    
    issues = []
    
    # 检查1: 止盈止损设置
    take_profit_pct = float(config.take_profit) * 100
    stop_loss_pct = float(config.stop_loss) * 100
    trade_cost_pct = 0.0004 * 2 * 100  # 0.08%
    
    print(f"止盈设置: {take_profit_pct:.2f}%")
    print(f"止损设置: {stop_loss_pct:.2f}%")
    print(f"交易成本: {trade_cost_pct:.2f}% (开仓+平仓)")
    print()
    
    if take_profit_pct <= trade_cost_pct:
        issues.append(f"⚠ 止盈设置({take_profit_pct:.2f}%)小于或等于交易成本({trade_cost_pct:.2f}%)，无法盈利")
        print(f"⚠ 止盈设置({take_profit_pct:.2f}%)小于或等于交易成本({trade_cost_pct:.2f}%)")
        print(f"  建议：将止盈至少设置为 {trade_cost_pct + 0.1:.2f}% 以上")
    
    # 检查2: 检查executor的entry_price和exit_price
    zero_pnl_count = sum(1 for e in filled_executors if abs(float(e.net_pnl_quote)) < 0.01)
    print(f"零盈亏executor数量: {zero_pnl_count}/{len(filled_executors)}")
    
    if zero_pnl_count > 0:
        issues.append(f"⚠ {zero_pnl_count}个executor的盈亏接近0")
        print(f"  可能原因:")
        print(f"    1. entry_price和exit_price相同或非常接近")
        print(f"    2. 止盈止损触发时价格没有变化")
        print(f"    3. 交易成本抵消了所有收益")
    
    # 检查3: 检查close_type分布
    close_types = {}
    for e in filled_executors:
        ct = str(e.close_type) if e.close_type else "None"
        close_types[ct] = close_types.get(ct, 0) + 1
    
    print()
    print(f"关闭类型分布:")
    for ct, count in close_types.items():
        print(f"  {ct}: {count}")
    
    # 检查4: 检查价格变化
    print()
    print("价格变化分析:")
    for i, executor in enumerate(filled_executors[:3], 1):
        custom_info = executor.custom_info
        entry_price = custom_info.get('current_position_average_price', None)
        exit_price = custom_info.get('close_price', None)
        
        if entry_price and exit_price:
            price_change = (float(exit_price) - float(entry_price)) / float(entry_price) * 100
            print(f"  Executor {i}: Entry=${float(entry_price):.4f}, Exit=${float(exit_price):.4f}, 变化={price_change:.4f}%")
    
    print()
    if issues:
        print("发现的问题:")
        for issue in issues:
            print(f"  - {issue}")
    else:
        print("✓ 未发现明显问题")
    
    print()
    print("="*80)
    print("建议")
    print("="*80)
    print()
    print("1. 调整止盈止损参数:")
    print(f"   - 当前止盈: {take_profit_pct:.2f}%")
    print(f"   - 当前止损: {stop_loss_pct:.2f}%")
    print(f"   - 建议止盈: 至少 {trade_cost_pct + 0.1:.2f}% (覆盖交易成本)")
    print(f"   - 建议止损: 至少 {stop_loss_pct:.2f}% (保持不变)")
    print()
    print("2. 检查executor的entry_price和exit_price:")
    print("   - 确保entry_price使用实际成交价格（close价格）")
    print("   - 确保exit_price使用实际平仓价格")
    print()
    print("3. 验证PnL计算逻辑:")
    print("   - 检查price_returns计算是否正确")
    print("   - 检查交易成本扣除是否正确")

if __name__ == "__main__":
    asyncio.run(diagnose_pnl_issue())

