# 半年回测运行状态

## 回测配置

- **时间范围**: 2025-01-01 至 2025-11-12（约10.5个月）
- **交易对**: BTC-USDT, SOL-USDT, ETH-USDT, XRP-USDT, AVAX-USDT, DOT-USDT, MYX-USDT
- **初始资金**: $1000
- **交易费用**: 0.04%
- **策略**: 
  - PMM Bar Portion（论文策略）
  - PMM Dynamic (MACD)（基准策略）

## 运行状态

回测正在后台运行中...

检查进度：
```bash
tail -f backtest_output.log
```

或检查进程：
```bash
ps aux | grep backtest_comparison
```

## 输出文件

回测完成后，结果将保存在：
- `data/paper_replication/results/custom_comparison_summary_*.csv` - 汇总结果
- `data/paper_replication/results/backtest_report_*.txt` - 详细报告

## 预计时间

由于需要获取7个交易对、10.5个月的数据，预计需要：
- 数据获取：每个交易对约2-5分钟
- 回测计算：每个交易对约5-10分钟
- 总计：约1-2小时

