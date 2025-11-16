#!/bin/bash
# 监控回测进度

LOG_FILE="sol_fixed_test.log"

echo "监控回测进度..."
echo "按 Ctrl+C 停止监控"
echo ""

while true; do
    if [ -f "$LOG_FILE" ]; then
        # 清屏
        clear
        
        echo "=========================================="
        echo "回测进度监控 - $(date '+%Y-%m-%d %H:%M:%S')"
        echo "=========================================="
        echo ""
        
        # 显示最新进度
        tail -5 "$LOG_FILE" | grep "回测进度" | tail -1
        
        # 检查是否完成
        if grep -q "回测完成" "$LOG_FILE"; then
            echo ""
            echo "✓ 回测已完成！"
            echo ""
            echo "最终结果:"
            grep -A 20 "回测结果汇总" "$LOG_FILE" | head -25
            break
        fi
        
        # 检查是否有错误
        if grep -q "Error\|Traceback" "$LOG_FILE"; then
            echo ""
            echo "⚠️ 发现错误:"
            grep -i "error\|traceback" "$LOG_FILE" | tail -3
        fi
        
        echo ""
        echo "等待5秒后刷新..."
        sleep 5
    else
        echo "等待日志文件生成..."
        sleep 2
    fi
done
