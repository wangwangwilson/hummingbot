#!/usr/bin/env python3
"""
调试PMM Bar Portion策略的因子生成和挂单价格计算
打印Bar Portion因子值，检查挂单价格是否合理
"""

import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path
import pandas as pd
import numpy as np

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

from hummingbot.data_feed.candles_feed.data_types import CandlesConfig
from controllers.market_making.pmm_bar_portion import PMMBarPortionControllerConfig, PMMBarPortionController
from hummingbot.strategy_v2.executors.position_executor.data_types import OrderType
from hummingbot.core.data_type.common import PriceType

# 导入本地数据管理器
from backtest_comparison_local import LocalBinanceDataProvider, LocalBacktestingDataProvider

# 测试参数
SYMBOL = "SOL-USDT"
START_DATE = datetime(2025, 10, 11)
END_DATE = datetime(2025, 10, 12)  # 1天数据用于详细分析（使用已验证的日期范围）

def analyze_bp_factor_and_orders():
    """分析BP因子和挂单价格"""
    print("="*80)
    print("PMM Bar Portion策略因子和挂单价格分析")
    print("="*80)
    print()
    print(f"交易对: {SYMBOL}")
    print(f"时间范围: {START_DATE.strftime('%Y-%m-%d')} 至 {END_DATE.strftime('%Y-%m-%d')}")
    print()
    
    # 初始化数据提供器
    local_data_provider = LocalBinanceDataProvider()
    local_backtesting_provider = LocalBacktestingDataProvider(local_data_provider)
    
    start_ts = int(START_DATE.timestamp())
    end_ts = int(END_DATE.timestamp())
    local_backtesting_provider.update_backtesting_time(start_ts, end_ts)
    
    # 加载数据
    print("加载数据...")
    test_df = local_data_provider.get_historical_candles(
        symbol=SYMBOL,
        start_ts=start_ts,
        end_ts=end_ts,
        interval="1m"
    )
    print(f"✓ 数据量: {len(test_df):,} 条K线")
    print()
    
    if len(test_df) == 0:
        print("✗ 数据加载失败")
        return
    
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
    
    # 创建控制器
    controller = PMMBarPortionController(
        config=config,
        market_data_provider=local_backtesting_provider,
        actions_queue=None
    )
    
    # 直接使用local_data_provider获取数据
    print("="*80)
    print("分析BP因子和挂单价格（前100根K线）")
    print("="*80)
    print()
    
    # 获取candles数据（直接使用local_data_provider）
    candles_df = local_data_provider.get_historical_candles(
        symbol=SYMBOL,
        start_ts=start_ts,
        end_ts=end_ts,
        interval="1m"
    )
    if candles_df is None or len(candles_df) == 0:
        print("✗ 无法获取candles数据")
        return
    
    # 确保timestamp是int64类型，并设置为索引
    if 'timestamp' in candles_df.columns:
        if pd.api.types.is_datetime64_any_dtype(candles_df['timestamp']):
            candles_df['timestamp'] = pd.to_datetime(candles_df['timestamp']).astype('int64') // 10**9
        else:
            candles_df['timestamp'] = candles_df['timestamp'].astype('int64')
        candles_df = candles_df.set_index('timestamp')
    elif candles_df.index.name == 'timestamp' or (isinstance(candles_df.index, pd.Index) and pd.api.types.is_integer_dtype(candles_df.index)):
        # timestamp已经是索引
        candles_df.index = candles_df.index.astype('int64')
    
    # 初始化candles feed（异步）- 用于controller
    import asyncio
    candles_config = CandlesConfig(
        connector=config.candles_connector,
        trading_pair=config.candles_trading_pair,
        interval=config.interval,
        max_records=config.training_window + 1000
    )
    asyncio.run(local_backtesting_provider.initialize_candles_feed([candles_config]))
    
    # 分析前100根K线（或所有可用数据）
    analysis_count = min(100, len(candles_df))
    
    print(f"{'时间':<20} {'O':<10} {'H':<10} {'L':<10} {'C':<10} {'BP':<10} {'RefPrice':<12} {'SpreadMult':<12} {'Buy1':<10} {'Sell1':<10} {'Market':<10} {'BuyGap%':<10} {'SellGap%':<10}")
    print("-" * 140)
    
    issues = []
    
    for i in range(analysis_count):
        # 获取到当前时间的数据
        current_candles = candles_df.iloc[:i+1].copy()
        
        if len(current_candles) < 2:
            continue
        
        # 获取当前K线
        current_candle = current_candles.iloc[-1]
        current_time = current_candle.name if hasattr(current_candle, 'name') else i
        
        # 更新processed_data（异步）
        try:
            # 需要先更新market_data_provider的时间
            if isinstance(current_time, (int, float)):
                local_backtesting_provider._time = int(current_time)
            
            # 调用异步方法
            asyncio.run(controller.update_processed_data())
        except Exception as e:
            print(f"  ⚠️  更新processed_data失败 (i={i}): {e}")
            continue
        
        # 获取processed_data
        processed_data = controller.processed_data
        if not processed_data:
            # 如果processed_data为空，尝试手动计算BP因子
            if len(current_candles) >= 2:
                # 手动计算BP因子
                high_low_diff = current_candles["high"] - current_candles["low"]
                high_low_diff = high_low_diff.replace(0, np.nan)
                bar_portion = (current_candles["close"] - current_candles["open"]) / high_low_diff
                bar_portion = bar_portion.clip(-1, 1).fillna(0)
                
                bp_value = bar_portion.iloc[-1] if len(bar_portion) > 0 else np.nan
                reference_price = float(current_candle['close'])
                spread_multiplier = 0.01  # 默认值
            else:
                continue
        else:
            features = processed_data.get('features', pd.DataFrame())
            if features.empty or len(features) == 0:
                # 如果features为空，使用当前K线数据
                if len(current_candles) >= 2:
                    high_low_diff = current_candles["high"] - current_candles["low"]
                    high_low_diff = high_low_diff.replace(0, np.nan)
                    bar_portion = (current_candles["close"] - current_candles["open"]) / high_low_diff
                    bar_portion = bar_portion.clip(-1, 1).fillna(0)
                    bp_value = bar_portion.iloc[-1] if len(bar_portion) > 0 else np.nan
                    reference_price = float(processed_data.get('reference_price', current_candle['close']))
                    spread_multiplier = float(processed_data.get('spread_multiplier', 0.01))
                else:
                    continue
            else:
                # 获取最新的特征值
                latest_features = features.iloc[-1] if len(features) > 0 else None
                if latest_features is None:
                    continue
                
                # 提取BP因子
                bp_value = latest_features.get('bar_portion', np.nan) if hasattr(latest_features, 'get') else getattr(latest_features, 'bar_portion', np.nan)
                reference_price = float(processed_data.get('reference_price', current_candle['close']))
                spread_multiplier = float(processed_data.get('spread_multiplier', 0.01))
        
        # 计算挂单价格
        try:
            # 获取买1和卖1的价格
            buy_spreads = config.buy_spreads
            sell_spreads = config.sell_spreads
            
            # 计算挂单价格（使用controller的方法）
            buy_price_1 = None
            sell_price_1 = None
            
            try:
                # 获取level_id对应的价格
                buy_level_1_id = f"buy_{config.buy_spreads[0]}"
                sell_level_1_id = f"sell_{config.sell_spreads[0]}"
                
                buy_price_1, buy_amount_1 = controller.get_price_and_amount(buy_level_1_id)
                sell_price_1, sell_amount_1 = controller.get_price_and_amount(sell_level_1_id)
                
                buy_price_1 = float(buy_price_1) if buy_price_1 else None
                sell_price_1 = float(sell_price_1) if sell_price_1 else None
            except Exception as e:
                # 如果无法通过controller获取，手动计算
                if reference_price > 0:
                    # 价差以波动率单位计算，需要乘以spread_multiplier
                    buy_spread_pct = buy_spreads[0] * spread_multiplier if spread_multiplier > 0 else buy_spreads[0] * 0.01
                    sell_spread_pct = sell_spreads[0] * spread_multiplier if spread_multiplier > 0 else sell_spreads[0] * 0.01
                    
                    buy_price_1 = reference_price * (1 - buy_spread_pct)
                    sell_price_1 = reference_price * (1 + sell_spread_pct)
            
            # 获取当前市场价格（使用close价格）
            market_price = float(current_candle['close'])
            
            # 计算挂单价格与市场价格的差距
            buy_gap_pct = ((market_price - buy_price_1) / market_price * 100) if buy_price_1 else None
            sell_gap_pct = ((sell_price_1 - market_price) / market_price * 100) if sell_price_1 else None
            
            # 格式化时间
            if isinstance(current_time, (int, float)):
                time_str = datetime.fromtimestamp(current_time).strftime('%Y-%m-%d %H:%M')
            else:
                time_str = str(current_time)[:19]
            
            # 打印信息
            print(f"{time_str:<20} {current_candle['open']:<10.4f} {current_candle['high']:<10.4f} {current_candle['low']:<10.4f} {current_candle['close']:<10.4f} {bp_value:<10.4f} {reference_price:<12.4f} {spread_multiplier:<12.6f} {buy_price_1:<10.4f} {sell_price_1:<10.4f} {market_price:<10.4f} {buy_gap_pct:<10.4f} {sell_gap_pct:<10.4f}")
            
            # 检查问题
            if pd.isna(bp_value) or abs(bp_value) > 1.1:
                issues.append(f"时间 {time_str}: BP值异常 ({bp_value})")
            
            if reference_price == 0:
                issues.append(f"时间 {time_str}: reference_price为0")
            
            if spread_multiplier <= 0 or spread_multiplier > 10:
                issues.append(f"时间 {time_str}: spread_multiplier异常 ({spread_multiplier})")
            
            if buy_price_1 and buy_gap_pct:
                if buy_gap_pct < 0:
                    issues.append(f"时间 {time_str}: 买单价格高于市场价格 ({buy_gap_pct:.2f}%)")
                elif buy_gap_pct > 5:
                    issues.append(f"时间 {time_str}: 买单价格距离市场过远 ({buy_gap_pct:.2f}%)")
            
            if sell_price_1 and sell_gap_pct:
                if sell_gap_pct < 0:
                    issues.append(f"时间 {time_str}: 卖单价格低于市场价格 ({sell_gap_pct:.2f}%)")
                elif sell_gap_pct > 5:
                    issues.append(f"时间 {time_str}: 卖单价格距离市场过远 ({sell_gap_pct:.2f}%)")
            
        except Exception as e:
            print(f"  ⚠️  计算挂单价格失败 (i={i}): {e}")
            import traceback
            traceback.print_exc()
            continue
    
    print()
    print("="*80)
    print("问题汇总")
    print("="*80)
    print()
    
    if issues:
        print(f"发现 {len(issues)} 个问题:")
        for issue in issues[:20]:  # 只显示前20个
            print(f"  - {issue}")
        if len(issues) > 20:
            print(f"  ... 还有 {len(issues) - 20} 个问题")
    else:
        print("✓ 未发现明显问题")
    
    print()
    
    # 统计分析
    print("="*80)
    print("统计分析")
    print("="*80)
    print()
    
    # 重新分析以收集统计数据
    bp_values = []
    ref_prices = []
    spread_mults = []
    buy_gaps = []
    sell_gaps = []
    
    for i in range(min(100, len(candles_df))):
        current_candles = candles_df.iloc[:i+1].copy()
        if len(current_candles) < 2:
            continue
        
        try:
            # 更新market_data_provider的时间
            if isinstance(current_time, (int, float)):
                local_backtesting_provider._time = int(current_time)
            
            # 调用异步方法
            asyncio.run(controller.update_processed_data())
            processed_data = controller.processed_data
            
            if processed_data and 'features' in processed_data:
                features = processed_data.get('features', pd.DataFrame())
                if not features.empty:
                    latest_features = features.iloc[-1]
                    bp_value = latest_features.get('bar_portion', np.nan) if hasattr(latest_features, 'get') else getattr(latest_features, 'bar_portion', np.nan)
                    if not pd.isna(bp_value):
                        bp_values.append(bp_value)
                    
                    ref_price = processed_data.get('reference_price', 0)
                    if ref_price > 0:
                        ref_prices.append(ref_price)
                    
                    spread_mult = processed_data.get('spread_multiplier', 1.0)
                    if spread_mult > 0:
                        spread_mults.append(spread_mult)
        except:
            continue
    
    if bp_values:
        print(f"BP因子统计:")
        print(f"  数量: {len(bp_values)}")
        print(f"  范围: {min(bp_values):.4f} 至 {max(bp_values):.4f}")
        print(f"  均值: {np.mean(bp_values):.4f}")
        print(f"  标准差: {np.std(bp_values):.4f}")
        print(f"  符合预期(-1到+1): {sum(-1 <= v <= 1 for v in bp_values)}/{len(bp_values)} ({sum(-1 <= v <= 1 for v in bp_values)/len(bp_values)*100:.1f}%)")
    
    if ref_prices:
        print(f"\nReference Price统计:")
        print(f"  数量: {len(ref_prices)}")
        print(f"  范围: ${min(ref_prices):.4f} 至 ${max(ref_prices):.4f}")
        print(f"  均值: ${np.mean(ref_prices):.4f}")
    
    if spread_mults:
        print(f"\nSpread Multiplier统计:")
        print(f"  数量: {len(spread_mults)}")
        print(f"  范围: {min(spread_mults):.6f} 至 {max(spread_mults):.6f}")
        print(f"  均值: {np.mean(spread_mults):.6f}")
        print(f"  中位数: {np.median(spread_mults):.6f}")
    
    print()

if __name__ == "__main__":
    analyze_bp_factor_and_orders()

