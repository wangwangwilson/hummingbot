"""数据准备模块：从数据源读取并准备回测数据"""
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Tuple
import numpy as np
import duckdb

# 添加 bigdata_plan 到路径以复用数据读取器
bigdata_plan_path = Path(__file__).parent.parent.parent.parent / "bigdata_plan"
if str(bigdata_plan_path) not in sys.path:
    sys.path.insert(0, str(bigdata_plan_path))

try:
    from src.utils.data_reader import BinanceDataReader
    from src.const import BINANCE_AGGTrades_DIR
except ImportError:
    # 如果无法导入，使用默认路径
    BINANCE_AGGTrades_DIR = "/mnt/hdd/data"
    BinanceDataReader = None
from .preprocessor import preprocess_aggtrades, merge_exchange_data, validate_data


class DataPreparer:
    """数据准备器，负责从数据源读取并准备回测数据"""
    
    def __init__(self, binance_data_dir: Optional[str] = None):
        """
        初始化数据准备器
        
        Args:
            binance_data_dir: Binance数据目录，默认使用配置中的路径
        """
        self.binance_data_dir = binance_data_dir or BINANCE_AGGTrades_DIR
        if BinanceDataReader is not None:
            self.reader = BinanceDataReader(base_dir=self.binance_data_dir)
        else:
            self.reader = None
    
    def prepare_binance_aggtrades(
        self,
        symbol: str,
        trading_type: str,
        start_date: datetime,
        end_date: datetime,
        contract_size: float = 1.0
    ) -> np.ndarray:
        """
        准备Binance逐笔成交数据
        
        Args:
            symbol: 交易对符号，如 'BTCUSDT'
            trading_type: 交易类型 ('spot', 'um', 'cm')
            start_date: 开始日期
            end_date: 结束日期
            contract_size: 合约乘数
        
        Returns:
            处理后的numpy数组，格式: [timestamp, order_side, price, quantity, mm_flag]
        """
        if self.reader is None:
            raise ImportError("BinanceDataReader 未可用，请检查 bigdata_plan 项目路径")
        
        # 读取原始数据
        df = self.reader.read_data(
            trading_type=trading_type,
            data_type='aggTrades',
            symbol=symbol,
            start_date=start_date,
            end_date=end_date
        )
        
        if df.empty:
            return np.empty((0, 5), dtype=np.float64)
        
        # 转换为numpy数组：timestamp, price, quantity, is_buyer_maker
        data_array = df[['timestamp', 'price', 'quantity', 'is_buyer_maker']].values
        
        # 预处理数据
        processed_data = preprocess_aggtrades(
            data=data_array,
            exchange_flag=0,  # 0表示市场数据
            contract_size=contract_size
        )
        
        return processed_data
    
    def prepare_from_duckdb(
        self,
        file_paths: List[str],
        start_ts: Optional[int] = None,
        end_ts: Optional[int] = None,
        contract_size: float = 1.0,
        exchange_flag: int = 0
    ) -> np.ndarray:
        """
        直接从DuckDB读取parquet文件准备数据
        
        Args:
            file_paths: parquet文件路径列表
            start_ts: 开始时间戳（毫秒）
            end_ts: 结束时间戳（毫秒）
            contract_size: 合约乘数
            exchange_flag: 交易所标识
        
        Returns:
            处理后的numpy数组
        """
        if not file_paths:
            return np.empty((0, 5), dtype=np.float64)
        
        conn = duckdb.connect()
        
        try:
            # 构建SQL查询
            file_list_str = str(file_paths)
            
            query = f"""
                SELECT 
                    timestamp as create_time,
                    CASE WHEN is_buyer_maker THEN -1 ELSE 1 END as order_side,
                    price as trade_price,
                    {contract_size} * quantity as trade_quantity,
                    {exchange_flag} as mm
                FROM read_parquet({file_list_str})
            """
            
            if start_ts is not None:
                query += f" WHERE timestamp >= {start_ts}"
            if end_ts is not None:
                if start_ts is not None:
                    query += f" AND timestamp <= {end_ts}"
                else:
                    query += f" WHERE timestamp <= {end_ts}"
            
            query += " ORDER BY timestamp ASC"
            
            # 执行查询
            result = conn.execute(query).fetchall()
            
            if not result:
                return np.empty((0, 5), dtype=np.float64)
            
            # 转换为numpy数组
            data_array = np.array(result, dtype=np.float64)
            
            return data_array
            
        finally:
            conn.close()
    
    def prepare_multi_exchange(
        self,
        data_sources: List[dict]
    ) -> np.ndarray:
        """
        准备多个交易所的数据并合并
        
        Args:
            data_sources: 数据源列表，每个元素为字典，包含：
                - 'type': 'binance' 或 'duckdb'
                - 'exchange_flag': 交易所标识
                - 其他参数根据type不同而不同
        
        Returns:
            合并后的数据数组
        """
        data_list = []
        exchange_flags = []
        
        for source in data_sources:
            source_type = source.get('type')
            exchange_flag = source.get('exchange_flag', 0)
            
            if source_type == 'binance':
                data = self.prepare_binance_aggtrades(
                    symbol=source['symbol'],
                    trading_type=source['trading_type'],
                    start_date=source['start_date'],
                    end_date=source['end_date'],
                    contract_size=source.get('contract_size', 1.0)
                )
            elif source_type == 'duckdb':
                data = self.prepare_from_duckdb(
                    file_paths=source['file_paths'],
                    start_ts=source.get('start_ts'),
                    end_ts=source.get('end_ts'),
                    contract_size=source.get('contract_size', 1.0),
                    exchange_flag=exchange_flag
                )
            else:
                continue
            
            if data.size > 0:
                data_list.append(data)
                exchange_flags.append(exchange_flag)
        
        # 合并数据
        if data_list:
            merged_data = merge_exchange_data(data_list, exchange_flags)
            # 验证数据
            is_valid, error_msg = validate_data(merged_data)
            if not is_valid:
                raise ValueError(f"数据验证失败: {error_msg}")
            return merged_data
        else:
            return np.empty((0, 5), dtype=np.float64)
    
    def close(self):
        """关闭数据读取器"""
        if self.reader is not None:
            self.reader.close()

