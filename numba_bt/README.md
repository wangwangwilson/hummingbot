# Numba Backtesting Framework

基于 Numba 和 NumPy 的高性能回测框架，支持多交易所数据融合回测。

## 项目结构

```
numba_bt/
├── src/
│   ├── data/              # 数据模块
│   │   ├── preprocessor.py    # 数据预处理
│   │   └── preparer.py        # 数据准备（复用现有读取器）
│   ├── core/              # 核心回测引擎
│   │   └── backtest.py        # Numba加速的回测核心
│   ├── wrapper/           # 回测包装类
│   │   └── backtester.py     # 策略回测器
│   └── analysis/          # 结果分析
│       ├── statistics.py      # 统计分析
│       └── visualization.py   # 可视化
├── tests/                 # 测试文件
│   └── test_backtest.py
├── pyproject.toml         # 项目配置
└── README.md
```

## 功能特性

1. **高性能**: 使用 Numba JIT 编译加速核心回测循环
2. **多交易所支持**: 支持融合多个交易所的数据进行回测
3. **模块化设计**: 数据预处理、回测引擎、结果分析分离
4. **数据复用**: 复用现有的数据读取器，避免重复开发

## 安装

使用 UV 管理环境：

```bash
# 安装 UV（如果未安装）
curl -LsSf https://astral.sh/uv/install.sh | sh

# 进入项目目录
cd numba_bt

# 创建虚拟环境并安装依赖
uv venv
source .venv/bin/activate  # Linux/Mac
# 或 .venv\Scripts\activate  # Windows

# 安装项目依赖
uv pip install -e .
```

## 使用方法

### 基本使用

```python
from datetime import datetime, timedelta
from src.data.preparer import DataPreparer
from src.wrapper.backtester import MarketMakerBacktester
from src.analysis.statistics import analyze_performance

# 1. 准备数据
preparer = DataPreparer()
data = preparer.prepare_binance_aggtrades(
    symbol="BTCUSDT",
    trading_type="um",
    start_date=datetime(2024, 1, 1),
    end_date=datetime(2024, 1, 2),
    contract_size=1.0
)

# 2. 初始化回测器
backtester = MarketMakerBacktester(
    exposure=250e4,
    target_pct=0.5,
    initial_cash=100e4
)

# 3. 执行回测
backtester.run_backtest(data)

# 4. 分析结果
performance = analyze_performance(
    accounts_raw=backtester.accounts,
    place_orders_stats_raw=backtester.place_orders_stats
)

print(performance)
```

### 多交易所数据融合

```python
# 准备多个交易所的数据
data_sources = [
    {
        'type': 'binance',
        'symbol': 'BTCUSDT',
        'trading_type': 'um',
        'start_date': datetime(2024, 1, 1),
        'end_date': datetime(2024, 1, 2),
        'contract_size': 1.0,
        'exchange_flag': 0  # Binance标识
    },
    {
        'type': 'duckdb',
        'file_paths': ['/path/to/okx/data.parquet'],
        'start_ts': int(datetime(2024, 1, 1).timestamp() * 1000),
        'end_ts': int(datetime(2024, 1, 2).timestamp() * 1000),
        'contract_size': 1.0,
        'exchange_flag': 1  # OKX标识
    }
]

preparer = DataPreparer()
merged_data = preparer.prepare_multi_exchange(data_sources)

# 使用融合后的数据进行回测
backtester = MarketMakerBacktester()
backtester.run_backtest(merged_data)
```

## 运行测试

```bash
# 直接运行测试脚本
python tests/test_backtest.py

# 或使用 pytest
pytest tests/test_backtest.py -v
```

## 数据格式

回测数据格式为 numpy 数组，包含以下列：

- `timestamp`: 时间戳（毫秒）
- `order_side`: 方向 (1=buy, -1=sell)
- `price`: 成交价格
- `quantity`: 成交数量
- `mm_flag`: 交易所标识 (0=市场数据, 1=用户订单)

## 性能指标

回测结果包含以下性能指标：

- **总体绩效**: 总PnL、夏普比率、最大回撤、年化收益、卡玛比率
- **Maker绩效**: Maker交易PnL、交易量、手续费返佣
- **Taker绩效**: Taker交易PnL、交易量、手续费成本
- **订单行为**: 成交时间、成交率、滑点等

## 注意事项

1. 数据目录路径需要在 `bigdata_plan/src/const.py` 中配置
2. 首次运行需要编译 Numba 函数，可能需要一些时间
3. 建议使用较小的数据集进行初步测试

