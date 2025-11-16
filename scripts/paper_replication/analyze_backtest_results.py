#!/usr/bin/env python3
"""
分析回测结果，检查盈亏计算逻辑
"""

import json
from pathlib import Path
from typing import Dict, List

def analyze_results():
    """分析回测结果"""
    result_file = Path('multi_symbol_backtest_results_20251113_055642.json')
    
    if not result_file.exists():
        print(f"结果文件不存在: {result_file}")
        return
    
    with open(result_file, 'r') as f:
        results = json.load(f)
    
    print("="*80)
    print("回测结果分析报告")
    print("="*80)
    print()
    
    # 问题统计
    issues = []
    
    for symbol, strategies in results.items():
        print(f"【{symbol}】")
        print("-" * 80)
        
        for strategy_key, result in strategies.items():
            if not result:
                continue
                
            strategy_name = result.get('strategy', 'Unknown')
            executor_count = result.get('executor_count', 0)
            filled_count = result.get('filled_count', 0)
            summary = result.get('summary', {})
            
            print(f"\n策略: {strategy_name}")
            print(f"  Executor总数: {executor_count}")
            print(f"  成交Executor: {filled_count} ({filled_count/executor_count*100:.2f}% if executor_count > 0 else 0)")
            print(f"  有持仓Executor: {summary.get('total_executors_with_position', 0)}")
            print(f"  总成交量: ${summary.get('total_volume', 0):.2f}")
            print(f"  总盈亏: ${summary.get('net_pnl_quote', 0):.2f}")
            print(f"  总盈亏%: {summary.get('net_pnl', 0)*100:.2f}%")
            print(f"  关闭类型: {summary.get('close_types', {})}")
            
            # 检查问题
            if summary.get('net_pnl_quote', 0) == 0 and filled_count > 0:
                issues.append(f"{symbol} {strategy_name}: 有成交但盈亏为0")
            
            if summary.get('total_executors_with_position', 0) == 0 and filled_count > 0:
                issues.append(f"{symbol} {strategy_name}: 有成交但total_executors_with_position为0")
            
            if summary.get('total_volume', 0) == 0 and filled_count > 0:
                issues.append(f"{symbol} {strategy_name}: 有成交但总成交量为0")
            
            if executor_count > 0 and filled_count == 0:
                issues.append(f"{symbol} {strategy_name}: 创建了{executor_count}个executor但无成交")
        
        print()
    
    # 总结问题
    print("="*80)
    print("问题总结")
    print("="*80)
    
    if issues:
        print(f"发现 {len(issues)} 个潜在问题:")
        for i, issue in enumerate(issues, 1):
            print(f"  {i}. {issue}")
    else:
        print("未发现明显问题")
    
    print()
    print("="*80)
    print("逻辑分析")
    print("="*80)
    print()
    print("1. 盈亏计算逻辑:")
    print("   - net_pnl_quote = net_pnl_pct * filled_amount_quote")
    print("   - net_pnl_pct = cumulative_returns (基于价格变化)")
    print("   - 如果所有executor都在TIME_LIMIT时关闭且价格回到entry_price，盈亏为0")
    print()
    print("2. total_executors_with_position:")
    print("   - 应该统计有持仓的executor数量")
    print("   - 如果为0但filled_count>0，说明统计逻辑可能有问题")
    print()
    print("3. 成交但无盈亏的可能原因:")
    print("   - Executor在TIME_LIMIT时关闭，价格回到entry_price")
    print("   - 所有executor都被EARLY_STOP，没有实际持仓")
    print("   - 盈亏计算逻辑有问题")
    print()
    print("4. 建议检查:")
    print("   - 检查executor的close_type分布")
    print("   - 检查executor的net_pnl_quote实际值")
    print("   - 检查summarize_results中的统计逻辑")

if __name__ == "__main__":
    analyze_results()


