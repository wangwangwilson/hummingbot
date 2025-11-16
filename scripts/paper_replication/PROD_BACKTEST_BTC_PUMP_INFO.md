# 正式环境回测任务信息（BTC和PUMP）

## 回测参数
- **环境**: prod（正式环境）
- **交易对**: BTC-USDT, PUMP-USDT（2个品种）
- **时间范围**: 2025-01-01 到 2025-11-09
- **基础数据分辨率**: 1分钟
- **回测分辨率**: 15分钟
- **画图频率**: 3分钟
- **并行处理**: 是（使用所有CPU核心）

## 手续费配置
- **Maker手续费**: 0（免手续费）
- **Taker手续费**: 万2（0.02%，即0.0002）
- **说明**: 
  - `maker_fee_pct`: 百分比形式（0%）
  - `taker_fee_pct`: 百分比形式（0.02%）
  - `maker_fee_wan`: 万分之几形式（0）
  - `taker_fee_wan`: 万分之几形式（2）

## 策略
1. PMM Simple
2. PMM Dynamic (MACD)
3. PMM Bar Portion

## 新增指标
- **daily_pnl**: 日均盈亏（美元）
- **daily_return**: 日均收益率，采用"万{ratio}"格式（万分之几）
  - 计算公式：`daily_return = (daily_pnl / daily_volume * 10000)`
  - 例如：`daily_return = 0.5` 表示万0.5（即0.05%）

## 输出目录
`backtest_results/prod/时间戳/品种/`

## 监控命令
```bash
# 查看日志
tail -f prod_backtest_btc_pump_20250101_20251109.log

# 查看进程
ps aux | grep backtest_with_plots_and_structure.py

# 查看输出目录
ls -lh backtest_results/prod/
```

## 预计时间
- 2个品种 × 3个策略 = 6个回测任务
- BTC: 约10个月数据（29,921个15分钟K线）
- PUMP: 约6.5个月数据（19,400个15分钟K线，从2025-04-12开始）
- 预计总时间：根据数据量和CPU性能，可能需要数分钟到数十分钟

## 任务状态
- 启动时间: 2025-11-14 18:18
- 状态: 运行中

## 数据说明
- **BTC-USDT**: 完整数据（2025-01-01 到 2025-11-09）
- **PUMP-USDT**: 部分数据（2025-04-12 到 2025-11-01），11月份部分zip文件损坏但已从月度文件加载

