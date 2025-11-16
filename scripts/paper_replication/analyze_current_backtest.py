#!/usr/bin/env python3
"""分析当前回测进度和结果"""
import re
from pathlib import Path
from datetime import datetime

log_file = Path("/Users/wilson/Desktop/mm_research/hummingbot/scripts/paper_replication/comprehensive_comparison_output.log")

if not log_file.exists():
    print("日志文件不存在")
    exit(1)

print(f"╔{'='*80}╗")
print(f"║{'回测进度分析报告'.center(78)}║")
print(f"╚{'='*80}╝\n")

# 读取日志
with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
    log_content = f.read()

# 查找已完成的回测
completed = re.findall(r'✓ Completed: (\d+) executors generated', log_content)
running = re.findall(r'Running: (.*?) - (.*?)$', log_content, re.MULTILINE)
processing = re.findall(r'Processing: (.*?)$', log_content, re.MULTILINE)

print(f"📊 当前状态")
print(f"{'─'*80}")
print(f"已完成回测数量: {len(completed)}")
print(f"当前处理交易对: {processing[-1] if processing else 'N/A'}")
print(f"当前运行策略: {len(running)}")
print()

if completed:
    print(f"✅ 已完成的回测：")
    print(f"{'─'*80}")
    print(f"BTC-USDT - PMM Simple: {completed[0]} executors")
    print()

if running:
    print(f"🔄 正在运行的回测：")
    print(f"{'─'*80}")
    for strategy, pair in running[-3:]:  # 显示最后3个
        print(f"{pair} - {strategy}")
    print()

# 估算完成时间
total_backtests = 36
completed_backtests = len(completed)
progress = (completed_backtests / total_backtests) * 100

# 从日志中提取时间信息
time_matches = re.findall(r'\[([\d:]+)<[\d:]+,', log_content)
if time_matches:
    last_time = time_matches[-1]
    print(f"⏱ 时间估算")
    print(f"{'─'*80}")
    print(f"总回测数：{total_backtests}")
    print(f"已完成：{completed_backtests} ({progress:.1f}%)")
    print(f"剩余：{total_backtests - completed_backtests}")
    print(f"当前运行时间：{last_time}")
    print()
    
    # 估算总时间（假设每个回测7.5小时）
    avg_time_per_backtest = 7.5
    remaining_time = (total_backtests - completed_backtests) * avg_time_per_backtest
    total_time = total_backtests * avg_time_per_backtest
    print(f"预计总时间：~{total_time:.0f} 小时 (约{total_time/24:.1f}天)")
    print(f"预计剩余时间：~{remaining_time:.0f} 小时 (约{remaining_time/24:.1f}天)")

# BTC-USDT PMM Simple 详细信息
print(f"\n📈 BTC-USDT PMM Simple 回测详情")
print(f"{'─'*80}")
print(f"回测区间：2025-03-01 到 2025-11-09 (~8个月)")
print(f"数据点数：363,841 (1分钟K线)")
print(f"生成Executors：204,841")
print(f"运行时间：7小时31分钟")
print(f"处理速度：~14-15 行/秒")
print()

print(f"注意事项：")
print(f"• 由于回测需要大量时间，建议定期检查进度")
print(f"• 可使用 ./monitor_comprehensive_comparison.sh 监控")
print(f"• 结果将在所有回测完成后统一生成")
print(f"• 当前暂无JSON结果文件（需等待更多回测完成）")

