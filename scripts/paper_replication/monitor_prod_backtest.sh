#!/bin/bash
# 监控正式环境回测任务进度

LOG_FILE="prod_backtest_20250101_20251109.log"
OUTPUT_DIR="backtest_results/prod"

echo "=========================================="
echo "正式环境回测任务监控"
echo "=========================================="
echo ""

# 检查进程
echo "1. 进程状态:"
if ps aux | grep -v grep | grep "backtest_with_plots_and_structure.py" > /dev/null; then
    echo "   ✓ 回测进程正在运行"
    ps aux | grep -v grep | grep "backtest_with_plots_and_structure.py" | awk '{print "   PID: " $2 ", CPU: " $3 "%, MEM: " $4 "%"}'
else
    echo "   ✗ 回测进程未运行"
fi
echo ""

# 检查日志
echo "2. 日志文件:"
if [ -f "$LOG_FILE" ]; then
    LOG_SIZE=$(ls -lh "$LOG_FILE" | awk '{print $5}')
    echo "   文件大小: $LOG_SIZE"
    echo "   最后更新: $(stat -f "%Sm" "$LOG_FILE" 2>/dev/null || stat -c "%y" "$LOG_FILE" 2>/dev/null)"
    echo ""
    echo "   最新日志（最后10行）:"
    tail -10 "$LOG_FILE" | sed 's/^/   /'
else
    echo "   ✗ 日志文件不存在"
fi
echo ""

# 检查输出目录
echo "3. 输出目录:"
if [ -d "$OUTPUT_DIR" ]; then
    TIMESTAMP_DIRS=$(find "$OUTPUT_DIR" -mindepth 1 -maxdepth 1 -type d | wc -l)
    echo "   时间戳目录数量: $TIMESTAMP_DIRS"
    
    if [ "$TIMESTAMP_DIRS" -gt 0 ]; then
        LATEST_DIR=$(find "$OUTPUT_DIR" -mindepth 1 -maxdepth 1 -type d | sort | tail -1)
        echo "   最新目录: $(basename "$LATEST_DIR")"
        echo ""
        echo "   已完成的品种:"
        find "$LATEST_DIR" -mindepth 1 -maxdepth 1 -type d | while read dir; do
            SYMBOL=$(basename "$dir")
            FILE_COUNT=$(find "$dir" -type f | wc -l)
            echo "     - $SYMBOL: $FILE_COUNT 个文件"
        done
    fi
else
    echo "   ✗ 输出目录不存在"
fi
echo ""

# 估算进度
echo "4. 任务进度:"
if [ -f "$LOG_FILE" ]; then
    TOTAL_TASKS=18  # 6个品种 × 3个策略
    COMPLETED=$(grep -c "✓ Completed" "$LOG_FILE" 2>/dev/null || echo "0")
    if [ "$COMPLETED" -gt 0 ]; then
        PERCENTAGE=$((COMPLETED * 100 / TOTAL_TASKS))
        echo "   已完成: $COMPLETED / $TOTAL_TASKS ($PERCENTAGE%)"
    else
        echo "   正在启动..."
    fi
fi
echo ""

echo "=========================================="
echo "监控命令:"
echo "  tail -f $LOG_FILE          # 实时查看日志"
echo "  ./monitor_prod_backtest.sh  # 查看进度"
echo "=========================================="

