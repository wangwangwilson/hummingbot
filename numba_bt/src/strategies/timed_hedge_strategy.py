"""定时对冲策略：在指定UTC时间点将仓位对冲到0"""
import numpy as np
from typing import Dict, Any, Optional, List, Tuple
from pathlib import Path
from datetime import datetime, timezone, timedelta

from .base_strategy import BaseStrategy
from ..core.backtest import _run_backtest_numba
from ..analysis.statistics import analyze_performance


class TimedHedgeStrategy(BaseStrategy):
    """定时对冲策略：在指定时间点将仓位对冲到目标比例"""
    
    def __init__(
        self,
        hedge_hours: List[int] = [0, 8, 16],  # UTC时间：0点、8点、16点，或UTC+8时间
        hedge_target_ratio: float = 0.0,  # 对冲目标比例，0表示对冲到0，0.2表示对冲到20%仓位
        timezone_offset: int = 8,  # 时区偏移（小时），默认8表示UTC+8，0表示UTC
        hedge_interval_hours: Optional[int] = None,  # 对冲间隔（小时），例如2表示每2小时对冲一次
        params: Optional[Dict[str, Any]] = None,
        params_file: Optional[Path] = None
    ):
        """
        初始化定时对冲策略
        
        Args:
            hedge_hours: 对冲时间点（小时），例如 [0, 8, 16] 表示每天0点、8点、16点
            hedge_target_ratio: 对冲目标比例，0表示对冲到0，0.2表示对冲到20%仓位（带符号）
            timezone_offset: 时区偏移（小时），0表示UTC，8表示UTC+8
            hedge_interval_hours: 对冲间隔（小时），例如2表示每2小时对冲一次（1,3,5,7...23）
            params: 参数字典
            params_file: 参数文件路径
        """
        # 过滤掉策略特定参数，只保留回测器需要的参数
        if params is not None:
            # 复制params，移除策略特定参数
            backtester_params = {k: v for k, v in params.items() 
                               if k not in ['funding_rate_data', 'hedge_target_ratio', 'timezone_offset', 'hedge_interval_hours', 'hedge_hours']}
            # 使用过滤后的参数初始化基类
            super().__init__(
                name="TimedHedge",
                description=f"定时对冲策略，在时间 {hedge_hours} 点将仓位对冲到{hedge_target_ratio*100}%",
                params=backtester_params,  # 使用过滤后的参数
                params_file=params_file
            )
            # 保存完整的params用于策略逻辑
            self.full_params = params
        else:
            super().__init__(
                name="TimedHedge",
                description=f"定时对冲策略，在时间 {hedge_hours} 点将仓位对冲到{hedge_target_ratio*100}%",
                params=params,
                params_file=params_file
            )
            self.full_params = params
        
        self.hedge_hours = sorted(hedge_hours) if hedge_hours else []
        self.hedge_target_ratio = hedge_target_ratio
        self.timezone_offset = timezone_offset
        self.hedge_interval_hours = hedge_interval_hours
        self.strategy_state["hedge_hours"] = self.hedge_hours
        self.strategy_state["hedge_target_ratio"] = self.hedge_target_ratio
        self.strategy_state["timezone_offset"] = self.timezone_offset
        self.strategy_state["hedge_interval_hours"] = self.hedge_interval_hours
    
    def _calculate_hedge_timestamps(self, data: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """
        计算对冲时间戳和目标比例
        
        Args:
            data: 市场数据数组
        
        Returns:
            (对冲时间戳数组, 对冲目标比例数组)，按升序排列
        """
        if not data.size > 0:
            return np.array([], dtype=np.int64), np.array([], dtype=np.float64)
        
        start_ts = int(data[0, 0])
        end_ts = int(data[-1, 0])
        
        # 转换为datetime（考虑时区偏移）
        start_dt_utc = datetime.fromtimestamp(start_ts / 1000, tz=timezone.utc)
        end_dt_utc = datetime.fromtimestamp(end_ts / 1000, tz=timezone.utc)
        
        # 转换为目标时区
        target_tz = timezone(timedelta(hours=self.timezone_offset))
        start_dt = start_dt_utc.astimezone(target_tz)
        end_dt = end_dt_utc.astimezone(target_tz)
        
        # 生成所有对冲时间点
        hedge_timestamps = []
        hedge_target_ratios = []
        
        # 如果指定了对冲间隔，生成间隔时间点
        if self.hedge_interval_hours is not None and self.hedge_interval_hours > 0:
            current_dt = start_dt.replace(minute=0, second=0, microsecond=0)
            # 找到第一个对冲时间点
            first_hour = current_dt.hour
            # 找到下一个间隔时间点
            next_hour = ((first_hour // self.hedge_interval_hours) + 1) * self.hedge_interval_hours
            if next_hour >= 24:
                next_hour = next_hour % 24
                current_dt = current_dt + timedelta(days=1)
            current_dt = current_dt.replace(hour=next_hour)
            
            while current_dt <= end_dt:
                # 转换为UTC时间戳
                hedge_dt_utc = current_dt.astimezone(timezone.utc)
                hedge_ts = int(hedge_dt_utc.timestamp() * 1000)
                
                if start_ts <= hedge_ts <= end_ts:
                    hedge_timestamps.append(hedge_ts)
                    hedge_target_ratios.append(self.hedge_target_ratio)
                
                # 增加间隔
                current_dt = current_dt + timedelta(hours=self.hedge_interval_hours)
        else:
            # 使用指定的对冲时间点
            current_date = start_dt.date()
            end_date = end_dt.date()
            
            while current_date <= end_date:
                for hour in self.hedge_hours:
                    hedge_dt = datetime.combine(current_date, datetime.min.time().replace(hour=hour), tzinfo=target_tz)
                    hedge_dt_utc = hedge_dt.astimezone(timezone.utc)
                    hedge_ts = int(hedge_dt_utc.timestamp() * 1000)
                    
                    # 只包含在数据时间范围内的
                    if start_ts <= hedge_ts <= end_ts:
                        hedge_timestamps.append(hedge_ts)
                        hedge_target_ratios.append(self.hedge_target_ratio)
                
                current_date += timedelta(days=1)
        
        if not hedge_timestamps:
            return np.array([-1], dtype=np.int64), np.array([0.0], dtype=np.float64)  # 禁用对冲
        
        # 排序并去重
        sorted_indices = np.argsort(hedge_timestamps)
        hedge_timestamps = np.array(hedge_timestamps)[sorted_indices]
        hedge_target_ratios = np.array(hedge_target_ratios)[sorted_indices]
        
        return hedge_timestamps, hedge_target_ratios
    
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
        
        # 计算对冲时间戳和目标比例
        hedge_timestamps, hedge_target_ratios = self._calculate_hedge_timestamps(processed_data)
        
        print(f"定时对冲策略：共 {len(hedge_timestamps)} 个对冲时间点，目标比例: {self.hedge_target_ratio*100}%")
        if len(hedge_timestamps) > 0 and hedge_timestamps[0] >= 0:
            for i, ts in enumerate(hedge_timestamps[:5]):  # 只显示前5个
                dt = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
                target_ratio = hedge_target_ratios[i] if i < len(hedge_target_ratios) else self.hedge_target_ratio
                print(f"  对冲时间点 {i+1}: {dt.strftime('%Y-%m-%d %H:%M:%S UTC')}, 目标比例: {target_ratio*100}%")
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
        
        # 准备资金费率数据（如果提供）
        funding_rate_data = self.params.get("funding_rate_data", np.array([]).reshape(0, 2))
        if isinstance(funding_rate_data, list):
            funding_rate_data = np.array(funding_rate_data, dtype=np.float64)
        elif funding_rate_data.size == 0:
            funding_rate_data = np.array([]).reshape(0, 2)
        
        # 调用带扩展点的回测函数
        accounts_count, stats_count = _run_backtest_numba(
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
            hedge_timestamps,
            hedge_target_ratios,
            funding_rate_data
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
            "hedge_timestamps_count": int(hedge_count),
            "hedge_timestamps": [int(ts) for ts in hedge_timestamps.tolist()] if hedge_count > 0 else []
        }
        
        return {
            "strategy_name": self.name,
            "accounts": accounts,
            "place_orders_stats": place_orders_stats,
            "performance": performance
        }

