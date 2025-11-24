"""详细分析PnL计算差异，验证未平仓仓位的影响"""
import sys
import numpy as np
from pathlib import Path
import json
import importlib.util

# 设置路径
project_root = Path(__file__).parent.absolute()
sys.path.insert(0, str(project_root))

# 动态导入analyze_performance
statistics_path = project_root / "src" / "analysis" / "statistics.py"
spec = importlib.util.spec_from_file_location("statistics", statistics_path)
statistics_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(statistics_module)
analyze_performance = statistics_module.analyze_performance

# 读取测试结果目录
result_dir = project_root / "results" / "test" / "2025_11_23" / "19_51" / "AXSUSDT" / "AXSUSDT_momentum_mm_optimized_30s_return_optimized_exposure_10000_hedge_threshold_pct_0.80_min_spread_pct_0.00_order_size_100.00_return_p20_-0.00_return_p80_0.00_spread_median_0.00_stop_loss_pct_0.10_target_pct_0.50"

# 读取accounts数据（如果有保存的话，否则需要重新运行回测）
# 这里我们直接分析performance.json中的结果

print("=" * 70)
print("PnL计算差异详细分析")
print("=" * 70)

# 读取performance.json
with open(result_dir / "performance.json", 'r') as f:
    performance = json.load(f)

# 提取关键数据
total_pnl_no_fees = performance['overall_performance']['total_pnl_no_fees']
maker_pnl_no_fees = performance['maker_performance']['total_maker_pnl_no_fees']
taker_pnl_no_fees = performance['taker_performance']['total_taker_pnl_no_fees']

print(f"\n1. 关键PnL数据:")
print(f"   total_pnl_no_fees: {total_pnl_no_fees:.2f}")
print(f"   maker_pnl_no_fees: {maker_pnl_no_fees:.2f}")
print(f"   taker_pnl_no_fees: {taker_pnl_no_fees:.2f}")
print(f"   maker + taker: {maker_pnl_no_fees + taker_pnl_no_fees:.2f}")
print(f"   差异: {total_pnl_no_fees - (maker_pnl_no_fees + taker_pnl_no_fees):.2f}")

print(f"\n2. 问题根源分析:")
print(f"   total_pnl_no_fees 的计算方式:")
print(f"     equity_no_fee = cash + pos_value")
print(f"     pnl_no_fee = diff(equity_no_fee)")
print(f"     total_pnl_no_fees = sum(pnl_no_fee)")
print(f"     → 这个计算包括:")
print(f"        a) 所有交易的已实现盈亏")
print(f"        b) 未平仓仓位的浮动盈亏 (mark-to-market)")
print(f"        c) 价格变化导致的仓位价值变化")
print(f"\n   maker_pnl_no_fees / taker_pnl_no_fees 的计算方式:")
print(f"     virtual_close_pnl = 只在平仓时计算盈亏")
print(f"     close_ind = (prev_pos * order_side < 0) & (order_side != 0)")
print(f"     → 这个计算只包括:")
print(f"        a) 已平仓的盈亏 (realized PnL)")
print(f"        b) 不包括未平仓的浮动盈亏")

print(f"\n3. 差异来源:")
print(f"   差异 = total_pnl_no_fees - (maker_pnl_no_fees + taker_pnl_no_fees)")
print(f"        = {total_pnl_no_fees - (maker_pnl_no_fees + taker_pnl_no_fees):.2f}")
print(f"   这个差异主要来自:")
print(f"     a) 未平仓仓位的浮动盈亏")
print(f"     b) 其他类型的交易 (对冲 order_role=1, 止损 order_role=7, 资金费 order_role=6)")
print(f"     c) 价格变化导致的仓位价值变化（即使没有交易）")

print(f"\n4. 验证方法:")
print(f"   如果最终仓位不为0，则:")
print(f"   未平仓浮动盈亏 = 最终仓位 * (最终价格 - 平均成本价)")
print(f"   这个值会被包含在 total_pnl_no_fees 中")
print(f"   但不会被包含在 maker_pnl_no_fees + taker_pnl_no_fees 中")

print(f"\n5. 修复建议:")
print(f"   方案1: 在统计中分别报告:")
print(f"     - realized_pnl = maker_pnl + taker_pnl (已实现盈亏)")
print(f"     - unrealized_pnl = 未平仓浮动盈亏 (未实现盈亏)")
print(f"     - total_pnl = realized_pnl + unrealized_pnl")
print(f"   方案2: 计算未平仓浮动盈亏并单独报告")
print(f"   方案3: 在maker/taker统计中排除未平仓的影响")

print(f"\n" + "=" * 70)

