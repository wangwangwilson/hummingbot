# 网格搜索结果分析报告
- 总参数组合数: 500
- 盈利组合数: 1 (0.2%)
- 亏损组合数: 499 (99.8%)
- 平均收益: -2258.31
- 最大收益: 78.62
- 最小收益: -5509.23

## 1. 参数相关性分析
参数与总收益的相关系数（绝对值越大，影响越大）:

- **order_size_pct_min**: -0.5369
- **base_target_pct**: +0.4170
- **order_size_pct_max**: -0.3878
- **base_exposure**: -0.3848
- **as_model_buy_distance**: +0.1322
- **as_model_sell_distance**: -0.0390

## 2. 盈利组 vs 亏损组对比
| 参数 | 盈利组平均 | 亏损组平均 | 差异 | P值 |
|------|-----------|-----------|------|-----|
| base_exposure | 10000.0000 | 11076.1523 | -1076.1523 | nan |
| base_target_pct | 0.6000 | 0.4958 | +0.1042 | nan |
| as_model_sell_distance | 0.9000 | 0.9996 | -0.0996 | nan |
| order_size_pct_min | 0.0300 | 0.0544 | -0.0244 | nan |
| order_size_pct_max | 0.0900 | 0.1048 | -0.0148 | nan |
| as_model_buy_distance | 1.0000 | 1.0054 | -0.0054 | nan |

## 3. Top 20% vs Bottom 20% 对比
| 参数 | Top 20%平均 | Bottom 20%平均 | 差异 |
|------|------------|---------------|------|
| base_exposure | 10630.0000 | 13000.0000 | -2370.0000 |
| base_target_pct | 0.5720 | 0.4100 | +0.1620 |
| as_model_buy_distance | 1.0270 | 0.9410 | +0.0860 |
| order_size_pct_min | 0.0388 | 0.0664 | -0.0276 |
| as_model_sell_distance | 0.9720 | 0.9910 | -0.0190 |
| order_size_pct_max | 0.0935 | 0.1119 | -0.0184 |

## 4. Top 5 参数组合
### 组合 #1 (PnL: 78.62)
- order_size_pct_min: 0.0300
- order_size_pct_max: 0.0900
- as_model_buy_distance: 1.0000
- as_model_sell_distance: 0.9000
- base_exposure: 10000.0000
- base_target_pct: 0.6000
- Sharpe Ratio: -2.7830
- Max Drawdown: 0.3916

### 组合 #2 (PnL: -191.96)
- order_size_pct_min: 0.0300
- order_size_pct_max: 0.0900
- as_model_buy_distance: 0.9000
- as_model_sell_distance: 0.8000
- base_exposure: 15000.0000
- base_target_pct: 0.6000
- Sharpe Ratio: -1.9875
- Max Drawdown: 0.3915

### 组合 #3 (PnL: -411.82)
- order_size_pct_min: 0.0300
- order_size_pct_max: 0.0900
- as_model_buy_distance: 1.0000
- as_model_sell_distance: 0.9000
- base_exposure: 12000.0000
- base_target_pct: 0.6000
- Sharpe Ratio: -2.4261
- Max Drawdown: 0.4364

### 组合 #4 (PnL: -446.14)
- order_size_pct_min: 0.0300
- order_size_pct_max: 0.1000
- as_model_buy_distance: 1.1000
- as_model_sell_distance: 0.8000
- base_exposure: 12000.0000
- base_target_pct: 0.7000
- Sharpe Ratio: -2.3671
- Max Drawdown: 0.4428

### 组合 #5 (PnL: -481.68)
- order_size_pct_min: 0.0300
- order_size_pct_max: 0.0800
- as_model_buy_distance: 1.0000
- as_model_sell_distance: 0.8000
- base_exposure: 10000.0000
- base_target_pct: 0.5000
- Sharpe Ratio: -3.5942
- Max Drawdown: 0.4352

## 5. 关键发现

1. **最重要的参数**: order_size_pct_min (相关性: -0.5369)
2. **盈利组与亏损组差异最大的参数**: base_exposure (差异: -1076.1523)
3. **盈利组合的平均特征**:
   - order_size_pct_min: 0.0300 (全部平均: 0.0544)
   - order_size_pct_max: 0.0900 (全部平均: 0.1048)
   - as_model_buy_distance: 1.0000 (全部平均: 1.0054)
   - as_model_sell_distance: 0.9000 (全部平均: 0.9994)
   - base_exposure: 10000.0000 (全部平均: 11074.0000)
   - base_target_pct: 0.6000 (全部平均: 0.4960)
