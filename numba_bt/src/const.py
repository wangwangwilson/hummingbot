"""项目常量配置"""
from pathlib import Path

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent

# 实验结果存储目录
RESULTS_ROOT = PROJECT_ROOT / "results"
RESULTS_PROD = RESULTS_ROOT / "prod"  # 正式回测结果
RESULTS_TEST = RESULTS_ROOT / "test"  # 测试结果

# 输出目录（临时输出，如图表等）
OUTPUT_DIR = PROJECT_ROOT / "output"

# mm_flag 设计规则（硬编码）
MM_FLAG_BLOFIN_TRADES = 0      # blofin trades (真实成交，Taker Trade)
MM_FLAG_BINANCE_TRADES = 1     # binance trades (市场数据)
MM_FLAG_OKX_TRADES = 2         # okx trades (市场数据)
MM_FLAG_BYBIT_TRADES = 3        # bybit trades (市场数据)
MM_FLAG_BINANCE_ORDERBOOK = -1  # binance orderbook (市场数据)
MM_FLAG_FUNDING_RATE = -2       # funding_rate (市场数据)

# 数据路径（如果需要）
DATA_ROOT = Path("/mnt/hdd")
BINANCE_DATA_DIR = DATA_ROOT / "binance-public-data" / "data" / "futures" / "um" / "daily" / "aggTrades"
OKX_DATA_DIR = DATA_ROOT / "okx-public-data" / "aggtrades" / "monthly"
BYBIT_DATA_DIR = DATA_ROOT / "bybit-public-data" / "aggtrades"

