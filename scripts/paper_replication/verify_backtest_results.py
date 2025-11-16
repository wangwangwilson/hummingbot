#!/usr/bin/env python3
"""
验证回测结果是否符合预期
"""

import sys
import re
from pathlib import Path

sys.path.insert(0, '/Users/wilson/Desktop/mm_research/hummingbot')

def parse_log_file():
    """解析日志文件，提取关键信息"""
    log_file = Path('sol_fixed_test.log')
    
    if not log_file.exists():
        print("❌ 日志文件不存在")
        return None
    
    with open(log_file, 'r') as f:
        content = f.read()
    
    results = {}
    
    # 检查是否完成
    if "回测完成" in content:
        results['completed'] = True
    else:
        results['completed'] = False
    
    # 提取关键指标
    patterns = {
        'total_executors': r'总Executor数:\s*(\d+)',
        'filled_executors': r'(?:有持仓|成交)Executor数:\s*(\d+)',
        'total_volume': r'总成交量:\s*\$([\d.]+)',
        'net_pnl_quote': r'总盈亏:\s*\$([\d.-]+)',
        'net_pnl_pct': r'总盈亏.*?\(([\d.-]+)%\)',
        'total_long': r'多单数:\s*(\d+)',
        'total_short': r'空单数:\s*(\d+)',
        'accuracy': r'胜率:\s*([\d.]+)%',
        'sharpe_ratio': r'Sharpe比率:\s*([\d.-]+)',
        'max_drawdown': r'最大回撤.*?\$([\d.]+)',
        'max_drawdown_pct': r'最大回撤.*?\(([\d.]+)%\)',
    }
    
    for key, pattern in patterns.items():
        match = re.search(pattern, content)
        if match:
            try:
                if '.' in match.group(1) or '-' in match.group(1):
                    results[key] = float(match.group(1))
                else:
                    results[key] = int(match.group(1))
            except:
                results[key] = match.group(1)
    
    # 提取关闭类型
    close_types_match = re.search(r'关闭类型:\s*({[^}]+})', content)
    if close_types_match:
        try:
            import json
            close_types_str = close_types_match.group(1)
            results['close_types'] = json.loads(close_types_str.replace("'", '"'))
        except:
            results['close_types'] = close_types_match.group(1)
    
    return results

def verify_results(results):
    """验证结果是否符合预期"""
    print("="*80)
    print("回测结果验证")
    print("="*80)
    print()
    
    if not results:
        print("❌ 无法解析结果")
        return False
    
    if not results.get('completed', False):
        print("⚠️  回测可能未完成")
        print()
    
    # 显示结果
    print("【回测结果】")
    print("-" * 80)
    for key, value in results.items():
        if key != 'close_types':
            print(f"  {key}: {value}")
    if 'close_types' in results:
        print(f"  关闭类型: {results['close_types']}")
    print()
    
    # 验证各项指标
    print("【验证检查】")
    print("-" * 80)
    
    checks = []
    
    # 1. 检查是否有executor
    total_executors = results.get('total_executors', 0)
    if total_executors > 0:
        checks.append(("✓", f"总Executor数: {total_executors} (正常)"))
    else:
        checks.append(("❌", "总Executor数为0 (异常)"))
    
    # 2. 检查是否有成交的executor
    filled_executors = results.get('filled_executors', 0)
    if filled_executors > 0:
        checks.append(("✓", f"成交Executor数: {filled_executors} (正常)"))
        if total_executors > 0:
            fill_rate = filled_executors / total_executors * 100
            checks.append(("✓", f"成交率: {fill_rate:.2f}%"))
            if fill_rate < 0.1:
                checks.append(("⚠️", "成交率很低，可能需要检查挂单价格"))
    else:
        checks.append(("❌", "成交Executor数为0 (异常 - 修复后应该>0)"))
    
    # 3. 检查总成交量
    total_volume = results.get('total_volume', 0)
    if total_volume > 0:
        checks.append(("✓", f"总成交量: ${total_volume:.2f} (正常)"))
    else:
        if filled_executors > 0:
            checks.append(("❌", f"总成交量为0但成交Executor数>0 (异常 - 统计逻辑可能有问题)"))
        else:
            checks.append(("⚠️", "总成交量为0 (可能没有成交)"))
    
    # 4. 检查盈亏
    net_pnl_quote = results.get('net_pnl_quote', 0)
    if net_pnl_quote != 0:
        checks.append(("✓", f"总盈亏: ${net_pnl_quote:.2f} (有盈亏)"))
    else:
        if filled_executors > 0:
            checks.append(("⚠️", "总盈亏为0但成交Executor数>0 (可能价格回到entry_price)"))
        else:
            checks.append(("⚠️", "总盈亏为0 (可能没有成交)"))
    
    # 5. 检查多空单
    total_long = results.get('total_long', 0)
    total_short = results.get('total_short', 0)
    if total_long > 0 or total_short > 0:
        checks.append(("✓", f"多单: {total_long}, 空单: {total_short} (正常)"))
    else:
        if filled_executors > 0:
            checks.append(("❌", "多空单数为0但成交Executor数>0 (异常)"))
    
    # 6. 检查关闭类型
    if 'close_types' in results:
        close_types = results['close_types']
        if isinstance(close_types, dict):
            early_stop = close_types.get('EARLY_STOP', 0)
            time_limit = close_types.get('TIME_LIMIT', 0)
            take_profit = close_types.get('TAKE_PROFIT', 0)
            stop_loss = close_types.get('STOP_LOSS', 0)
            
            if early_stop > 0:
                checks.append(("⚠️", f"EARLY_STOP: {early_stop} (未成交被提前停止)"))
            if time_limit > 0:
                checks.append(("✓", f"TIME_LIMIT: {time_limit} (达到时间限制)"))
            if take_profit > 0:
                checks.append(("✓", f"TAKE_PROFIT: {take_profit} (达到止盈)"))
            if stop_loss > 0:
                checks.append(("⚠️", f"STOP_LOSS: {stop_loss} (达到止损)"))
    
    for status, msg in checks:
        print(f"  {status} {msg}")
    
    print()
    
    # 总结
    print("【修复效果验证】")
    print("-" * 80)
    
    # 修复前的问题
    print("修复前:")
    print("  - total_executors_with_position: 0")
    print("  - total_volume: $0.00")
    print("  - 成交率: 0.02%")
    print()
    
    # 修复后的结果
    print("修复后:")
    print(f"  - total_executors_with_position: {filled_executors}")
    print(f"  - total_volume: ${total_volume:.2f}")
    if total_executors > 0:
        print(f"  - 成交率: {filled_executors/total_executors*100:.2f}%")
    print()
    
    # 判断修复是否成功
    success = True
    if filled_executors == 0:
        success = False
        print("❌ 修复未完全成功: 成交Executor数仍为0")
    elif total_volume == 0 and filled_executors > 0:
        success = False
        print("❌ 修复未完全成功: 总成交量仍为0")
    else:
        print("✓ 修复成功: 统计逻辑正常工作")
    
    return success

def main():
    """主函数"""
    print("="*80)
    print("回测结果验证")
    print("="*80)
    print()
    
    results = parse_log_file()
    if results:
        success = verify_results(results)
        
        print()
        print("="*80)
        if success:
            print("✓ 验证通过")
        else:
            print("⚠️  验证未完全通过，需要进一步检查")
        print("="*80)
    else:
        print("❌ 无法解析结果")

if __name__ == "__main__":
    main()

