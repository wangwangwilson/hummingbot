"""优化版本的基于30s return动量的做市策略"""
import numpy as np
from typing import Dict, Any, Optional, Tuple
from pathlib import Path
from datetime import datetime, timezone

# 支持相对导入和绝对导入
try:
    from .base_strategy import BaseStrategy
except ImportError:
    import sys
    from pathlib import Path
    project_root = Path(__file__).parent.parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    try:
        from src.strategies.base_strategy import BaseStrategy
    except ImportError:
        import importlib.util
        base_strategy_path = project_root / "src" / "strategies" / "base_strategy.py"
        spec = importlib.util.spec_from_file_location("base_strategy", base_strategy_path)
        base_strategy_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(base_strategy_module)
        BaseStrategy = base_strategy_module.BaseStrategy

try:
    from ..core.backtest_momentum_mm_optimized import _run_backtest_momentum_mm_optimized_numba
except ImportError:
    try:
        from src.core.backtest_momentum_mm_optimized import _run_backtest_momentum_mm_optimized_numba
    except ImportError:
        import importlib.util
        from pathlib import Path
        project_root = Path(__file__).parent.parent.parent
        backtest_path = project_root / "src" / "core" / "backtest_momentum_mm_optimized.py"
        spec = importlib.util.spec_from_file_location("backtest_momentum_mm_optimized", backtest_path)
        backtest_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(backtest_module)
        _run_backtest_momentum_mm_optimized_numba = backtest_module._run_backtest_momentum_mm_optimized_numba

try:
    from ..analysis.statistics import analyze_performance
except ImportError:
    try:
        from src.analysis.statistics import analyze_performance
    except ImportError:
        analyze_performance = None


class MomentumMMOptimizedStrategy(BaseStrategy):
    """优化版本的基于30s return动量的做市策略"""
    
    def __init__(
        self,
        return_percentile_20: float = 0.0,
        return_percentile_80: float = 0.0,
        spread_median: float = 0.0,
        order_size: float = 100.0,
        price_update_threshold: float = 0.002,  # 增加默认阈值
        min_spread_pct: float = 0.002,  # 最小spread 0.2%
        hedge_threshold_pct: float = 0.8,  # 对冲阈值 80%
        stop_loss_pct: float = 0.1,  # 止损 10%
        params: Optional[Dict[str, Any]] = None,
        params_file: Optional[Path] = None
    ):
        """
        初始化优化版本的动量做市策略
        
        Args:
            return_percentile_20: 30s return的20%分位数
            return_percentile_80: 30s return的80%分位数
            spread_median: spread中位数
            order_size: 单笔挂单金额
            price_update_threshold: 价格更新阈值（相对价格）
            min_spread_pct: 最小spread百分比（至少0.2%）
            hedge_threshold_pct: 对冲阈值（0.8表示当仓位超过exposure*0.8时开始对冲）
            stop_loss_pct: 止损百分比（0.1表示单笔亏损超过exposure*0.1时止损）
            params: 参数字典
            params_file: 参数文件路径
        """
        # 过滤掉策略特定参数
        if params is not None:
            strategy_specific_params = {
                'return_percentile_20', 'return_percentile_80', 'spread_median',
                'order_size', 'price_update_threshold', 'min_spread_pct',
                'hedge_threshold_pct', 'stop_loss_pct', 'funding_rate_data'
            }
            filtered_params = {k: v for k, v in params.items() 
                             if k not in strategy_specific_params}
            super().__init__(
                name="MomentumMMOptimized",
                description="优化版本的基于30s return动量的做市策略（反向挂单、增加spread、改进仓位控制、止损）",
                params=filtered_params,
                params_file=params_file
            )
            self.full_params = params
        else:
            super().__init__(
                name="MomentumMMOptimized",
                description="优化版本的基于30s return动量的做市策略（反向挂单、增加spread、改进仓位控制、止损）",
                params=params,
                params_file=params_file
            )
            self.full_params = self.params
        
        # 策略特定参数
        self.return_percentile_20 = return_percentile_20
        self.return_percentile_80 = return_percentile_80
        self.spread_median = spread_median
        self.order_size = order_size
        self.price_update_threshold = price_update_threshold
        self.min_spread_pct = min_spread_pct
        self.hedge_threshold_pct = hedge_threshold_pct
        self.stop_loss_pct = stop_loss_pct
        
        # 从params中获取（如果提供）
        if self.full_params:
            self.return_percentile_20 = self.full_params.get('return_percentile_20', return_percentile_20)
            self.return_percentile_80 = self.full_params.get('return_percentile_80', return_percentile_80)
            self.spread_median = self.full_params.get('spread_median', spread_median)
            self.order_size = self.full_params.get('order_size', order_size)
            self.price_update_threshold = self.full_params.get('price_update_threshold', price_update_threshold)
            self.min_spread_pct = self.full_params.get('min_spread_pct', min_spread_pct)
            self.hedge_threshold_pct = self.full_params.get('hedge_threshold_pct', hedge_threshold_pct)
            self.stop_loss_pct = self.full_params.get('stop_loss_pct', stop_loss_pct)
        
        # 策略状态
        self.strategy_state = {
            "return_percentile_20": self.return_percentile_20,
            "return_percentile_80": self.return_percentile_80,
            "spread_median": self.spread_median,
            "order_size": self.order_size,
            "price_update_threshold": self.price_update_threshold,
            "min_spread_pct": self.min_spread_pct,
            "hedge_threshold_pct": self.hedge_threshold_pct,
            "stop_loss_pct": self.stop_loss_pct
        }
    
    def preprocess_data(self, data: np.ndarray) -> np.ndarray:
        """预处理数据（策略特定的数据转换）"""
        # 按时间戳排序
        if len(data) > 0:
            sorted_indices = np.argsort(data[:, 0])
            return data[sorted_indices]
        return data
    
    def run_backtest(self, data: np.ndarray) -> Dict[str, Any]:
        """执行回测（策略特定的回测逻辑）"""
        processed_data = self.preprocess_data(data)
        
        if len(processed_data) == 0:
            raise ValueError("输入数据为空")
        
        # 准备资金费率数据（确保始终是2D数组）
        funding_rate_data_raw = self.full_params.get("funding_rate_data", [])
        if isinstance(funding_rate_data_raw, list):
            if len(funding_rate_data_raw) == 0:
                funding_rate_data = np.empty((0, 2), dtype=np.float64)
            else:
                funding_rate_data = np.array(funding_rate_data_raw, dtype=np.float64)
                if len(funding_rate_data.shape) == 1:
                    funding_rate_data = funding_rate_data.reshape(-1, 2)
                elif len(funding_rate_data.shape) != 2 or funding_rate_data.shape[1] != 2:
                    funding_rate_data = np.empty((0, 2), dtype=np.float64)
        else:
            if funding_rate_data_raw.size == 0:
                funding_rate_data = np.empty((0, 2), dtype=np.float64)
            else:
                funding_rate_data = funding_rate_data_raw
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
        
        print("开始执行优化版本的动量做市策略回测...")
        accounts_count, stats_count = _run_backtest_momentum_mm_optimized_numba(
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
            self.min_spread_pct,
            self.hedge_threshold_pct,
            self.stop_loss_pct,
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

