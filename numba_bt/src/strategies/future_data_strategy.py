"""未来数据测试策略：使用未来30秒的价格方向进行挂单"""
import numpy as np
from typing import Dict, Any, Optional
from pathlib import Path
import sys
import importlib.util

# 支持相对导入和绝对导入
try:
    from .base_strategy import BaseStrategy
except ImportError:
    project_root = Path(__file__).parent.parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    try:
        from src.strategies.base_strategy import BaseStrategy
    except ImportError:
        base_strategy_path = project_root / "src" / "strategies" / "base_strategy.py"
        spec = importlib.util.spec_from_file_location("base_strategy", base_strategy_path)
        base_strategy_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(base_strategy_module)
        BaseStrategy = base_strategy_module.BaseStrategy

try:
    from ..core.backtest_future_data import _run_backtest_future_data_numba, _calculate_future_30s_returns
except ImportError:
    try:
        from src.core.backtest_future_data import _run_backtest_future_data_numba, _calculate_future_30s_returns
    except ImportError:
        backtest_path = Path(__file__).parent.parent / "core" / "backtest_future_data.py"
        spec = importlib.util.spec_from_file_location("backtest_future_data", backtest_path)
        backtest_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(backtest_module)
        _run_backtest_future_data_numba = backtest_module._run_backtest_future_data_numba
        _calculate_future_30s_returns = backtest_module._calculate_future_30s_returns


class FutureDataStrategy(BaseStrategy):
    """未来数据测试策略：使用未来30秒的价格方向进行挂单"""
    
    def __init__(
        self,
        return_percentile_20: float = 0.0,
        return_percentile_80: float = 0.0,
        spread_median: float = 0.0,
        order_size: float = 100.0,
        price_update_threshold: float = 0.002,
        min_spread_pct: float = 0.002,
        hedge_threshold_pct: float = 0.8,
        stop_loss_pct: float = 0.1,
        params: Optional[Dict[str, Any]] = None,
        params_file: Optional[Path] = None
    ):
        """
        初始化未来数据测试策略
        
        这个策略使用未来30秒的价格方向来决定挂单，模拟完美预测
        用于测试：如果策略能够完美预测未来价格方向，是否能盈利
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
                name="FutureData",
                description="未来数据测试策略：使用未来30秒的价格方向进行挂单（模拟完美预测）",
                params=filtered_params,
                params_file=params_file
            )
            self.full_params = params
        else:
            super().__init__(
                name="FutureData",
                description="未来数据测试策略：使用未来30秒的价格方向进行挂单（模拟完美预测）",
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
        """预处理数据（按时间戳排序）"""
        if len(data) > 0:
            sorted_indices = np.argsort(data[:, 0])
            return data[sorted_indices]
        return data
    
    def run_backtest(self, data: np.ndarray) -> Dict[str, Any]:
        """执行回测（使用未来数据）"""
        processed_data = self.preprocess_data(data)
        
        if len(processed_data) == 0:
            raise ValueError("输入数据为空")
        
        # 预先计算所有未来30秒的return
        print("正在计算未来30秒return...")
        future_30s_returns = _calculate_future_30s_returns(processed_data)
        print(f"✅ 未来30秒return计算完成，共 {len(future_30s_returns)} 个值")
        
        # 准备资金费率数据
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
        
        print("开始执行未来数据策略回测（模拟完美预测）...")
        accounts_count, stats_count = _run_backtest_future_data_numba(
            processed_data,
            future_30s_returns,
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
            "strategy_state": self.strategy_state,
            "future_30s_returns": future_30s_returns  # 保存未来return用于分析
        }

