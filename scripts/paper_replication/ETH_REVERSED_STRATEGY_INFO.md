# ETH-USDT 反向策略回测信息

## 策略修改说明

### 问题分析
根据回测结果，ETH-USDT的PMM Bar Portion策略持续亏损，仓位主要偏向空仓（负值）。用户建议将MACD和BP策略的方向反转，验证是否能够改善收益。

### 修改内容

#### 1. PMM Bar Portion策略（`controllers/market_making/pmm_bar_portion.py`）

**修改位置1**：数据不足时的简单计算（第287行）
```python
# 修改前：
price_shift = float(current_bp) * 0.001

# 修改后：
price_shift = -float(current_bp) * 0.001  # 反转方向
```

**修改位置2**：正常情况下的回归预测（第347行）
```python
# 修改前：
price_shift = self.predict_price_shift(current_bp)

# 修改后：
price_shift = -self.predict_price_shift(current_bp)  # 反转方向
```

#### 2. PMM Dynamic (MACD)策略（`controllers/market_making/pmm_dynamic.py`）

**修改位置1**：数据不足时的计算（第152行）
```python
# 修改前：
price_multiplier = ((0.5 * macd_signal + 0.5 * macdh_signal) * float(max_price_shift)).iloc[-1]

# 修改后：
price_multiplier = -((0.5 * macd_signal + 0.5 * macdh_signal) * float(max_price_shift)).iloc[-1]  # 反转方向
```

**修改位置2**：正常情况下的计算（第192行）
```python
# 修改前：
price_multiplier = ((0.5 * macd_signal + 0.5 * macdh_signal) * max_price_shift).iloc[-1]

# 修改后：
price_multiplier = -((0.5 * macd_signal + 0.5 * macdh_signal) * max_price_shift).iloc[-1]  # 反转方向
```

### 回测配置

- **交易对**: ETH-USDT
- **回测区间**: 2025-01-01 到 2025-11-09
- **K线分辨率**: 15分钟（从1分钟数据重采样）
- **画图频率**: 3分钟
- **环境**: prod
- **策略**: 
  - PMM Simple（未修改，作为对照）
  - PMM Dynamic (MACD) Reversed（方向反转）
  - PMM Bar Portion Reversed（方向反转）

### 预期效果

通过反转价格调整方向：
- **原策略**：BP/MACD信号为正时，提高reference_price，导致更多卖单（空仓）
- **反转策略**：BP/MACD信号为正时，降低reference_price，导致更多买单（多仓）

如果原策略持续亏损且偏向空仓，反转后应该：
1. 仓位偏向多仓（正值）
2. 如果市场趋势向上，反转策略应该能够盈利

### 回测状态

**启动时间**: 2025-11-14 22:12

**状态**: 进行中

### 注意事项

⚠️ **重要**：这些修改会影响所有使用BP和MACD策略的回测。如果需要在其他回测中使用原始方向，需要：
1. 回测完成后，将修改恢复
2. 或者创建一个策略变体，通过配置参数控制方向

### 结果对比

回测完成后，将对比：
- **原始策略** vs **反转策略**的：
  - 总PnL
  - 仓位分布（多仓/空仓比例）
  - 成交率
  - 日均收益率

