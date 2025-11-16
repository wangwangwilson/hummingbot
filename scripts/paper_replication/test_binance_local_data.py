#!/usr/bin/env python3
"""
测试使用 BinancePublicDataManager 读取本地zip数据
"""

import sys
from pathlib import Path
from datetime import date, datetime, timedelta

# 添加 tradingview-ai 项目路径
tradingview_ai_path = Path("/Users/wilson/Desktop/tradingview-ai")
sys.path.insert(0, str(tradingview_ai_path))

# 临时禁用ccxt导入（如果只需要读取本地数据）
import sys
_original_modules = sys.modules.copy()

# 创建一个假的ccxt模块
class FakeCCXT:
    pass

sys.modules['ccxt'] = FakeCCXT()

try:
    from src.data.sources.binance_public_data_manager import BinancePublicDataManager
    print("✓ 成功导入 BinancePublicDataManager")
except ImportError as e:
    print(f"✗ 导入失败: {e}")
    print("提示: 如果只需要读取本地数据，ccxt不是必需的")
    sys.exit(1)


def test_read_single_symbol():
    """测试读取单个交易对数据"""
    print("\n" + "="*80)
    print("测试1: 读取单个交易对数据 (BTCUSDT)")
    print("="*80)
    
    manager = BinancePublicDataManager()
    
    # 测试读取最近1天的数据
    end_date = date(2024, 11, 12)
    start_date = date(2024, 11, 11)
    
    print(f"\n时间范围: {start_date} 至 {end_date}")
    print("正在读取数据...")
    
    try:
        df = manager.get_klines_data(
            symbol='BTCUSDT',
            start_date=start_date,
            end_date=end_date,
            check_gaps=False  # 快速测试，不检查间隔
        )
        
        if not df.empty:
            print(f"\n✓ 成功读取数据: {len(df)} 条K线")
            print(f"  数据列: {list(df.columns)}")
            print(f"\n  前5条数据:")
            print(df.head())
            
            # 检查是否有timestamp列，如果没有则检查其他时间列
            if 'timestamp' in df.columns:
                print(f"  时间范围: {df['timestamp'].min()} 至 {df['timestamp'].max()}")
            elif 'open_time' in df.columns:
                print(f"  时间范围: {df['open_time'].min()} 至 {df['open_time'].max()}")
                # 转换时间戳
                if df['open_time'].dtype in ['int64', 'int32']:
                    df['timestamp'] = pd.to_datetime(df['open_time'], unit='ms')
                    print(f"  转换后时间范围: {df['timestamp'].min()} 至 {df['timestamp'].max()}")
            
            print(f"\n  数据统计:")
            print(df.describe())
            return True
        else:
            print("\n✗ 未获取到数据")
            return False
            
    except Exception as e:
        print(f"\n✗ 读取失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_read_multiple_symbols():
    """测试读取多个交易对数据"""
    print("\n" + "="*80)
    print("测试2: 读取多个交易对数据 (BTCUSDT, ETHUSDT, SOLUSDT)")
    print("="*80)
    
    manager = BinancePublicDataManager()
    
    symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']
    end_date = date(2024, 11, 12)
    start_date = date(2024, 11, 11)
    
    print(f"\n时间范围: {start_date} 至 {end_date}")
    print(f"交易对: {', '.join(symbols)}")
    print("正在并行读取数据...")
    
    try:
        results = manager.get_multiple_symbols_data(
            symbols=symbols,
            start_date=start_date,
            end_date=end_date,
            max_workers=3,
            check_gaps=False
        )
        
        print("\n读取结果:")
        success_count = 0
        for symbol, df in results.items():
            if not df.empty:
                print(f"  ✓ {symbol}: {len(df)} 条K线")
                success_count += 1
            else:
                print(f"  ✗ {symbol}: 无数据")
        
        print(f"\n成功率: {success_count}/{len(symbols)}")
        return success_count == len(symbols)
        
    except Exception as e:
        print(f"\n✗ 读取失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_check_data_format():
    """测试数据格式是否符合Hummingbot要求"""
    print("\n" + "="*80)
    print("测试3: 检查数据格式是否符合Hummingbot要求")
    print("="*80)
    
    manager = BinancePublicDataManager()
    
    end_date = date(2024, 11, 12)
    start_date = date(2024, 11, 11)
    
    try:
        df = manager.get_klines_data(
            symbol='BTCUSDT',
            start_date=start_date,
            end_date=end_date,
            check_gaps=False
        )
        
        if df.empty:
            print("✗ 无数据，无法检查格式")
            return False
        
        # 检查必需的列（timestamp可能是索引）
        required_columns = ['open', 'high', 'low', 'close', 'volume']
        missing_columns = [col for col in required_columns if col not in df.columns]
        
        if missing_columns:
            print(f"✗ 缺少必需的列: {missing_columns}")
            return False
        
        print("✓ 所有必需的列都存在")
        
        # 检查时间戳（可能是索引或列）
        if 'timestamp' in df.columns:
            timestamp_col = df['timestamp']
        elif df.index.name == 'timestamp' or isinstance(df.index, pd.DatetimeIndex):
            timestamp_col = df.index
            print("  timestamp是索引")
        else:
            print("⚠️  警告: 未找到timestamp列或索引")
            return False
        
        # 检查数据类型
        print("\n数据类型:")
        print(f"  timestamp: {timestamp_col.dtype} (应该是datetime64)")
        for col in required_columns:
            print(f"  {col}: {df[col].dtype} (应该是float64)")
        
        # 转换为Unix时间戳（秒）
        if isinstance(timestamp_col, pd.DatetimeIndex):
            timestamps = timestamp_col.astype('int64') // 10**9
        else:
            timestamps = pd.to_datetime(timestamp_col).astype('int64') // 10**9
        
        print(f"\n时间戳范围: {timestamps.min()} 至 {timestamps.max()}")
        print(f"  对应时间: {datetime.fromtimestamp(timestamps.min())} 至 {datetime.fromtimestamp(timestamps.max())}")
        
        print("\n✓ 数据格式检查通过")
        return True
        
    except Exception as e:
        print(f"\n✗ 检查失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """主函数"""
    print("="*80)
    print("Binance Public Data 本地数据读取测试")
    print("="*80)
    print(f"\n数据目录: /Users/wilson/Desktop/tradingview-ai/data/binance-public-data")
    
    results = []
    
    # 测试1: 读取单个交易对
    results.append(("单个交易对读取", test_read_single_symbol()))
    
    # 测试2: 读取多个交易对
    results.append(("多个交易对读取", test_read_multiple_symbols()))
    
    # 测试3: 检查数据格式
    results.append(("数据格式检查", test_check_data_format()))
    
    # 总结
    print("\n" + "="*80)
    print("测试总结")
    print("="*80)
    
    for test_name, result in results:
        status = "✓ 通过" if result else "✗ 失败"
        print(f"{status}: {test_name}")
    
    all_passed = all(result for _, result in results)
    
    if all_passed:
        print("\n✓ 所有测试通过！可以使用本地数据替代API调用")
    else:
        print("\n✗ 部分测试失败，请检查数据或配置")
    
    return all_passed


if __name__ == "__main__":
    import pandas as pd
    success = main()
    sys.exit(0 if success else 1)

