# 盈亏为0问题修复总结

## 问题诊断结果

### 发现的问题

1. **理论盈亏与实际盈亏不一致**
   - 理论盈亏应该是正的（$12.22, $27.94等）或负的（-$42.71等）
   - 但实际盈亏都是$0.00
   - 所有executor的`net_pnl_pct`都是0.0000%

2. **价格变化存在但盈亏为0**
   - Entry=$183.6599, Exit=$185.0800, 变化=0.7732%
   - Entry=$182.5361, Exit=$184.8800, 变化=1.2841%
   - 价格确实有变化，但盈亏为0

3. **止盈止损设置可能过小**
   - 当前止盈: 0.50%
   - 当前止损: 1.00%
   - 交易成本: 0.08% (开仓+平仓)
   - 止盈设置(0.50%)虽然大于交易成本(0.08%)，但可能仍然太小

## 已尝试的修复

1. **修复`df_filtered[:close_timestamp]`切片**
   - 改为使用`df_filtered[df_filtered.index <= close_timestamp]`确保包含close_timestamp这一行
   - 问题仍然存在

2. **修复`get_executor_info_at_timestamp`**
   - 确保executor关闭时获取最后一行数据
   - 问题仍然存在

3. **修复`net_pnl_quote`计算**
   - 确保使用正确的`net_pnl_pct`和`filled_amount_quote`计算
   - 问题仍然存在

4. **修复`fillna`逻辑**
   - 分别处理start_timestamp之前和之后的行
   - 问题仍然存在

## 可能的原因

1. **`net_pnl_pct`在截断后丢失**
   - 在`df_filtered = df_filtered[df_filtered.index <= close_timestamp]`后，`net_pnl_pct`可能没有被正确保留
   - 需要检查截断后的DataFrame是否包含正确的`net_pnl_pct`值

2. **`get_executor_info_at_timestamp`获取的行不正确**
   - 虽然已经修复了获取最后一行的逻辑，但可能还有其他问题
   - 需要检查`last_entry['net_pnl_pct']`的实际值

3. **`net_pnl_pct`计算本身有问题**
   - `price_returns`计算可能有问题
   - `net_returns`计算可能有问题
   - 需要检查`net_pnl_pct`在DataFrame中的实际值

## 下一步行动

1. **创建详细的调试脚本**
   - 直接检查`executor_simulation` DataFrame的内容
   - 打印`net_pnl_pct`在最后几行的值
   - 验证`get_executor_info_at_timestamp`返回的值

2. **检查`net_pnl_pct`计算逻辑**
   - 验证`price_returns`计算是否正确
   - 验证`net_returns`计算是否正确
   - 验证`net_pnl_quote`计算是否正确

3. **检查止盈止损触发逻辑**
   - 验证`close_timestamp`是否正确
   - 验证`close_type`是否正确
   - 验证截断后的DataFrame是否包含正确的数据

## 建议

1. **调整止盈止损参数**
   - 将止盈从0.50%提高到至少0.20%以上（覆盖交易成本）
   - 保持止损在1.00%

2. **进一步调试**
   - 需要更详细的调试信息来确定问题的根本原因
   - 可能需要直接检查`executor_simulation` DataFrame的内容

