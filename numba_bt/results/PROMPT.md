# 实验结果存储目录结构设计提示词

## 需求描述

设计合理的项目目录结构，用于存储实验结果。要求如下：

### 目录结构

```
results/                    # 根目录（相对路径配置在 const.py）
├── prod/                   # 正式回测结果
│   └── {YYYY_MM_DD}/       # 日期目录，例如: 2025_11_16
│       └── {HH_MM}/        # 时间目录，例如: 10_12
│           └── {symbol}/   # 交易对或组名，例如: BTCUSDT 或 group1
│               └── {experiment_name}/  # 实验目录
│                   ├── run_info.json      # 运行信息
│                   ├── results.json       # 回测结果
│                   ├── accounts.npy       # 账户数据（可选）
│                   ├── orders_stats.npy   # 订单统计（可选）
│                   └── *.png             # 可视化图表
│
└── test/                   # 测试结果
    └── {YYYY_MM_DD}/       # 日期目录
        └── {HH_MM}/        # 时间目录
            └── {symbol}/   # 交易对或组名
                └── {experiment_name}/  # 实验目录
                    ├── run_info.json
                    ├── results.json
                    └── *.png
```

### 配置要求

1. **相对路径配置**：在 `src/const.py` 中配置相对路径
   - `RESULTS_ROOT = PROJECT_ROOT / "results"`
   - `RESULTS_PROD = RESULTS_ROOT / "prod"`
   - `RESULTS_TEST = RESULTS_ROOT / "test"`

2. **日期时间格式**：
   - 日期目录：`YYYY_MM_DD`，例如：`2025_11_16`
   - 时间目录：`HH_MM`，例如：`10_12`

3. **实验命名规则**：
   - 格式：`{symbol}_{target}_{scenario}_{param1}_{param2}_...`
   - 使用英文表达
   - 参数格式：`{key}_{value}`
   - 浮点数保留2位小数
   - 按key字母顺序排列

### 命名示例

```
# 单交易所回测
AXSUSDT_backtest_single_exchange_exposure_50000.00_target_pct_0.50

# 多交易所融合测试
BTCUSDT_backtest_multi_exchange_exposure_250000.00_target_pct_0.50

# 参数优化
SOLUSDT_optimization_maker_strategy_exposure_100000.00

# 策略对比
ETHUSDT_comparison_maker_vs_taker_exposure_50000.00
```

### 功能要求

1. **自动创建目录**：每次程序运行自动创建日期时间目录
2. **保存运行信息**：自动生成 `run_info.json`，包含：
   - mode (prod/test)
   - symbol
   - experiment_name
   - experiment_scenario
   - parameters
   - timestamp
   - directory

3. **结果保存**：
   - 性能分析结果保存为 JSON
   - 账户和订单数据保存为 NumPy 格式（可选）
   - 可视化图表保存为 PNG

4. **路径管理工具**：
   - 提供 `ResultPathManager` 类管理路径
   - 提供便捷函数 `create_result_directory` 快速创建目录

### 实现要点

1. 使用 `pathlib.Path` 进行路径管理
2. 使用相对路径，便于项目迁移
3. 自动创建所有必要的父目录
4. 保存完整的运行信息，便于后续分析
5. 支持 prod 和 test 两种模式

### 使用示例

```python
from src.utils.path_manager import create_result_directory

# 创建结果目录
run_dir, manager = create_result_directory(
    mode="test",
    symbol="AXSUSDT",
    target="backtest",
    scenario="multi_exchange",
    parameters={
        "exposure": 50000,
        "target_pct": 0.5,
        "days": 3
    }
)

# 保存结果
manager.save_results(performance, "performance.json")
np.save(manager.get_output_path("accounts.npy"), accounts)
```

## 设计原则

1. **层次清晰**：按模式、日期、时间、交易对、实验组织
2. **易于查找**：通过日期时间快速定位实验结果
3. **信息完整**：保存所有必要的运行信息和参数
4. **可扩展性**：支持未来添加新的实验类型和参数
5. **自动化**：减少手动操作，自动创建和管理目录

