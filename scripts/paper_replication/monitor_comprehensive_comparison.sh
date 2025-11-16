#!/bin/bash

echo "==================================================================="
echo "Comprehensive Strategy Comparison - Progress Monitor"
echo "==================================================================="
echo ""

# Check if process is running
if ps aux | grep "comprehensive_strategy_comparison.py" | grep -v grep > /dev/null; then
    echo "✓ Backtest is running"
    echo ""
    
    # Show CPU and memory usage
    echo "Resource Usage:"
    ps aux | grep "comprehensive_strategy_comparison.py" | grep -v grep | awk '{print "  CPU: " $3 "%, Memory: " $4 "%"}'
    echo ""
    
    # Show latest progress
    echo "Latest Progress:"
    tail -20 comprehensive_comparison_output.log 2>/dev/null | grep -E "(Processing:|Running:|✓|回测进度)" | tail -10
    echo ""
    
    # Count completed
    completed=$(grep -c "✓ Completed:" comprehensive_comparison_output.log 2>/dev/null)
    total=36  # 12 pairs * 3 strategies
    echo "Completed: $completed / $total backtests"
    echo "Progress: $(echo "scale=1; $completed * 100 / $total" | bc)%"
    
else
    echo "✗ Backtest is not running"
    echo ""
    echo "Last lines of output:"
    tail -20 comprehensive_comparison_output.log 2>/dev/null
fi

echo ""
echo "==================================================================="

