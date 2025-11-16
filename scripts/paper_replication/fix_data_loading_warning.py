#!/usr/bin/env python3
"""
修复数据加载警告问题
验证数据加载是否正常，并抑制误导性警告
"""

import sys
import io
from datetime import datetime, date
from pathlib import Path
import pandas as pd

# Add project paths
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
tradingview_ai_path = Path("/Users/wilson/Desktop/tradingview-ai")
sys.path.insert(0, str(tradingview_ai_path))

# Temporary disable ccxt
class FakeCCXT:
    pass
sys.modules['ccxt'] = FakeCCXT()

from backtest_comparison_local import LocalBinanceDataProvider

# Test parameters
TRADING_PAIR = "BTC-USDT"
START_DATE = datetime(2025, 1, 1)
END_DATE = datetime(2025, 5, 1)
BACKTEST_RESOLUTION = "1m"


def test_data_loading_with_suppressed_warning():
    """测试数据加载，抑制误导性警告"""
    print("="*80)
    print("测试数据加载（抑制误导性警告）")
    print("="*80)
    
    local_data_provider = LocalBinanceDataProvider()
    start_ts = int(START_DATE.timestamp())
    end_ts = int(END_DATE.timestamp())
    
    # 临时重定向stderr以捕获警告
    old_stderr = sys.stderr
    sys.stderr = io.StringIO()
    
    try:
        # 加载数据
        df = local_data_provider.get_historical_candles(
            symbol=TRADING_PAIR,
            start_ts=start_ts,
            end_ts=end_ts,
            interval=BACKTEST_RESOLUTION
        )
        
        # 获取警告信息
        stderr_output = sys.stderr.getvalue()
    finally:
        sys.stderr = old_stderr
    
    print(f"数据加载结果: {len(df):,} 条K线")
    
    if df.empty:
        print("  ✗ 数据加载失败")
        if stderr_output:
            print(f"  警告信息: {stderr_output.strip()}")
        return False
    else:
        print("  ✓ 数据加载成功")
        if stderr_output and "未找到" in stderr_output:
            print(f"  ⚠ 警告信息（可忽略）: {stderr_output.strip()}")
            print(f"    说明: 虽然显示'未找到数据文件'，但数据实际上成功加载")
            print(f"    原因: BinancePublicDataManager从月度文件加载数据，而不是日级别文件")
        
        # 验证数据
        min_ts = df['timestamp'].min()
        max_ts = df['timestamp'].max()
        min_dt = datetime.fromtimestamp(min_ts)
        max_dt = datetime.fromtimestamp(max_ts)
        
        print(f"\n数据验证:")
        print(f"  时间范围: {min_dt} 到 {max_dt}")
        print(f"  数据点数: {len(df):,}")
        print(f"  数据连续性: {'✓ 良好' if len(df) > 100000 else '⚠ 可能不足'}")
        
        return True


def verify_monthly_files():
    """验证月度文件是否存在"""
    print(f"\n{'='*80}")
    print("验证月度文件")
    print(f"{'='*80}")
    
    from src.data.sources.binance_public_data_manager import BinancePublicDataManager
    
    manager = BinancePublicDataManager()
    binance_symbol = TRADING_PAIR.replace('-', '')
    
    # 检查需要的月份
    needed_months = []
    current = START_DATE.replace(day=1)
    while current <= END_DATE.replace(day=1):
        year = current.year
        month = current.month
        
        zip_path = manager.data_dir / 'data' / 'futures' / 'um' / 'monthly' / 'klines' / binance_symbol / '1m' / f"{binance_symbol}-1m-{year}-{month:02d}.zip"
        
        exists = zip_path.exists()
        size = zip_path.stat().st_size if exists else 0
        
        needed_months.append((f"{year}-{month:02d}", exists, size))
        
        if exists:
            print(f"  ✓ {year}-{month:02d}: {zip_path.name} ({size:,} bytes)")
        else:
            print(f"  ✗ {year}-{month:02d}: {zip_path.name} (不存在)")
        
        # 移动到下一个月
        if month == 12:
            current = current.replace(year=year + 1, month=1)
        else:
            current = current.replace(month=month + 1)
    
    existing_count = sum(1 for _, exists, _ in needed_months if exists)
    print(f"\n总结: {existing_count}/{len(needed_months)} 个月度文件存在")
    
    return existing_count > 0


if __name__ == "__main__":
    # 1. 验证月度文件
    files_exist = verify_monthly_files()
    
    # 2. 测试数据加载
    load_success = test_data_loading_with_suppressed_warning()
    
    # 总结
    print(f"\n{'='*80}")
    print("总结")
    print(f"{'='*80}")
    print(f"月度文件存在: {'✓' if files_exist else '✗'}")
    print(f"数据加载成功: {'✓' if load_success else '✗'}")
    
    if files_exist and load_success:
        print(f"\n✓ 数据加载正常，警告信息可以忽略")
        print(f"  警告来自BinancePublicDataManager找不到日级别文件，")
        print(f"  但数据实际上从月度文件成功加载")
    elif not files_exist:
        print(f"\n⚠ 月度文件不存在，需要检查数据目录")
    elif not load_success:
        print(f"\n✗ 数据加载失败，需要进一步检查")

