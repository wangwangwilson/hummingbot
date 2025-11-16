# SOL回测详细分析报告

## 时间区间
- **开始日期**: 2025-09-01
- **结束日期**: 2025-11-01
- **数据量**: 87,361 条K线

## 1. 回测逻辑和Executor概念

### 回测逻辑流程
```
1. 加载历史K线数据（1分钟K线）
2. 逐行处理每个K线：
   a. 更新市场状态（当前价格、时间戳）
   b. 更新策略因子（Bar Portion、回归模型、参考价格）
   c. 计算挂单价格和数量（基于参考价格和spread）
   d. 创建新的Executor（如果需要新的挂单）
   e. 检查现有Executor是否成交（价格是否触及挂单价格）
   f. 检查Executor是否达到关闭条件（止损/止盈/时间限制/EARLY_STOP）
3. 汇总所有Executor的结果
```

### Executor概念
**Executor**是策略执行单元，代表一个订单的执行：

- **创建**: 策略根据市场条件创建Executor，包含：
  - 方向（BUY/SELL）
  - 挂单价格（entry_price）
  - 数量（amount）
  - 止损/止盈配置
  - 时间限制

- **成交条件**:
  - **买单**: 当市场价格 <= 挂单价格时成交
  - **卖单**: 当市场价格 >= 挂单价格时成交

- **关闭条件**:
  - **TAKE_PROFIT**: 达到止盈（2%）
  - **STOP_LOSS**: 达到止损（3%）
  - **TIME_LIMIT**: 达到时间限制（45分钟）
  - **EARLY_STOP**: 提前停止（60秒内未成交）

## 2. 数据准备分析

### ✅ 数据质量
- **数据量**: 87,361 条K线
- **加载时间**: 0.18秒
- **时间范围**: 2025-09-01 08:00:00 至 2025-11-01 00:00:00
- **缺失值**: 0
- **价格范围**: $148.52 - $253.20
- **平均价格**: $210.75
- **价格波动**: $18.93
- **数据连续性**: ✅ 正常

### ⚠️ 数据问题
- 有一个zip文件损坏（SOLUSDT-1m-2025-11-01.zip），但不影响主要数据

## 3. 因子生成分析

### ✅ 因子生成正常
- **特征数据量**: 87,361 行
- **特征列**: timestamp, open, high, low, close, volume, bar_portion, returns, spread_multiplier, reference_price, price_shift
- **最新参考价格**: $187.72
- **Spread multiplier**: 0.0017 (0.17%)

### 因子计算逻辑
1. **Bar Portion**: 计算K线的Bar Portion指标
2. **线性回归**: 使用Bar Portion预测价格变化
3. **参考价格**: `current_close * (1 + price_shift)`
4. **动态Spread**: 基于NATR（归一化真实波动率）

## 4. 挂单逻辑分析

### 挂单价格计算
- **参考价格**: $187.72
- **Spread配置**: 1% 和 2%
- **Spread multiplier**: 0.17%

**实际Spread**:
- 买单1: 1% × 0.17% = 0.17% → 价格 $187.72 × (1 - 0.0017) = $187.40
- 买单2: 2% × 0.17% = 0.34% → 价格 $187.72 × (1 - 0.0034) = $187.08
- 卖单1: 1% × 0.17% = 0.17% → 价格 $187.72 × (1 + 0.0017) = $188.04
- 卖单2: 2% × 0.17% = 0.34% → 价格 $187.72 × (1 + 0.0034) = $188.36

**但实际计算**:
- 买单1: $185.84 (spread: 1.00%)
- 买单2: $183.96 (spread: 2.00%)
- 卖单1: $189.59 (spread: 1.00%)
- 卖单2: $191.47 (spread: 2.00%)

### ⚠️ 问题发现

**挂单价格与市场价格对比**:
- **最近100个K线价格范围**: $187.01 - $190.02
- **最低买单价**: $183.96
- **最高卖单价**: $191.47
- **价格触及买单范围**: 0 次
- **价格触及卖单范围**: 10 次

**问题**:
1. **买单价格太低**: 买单价格($183.96-$185.84)远低于市场价格($187-$190)
2. **无法成交**: 市场价格从未触及买单范围
3. **卖单价格合理**: 卖单价格($189.59-$191.47)在市场价格范围内

## 5. Executor创建和关闭分析

### Executor创建
- **总Executor数**: 16,408
- **成交Executor数**: 4 (0.02%)
- **未成交Executor数**: 16,404 (99.98%)

### 关闭类型统计
- **EARLY_STOP**: 16,404 (99.98%)
- **TIME_LIMIT**: 4 (0.02%)

### EARLY_STOP原因
在`market_making_controller_base.py`的`executors_to_refresh`方法中：
```python
filter_func=lambda x: not x.is_trading and x.is_active and 
self.market_data_provider.time() - x.timestamp > self.config.executor_refresh_time
```

**EARLY_STOP条件**:
- `not x.is_trading`: Executor未成交
- `x.is_active`: Executor仍活跃
- `time() - x.timestamp > executor_refresh_time`: 超过60秒未成交

**含义**: 如果Executor在60秒内没有成交，就会被提前停止，避免挂单时间过长。

## 6. 根本原因分析

### 问题1: 挂单价格计算错误

**现象**:
- 买单价格: $183.96 - $185.84
- 市场价格: $187.01 - $190.02
- 买单价格低于市场价格，无法成交

**原因分析**:
在`get_price_and_amount`中（第330-333行）:
```python
reference_price = Decimal(self.processed_data["reference_price"])
spread_in_pct = Decimal(spreads[int(level)]) * Decimal(self.processed_data["spread_multiplier"])
side_multiplier = Decimal("-1") if trade_type == TradeType.BUY else Decimal("1")
order_price = reference_price * (1 + side_multiplier * spread_in_pct)
```

**问题**:
- `spread_multiplier`是0.0017（0.17%），但实际使用的是`spreads[int(level)]`（1%或2%）
- 计算时：`spread_in_pct = 0.01 * 0.0017 = 0.000017`（0.0017%）
- 但实际显示的是1%和2%，说明可能没有使用`spread_multiplier`

**检查代码**:
在`pmm_bar_portion.py`中，`get_price_and_amount`可能被重写，需要检查。

### 问题2: 成交率极低

**原因**:
1. **挂单价格不合理**: 买单价格太低，无法成交
2. **EARLY_STOP机制**: 60秒内未成交就被停止
3. **Spread设置**: 可能spread设置不合理

### 问题3: 盈亏为0

**原因**:
1. **成交数量为0**: 大部分Executor未成交，`filled_amount_quote = 0`
2. **统计逻辑**: 使用`net_pnl_quote != 0`判断持仓，未成交的executor被排除

## 7. 修复建议

### 1. 检查挂单价格计算
检查`pmm_bar_portion.py`中是否重写了`get_price_and_amount`方法，确保：
- Spread计算正确
- 买单价格略低于当前市场价格
- 卖单价格略高于当前市场价格

### 2. 调整Spread设置
- 当前spread可能太小（1%-2%）
- 对于波动较大的市场，可能需要更大的spread
- 或者确保`spread_multiplier`正确应用

### 3. 调整executor_refresh_time
- 当前默认60秒可能太短
- 对于1分钟K线，可能需要更长的refresh_time（如300秒）

### 4. 修复统计逻辑
在`summarize_results`中：
```python
# 修改前
executors_with_position = executors_df[executors_df["net_pnl_quote"] != 0]

# 修改后
executors_with_position = executors_df[executors_df["filled_amount_quote"] > 0]
```

## 8. 结论

### 回测结果不正常的原因

1. **挂单价格计算有问题**: 
   - 买单价格($183.96-$185.84)远低于市场价格($187-$190)
   - 导致买单无法成交

2. **成交率极低**: 
   - 只有0.02%的executor成交
   - 大部分executor被EARLY_STOP

3. **盈亏为0**: 
   - 因为未成交，`filled_amount_quote = 0`
   - 统计逻辑使用`net_pnl_quote != 0`判断持仓，导致统计错误

### 需要修复的问题

1. ✅ 数据准备正常
2. ✅ 因子生成正常（但reference_price在某些时候为0）
3. ❌ 挂单价格计算有问题（买单价格太低）
4. ❌ 成交率极低（挂单价格不合理）
5. ❌ 统计逻辑有问题（使用错误的判断条件）

### 下一步行动

1. 检查`pmm_bar_portion.py`中的`get_price_and_amount`方法
2. 验证spread计算逻辑
3. 修复统计逻辑
4. 重新运行回测验证


