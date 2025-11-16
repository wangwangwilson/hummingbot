#!/usr/bin/env python3
"""
测试修复后的ZIP文件是否能正常加载数据
"""

import sys
from pathlib import Path
from datetime import date, datetime
import pandas as pd

# 添加项目路径
tradingview_ai_path = Path("/Users/wilson/Desktop/tradingview-ai")
sys.path.insert(0, str(tradingview_ai_path))

# 临时禁用ccxt
class FakeCCXT:
    pass
sys.modules['ccxt'] = FakeCCXT()

from src.data.sources.binance_public_data_manager import BinancePublicDataManager

def test_data_loading(manager: BinancePublicDataManager, symbol: str, start_date: date, end_date: date):
    """测试数据加载"""
    print(f"\n{'='*80}")
    print(f"测试数据加载: {symbol}")
    print(f"时间范围: {start_date} 至 {end_date}")
    print(f"{'='*80}")
    
    try:
        # 加载数据
        df = manager.get_klines_data(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            check_gaps=False  # 快速检查，不检查间隔
        )
        
        if df.empty:
            print(f"  ✗ 数据加载失败：未获取到数据")
            return False
        
        print(f"  ✓ 数据加载成功")
        print(f"    数据行数: {len(df):,}")
        print(f"    数据列: {list(df.columns)}")
        
        # 检查数据范围
        if isinstance(df.index, pd.DatetimeIndex):
            actual_start = df.index.min()
            actual_end = df.index.max()
            print(f"    实际开始时间: {actual_start}")
            print(f"    实际结束时间: {actual_end}")
            
            # 检查是否包含修复后的日期范围
            target_start = pd.Timestamp(start_date)
            target_end = pd.Timestamp(end_date) + pd.Timedelta(days=1)
            
            if actual_start <= target_start and actual_end >= target_end - pd.Timedelta(days=1):
                print(f"    ✓ 数据范围符合预期（包含修复后的日期）")
            else:
                print(f"    ⚠ 数据范围可能不完整")
                print(f"      预期: {target_start.date()} 至 {target_end.date() - pd.Timedelta(days=1)}")
        
        # 检查数据质量
        if 'close' in df.columns:
            print(f"    价格范围: ${df['close'].min():.4f} - ${df['close'].max():.4f}")
            print(f"    平均价格: ${df['close'].mean():.4f}")
            print(f"    平均成交量: {df['volume'].mean():.2f}")
        
        # 检查是否有修复后的日期数据
        if isinstance(df.index, pd.DatetimeIndex):
            repaired_dates = [date(2025, 11, d) for d in range(1, 10)]
            found_dates = []
            for d in repaired_dates:
                if d in [idx.date() for idx in df.index]:
                    found_dates.append(d)
            
            if found_dates:
                print(f"    ✓ 找到修复后的日期数据: {len(found_dates)} 天")
                print(f"      日期: {', '.join([str(d) for d in found_dates[:5]])}")
                if len(found_dates) > 5:
                    print(f"      ... 还有 {len(found_dates) - 5} 天")
            else:
                print(f"    ⚠ 未找到修复后的日期数据（可能不在请求范围内）")
        
        return True
        
    except Exception as e:
        print(f"  ✗ 数据加载失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """主函数"""
    print("="*80)
    print("测试修复后的ZIP文件数据加载")
    print("="*80)
    print()
    
    # 初始化管理器
    manager = BinancePublicDataManager()
    print(f"数据目录: {manager.data_dir}")
    print()
    
    # 测试修复后的日期范围
    test_cases = [
        ("SOLUSDT", date(2025, 11, 1), date(2025, 11, 9)),  # 修复后的日期范围
        ("ETHUSDT", date(2025, 11, 1), date(2025, 11, 9)),  # 修复后的日期范围
        ("SOLUSDT", date(2025, 10, 27), date(2025, 11, 11)),  # 包含修复日期的更大范围
        ("ETHUSDT", date(2025, 10, 27), date(2025, 11, 11)),  # 包含修复日期的更大范围
    ]
    
    results = []
    for symbol, start_date, end_date in test_cases:
        success = test_data_loading(manager, symbol, start_date, end_date)
        results.append((symbol, start_date, end_date, success))
    
    # 汇总
    print()
    print("="*80)
    print("测试结果汇总")
    print("="*80)
    
    for symbol, start_date, end_date, success in results:
        status = "✓ 通过" if success else "✗ 失败"
        print(f"  {symbol} ({start_date} 至 {end_date}): {status}")
    
    all_passed = all(success for _, _, _, success in results)
    print()
    if all_passed:
        print("✓ 所有测试通过 - 修复后的文件可以正常加载数据")
    else:
        print("✗ 部分测试失败 - 需要进一步检查")
    
    print()

if __name__ == "__main__":
    main()

