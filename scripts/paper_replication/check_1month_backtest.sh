#!/bin/bash
# 检查1个月回测进度

LOG_FILE="backtest_1month.log"
PID=$(pgrep -f "backtest_1month_comparison.py")

if [ -z "$PID" ]; then
    echo "回测进程未运行"
else
    echo "回测进程运行中 (PID: $PID)"
    ps aux | grep "$PID" | grep -v grep
fi

echo ""
echo "最新日志 (最后30行):"
echo "----------------------------------------"
if [ -f "$LOG_FILE" ]; then
    tail -30 "$LOG_FILE"
else
    echo "日志文件不存在"
fi

echo ""
echo "检查结果文件:"
if [ -f "BACKTEST_1MONTH_REPORT.md" ]; then
    echo "✓ 报告文件已生成"
    echo "  文件大小: $(ls -lh BACKTEST_1MONTH_REPORT.md | awk '{print $5}')"
else
    echo "✗ 报告文件未生成"
fi

if [ -f "BACKTEST_1MONTH_RESULTS.json" ]; then
    echo "✓ 结果JSON文件已生成"
    echo "  文件大小: $(ls -lh BACKTEST_1MONTH_RESULTS.json | awk '{print $5}')"
else
    echo "✗ 结果JSON文件未生成"
fi

