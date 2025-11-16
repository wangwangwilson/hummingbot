#!/usr/bin/env python3
"""
检查并修复损坏的ZIP文件
使用BinancePublicDataManager的检查和修复工具
"""

import sys
from pathlib import Path
from datetime import date, datetime

# 添加项目路径
tradingview_ai_path = Path("/Users/wilson/Desktop/tradingview-ai")
sys.path.insert(0, str(tradingview_ai_path))

# 临时禁用ccxt
class FakeCCXT:
    pass
sys.modules['ccxt'] = FakeCCXT()

from src.data.sources.binance_public_data_manager import BinancePublicDataManager

def check_single_file(manager: BinancePublicDataManager, symbol: str, file_date: date):
    """检查单个文件"""
    zip_path = manager.data_dir / 'data' / 'futures' / 'um' / 'daily' / 'klines' / symbol / '1m' / f"{symbol}-1m-{file_date.strftime('%Y-%m-%d')}.zip"
    
    print(f"\n检查文件: {zip_path.name}")
    print(f"  路径: {zip_path}")
    print(f"  存在: {zip_path.exists()}")
    
    if not zip_path.exists():
        print(f"  ✗ 文件不存在")
        return False
    
    file_size = zip_path.stat().st_size
    print(f"  大小: {file_size:,} 字节 ({file_size/1024:.2f} KB)")
    
    # 使用check_file_integrity检查
    is_valid = manager.check_file_integrity(zip_path)
    print(f"  完整性检查: {'✓ 通过' if is_valid else '✗ 失败（文件损坏）'}")
    
    # 使用_get_zip_file_list检查
    file_list = manager._get_zip_file_list(zip_path)
    if file_list:
        print(f"  ZIP内容: {len(file_list)} 个文件")
        print(f"    文件列表: {file_list}")
    else:
        print(f"  ZIP内容: 无法读取（文件可能损坏）")
    
    return is_valid

def repair_single_file(manager: BinancePublicDataManager, symbol: str, file_date: date):
    """修复单个文件"""
    print(f"\n尝试修复: {symbol}-1m-{file_date.strftime('%Y-%m-%d')}.zip")
    
    try:
        success = manager.redownload_file(
            symbol=symbol,
            file_type='daily',
            day=file_date
        )
        
        if success:
            print(f"  ✓ 修复成功")
            # 再次检查
            zip_path = manager.data_dir / 'data' / 'futures' / 'um' / 'daily' / 'klines' / symbol / '1m' / f"{symbol}-1m-{file_date.strftime('%Y-%m-%d')}.zip"
            if manager.check_file_integrity(zip_path):
                print(f"  ✓ 验证通过")
                return True
            else:
                print(f"  ⚠ 修复后验证失败")
                return False
        else:
            print(f"  ✗ 修复失败")
            return False
    except Exception as e:
        print(f"  ✗ 修复过程出错: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """主函数"""
    print("="*80)
    print("检查并修复损坏的ZIP文件")
    print("="*80)
    print()
    
    # 初始化管理器
    manager = BinancePublicDataManager()
    print(f"数据目录: {manager.data_dir}")
    print()
    
    # 需要检查的文件
    symbols = ["SOLUSDT", "ETHUSDT"]
    start_date = date(2025, 11, 1)
    end_date = date(2025, 11, 9)
    
    print(f"检查范围:")
    print(f"  交易对: {', '.join(symbols)}")
    print(f"  日期范围: {start_date} 到 {end_date}")
    print()
    
    # 检查所有文件
    print("="*80)
    print("【第一步：检查文件完整性】")
    print("="*80)
    
    damaged_files = []
    valid_files = []
    
    current_date = start_date
    while current_date <= end_date:
        for symbol in symbols:
            is_valid = check_single_file(manager, symbol, current_date)
            if is_valid:
                valid_files.append((symbol, current_date))
            else:
                damaged_files.append((symbol, current_date))
        current_date = current_date.replace(day=current_date.day + 1) if current_date.day < 28 else current_date.replace(month=current_date.month + 1, day=1)
        if current_date > end_date:
            break
    
    print()
    print("="*80)
    print("检查结果汇总")
    print("="*80)
    print(f"  正常文件: {len(valid_files)} 个")
    print(f"  损坏文件: {len(damaged_files)} 个")
    print()
    
    if damaged_files:
        print("损坏文件列表:")
        for symbol, file_date in damaged_files:
            print(f"  - {symbol}-1m-{file_date.strftime('%Y-%m-%d')}.zip")
        print()
        
        # 询问是否修复
        print("="*80)
        print("【第二步：尝试修复损坏文件】")
        print("="*80)
        print()
        
        repaired_count = 0
        failed_count = 0
        
        for symbol, file_date in damaged_files:
            if repair_single_file(manager, symbol, file_date):
                repaired_count += 1
            else:
                failed_count += 1
        
        print()
        print("="*80)
        print("修复结果汇总")
        print("="*80)
        print(f"  成功修复: {repaired_count} 个")
        print(f"  修复失败: {failed_count} 个")
        print()
        
        # 再次检查修复后的文件
        if repaired_count > 0:
            print("="*80)
            print("【第三步：验证修复后的文件】")
            print("="*80)
            print()
            
            for symbol, file_date in damaged_files:
                zip_path = manager.data_dir / 'data' / 'futures' / 'um' / 'daily' / 'klines' / symbol / '1m' / f"{symbol}-1m-{file_date.strftime('%Y-%m-%d')}.zip"
                if zip_path.exists():
                    is_valid = manager.check_file_integrity(zip_path)
                    file_list = manager._get_zip_file_list(zip_path)
                    status = "✓ 正常" if (is_valid and file_list) else "✗ 仍损坏"
                    print(f"  {zip_path.name}: {status}")
    else:
        print("✓ 所有文件正常，无需修复")
    
    print()
    print("="*80)
    print("完成")
    print("="*80)

if __name__ == "__main__":
    main()

