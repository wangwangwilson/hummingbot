#!/usr/bin/env python3
"""
测试BinancePublicDataManager数据加载
"""

import sys
from pathlib import Path
from datetime import date, datetime

# 添加 tradingview-ai 项目路径
tradingview_ai_path = Path("/Users/wilson/Desktop/tradingview-ai")
sys.path.insert(0, str(tradingview_ai_path))

# 临时禁用ccxt
class FakeCCXT:
    pass
sys.modules['ccxt'] = FakeCCXT()

from src.data.sources.binance_public_data_manager import BinancePublicDataManager

def test_symbol_data(symbol: str, start_date: date, end_date: date):
    """测试单个交易对的数据加载"""
    print(f"\n{'='*80}")
    print(f"测试交易对: {symbol}")
    print(f"{'='*80}")
    
    manager = BinancePublicDataManager()
    
    print(f"时间范围: {start_date} 至 {end_date}")
    print("正在读取数据...")
    
    try:
        df = manager.get_klines_data(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            check_gaps=False
        )
        
        if df.empty:
            print(f"✗ 未获取到数据")
            return False
        
        print(f"✓ 成功读取数据: {len(df)} 条K线")
        print(f"  数据列: {list(df.columns)}")
        
        # 检查时间戳
        if isinstance(df.index, pd.DatetimeIndex):
            print(f"  时间范围: {df.index.min()} 至 {df.index.max()}")
            timestamps = df.index.astype('int64') // 10**9
        elif 'timestamp' in df.columns:
            print(f"  时间范围: {df['timestamp'].min()} 至 {df['timestamp'].max()}")
            timestamps = pd.to_datetime(df['timestamp']).astype('int64') // 10**9
        else:
            print(f"  ⚠️  未找到时间戳列")
            return False
        
        print(f"  时间戳范围: {timestamps.min()} 至 {timestamps.max()}")
        print(f"  对应时间: {datetime.fromtimestamp(timestamps.min())} 至 {datetime.fromtimestamp(timestamps.max())}")
        
        # 检查数据质量
        print(f"\n  数据质量:")
        print(f"    - Open价格范围: {df['open'].min():.2f} 至 {df['open'].max():.2f}")
        print(f"    - Close价格范围: {df['close'].min():.2f} 至 {df['close'].max():.2f}")
        print(f"    - 平均成交量: {df['volume'].mean():.2f}")
        print(f"    - 数据完整性: {df.isnull().sum().sum()} 个缺失值")
        
        # 显示前几条数据
        print(f"\n  前5条数据:")
        print(df.head())
        
        return True
        
    except Exception as e:
        print(f"✗ 读取失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    import pandas as pd
    
    # 测试SOL和MYX
    test_date = date(2024, 11, 11)
    end_date = date(2024, 11, 12)
    
    print("="*80)
    print("Binance Public Data 数据加载测试")
    print("="*80)
    
    results = []
    
    # 测试SOL
    results.append(("SOLUSDT", test_symbol_data("SOLUSDT", test_date, end_date)))
    
    # 测试MYX
    results.append(("MYXUSDT", test_symbol_data("MYXUSDT", test_date, end_date)))
    
    # 总结
    print(f"\n{'='*80}")
    print("测试总结")
    print(f"{'='*80}")
    
    for symbol, result in results:
        status = "✓ 通过" if result else "✗ 失败"
        print(f"{status}: {symbol}")
    
    all_passed = all(result for _, result in results)
    
    if all_passed:
        print("\n✓ 所有测试通过！数据加载正常")
    else:
        print("\n✗ 部分测试失败，请检查数据")

