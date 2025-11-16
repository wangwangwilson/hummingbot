#!/usr/bin/env python3
"""
诊断数据流问题
检查get_candles_df返回的数据格式，update_processed_data的调用，processed_data的状态
"""

import sys
import asyncio
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

from hummingbot.data_feed.candles_feed.data_types import CandlesConfig
from controllers.market_making.pmm_bar_portion import PMMBarPortionControllerConfig, PMMBarPortionController
from hummingbot.strategy_v2.executors.position_executor.data_types import OrderType

# 导入本地数据管理器
from backtest_comparison_local import LocalBinanceDataProvider, LocalBacktestingDataProvider

# 测试参数
SYMBOL = "SOL-USDT"
START_DATE = datetime(2025, 10, 11)
END_DATE = datetime(2025, 10, 12)

async def diagnose_data_flow():
    """诊断数据流"""
    print("="*80)
    print("数据流诊断")
    print("="*80)
    print()
    
    # 1. 检查LocalBinanceDataProvider返回的数据格式
    print("1. 检查LocalBinanceDataProvider返回的数据格式")
    print("-" * 80)
    local_data_provider = LocalBinanceDataProvider()
    start_ts = int(START_DATE.timestamp())
    end_ts = int(END_DATE.timestamp())
    
    raw_df = local_data_provider.get_historical_candles(
        symbol=SYMBOL,
        start_ts=start_ts,
        end_ts=end_ts,
        interval="1m"
    )
    
    print(f"✓ 数据量: {len(raw_df)} 条")
    print(f"  列: {list(raw_df.columns)}")
    print(f"  索引: {raw_df.index.name if raw_df.index.name else '无名称'}")
    print(f"  数据类型: {raw_df.dtypes.to_dict()}")
    if len(raw_df) > 0:
        print(f"  前3行:")
        print(raw_df.head(3))
        print(f"  最后3行:")
        print(raw_df.tail(3))
    print()
    
    # 2. 检查LocalBacktestingDataProvider的get_candles_df
    print("2. 检查LocalBacktestingDataProvider.get_candles_df")
    print("-" * 80)
    local_backtesting_provider = LocalBacktestingDataProvider(local_data_provider)
    local_backtesting_provider.update_backtesting_time(start_ts, end_ts)
    
    # 初始化candles feed
    candles_config = CandlesConfig(
        connector="binance_perpetual",
        trading_pair=SYMBOL,
        interval="1m",
        max_records=1000
    )
    await local_backtesting_provider.initialize_candles_feed([candles_config])
    
    # 获取candles_df
    candles_df = local_backtesting_provider.get_candles_df(
        connector_name="binance_perpetual",
        trading_pair=SYMBOL,
        interval="1m",
        max_records=1000
    )
    
    print(f"✓ 数据量: {len(candles_df)} 条")
    print(f"  列: {list(candles_df.columns)}")
    print(f"  索引: {candles_df.index.name if candles_df.index.name else '无名称'}")
    print(f"  数据类型: {candles_df.dtypes.to_dict()}")
    if len(candles_df) > 0:
        print(f"  前3行:")
        print(candles_df.head(3))
        print(f"  最后3行:")
        print(candles_df.tail(3))
        print(f"  close价格范围: {candles_df['close'].min():.4f} - {candles_df['close'].max():.4f}")
    print()
    
    # 3. 检查Controller的update_processed_data
    print("3. 检查Controller.update_processed_data")
    print("-" * 80)
    
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
    
    controller = PMMBarPortionController(
        config=config,
        market_data_provider=local_backtesting_provider,
        actions_queue=None
    )
    
    # 检查初始processed_data
    print(f"初始processed_data: {controller.processed_data}")
    print()
    
    # 更新processed_data
    print("调用update_processed_data...")
    await controller.update_processed_data()
    
    # 检查更新后的processed_data
    print(f"更新后processed_data:")
    if controller.processed_data:
        print(f"  reference_price: {controller.processed_data.get('reference_price', 'N/A')}")
        print(f"  spread_multiplier: {controller.processed_data.get('spread_multiplier', 'N/A')}")
        features = controller.processed_data.get('features', pd.DataFrame())
        print(f"  features: {len(features)} 行")
        if len(features) > 0:
            print(f"    columns: {list(features.columns)}")
            print(f"    最后一行close: {features['close'].iloc[-1] if 'close' in features.columns else 'N/A'}")
    else:
        print("  processed_data为空！")
    print()
    
    # 4. 检查get_price_and_amount
    print("4. 检查get_price_and_amount")
    print("-" * 80)
    
    try:
        buy_price, buy_amount = controller.get_price_and_amount("buy_0")
        sell_price, sell_amount = controller.get_price_and_amount("sell_0")
        
        print(f"✓ Buy1价格: {buy_price}, 数量: {buy_amount}")
        print(f"✓ Sell1价格: {sell_price}, 数量: {sell_amount}")
        
        # 获取当前市场价格
        if len(candles_df) > 0:
            market_price = candles_df['close'].iloc[-1]
            print(f"  市场价格: {market_price}")
            print(f"  Buy1差距: {((market_price - float(buy_price)) / market_price * 100):.2f}%")
            print(f"  Sell1差距: {((float(sell_price) - market_price) / market_price * 100):.2f}%")
    except Exception as e:
        print(f"✗ 错误: {e}")
        import traceback
        traceback.print_exc()
    print()
    
    # 5. 检查数据流中的问题
    print("5. 问题诊断")
    print("-" * 80)
    
    issues = []
    
    # 检查1: LocalBinanceDataProvider返回的数据
    if len(raw_df) == 0:
        issues.append("LocalBinanceDataProvider返回空数据")
    elif 'close' not in raw_df.columns:
        issues.append("LocalBinanceDataProvider返回的数据缺少close列")
    elif raw_df['close'].iloc[-1] == 0:
        issues.append("LocalBinanceDataProvider返回的close价格为0")
    
    # 检查2: LocalBacktestingDataProvider.get_candles_df
    if len(candles_df) == 0:
        issues.append("LocalBacktestingDataProvider.get_candles_df返回空数据")
    elif 'close' not in candles_df.columns:
        issues.append("LocalBacktestingDataProvider.get_candles_df返回的数据缺少close列")
    elif candles_df['close'].iloc[-1] == 0:
        issues.append("LocalBacktestingDataProvider.get_candles_df返回的close价格为0")
    
    # 检查3: processed_data
    if not controller.processed_data:
        issues.append("processed_data为空")
    elif controller.processed_data.get('reference_price', 0) == 0:
        issues.append("reference_price为0")
    elif float(controller.processed_data.get('reference_price', 0)) < 1:
        issues.append(f"reference_price异常: {controller.processed_data.get('reference_price')}")
    
    # 检查4: 挂单价格
    try:
        buy_price, _ = controller.get_price_and_amount("buy_0")
        if float(buy_price) < 1:
            issues.append(f"Buy1价格异常: {buy_price}")
    except:
        pass
    
    if issues:
        print("发现的问题:")
        for i, issue in enumerate(issues, 1):
            print(f"  {i}. {issue}")
    else:
        print("✓ 未发现明显问题")
    
    print()
    print("="*80)
    print("诊断完成")
    print("="*80)

if __name__ == "__main__":
    asyncio.run(diagnose_data_flow())

