# Numba回测框架 - 策略架构与流程文档

## 1. 概述

本框架是一个基于Numba加速的高频交易回测系统，支持多交易所数据融合、策略继承、定时对冲、资金费率等高级功能。

## 2. 策略创建与继承

### 2.1 策略基类 (BaseStrategy)

位置: `src/strategies/base_strategy.py`

所有策略必须继承自 `BaseStrategy` 基类，实现以下抽象方法：

```python
from src.strategies.base_strategy import BaseStrategy

class MyStrategy(BaseStrategy):
    def __init__(self, params: Optional[Dict[str, Any]] = None):
        super().__init__(
            name="MyStrategy",
            description="策略描述",
            params=params
        )
    
    def preprocess_data(self, data: np.ndarray) -> np.ndarray:
        """预处理数据"""
        return data
    
    def run_backtest(self, data: np.ndarray) -> Dict[str, Any]:
        """执行回测"""
        # 实现策略逻辑
        pass
```

### 2.2 策略属性

- `name`: 策略名称
- `description`: 策略说明
- `params`: 策略参数字典
- `backtester`: `MarketMakerBacktester` 实例
- `strategy_state`: 策略特定状态字典

### 2.3 已实现策略

#### TimedHedgeStrategy (定时对冲策略)

位置: `src/strategies/timed_hedge_strategy.py`

**功能**:
- 在指定时间点将仓位对冲到目标比例
- 支持时区设置（默认UTC+8）
- 支持对冲间隔（如每2小时）
- 支持资金费率处理

**参数**:
- `hedge_hours`: 对冲时间点列表（小时），如 `[0, 8, 16]`
- `hedge_target_ratio`: 对冲目标比例，0表示对冲到0，0.2表示对冲到20%仓位
- `timezone_offset`: 时区偏移（小时），默认8（UTC+8），0表示UTC
- `hedge_interval_hours`: 对冲间隔（小时），如2表示每2小时对冲一次（1,3,5,7...23点）

**使用示例**:
```python
strategy = TimedHedgeStrategy(
    hedge_hours=[],
    hedge_target_ratio=0.2,
    timezone_offset=8,  # UTC+8
    hedge_interval_hours=2,
    params={
        "exposure": 50000,
        "target_pct": 0.5,
        "funding_rate_data": funding_data.tolist()
    }
)
```

## 3. 策略执行逻辑

### 3.1 回测核心逻辑

位置: `src/core/backtest.py`

核心函数: `_run_backtest_numba`

**功能**:
- 使用Numba JIT加速的核心回测循环
- 支持可选的扩展点（定时对冲、资金费率）
- 处理Taker Trade（真实成交，mm_flag=0）
- 处理Maker Trade（挂单成交，mm_flag!=0）
- 策略逻辑（下单、撤单、改单）

**扩展点参数**:
- `hedge_timestamps`: 定时对冲时间戳数组（毫秒），空数组或-1表示禁用
- `hedge_target_ratios`: 对冲目标比例数组
- `funding_rate_data`: 资金费率数据 `[[ts, funding_rate], ...]`

**数据流**:
1. 遍历数据feed
2. 检查定时对冲（扩展点1）
3. 检查资金费率支付（扩展点2）
4. 处理Taker Trade（mm_flag=0）
5. 处理Maker Trade（mm_flag!=0）
6. 执行策略逻辑（下单、撤单、改单）

### 3.2 回测包装类

位置: `src/wrapper/backtester.py`

类: `MarketMakerBacktester`

**功能**:
- 封装策略参数和执行逻辑
- 提供统一的回测接口
- 支持扩展点参数传递

**使用示例**:
```python
backtester = MarketMakerBacktester(
    exposure=50000,
    target_pct=0.5,
    # ... 其他参数
)

backtester.run_backtest(
    data_feed=data,
    hedge_timestamps=hedge_timestamps,
    hedge_target_ratios=hedge_target_ratios,
    funding_rate_data=funding_rate_data
)
```

## 4. 数据需求

### 4.1 市场数据格式

**aggtrade数据**:
- 格式: `[timestamp, order_side, price, quantity, mm_flag]`
- `timestamp`: 时间戳（毫秒）
- `order_side`: 订单方向，1表示买入，-1表示卖出
- `price`: 成交价格
- `quantity`: 成交数量
- `mm_flag`: 数据源标识
  - `0`: blofin trades (真实成交，Taker Trade)
  - `1`: binance trades (市场数据)
  - `2`: okx trades (市场数据)
  - `3`: bybit trades (市场数据)
  - `-1`: binance orderbook (市场数据)
  - `-2`: funding_rate (市场数据)

### 4.2 资金费率数据格式

**资金费率数据**:
- 格式: `[[timestamp, funding_rate], ...]`
- `timestamp`: 资金费结算时间戳（毫秒）
- `funding_rate`: 资金费率（每8小时的费率）

## 5. 数据加载方法

### 5.1 DataPreparer类

位置: `src/data/preparer.py`

**功能**:
- 从数据源读取并准备回测数据
- 支持Binance aggtrade数据读取
- 支持资金费率数据读取（整合bigdata_plan工具）

**方法**:
- `prepare_binance_aggtrades()`: 准备Binance逐笔成交数据
- `prepare_funding_rate()`: 准备资金费率数据

### 5.2 数据预处理

位置: `src/data/preprocessor.py`

**功能**:
- `preprocess_aggtrades()`: 预处理逐笔成交数据
- `merge_exchange_data()`: 合并多交易所数据
- `validate_data()`: 验证数据格式

### 5.3 数据加载示例

```python
from src.data.preparer import DataPreparer
from src.data.preprocessor import merge_exchange_data

preparer = DataPreparer()

# 读取aggtrade数据
binance_data = preparer.prepare_binance_aggtrades(
    symbol="AXSUSDT",
    trading_type="um",
    start_date=start_date,
    end_date=end_date
)

# 读取资金费率数据
funding_data = preparer.prepare_funding_rate(
    symbol="AXSUSDT",
    start_date=start_date,
    end_date=end_date
)

# 合并数据（如果需要多交易所）
merged_data = merge_exchange_data([binance_data], [1])
```

## 6. 数据结构

### 6.1 输入数据结构

**市场数据数组** (`data_feed`):
- Shape: `(N, 5)`
- 列: `[timestamp, order_side, price, quantity, mm_flag]`
- 类型: `np.float64`

**资金费率数据数组** (`funding_rate_data`):
- Shape: `(M, 2)`
- 列: `[timestamp, funding_rate]`
- 类型: `np.float64`

### 6.2 输出数据结构

**账户日志** (`accounts_log`):
- Shape: `(K, 10)`
- 列: `[timestamp, cash, pos, avg_cost_price, price, quantity, order_side, taker_fee, maker_fee, type]`
- `type`: 交易类型标识
  - `0`: Taker Trade
  - `1`: Taker下单（止损/止盈）
  - `2`: Maker Trade
  - `5`: 定时对冲
  - `6`: 资金费支付

**订单统计日志** (`place_orders_stats_log`):
- Shape: `(L, 13)`
- 列: `[init_ts, lifecycle, price, side, origin_vol, finish_vol, avg_price, init_price, info, revoke_cnt, adj_price_cnt, desc_volume_cnt, asc_volume_cnt]`

## 7. 回测结果输出

### 7.1 性能指标

位置: `src/analysis/statistics.py`

函数: `analyze_performance()`

**返回结构**:
```python
{
    'overall_performance': {
        'total_pnl_with_fees': float,
        'total_pnl_no_fees': float,
        'pnl_with_fees_ratio': float,  # bps
        'max_drawdown': float,
        'sharpe_ratio': float,
        'calmar_ratio': float,
        'annualized_return': float
    },
    'maker_performance': {
        'total_maker_pnl_no_fees': float,
        'maker_volume_total': float,
        'maker_pnl_ratio': float,  # bps
        'actual_maker_fees_cost_rebate': float
    },
    'taker_performance': {
        'total_taker_pnl_no_fees': float,
        'taker_volume_total': float,
        'taker_pnl_ratio': float,  # bps
        'actual_taker_fees_cost': float
    },
    'fee_analysis': {
        'total_actual_fees': float
    },
    'funding_analysis': {
        'total_funding_fee': float,
        'funding_income': float,
        'funding_income_ratio': float,  # 资金费收入占比（%）
        'funding_return_rate': float  # 资金费交易额收益率（bps）
    },
    'order_behavior_metrics': {
        'avg_fill_time_sec': float,
        'median_fill_time_sec': float,
        'avg_fill_rate': float,
        'finish_all_pct': float,
        'finish_hit_pct': float,
        'avg_slippage_pct': float,
        'total_slippage_value': float,
        'api_calls_per_minute': dict
    }
}
```

### 7.2 结果保存

位置: `src/utils/path_manager.py`

**目录结构**:
```
results/
  prod/ 或 test/
    YYYY_MM_DD/
      HH_MM/
        SYMBOL/
          SYMBOL_target_scenario_params/
            performance.json
            strategy_params.json
            comprehensive_analysis.png
            ...
```

**注意**: 为节省空间，不保存npy大文件（accounts.npy, place_orders_stats.npy, funding_rate_data.npy）

## 8. 分析方法

### 8.1 统计分析

位置: `src/analysis/statistics.py`

**功能**:
- 计算总体绩效指标
- 计算Maker/Taker绩效
- 计算手续费分析
- 计算资金费分析
- 计算订单行为指标

### 8.2 可视化分析

位置: `src/analysis/visualization.py`

**函数**: `plot_comprehensive_analysis()`

**图表内容**:
1. **价格和盈亏图**（双y轴）
   - 左y轴: 价格
   - 右y轴: 累计PnL

2. **仓位和累计交易额图**（双y轴）
   - 左y轴: 仓位
   - 右y轴: 累计Maker/Taker交易额

3. **订单成交点图**
   - Maker Buy (绿色圆形)
   - Maker Sell (红色圆形)
   - Taker Buy (绿色三角形)
   - Taker Sell (红色三角形)
   - 标记大小根据订单金额归一化

4. **资金费率和累计收益图**（双y轴）
   - 左y轴: 资金费率（bps）
   - 右y轴: 累计资金费收益

5. **统计图表**
   - 左图: 仓位价值分布
   - 右图: 订单类型统计

6. **统计指标表格**
   - 总体绩效
   - Maker/Taker绩效
   - 手续费
   - 资金费统计
   - 订单行为指标
   - API调用统计

## 9. 完整流程

### 9.1 数据准备流程

1. **配置参数**
   - 交易对符号
   - 时间范围
   - 数据源

2. **读取aggtrade数据**
   - 使用DataPreparer或直接使用DuckDB读取
   - 打印数据shape和时间范围

3. **读取资金费率数据**
   - 使用DataPreparer.prepare_funding_rate()
   - 打印数据shape和时间范围
   - 检查时间对齐

4. **数据预处理**
   - 合并多交易所数据
   - 验证数据格式

### 9.2 策略执行流程

1. **创建策略实例**
   - 设置策略参数
   - 配置对冲参数（时间、比例、时区）
   - 传入资金费率数据

2. **执行回测**
   - 调用strategy.run_backtest()
   - 内部调用核心回测函数
   - 返回回测结果

3. **性能分析**
   - 调用analyze_performance()
   - 计算各项指标

4. **结果保存**
   - 创建结果目录
   - 保存performance.json
   - 保存strategy_params.json
   - 不保存npy大文件

5. **可视化**
   - 调用plot_comprehensive_analysis()
   - 生成综合分析图表

### 9.3 完整示例

```python
from datetime import datetime, timedelta, timezone
from src.data.preparer import DataPreparer
from src.strategies.timed_hedge_strategy import TimedHedgeStrategy
from src.utils.path_manager import create_result_directory
from src.analysis.visualization import plot_comprehensive_analysis
from src.analysis.statistics import analyze_performance

# 1. 配置参数
symbol = "AXSUSDT"
days = 10
end_date = datetime.now(timezone.utc)
start_date = end_date - timedelta(days=days)

# 2. 读取数据
preparer = DataPreparer()
binance_data = preparer.prepare_binance_aggtrades(...)
funding_data = preparer.prepare_funding_rate(...)

# 3. 创建策略
strategy = TimedHedgeStrategy(
    hedge_target_ratio=0.2,
    timezone_offset=8,  # UTC+8
    hedge_interval_hours=2,
    params={
        "exposure": 50000,
        "target_pct": 0.5,
        "funding_rate_data": funding_data.tolist()
    }
)

# 4. 执行回测
results = strategy.run_backtest(merged_data)

# 5. 分析结果
performance = analyze_performance(
    accounts_raw=results["accounts"],
    place_orders_stats_raw=results["place_orders_stats"]
)

# 6. 保存结果
run_dir, manager = create_result_directory(...)
manager.save_results(performance, "performance.json")

# 7. 可视化
plot_comprehensive_analysis(
    accounts=results["accounts"],
    place_orders_stats=results["place_orders_stats"],
    performance=performance,
    save_path=str(manager.get_output_path("comprehensive_analysis.png"))
)
```

## 10. 注意事项

1. **数据对齐**: 确保aggtrade数据和资金费率数据的时间范围对齐
2. **内存管理**: 不保存npy大文件，节省存储空间
3. **时区设置**: 定时对冲默认使用UTC+8，可通过`timezone_offset`参数调整
4. **资金费计算**: 资金费率数据应为每8小时的费率
5. **数据验证**: 在回测前验证数据格式和完整性

## 11. 扩展开发

### 11.1 创建新策略

1. 继承`BaseStrategy`
2. 实现`preprocess_data()`和`run_backtest()`方法
3. 在`run_backtest()`中调用核心回测函数，传入扩展点参数

### 11.2 添加新的扩展点

1. 在`_run_backtest_numba()`中添加新的扩展点逻辑
2. 在`MarketMakerBacktester.run_backtest()`中添加参数传递
3. 在策略类中生成扩展点数据并传递

## 12. 测试验证

测试脚本: `tests/test_timed_hedge_with_funding.py`

**测试内容**:
- AXSUSDT 10天数据
- 20%数据作为Blofin trades
- 每2小时对冲一次，对冲到20%仓位
- 资金费率数据处理
- 完整的数据加载打印和时间对齐检查
- 不保存npy大文件

**执行测试**:
```bash
cd /home/wilson/hummingbot/numba_bt
python3 tests/test_timed_hedge_with_funding.py
```

