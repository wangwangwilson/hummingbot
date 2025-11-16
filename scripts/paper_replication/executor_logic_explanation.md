# Executor逻辑说明

## 1. Executor概念

### 什么是Executor？
- **Executor**是策略执行单元，代表一个订单的执行
- 每个Executor包含：
  - **方向**: 买入(BUY)或卖出(SELL)
  - **价格**: 挂单价格（entry_price）
  - **数量**: 订单数量（amount）
  - **止损/止盈**: Triple Barrier配置
  - **时间限制**: 订单有效期

### Executor的生命周期
1. **创建**: 策略根据市场条件创建Executor
2. **挂单**: Executor以限价单(limit order)形式挂单
3. **成交**: 当市场价格触及挂单价格时成交
4. **关闭**: 在以下情况关闭：
   - **TAKE_PROFIT**: 达到止盈
   - **STOP_LOSS**: 达到止损
   - **TIME_LIMIT**: 达到时间限制
   - **EARLY_STOP**: 提前停止（未成交且超过refresh_time）
   - **TRAILING_STOP**: 追踪止损

## 2. 回测逻辑

### 回测流程
```
1. 加载历史K线数据
2. 逐行处理每个K线：
   a. 更新市场状态（价格、时间）
   b. 更新策略因子（Bar Portion、MACD等）
   c. 计算挂单价格和数量
   d. 创建新的Executor（如果需要）
   e. 检查现有Executor是否成交
   f. 检查Executor是否达到关闭条件
3. 汇总所有Executor的结果
```

### Executor成交条件
- **买单**: 当市场价格 <= 挂单价格时成交
- **卖单**: 当市场价格 >= 挂单价格时成交

### EARLY_STOP的原因
在`market_making_controller_base.py`中：
```python
def executors_to_refresh(self):
    executors_to_refresh = self.filter_executors(
        executors=self.executors_info,
        filter_func=lambda x: not x.is_trading and x.is_active and 
        self.market_data_provider.time() - x.timestamp > self.config.executor_refresh_time
    )
```

**EARLY_STOP条件**:
- `not x.is_trading`: Executor未成交
- `x.is_active`: Executor仍活跃
- `time() - x.timestamp > executor_refresh_time`: 超过refresh_time（默认60秒）未成交

**含义**: 如果Executor在60秒内没有成交，就会被提前停止，避免挂单时间过长。

## 3. 当前问题分析

### 问题1: 成交率极低（0.02%）

**原因**:
1. **挂单价格不合理**:
   - 买单价格: $183.96 - $185.84
   - 市场价格: $187.01 - $190.02
   - 买单价格低于市场价格，无法成交

2. **Spread设置问题**:
   - 当前spread: 1% 和 2%
   - 参考价格: $187.72
   - 买单价格 = $187.72 * (1 - 0.01) = $185.84
   - 但市场价格在$187-$190，买单价格太低

3. **Executor被EARLY_STOP**:
   - 大部分Executor在60秒内未成交
   - 被标记为EARLY_STOP
   - 因此`filled_amount_quote = 0`

### 问题2: 盈亏为0

**原因**:
1. **成交数量为0**: 如果Executor未成交，`filled_amount_quote = 0`
2. **统计逻辑问题**: `summarize_results`使用`net_pnl_quote != 0`判断持仓
3. **即使成交了**: 如果价格回到entry_price，盈亏也可能为0

## 4. 修复建议

### 1. 调整Spread设置
- 当前spread可能太小（1%-2%）
- 对于波动较大的市场，可能需要更大的spread
- 或者使用动态spread（基于NATR）

### 2. 检查挂单价格计算
- 确保挂单价格在合理范围内
- 买单价格应该略低于当前市场价格
- 卖单价格应该略高于当前市场价格

### 3. 调整executor_refresh_time
- 当前默认60秒可能太短
- 对于1分钟K线，可能需要更长的refresh_time

### 4. 修复统计逻辑
- 使用`filled_amount_quote > 0`判断持仓
- 而不是`net_pnl_quote != 0`


