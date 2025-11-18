"""定时对冲策略：在指定UTC时间点将仓位对冲到0"""
import numpy as np
from typing import Dict, Any, Optional, List
from pathlib import Path
from datetime import datetime, timezone, timedelta

from .base_strategy import BaseStrategy
from ..core.backtest_with_hooks import _run_backtest_numba_with_hooks
from ..analysis.statistics import analyze_performance


class TimedHedgeStrategy(BaseStrategy):
    """定时对冲策略：在UTC时间的指定时刻（如8/16/0点）将仓位对冲到0"""
    
    def __init__(
        self,
        hedge_hours: List[int] = [0, 8, 16],  # UTC时间：0点、8点、16点
        params: Optional[Dict[str, Any]] = None,
        params_file: Optional[Path] = None
    ):
        """
        初始化定时对冲策略
        
        Args:
            hedge_hours: 对冲时间点（UTC小时），例如 [0, 8, 16] 表示每天0点、8点、16点
            params: 参数字典
            params_file: 参数文件路径
        """
        super().__init__(
            name="TimedHedge",
            description=f"定时对冲策略，在UTC时间 {hedge_hours} 点将仓位对冲到0",
            params=params,
            params_file=params_file
        )
        self.hedge_hours = sorted(hedge_hours)
        self.strategy_state["hedge_hours"] = self.hedge_hours
    
    def _calculate_hedge_timestamps(self, data: np.ndarray) -> np.ndarray:
        """
        计算对冲时间戳
        
        Args:
            data: 市场数据数组
        
        Returns:
            对冲时间戳数组（毫秒），按升序排列
        """
        if not data.size > 0:
            return np.array([], dtype=np.int64)
        
        start_ts = int(data[0, 0])
        end_ts = int(data[-1, 0])
        
        # 转换为datetime
        start_dt = datetime.fromtimestamp(start_ts / 1000, tz=timezone.utc)
        end_dt = datetime.fromtimestamp(end_ts / 1000, tz=timezone.utc)
        
        # 生成所有对冲时间点
        hedge_timestamps = []
        current_date = start_dt.date()
        end_date = end_dt.date()
        
        while current_date <= end_date:
            for hour in self.hedge_hours:
                hedge_dt = datetime.combine(current_date, datetime.min.time().replace(hour=hour), tzinfo=timezone.utc)
                hedge_ts = int(hedge_dt.timestamp() * 1000)
                
                # 只包含在数据时间范围内的
                if start_ts <= hedge_ts <= end_ts:
                    hedge_timestamps.append(hedge_ts)
            
            current_date += timedelta(days=1)
        
        if not hedge_timestamps:
            return np.array([-1], dtype=np.int64)  # 禁用对冲
        
        return np.array(sorted(set(hedge_timestamps)), dtype=np.int64)
    
    def preprocess_data(self, data: np.ndarray) -> np.ndarray:
        """预处理数据"""
        return data
    
    def run_backtest(self, data: np.ndarray) -> Dict[str, Any]:
        """
        执行回测（使用带扩展点的回测引擎）
        
        Args:
            data: 市场数据数组
        
        Returns:
            回测结果字典
        """
        processed_data = self.preprocess_data(data)
        
        # 计算对冲时间戳
        hedge_timestamps = self._calculate_hedge_timestamps(processed_data)
        
        print(f"定时对冲策略：共 {len(hedge_timestamps)} 个对冲时间点")
        if len(hedge_timestamps) > 0 and hedge_timestamps[0] >= 0:
            for i, ts in enumerate(hedge_timestamps[:5]):  # 只显示前5个
                dt = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
                print(f"  对冲时间点 {i+1}: {dt.strftime('%Y-%m-%d %H:%M:%S UTC')}")
            if len(hedge_timestamps) > 5:
                print(f"  ... 还有 {len(hedge_timestamps) - 5} 个时间点")
        
        # 准备回测参数（合并默认参数）
        from ..utils.params_manager import ParamsManager
        default_params = ParamsManager.get_default_mm_params()
        params = {**default_params, **self.params}  # 用户参数覆盖默认参数
        mini_price_step = params.get("mini_price_step")
        if mini_price_step is None:
            market_prices = processed_data[processed_data[:, 4] != 0, 2]
            if market_prices.size > 0:
                mini_price_step = market_prices[0] * 1e-4
            else:
                mini_price_step = 0.01
        
        # 预分配结果数组
        accounts_log = np.zeros((len(processed_data) * 3, 10), dtype=np.float64)
        place_orders_stats_log = np.zeros((len(processed_data), 13), dtype=np.float64)
        
        print("开始执行Numba加速的回测循环（带定时对冲）...")
        
        # 调用带扩展点的回测函数
        accounts_count, stats_count = _run_backtest_numba_with_hooks(
            processed_data,
            params["exposure"], params["target_pct"],
            params["buy_place_grid_step_value"], params["sell_place_grid_step_value"],
            params["buy_maker_place_thred_pct"], params["sell_maker_place_thred_pct"],
            params["buy_revoke_grid_step_value_pct"], params["sell_revoke_grid_step_value_pct"],
            params["sp_taker_value_thred_pct"], params["sp_taker_pct"], params["const_taker_step_size"],
            params["enable_price_step_maker"], params["enable_AS_adjust"], params["AS_MODEL"],
            params["adjust_maker_step_num_max"], params["const_maker_step_num"],
            params["enable_cost_price_lock"], params["adj_price_step_thred"],
            params["sp_pct"], params["sp_pct_grid_step"], mini_price_step,
            params["taker_fee_rate"], params["maker_fee_rate"], params["open_ratio"],
            params["enable_spl_taker"],
            params["initial_cash"], params["initial_pos"],
            accounts_log, place_orders_stats_log,
            hedge_timestamps
        )
        
        print("回测循环执行完毕。")
        
        # 截取有效数据
        accounts = accounts_log[:accounts_count]
        place_orders_stats = place_orders_stats_log[:stats_count]
        
        # 更新回测器状态（用于兼容性）
        self.backtester.accounts = accounts
        self.backtester.place_orders_stats = place_orders_stats
        
        print(f"回测完成。共记录 {accounts_count} 条账户变动，{stats_count} 条订单生命周期。")
        
        # 性能分析
        performance = analyze_performance(
            accounts_raw=accounts,
            place_orders_stats_raw=place_orders_stats
        )
        
        # 统计对冲次数
        hedge_count = len(hedge_timestamps) if len(hedge_timestamps) > 0 and hedge_timestamps[0] >= 0 else 0
        performance["hedge_info"] = {
            "hedge_hours": self.hedge_hours,
            "hedge_timestamps_count": hedge_count,
            "hedge_timestamps": hedge_timestamps.tolist() if hedge_count > 0 else []
        }
        
        return {
            "strategy_name": self.name,
            "accounts": accounts,
            "place_orders_stats": place_orders_stats,
            "performance": performance
        }

