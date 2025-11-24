"""验证挂单量是否在5%-10%范围内"""
import sys
import numpy as np
from pathlib import Path
import json

# 设置路径
project_root = Path(__file__).parent.absolute()
sys.path.insert(0, str(project_root))

# 读取最新的测试结果
result_dir = project_root / "results" / "test" / "2025_11_24" / "01_56" / "AXSUSDT" / "AXSUSDT_as_model_future_perfect_prediction_base_exposure_10000_base_target_pct_0.50_buy_distance_1.00_order_size_pct_max_0.10_order_size_pct_min_0.05_sell_distance_1.00"

# 读取performance.json获取初始资金
with open(result_dir / "performance.json", 'r') as f:
    performance = json.load(f)

# 读取strategy_params.json获取参数
with open(result_dir / "strategy_params.json", 'r') as f:
    strategy_params = json.load(f)

initial_cash = strategy_params.get("initial_cash", 10000.0)
order_size_pct_min = strategy_params.get("order_size_pct_min", 0.05)
order_size_pct_max = strategy_params.get("order_size_pct_max", 0.10)

print("=" * 70)
print("挂单量验证分析")
print("=" * 70)
print(f"初始资金: {initial_cash:.2f} USDT")
print(f"挂单量范围: {initial_cash * order_size_pct_min:.2f} - {initial_cash * order_size_pct_max:.2f} USDT")
print(f"挂单量百分比范围: {order_size_pct_min*100:.1f}% - {order_size_pct_max*100:.1f}%")

# 分析place_orders_stats
# place_orders_stats: [timestamp, lifecycle_ms, price, side, origin_volume, filled_volume, avg_fill_price, ...]
# origin_volume是总挂单量（已成交+剩余）

print(f"\n问题分析:")
print(f"  place_orders_stats中的origin_volume是总挂单量（已成交+剩余）")
print(f"  如果挂单量在调整过程中超出10%，那么origin_volume也会超出")
print(f"  需要确保在记录挂单时，origin_volume也在5%-10%范围内")

print(f"\n建议:")
print(f"  1. 在记录挂单时，验证origin_volume是否在5%-10%范围内")
print(f"  2. 如果超出，记录警告或调整")
print(f"  3. 确保所有挂单量计算都经过验证")

