# 实验结果存储目录结构说明

## 目录结构

```
results/
├── prod/                    # 正式回测结果
│   └── {YYYY_MM_DD}/        # 日期目录，例如: 2025_11_16
│       └── {HH_MM}/         # 时间目录，例如: 10_12
│           └── {symbol}/     # 交易对或组名，例如: BTCUSDT 或 group1
│               └── {experiment_name}/  # 实验目录
│                   ├── run_info.json      # 运行信息
│                   ├── results.json       # 回测结果
│                   ├── accounts.npy      # 账户数据（可选）
│                   ├── orders_stats.npy   # 订单统计（可选）
│                   └── *.png             # 可视化图表
│
└── test/                    # 测试结果
    └── {YYYY_MM_DD}/        # 日期目录
        └── {HH_MM}/         # 时间目录
            └── {symbol}/    # 交易对或组名
                └── {experiment_name}/  # 实验目录
                    ├── run_info.json
                    ├── results.json
                    └── *.png
```

## 实验命名规则

实验目录名称格式：`{symbol}_{target}_{scenario}_{param1}_{param2}_...`

### 组成部分

1. **symbol**: 交易对符号或组名
   - 单个交易对：`BTCUSDT`, `AXSUSDT`
   - 交易对组：`group1`, `major_pairs`

2. **target**: 实验目标
   - `backtest`: 回测
   - `optimization`: 参数优化
   - `analysis`: 分析
   - `comparison`: 对比实验

3. **scenario**: 实验场景
   - `maker_strategy`: Maker策略
   - `taker_strategy`: Taker策略
   - `multi_exchange`: 多交易所融合
   - `single_exchange`: 单交易所

4. **parameters**: 关键参数（可选）
   - 参数格式：`{key}_{value}`
   - 浮点数保留2位小数
   - 按key字母顺序排列

### 命名示例

```
# 示例1: 单交易所回测
AXSUSDT_backtest_single_exchange_exposure_50000.00_target_pct_0.50

# 示例2: 多交易所融合测试
BTCUSDT_backtest_multi_exchange_exposure_250000.00_target_pct_0.50

# 示例3: 参数优化
SOLUSDT_optimization_maker_strategy_exposure_100000.00

# 示例4: 策略对比
ETHUSDT_comparison_maker_vs_taker_exposure_50000.00
```

## 使用方法

### 基本使用

```python
from src.utils.path_manager import create_result_directory
from datetime import datetime

# 创建测试结果目录
run_dir, manager = create_result_directory(
    mode="test",
    symbol="AXSUSDT",
    target="backtest",
    scenario="single_exchange",
    parameters={
        "exposure": 50000,
        "target_pct": 0.5
    }
)

# 保存结果
results = {
    "total_pnl": 1000.0,
    "sharpe_ratio": 1.5
}
manager.save_results(results, "results.json")

# 保存图表
manager.get_output_path("equity_curve.png")
```

### 高级使用

```python
from src.utils.path_manager import ResultPathManager

# 创建路径管理器
manager = ResultPathManager(mode="prod")

# 手动创建目录
run_dir = manager.create_run_directory(
    symbol="BTCUSDT",
    experiment_name="BTCUSDT_backtest_multi_exchange_exposure_250000.00",
    experiment_scenario="多交易所融合回测",
    parameters={
        "exposure": 250000,
        "target_pct": 0.5,
        "taker_fee_rate": 0.00015
    }
)

# 保存各种结果
manager.save_results(performance_dict, "performance.json")
manager.save_results(statistics_dict, "statistics.json")

# 获取输出路径
chart_path = manager.get_output_path("equity_curve.png")
```

## 文件说明

### run_info.json

每次运行自动生成，包含：

```json
{
  "mode": "test",
  "symbol": "AXSUSDT",
  "experiment_name": "AXSUSDT_backtest_single_exchange_exposure_50000.00_target_pct_0.50",
  "experiment_scenario": "单交易所回测",
  "parameters": {
    "exposure": 50000,
    "target_pct": 0.5
  },
  "timestamp": "2025-11-18T16:16:18.440592",
  "directory": "/path/to/results/test/2025_11_18/16_16/AXSUSDT/..."
}
```

### results.json

回测结果数据，包含性能指标、统计信息等。

### 其他文件

- `accounts.npy`: 账户变动数据（NumPy格式）
- `orders_stats.npy`: 订单统计数据（NumPy格式）
- `*.png`: 可视化图表

## 配置

目录路径在 `src/const.py` 中配置：

```python
RESULTS_ROOT = PROJECT_ROOT / "results"
RESULTS_PROD = RESULTS_ROOT / "prod"
RESULTS_TEST = RESULTS_ROOT / "test"
```

## 注意事项

1. **目录自动创建**: 使用 `ResultPathManager` 会自动创建所有必要的目录
2. **时间戳**: 如果不指定时间戳，使用当前时间
3. **命名规范**: 实验名称使用英文，避免特殊字符
4. **参数格式**: 参数值会自动格式化（浮点数保留2位小数）
5. **路径管理**: 使用相对路径配置，便于项目迁移

## 最佳实践

1. **测试阶段**: 使用 `mode="test"` 存储测试结果
2. **正式回测**: 使用 `mode="prod"` 存储正式结果
3. **参数记录**: 确保所有关键参数都记录在 `parameters` 中
4. **结果备份**: 重要结果建议定期备份
5. **命名清晰**: 使用描述性的实验名称，便于后续查找

