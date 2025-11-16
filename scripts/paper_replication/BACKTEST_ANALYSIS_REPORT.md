# 回测结果分析报告

## 📊 回测结果概览

### 时间范围
- **开始日期**: 2025-06-01
- **结束日期**: 2025-11-09
- **总时长**: 约5个月

### 交易品种
7个品种：BTC, SOL, ETH, XRP, AVAX, DOT, MYX

### 策略
- PMM Bar Portion
- PMM Dynamic (MACD)

## ⚠️ 发现的问题

### 1. 盈亏全部为0
**现象**:
- 所有品种、所有策略的 `net_pnl_quote` 都是 0
- 所有品种、所有策略的 `net_pnl` 都是 0%

**影响**:
- 无法评估策略的实际盈利能力
- 无法进行策略对比

### 2. total_executors_with_position = 0
**现象**:
- 虽然有 `filled_count > 0`（有成交的executor）
- 但 `total_executors_with_position = 0`（没有有持仓的executor）

**原因分析**:
在 `summarize_results` 中（第322行）:
```python
executors_with_position = executors_df[executors_df["net_pnl_quote"] != 0]
```

这意味着只有 `net_pnl_quote != 0` 的executor才被认为"有持仓"。
如果所有executor的盈亏都是0，就不会被计入。

### 3. total_volume = 0
**现象**:
- 虽然有成交的executor（`filled_count > 0`）
- 但 `total_volume = 0`

**原因**:
因为 `total_volume` 是从 `executors_with_position` 计算的（第324行）:
```python
total_volume = executors_with_position["filled_amount_quote"].sum()
```

如果 `executors_with_position` 为空，`total_volume` 就是0。

### 4. 成交率极低
**现象**:
- PMM Bar Portion: 成交率 0.01% - 0.20%
- PMM Dynamic: 成交率 40% - 100%（但只有4个executor）

**分析**:
- PMM Bar Portion创建了大量executor（几千到几万个），但只有4个成交
- 大部分executor被 `EARLY_STOP`（提前停止）
- 说明策略条件可能过于严格，或者市场条件不满足

## 🔍 根本原因分析

### 问题1: 盈亏计算逻辑

在 `position_executor_simulator.py` 中:
```python
# 第60行
cumulative_returns = (((1 + returns).cumprod() - 1) * side_multiplier) - trade_cost
df_filtered.loc[start_timestamp:, 'net_pnl_pct'] = cumulative_returns
df_filtered.loc[start_timestamp:, 'filled_amount_quote'] = float(config.amount) * entry_price
df_filtered['net_pnl_quote'] = df_filtered['net_pnl_pct'] * df_filtered['filled_amount_quote']
```

**可能的问题**:
1. 如果executor在 `TIME_LIMIT` 时关闭，且价格回到 `entry_price`
2. `cumulative_returns` 会接近 0（减去 `trade_cost` 后可能为很小的负数）
3. 但由于浮点数精度或计算问题，可能被计算为0

### 问题2: 统计逻辑问题

在 `summarize_results` 中:
```python
executors_with_position = executors_df[executors_df["net_pnl_quote"] != 0]
```

**问题**:
- 使用 `net_pnl_quote != 0` 来判断是否有持仓是不准确的
- 应该使用 `filled_amount_quote > 0` 来判断是否有持仓
- 一个executor可能成交了但盈亏为0（价格回到entry_price），这仍然是有效的持仓

### 问题3: filled_amount_quote 被修改

在 `position_executor_simulator.py` 第101行:
```python
df_filtered.loc[df_filtered.index[-1], "filled_amount_quote"] = df_filtered["filled_amount_quote"].iloc[-1] * 2
```

这会将最后的 `filled_amount_quote` 乘以2，但 `net_pnl_quote` 可能没有相应更新。

## ✅ 修复建议

### 1. 修改统计逻辑

在 `summarize_results` 中，应该使用 `filled_amount_quote > 0` 来判断是否有持仓:

```python
# 修改前
executors_with_position = executors_df[executors_df["net_pnl_quote"] != 0]

# 修改后
executors_with_position = executors_df[executors_df["filled_amount_quote"] > 0]
```

### 2. 检查盈亏计算

检查 `position_executor_simulator.py` 中的盈亏计算逻辑，确保:
- `net_pnl_quote` 正确计算
- 在 `TIME_LIMIT` 关闭时，盈亏应该反映实际的价格变化
- 考虑 `trade_cost` 的影响

### 3. 检查executor关闭逻辑

检查为什么大部分executor被 `EARLY_STOP`:
- 是否策略条件过于严格？
- 是否市场数据有问题？
- 是否需要调整策略参数？

### 4. 添加调试信息

在回测过程中添加调试信息，输出:
- 每个executor的 `filled_amount_quote`
- 每个executor的 `net_pnl_quote`
- 每个executor的 `close_type`
- 每个executor的 `close_timestamp`

## 📈 预期行为

### 正常情况应该:
1. **有盈亏**: 如果executor成交了，应该有盈亏（可能为正或负）
2. **有成交量**: 如果executor成交了，`total_volume` 应该 > 0
3. **有持仓统计**: 如果executor成交了，`total_executors_with_position` 应该 > 0
4. **合理的成交率**: 成交率应该在合理范围内（不是0.01%）

### 当前情况:
- ❌ 所有盈亏为0
- ❌ 所有成交量为0
- ❌ 所有持仓统计为0
- ⚠️ 成交率极低（PMM Bar Portion）

## 🎯 结论

**回测结果不正常**，主要问题：

1. **盈亏计算可能有问题**: 所有executor的盈亏都是0，这不正常
2. **统计逻辑有问题**: 使用 `net_pnl_quote != 0` 来判断持仓是不准确的
3. **成交率极低**: PMM Bar Portion策略创建了大量executor但只有极少数成交

**建议**:
1. 修复 `summarize_results` 中的统计逻辑
2. 检查并修复盈亏计算逻辑
3. 检查为什么成交率这么低
4. 重新运行回测验证修复


