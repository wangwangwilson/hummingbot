#!/bin/bash
# 检查回测进度

cd "$(dirname "$0")"

echo "=== 回测状态检查 ==="
echo ""

# 检查进程
if ps aux | grep -v grep | grep "backtest_comparison.py CUSTOM" > /dev/null; then
    echo "✓ 回测进程正在运行"
    ps aux | grep -v grep | grep "backtest_comparison.py CUSTOM" | head -1
else
    echo "✗ 回测进程未运行"
fi

echo ""

# 检查日志
if [ -f backtest_output.log ]; then
    lines=$(wc -l < backtest_output.log)
    echo "日志文件行数: $lines"
    if [ $lines -gt 0 ]; then
        echo ""
        echo "=== 最后20行输出 ==="
        tail -20 backtest_output.log
    else
        echo "日志文件为空（可能还在初始化）"
    fi
else
    echo "日志文件不存在"
fi

echo ""

# 检查结果文件
results_dir="../../data/paper_replication/results"
if [ -d "$results_dir" ]; then
    echo "=== 结果文件 ==="
    ls -lht "$results_dir"/*.csv "$results_dir"/*.txt 2>/dev/null | head -5
else
    echo "结果目录不存在: $results_dir"
fi

