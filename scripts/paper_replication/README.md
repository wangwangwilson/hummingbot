# 论文复现：Market Making in Crypto

本目录包含复现论文 **"Market Making in Crypto" by Stoikov et al. (2024)** 的完整代码实现。

## 📄 论文概述

**核心策略：**
- **PMM Bar Portion (BP)**: 使用Bar Portion alpha信号的做市策略
  - Bar Portion = (Close - Open) / (High - Low)
  - 范围：-1到1，捕捉均值回归行为
  - 使用滚动线性回归预测价格变化

- **PMM Dynamic (MACD基准)**: 使用MACD指标的动态做市策略
  - MACD指标调整中间价
  - NATR动态调整spread

**风险管理：**
- 三重屏障策略（Triple Barrier Strategy）
  - 止损（Stop Loss）
  - 止盈（Take Profit）
  - 时间限制（Time Limit）

**测试数据：**
- 30个加密货币永续合约
- 1分钟K线数据
- 时间范围：2024年9月1日至10月14日（45天）
- 重点测试对：SOL-USDT, DOGE-USDT, GALA-USDT

## 📁 文件结构

```
paper_replication/
├── README.md                      # 本文件
├── download_candles_data.py       # 数据下载脚本
├── backtest_comparison.py         # 回测对比脚本
├── visualize_results.py           # 结果可视化脚本
└── run_full_experiment.py         # 完整实验运行脚本
```

## 🚀 快速开始

### 1. 环境准备

确保已安装Hummingbot及其依赖：

```bash
cd /workspace
pip install -r setup/pip_packages.txt
```

### 2. 下载数据

下载论文测试交易对的数据：

```bash
python scripts/paper_replication/download_candles_data.py test
```

下载所有30个交易对的数据：

```bash
python scripts/paper_replication/download_candles_data.py all
```

按类别下载：

```bash
# Layer-1协议
python scripts/paper_replication/download_candles_data.py layer1

# Meme币
python scripts/paper_replication/download_candles_data.py meme

# DeFi代币
python scripts/paper_replication/download_candles_data.py defi

# 实用代币
python scripts/paper_replication/download_candles_data.py utility
```

查看已下载数据摘要：

```bash
python scripts/paper_replication/download_candles_data.py summary
```

### 3. 运行回测

对单个交易对进行回测：

```bash
python scripts/paper_replication/backtest_comparison.py SOL-USDT
```

对所有测试交易对进行完整回测：

```bash
python scripts/paper_replication/backtest_comparison.py ALL
```

### 4. 生成完整实验报告

运行完整实验（下载数据 + 回测 + 可视化）：

```bash
python scripts/paper_replication/run_full_experiment.py
```

## 📊 输出结果

### 数据文件
- 位置：`/workspace/data/paper_replication/`
- 格式：CSV文件，包含OHLCV数据

### 回测结果
- 位置：`/workspace/data/paper_replication/results/`
- 文件：
  - `comparison_summary_YYYYMMDD_HHMMSS.csv` - 策略对比汇总
  - 包含每个交易对的详细指标

### 可视化图表
- 位置：`/workspace/data/paper_replication/figures/`
- 图表类型：
  - 累积收益曲线（Cumulative Returns）
  - 回撤曲线（Drawdown）
  - 交易P&L分布（Trade Distribution）
  - 多交易对指标对比（Metrics Comparison）

## 📈 性能指标

回测计算以下指标：

1. **收益指标**
   - Total Return ($)：总收益（美元）
   - Total Return (%)：总收益率（百分比）

2. **风险指标**
   - Sharpe Ratio：夏普比率
   - Maximum Drawdown ($)：最大回撤（美元）
   - Maximum Drawdown (%)：最大回撤（百分比）

3. **交易指标**
   - Total Trades：总交易次数
   - Win Rate (%)：胜率
   - Average Trade P&L：平均交易盈亏

## 🔧 自定义配置

### 修改策略参数

编辑 `backtest_comparison.py` 中的配置：

```python
# Bar Portion策略参数
bp_config = backtester.create_bp_config(
    spreads=[0.01, 0.02],       # Spread列表
    stop_loss=0.03,              # 止损 3%
    take_profit=0.02,            # 止盈 2%
    time_limit_minutes=45        # 时间限制 45分钟
)

# MACD策略参数
macd_config = backtester.create_macd_config(
    spreads=[1.0, 2.0, 4.0],    # Spread倍数
    stop_loss=0.03,
    take_profit=0.02,
    time_limit_minutes=45,
    macd_fast=21,                # MACD快线
    macd_slow=42,                # MACD慢线
    macd_signal=9                # MACD信号线
)
```

### 修改数据时间范围

编辑 `download_candles_data.py`：

```python
START_DATE = datetime(2024, 9, 1)
END_DATE = datetime(2024, 10, 14)
```

### 修改初始资金

编辑 `backtest_comparison.py`：

```python
INITIAL_PORTFOLIO_USD = 1000  # 初始资金
```

## 🎯 论文关键发现

根据论文，Bar Portion策略相比MACD基准表现更优：

**实时交易24小时结果（论文数据）：**

| 交易对 | BP Return | MACD Return | BP Sharpe | MACD Sharpe |
|--------|-----------|-------------|-----------|-------------|
| SOL-USDT | 0.26% | -0.32% | - | - |
| DOGE-USDT | 0.249% | 0.244% | - | - |
| GALA-USDT | - | - | - | - |

**回测结果（论文数据，9天）：**
- BP累积收益：45.84%
- MACD累积收益：-0.59%
- BP最大回撤：3.94%
- MACD最大回撤：8.71%
- BP夏普比率：0.78
- MACD夏普比率：-0.01

## 📚 参考文献

Stoikov, S., Zhuang, E., Chen, H., Zhang, Q., Wang, S., Li, S., & Shan, C. (2024). 
*Market Making in Crypto*. Cornell Financial Engineering Manhattan.

## 🤝 贡献

本实现基于Hummingbot开源框架，策略控制器位于：
- `/workspace/controllers/market_making/pmm_bar_portion.py` - Bar Portion策略
- `/workspace/controllers/market_making/pmm_dynamic.py` - MACD基准策略

## ⚠️ 免责声明

本代码仅用于学术研究和教育目的。实际交易存在风险，历史回测结果不代表未来表现。
使用前请充分理解策略逻辑，并进行充分的测试。

## 📧 联系方式

如有问题或建议，请提交Issue或Pull Request。
