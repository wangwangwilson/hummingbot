# mm_flag 设计规则文档

## 设计原则

采用硬编码方式，提前设计好数据类型，便于未来扩展和兼容不同的数据源。

## mm_flag 编码规则

| mm_flag | 数据类型 | 处理方式 | 说明 |
|---------|---------|---------|------|
| 0 | blofin trades | Taker Trade | 真实成交，会直接更新账户 |
| 1 | binance trades | 市场数据 | 用于更新价格和检查挂单成交 |
| 2 | okx trades | 市场数据 | 用于更新价格和检查挂单成交 |
| 3 | bybit trades | 市场数据 | 用于更新价格和检查挂单成交 |
| -1 | binance orderbook | 市场数据 | 订单簿数据，用于更新价格 |
| -2 | funding_rate | 市场数据 | 资金费率数据，用于更新价格 |

## 处理逻辑

### 1. Taker Trade 处理（mm_flag == 0）

只有当 `mm_flag == 0` 时，才会处理为交易所的真实成交（Taker Trade）：

```python
if mm_flag == 0:
    # 更新仓位和资金
    pos += order_side * trade_quantity
    cash -= order_side * trade_quantity * trade_price
    # 记录账户变化
    accounts_log[accounts_idx] = [...]
```

### 2. 市场数据处理（mm_flag != 0）

当 `mm_flag != 0` 时，只更新市场价格，不直接更新账户：

```python
else:
    # 只更新市场价格
    last_mark_price = trade_price
```

### 3. Maker Trade 撮合（mm_flag != 0）

只有市场数据（`mm_flag != 0`）才能触发挂单成交：

```python
if is_order_active and mm_flag != 0 and now_place_order[2] * order_side < 0:
    # 检查挂单是否成交
    # 如果成交，更新账户并记录为Maker Trade
```

## 数据准备

### 默认值

- 如果数据没有mm_flag列，使用默认值：
  - Binance数据：`mm_flag = 1`
  - Blofin数据：`mm_flag = 0`
  - 其他数据源：根据交易所类型设置

### 数据合并

多个数据源合并时，保持各自的mm_flag值：

```python
# Blofin数据
blofin_data[:, 4] = 0  # mm_flag = 0

# Binance数据
binance_data[:, 4] = 1  # mm_flag = 1

# 合并
merged_data = merge_exchange_data([blofin_data, binance_data], [0, 1])
```

## 测试验证

### 测试场景

使用AXS最近3天数据进行完整测试：

1. **数据准备**：
   - 读取Binance数据（mm_flag=1）
   - 从Binance数据中随机采样20%作为Blofin数据（mm_flag=0）
   - 合并数据

2. **回测参数**：
   - exposure = 50000
   - target_pct = 0.5

3. **验证点**：
   - 数据读取和合并正常
   - mm_flag分类正确
   - 回测执行正常
   - 账户变动记录正确
   - 性能分析正常
   - 可视化图表生成正常

### 测试结果

```
总交易记录数: 33426
  - Blofin trades (mm_flag=0): 5571 条
  - Binance trades (mm_flag=1): 27855 条
账户变动记录数: 5869
订单生命周期记录数: 1

总体绩效:
  总PnL (含手续费): -93.78
  总PnL (不含手续费): 68.71
  Taker PnL: 1433.72
```

## 扩展性

### 添加新数据源

1. 在编码规则表中添加新的mm_flag值
2. 在数据预处理时设置对应的mm_flag
3. 回测逻辑自动支持（因为只有mm_flag==0才处理为Taker Trade）

### 示例：添加新交易所

```python
# 假设添加Coinbase数据
# mm_flag = 4: coinbase trades (市场数据)

coinbase_data[:, 4] = 4  # 设置mm_flag
merged_data = merge_exchange_data([blofin_data, binance_data, coinbase_data], [0, 1, 4])
```

## 注意事项

1. **mm_flag=0的特殊性**：只有mm_flag=0的数据会直接更新账户，其他都是市场数据
2. **数据顺序**：合并数据时需要按时间戳排序
3. **数据完整性**：如果数据缺少mm_flag列，使用默认值0或1
4. **性能考虑**：mm_flag判断使用`==`而不是`!=`，因为只有0需要特殊处理

