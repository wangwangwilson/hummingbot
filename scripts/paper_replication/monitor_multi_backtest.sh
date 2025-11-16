#!/bin/bash
# 监控多品种回测脚本

cd /Users/wilson/Desktop/mm_research/hummingbot/scripts/paper_replication

echo "=== 多品种回测监控 ==="
echo ""

# 检查进程
PROCESS=$(ps aux | grep "multi_symbol_backtest.py" | grep -v grep)
if [ -z "$PROCESS" ]; then
    echo "❌ 回测进程未运行"
    exit 1
fi

echo "✅ 回测进程运行中"
echo ""

# 显示进程信息
echo "$PROCESS" | awk '{print "PID: " $2 " | CPU: " $3 "% | 内存: " $6/1024 " MB | 运行时间: " $10}'
echo ""

# 显示最新日志
if [ -f multi_symbol_backtest.log ]; then
    echo "最新日志 (最后30行):"
    echo "---"
    tail -30 multi_symbol_backtest.log
    echo "---"
    echo ""
    echo "日志文件大小: $(wc -l < multi_symbol_backtest.log) 行"
else
    echo "⚠️  日志文件不存在"
fi

echo ""
echo "实时监控命令:"
echo "  tail -f multi_symbol_backtest.log"
echo ""
echo "停止回测命令:"
echo "  pkill -f multi_symbol_backtest.py"


