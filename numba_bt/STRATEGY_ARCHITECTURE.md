# 策略架构设计文档

## 设计目标

1. **参数管理**：JSON格式保存和加载，支持注释和元数据
2. **策略继承**：基于BaseStrategy的继承结构，便于扩展
3. **扩展点设计**：在回测循环中支持策略特定逻辑（如定时对冲）
4. **保持性能**：继续使用Numba加速核心循环

## 架构概览

```
src/
├── strategies/              # 策略模块
│   ├── base_strategy.py     # 策略基类
│   ├── standard_mm_strategy.py  # 标准做市策略
│   └── timed_hedge_strategy.py  # 定时对冲策略
├── core/
│   ├── backtest.py          # 基础回测引擎
│   └── backtest_with_hooks.py  # 带扩展点的回测引擎
└── utils/
    ├── params_manager.py    # 参数管理
    └── path_manager.py      # 路径管理
```

## 参数架构

### 参数文件格式

```json
{
  "description": "策略参数说明",
  "metadata": {
    "created_at": "2025-11-19T00:20:24",
    "version": "1.0",
    "strategy_name": "TimedHedge",
    "strategy_description": "定时对冲策略说明"
  },
  "parameters": {
    "exposure": 50000.0,
    "target_pct": 0.5,
    "taker_fee_rate": 0.00015,
    ...
  }
}
```

### 参数管理功能

1. **保存参数**：`ParamsManager.save_params()`
   - 自动添加描述和元数据
   - 支持自定义元数据

2. **加载参数**：`ParamsManager.load_params()`
   - 从JSON文件加载
   - 返回参数字典

3. **默认参数**：`ParamsManager.get_default_mm_params()`
   - 提供标准做市策略的默认参数
   - 新策略可以基于默认参数扩展

## 策略继承结构

### BaseStrategy (抽象基类)

**属性**：
- `name`: 策略名称
- `description`: 策略说明
- `params`: 参数字典
- `backtester`: 回测器实例
- `strategy_state`: 策略特定状态

**方法**：
- `preprocess_data()`: 抽象方法，数据预处理
- `run_backtest()`: 抽象方法，执行回测
- `save_params()`: 保存策略参数
- `get_params()`: 获取当前参数
- `update_params()`: 更新参数

### 策略实现

#### StandardMMStrategy

标准做市策略，使用基础回测引擎：

```python
class StandardMMStrategy(BaseStrategy):
    def run_backtest(self, data):
        # 使用 self.backtester.run_backtest()
        # 或直接调用基础回测引擎
        pass
```

#### TimedHedgeStrategy

定时对冲策略，使用带扩展点的回测引擎：

```python
class TimedHedgeStrategy(BaseStrategy):
    def __init__(self, hedge_hours=[0, 8, 16], ...):
        # 设置对冲时间点
        self.hedge_hours = hedge_hours
    
    def run_backtest(self, data):
        # 计算对冲时间戳
        hedge_timestamps = self._calculate_hedge_timestamps(data)
        
        # 调用带扩展点的回测引擎
        _run_backtest_numba_with_hooks(..., hedge_timestamps)
```

## 扩展点设计

### 回测循环扩展点

在 `backtest_with_hooks.py` 中：

1. **定时对冲扩展点**：
   - 参数：`hedge_timestamps` (时间戳数组)
   - 逻辑：在指定时间点将仓位对冲到0
   - 实现：在循环开始处检查并执行对冲

2. **未来扩展**：
   - 可以添加更多扩展点参数
   - 在循环的不同位置插入策略逻辑

### 扩展点实现原则

1. **Numba兼容**：扩展点参数必须是Numba支持的类型
2. **性能优先**：扩展逻辑应在Numba函数内部实现
3. **最小侵入**：尽量不改变原有回测逻辑
4. **可配置**：通过参数控制扩展点的启用/禁用

## 数据流

```
原始数据
    ↓
Strategy.preprocess_data()  # 策略特定的数据预处理
    ↓
Strategy.run_backtest()      # 策略特定的回测逻辑
    ↓
回测引擎（Numba加速）
    ├── 基础逻辑（标准做市）
    └── 扩展点逻辑（策略特定）
    ↓
回测结果
    ↓
性能分析
    ↓
结果保存
```

## 使用示例

### 创建策略

```python
from src.strategies.timed_hedge_strategy import TimedHedgeStrategy

# 创建定时对冲策略
strategy = TimedHedgeStrategy(
    hedge_hours=[0, 8, 16],  # UTC时间：0点、8点、16点
    params={
        "exposure": 50000,
        "target_pct": 0.5
    }
)
```

### 执行回测

```python
# 执行回测
results = strategy.run_backtest(data)

# 获取结果
accounts = results["accounts"]
performance = results["performance"]
hedge_info = performance["hedge_info"]
```

### 参数管理

```python
# 保存参数
strategy.save_params(Path("strategy_params.json"))

# 从文件加载
strategy2 = TimedHedgeStrategy(
    hedge_hours=[0, 8, 16],
    params_file=Path("strategy_params.json")
)
```

## 测试验证

### 定时对冲策略测试

测试脚本：`tests/test_timed_hedge_strategy.py`

测试内容：
1. 数据读取（Binance）
2. 数据采样（20%作为Blofin）
3. 数据合并
4. 策略创建
5. 回测执行
6. 对冲效果验证
7. 结果保存

### 验证要点

1. **对冲时间点**：检查是否在指定时间点执行对冲
2. **仓位归零**：验证对冲后仓位是否为0
3. **挂单处理**：验证对冲时是否正确撤单
4. **性能指标**：验证回测结果是否合理

## 架构优势

1. **可扩展性**：易于添加新策略
2. **参数管理**：统一的参数保存和加载
3. **性能保持**：继续使用Numba加速
4. **代码复用**：基础逻辑复用，策略特定逻辑分离
5. **易于测试**：每个策略可独立测试

## 未来扩展

1. **更多策略类型**：
   - 网格策略
   - 套利策略
   - 趋势跟踪策略

2. **更多扩展点**：
   - 定时调仓
   - 风险控制触发
   - 条件订单

3. **参数优化**：
   - 参数网格搜索
   - 遗传算法优化
   - 贝叶斯优化

