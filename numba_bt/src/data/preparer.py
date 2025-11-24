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

# 也尝试直接添加绝对路径
bigdata_plan_abs = Path("/home/wilson/bigdata_plan")
if str(bigdata_plan_abs) not in sys.path and bigdata_plan_abs.exists():
    sys.path.insert(0, str(bigdata_plan_abs))

try:
    from src.utils.data_reader import BinanceDataReader
    from src.const import BINANCE_AGGTrades_DIR
except ImportError:
    # 如果无法导入，使用默认路径
    BINANCE_AGGTrades_DIR = "/mnt/hdd/data"
    BinanceDataReader = None

# 单独尝试导入FundingRateReader，因为它的依赖可能不同
FundingRateReader = None
try:
    # 先确保bigdata_plan在sys.path中
    if str(bigdata_plan_abs) not in sys.path:
        sys.path.insert(0, str(bigdata_plan_abs))
    
    from src.utils.funding_rate_reader import FundingRateReader
    print(f"  ✅ FundingRateReader 导入成功（标准导入）")
except ImportError as e:
    try:
        # 尝试从绝对路径导入
        import importlib.util
        funding_reader_path = bigdata_plan_abs / "src" / "utils" / "funding_rate_reader.py"
        if funding_reader_path.exists():
            # 临时添加bigdata_plan到sys.path
            if str(bigdata_plan_abs) not in sys.path:
                sys.path.insert(0, str(bigdata_plan_abs))
            
            # 先导入依赖模块
            try:
                # 导入const
                const_path = bigdata_plan_abs / "src" / "const.py"
                if const_path.exists():
                    const_spec = importlib.util.spec_from_file_location("src.const", const_path)
                    const_module = importlib.util.module_from_spec(const_spec)
                    const_spec.loader.exec_module(const_module)
                    # 将const模块添加到sys.modules，以便funding_rate_reader可以导入
                    if 'src' not in sys.modules:
                        import types
                        sys.modules['src'] = types.ModuleType('src')
                    if 'src.utils' not in sys.modules:
                        import types
                        sys.modules['src.utils'] = types.ModuleType('src.utils')
                    sys.modules['src.const'] = const_module
                
                # 导入zip_validator
                zip_validator_path = bigdata_plan_abs / "src" / "utils" / "zip_validator.py"
                if zip_validator_path.exists():
                    zip_validator_spec = importlib.util.spec_from_file_location("src.utils.zip_validator", zip_validator_path)
                    zip_validator_module = importlib.util.module_from_spec(zip_validator_spec)
                    zip_validator_spec.loader.exec_module(zip_validator_module)
                    sys.modules['src.utils.zip_validator'] = zip_validator_module
            except Exception as dep_e:
                print(f"  ⚠️  依赖模块导入失败: {dep_e}")
            
            spec = importlib.util.spec_from_file_location("funding_rate_reader", funding_reader_path)
            funding_reader_module = importlib.util.module_from_spec(spec)
            # 设置模块的__file__属性，以便相对导入能工作
            funding_reader_module.__file__ = str(funding_reader_path)
            # 设置__package__属性
            funding_reader_module.__package__ = "src.utils"
            spec.loader.exec_module(funding_reader_module)
            FundingRateReader = funding_reader_module.FundingRateReader
            print(f"  ✅ FundingRateReader 导入成功（importlib导入）")
        else:
            print(f"  ⚠️  FundingRateReader文件不存在: {funding_reader_path}")
    except Exception as e2:
        print(f"  ⚠️  FundingRateReader导入失败: {e2}")
        import traceback
        traceback.print_exc()
# 支持相对导入和绝对导入
try:
    from .preprocessor import preprocess_aggtrades, merge_exchange_data, validate_data
except ImportError:
    # 如果相对导入失败，尝试绝对导入
    import sys
    from pathlib import Path
    project_root = Path(__file__).parent.parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    try:
        from src.data.preprocessor import preprocess_aggtrades, merge_exchange_data, validate_data
    except ImportError:
        # 如果绝对导入也失败，使用importlib
        import importlib.util
        preprocessor_path = project_root / "src" / "data" / "preprocessor.py"
        spec = importlib.util.spec_from_file_location("preprocessor", preprocessor_path)
        preprocessor_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(preprocessor_module)
        preprocess_aggtrades = preprocessor_module.preprocess_aggtrades
        merge_exchange_data = preprocessor_module.merge_exchange_data
        validate_data = preprocessor_module.validate_data


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
        
        # 初始化资金费率读取器
        if FundingRateReader is not None:
            self.funding_reader = FundingRateReader()
        else:
            self.funding_reader = None
    
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
    
    def prepare_funding_rate(
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime
    ) -> np.ndarray:
        """
        准备资金费率数据
        
        Args:
            symbol: 交易对符号，如 'BTCUSDT'
            start_date: 开始日期
            end_date: 结束日期
        
        Returns:
            资金费率numpy数组，格式: [[timestamp, funding_rate], ...]
        """
        if self.funding_reader is None:
            # 如果FundingRateReader不可用，返回空数组
            print(f"  ⚠️  FundingRateReader 未可用，返回空资金费率数据")
            return np.empty((0, 2), dtype=np.float64)
        
        # 读取资金费率数据
        print(f"  📂 资金费率数据目录: {self.funding_reader.BIGDATA_FUNDING_DIR}")
        print(f"  📂 资金费率数据目录 (tradis): {self.funding_reader.TRADIS_RAW_DIR}")
        
        df = self.funding_reader.read_funding_rate(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date
        )
        
        if df.empty:
            print(f"  ⚠️  未找到资金费率数据")
            return np.empty((0, 2), dtype=np.float64)
        
        # 输出加载的文件信息
        # 查找加载的文件
        bigdata_files = self.funding_reader._find_bigdata_files(symbol, start_date, end_date)
        tradis_files = self.funding_reader._find_tradis_files(symbol, start_date, end_date)
        
        print(f"  📁 找到 {len(bigdata_files)} 个 bigdata 文件:")
        for file_path, file_date in bigdata_files:
            print(f"     - {Path(file_path).name} ({file_date.strftime('%Y-%m')})")
        
        print(f"  📁 找到 {len(tradis_files)} 个 tradis 文件:")
        for file_path, file_date in tradis_files:
            print(f"     - {Path(file_path).name} ({file_date.strftime('%Y-%m-%d')})")
        
        print(f"  ✅ 成功加载 {len(df)} 条资金费率记录")
        
        # 转换为numpy数组：timestamp, funding_rate
        funding_array = df[['funding_time', 'funding_rate']].values.astype(np.float64)
        
        return funding_array
    
    def close(self):
        """关闭数据读取器"""
        if self.reader is not None:
            self.reader.close()

