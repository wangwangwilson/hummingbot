# 回测系统使用说明文档

本文档详细说明如何配置和运行回测系统，包括环境配置、参数设置、数据路径配置等。

---

## 目录

1. [UV环境配置与激活](#1-uv环境配置与激活)
2. [回测脚本运行指南](#2-回测脚本运行指南)
3. [本地数据路径配置](#3-本地数据路径配置)
4. [回测报告路径配置](#4-回测报告路径配置)
5. [常见问题与故障排除](#5-常见问题与故障排除)

---

## 1. UV环境配置与激活

### 1.1 安装UV（如果尚未安装）

```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# 或使用Homebrew (macOS)
brew install uv

# 验证安装
uv --version
```

### 1.2 创建虚拟环境

```bash
cd /Users/wilson/Desktop/mm_research/hummingbot/scripts/paper_replication

# 使用UV创建虚拟环境（推荐使用Python 3.10+）
uv venv --python 3.10

# 或使用系统Python
uv venv
```

### 1.3 激活虚拟环境

```bash
# 激活虚拟环境
source .venv/bin/activate

# 验证激活成功（命令提示符前应显示(.venv)）
which python
# 应显示: /Users/wilson/Desktop/mm_research/hummingbot/scripts/paper_replication/.venv/bin/python
```

### 1.4 安装依赖包

```bash
# 激活环境后，安装必要的依赖
source .venv/bin/activate

# 安装核心依赖
uv pip install pandas numpy matplotlib joblib duckdb pandas-ta pydantic

# 如果需要安装项目依赖
export PYTHONPATH=/Users/wilson/Desktop/mm_research/hummingbot:$PYTHONPATH
```

### 1.5 设置PYTHONPATH

```bash
# 每次激活环境后，需要设置PYTHONPATH以导入hummingbot模块
export PYTHONPATH=/Users/wilson/Desktop/mm_research/hummingbot:$PYTHONPATH

# 或添加到激活脚本中（推荐）
echo 'export PYTHONPATH=/Users/wilson/Desktop/mm_research/hummingbot:$PYTHONPATH' >> .venv/bin/activate
```

### 1.6 验证环境配置

```bash
source .venv/bin/activate
export PYTHONPATH=/Users/wilson/Desktop/mm_research/hummingbot:$PYTHONPATH

# 测试导入
python3 -c "
import pandas as pd
import numpy as np
from hummingbot.strategy_v2.backtesting.backtesting_engine_base import BacktestingEngineBase
print('✓ 环境配置成功！')
"
```

---

## 2. 回测脚本运行指南

### 2.1 脚本位置

回测主脚本：`backtest_with_plots_and_structure.py`

### 2.2 基本运行命令

```bash
# 1. 进入目录
cd /Users/wilson/Desktop/mm_research/hummingbot/scripts/paper_replication

# 2. 激活环境
source .venv/bin/activate

# 3. 设置PYTHONPATH
export PYTHONPATH=/Users/wilson/Desktop/mm_research/hummingbot:$PYTHONPATH

# 4. 运行回测（前台运行）
python3 backtest_with_plots_and_structure.py

# 5. 运行回测（后台运行，推荐）
nohup python3 backtest_with_plots_and_structure.py > backtest.log 2>&1 &
```

### 2.3 配置运行参数

编辑 `backtest_with_plots_and_structure.py` 文件，修改以下参数：

```python
# ========== 回测参数配置 ==========

# 交易对列表
TRADING_PAIRS = ["BTC-USDT", "ETH-USDT", "PUMP-USDT"]

# 回测时间范围
START_DATE = datetime(2025, 9, 1)    # 开始日期
END_DATE = datetime(2025, 9, 21)     # 结束日期

# 初始资金
INITIAL_PORTFOLIO_USD = 10000

# 手续费设置
MAKER_FEE = 0.0      # Maker手续费：0（免手续费）
TAKER_FEE = 0.0002   # Taker手续费：万2（0.02%）

# K线数据配置
BACKTEST_RESOLUTION = "1m"              # 基础数据：1分钟
RESAMPLE_INTERVAL: Optional[str] = None # 重采样间隔（None表示不重采样）
PLOT_FREQUENCY = "3min"                 # 画图频率：3分钟

# 并行处理配置
USE_MULTIPROCESSING = True  # 使用joblib多进程并行
N_JOBS = -1                 # -1表示使用所有CPU核心

# 输出环境
ENVIRONMENT = "prod"  # "prod" 或 "test"
```

### 2.4 策略配置

脚本支持以下策略：

1. **PMM Simple** - 经典做市策略
2. **PMM Dynamic (MACD)** - MACD动态做市策略
3. **PMM Bar Portion** - Bar Portion做市策略
4. **PMM Simple (Future Data)** - 使用未来数据的理想基准
5. **PMM Dynamic (MACD) Future Data** - MACD未来数据版本
6. **PMM Bar Portion (Future Data)** - BP未来数据版本

策略配置在脚本的 `strategies` 字典中：

```python
strategies = {
    "PMM_Simple": {
        "name": "PMM Simple",
        "config_class": PMMSimpleConfig,
        "params": {
            "buy_spreads": [0.005, 0.01],
            "sell_spreads": [0.005, 0.01],
            "buy_amounts_pct": [Decimal("0.5"), Decimal("0.5")],
            "sell_amounts_pct": [Decimal("0.5"), Decimal("0.5")],
            "executor_refresh_time": 300,
        }
    },
    # ... 其他策略配置
}
```

### 2.5 运行示例

#### 示例1：快速测试（5天数据，单个交易对）

```python
# 修改 backtest_with_plots_and_structure.py
TRADING_PAIRS = ["PUMP-USDT"]
START_DATE = datetime(2025, 10, 25)
END_DATE = datetime(2025, 10, 30)
ENVIRONMENT = "test"
```

#### 示例2：完整回测（多交易对，长时间范围）

```python
# 修改 backtest_with_plots_and_structure.py
TRADING_PAIRS = ["BTC-USDT", "ETH-USDT", "SOL-USDT", "XRP-USDT"]
START_DATE = datetime(2025, 1, 1)
END_DATE = datetime(2025, 11, 9)
ENVIRONMENT = "prod"
RESAMPLE_INTERVAL = "15m"  # 使用15分钟K线加速回测
```

#### 示例3：后台运行并查看日志

```bash
# 启动后台回测
nohup python3 backtest_with_plots_and_structure.py > prod_backtest.log 2>&1 &

# 查看实时日志
tail -f prod_backtest.log

# 查看最新进度
tail -50 prod_backtest.log | grep -E "(Done|elapsed|remaining|Step)"
```

---

## 3. 本地数据路径配置

### 3.1 数据源说明

回测系统使用本地Binance Public Data（zip文件格式），通过DuckDB读取。

### 3.2 配置数据路径

在 `backtest_comparison_local.py` 或相关数据提供者文件中，配置本地数据路径：

```python
# 默认数据路径
tradingview_ai_path = Path("/Users/wilson/Desktop/tradingview-ai")
sys.path.insert(0, str(tradingview_ai_path))

# 数据目录结构
# /Users/wilson/Desktop/tradingview-ai/
#   └── binance_public_data/
#       ├── data/
#       │   ├── spot/
#       │   │   └── monthly/
#       │   │       └── um/
#       │   │           └── USDT/
#       │   │               ├── BTCUSDT-1m-2025-01.zip
#       │   │               ├── BTCUSDT-1m-2025-02.zip
#       │   │               └── ...
#       │   └── futures/
#       │       └── monthly/
#       │           └── um/
#       │               └── USDT/
#       │                   ├── BTCUSDT-1m-2025-01.zip
#       │                   └── ...
```

### 3.3 修改数据路径

如果需要使用不同的数据路径，修改以下文件：

**文件1：`backtest_comparison_local.py`**

```python
# 找到以下代码
tradingview_ai_path = Path("/Users/wilson/Desktop/tradingview-ai")
sys.path.insert(0, str(tradingview_ai_path))

# 修改为你的数据路径
tradingview_ai_path = Path("/your/custom/data/path")
sys.path.insert(0, str(tradingview_ai_path))
```

**文件2：`backtest_with_plots_and_structure.py`**

```python
# 找到以下代码
tradingview_ai_path = Path("/Users/wilson/Desktop/tradingview-ai")
sys.path.insert(0, str(tradingview_ai_path))

# 修改为你的数据路径
tradingview_ai_path = Path("/your/custom/data/path")
sys.path.insert(0, str(tradingview_ai_path))
```

### 3.4 数据格式要求

- **文件格式**：ZIP压缩文件
- **文件命名**：`{SYMBOL}-{INTERVAL}-{YYYY-MM}.zip`
  - 例如：`BTCUSDT-1m-2025-01.zip`
- **数据内容**：CSV格式，包含以下列：
  - `timestamp` (Unix时间戳，毫秒)
  - `open`, `high`, `low`, `close` (价格)
  - `volume` (成交量)

### 3.5 验证数据路径

```bash
# 检查数据目录是否存在
ls -la /Users/wilson/Desktop/tradingview-ai/binance_public_data/data/

# 检查特定交易对的数据文件
ls -la /Users/wilson/Desktop/tradingview-ai/binance_public_data/data/spot/monthly/um/USDT/ | grep BTCUSDT

# 测试数据读取
python3 -c "
from pathlib import Path
import sys
sys.path.insert(0, '/Users/wilson/Desktop/tradingview-ai')
from src.data.sources.binance_public_data_manager import BinancePublicDataManager

manager = BinancePublicDataManager()
df = manager.get_klines_data('BTCUSDT', '2025-01-01', '2025-01-02')
print(f'✓ 数据读取成功: {len(df)} 条记录')
"
```

---

## 4. 回测报告路径配置

### 4.1 默认输出路径

回测结果默认保存在：

```
scripts/paper_replication/backtest_results/
├── prod/                    # 生产环境结果
│   └── 2025_11_14_18_10/   # 时间戳目录
│       ├── BTC_USDT/
│       │   ├── BTC_USDT_prod.json
│       │   ├── BTC_USDT_prod_PMM_Simple_plots.png
│       │   ├── BTC_USDT_prod_PMM_Simple_data.csv
│       │   ├── BTC_USDT_prod_PMM_Dynamic_MACD_plots.png
│       │   └── ...
│       └── ETH_USDT/
│           └── ...
└── test/                    # 测试环境结果
    └── 2025_11_14_19_45/
        └── ...
```

### 4.2 目录结构说明

- **环境目录**：`prod/` 或 `test/`（由 `ENVIRONMENT` 参数控制）
- **时间戳目录**：格式为 `YYYY_MM_DD_HH_MM`（自动生成）
- **交易对目录**：交易对名称，格式为 `{SYMBOL}_{QUOTE}`（如 `BTC_USDT`）
- **结果文件**：
  - `{SYMBOL}_{ENV}.json` - JSON格式的完整回测结果
  - `{SYMBOL}_{ENV}_{STRATEGY}_plots.png` - 策略图表
  - `{SYMBOL}_{ENV}_{STRATEGY}_data.csv` - 策略数据（equity curve）

### 4.3 修改输出路径

在 `backtest_with_plots_and_structure.py` 中修改：

```python
def create_output_directory(environment: str = "test") -> Path:
    """
    创建输出目录结构
    """
    # 默认路径
    base_dir = Path(__file__).parent / "backtest_results"
    
    # 修改为自定义路径
    # base_dir = Path("/your/custom/output/path")
    
    env_dir = base_dir / environment
    
    # 创建时间戳目录
    now = datetime.now()
    timestamp_dir = env_dir / now.strftime("%Y_%m_%d_%H_%M")
    timestamp_dir.mkdir(parents=True, exist_ok=True)
    
    return timestamp_dir
```

### 4.4 输出文件说明

#### JSON结果文件

包含完整的回测指标：

```json
{
  "start_date": "2025-09-01",
  "end_date": "2025-09-21",
  "trading_pair": "BTC-USDT",
  "backtest_resolution": "1m",
  "environment": "prod",
  "trading_fees": {
    "maker_fee": 0.0,
    "taker_fee": 0.0002,
    "maker_fee_pct": 0.0,
    "taker_fee_pct": 0.02
  },
  "data_info": {
    "trading_pair": "BTC-USDT",
    "data_points": 28800,
    "actual_start": "2025-09-01 08:00:00",
    "actual_end": "2025-09-21 00:00:00"
  },
  "results": [
    {
      "strategy_name": "PMM Simple",
      "total_executors": 1000,
      "filled_executors": 150,
      "fill_rate": 0.15,
      "total_pnl": 1234.56,
      "total_volume": 100000.0,
      "daily_pnl": 61.73,
      "daily_return": 6.17,
      "max_long_position_value": 5000.0,
      "max_short_position_value": 5000.0,
      ...
    }
  ]
}
```

#### PNG图表文件

包含5个子图：
1. **Position Value Over Time** - 仓位价值曲线（正=多仓，负=空仓）
2. **Cumulative PnL Over Time** - 累积盈亏曲线
3. **Order Prices Over Time** - 挂单价格曲线
4. **Position Value Distribution** - 仓位价值分布直方图
5. **Volatility vs. Turnover Return** - 波动率vs收益率柱状图

#### CSV数据文件

包含equity curve数据：
- `timestamp` - 时间戳
- `position_value` - 仓位价值（正=多仓，负=空仓）
- `cumulative_pnl` - 累积盈亏
- `buy_order_price`, `sell_order_price` - 买卖挂单价格
- `volatility`, `turnover_return` - 波动率和收益率

---

## 5. 常见问题与故障排除

### 5.1 环境相关问题

#### 问题：`ModuleNotFoundError: No module named 'hummingbot'`

**解决方案：**

```bash
# 确保设置了PYTHONPATH
export PYTHONPATH=/Users/wilson/Desktop/mm_research/hummingbot:$PYTHONPATH

# 验证路径
echo $PYTHONPATH

# 测试导入
python3 -c "import hummingbot; print('OK')"
```

#### 问题：`ModuleNotFoundError: No module named 'duckdb'`

**解决方案：**

```bash
source .venv/bin/activate
uv pip install duckdb
```

#### 问题：虚拟环境激活失败

**解决方案：**

```bash
# 重新创建虚拟环境
rm -rf .venv
uv venv
source .venv/bin/activate
```

### 5.2 数据相关问题

#### 问题：`IO Error: Could not open as zip file`

**原因：** ZIP文件损坏或不存在

**解决方案：**

```bash
# 检查文件是否存在
ls -lh /Users/wilson/Desktop/tradingview-ai/binance_public_data/data/spot/monthly/um/USDT/BTCUSDT-1m-2025-01.zip

# 检查文件大小（损坏的文件通常只有4KB）
# 如果文件损坏，需要重新下载
```

#### 问题：数据加载失败，显示"未找到数据文件"

**原因：** 数据路径配置错误或数据文件不存在

**解决方案：**

```bash
# 1. 检查数据路径配置
grep -r "tradingview-ai" backtest_comparison_local.py

# 2. 验证数据目录结构
ls -la /Users/wilson/Desktop/tradingview-ai/binance_public_data/data/spot/monthly/um/USDT/

# 3. 检查特定交易对的数据
ls -la /Users/wilson/Desktop/tradingview-ai/binance_public_data/data/spot/monthly/um/USDT/ | grep BTCUSDT
```

### 5.3 回测运行问题

#### 问题：回测进程卡住或运行很慢

**解决方案：**

```bash
# 1. 检查CPU使用率
top -p $(pgrep -f backtest_with_plots_and_structure.py)

# 2. 检查并行配置
# 如果CPU核心数较少，减少N_JOBS
# 在脚本中修改：N_JOBS = 4  # 使用4个核心

# 3. 使用重采样加速
# 在脚本中修改：RESAMPLE_INTERVAL = "15m"  # 使用15分钟K线
```

#### 问题：`pydantic_core._pydantic_core.ValidationError`

**原因：** 策略配置参数类型错误

**解决方案：**

```python
# 确保Decimal类型正确
from decimal import Decimal

# 错误示例
"buy_amounts_pct": [0.5, 0.5]  # ❌

# 正确示例
"buy_amounts_pct": [Decimal("0.5"), Decimal("0.5")]  # ✓
```

#### 问题：回测结果中PnL为0或异常

**解决方案：**

```bash
# 1. 检查数据完整性
# 确保数据时间范围覆盖回测区间

# 2. 检查策略参数
# 确保spread设置合理（不要太大导致无法成交）

# 3. 检查日志
tail -100 backtest.log | grep -E "(Error|Warning|失败)"
```

### 5.4 输出路径问题

#### 问题：无法创建输出目录

**解决方案：**

```bash
# 检查目录权限
ls -ld backtest_results/

# 手动创建目录
mkdir -p backtest_results/prod
mkdir -p backtest_results/test

# 检查磁盘空间
df -h .
```

---

## 6. 快速参考命令

### 6.1 完整运行流程

```bash
# 1. 进入目录
cd /Users/wilson/Desktop/mm_research/hummingbot/scripts/paper_replication

# 2. 激活环境
source .venv/bin/activate

# 3. 设置PYTHONPATH
export PYTHONPATH=/Users/wilson/Desktop/mm_research/hummingbot:$PYTHONPATH

# 4. 编辑配置（可选）
# 编辑 backtest_with_plots_and_structure.py 中的参数

# 5. 运行回测
nohup python3 backtest_with_plots_and_structure.py > backtest.log 2>&1 &

# 6. 查看进度
tail -f backtest.log

# 7. 查看结果
ls -lth backtest_results/prod/*/
```

### 6.2 常用检查命令

```bash
# 检查回测进程
ps aux | grep backtest_with_plots_and_structure.py

# 查看最新日志
tail -50 backtest.log

# 查看已完成的结果
find backtest_results -name "*.json" -type f | sort

# 检查数据文件
ls -lh /Users/wilson/Desktop/tradingview-ai/binance_public_data/data/spot/monthly/um/USDT/ | head -20
```

---

## 7. 配置示例

### 7.1 测试环境配置（快速验证）

```python
# backtest_with_plots_and_structure.py

TRADING_PAIRS = ["PUMP-USDT"]
START_DATE = datetime(2025, 10, 25)
END_DATE = datetime(2025, 10, 30)
BACKTEST_RESOLUTION = "1m"
RESAMPLE_INTERVAL = "15m"  # 加速回测
ENVIRONMENT = "test"
N_JOBS = 4  # 限制并行数
```

### 7.2 生产环境配置（完整回测）

```python
# backtest_with_plots_and_structure.py

TRADING_PAIRS = ["BTC-USDT", "ETH-USDT", "SOL-USDT", "XRP-USDT", "PUMP-USDT"]
START_DATE = datetime(2025, 1, 1)
END_DATE = datetime(2025, 11, 9)
BACKTEST_RESOLUTION = "1m"
RESAMPLE_INTERVAL = "15m"  # 使用15分钟K线
ENVIRONMENT = "prod"
N_JOBS = -1  # 使用所有CPU核心
```

### 7.3 未来数据基准测试配置

```python
# 包含未来数据策略的完整对比
TRADING_PAIRS = ["BTC-USDT", "ETH-USDT", "PUMP-USDT"]
START_DATE = datetime(2025, 9, 1)
END_DATE = datetime(2025, 9, 21)
BACKTEST_RESOLUTION = "1m"
RESAMPLE_INTERVAL = None  # 使用1分钟原始数据
ENVIRONMENT = "prod"
```

---

## 8. 联系与支持

如有问题或需要帮助，请：

1. 查看日志文件：`backtest.log`
2. 检查错误信息：`tail -100 backtest.log | grep -i error`
3. 验证数据路径和文件权限
4. 确认环境配置正确

---

**文档版本：** 1.0  
**最后更新：** 2025-11-14  
**维护者：** Hummingbot Development Team

