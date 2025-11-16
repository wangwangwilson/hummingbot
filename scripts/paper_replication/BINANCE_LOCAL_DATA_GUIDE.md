# Binance Public Data 本地数据使用指南

## 概述

本指南说明如何在任何项目中使用 `/Users/wilson/Desktop/tradingview-ai` 目录中存储的 Binance Public Data 本地zip数据，避免API限流问题。

## 数据位置

- **数据目录**: `/Users/wilson/Desktop/tradingview-ai/data/binance-public-data`
- **数据格式**: ZIP压缩的CSV文件
- **数据组织**:
  - 月度文件: `data/futures/um/monthly/klines/{SYMBOL}/1m/{SYMBOL}-1m-{YYYY}-{MM}.zip`
  - 日级别文件: `data/futures/um/daily/klines/{SYMBOL}/1m/{SYMBOL}-1m-{YYYY}-{MM}-{DD}.zip`

## 快速开始

### 1. 安装依赖

```bash
# 在您的项目虚拟环境中安装
pip install duckdb pandas
# 或使用uv
uv pip install duckdb pandas
```

**注意**: 如果只需要读取本地数据，**不需要安装ccxt**。如果需要下载/更新数据，才需要ccxt。

### 2. 导入数据管理器

```python
import sys
from pathlib import Path

# 添加 tradingview-ai 项目路径
tradingview_ai_path = Path("/Users/wilson/Desktop/tradingview-ai")
sys.path.insert(0, str(tradingview_ai_path))

# 如果只需要读取本地数据，可以临时禁用ccxt
import sys
class FakeCCXT:
    pass
sys.modules['ccxt'] = FakeCCXT()

# 导入数据管理器
from src.data.sources.binance_public_data_manager import BinancePublicDataManager
```

### 3. 使用示例

#### 示例1: 读取单个交易对数据

```python
from datetime import date

# 创建数据管理器
manager = BinancePublicDataManager()

# 读取BTCUSDT最近1天的数据
df = manager.get_klines_data(
    symbol='BTCUSDT',
    start_date=date(2024, 11, 11),
    end_date=date(2024, 11, 12),
    check_gaps=False  # 快速读取，不检查数据间隔
)

print(f"读取到 {len(df)} 条K线")
print(df.head())
```

#### 示例2: 并行读取多个交易对

```python
symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'XRPUSDT']
results = manager.get_multiple_symbols_data(
    symbols=symbols,
    start_date=date(2024, 11, 11),
    end_date=date(2024, 11, 12),
    max_workers=4,  # 并行数
    check_gaps=False
)

for symbol, df in results.items():
    print(f"{symbol}: {len(df)} 条K线")
```

#### 示例3: 数据格式转换（适配Hummingbot）

```python
import pandas as pd
from datetime import datetime

# 读取数据
df = manager.get_klines_data(
    symbol='BTCUSDT',
    start_date=date(2024, 11, 11),
    end_date=date(2024, 11, 12),
    check_gaps=False
)

# 确保timestamp是列（如果是索引，重置为列）
if df.index.name == 'timestamp' or isinstance(df.index, pd.DatetimeIndex):
    df = df.reset_index()
    if 'timestamp' not in df.columns:
        df['timestamp'] = df.index

# 转换为Unix时间戳（秒）- Hummingbot需要
df['timestamp'] = pd.to_datetime(df['timestamp']).astype('int64') // 10**9

# 数据格式: timestamp(秒), open, high, low, close, volume
print(df.head())
```

## 数据格式说明

### 返回的DataFrame格式

- **列名**: `['open', 'high', 'low', 'close', 'volume']`
- **索引**: `timestamp` (DatetimeIndex)
- **数据类型**:
  - `open`, `high`, `low`, `close`, `volume`: float64
  - `timestamp`: datetime64[ns]

### 转换为Hummingbot格式

Hummingbot的回测引擎需要：
- `timestamp`: Unix时间戳（秒，不是毫秒）
- `open`, `high`, `low`, `close`, `volume`: float64

转换代码：
```python
# 如果timestamp是索引
if isinstance(df.index, pd.DatetimeIndex):
    df = df.reset_index()
    df['timestamp'] = pd.to_datetime(df['timestamp']).astype('int64') // 10**9
else:
    # 如果timestamp是列
    df['timestamp'] = pd.to_datetime(df['timestamp']).astype('int64') // 10**9
```

## 在Hummingbot回测中使用

### 集成到回测脚本

可以创建一个自定义的数据提供器，使用本地数据替代API调用：

```python
from hummingbot.data_feed.candles_feed.candles_base import CandlesBase
from hummingbot.data_feed.candles_feed.data_types import HistoricalCandlesConfig
import pandas as pd
from datetime import date

class LocalBinanceDataProvider:
    """使用本地Binance数据的提供器"""
    
    def __init__(self):
        import sys
        from pathlib import Path
        
        tradingview_ai_path = Path("/Users/wilson/Desktop/tradingview-ai")
        sys.path.insert(0, str(tradingview_ai_path))
        
        # 临时禁用ccxt
        class FakeCCXT:
            pass
        sys.modules['ccxt'] = FakeCCXT()
        
        from src.data.sources.binance_public_data_manager import BinancePublicDataManager
        self.manager = BinancePublicDataManager()
    
    def get_historical_candles(self, symbol: str, start_ts: int, end_ts: int) -> pd.DataFrame:
        """
        获取历史K线数据
        
        Args:
            symbol: 交易对符号（如 'BTCUSDT'）
            start_ts: 开始时间戳（秒）
            end_ts: 结束时间戳（秒）
        
        Returns:
            DataFrame with columns: timestamp, open, high, low, close, volume
        """
        from datetime import datetime
        
        start_date = datetime.fromtimestamp(start_ts).date()
        end_date = datetime.fromtimestamp(end_ts).date()
        
        # 读取数据
        df = self.manager.get_klines_data(
            symbol=symbol.replace('-', ''),  # BTC-USDT -> BTCUSDT
            start_date=start_date,
            end_date=end_date,
            check_gaps=False
        )
        
        if df.empty:
            return pd.DataFrame(columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        
        # 确保timestamp是列
        if isinstance(df.index, pd.DatetimeIndex):
            df = df.reset_index()
        
        # 转换为Unix时间戳（秒）
        df['timestamp'] = pd.to_datetime(df['timestamp']).astype('int64') // 10**9
        
        # 过滤时间范围
        df = df[(df['timestamp'] >= start_ts) & (df['timestamp'] <= end_ts)]
        
        # 确保列顺序
        df = df[['timestamp', 'open', 'high', 'low', 'close', 'volume']]
        
        return df
```

## 优势

### 1. 避免API限流
- ✅ 完全本地读取，无API调用
- ✅ 无429错误
- ✅ 无请求频率限制

### 2. 性能优势
- ✅ 使用DuckDB zipfs扩展，直接读取zip文件
- ✅ 无需解压，节省磁盘空间
- ✅ 读取速度快

### 3. 数据完整性
- ✅ 数据已下载并验证
- ✅ 支持数据间隔检查（可选）
- ✅ 支持损坏文件检测和修复

## 注意事项

### 1. 交易对符号格式
- **本地数据**: `BTCUSDT` (无分隔符)
- **Hummingbot**: `BTC-USDT` (有分隔符)
- **转换**: `symbol.replace('-', '')` 或 `symbol.replace('USDT', 'USDT')`

### 2. 时间戳单位
- **本地数据返回**: datetime64 (索引或列)
- **Hummingbot需要**: Unix时间戳（秒）
- **转换**: `pd.to_datetime(df['timestamp']).astype('int64') // 10**9`

### 3. 数据范围
- 确保所需时间范围的数据已下载
- 检查数据目录中是否存在对应的zip文件
- 如果数据不存在，需要先下载

### 4. 依赖管理
- **必需**: `duckdb`, `pandas`
- **可选**: `ccxt` (仅用于下载/更新数据)
- 如果只需要读取，可以创建假的ccxt模块避免安装问题

## 测试脚本

参考 `test_binance_local_data.py` 进行测试：

```bash
cd /Users/wilson/Desktop/mm_research/hummingbot/scripts/paper_replication
source .venv/bin/activate
python3 test_binance_local_data.py
```

## 常见问题

### Q1: 导入失败 "No module named 'ccxt'"
**A**: 如果只需要读取本地数据，不需要ccxt。在导入前创建假的ccxt模块：
```python
import sys
class FakeCCXT:
    pass
sys.modules['ccxt'] = FakeCCXT()
```

### Q2: 数据读取返回空DataFrame
**A**: 检查：
1. 数据文件是否存在
2. 时间范围是否正确
3. 交易对符号格式是否正确（BTCUSDT vs BTC-USDT）

### Q3: timestamp列不存在
**A**: timestamp可能是索引，使用 `df.reset_index()` 转换为列。

### Q4: 如何检查数据是否存在？
**A**: 
```python
from pathlib import Path
data_dir = Path("/Users/wilson/Desktop/tradingview-ai/data/binance-public-data")
symbol = "BTCUSDT"
zip_file = data_dir / "data" / "futures" / "um" / "daily" / "klines" / symbol / "1m" / f"{symbol}-1m-2024-11-11.zip"
print(f"文件存在: {zip_file.exists()}")
```

## 总结

使用本地Binance Public Data可以：
- ✅ 完全避免API限流问题
- ✅ 提高回测速度
- ✅ 减少网络依赖
- ✅ 支持大规模并行回测

只需安装 `duckdb` 和 `pandas`，即可在任何项目中使用这些数据。

---

**文档版本**: 1.0  
**最后更新**: 2025-11-13  
**数据位置**: `/Users/wilson/Desktop/tradingview-ai/data/binance-public-data`

