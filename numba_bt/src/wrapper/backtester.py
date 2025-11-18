"""回测包装类，封装策略参数和执行逻辑"""
import numpy as np
from typing import Optional

from ..core.backtest import _run_backtest_numba


class MarketMakerBacktester:
    """
    做市策略回测框架。

    该类封装了做市策略的状态、参数和执行逻辑。
    通过调用 `run_backtest` 方法来执行回测。
    核心计算循环使用了 Numba JIT 加速。

    使用方法:
    1. 初始化类，传入策略参数。
    2. 调用 `run_backtest` 方法，传入市场数据。
    3. 从 `self.accounts` 和 `self.place_orders_stats` 获取回测结果。
    """
    def __init__(self,
                 # ---- 核心参数 ----
                 exposure=250e4, target_pct=0.5,
                 # ---- taker相关参数 ----
                 enable_spl_taker=True, sp_taker_value_thred_pct=2e-2, sp_taker_pct=1e-3, const_taker_step_size=1,
                 # ---- maker挂单参数 ----
                 buy_maker_place_thred_pct=0.7, sell_maker_place_thred_pct=0.7,
                 buy_place_grid_step_value=5000, sell_place_grid_step_value=5000,
                 buy_revoke_grid_step_value_pct=3e-3, sell_revoke_grid_step_value_pct=3e-3,
                 # ---- 价格调整策略 ----
                 enable_price_step_maker=True, enable_AS_adjust=True, AS_MODEL=0,
                 adjust_maker_step_num_max=200, const_maker_step_num=5, adj_price_step_thred=10,
                 enable_cost_price_lock=False, sp_pct=5e-4, sp_pct_grid_step=1e-4,
                 # ---- 交易设置 ----
                 taker_fee_rate=1.5e-4, maker_fee_rate=-0.5e-4, open_ratio=0.5,
                 # ---- 初始状态 ----
                 initial_cash=100e4, initial_pos=0.0,
                 # ---- 价格精度 ----
                 mini_price_step: Optional[float] = None
                 ):

        # 将所有参数保存为类的属性
        self.exposure = exposure
        self.target_pct = target_pct
        self.buy_place_grid_step_value = buy_place_grid_step_value
        self.sell_place_grid_step_value = sell_place_grid_step_value
        self.buy_maker_place_thred_pct = buy_maker_place_thred_pct
        self.sell_maker_place_thred_pct = sell_maker_place_thred_pct
        self.buy_revoke_grid_step_value_pct = buy_revoke_grid_step_value_pct
        self.sell_revoke_grid_step_value_pct = sell_revoke_grid_step_value_pct
        self.sp_taker_value_thred_pct = sp_taker_value_thred_pct
        self.sp_taker_pct = sp_taker_pct
        self.const_taker_step_size = const_taker_step_size
        self.enable_price_step_maker = enable_price_step_maker
        self.enable_AS_adjust = enable_AS_adjust
        self.AS_MODEL = AS_MODEL
        self.adjust_maker_step_num_max = adjust_maker_step_num_max
        self.const_maker_step_num = const_maker_step_num
        self.enable_cost_price_lock = enable_cost_price_lock
        self.adj_price_step_thred = adj_price_step_thred
        self.sp_pct = sp_pct
        self.sp_pct_grid_step = sp_pct_grid_step
        self.taker_fee_rate = taker_fee_rate
        self.maker_fee_rate = maker_fee_rate
        self.open_ratio = open_ratio
        self.enable_spl_taker = enable_spl_taker
        self.initial_cash = initial_cash
        self.initial_pos = initial_pos
        self.mini_price_step = mini_price_step
        
        # 回测结果
        self.accounts = None
        self.place_orders_stats = None
        

    def run_backtest(self, data_feed: np.ndarray):
        """
        执行回测。

        Args:
            data_feed (np.ndarray): 市场数据Numpy数组。
                                    结构: [timestamp, side, price, quantity, mm_flag]
        """
        if not isinstance(data_feed, np.ndarray):
            raise TypeError("输入数据必须是 NumPy 数组")
        
        if data_feed.size == 0:
            raise ValueError("输入数据为空")

        # 最小价格步长，如果未指定则从数据中推断
        if self.mini_price_step is None:
            # 从非市场数据（mm_flag=0）中获取价格，计算最小步长
            market_prices = data_feed[data_feed[:, 4] == 0, 2]
            if market_prices.size > 0:
                # 简单估算：取价格的小数位数
                sample_price = market_prices[0]
                # 假设最小步长为价格的0.0001倍（万分之一）
                self.mini_price_step = sample_price * 1e-4
            else:
                self.mini_price_step = 0.01  # 默认值

        # 预分配内存用于存储结果，大小为输入数据长度，这是一个安全的上限
        # 账户日志结构: [ts, cash, pos, avg_cost, price, qty, side, taker_fee, maker_fee, type]
        accounts_log = np.zeros((len(data_feed) * 2, 10), dtype=np.float64)
        # 订单统计结构: [init_ts, lifecycle, price, side, origin_vol, finish_vol, avg_price, init_price, info, revoke_cnt, adj_price_cnt, desc_volume_cnt, asc_volume_cnt]
        place_orders_stats_log = np.zeros((len(data_feed), 13), dtype=np.float64)

        print("开始执行Numba加速的回测循环...")
        # 调用Numba JIT函数
        accounts_count, stats_count = _run_backtest_numba(
            data_feed,
            self.exposure, self.target_pct, self.buy_place_grid_step_value, self.sell_place_grid_step_value,
            self.buy_maker_place_thred_pct, self.sell_maker_place_thred_pct,
            self.buy_revoke_grid_step_value_pct, self.sell_revoke_grid_step_value_pct,
            self.sp_taker_value_thred_pct, self.sp_taker_pct, self.const_taker_step_size,
            self.enable_price_step_maker, self.enable_AS_adjust, self.AS_MODEL, self.adjust_maker_step_num_max,
            self.const_maker_step_num, self.enable_cost_price_lock, self.adj_price_step_thred,
            self.sp_pct, self.sp_pct_grid_step, self.mini_price_step,
            self.taker_fee_rate, self.maker_fee_rate, self.open_ratio,
            self.enable_spl_taker,
            self.initial_cash, self.initial_pos,
            accounts_log, place_orders_stats_log
        )
        print("回测循环执行完毕。")

        # 截取有效数据部分
        self.accounts = accounts_log[:accounts_count]
        self.place_orders_stats = place_orders_stats_log[:stats_count]

        print(f"回测完成。共记录 {accounts_count} 条账户变动，{stats_count} 条订单生命周期。")

