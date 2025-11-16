#!/usr/bin/env python3
"""
分析修复后的回测结果
"""

import json
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, '/Users/wilson/Desktop/mm_research/hummingbot')

def analyze_log_file():
    """分析日志文件"""
    log_file = Path('sol_fixed_test.log')
    
    if not log_file.exists():
        print("日志文件不存在")
        return
    
    print("="*80)
    print("修复后的回测结果分析")
    print("="*80)
    print()
    
    with open(log_file, 'r') as f:
        lines = f.readlines()
    
    # 查找关键信息
    in_results = False
    results_section = []
    
    for i, line in enumerate(lines):
        if "回测结果汇总" in line:
            in_results = True
            results_section = lines[i:]
            break
    
    if results_section:
        print("回测结果:")
        print("-" * 80)
        for line in results_section[:30]:  # 显示前30行
            print(line.rstrip())
    else:
        # 查找进度信息
        print("查找回测进度...")
        for line in lines[-50:]:
            if "回测进度" in line or "executor" in line.lower() or "完成" in line:
                print(line.rstrip())
    
    print()
    print("="*80)
    print("检查修复效果")
    print("="*80)
    print()
    
    # 检查是否有错误
    errors = [line for line in lines if "error" in line.lower() or "Error" in line or "Traceback" in line]
    if errors:
        print("⚠️ 发现错误:")
        for error in errors[-5:]:  # 显示最后5个错误
            print(f"  {error.rstrip()}")
    else:
        print("✓ 未发现错误")
    
    print()
    
    # 检查关键指标
    total_executors = None
    filled_executors = None
    total_volume = None
    net_pnl = None
    
    for line in lines:
        if "总Executor数" in line:
            try:
                total_executors = int(line.split(":")[1].strip())
            except:
                pass
        if "有持仓Executor数" in line or "成交Executor数" in line:
            try:
                filled_executors = int(line.split(":")[1].strip())
            except:
                pass
        if "总成交量" in line:
            try:
                total_volume = float(line.split("$")[1].split()[0])
            except:
                pass
        if "总盈亏" in line:
            try:
                net_pnl = float(line.split("$")[1].split()[0])
            except:
                pass
    
    print("关键指标:")
    if total_executors is not None:
        print(f"  总Executor数: {total_executors}")
    if filled_executors is not None:
        print(f"  成交Executor数: {filled_executors}")
        if total_executors:
            print(f"  成交率: {filled_executors/total_executors*100:.2f}%")
    if total_volume is not None:
        print(f"  总成交量: ${total_volume:.2f}")
    if net_pnl is not None:
        print(f"  总盈亏: ${net_pnl:.2f}")
    
    print()
    
    # 对比修复前后
    print("修复前后对比:")
    print("-" * 80)
    print("修复前:")
    print("  - 成交率: 0.02%")
    print("  - 总成交量: $0.00")
    print("  - 总盈亏: $0.00")
    print("  - total_executors_with_position: 0")
    print()
    print("修复后:")
    if filled_executors is not None and total_executors:
        print(f"  - 成交率: {filled_executors/total_executors*100:.2f}%")
    if total_volume is not None:
        print(f"  - 总成交量: ${total_volume:.2f}")
    if net_pnl is not None:
        print(f"  - 总盈亏: ${net_pnl:.2f}")
    if filled_executors is not None:
        print(f"  - total_executors_with_position: {filled_executors}")

if __name__ == "__main__":
    analyze_log_file()

