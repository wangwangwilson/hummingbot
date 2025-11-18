# 回测框架架构说明

## 模块划分

### 1. 数据模块 (`src/data/`)

#### `preprocessor.py` - 数据预处理
- **功能**: 将原始数据转换为回测所需的标准格式
- **主要函数**:
  - `preprocess_aggtrades()`: 预处理逐笔成交数据
  - `merge_exchange_data()`: 合并多个交易所的数据
  - `validate_data()`: 验证数据格式

#### `preparer.py` - 数据准备
- **功能**: 从数据源读取并准备回测数据
- **主要类**: `DataPreparer`
- **方法**:
  - `prepare_binance_aggtrades()`: 准备Binance数据（复用现有读取器）
  - `prepare_from_duckdb()`: 直接从DuckDB读取parquet文件
  - `prepare_multi_exchange()`: 准备多交易所融合数据

### 2. 核心回测引擎 (`src/core/`)

#### `backtest.py` - Numba加速的回测核心
- **功能**: 使用Numba JIT编译的核心回测循环
- **主要函数**: `_run_backtest_numba()`
- **特点**: 
  - 纯NumPy数组操作
  - Numba JIT编译加速
  - 支持Maker/Taker策略逻辑

### 3. 回测包装类 (`src/wrapper/`)

#### `backtester.py` - 策略回测器
- **功能**: 封装策略参数和执行逻辑
- **主要类**: `MarketMakerBacktester`
- **方法**:
  - `__init__()`: 初始化策略参数
  - `run_backtest()`: 执行回测

### 4. 结果分析 (`src/analysis/`)

#### `statistics.py` - 统计分析
- **功能**: 计算回测性能指标
- **主要函数**: `analyze_performance()`
- **输出指标**:
  - 总体绩效: PnL、夏普比率、最大回撤、年化收益等
  - Maker/Taker绩效: 分类统计
  - 订单行为: 成交时间、成交率、滑点等

#### `visualization.py` - 可视化
- **功能**: 生成回测结果图表
- **主要函数**:
  - `plot_equity_curve()`: 净值曲线
  - `plot_drawdown()`: 回撤曲线
  - `plot_trade_distribution()`: 交易分布

## 数据流

```
原始数据 (ZIP/Parquet)
    ↓
DataPreparer (数据准备)
    ↓
预处理后的NumPy数组 [timestamp, side, price, quantity, mm_flag]
    ↓
MarketMakerBacktester.run_backtest()
    ↓
Numba加速的回测循环
    ↓
回测结果 (accounts, place_orders_stats)
    ↓
analyze_performance() (统计分析)
    ↓
性能指标字典
    ↓
可视化图表
```

## 数据格式

### 输入数据格式
```python
np.ndarray shape: (N, 5)
列:
  0: timestamp (int64) - 时间戳（毫秒）
  1: order_side (float64) - 方向 (1=buy, -1=sell)
  2: price (float64) - 成交价格
  3: quantity (float64) - 成交数量
  4: mm_flag (float64) - 交易所标识 (0=市场数据, 1=用户订单)
```

### 输出数据格式

#### accounts (账户记录)
```python
np.ndarray shape: (M, 10)
列:
  0: timestamp
  1: cash
  2: pos
  3: avg_cost_price
  4: trade_price
  5: trade_quantity
  6: order_side
  7: taker_fee
  8: maker_fee
  9: order_role (0=市场, 1=Taker, 2=Maker)
```

#### place_orders_stats (订单统计)
```python
np.ndarray shape: (K, 13)
列:
  0: init_place_ts
  1: lifecycle_ms
  2: last_limit_price
  3: order_side
  4: place_origin_volume
  5: finish_volume
  6: avg_match_trade_price
  7: init_place_order_price
  8: info
  9: revoke_cnt
  10: adj_price_cnt
  11: desc_volume_cnt
  12: asc_volume_cnt
```

## 多交易所支持

框架支持融合多个交易所的数据进行回测：

1. **单交易所**: 直接使用 `prepare_binance_aggtrades()` 或 `prepare_from_duckdb()`
2. **多交易所**: 使用 `prepare_multi_exchange()` 传入多个数据源配置

每个数据源通过 `exchange_flag` 标识，在回测过程中可以区分不同交易所的数据。

## 性能优化

1. **Numba JIT编译**: 核心回测循环使用 `@njit` 装饰器加速
2. **NumPy数组**: 所有数据操作使用NumPy数组，避免Python循环
3. **预分配内存**: 结果数组预先分配，避免动态扩容
4. **向量化操作**: 尽可能使用NumPy向量化操作

## 扩展性

- **新交易所**: 在 `preparer.py` 中添加新的数据准备方法
- **新策略**: 修改 `backtest.py` 中的策略逻辑
- **新指标**: 在 `statistics.py` 中添加新的计算函数
- **新图表**: 在 `visualization.py` 中添加新的绘图函数

