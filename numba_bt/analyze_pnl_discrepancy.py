"""分析PnL计算差异的原因"""
import sys
import numpy as np
from pathlib import Path
import json

# 设置路径
project_root = Path(__file__).parent.absolute()
sys.path.insert(0, str(project_root))

# 读取测试结果
result_dir = project_root / "results" / "test" / "2025_11_23" / "19_51" / "AXSUSDT" / "AXSUSDT_momentum_mm_optimized_30s_return_optimized_exposure_10000_hedge_threshold_pct_0.80_min_spread_pct_0.00_order_size_100.00_return_p20_-0.00_return_p80_0.00_spread_median_0.00_stop_loss_pct_0.10_target_pct_0.50"

# 读取performance.json
with open(result_dir / "performance.json", 'r') as f:
    performance = json.load(f)

print("=" * 70)
print("PnL计算差异分析")
print("=" * 70)

# 1. 提取关键数据
total_pnl_no_fees = performance['overall_performance']['total_pnl_no_fees']
maker_pnl_no_fees = performance['maker_performance']['total_maker_pnl_no_fees']
taker_pnl_no_fees = performance['taker_performance']['total_taker_pnl_no_fees']

print(f"\n1. 关键PnL数据:")
print(f"   total_pnl_no_fees: {total_pnl_no_fees:.2f}")
print(f"   maker_pnl_no_fees: {maker_pnl_no_fees:.2f}")
print(f"   taker_pnl_no_fees: {taker_pnl_no_fees:.2f}")
print(f"   maker + taker: {maker_pnl_no_fees + taker_pnl_no_fees:.2f}")
print(f"   差异: {total_pnl_no_fees - (maker_pnl_no_fees + taker_pnl_no_fees):.2f}")

# 2. 分析计算方式的差异
print(f"\n2. 计算方式分析:")
print(f"   total_pnl_no_fees 计算方式:")
print(f"     - 基于权益变化: equity = cash + pos_value")
print(f"     - pnl = diff(equity)")
print(f"     - 包括: 所有交易盈亏 + 未平仓仓位浮动盈亏 (mark-to-market)")
print(f"\n   maker_pnl_no_fees / taker_pnl_no_fees 计算方式:")
print(f"     - 基于虚拟平仓: virtual_close_pnl")
print(f"     - 只计算: 已平仓的盈亏 (close_ind = prev_pos * order_side < 0)")
print(f"     - 不包括: 未平仓仓位的浮动盈亏")

# 3. 分析未平仓仓位的影响
print(f"\n3. 未平仓仓位影响分析:")
print(f"   差异主要来自:")
print(f"     a) 未平仓仓位的浮动盈亏 (mark-to-market)")
print(f"     b) 其他类型的交易 (如对冲 order_role=1, 止损 order_role=7)")
print(f"     c) 资金费率支付 (order_role=6)")

# 4. 验证计算逻辑
print(f"\n4. 计算逻辑验证:")
print(f"   如果最终仓位不为0，则:")
print(f"   未平仓浮动盈亏 = 最终仓位 * (最终价格 - 平均成本价)")
print(f"   这个值会被包含在 total_pnl_no_fees 中")
print(f"   但不会被包含在 maker_pnl_no_fees + taker_pnl_no_fees 中")

# 5. 建议修复方案
print(f"\n5. 建议修复方案:")
print(f"   方案1: 在 total_pnl_no_fees 中减去未平仓浮动盈亏")
print(f"   方案2: 在 maker/taker_pnl 中加上对应的未平仓浮动盈亏")
print(f"   方案3: 分别报告:")
print(f"     - 已实现PnL (realized_pnl) = maker_pnl + taker_pnl")
print(f"     - 未实现PnL (unrealized_pnl) = 未平仓浮动盈亏")
print(f"     - 总PnL (total_pnl) = 已实现 + 未实现")

print(f"\n" + "=" * 70)

