"""分析策略亏损原因"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
from datetime import datetime

# 添加项目路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# 读取回测结果
results_dir = project_root / "results" / "test" / "2025_11_23" / "18_39" / "AXSUSDT" / "AXSUSDT_momentum_mm_30s_return_exposure_10000_order_size_100.00_return_p20_-0.00_return_p80_0.00_spread_median_0.00_target_pct_0.50"

import json
with open(results_dir / "performance.json", 'r') as f:
    performance = json.load(f)

print("=" * 70)
print("策略亏损原因分析")
print("=" * 70)

overall = performance.get('overall_performance', {})
maker = performance.get('maker_performance', {})
taker = performance.get('taker_performance', {})
fees = performance.get('fee_analysis', {})
order_behavior = performance.get('order_behavior_metrics', {})

print("\n1. 总体绩效分析")
print(f"   总PnL (含手续费): {overall.get('total_pnl_with_fees', 0):.2f}")
print(f"   总PnL (不含手续费): {overall.get('total_pnl_no_fees', 0):.2f}")
print(f"   手续费成本: {fees.get('total_actual_fees', 0):.2f}")
print(f"   手续费占比: {fees.get('total_actual_fees', 0) / abs(overall.get('total_pnl_with_fees', 1)) * 100:.2f}%")

print("\n2. Maker vs Taker 分析")
print(f"   Maker PnL: {maker.get('total_maker_pnl_no_fees', 0):.2f}")
print(f"   Maker交易额: {maker.get('maker_volume_total', 0):.2f}")
print(f"   Maker PnL比率: {maker.get('maker_pnl_ratio', 0):.4f} bps")
print(f"   Maker手续费(返佣): {maker.get('actual_maker_fees_cost_rebate', 0):.2f}")
print(f"\n   Taker PnL: {taker.get('total_taker_pnl_no_fees', 0):.2f}")
print(f"   Taker交易额: {taker.get('taker_volume_total', 0):.2f}")
print(f"   Taker PnL比率: {taker.get('taker_pnl_ratio', 0):.4f} bps")
print(f"   Taker手续费(成本): {taker.get('actual_taker_fees_cost', 0):.2f}")

print("\n3. 订单行为分析")
print(f"   平均成交时间: {order_behavior.get('avg_fill_time_sec', 0):.2f} 秒")
print(f"   平均成交率: {order_behavior.get('avg_fill_rate', 0)*100:.2f}%")
print(f"   完全成交比例: {order_behavior.get('finish_all_pct', 0)*100:.2f}%")
print(f"   平均滑点: {order_behavior.get('avg_slippage_pct', 0)*100:.4f}%")
print(f"   总滑点价值: {order_behavior.get('total_slippage_value', 0):.2f}")

print("\n4. 策略逻辑问题分析")
print("   可能的问题：")
print("   a) 看涨时买单挂盘口下方，容易成交；卖单挂远，难成交")
print("      导致单向持仓累积，风险暴露过大")
print("   b) 看跌时卖单挂盘口上方，容易成交；买单挂远，难成交")
print("      同样导致单向持仓累积")
print("   c) 中性时多空等距等量，但spread可能太小，无法覆盖手续费")
print("   d) 当return反转时撤单，但可能已经部分成交，导致不利持仓")
print("   e) Taker成交（mm_flag=0）直接成交，没有考虑价格滑点")
print("   f) 仓位控制逻辑：当超过exposure时用taker对冲，但可能对冲不及时")

print("\n5. 建议修复方向")
print("   a) 调整挂单策略：看涨时买单挂远，卖单挂近（反向）")
print("   b) 增加spread，确保能覆盖手续费和滑点")
print("   c) 改进仓位控制：更及时的对冲机制")
print("   d) 优化订单更新逻辑：避免频繁撤单和重新挂单")
print("   e) 增加止损机制：限制单笔交易的最大亏损")

print("\n" + "=" * 70)

