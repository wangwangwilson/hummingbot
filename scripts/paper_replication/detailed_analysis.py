#!/usr/bin/env python3
"""
详细分析回测结果，检查executor的实际数据
"""

import json
import sys
from pathlib import Path

# 添加路径
sys.path.insert(0, '/Users/wilson/Desktop/mm_research/hummingbot')

from hummingbot.strategy_v2.executors.position_executor.data_types import ExecutorInfo

def analyze_executor_details():
    """分析executor的详细数据"""
    
    # 检查是否有保存的executor数据
    # 由于JSON只保存了摘要，我们需要检查逻辑
    
    print("="*80)
    print("回测结果详细分析")
    print("="*80)
    print()
    
    result_file = Path('multi_symbol_backtest_results_20251113_055642.json')
    with open(result_file, 'r') as f:
        results = json.load(f)
    
    print("【核心问题分析】")
    print("-" * 80)
    print()
    
    print("1. 盈亏计算逻辑问题:")
    print("   在 summarize_results 中:")
    print("   - executors_with_position = executors_df[executors_df['net_pnl_quote'] != 0]")
    print("   - 这意味着只有 net_pnl_quote != 0 的executor才被认为'有持仓'")
    print("   - 但如果executor成交后盈亏为0（价格回到entry_price），就不会被计入")
    print()
    
    print("2. 从结果看:")
    print("   - filled_count > 0 (有成交)")
    print("   - 但 total_executors_with_position = 0 (没有有持仓的executor)")
    print("   - 这说明所有成交的executor的 net_pnl_quote 都是 0")
    print()
    
    print("3. 可能的原因:")
    print("   a) 所有executor都在TIME_LIMIT时关闭，且价格回到了entry_price")
    print("   b) 盈亏计算逻辑有问题 - net_pnl_quote计算不正确")
    print("   c) Executor在关闭时，net_pnl_quote被重置为0")
    print()
    
    print("4. 检查代码逻辑:")
    print("   在 position_executor_simulator.py 中:")
    print("   - net_pnl_quote = net_pnl_pct * filled_amount_quote")
    print("   - net_pnl_pct = cumulative_returns")
    print("   - cumulative_returns = (((1 + returns).cumprod() - 1) * side_multiplier) - trade_cost")
    print()
    print("   问题可能在于:")
    print("   - 如果executor在TIME_LIMIT时关闭，且价格回到entry_price")
    print("   - cumulative_returns 会接近 0（减去trade_cost后可能为负但很小）")
    print("   - 但由于浮点数精度或计算问题，可能被计算为0")
    print()
    
    print("5. 另一个问题:")
    print("   在 position_executor_simulator.py 第101行:")
    print("   df_filtered.loc[df_filtered.index[-1], 'filled_amount_quote'] = df_filtered['filled_amount_quote'].iloc[-1] * 2")
    print("   这会将最后的 filled_amount_quote 乘以2，但net_pnl_quote可能没有相应更新")
    print()
    
    print("6. 建议修复:")
    print("   a) 检查executor的net_pnl_quote实际值（不应该都是0）")
    print("   b) 检查filled_amount_quote和net_pnl_quote的关系")
    print("   c) 修改summarize_results，使用filled_amount_quote > 0来判断是否有持仓")
    print("   d) 检查TIME_LIMIT关闭时的盈亏计算")
    print()
    
    # 统计关闭类型
    print("="*80)
    print("关闭类型统计")
    print("="*80)
    print()
    
    for symbol, strategies in results.items():
        print(f"{symbol}:")
        for strategy_key, result in strategies.items():
            if result:
                summary = result.get('summary', {})
                close_types = summary.get('close_types', {})
                print(f"  {result.get('strategy')}: {close_types}")
        print()

if __name__ == "__main__":
    analyze_executor_details()


