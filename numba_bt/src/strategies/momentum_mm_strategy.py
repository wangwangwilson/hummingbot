"""基于30s return动量的做市策略"""
import numpy as np
from typing import Dict, Any, Optional, Tuple
from pathlib import Path
from datetime import datetime, timezone

# 支持相对导入和绝对导入
try:
    from .base_strategy import BaseStrategy
except ImportError:
    # 如果相对导入失败，尝试绝对导入
    import sys
    from pathlib import Path
    project_root = Path(__file__).parent.parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    try:
        from src.strategies.base_strategy import BaseStrategy
    except ImportError:
        # 如果绝对导入也失败，使用importlib
        import importlib.util
        base_strategy_path = project_root / "src" / "strategies" / "base_strategy.py"
        spec = importlib.util.spec_from_file_location("base_strategy", base_strategy_path)
        base_strategy_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(base_strategy_module)
        BaseStrategy = base_strategy_module.BaseStrategy

try:
    from ..core.backtest_momentum_mm import _run_backtest_momentum_mm_numba
except ImportError:
    try:
        from src.core.backtest_momentum_mm import _run_backtest_momentum_mm_numba
    except ImportError:
        # 如果绝对导入也失败，使用importlib
        import importlib.util
        from pathlib import Path
        project_root = Path(__file__).parent.parent.parent
        backtest_momentum_mm_path = project_root / "src" / "core" / "backtest_momentum_mm.py"
        spec = importlib.util.spec_from_file_location("backtest_momentum_mm", backtest_momentum_mm_path)
        backtest_momentum_mm_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(backtest_momentum_mm_module)
        _run_backtest_momentum_mm_numba = backtest_momentum_mm_module._run_backtest_momentum_mm_numba

try:
    from ..analysis.statistics import analyze_performance
except ImportError:
    try:
        from src.analysis.statistics import analyze_performance
    except ImportError:
        # analyze_performance在run_backtest中不使用，可以忽略
        analyze_performance = None


class MomentumMMStrategy(BaseStrategy):
    """基于30s return动量的做市策略"""
    
    def __init__(
        self,
        return_percentile_20: float = 0.0,  # 30s return的20%分位数
        return_percentile_80: float = 0.0,  # 30s return的80%分位数
        spread_median: float = 0.0,  # spread中位数
        order_size: float = 100.0,  # 单笔挂单金额
        price_update_threshold: float = 0.001,  # 价格更新阈值（相对价格）
        params: Optional[Dict[str, Any]] = None,
        params_file: Optional[Path] = None
    ):
        """
        初始化动量做市策略
        
        Args:
            return_percentile_20: 30s return的20%分位数
            return_percentile_80: 30s return的80%分位数
            spread_median: spread中位数
            order_size: 单笔挂单金额
            price_update_threshold: 价格更新阈值（相对价格）
            params: 参数字典
            params_file: 参数文件路径
        """
        # 过滤掉策略特定参数
        if params is not None:
            backtester_params = {k: v for k, v in params.items() 
                               if k not in ['funding_rate_data', 'return_percentile_20', 'return_percentile_80', 
                                          'spread_median', 'order_size', 'price_update_threshold']}
            super().__init__(
                name="MomentumMM",
                description="基于30s return动量的做市策略",
                params=backtester_params,
                params_file=params_file
            )
            self.full_params = params
        else:
            super().__init__(
                name="MomentumMM",
                description="基于30s return动量的做市策略",
                params=params,
                params_file=params_file
            )
            self.full_params = params
        
        self.return_percentile_20 = return_percentile_20
        self.return_percentile_80 = return_percentile_80
        self.spread_median = spread_median
        self.order_size = order_size
        self.price_update_threshold = price_update_threshold
        
        self.strategy_state["return_percentile_20"] = self.return_percentile_20
        self.strategy_state["return_percentile_80"] = self.return_percentile_80
        self.strategy_state["spread_median"] = self.spread_median
        self.strategy_state["order_size"] = self.order_size
        self.strategy_state["price_update_threshold"] = self.price_update_threshold
    
    def preprocess_data(self, data: np.ndarray) -> np.ndarray:
        """预处理数据（如果需要）"""
        return data
    
    def run_backtest(self, data: np.ndarray) -> Dict[str, Any]:
        """
        执行回测
        
        使用自定义的动量做市策略回测函数
        """
        processed_data = self.preprocess_data(data)
        
        if processed_data.size == 0:
            raise ValueError("输入数据为空")
        
        # 准备资金费率数据（确保始终是2D数组）
        funding_rate_data_raw = self.full_params.get("funding_rate_data", [])
        if isinstance(funding_rate_data_raw, list):
            if len(funding_rate_data_raw) == 0:
                funding_rate_data = np.empty((0, 2), dtype=np.float64)
            else:
                funding_rate_data = np.array(funding_rate_data_raw, dtype=np.float64)
                # 确保是2D数组
                if len(funding_rate_data.shape) == 1:
                    funding_rate_data = funding_rate_data.reshape(-1, 2)
                elif len(funding_rate_data.shape) != 2 or funding_rate_data.shape[1] != 2:
                    funding_rate_data = np.empty((0, 2), dtype=np.float64)
        else:
            # 已经是numpy数组
            if funding_rate_data_raw.size == 0:
                funding_rate_data = np.empty((0, 2), dtype=np.float64)
            else:
                funding_rate_data = funding_rate_data_raw
                # 确保是2D数组
                if len(funding_rate_data.shape) == 1:
                    funding_rate_data = funding_rate_data.reshape(-1, 2)
                elif len(funding_rate_data.shape) != 2 or funding_rate_data.shape[1] != 2:
                    funding_rate_data = np.empty((0, 2), dtype=np.float64)
        
        # 获取参数
        exposure = self.params.get("exposure", 10000)
        target_pct = self.params.get("target_pct", 0.5)
        mini_price_step = self.params.get("mini_price_step", 0.0001)
        taker_fee_rate = self.params.get("taker_fee_rate", 0.00015)
        maker_fee_rate = self.params.get("maker_fee_rate", -0.00005)
        open_ratio = self.params.get("open_ratio", 0.5)
        initial_cash = self.params.get("initial_cash", 10000.0)
        initial_pos = self.params.get("initial_pos", 0.0)
        
        # 预分配结果数组
        accounts_log = np.zeros((len(processed_data) * 2, 10), dtype=np.float64)
        place_orders_stats_log = np.zeros((len(processed_data), 13), dtype=np.float64)
        
        print("开始执行动量做市策略回测...")
        accounts_count, stats_count = _run_backtest_momentum_mm_numba(
            processed_data,
            exposure,
            target_pct,
            mini_price_step,
            taker_fee_rate,
            maker_fee_rate,
            open_ratio,
            self.return_percentile_20,
            self.return_percentile_80,
            self.spread_median,
            self.order_size,
            self.price_update_threshold,
            initial_cash,
            initial_pos,
            accounts_log,
            place_orders_stats_log,
            funding_rate_data
        )
        print(f"回测完成。共记录 {accounts_count} 条账户变动，{stats_count} 条订单生命周期。")
        
        return {
            "accounts": accounts_log[:accounts_count],
            "place_orders_stats": place_orders_stats_log[:stats_count],
            "strategy_state": self.strategy_state
        }

