#!/bin/bash
# Monitor comprehensive backtest progress

LOG_FILE="/Users/wilson/Desktop/mm_research/hummingbot/scripts/paper_replication/comprehensive_backtest.log"

echo "Monitoring comprehensive backtest..."
echo "Press Ctrl+C to stop"
echo ""

while true; do
    clear
    echo "=========================================="
    echo "Comprehensive Backtest Monitor"
    echo "=========================================="
    echo ""
    
    # Check if process is running
    if pgrep -f "comprehensive_backtest_comparison.py" > /dev/null; then
        echo "✓ Process is running"
    else
        echo "✗ Process is not running"
    fi
    
    echo ""
    echo "Latest log output (last 30 lines):"
    echo "----------------------------------------"
    tail -30 "$LOG_FILE" 2>/dev/null || echo "Log file not found or empty"
    
    echo ""
    echo "=========================================="
    echo "Press Ctrl+C to stop monitoring"
    sleep 5
done

