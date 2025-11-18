# 策略架构说明

## 架构设计

### 1. 策略继承结构

```
BaseStrategy (抽象基类)
├── StandardMMStrategy (标准做市策略)
├── TimedHedgeStrategy (定时对冲策略)
└── ... (其他策略)
```

### 2. 核心组件

#### BaseStrategy (策略基类)

所有策略的基类，提供：

- **策略元信息**：name, description
- **参数管理**：加载、保存、更新参数
- **回测器管理**：自动创建和管理回测器实例
- **抽象方法**：
  - `preprocess_data()`: 数据预处理
  - `run_backtest()`: 执行回测

#### 回测引擎扩展

- **backtest.py**: 基础回测引擎（标准策略使用）
- **backtest_with_hooks.py**: 带扩展点的回测引擎（支持策略特定逻辑）

### 3. 参数管理

#### ParamsManager

- **保存参数**：JSON格式，包含描述和元数据
- **加载参数**：从JSON文件加载
- **默认参数**：提供标准做市策略的默认参数

#### 参数文件格式

```json
{
  "description": "策略参数说明",
  "metadata": {
    "created_at": "2025-11-19T00:20:24",
    "version": "1.0",
    "strategy_name": "TimedHedge"
  },
  "parameters": {
    "exposure": 50000.0,
    "target_pct": 0.5,
    ...
  }
}
```

## 策略实现

### StandardMMStrategy

标准做市策略，基于原始回测逻辑：

```python
strategy = StandardMMStrategy(
    params={"exposure": 50000, "target_pct": 0.5}
)
results = strategy.run_backtest(data)
```

### TimedHedgeStrategy

定时对冲策略，在指定UTC时间点将仓位对冲到0：

```python
strategy = TimedHedgeStrategy(
    hedge_hours=[0, 8, 16],  # UTC时间：0点、8点、16点
    params={"exposure": 50000, "target_pct": 0.5}
)
results = strategy.run_backtest(data)
```

**特性**：
- 支持多个对冲时间点
- 自动计算对冲时间戳
- 在对冲时间点执行Taker交易将仓位对冲到0
- 如果有挂单，先撤单再对冲

## 扩展点设计

### 回测循环扩展点

在 `backtest_with_hooks.py` 中，支持以下扩展：

1. **定时对冲**：通过 `hedge_timestamps` 参数传入对冲时间点
2. **未来扩展**：可以添加更多扩展点，如：
   - 定时调仓
   - 条件触发
   - 风险控制

### 实现新策略

1. **继承BaseStrategy**：

```python
from .base_strategy import BaseStrategy

class MyStrategy(BaseStrategy):
    def __init__(self, ...):
        super().__init__(
            name="MyStrategy",
            description="我的策略说明",
            params=params
        )
    
    def preprocess_data(self, data):
        # 数据预处理逻辑
        return data
    
    def run_backtest(self, data):
        # 回测逻辑
        # 可以使用 self.backtester 或直接调用回测引擎
        return results
```

2. **使用扩展的回测引擎**：

如果需要策略特定的逻辑（如定时对冲），可以：

- 直接调用 `_run_backtest_numba_with_hooks`
- 传入扩展参数（如 `hedge_timestamps`）

## 数据流

```
原始数据
    ↓
Strategy.preprocess_data()  # 策略特定的数据预处理
    ↓
Strategy.run_backtest()     # 执行回测
    ↓
回测引擎（Numba加速）
    ↓
回测结果
    ↓
性能分析
    ↓
结果保存
```

## 使用示例

### 基本使用

```python
from src.strategies.standard_mm_strategy import StandardMMStrategy

# 创建策略
strategy = StandardMMStrategy(
    params={"exposure": 50000, "target_pct": 0.5}
)

# 执行回测
results = strategy.run_backtest(data)

# 获取结果
accounts = results["accounts"]
performance = results["performance"]
```

### 从文件加载参数

```python
from src.strategies.timed_hedge_strategy import TimedHedgeStrategy
from pathlib import Path

# 从文件加载参数
strategy = TimedHedgeStrategy(
    hedge_hours=[0, 8, 16],
    params_file=Path("params.json")
)

# 执行回测
results = strategy.run_backtest(data)

# 保存参数
strategy.save_params(Path("saved_params.json"))
```

### 参数管理

```python
from src.utils.params_manager import ParamsManager

# 获取默认参数
default_params = ParamsManager.get_default_mm_params()

# 保存参数
ParamsManager.save_params(
    params=default_params,
    filepath=Path("my_params.json"),
    description="我的策略参数"
)

# 加载参数
params = ParamsManager.load_params(Path("my_params.json"))
```

## 注意事项

1. **Numba兼容性**：扩展的回测引擎必须使用Numba支持的类型
2. **性能考虑**：策略特定的逻辑应尽量在Numba函数中实现
3. **参数合并**：策略参数会自动合并默认参数
4. **数据格式**：输入输出数据格式保持一致
5. **扩展点设计**：新增扩展点需要考虑Numba的限制

## 测试验证

所有策略都应通过完整测试：

1. 数据读取和预处理
2. 回测执行
3. 结果验证
4. 性能分析
5. 结果保存

参考 `test_timed_hedge_strategy.py` 的实现。

