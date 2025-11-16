# 正式环境批量回测任务信息

## 回测参数
- **环境**: prod（正式环境）
- **交易对**: ASTER-USDT, BTC-USDT, ETH-USDT, PUMP-USDT, SOL-USDT, XRP-USDT
- **时间范围**: 2025-01-01 到 2025-11-09
- **基础数据分辨率**: 1分钟
- **回测分辨率**: 15分钟
- **画图频率**: 3分钟
- **并行处理**: 是（使用所有CPU核心）

## 策略
1. PMM Simple
2. PMM Dynamic (MACD)
3. PMM Bar Portion

## 输出目录
`backtest_results/prod/时间戳/品种/`

## 监控命令
```bash
# 查看日志
tail -f prod_backtest_20250101_20251109.log

# 查看进程
ps aux | grep backtest_with_plots_and_structure.py

# 查看输出目录
ls -lh backtest_results/prod/
```

## 预计时间
- 6个品种 × 3个策略 = 18个回测任务
- 每个品种约10个月数据（1分钟数据采样到15分钟）
- 预计总时间：根据数据量和CPU性能，可能需要数小时

## 任务状态
- 启动时间: 2025-11-14
- 状态: 运行中

