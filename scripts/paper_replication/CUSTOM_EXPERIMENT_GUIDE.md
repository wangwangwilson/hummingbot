# 自定义交易对回测实验指南

## 📋 实验概述

本指南说明如何对以下交易对进行最近6个月的回测分析：
- **BTC-USDT**
- **SOL-USDT**
- **ETH-USDT**
- **XRP-USDT**
- **AVAX-USDT**
- **DOT-USDT**
- **MYX-USDT**

## 🚀 快速开始

### 前置要求

1. **已安装Hummingbot环境**
   ```bash
   cd /Users/wilson/Desktop/mm_research/hummingbot
   ./install  # 安装conda环境和依赖
   ```

2. **激活Hummingbot环境**
   ```bash
   conda activate hummingbot
   ```

### 方法1: 一键运行完整实验（推荐）

```bash
cd /Users/wilson/Desktop/mm_research/hummingbot/scripts/paper_replication

# 运行完整实验（数据下载 + 回测 + 可视化）
python3 run_custom_experiment.py
```

### 方法2: 分步执行

#### 步骤1: 下载数据

```bash
cd /Users/wilson/Desktop/mm_research/hummingbot/scripts/paper_replication
python3 download_candles_data.py custom
```

或使用别名：
```bash
python3 download_candles_data.py 6months
```

#### 步骤2: 运行回测

```bash
python3 backtest_comparison.py CUSTOM
```

或使用别名：
```bash
python3 backtest_comparison.py 6MONTHS
```

#### 步骤3: 分析结果

```bash
python3 analyze_results.py
```

## 📊 输出结果

### 数据文件
- 位置: `{项目根目录}/data/paper_replication/`
- 格式: CSV文件，包含1分钟K线数据（OHLCV）

### 回测结果
- 位置: `{项目根目录}/data/paper_replication/results/`
- 文件: `custom_comparison_summary_YYYYMMDD_HHMMSS.csv`
- 包含每个交易对的详细指标对比

### 可视化图表
- 位置: `{项目根目录}/data/paper_replication/figures/`
- 图表类型:
  - 累积收益曲线
  - 回撤分析
  - 交易P&L分布
  - 多交易对指标对比

### 分析报告
- 位置: `{项目根目录}/data/paper_replication/analysis/`
- 文件: `analysis_report_YYYYMMDD_HHMMSS.txt`
- 包含详细的统计分析

## 📈 分析指标

回测会计算以下指标：

### 收益指标
- **Total Return (%)**: 总收益率
- **Average Return**: 平均收益

### 风险指标
- **Sharpe Ratio**: 夏普比率（风险调整后收益）
- **Maximum Drawdown (%)**: 最大回撤

### 交易指标
- **Total Trades**: 总交易次数
- **Win Rate (%)**: 胜率
- **Average Trade P&L**: 平均交易盈亏

### 综合评分
- 综合得分 = 收益×0.5 + Sharpe×0.3 - 回撤×0.2

## 🔧 自定义配置

### 修改交易对

编辑 `download_candles_data.py`:
```python
CUSTOM_TEST_PAIRS = ["BTC-USDT", "SOL-USDT", "ETH-USDT", ...]
```

### 修改时间范围

编辑 `download_candles_data.py` 中的 `get_last_6_months_range()`:
```python
def get_last_6_months_range():
    end_date = datetime.now()
    start_date = end_date - timedelta(days=180)  # 修改天数
    return start_date, end_date
```

### 修改策略参数

编辑 `backtest_comparison.py` 中的策略配置:
```python
# Bar Portion策略
bp_config = backtester.create_bp_config(
    spreads=[0.01, 0.02],       # Spread列表
    stop_loss=0.03,              # 止损 3%
    take_profit=0.02,            # 止盈 2%
    time_limit_minutes=45        # 时间限制 45分钟
)
```

## ⚠️ 注意事项

1. **MYX-USDT**: 如果该交易对在Binance不存在，下载会失败，但其他交易对会继续下载

2. **数据下载时间**: 下载7个交易对最近6个月的数据可能需要10-30分钟，取决于网络速度

3. **回测时间**: 每个交易对的回测可能需要5-15分钟，总共约1-2小时

4. **存储空间**: 6个月1分钟K线数据约需要500MB-1GB存储空间

## 🐛 故障排除

### 问题1: 模块导入错误

```bash
# 确保在项目根目录，并设置PYTHONPATH
export PYTHONPATH=/Users/wilson/Desktop/mm_research/hummingbot:$PYTHONPATH
```

### 问题2: 数据下载失败

- 检查网络连接
- 确认交易对名称正确（例如MYX-USDT可能不存在）
- 查看错误日志

### 问题3: 回测失败

- 确保数据已成功下载
- 检查数据文件是否完整
- 查看回测日志

## 📚 相关文档

- **README.md**: 项目完整说明
- **QUICKSTART.md**: 快速开始指南
- **UV_QUICKSTART.md**: UV环境快速开始
- **IMPLEMENTATION_SUMMARY.md**: 实现细节

## 🎯 实验流程总结

```
1. 环境准备
   └─> conda activate hummingbot

2. 下载数据
   └─> python3 download_candles_data.py custom

3. 运行回测
   └─> python3 backtest_comparison.py CUSTOM

4. 分析结果
   └─> python3 analyze_results.py

5. 查看结果
   └─> 查看 data/paper_replication/ 目录
```

## 💡 提示

- 使用 `python3 download_candles_data.py summary` 查看已下载数据摘要
- 使用 `python3 analyze_results.py` 可以多次运行，会自动加载最新的结果文件
- 所有结果文件都包含时间戳，方便对比不同时间的回测结果

---

**祝实验顺利！** 🚀📈

