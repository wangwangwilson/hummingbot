#!/usr/bin/env python3
"""检查当前已完成的回测结果"""
import json
from pathlib import Path
from datetime import datetime

# 查找最新的结果文件
result_dir = Path("/Users/wilson/Desktop/mm_research/hummingbot/scripts/paper_replication")
result_files = list(result_dir.glob("comparison_results_*.json"))

if result_files:
    latest_file = max(result_files, key=lambda p: p.stat().st_mtime)
    print(f"最新结果文件: {latest_file.name}")
    print(f"修改时间: {datetime.fromtimestamp(latest_file.stat().st_mtime)}")
    print()
    
    with open(latest_file, 'r') as f:
        data = json.load(f)
    
    if 'metrics' in data and data['metrics']:
        print(f"已完成的回测数量: {len(data['metrics'])}")
        print("\n已完成的回测:")
        print("-" * 80)
        
        for metric in data['metrics']:
            pair = metric.get('trading_pair', 'N/A')
            strategy = metric.get('strategy', 'N/A')
            total_pnl = metric.get('total_pnl', 0)
            fill_rate = metric.get('fill_rate', 0)
            total_execs = metric.get('total_executors', 0)
            filled_execs = metric.get('filled_executors', 0)
            
            print(f"{pair:<15} {strategy:<20} Executors: {total_execs:>6} | Filled: {filled_execs:>6} ({fill_rate:>5.1f}%) | PnL: ${total_pnl:>12,.2f}")
        
        print("-" * 80)
    else:
        print("暂无完成的回测数据")
else:
    print("未找到结果文件")

# 检查日志中的最新状态
log_file = result_dir / "comprehensive_comparison_output.log"
if log_file.exists():
    print("\n\n最近10条重要日志:")
    print("=" * 80)
    import subprocess
    result = subprocess.run(
        f"tail -500 {log_file} | grep -E '(✓ Completed|Running:|Processing:)' | tail -10",
        shell=True,
        capture_output=True,
        text=True
    )
    print(result.stdout)
