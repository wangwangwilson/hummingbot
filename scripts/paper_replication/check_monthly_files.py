#!/usr/bin/env python3
"""
检查月度数据文件是否存在
"""

import sys
from pathlib import Path
from datetime import datetime

tradingview_ai_path = Path("/Users/wilson/Desktop/tradingview-ai")
sys.path.insert(0, str(tradingview_ai_path))

class FakeCCXT:
    pass
sys.modules['ccxt'] = FakeCCXT()

from src.data.sources.binance_public_data_manager import BinancePublicDataManager

TRADING_PAIR = "BTC-USDT"
START_DATE = datetime(2025, 1, 1)
END_DATE = datetime(2025, 5, 1)

manager = BinancePublicDataManager()
binance_symbol = TRADING_PAIR.replace('-', '')

print("="*80)
print("检查月度数据文件")
print("="*80)
print(f"数据目录: {manager.data_dir}")
print(f"交易对: {binance_symbol}")
print(f"时间范围: {START_DATE.date()} 到 {END_DATE.date()}")
print()

# 检查月度文件
monthly_dir = manager.data_dir / "futures" / "um" / "monthly" / "klines" / binance_symbol / "1m"
print(f"月度文件目录: {monthly_dir}")
print()

if monthly_dir.exists():
    monthly_files = list(monthly_dir.glob(f"{binance_symbol}-1m-*.zip"))
    monthly_files.sort()
    
    print(f"找到月度文件: {len(monthly_files)} 个")
    for f in monthly_files:
        size = f.stat().st_size
        print(f"  {f.name}: {size:,} bytes")
    
    # 检查需要的月份
    needed_months = []
    current = START_DATE
    while current <= END_DATE:
        month_str = current.strftime('%Y-%m')
        file_name = f"{binance_symbol}-1m-{month_str}.zip"
        file_path = monthly_dir / file_name
        
        if file_path.exists():
            size = file_path.stat().st_size
            needed_months.append((month_str, file_path, size, True))
            print(f"  ✓ {month_str}: {file_name} ({size:,} bytes)")
        else:
            needed_months.append((month_str, file_path, 0, False))
            print(f"  ✗ {month_str}: {file_name} (不存在)")
        
        # 移动到下一个月
        if current.month == 12:
            current = current.replace(year=current.year + 1, month=1)
        else:
            current = current.replace(month=current.month + 1)
    
    print()
    print("总结:")
    existing = sum(1 for _, _, _, exists in needed_months if exists)
    missing = len(needed_months) - existing
    print(f"  需要的月份: {len(needed_months)}")
    print(f"  存在的月份: {existing}")
    print(f"  缺失的月份: {missing}")
    
    if existing > 0:
        print(f"\n  ✓ 数据可以从月度文件加载")
    else:
        print(f"\n  ✗ 无法从月度文件加载数据")
else:
    print(f"  ✗ 月度文件目录不存在: {monthly_dir}")

