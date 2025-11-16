# Max Records限制问题修复总结

## 问题诊断

### 现象
回测中的executors和仓位变化只集中在数据的最后一天，而不是分布在整个回测时间范围内。

### 根本原因
在`LocalBacktestingDataProvider.get_candles_df`方法中，存在一个`max_records=500`的默认参数限制，导致即使加载了数千条数据，也只返回**最后500条**：

```python
def get_candles_df(self, connector_name: str, trading_pair: str, interval: str, max_records: int = 500):
    # ...
    if len(filtered_df) > max_records:
        filtered_df = filtered_df.iloc[-max_records:]  # ← 问题：只取最后500条
    return filtered_df
```

### 影响
- 请求2025-01-01到2025-01-05（4天，5281条数据）
- 实际使用：仅最后500条（约8.3小时）
- 结果：executors只在2025-01-04的最后时段创建

## 修复方案

### 代码更改
将`max_records`默认值改为`None`（不限制），并添加条件判断：

```python
def get_candles_df(self, connector_name: str, trading_pair: str, interval: str, max_records: int = None):
    """获取candles DataFrame（必须包含timestamp列）
    
    Args:
        max_records: 最大记录数（None表示不限制）
    """
    # ...
    # 限制返回的记录数（仅当max_records不为None时）
    if max_records is not None and len(filtered_df) > max_records:
        filtered_df = filtered_df.iloc[-max_records:]
    
    return filtered_df
```

### 修复文件
- `/Users/wilson/Desktop/mm_research/hummingbot/scripts/paper_replication/backtest_comparison_local.py`
  - 第406行：`max_records: int = 500` → `max_records: int = None`
  - 第457-459行：添加`if max_records is not None`条件

## 修复验证

### 修复前（2025-01-01到2025-01-05，4天测试）
```
按小时分布:
时间                 总数       成交       Buy    Sell   成交率     
------------------------------------------------------------
2025-01-04 15:00   10       4        0      4      40.0%
2025-01-04 16:00   30       12       0      12     40.0%
...
2025-01-04 23:00   28       14       6      8      50.0%

总Executors: 238
已成交Executors: 112 (47.1%)
时间跨度: 仅最后一天（2025-01-04 15:00-23:00）
```

### 修复后（2025-01-01到2025-01-05，4天测试）
```
按小时分布:
时间                 总数       成交       Buy    Sell   成交率     
------------------------------------------------------------
2025-01-01 08:00   28       12       12     0      42.9%
2025-01-01 09:00   30       12       12     0      40.0%
...
2025-01-04 22:00   28       12       0      12     42.9%
2025-01-04 23:00   30       14       8      6      46.7%

总Executors: 2,408
已成交Executors: 1,076 (44.7%)
  BUY订单: 792
  SELL订单: 284
  总PnL: $-3613.74

时间跨度: 完整4天（2025-01-01 08:00 到 2025-01-04 23:59）
✓ Executors均匀分布在整个时间范围内
✓ 多空交替正常
```

## 关键改进

1. **时间分布**：从只覆盖最后8.3小时 → 覆盖完整4天
2. **Executor数量**：从238个 → 2,408个（增加10倍）
3. **成交数量**：从112个 → 1,076个（增加近10倍）
4. **时间覆盖**：每个小时都有executors创建和成交
5. **多空交替**：BUY和SELL订单均有分布

## 下一步

- ✅ 数据加载问题已修复
- ✅ Executor时间分布已正常
- ⏭ 需要运行更长时间的回测（如1-3个月）来验证策略表现
- ⏭ 需要分析为什么BUY订单(792)远多于SELL订单(284)
- ⏭ 需要优化策略参数以提高PnL（当前为负）

## 总结

**根本问题**：`max_records=500`默认限制导致回测只使用最后500条数据。

**解决方案**：移除默认限制，改为`max_records=None`，允许使用完整数据集。

**验证结果**：修复后，executors和仓位变化均匀分布在整个回测时间范围内，符合预期。

