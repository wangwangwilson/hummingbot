"""
回测对比脚本 - 使用本地Binance Public Data

对比PMM Bar Portion策略与PMM Dynamic (MACD)基准策略
使用本地zip数据替代API调用，避免限流问题
"""

import asyncio
import os
import sys
from datetime import datetime, timedelta, date
from decimal import Decimal
from pathlib import Path
from typing import Dict, List

import pandas as pd
import numpy as np

# 配置SSL证书（支持zerotrust VPN）
cert_file = Path.home() / ".hummingbot_certs.pem"
if cert_file.exists():
    os.environ['SSL_CERT_FILE'] = str(cert_file)
    os.environ['REQUESTS_CA_BUNDLE'] = str(cert_file)
    os.environ['CURL_CA_BUNDLE'] = str(cert_file)

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# 添加 tradingview-ai 项目路径（用于BinancePublicDataManager）
# 数据路径已迁移到新位置: /mnt/hdd/bigdata/binance_klines/data/futures/um
# 如果需要使用 BinancePublicDataManager，需要设置环境变量或修改其配置
# tradingview_ai_path = Path("/Users/wilson/Desktop/tradingview-ai")
# sys.path.insert(0, str(tradingview_ai_path))

# 临时禁用ccxt（如果只需要读取本地数据）
class FakeCCXT:
    pass
sys.modules['ccxt'] = FakeCCXT()

from hummingbot.strategy_v2.backtesting.backtesting_engine_base import BacktestingEngineBase
from hummingbot.data_feed.candles_feed.candles_factory import CandlesConfig
from controllers.market_making.pmm_bar_portion import PMMBarPortionControllerConfig
from controllers.market_making.pmm_dynamic import PMMDynamicControllerConfig
from hummingbot.strategy_v2.executors.position_executor.data_types import TripleBarrierConfig, OrderType

# 导入本地数据管理器
# 数据路径已迁移到新位置，直接读取本地zip文件
LOCAL_DATA_AVAILABLE = True
DATA_BASE_PATH = Path("/mnt/hdd/bigdata/binance_klines/data/futures/um")

# 自定义交易对
CUSTOM_TEST_PAIRS = ["BTC-USDT", "SOL-USDT", "ETH-USDT", "XRP-USDT", "AVAX-USDT", "DOT-USDT", "MYX-USDT"]

# 最近1天时间范围（用于快速验证）
def get_last_1_day_dates():
    """获取最近1天的日期字符串"""
    current_year = datetime.now().year
    if current_year > 2024:
        end_date = datetime(2024, 11, 12)
    else:
        end_date = datetime.now()
    start_date = end_date - timedelta(days=1)
    return start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")

# 最近半年时间范围
def get_last_6_months_dates():
    """获取最近6个月的日期字符串"""
    start_date = datetime(2025, 1, 1)
    end_date = datetime(2025, 11, 12)
    return start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")

INITIAL_PORTFOLIO_USD = 1000  # 初始资金
TRADING_FEE = 0.0004  # 0.04% 交易费用


class LocalBinanceDataProvider:
    """使用本地Binance数据的提供器 - 直接读取新路径数据"""
    
    def __init__(self, data_base_path: Path = None):
        if not LOCAL_DATA_AVAILABLE:
            raise ImportError("本地数据不可用")
        self.data_base_path = data_base_path or DATA_BASE_PATH
        self._cache = {}  # 缓存已加载的数据
    
    def _convert_symbol(self, symbol: str) -> str:
        """转换交易对格式: BTC-USDT -> BTCUSDT"""
        return symbol.replace('-', '')
    
    def _load_data_from_zip(self, symbol: str, start_date: date, end_date: date) -> pd.DataFrame:
        """直接从zip文件加载数据"""
        import zipfile
        from calendar import monthrange
        
        all_data = []
        
        # 生成需要读取的月份列表
        current_date = start_date.replace(day=1)  # 从月初开始
        end_month = end_date.replace(day=1)
        
        while current_date <= end_month:
            year = current_date.year
            month = current_date.month
            
            # 构建zip文件路径: monthly/klines/{SYMBOL}/1m/{SYMBOL}-1m-{YYYY}-{MM}.zip
            zip_path = self.data_base_path / "monthly" / "klines" / symbol / "1m" / f"{symbol}-1m-{year:04d}-{month:02d}.zip"
            
            if zip_path.exists():
                try:
                    with zipfile.ZipFile(zip_path, 'r') as zf:
                        # 读取zip内的CSV文件（通常只有一个文件）
                        csv_files = [f for f in zf.namelist() if f.endswith('.csv')]
                        if csv_files:
                            csv_file = csv_files[0]
                            # 读取CSV数据
                            df = pd.read_csv(zf.open(csv_file))
                            
                            # Binance数据格式: open_time, open, high, low, close, volume, close_time, ...
                            # 重命名列
                            if 'open_time' in df.columns:
                                df['timestamp'] = pd.to_datetime(df['open_time'], unit='ms')
                            elif 'timestamp' not in df.columns:
                                # 如果没有timestamp，尝试第一列
                                if len(df.columns) > 0:
                                    df['timestamp'] = pd.to_datetime(df.iloc[:, 0], unit='ms')
                            
                            # 确保有必要的列
                            required_cols = ['open', 'high', 'low', 'close', 'volume']
                            col_mapping = {
                                1: 'open', 2: 'high', 3: 'low', 4: 'close', 5: 'volume'
                            }
                            for idx, col_name in col_mapping.items():
                                if col_name not in df.columns and len(df.columns) > idx:
                                    df[col_name] = df.iloc[:, idx]
                            
                            all_data.append(df)
                except Exception as e:
                    print(f"⚠️  读取文件失败 {zip_path}: {e}")
            
            # 移动到下一个月
            if month == 12:
                current_date = current_date.replace(year=year + 1, month=1)
            else:
                current_date = current_date.replace(month=month + 1)
        
        if not all_data:
            return pd.DataFrame(columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        
        # 合并所有数据
        df = pd.concat(all_data, ignore_index=True)
        
        # 确保timestamp是datetime类型
        if 'timestamp' in df.columns:
            if not pd.api.types.is_datetime64_any_dtype(df['timestamp']):
                df['timestamp'] = pd.to_datetime(df['timestamp'])
        else:
            return pd.DataFrame(columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        
        # 过滤日期范围
        df = df[(df['timestamp'].dt.date >= start_date) & (df['timestamp'].dt.date <= end_date)]
        
        # 选择需要的列
        required_columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
        available_columns = [col for col in required_columns if col in df.columns]
        df = df[available_columns].copy()
        
        # 确保数据类型正确
        for col in ['open', 'high', 'low', 'close', 'volume']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        
        # 按timestamp排序
        df = df.sort_values('timestamp').reset_index(drop=True)
        
        return df
    
    def get_historical_candles(
        self,
        symbol: str,
        start_ts: int,
        end_ts: int,
        interval: str = "1m"
    ) -> pd.DataFrame:
        """
        获取历史K线数据
        
        Args:
            symbol: 交易对符号（如 'BTC-USDT'）
            start_ts: 开始时间戳（秒）
            end_ts: 结束时间戳（秒）
            interval: K线间隔（默认1m，支持1m, 3m, 5m, 15m, 30m, 1h等）
        
        Returns:
            DataFrame with columns: timestamp, open, high, low, close, volume
        """
        # 确保时间戳是整数类型
        if isinstance(start_ts, str):
            start_ts = int(start_ts)
        if isinstance(end_ts, str):
            end_ts = int(end_ts)
        
        # 转换交易对格式
        binance_symbol = self._convert_symbol(symbol)
        
        # 转换时间戳为日期
        start_date = datetime.fromtimestamp(int(start_ts)).date()
        end_date = datetime.fromtimestamp(int(end_ts)).date()
        
        # 检查缓存（包含interval）
        cache_key = f"{binance_symbol}_{start_date}_{end_date}_{interval}"
        if cache_key in self._cache:
            df = self._cache[cache_key].copy()
        else:
            # 总是从1分钟数据读取（BinancePublicDataManager只支持1m）
            base_cache_key = f"{binance_symbol}_{start_date}_{end_date}_1m"
            if base_cache_key in self._cache:
                df = self._cache[base_cache_key].copy()
            else:
                # 直接读取新路径的zip文件
                df = self._load_data_from_zip(binance_symbol, start_date, end_date)
                
                if df.empty:
                    return pd.DataFrame(columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                
                # BinancePublicDataManager返回的格式：
                # - 索引：DatetimeIndex (name='timestamp')
                # - 列：['open', 'high', 'low', 'close', 'volume']
                
                # 重置索引，将timestamp从索引转为列
                if isinstance(df.index, pd.DatetimeIndex) and df.index.name == 'timestamp':
                    df = df.reset_index()  # 将DatetimeIndex转为timestamp列
                
                # 确保timestamp列存在
                if 'timestamp' not in df.columns:
                    # 如果没有timestamp列，尝试从索引创建
                    if isinstance(df.index, pd.DatetimeIndex):
                        df = df.reset_index()
                        df['timestamp'] = df.index if 'index' not in df.columns else df['index']
                    else:
                        raise ValueError("无法找到timestamp列或索引")
                
                # 将timestamp转换为datetime（用于resample）
                if not pd.api.types.is_datetime64_any_dtype(df['timestamp']):
                    df['timestamp'] = pd.to_datetime(df['timestamp'])
                
                # 缓存1分钟数据
                self._cache[base_cache_key] = df.copy()
            
            # 如果需要聚合到更大的时间间隔
            if interval != "1m":
                # 设置timestamp为索引用于resample
                df_resample = df.set_index('timestamp')
                
                # 定义resample规则
                interval_map = {
                    "3m": "3min",
                    "5m": "5min",
                    "15m": "15min",
                    "30m": "30min",
                    "1h": "1H",
                    "2h": "2H",
                    "4h": "4H",
                    "6h": "6H",
                    "12h": "12H",
                    "1d": "1D",
                }
                
                resample_rule = interval_map.get(interval, interval)
                
                # 聚合K线数据
                df_resampled = df_resample.resample(resample_rule).agg({
                    'open': 'first',
                    'high': 'max',
                    'low': 'min',
                    'close': 'last',
                    'volume': 'sum'
                }).dropna()
                
                # 重置索引，将timestamp转为列
                df = df_resampled.reset_index()
            
            # 将timestamp转换为Unix时间戳（秒，整数）
            if pd.api.types.is_datetime64_any_dtype(df['timestamp']):
                # 如果是datetime类型，转换为Unix时间戳（秒）
                df['timestamp'] = (df['timestamp'].astype('int64') // 10**9).astype('int64')
            elif pd.api.types.is_integer_dtype(df['timestamp']):
                # 如果已经是整数，检查是否是毫秒（>1e12），如果是则转换为秒
                if df['timestamp'].max() > 1e12:
                    df['timestamp'] = (df['timestamp'] // 1000).astype('int64')
                else:
                    df['timestamp'] = df['timestamp'].astype('int64')
            else:
                # 其他类型，尝试转换
                df['timestamp'] = pd.to_datetime(df['timestamp']).astype('int64') // 10**9
                df['timestamp'] = df['timestamp'].astype('int64')
            
            # 过滤时间范围
            df = df[(df['timestamp'] >= start_ts) & (df['timestamp'] <= end_ts)]
            
            # 确保所有必需的列存在
            required_columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
            for col in required_columns:
                if col not in df.columns:
                    if col == 'timestamp':
                        continue
                    df[col] = 0.0
            
            # 确保数据类型正确
            df['timestamp'] = df['timestamp'].astype('int64')
            df['open'] = df['open'].astype('float64')
            df['high'] = df['high'].astype('float64')
            df['low'] = df['low'].astype('float64')
            df['close'] = df['close'].astype('float64')
            df['volume'] = df['volume'].astype('float64')
            
            # 按timestamp排序
            df = df[required_columns].copy()
            df = df.sort_values('timestamp').reset_index(drop=True)
            
            # 缓存数据（保持timestamp为列，回测引擎会处理索引）
            self._cache[cache_key] = df.copy()
        
        return df


class LocalBacktestingDataProvider:
    """使用本地数据的回测数据提供器（兼容BacktestingDataProvider接口）"""
    
    def __init__(self, local_data_provider: LocalBinanceDataProvider):
        from hummingbot.data_feed.market_data_provider import MarketDataProvider
        # 初始化MarketDataProvider的基本属性
        self.connectors = {}
        self.candles_feeds = {}
        self.start_time = None
        self.end_time = None
        self._time = None
        self.prices = {}
        self.trading_rules = {}
        self.local_data_provider = local_data_provider
    
    @staticmethod
    def ensure_epoch_index(df: pd.DataFrame, timestamp_column: str = "timestamp",
                           keep_original: bool = True, index_name: str = "epoch_seconds") -> pd.DataFrame:
        """
        确保DataFrame有数字时间戳索引（秒级，整数类型）
        
        这个方法会被BacktestingEngineBase调用，用于将timestamp列转换为整数索引
        """
        # 如果已经是正确的索引，直接返回
        if df.index.name == index_name and pd.api.types.is_integer_dtype(df.index):
            return df
        
        if df.empty:
            return df
        
        # DatetimeIndex → 转换为秒（整数）
        if isinstance(df.index, pd.DatetimeIndex):
            df.index = (df.index.astype('int64') // 10**9).astype('int64')
        # 有timestamp列 → 用作索引
        elif timestamp_column in df.columns:
            # 确保timestamp列是整数类型
            if not pd.api.types.is_integer_dtype(df[timestamp_column]):
                df[timestamp_column] = df[timestamp_column].astype('int64')
            
            df = df.set_index(timestamp_column, drop=not keep_original)
            # 确保索引是整数类型（不是float）
            if not pd.api.types.is_integer_dtype(df.index):
                df.index = df.index.astype('int64')
        else:
            raise ValueError(f"Cannot create timestamp index: no '{timestamp_column}' column found and index isn't convertible")
        
        df.sort_index(inplace=True)
        df.index.name = index_name
        # 确保索引是int64类型（不是float）
        df.index = df.index.astype('int64')
        return df
    
    def update_backtesting_time(self, start_time: int, end_time: int):
        """更新回测时间范围"""
        self.start_time = start_time
        self.end_time = end_time
        self._time = start_time
    
    def time(self):
        """返回当前回测时间"""
        return self._time
    
    def _generate_candle_feed_key(self, config) -> str:
        """生成candle feed的key"""
        from hummingbot.data_feed.candles_feed.data_types import CandlesConfig
        if isinstance(config, CandlesConfig):
            return f"{config.connector}_{config.trading_pair}_{config.interval}"
        return str(config)
    
    async def initialize_trading_rules(self, connector_name: str):
        """初始化交易规则（本地数据不需要）"""
        if connector_name not in self.trading_rules:
            # 创建空的交易规则
            self.trading_rules[connector_name] = {}
    
    async def initialize_candles_feed(self, config):
        """初始化candle feed"""
        await self.get_candles_feed(config)
    
    async def get_candles_feed(self, config):
        """获取candle feed数据"""
        from hummingbot.data_feed.candles_feed.data_types import CandlesConfig
        
        if isinstance(config, CandlesConfig):
            connector_name = config.connector
            trading_pair = config.trading_pair
            interval = config.interval
        else:
            # 兼容其他格式
            connector_name = getattr(config, 'connector', 'binance_perpetual')
            trading_pair = getattr(config, 'trading_pair', '')
            interval = getattr(config, 'interval', '1m')
        
        key = self._generate_candle_feed_key(config)
        
        # 检查缓存
        if key in self.candles_feeds:
            existing_feed = self.candles_feeds[key]
            if not existing_feed.empty:
                # 检查timestamp是索引还是列
                if existing_feed.index.name == 'timestamp' or (isinstance(existing_feed.index, pd.Index) and pd.api.types.is_integer_dtype(existing_feed.index)):
                    existing_start = existing_feed.index.min()
                    existing_end = existing_feed.index.max()
                elif 'timestamp' in existing_feed.columns:
                    existing_start = existing_feed["timestamp"].min()
                    existing_end = existing_feed["timestamp"].max()
                else:
                    existing_start = None
                    existing_end = None
                
                if existing_start is not None and existing_start <= self.start_time and existing_end >= self.end_time:
                    return existing_feed
        
        # 从本地数据获取
        candles_df = self.local_data_provider.get_historical_candles(
            symbol=trading_pair,
            start_ts=self.start_time,
            end_ts=self.end_time,
            interval=interval
        )
        
        # 确保数据格式正确（timestamp必须是列，且为int64）
        if not candles_df.empty:
            # 如果timestamp是索引，重置为列
            if candles_df.index.name == 'timestamp' or (isinstance(candles_df.index, pd.Index) and pd.api.types.is_integer_dtype(candles_df.index)):
                candles_df = candles_df.reset_index()
                if 'timestamp' not in candles_df.columns:
                    candles_df['timestamp'] = candles_df.index
            
            # 确保timestamp是int64类型
            if 'timestamp' in candles_df.columns:
                candles_df['timestamp'] = candles_df['timestamp'].astype('int64')
            
            # 确保所有必需的列存在
            required_columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
            for col in required_columns:
                if col not in candles_df.columns:
                    if col == 'timestamp':
                        continue
                    candles_df[col] = 0.0
            
            # 确保数据类型正确
            candles_df['open'] = candles_df['open'].astype('float64')
            candles_df['high'] = candles_df['high'].astype('float64')
            candles_df['low'] = candles_df['low'].astype('float64')
            candles_df['close'] = candles_df['close'].astype('float64')
            candles_df['volume'] = candles_df['volume'].astype('float64')
        
        # 存储到缓存（即使为空也要存储，避免重复查询）
        self.candles_feeds[key] = candles_df
        
        return candles_df
    
    def get_candles_df(self, connector_name: str, trading_pair: str, interval: str, max_records: int = None):
        """获取candles DataFrame（必须包含timestamp列）
        
        Args:
            connector_name: 连接器名称
            trading_pair: 交易对
            interval: 时间间隔
            max_records: 最大记录数（None表示不限制）
        """
        key = f"{connector_name}_{trading_pair}_{interval}"
        candles_df = self.candles_feeds.get(key)
        
        # 如果缓存中没有数据，尝试从本地数据提供器直接获取
        if candles_df is None or candles_df.empty:
            # 直接调用local_data_provider获取数据
            candles_df = self.local_data_provider.get_historical_candles(
                symbol=trading_pair,
                start_ts=self.start_time,
                end_ts=self.end_time,
                interval=interval
            )
            
            # 如果获取到数据，存储到缓存
            if not candles_df.empty:
                self.candles_feeds[key] = candles_df.copy()
            else:
                return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])
        
        # 如果timestamp是索引，重置为列
        if candles_df.index.name == 'timestamp' or (isinstance(candles_df.index, pd.Index) and pd.api.types.is_integer_dtype(candles_df.index)):
            # timestamp是索引，重置为列
            candles_df = candles_df.reset_index()
            if 'timestamp' not in candles_df.columns:
                candles_df['timestamp'] = candles_df.index
            # 清理reset_index产生的'index'列
            if 'index' in candles_df.columns:
                candles_df = candles_df.drop(columns=['index'])
        
        # 确保timestamp是列且为int64
        if 'timestamp' not in candles_df.columns:
            return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])
        
        # 确保timestamp是int64类型（不是float）
        candles_df['timestamp'] = candles_df['timestamp'].astype('int64')
        
        # 过滤时间范围
        filtered_df = candles_df[
            (candles_df["timestamp"] >= self.start_time) & 
            (candles_df["timestamp"] <= self.end_time)
        ]
        
        # 限制返回的记录数（仅当max_records不为None时）
        if max_records is not None and len(filtered_df) > max_records:
            filtered_df = filtered_df.iloc[-max_records:]
        
        return filtered_df
    
    def get_price_by_type(self, connector_name: str, trading_pair: str, price_type):
        """获取价格（本地数据不需要）"""
        from hummingbot.core.data_type.common import PriceType
        key = f"{connector_name}_{trading_pair}"
        return self.prices.get(key, Decimal("1"))
    
    def quantize_order_amount(self, connector_name: str, trading_pair: str, amount: Decimal):
        """量化订单数量（本地数据不需要）"""
        return amount
    
    def initialize_rate_sources(self, connector_pairs):
        """初始化汇率源（本地数据不需要，同步方法）"""
        pass
    
    def get_trading_rules(self, connector_name: str, trading_pair: str):
        """获取交易规则（本地数据不需要）"""
        return self.trading_rules.get(connector_name, {}).get(trading_pair, None)


class StrategyBacktester:
    """策略回测器（使用本地数据）"""
    
    def __init__(
        self,
        trading_pair: str,
        start_date: str,
        end_date: str,
        initial_portfolio: float = INITIAL_PORTFOLIO_USD
    ):
        self.trading_pair = trading_pair
        self.start_date = start_date
        self.end_date = end_date
        self.initial_portfolio = initial_portfolio
        
        # 初始化本地数据提供器
        if not LOCAL_DATA_AVAILABLE:
            raise ImportError("本地数据不可用，请检查BinancePublicDataManager")
        
        self.local_data_provider = LocalBinanceDataProvider()
        self.local_backtesting_provider = LocalBacktestingDataProvider(self.local_data_provider)
        
    def create_bp_config(
        self,
        spreads: List[float] = None,
        stop_loss: float = 0.03,
        take_profit: float = 0.02,
        time_limit_minutes: int = 45
    ) -> PMMBarPortionControllerConfig:
        """创建Bar Portion策略配置"""
        if spreads is None:
            spreads = [0.01, 0.02]  # 1%, 2% spread
        
        return PMMBarPortionControllerConfig(
            controller_name="pmm_bar_portion",
            connector_name="binance_perpetual",
            trading_pair=self.trading_pair,
            total_amount_quote=Decimal(str(self.initial_portfolio)),
            buy_spreads=spreads,
            sell_spreads=spreads,
            buy_amounts_pct=[0.5, 0.5],  # 平均分配
            sell_amounts_pct=[0.5, 0.5],
            candles_connector="binance_perpetual",
            candles_trading_pair=self.trading_pair,
            interval="1m",
            stop_loss=Decimal(str(stop_loss)),
            take_profit=Decimal(str(take_profit)),
            time_limit=time_limit_minutes * 60,
        )
    
    def create_macd_config(
        self,
        buy_spreads: List[float] = None,
        sell_spreads: List[float] = None
    ) -> PMMDynamicControllerConfig:
        """创建MACD策略配置"""
        if buy_spreads is None:
            buy_spreads = [1.0, 2.0, 4.0]
        if sell_spreads is None:
            sell_spreads = [1.0, 2.0, 4.0]
        
        return PMMDynamicControllerConfig(
            controller_name="pmm_dynamic",
            connector_name="binance_perpetual",
            trading_pair=self.trading_pair,
            total_amount_quote=Decimal(str(self.initial_portfolio)),
            buy_spreads=buy_spreads,
            sell_spreads=sell_spreads,
            candles_connector="binance_perpetual",
            candles_trading_pair=self.trading_pair,
            interval="1m"
        )
    
    async def run_backtest(
        self,
        config,
        backtesting_resolution: str = "1m"
    ) -> Dict:
        """
        运行回测
        
        Args:
            config: 策略配置
            backtesting_resolution: 回测分辨率
        
        Returns:
            Dict: 回测结果
        """
        print(f"\n运行回测: {config.controller_name} - {self.trading_pair}")
        print(f"时间范围: {self.start_date} 至 {self.end_date}")
        
        try:
            # 创建回测引擎
            engine = BacktestingEngineBase()
            
            # 替换数据提供器为本地数据提供器
            engine.backtesting_data_provider = self.local_backtesting_provider
            
            # 转换日期字符串为时间戳（秒）
            start_dt = datetime.strptime(self.start_date, "%Y-%m-%d")
            end_dt = datetime.strptime(self.end_date, "%Y-%m-%d")
            start_ts = int(start_dt.timestamp())
            end_ts = int(end_dt.timestamp())
            
            # 更新回测时间
            self.local_backtesting_provider.update_backtesting_time(start_ts, end_ts)
            
            # 验证数据获取
            print(f"验证数据获取...")
            test_df = self.local_data_provider.get_historical_candles(
                symbol=self.trading_pair,
                start_ts=start_ts,
                end_ts=end_ts,
                interval=backtesting_resolution
            )
            
            print(f"数据获取: {len(test_df)} 条K线")
            if len(test_df) == 0:
                print(f"⚠️  警告: 未获取到任何数据！")
                print(f"   时间范围: {self.start_date} 至 {self.end_date}")
                print(f"   时间戳: {start_ts} ({datetime.fromtimestamp(start_ts)}) 至 {end_ts} ({datetime.fromtimestamp(end_ts)})")
                return None
            elif len(test_df) < 100:
                print(f"⚠️  警告: 数据量不足（{len(test_df)} < 100），可能影响回测质量")
            else:
                print(f"✓ 数据量充足: {len(test_df)} 条K线")
            
            # 运行回测
            results = await engine.run_backtesting(
                controller_config=config,
                start=start_ts,
                end=end_ts,
                backtesting_resolution=backtesting_resolution,
                trade_cost=TRADING_FEE
            )
            
            # 验证结果
            if results:
                if isinstance(results, dict) and 'executors' in results:
                    executors = results['executors']
                    print(f"✓ 回测完成，生成 {len(executors)} 个executor")
                    if len(executors) == 0:
                        print(f"⚠️  警告: 未生成任何executor")
                    else:
                        filled = [e for e in executors if hasattr(e, 'filled_amount_quote') and float(e.filled_amount_quote) > 0]
                        active = [e for e in executors if hasattr(e, 'is_active') and e.is_active]
                        print(f"  - 活跃executor: {len(active)}/{len(executors)}")
                        print(f"  - 成交executor: {len(filled)}/{len(executors)}")
                        if len(filled) > 0:
                            total_pnl = sum(float(e.net_pnl_quote) for e in filled)
                            print(f"  - 总盈亏: ${total_pnl:.2f}")
                            for i, e in enumerate(filled[:3]):
                                print(f"    Executor {i+1}: PnL=${float(e.net_pnl_quote):.2f}, Amount=${float(e.filled_amount_quote):.2f}")
            
            return results
            
        except Exception as e:
            print(f"回测失败: {str(e)}")
            import traceback
            traceback.print_exc()
            return None


# 性能分析器（复用原有代码）
class PerformanceAnalyzer:
    """性能分析器"""
    
    @staticmethod
    def calculate_metrics(executors: List) -> Dict:
        """计算性能指标"""
        if not executors:
            return {
                'total_return': 0.0,
                'total_return_pct': 0.0,
                'sharpe_ratio': 0.0,
                'max_drawdown': 0.0,
                'max_drawdown_pct': 0.0,
                'win_rate': 0.0,
                'total_trades': 0,
                'winning_trades': 0,
                'losing_trades': 0,
                'avg_trade_pnl': 0.0
            }
        
        # 过滤已成交的executor
        filled_executors = [
            e for e in executors 
            if hasattr(e, 'filled_amount_quote') and float(e.filled_amount_quote) > 0
        ]
        
        if not filled_executors:
            return {
                'total_return': 0.0,
                'total_return_pct': 0.0,
                'sharpe_ratio': 0.0,
                'max_drawdown': 0.0,
                'max_drawdown_pct': 0.0,
                'win_rate': 0.0,
                'total_trades': 0,
                'winning_trades': 0,
                'losing_trades': 0,
                'avg_trade_pnl': 0.0
            }
        
        # 计算总收益
        total_pnl = sum(float(e.net_pnl_quote) for e in filled_executors)
        total_return_pct = (total_pnl / INITIAL_PORTFOLIO_USD) * 100
        
        # 计算Sharpe Ratio
        pnls = [float(e.net_pnl_quote) for e in filled_executors]
        if len(pnls) > 1 and np.std(pnls) > 0:
            sharpe_ratio = np.mean(pnls) / np.std(pnls) * np.sqrt(len(pnls))
        else:
            sharpe_ratio = 0.0
        
        # 计算最大回撤
        cumulative_pnl = np.cumsum(pnls)
        running_max = np.maximum.accumulate(cumulative_pnl)
        drawdown = cumulative_pnl - running_max
        max_drawdown = abs(np.min(drawdown)) if len(drawdown) > 0 else 0.0
        max_drawdown_pct = (max_drawdown / INITIAL_PORTFOLIO_USD) * 100
        
        # 计算胜率
        winning_trades = sum(1 for e in filled_executors if float(e.net_pnl_quote) > 0)
        losing_trades = sum(1 for e in filled_executors if float(e.net_pnl_quote) < 0)
        total_trades = len(filled_executors)
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0.0
        
        # 平均每笔交易盈亏
        avg_trade_pnl = np.mean(pnls) if pnls else 0.0
        
        return {
            'total_return': total_pnl,
            'total_return_pct': total_return_pct,
            'sharpe_ratio': sharpe_ratio,
            'max_drawdown': max_drawdown,
            'max_drawdown_pct': max_drawdown_pct,
            'win_rate': win_rate,
            'total_trades': total_trades,
            'winning_trades': winning_trades,
            'losing_trades': losing_trades,
            'avg_trade_pnl': avg_trade_pnl
        }


async def run_single_pair_comparison(pair: str, use_custom_dates: bool = False, use_1day: bool = False):
    """运行单个交易对的策略对比"""
    if use_1day:
        start_date, end_date = get_last_1_day_dates()
    elif use_custom_dates:
        start_date, end_date = get_last_6_months_dates()
    else:
        start_date, end_date = "2024-09-01", "2024-10-14"
    
    backtester = StrategyBacktester(pair, start_date, end_date)
    
    # 运行BP策略
    print(f"\n[1/2] 运行PMM Bar Portion策略回测...")
    bp_config = backtester.create_bp_config()
    bp_results = await backtester.run_backtest(bp_config)
    
    # 运行MACD策略
    print(f"\n[2/2] 运行PMM Dynamic (MACD)策略回测...")
    macd_config = backtester.create_macd_config()
    macd_results = await backtester.run_backtest(macd_config)
    
    # 计算指标
    bp_metrics = PerformanceAnalyzer.calculate_metrics(
        bp_results['executors'] if bp_results and 'executors' in bp_results else []
    )
    macd_metrics = PerformanceAnalyzer.calculate_metrics(
        macd_results['executors'] if macd_results and 'executors' in macd_results else []
    )
    
    # 打印结果
    print(f"\n{'='*80}")
    print(f"策略对比结果 - {pair}")
    print(f"{'='*80}")
    print(f"{'Metric':<20} {'PMM Bar Portion':<20} {'PMM Dynamic (MACD)':<20}")
    print(f"{'-'*80}")
    print(f"{'Total Return ($)':<20} ${bp_metrics['total_return']:<19.2f} ${macd_metrics['total_return']:<19.2f}")
    print(f"{'Total Return (%)':<20} {bp_metrics['total_return_pct']:<19.2f}% {macd_metrics['total_return_pct']:<19.2f}%")
    print(f"{'Sharpe Ratio':<20} {bp_metrics['sharpe_ratio']:<19.4f} {macd_metrics['sharpe_ratio']:<19.4f}")
    print(f"{'Max Drawdown ($)':<20} ${bp_metrics['max_drawdown']:<19.2f} ${macd_metrics['max_drawdown']:<19.2f}")
    print(f"{'Max Drawdown (%)':<20} {bp_metrics['max_drawdown_pct']:<19.2f}% {macd_metrics['max_drawdown_pct']:<19.2f}%")
    print(f"{'Win Rate (%)':<20} {bp_metrics['win_rate']:<19.2f}% {macd_metrics['win_rate']:<19.2f}%")
    print(f"{'Total Trades':<20} {bp_metrics['total_trades']:<19} {macd_metrics['total_trades']:<19}")
    print(f"{'Winning Trades':<20} {bp_metrics['winning_trades']:<19} {macd_metrics['winning_trades']:<19}")
    print(f"{'Losing Trades':<20} {bp_metrics['losing_trades']:<19} {macd_metrics['losing_trades']:<19}")
    print(f"{'Avg Trade P&L ($)':<20} ${bp_metrics['avg_trade_pnl']:<19.4f} ${macd_metrics['avg_trade_pnl']:<19.4f}")
    
    return {
        'trading_pair': pair,
        'bp_metrics': bp_metrics,
        'macd_metrics': macd_metrics
    }


async def run_custom_pairs_comparison(use_1day: bool = False, parallel: bool = True, max_workers: int = 4):
    """运行自定义交易对的回测（使用本地数据）"""
    from datetime import datetime as dt
    
    if use_1day:
        start_date, end_date = get_last_1_day_dates()
        print("⚠️  使用最近1天数据（快速验证模式）")
    else:
        start_date, end_date = get_last_6_months_dates()
    
    print("="*80)
    print("自定义交易对回测（使用本地数据）")
    print("="*80)
    print(f"测试交易对: {', '.join(CUSTOM_TEST_PAIRS)}")
    print(f"时间范围: {start_date} 至 {end_date}")
    print(f"初始资金: ${INITIAL_PORTFOLIO_USD}")
    print(f"交易费用: {TRADING_FEE*100}%")
    print(f"并行模式: {'启用' if parallel else '禁用'}（{max_workers if parallel else 1} 核）")
    print("="*80)
    
    all_results = []
    start_time = dt.now()
    
    if parallel:
        print(f"\n开始并发回测（{len(CUSTOM_TEST_PAIRS)} 个交易对）...")
        print(f"✓ 使用本地数据，无API限流问题")
        
        safe_max_workers = min(max_workers, 4)
        semaphore = asyncio.Semaphore(safe_max_workers)
        
        async def run_with_semaphore(pair, index):
            async with semaphore:
                if index > 0:
                    await asyncio.sleep(index * 0.1)  # 短暂延迟
                return await run_single_pair_comparison(pair, use_custom_dates=True, use_1day=use_1day)
        
        tasks = [run_with_semaphore(pair, i) for i, pair in enumerate(CUSTOM_TEST_PAIRS)]
        
        completed = 0
        for coro in asyncio.as_completed(tasks):
            completed += 1
            try:
                result = await coro
                all_results.append(result)
                elapsed = (dt.now() - start_time).total_seconds()
                pair = result.get('trading_pair', 'Unknown')
                print(f"[{completed}/{len(CUSTOM_TEST_PAIRS)}] ✓ {pair} 完成 (耗时: {elapsed:.1f}秒)")
            except Exception as e:
                print(f"[{completed}/{len(CUSTOM_TEST_PAIRS)}] ✗ 失败: {e}")
                all_results.append({
                    'trading_pair': 'Unknown',
                    'bp_metrics': {},
                    'macd_metrics': {},
                    'error': str(e)
                })
    else:
        for i, pair in enumerate(CUSTOM_TEST_PAIRS, 1):
            print(f"\n[{i}/{len(CUSTOM_TEST_PAIRS)}] 处理 {pair}...")
            result = await run_single_pair_comparison(pair, use_custom_dates=True, use_1day=use_1day)
            all_results.append(result)
    
    total_time = (dt.now() - start_time).total_seconds()
    print(f"\n✓ 所有回测完成，总耗时: {total_time:.1f}秒 ({total_time/60:.1f}分钟)")
    print(f"平均每个交易对: {total_time/len(CUSTOM_TEST_PAIRS):.1f}秒")
    
    # 生成汇总报告
    print(f"\n{'='*80}")
    print("汇总结果")
    print(f"{'='*80}")
    print(f"{'Trading Pair':<15} {'BP Return (%)':<15} {'MACD Return (%)':<15} {'BP Sharpe':<12} {'MACD Sharpe':<12} {'BP Max DD (%)':<15} {'MACD Max DD (%)':<15}")
    print(f"{'-'*80}")
    
    for result in all_results:
        pair = result.get('trading_pair', 'Unknown')
        bp_metrics = result.get('bp_metrics', {})
        macd_metrics = result.get('macd_metrics', {})
        print(f"{pair:<15} {bp_metrics.get('total_return_pct', 0):<15.2f} {macd_metrics.get('total_return_pct', 0):<15.2f} "
              f"{bp_metrics.get('sharpe_ratio', 0):<12.4f} {macd_metrics.get('sharpe_ratio', 0):<12.4f} "
              f"{bp_metrics.get('max_drawdown_pct', 0):<15.2f} {macd_metrics.get('max_drawdown_pct', 0):<15.2f}")
    
    return all_results


async def main():
    """主函数"""
    import sys
    
    if not LOCAL_DATA_AVAILABLE:
        print("✗ 错误: 本地数据不可用")
        print("请确保:")
        print("1. 数据路径正确: /mnt/hdd/bigdata/binance_klines/data/futures/um")
        print("2. 数据文件存在且可读")
        sys.exit(1)
    
    if len(sys.argv) > 1:
        command = sys.argv[1].upper()
        if command == "TEST" or command == "1DAY":
            await run_custom_pairs_comparison(use_1day=True, parallel=True, max_workers=4)
        elif command == "CUSTOM" or command == "6MONTHS":
            await run_custom_pairs_comparison(use_1day=False, parallel=True, max_workers=4)
        else:
            print(f"未知命令: {command}")
            print("可用命令: TEST/1DAY (1天), CUSTOM/6MONTHS (6个月)")
    else:
        # 默认运行1天测试
        await run_custom_pairs_comparison(use_1day=True, parallel=True, max_workers=4)


if __name__ == "__main__":
    asyncio.run(main())

