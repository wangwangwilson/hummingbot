import polars as pl
import numpy as np
from datetime import datetime
import numpy as np
from numba import njit
from tqdm import tqdm

# 为了Numba兼容性，我们将字符串映射为整数
order_update_flag_map = {
    "finish": 0,
    "same_side_revoke": 1,
    "revoke_for_under_target_pos": 2,
    "desc_to_revoke": 3,
    "revoke_change_to_taker": 4,
}

order_type_map = {"taker": 1, "maker": 2}

@njit
def _run_backtest_numba(
    # ---- 数据 ----
    data_feed,
    # ---- 参数 ----
    exposure, 
    target_pct,
    buy_place_grid_step_value, 
    sell_place_grid_step_value,
    buy_maker_place_thred_pct, 
    sell_maker_place_thred_pct,
    buy_revoke_grid_step_value_pct, 
    sell_revoke_grid_step_value_pct,
    sp_taker_value_thred_pct, 
    sp_taker_pct, 
    const_taker_step_size,
    enable_price_step_maker, 
    enable_AS_adjust, 
    AS_MODEL, 
    adjust_maker_step_num_max,
    const_maker_step_num, 
    enable_cost_price_lock, 
    adj_price_step_thred,
    sp_pct, 
    sp_pct_grid_step, 
    mini_price_step,
    taker_fee_rate, 
    maker_fee_rate,
    
    open_ratio,
    enable_spl_taker,
    # ---- 初始状态 ----
    initial_cash, initial_pos,
    # ---- 预分配的结果数组 ----
    accounts_log, place_orders_stats_log
):
    """
    使用 Numba JIT 编译的核心回测循环。
    为了性能，此函数只使用 Numba 支持的类型（如 NumPy 数组和基本数据类型）。
    """
    # 内部状态变量
    cash = initial_cash
    pos = initial_pos
    avg_cost_price = 0.0
    taker_fee = 0.0
    maker_fee = 0.0
    target_pos_value = exposure * target_pct

    # 挂单状态
    # 使用一个 NumPy 数组代表当前挂单，和一个布尔标志位判断是否存在
    # 结构: [创建时间, 价格, 方向, 数量, 初始价格, 已成交量, 成交均价, 初始时间]
    now_place_order = np.zeros(8)
    is_order_active = False
    _adj_price_cnt = 0
    _desc_volume_cnt = 0
    _asc_volume_cnt = 0

    # 结果数组的索引
    accounts_idx = 0
    stats_idx = 0

    last_mark_price = data_feed[0, 2]

    for i in range(data_feed.shape[0]):
        line = data_feed[i]
        now_ts, order_side, trade_price, trade_quantity, mm_flag = line[0], line[1], line[2], line[3], line[4]

        # 1. 处理交易所的真实成交 (Taker Trade)
        if mm_flag:
            if pos * order_side < 0 and trade_quantity > abs(pos):
                avg_cost_price = trade_price
            elif pos * order_side >= 0:
                # 防止分母为0
                if (pos + order_side * trade_quantity) != 0:
                    avg_cost_price = (avg_cost_price * pos + order_side * trade_quantity * trade_price) / (pos + order_side * trade_quantity)
            
            pos += order_side * trade_quantity
            cash -= order_side * trade_quantity * trade_price

            # 记录账户变化
            accounts_log[accounts_idx] = [now_ts, cash, pos, avg_cost_price, trade_price, trade_quantity, order_side, taker_fee, maker_fee, 0]
            accounts_idx += 1
        else:
            last_mark_price = trade_price

        pos_value = pos * last_mark_price

        # 2. 检查并处理挂单的撮合 (Maker Trade)
        have_trade_match = False
        if is_order_active and not mm_flag and now_place_order[2] * order_side < 0:
            _place_order_price = now_place_order[1]
            _place_order_side = now_place_order[2]
            _cross_price = (_place_order_price - trade_price) * _place_order_side
            
            _trade_volume = 0.0
            # 判断是否满足成交条件
            if _cross_price > 0: # 价格穿过
                _trade_volume = min(now_place_order[3], trade_quantity)
            elif _cross_price == 0: # 价格正好
                _trade_volume = min(now_place_order[3], trade_quantity * open_ratio)

            if _trade_volume > 0:
                have_trade_match = True
                finish_volume = now_place_order[5] + _trade_volume
                avg_match_trade_price = (now_place_order[6] * now_place_order[5] + _place_order_price * _trade_volume) / finish_volume

                # 更新或移除挂单
                if _trade_volume == now_place_order[3]: # 挂单被完全成交
                    lifecycle_ms = now_ts - now_place_order[7]
                    place_origin_volume = now_place_order[5] + now_place_order[3]
                    place_orders_stats_log[stats_idx] = [now_place_order[7], lifecycle_ms, _place_order_price, _place_order_side, place_origin_volume, finish_volume, avg_match_trade_price, now_place_order[4], 0, 0, _adj_price_cnt, _desc_volume_cnt, _asc_volume_cnt]
                    stats_idx += 1
                    is_order_active = False
                    _adj_price_cnt, _desc_volume_cnt, _asc_volume_cnt = 0, 0, 0
                else: # 部分成交
                    now_place_order[3] -= _trade_volume # 减少剩余挂单量
                    now_place_order[5] = finish_volume   # 更新已成交量
                    now_place_order[6] = avg_match_trade_price # 更新成交均价

                # 更新仓位和资金
                if _place_order_side * pos >= 0:
                     if (pos + _place_order_side * _trade_volume) != 0:
                        avg_cost_price = (avg_cost_price * pos + _place_order_side * _trade_volume * _place_order_price) / (pos + _place_order_side * _trade_volume)
                else: # 反向单，可能平仓或反向开仓
                    if _trade_volume > abs(pos):
                        avg_cost_price = _place_order_price
                    # 其他情况，持仓成本不变

                pos += _place_order_side * _trade_volume
                order_value = _trade_volume * _place_order_price
                cash -= _place_order_side * order_value
                maker_fee -= maker_fee_rate * order_value
                accounts_log[accounts_idx] = [now_ts, cash, pos, avg_cost_price, _place_order_price, _trade_volume, _place_order_side, taker_fee, maker_fee, 2]
                accounts_idx += 1

        # 3. 策略逻辑：根据当前状态决定是否下单、撤单、改单
        place_taker_ddh_order = False
        ddh_order_side = 0
        ddh_order_volume = 0.0

        # 3.1 Taker下单逻辑 (止损/止盈)
        if pos_value > exposure + 500:
            ddh_order_side = -1
            ddh_order_volume = (pos_value - target_pos_value) / last_mark_price
            place_taker_ddh_order = True
        elif pos_value < -exposure - 500:
            ddh_order_side = 1
            ddh_order_volume = (abs(pos_value) - target_pos_value) / last_mark_price
            place_taker_ddh_order = True
        elif enable_spl_taker and abs(pos_value) > sp_taker_value_thred_pct * exposure and avg_cost_price > 0 and np.sign(pos) * (last_mark_price - avg_cost_price) / avg_cost_price > sp_taker_pct:
            ddh_order_side = -np.sign(pos)
            ddh_order_volume = abs(pos)
            place_taker_ddh_order = True

        if place_taker_ddh_order:
            if is_order_active:
                # 如果存在挂单，先撤单
                lifecycle_ms = now_ts - now_place_order[7]
                place_origin_volume = now_place_order[5] + now_place_order[3]
                place_orders_stats_log[stats_idx] = [now_place_order[7], lifecycle_ms, now_place_order[1], now_place_order[2], place_origin_volume, now_place_order[5], now_place_order[6], now_place_order[4], 4, 1, _adj_price_cnt, _desc_volume_cnt, _asc_volume_cnt]
                stats_idx += 1
                is_order_active = False
                _adj_price_cnt, _desc_volume_cnt, _asc_volume_cnt = 0, 0, 0

            _taker_price = last_mark_price + ddh_order_side * mini_price_step * const_taker_step_size
            pos += ddh_order_side * ddh_order_volume
            order_value = ddh_order_volume * _taker_price
            cash -= ddh_order_side * order_value
            taker_fee -= taker_fee_rate * order_value
            accounts_log[accounts_idx] = [now_ts, cash, pos, avg_cost_price, _taker_price, ddh_order_volume, ddh_order_side, taker_fee, maker_fee, 1]
            accounts_idx += 1
            continue # Taker下单后，本轮后续逻辑不再执行

        # 3.2 Maker单调整/撤销逻辑
        if is_order_active:
            # 如果成交后，仓位和挂单同向，则撤单
            if pos * now_place_order[2] > 0:
                lifecycle_ms = now_ts - now_place_order[7]
                place_origin_volume = now_place_order[5] + now_place_order[3]
                place_orders_stats_log[stats_idx] = [now_place_order[7], lifecycle_ms, now_place_order[1], now_place_order[2], place_origin_volume, now_place_order[5], now_place_order[6], now_place_order[4], 1, 1, _adj_price_cnt, _desc_volume_cnt, _asc_volume_cnt]
                stats_idx += 1
                is_order_active = False
                _adj_price_cnt, _desc_volume_cnt, _asc_volume_cnt = 0, 0, 0
            # 如果仓位敞口低于目标，撤单以重新决策
            elif abs(pos) * last_mark_price < target_pos_value:
                lifecycle_ms = now_ts - now_place_order[7]
                place_origin_volume = now_place_order[5] + now_place_order[3]
                place_orders_stats_log[stats_idx] = [now_place_order[7], lifecycle_ms, now_place_order[1], now_place_order[2], place_origin_volume, now_place_order[5], now_place_order[6], now_place_order[4], 2, 1, _adj_price_cnt, _desc_volume_cnt, _asc_volume_cnt]
                stats_idx += 1
                is_order_active = False
                _adj_price_cnt, _desc_volume_cnt, _asc_volume_cnt = 0, 0, 0
            # 根据仓位变化调整挂单量 (减少)
            elif abs(pos) < now_place_order[3]:
                _delta_volume = now_place_order[3] - abs(pos)
                revoke_thred = buy_revoke_grid_step_value_pct if now_place_order[2] > 0 else sell_revoke_grid_step_value_pct
                if _delta_volume * last_mark_price > revoke_thred * exposure:
                    _desc_volume_cnt += 1
                    _adj_new_volume = now_place_order[3] - _delta_volume
                    if _adj_new_volume > 0:
                        now_place_order[3] = _adj_new_volume
                    else:
                        lifecycle_ms = now_ts - now_place_order[7]
                        place_origin_volume = now_place_order[5] + now_place_order[3]
                        place_orders_stats_log[stats_idx] = [now_place_order[7], lifecycle_ms, now_place_order[1], now_place_order[2], place_origin_volume, now_place_order[5], now_place_order[6], now_place_order[4], 3, 1, _adj_price_cnt, _desc_volume_cnt, _asc_volume_cnt]
                        stats_idx += 1
                        is_order_active = False
            # 增加挂单量逻辑 (当前未实现，原逻辑复杂且可能引入问题，暂略)

            # 调整挂单价格
            if is_order_active:
                _lock_price = avg_cost_price if enable_cost_price_lock and avg_cost_price > 0 else last_mark_price
                if enable_price_step_maker:
                    if enable_AS_adjust:
                        _step = max(int((1 - abs(pos_value) / exposure) * adjust_maker_step_num_max), 1)
                    else:
                        _step = const_maker_step_num
                    _adj_limit_price = _lock_price - now_place_order[2] * mini_price_step * _step
                    _delta_price_step = (_adj_limit_price - now_place_order[1]) / mini_price_step
                    if abs(_delta_price_step) > adj_price_step_thred:
                        _adj_price_cnt += 1
                        now_place_order[0] = now_ts
                        now_place_order[1] = _adj_limit_price
                else:
                    _adj_limit_price = _lock_price * (1 - now_place_order[2] * sp_pct)
                    if now_place_order[1] > 0:
                         _adj_change_rate = (_adj_limit_price - now_place_order[1]) / now_place_order[1]
                         if abs(_adj_change_rate) > sp_pct_grid_step:
                            _adj_price_cnt += 1
                            now_place_order[0] = now_ts
                            now_place_order[1] = _adj_limit_price

        # 3.3 Maker 下新单逻辑
        else: # not is_order_active
            _place_maker_order = False
            if pos_value > sell_maker_place_thred_pct * exposure:
                ddh_order_side = -1
                ddh_order_volume = abs(pos_value - target_pos_value) / last_mark_price
                _place_maker_order = True
            elif pos_value < -buy_maker_place_thred_pct * exposure:
                ddh_order_side = 1
                ddh_order_volume = abs(abs(pos_value) - target_pos_value) / last_mark_price
                _place_maker_order = True

            if _place_maker_order:
                _lock_price = avg_cost_price if enable_cost_price_lock and avg_cost_price > 0 else last_mark_price
                limit_price = 0.0
                if enable_price_step_maker:
                    if enable_AS_adjust:
                        if AS_MODEL == 0:
                            _step = max(int((1 - abs(pos_value) / exposure) * adjust_maker_step_num_max), 1)
                    else:
                        _step = const_maker_step_num
                    limit_price = _lock_price - ddh_order_side * mini_price_step * _step
                else:
                    limit_price = _lock_price * (1 - ddh_order_side * sp_pct)
                
                # [创建时间, 价格, 方向, 数量, 初始价格, 已成交量, 成交均价, 初始时间]
                now_place_order = np.array([now_ts, limit_price, ddh_order_side, ddh_order_volume, limit_price, 0.0, 0.0, now_ts])
                is_order_active = True
                _adj_price_cnt, _desc_volume_cnt, _asc_volume_cnt = 0, 0, 0

    return accounts_idx, stats_idx


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
                 initial_cash=100e4, initial_pos=0.0
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
        # 回测结果
        self.accounts = None
        self.place_orders_stats = None
        

    def run_backtest(self, data_feed):
        """
        执行回测。

        Args:
            data_feed (np.ndarray): 市场数据Numpy数组。
                                    结构: [timestamp, side, price, quantity, mm_flag]
        """
        if not isinstance(data_feed, np.ndarray):
            raise TypeError("输入数据必须是 NumPy 数组")

        # 最小价格步长，这里假设从数据中获取，或设为固定值
        # match_trade_price = data_feed[data_feed[:, -1] == 0][0, 2]
        # mini_price_step = get_decimal_resolution(match_trade_price)
        mini_price_step = 0.01 # 假设一个固定的值

        # 预分配内存用于存储结果，大小为输入数据长度，这是一个安全的上限
        # 账户日志结构: [ts, cash, pos, avg_cost, price, qty, side, taker_fee, maker_fee, type]
        accounts_log = np.zeros((len(data_feed) * 1, 10))
        # 订单统计结构: [init_ts, lifecycle, price, side, origin_vol, finish_vol, avg_price, init_price, info, ...]
        place_orders_stats_log = np.zeros((len(data_feed), 13))

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
            self.sp_pct, self.sp_pct_grid_step, mini_price_step,
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


def analyze_ddh_maker_performance_np(accounts_raw: np.ndarray, place_orders_stats_raw: np.ndarray) -> dict:
    """
    使用NumPy和Polars实现的DDH Maker策略性能分析函数，大幅提升性能。
    
    Args:
        accounts_raw (np.ndarray): 账户状态数组
        place_orders_stats_raw (np.ndarray): 订单统计数组
        
    Returns:
        dict: 包含性能指标的字典
    """
    if accounts_raw.shape[0] == 0:
        # Handle empty accounts_raw gracefully
        return {
            'overall_performance': {
                'total_pnl_with_fees': 0.0, 'total_pnl_no_fees': 0.0,
                'pnl_with_fees_ratio': 0.0, 'pnl_no_fees_ratio': 0.0,
                'sharpe_ratio': np.nan, 'max_drawdown': 0.0,
                'calmar_ratio': np.nan, 'annualized_return': np.nan,
                'duration_years': 0.0
            },
            'maker_performance': {
                'total_maker_pnl_no_fees': 0.0, 'maker_volume_total': 0.0,
                'maker_pnl_ratio': 0.0, 'maker_pnl_pct_volume': 0.0,
                'actual_maker_fees_cost_rebate': 0.0
            },
            'taker_performance': {
                'total_taker_pnl_no_fees': 0.0, 'taker_volume_total': 0.0,
                'taker_pnl_ratio': 0.0, 'taker_pnl_pct_volume': 0.0,
                'actual_taker_fees_cost': 0.0
            },
            'fee_analysis': {
                'total_actual_fees': 0.0
            },
            'order_behavior_metrics': {
                'avg_fill_time_sec': np.nan, 'median_fill_time_sec': np.nan,
                'avg_fill_rate': np.nan, 'finish_all_pct': np.nan,
                'finish_hit_pct': np.nan, 'buy_orders': {}, 'sell_orders': {},
                'avg_slippage_pct': np.nan, 'total_slippage_value': 0.0,
                'buy_api_stats_1min': {}, 'sell_api_stats_1min': {},
                'api_calls_per_minute': { 'mean': 0.0, 'median': 0.0, 'max': 0.0, 'min': 0.0 }
            }
        }


    # 1. 提取账户数据各列
    now_ts = accounts_raw[:, 0]
    cash = accounts_raw[:, 1]
    pos = accounts_raw[:, 2]
    avg_cost_price = accounts_raw[:, 3]
    trade_price = accounts_raw[:, 4]
    trade_quantity = accounts_raw[:, 5]
    order_side = accounts_raw[:, 6]
    taker_fee = accounts_raw[:, 7]
    maker_fee = accounts_raw[:, 8]
    order_role = accounts_raw[:, 9]
    
    # 2. 基础计算
    pos_value = pos * trade_price
    equity_no_fee = cash + pos_value
    pnl_no_fee = np.diff(equity_no_fee, prepend=equity_no_fee[0])
    
    # 3. 计算虚拟平仓PnL
    prev_pos = np.roll(pos, 1)
    prev_pos[0] = 0
    close_ind = (prev_pos * order_side < 0) & (order_side != 0)
    prev_avg_cost_price = np.roll(avg_cost_price, 1)
    prev_avg_cost_price[0] = avg_cost_price[0] # The first avg_cost_price is correct as is
    virtual_close_pnl = np.where(
        close_ind,
        -(trade_price - prev_avg_cost_price) * order_side * trade_quantity,
        0.0
    )
    realized_pnl_no_fee = np.cumsum(virtual_close_pnl) # This is cumulative, not used in final output
    
    # 4. 计算含手续费的PnL
    total_fee_cum = taker_fee + maker_fee
    equity_with_fee = cash + pos_value + total_fee_cum
    pnl_with_fee = np.diff(equity_with_fee, prepend=equity_with_fee[0])
    
    # 5. 总体绩效指标
    total_trade_value = np.sum(trade_quantity * trade_price)
    total_pnl_with_fees = np.sum(pnl_with_fee)
    total_pnl_no_fees = np.sum(pnl_no_fee)
    
    # 修改命名并转换为万分之几的单位
    pnl_with_fees_ratio = (total_pnl_with_fees / total_trade_value * 10000 
                           if total_trade_value > 0 else 0.0)
    pnl_no_fees_ratio = (total_pnl_no_fees / total_trade_value * 10000 
                         if total_trade_value > 0 else 0.0)

    # 6. 计算最大回撤
    peak_equity = np.maximum.accumulate(equity_with_fee)
    drawdown_pct = np.where(peak_equity != 0, (equity_with_fee - peak_equity) / peak_equity, 0)
    max_drawdown = abs(np.min(drawdown_pct)) if drawdown_pct.size > 0 else 0.0
    
    # 7. 计算年化收益和卡玛比率
    t_min = now_ts[0]
    t_max = now_ts[-1]
    duration_years = (t_max - t_min) / (1000 * 3600 * 24 * 365.25)
    
    annualized_return = np.nan
    calmar_ratio = np.nan
    
    if duration_years > 0 and equity_with_fee[0] != 0:
        # Check for non-negative equity for meaningful return calculation
        if equity_with_fee[0] > 0 and equity_with_fee[-1] > 0:
            annualized_return = ((equity_with_fee[-1] / equity_with_fee[0]) ** (1 / duration_years)) - 1
        elif equity_with_fee[0] < 0 and equity_with_fee[-1] < 0: # If both are negative, handle with care or treat as NaN
            annualized_return = np.nan # Or a specific indicator for negative initial equity
        else: # Mixed signs, return undefined
            annualized_return = np.nan

        if not np.isnan(annualized_return) and max_drawdown > 0:
            calmar_ratio = annualized_return / max_drawdown
        elif not np.isnan(annualized_return) and annualized_return > 0 and max_drawdown == 0:
            calmar_ratio = np.inf
    
    # 8. 计算夏普比率 (使用日度数据)
    sharpe_ratio = np.nan
    
    # 将时间戳转换为天数，并获取每天的最后一个数据点
    timestamps_days = now_ts // (1000 * 3600 * 24)
    # Using np.unique with return_index to get the first occurrence of each day
    # Then we need to find the *last* occurrence for daily equity.
    # A more robust way to get last daily equity:
    if now_ts.size > 0:
        unique_days, last_indices = np.unique(timestamps_days, return_index=True)
        # To get the last equity, a robust method is needed. Let's correct this logic.
        # A simple approach for last daily equity:
        _, unique_indices_last = np.unique(timestamps_days[::-1], return_index=True)
        daily_equity_indices = (len(timestamps_days) - 1) - unique_indices_last
        daily_equity = equity_with_fee[np.sort(daily_equity_indices)]


        if daily_equity.size > 1:
            # 计算日收益率
            daily_returns = np.diff(daily_equity) / daily_equity[:-1]
            
            # 计算夏普比率 (假设无风险利率为0)
            if np.std(daily_returns) > 0:
                sharpe_ratio = np.mean(daily_returns) / np.std(daily_returns) * np.sqrt(252)
    
    # 9. Maker和Taker分析
    maker_mask = (order_role == 2)
    taker_mask = (order_role == 1)
    
    # Maker统计
    maker_pnl_no_fee = np.sum(virtual_close_pnl[maker_mask])
    maker_volume_array = trade_quantity[maker_mask] * trade_price[maker_mask]
    maker_volume = np.sum(maker_volume_array)
    
    maker_pnl_ratio = (maker_pnl_no_fee / maker_volume * 10000 
                       if maker_volume > 0 else 0.0)
    maker_pnl_pct_volume = (maker_pnl_no_fee / maker_volume 
                            if maker_volume > 0 else 0.0)
    actual_maker_fees = maker_fee[-1] if maker_fee.size > 0 else 0.0
    
    # Taker统计
    taker_pnl_no_fee = np.sum(virtual_close_pnl[taker_mask])
    taker_volume_array = trade_quantity[taker_mask] * trade_price[taker_mask]
    taker_volume = np.sum(taker_volume_array)
    
    taker_pnl_ratio = (taker_pnl_no_fee / taker_volume * 10000 
                       if taker_volume > 0 else 0.0)
    taker_pnl_pct_volume = (taker_pnl_no_fee / taker_volume 
                            if taker_volume > 0 else 0.0)
    actual_taker_fees = taker_fee[-1] if taker_fee.size > 0 else 0.0
    
    # 10. 订单行为分析
    order_behavior_metrics = {}
    
    if len(place_orders_stats_raw) > 0:
        # 提取订单数据各列
        init_place_ts = place_orders_stats_raw[:, 0]
        lifecycle_ms = place_orders_stats_raw[:, 1]
        last_limit_price = place_orders_stats_raw[:, 2] # Unused
        order_side_orders = place_orders_stats_raw[:, 3]
        place_origin_volume = place_orders_stats_raw[:, 4]
        finish_volume = place_orders_stats_raw[:, 5]
        avg_match_trade_price = place_orders_stats_raw[:, 6]
        init_place_order_price = place_orders_stats_raw[:, 7]
        info = place_orders_stats_raw[:, 8] # Unused
        
        # Explicitly ensure numerical type and flatness for count columns
        revoke_cnt_raw = np.array([x[0] if isinstance(x, (list, np.ndarray)) and len(x) > 0 else x for x in place_orders_stats_raw[:, 9]], dtype=np.int64)
        adj_price_cnt_raw = np.array([x[0] if isinstance(x, (list, np.ndarray)) and len(x) > 0 else x for x in place_orders_stats_raw[:, 10]], dtype=np.int64)
        desc_volume_cnt_raw = np.array([x[0] if isinstance(x, (list, np.ndarray)) and len(x) > 0 else x for x in place_orders_stats_raw[:, 11]], dtype=np.int64)
        asc_volume_cnt_raw = np.array([x[0] if isinstance(x, (list, np.ndarray)) and len(x) > 0 else x for x in place_orders_stats_raw[:, 12]], dtype=np.int64)

        # Calculate fill percentage safely
        finish_pct = np.divide(
            finish_volume, 
            place_origin_volume, 
            out=np.zeros_like(finish_volume, dtype=float), 
            where=place_origin_volume!=0
        )
        
        # Calculate price slippage percentage
        price_slippage_pct = np.zeros_like(finish_volume, dtype=float)
        valid_match_mask = (finish_volume > 0) & (avg_match_trade_price != 0)
        if np.any(valid_match_mask):
            price_slippage_pct[valid_match_mask] = order_side_orders[valid_match_mask] * (
                init_place_order_price[valid_match_mask] - avg_match_trade_price[valid_match_mask]
            ) / avg_match_trade_price[valid_match_mask]
        
        # Calculate price slippage value
        price_slippage_value = price_slippage_pct * finish_volume * avg_match_trade_price
        
        # Find orders that had any trade match
        have_trade_mask = finish_volume > 0
        
        if np.any(have_trade_mask):
            # Calculate mean/median only if there are trades
            avg_fill_time_sec = np.mean(lifecycle_ms[have_trade_mask]) / 1000
            median_fill_time_sec = np.median(lifecycle_ms[have_trade_mask]) / 1000
            avg_fill_rate = np.mean(finish_pct[have_trade_mask])
            
            # Percentage of fully filled and partially hit orders
            finish_all_mask = finish_pct > 0.9995
            finish_hit_mask = finish_pct > 0.0005
            
            total_trades_count = np.sum(have_trade_mask)
            finish_all_pct = np.sum(finish_all_mask & have_trade_mask) / total_trades_count if total_trades_count > 0 else np.nan
            finish_hit_pct = np.sum(finish_hit_mask & have_trade_mask) / total_trades_count if total_trades_count > 0 else np.nan
            
            # Buy/Sell orders trade statistics
            buy_orders_mask_trade = (order_side_orders == 1) & have_trade_mask
            sell_orders_mask_trade = (order_side_orders == -1) & have_trade_mask
            
            buy_orders = {}
            sell_orders = {}
            
            if np.any(buy_orders_mask_trade):
                buy_orders = {
                    'avg_fill_time_sec': np.mean(lifecycle_ms[buy_orders_mask_trade]) / 1000,
                    'median_fill_time_sec': np.median(lifecycle_ms[buy_orders_mask_trade]) / 1000,
                    'avg_fill_rate': np.mean(finish_pct[buy_orders_mask_trade]),
                    'avg_slippage_pct': np.mean(price_slippage_pct[buy_orders_mask_trade]),
                    'median_slippage_pct': np.median(price_slippage_pct[buy_orders_mask_trade]),
                    'total_slippage_value': np.sum(price_slippage_value[buy_orders_mask_trade]),
                    'order_count': np.sum(buy_orders_mask_trade)
                }
            
            if np.any(sell_orders_mask_trade):
                sell_orders = {
                    'avg_fill_time_sec': np.mean(lifecycle_ms[sell_orders_mask_trade]) / 1000,
                    'median_fill_time_sec': np.median(lifecycle_ms[sell_orders_mask_trade]) / 1000,
                    'avg_fill_rate': np.mean(finish_pct[sell_orders_mask_trade]),
                    'avg_slippage_pct': np.mean(price_slippage_pct[sell_orders_mask_trade]),
                    'median_slippage_pct': np.median(price_slippage_pct[sell_orders_mask_trade]),
                    'total_slippage_value': np.sum(price_slippage_value[sell_orders_mask_trade]),
                    'order_count': np.sum(sell_orders_mask_trade)
                }
            
            # Slippage statistics
            avg_slippage_pct = np.mean(price_slippage_pct[have_trade_mask])
            total_slippage_value = np.sum(price_slippage_value[have_trade_mask])
            
            # API Request Frequency Statistics
            # Convert timestamps to minutes
            minute_ts = init_place_ts // (60 * 1000)
            
            # Initialize empty Polars DataFrames for API stats
            buy_api_stats_df = pl.DataFrame()
            sell_api_stats_df = pl.DataFrame()
            api_calls_stats_df = pl.DataFrame()

            # Create Polars DataFrame for API data
            api_data = {
                'minute_ts': minute_ts.tolist(), # Polars likes lists for constructing DataFrames
                'order_side': order_side_orders.tolist(),
                'revoke_cnt': revoke_cnt_raw.tolist(), # These are now guaranteed 1D lists of ints
                'adj_price_cnt': adj_price_cnt_raw.tolist(),
                'desc_volume_cnt': desc_volume_cnt_raw.tolist(),
                'asc_volume_cnt': asc_volume_cnt_raw.tolist()
            }
            
            pl_df = pl.DataFrame(api_data).with_columns([
                pl.col('revoke_cnt').cast(pl.Int64),
                pl.col('adj_price_cnt').cast(pl.Int64),
                pl.col('desc_volume_cnt').cast(pl.Int64),
                pl.col('asc_volume_cnt').cast(pl.Int64)
            ])
            
            
            # Buy order API statistics
            if np.any(order_side_orders == 1):
                buy_api_stats_df = (
                    pl_df.filter(pl.col('order_side') == 1)
                    .group_by('minute_ts')
                    .agg([
                        pl.sum('revoke_cnt').alias('revoke_cnt'),
                        pl.sum('adj_price_cnt').alias('adj_price_cnt'),
                        pl.sum('desc_volume_cnt').alias('desc_volume_cnt'),
                        pl.sum('asc_volume_cnt').alias('asc_volume_cnt'),
                        pl.count('order_side').alias('order_count')
                    ])
                )
            
            buy_api_metrics = {}
            if buy_api_stats_df.shape[0] > 0:
                buy_api_metrics = {
                    'revoke_cnt': {
                        'mean': buy_api_stats_df['revoke_cnt'].mean(),
                        'median': buy_api_stats_df['revoke_cnt'].median(),
                        'max': buy_api_stats_df['revoke_cnt'].max()
                    },
                    'adj_price_cnt': {
                        'mean': buy_api_stats_df['adj_price_cnt'].mean(),
                        'median': buy_api_stats_df['adj_price_cnt'].median(),
                        'max': buy_api_stats_df['adj_price_cnt'].max()
                    },
                    'desc_volume_cnt': {
                        'mean': buy_api_stats_df['desc_volume_cnt'].mean(),
                        'median': buy_api_stats_df['desc_volume_cnt'].median(),
                        'max': buy_api_stats_df['desc_volume_cnt'].max()
                    },
                    'asc_volume_cnt': {
                        'mean': buy_api_stats_df['asc_volume_cnt'].mean(),
                        'median': buy_api_stats_df['asc_volume_cnt'].median(),
                        'max': buy_api_stats_df['asc_volume_cnt'].max()
                    },
                    'order_count_mean': buy_api_stats_df['order_count'].mean()
                }
            
            # Sell order API statistics
            if np.any(order_side_orders == -1):
                sell_api_stats_df = (
                    pl_df.filter(pl.col('order_side') == -1)
                    .group_by('minute_ts')
                    .agg([
                        pl.sum('revoke_cnt').alias('revoke_cnt'),
                        pl.sum('adj_price_cnt').alias('adj_price_cnt'),
                        pl.sum('desc_volume_cnt').alias('desc_volume_cnt'),
                        pl.sum('asc_volume_cnt').alias('asc_volume_cnt'),
                        pl.count('order_side').alias('order_count')
                    ])
                )
            
            sell_api_metrics = {}
            if sell_api_stats_df.shape[0] > 0:
                sell_api_metrics = {
                    'revoke_cnt': {
                        'mean': sell_api_stats_df['revoke_cnt'].mean(),
                        'median': sell_api_stats_df['revoke_cnt'].median(),
                        'max': sell_api_stats_df['revoke_cnt'].max()
                    },
                    'adj_price_cnt': {
                        'mean': sell_api_stats_df['adj_price_cnt'].mean(),
                        'median': sell_api_stats_df['adj_price_cnt'].median(),
                        'max': sell_api_stats_df['adj_price_cnt'].max()
                    },
                    'desc_volume_cnt': {
                        'mean': sell_api_stats_df['desc_volume_cnt'].mean(),
                        'median': sell_api_stats_df['desc_volume_cnt'].median(),
                        'max': sell_api_stats_df['desc_volume_cnt'].max()
                    },
                    'asc_volume_cnt': {
                        'mean': sell_api_stats_df['asc_volume_cnt'].mean(),
                        'median': sell_api_stats_df['asc_volume_cnt'].median(),
                        'max': sell_api_stats_df['asc_volume_cnt'].max()
                    },
                    'order_count_mean': sell_api_stats_df['order_count'].mean()
                }
            
            # === FIX IS HERE ===
            # Calculate total API calls per minute
            api_calls_stats_df = (
                pl_df.group_by('minute_ts')
                .agg([
                    (pl.sum('revoke_cnt') + pl.sum('adj_price_cnt') + 
                     pl.sum('desc_volume_cnt') + pl.sum('asc_volume_cnt')).alias('total_api_calls')
                ])
            )
            
            api_calls_values = api_calls_stats_df['total_api_calls'].to_numpy() if api_calls_stats_df.shape[0] > 0 else np.array([])
            
            api_calls_per_minute = {
                'mean': float(np.mean(api_calls_values)) if api_calls_values.size > 0 else 0.0,
                'median': float(np.median(api_calls_values)) if api_calls_values.size > 0 else 0.0,
                'max': float(np.max(api_calls_values)) if api_calls_values.size > 0 else 0.0,
                'min': float(np.min(api_calls_values)) if api_calls_values.size > 0 else 0.0
            }
        
            order_behavior_metrics = {
                'avg_fill_time_sec': float(avg_fill_time_sec),
                'median_fill_time_sec': float(median_fill_time_sec),
                'avg_fill_rate': float(avg_fill_rate),
                'finish_all_pct': float(finish_all_pct),
                'finish_hit_pct': float(finish_hit_pct),
                'buy_orders': buy_orders,
                'sell_orders': sell_orders,
                'avg_slippage_pct': float(avg_slippage_pct),
                'total_slippage_value': float(total_slippage_value),
                'buy_api_stats_1min': buy_api_metrics,
                'sell_api_stats_1min': sell_api_metrics,
                'api_calls_per_minute': api_calls_per_minute
            }
        else:
            # If no matched orders, set default values
            order_behavior_metrics = {
                'avg_fill_time_sec': np.nan,
                'median_fill_time_sec': np.nan,
                'avg_fill_rate': np.nan,
                'finish_all_pct': np.nan,
                'finish_hit_pct': np.nan,
                'buy_orders': {},
                'sell_orders': {},
                'avg_slippage_pct': np.nan,
                'total_slippage_value': 0.0,
                'buy_api_stats_1min': {},
                'sell_api_stats_1min': {},
                'api_calls_per_minute': { 'mean': 0.0, 'median': 0.0, 'max': 0.0, 'min': 0.0 }
            }
    else:
        # If no order data, set default values
        order_behavior_metrics = {
            'avg_fill_time_sec': np.nan,
            'median_fill_time_sec': np.nan,
            'avg_fill_rate': np.nan,
            'finish_all_pct': np.nan,
            'finish_hit_pct': np.nan,
            'buy_orders': {},
            'sell_orders': {},
            'avg_slippage_pct': np.nan,
            'total_slippage_value': 0.0,
            'buy_api_stats_1min': {},
            'sell_api_stats_1min': {},
            'api_calls_per_minute': { 'mean': 0.0, 'median': 0.0, 'max': 0.0, 'min': 0.0 }
        }
    
    # 11. 构建并返回结果字典
    return {
        'overall_performance': {
            'total_pnl_with_fees': float(total_pnl_with_fees),
            'total_pnl_no_fees': float(total_pnl_no_fees),
            'pnl_with_fees_ratio': float(pnl_with_fees_ratio),  # 万分之几
            'pnl_no_fees_ratio': float(pnl_no_fees_ratio),      # 万分之几
            'sharpe_ratio': float(sharpe_ratio),
            'max_drawdown': float(max_drawdown),
            'calmar_ratio': float(calmar_ratio),
            'annualized_return': float(annualized_return),
            'duration_years': float(duration_years)
        },
        'maker_performance': {
            'total_maker_pnl_no_fees': float(maker_pnl_no_fee),
            'maker_volume_total': float(maker_volume),
            'maker_pnl_ratio': float(maker_pnl_ratio),          # 万分之几
            'maker_pnl_pct_volume': float(maker_pnl_pct_volume),  # 兼容旧版
            'actual_maker_fees_cost_rebate': float(actual_maker_fees)
        },
        'taker_performance': {
            'total_taker_pnl_no_fees': float(taker_pnl_no_fee),
            'taker_volume_total': float(taker_volume),
            'taker_pnl_ratio': float(taker_pnl_ratio),          # 万分之几
            'taker_pnl_pct_volume': float(taker_pnl_pct_volume),  # 兼容旧版
            'actual_taker_fees_cost': float(actual_taker_fees)
        },
        'fee_analysis': {
            'total_actual_fees': float(total_fee_cum[-1]) if total_fee_cum.size > 0 else 0.0
        },
        'order_behavior_metrics': order_behavior_metrics
    }


def analyze_ddh_maker_performance(accounts_raw, place_orders_stats_raw):
    """
    分析 DDH Maker V3 策略的性能指标。

    Args:
        accounts_raw (list): 原始的 accounts 列表，包含每笔交易后的账户状态。
                             列顺序必须与函数内部定义的一致。
                             其中 'taker_fee' 和 'maker_fee'：
                             - 大于 0 代表返佣 (rebate)
                             - 小于 0 代表付出的手续费 (cost)
        place_orders_stats_raw (list): 原始的 place_orders_stats 列表，包含挂单生命周期信息。
                                       列顺序必须与函数内部定义的一致。

    Returns:
        dict: 包含所有计算出的 DataFrame 和性能指标的字典。
    """

    # --- 1. 初始化 DataFrame ---
    accounts_bt_df = pd.DataFrame(accounts_raw, columns=[
        'now_ts', 'cash', 'pos', 'avg_cost_price', 'trade_price',
        'trade_quantity', 'order_side', 'taker_fee', 'maker_fee', 'order_role'
    ])
    accounts_bt_df.index = pd.to_datetime(accounts_bt_df['now_ts'], unit='ms', utc=True)

    limit_orders_df = pd.DataFrame(place_orders_stats_raw, columns=[
        'init_place_ts', 'lifecycle_ms', 'last_limit_price', 'order_side',
        'place_origin_volume', 'finish_volume', 'avg_match_trade_price',
        'init_place_order_price', 'info', 'revoke_cnt', 'adj_price_cnt',
        'desc_volume_cnt', 'asc_volume_cnt'
    ])
    limit_orders_df.index = pd.to_datetime(limit_orders_df['init_place_ts'], unit='ms', utc=True)

    # --- 修复 TypeError: unhashable type: 'list' ---
    # 'order_side' 列中的某些值可能是列表，导致 groupby 失败。
    # 定义一个更健壮的函数来处理可能包含单值列表的情况，以及非预期列表格式。
    # 目标是确保 'order_side' 列中的所有值都是可哈希的数值类型（如 float 或 int）。
    def safe_numeric_order_side(val):
        if isinstance(val, list):
            if len(val) == 1:
                # 如果是包含单个元素的列表，则取出该元素
                return val[0]
            else:
                # 如果是空列表或包含多个元素的列表，则视为无效数据，返回 NaN
                return np.nan
        # 如果不是列表，直接返回原值
        return val

    # 对两个 DataFrame 中的 'order_side' 列应用此清理函数，并转换为浮点类型
    accounts_bt_df['order_side'] = accounts_bt_df['order_side'].apply(safe_numeric_order_side).astype(float)
    limit_orders_df['order_side'] = limit_orders_df['order_side'].apply(safe_numeric_order_side).astype(float)

    # --- 2. 基础 PnL 计算 (不带手续费) ---
    accounts_bt_df['pos_value'] = accounts_bt_df['pos'] * accounts_bt_df['trade_price']
    
    # equity_with_no_fee 累计 PnL (不含手续费)
    accounts_bt_df['equity_with_no_fee'] = accounts_bt_df['cash'] + accounts_bt_df['pos_value']
    
    # PnL per step (不含手续费)
    # 对于第一行，PnL为0
    accounts_bt_df['pnl_no_fee'] = accounts_bt_df['equity_with_no_fee'].diff().fillna(0)


    accounts_bt_df['trade_sub_cost_price'] = accounts_bt_df['trade_price'] - accounts_bt_df['avg_cost_price'].shift()

    # 虚拟平仓 PnL：仅在发生反向平仓交易时计算
    # pos.shift(1) 捕获上一时刻的持仓方向
    close_trades_ind = (accounts_bt_df['pos'].shift(1).fillna(0) * accounts_bt_df['order_side'] < 0) & \
                       (accounts_bt_df['order_side'] != 0) # 确保有实际交易方向
    
    # 虚拟平仓P&L计算，当发生反向交易且导致仓位减少或清零时
    # 考虑到 'order_side' 为 1 (buy) 或 -1 (sell)
    # 并且 trade_quantity 是交易量（正数）
    accounts_bt_df['virtual_close_pnl'] = (
        -(accounts_bt_df['trade_price'] - accounts_bt_df['avg_cost_price'].shift()) * accounts_bt_df['order_side'] * accounts_bt_df['trade_quantity']
    )
    accounts_bt_df.loc[~close_trades_ind, 'virtual_close_pnl'] = 0 # 非平仓交易的虚拟平仓PnL为0

    accounts_bt_df['un_pnl'] = accounts_bt_df['pos'] * (accounts_bt_df['trade_price'] - accounts_bt_df['avg_cost_price'])
    accounts_bt_df['realized_pnl_no_fee'] = accounts_bt_df['virtual_close_pnl'].cumsum()

    # --- 3. 包含手续费的 PnL 计算 ---
    # taker_fee 和 maker_fee 在 accounts_raw 中是累积值
    # 这些值已经体现了正负：正为返佣，负为成本
    accounts_bt_df['total_fee_cumulative'] = accounts_bt_df['taker_fee'] + accounts_bt_df['maker_fee']
    
    # 净值 (包含手续费)
    accounts_bt_df['equity_with_fees'] = accounts_bt_df['cash'] + accounts_bt_df['pos_value'] + accounts_bt_df['total_fee_cumulative']
    
    # PnL per step (包含手续费)
    accounts_bt_df['pnl_with_fee'] = accounts_bt_df['equity_with_fees'].diff().fillna(0)

    # --- 4. 分类交易统计 (Maker vs Taker) ---
    mm_inds = accounts_bt_df['order_role'] == 0
    maker_inds = accounts_bt_df['order_role'] == 2 # 明确 Maker 角色
    taker_inds = accounts_bt_df['order_role'] == 1 # 明确 Taker 角色

    mm_trades = accounts_bt_df.loc[mm_inds].copy()
    taker_trades = accounts_bt_df.loc[taker_inds].copy()

    # 沿用原脚本中对 mm_trades 和 hedge_trades 的 equity_with_no_fee 计算
    # 注意：此处计算方式可能与常见的累计净值不同，是特定语境下的指标。
    if not mm_trades.empty:
        mm_trades['equity_with_no_fee_specific'] = (mm_trades['trade_quantity'] * mm_trades['order_side']).cumsum() * mm_trades['trade_price'] - \
                                                 (mm_trades['trade_quantity'] * mm_trades['order_side'] * mm_trades['trade_price']).cumsum()
    else:
        mm_trades['equity_with_no_fee_specific'] = pd.Series([], dtype=float) # empty series

    if not taker_trades.empty:
        taker_trades['equity_with_no_fee_specific'] = (taker_trades['trade_quantity'] * taker_trades['order_side']).cumsum() * taker_trades['trade_price'] - \
                                                    (taker_trades['trade_quantity'] * taker_trades['order_side'] * taker_trades['trade_price']).cumsum()
    else:
        taker_trades['equity_with_no_fee_specific'] = pd.Series([], dtype=float) # empty series


    # --- 5. 挂单行为统计 ---
    have_trade_inds = limit_orders_df['finish_volume'] > 0
    have_trade_limit_df = limit_orders_df.loc[have_trade_inds].copy()

    if not have_trade_limit_df.empty:
        have_trade_limit_df['finish_pct'] = have_trade_limit_df['finish_volume'] / have_trade_limit_df['place_origin_volume']
        # 确保分母不为零，避免除零错误
        have_trade_limit_df['alpha_limit_price_pct'] = have_trade_limit_df['order_side'] * \
            (have_trade_limit_df['init_place_order_price'] - have_trade_limit_df['avg_match_trade_price']) / \
            have_trade_limit_df['avg_match_trade_price'].replace(0, np.nan) # Replace 0 with NaN to avoid division by zero
    else:
        have_trade_limit_df['finish_pct'] = pd.Series([], dtype=float)
        have_trade_limit_df['alpha_limit_price_pct'] = pd.Series([], dtype=float)

    # --- 6. 新增指标计算 ---

    overall_performance = {}
    maker_performance = {}
    taker_performance = {}
    fee_analysis = {}
    order_behavior_metrics = {}

    # 总交易量 (取绝对值，因为 trade_quantity 总是正数，order_side 决定方向)
    # 实际交易额 = 数量 * 价格
    total_trade_value = (accounts_bt_df['trade_quantity'] * accounts_bt_df['trade_price']).sum()

    # --- 总体绩效 ---
    overall_performance['total_pnl_with_fees'] = accounts_bt_df['pnl_with_fee'].sum()
    overall_performance['total_pnl_no_fees'] = accounts_bt_df['pnl_no_fee'].sum()

    if total_trade_value > 0:
        overall_performance['pnl_with_fees_pct_volume'] = overall_performance['total_pnl_with_fees'] / total_trade_value
        overall_performance['pnl_no_fees_pct_volume'] = overall_performance['total_pnl_no_fees'] / total_trade_value
    else:
        overall_performance['pnl_with_fees_pct_volume'] = 0.0
        overall_performance['pnl_no_fees_pct_volume'] = 0.0

    # 夏普比率和卡玛比率
    if len(accounts_bt_df) > 1:
        # 将数据重采样到日级别，以计算日收益率
        # 确保初始值不为0，避免除以零错误
        initial_equity_for_pnl_calc = accounts_bt_df['equity_with_fees'].iloc[0]
        if initial_equity_for_pnl_calc == 0:
            # 如果初始资金为0，则无法计算百分比收益率，将此项设为NaN或根据业务定义处理
            daily_returns = pd.Series([], dtype=float)
        else:
            daily_equity = accounts_bt_df['equity_with_fees'].resample('D').last().dropna()
            # 从第2天开始计算百分比变化
            daily_returns = daily_equity.pct_change().dropna() 
        
        if not daily_returns.empty:
            # 假设无风险利率为 0
            annualization_factor = np.sqrt(252) # 假设每年252个交易日
            
            # 夏普比率
            # 只有当收益率的标准差不为零时才计算
            if daily_returns.std() != 0:
                overall_performance['sharpe_ratio'] = daily_returns.mean() / daily_returns.std() * annualization_factor
            else:
                overall_performance['sharpe_ratio'] = np.inf if daily_returns.mean() > 0 else np.nan # 无波动但有收益，夏普为无穷大
            
            # 最大回撤
            cumulative_equity = accounts_bt_df['equity_with_fees']
            peak_equity = cumulative_equity.cummax()
            # 避免除以零或inf
            drawdown_percentage = (cumulative_equity - peak_equity) / peak_equity.replace(0, np.nan)
            max_drawdown = abs(drawdown_percentage.min()) if not drawdown_percentage.empty else 0
            overall_performance['max_drawdown'] = max_drawdown

            # 卡玛比率 (需要年化收益率和最大回撤)
            # 计算年化总收益率
            total_duration_years = (accounts_bt_df.index.max() - accounts_bt_df.index.min()).total_seconds() / (365.25 * 24 * 3600)
            
            # 只有当有足够的数据点且起始净值非零时才计算年化收益率
            if total_duration_years > 0 and accounts_bt_df['equity_with_fees'].iloc[0] != 0:
                annualized_return = ((accounts_bt_df['equity_with_fees'].iloc[-1] / accounts_bt_df['equity_with_fees'].iloc[0]) ** (1 / total_duration_years)) - 1
                if max_drawdown > 0:
                    overall_performance['calmar_ratio'] = annualized_return / max_drawdown
                else:
                    overall_performance['calmar_ratio'] = np.inf if annualized_return > 0 else np.nan # 无回撤但有收益，卡玛为无穷大
            else:
                overall_performance['calmar_ratio'] = np.nan # 无法计算
        else:
            overall_performance['sharpe_ratio'] = np.nan
            overall_performance['max_drawdown'] = np.nan
            overall_performance['calmar_ratio'] = np.nan
    else:
        overall_performance['sharpe_ratio'] = np.nan
        overall_performance['max_drawdown'] = np.nan
        overall_performance['calmar_ratio'] = np.nan
    
    # --- Maker 绩效 ---
    # Maker 的无手续费 P&L (根据虚拟平仓 P&L 计算)
    maker_pnl_no_fee = accounts_bt_df.loc[maker_inds, 'virtual_close_pnl'].sum()
    # Maker 交易额
    maker_volume_total = (accounts_bt_df.loc[maker_inds, 'trade_quantity'] * accounts_bt_df.loc[maker_inds, 'trade_price']).sum()
    
    maker_performance['total_maker_pnl_no_fees'] = maker_pnl_no_fee
    maker_performance['maker_volume_total'] = maker_volume_total
    if maker_volume_total > 0:
        maker_performance['maker_pnl_pct_volume'] = maker_pnl_no_fee / maker_volume_total
    else:
        maker_performance['maker_pnl_pct_volume'] = 0.0

    # Maker 实际手续费/返佣（从账户总手续费中提取，正为返佣，负为成本）
    maker_performance['actual_maker_fees_cost_rebate'] = accounts_bt_df['maker_fee'].iloc[-1] if not accounts_bt_df.empty else 0.0

    # --- Taker 绩效 ---
    # Taker 的无手续费 P&L (根据虚拟平仓 P&L 计算)
    taker_pnl_no_fee = accounts_bt_df.loc[taker_inds, 'virtual_close_pnl'].sum()
    # Taker 交易额
    taker_volume_total = (accounts_bt_df.loc[taker_inds, 'trade_quantity'] * accounts_bt_df.loc[taker_inds, 'trade_price']).sum()
    
    taker_performance['total_taker_pnl_no_fees'] = taker_pnl_no_fee
    taker_performance['taker_volume_total'] = taker_volume_total
    if taker_volume_total > 0:
        taker_performance['taker_pnl_pct_volume'] = taker_pnl_no_fee / taker_volume_total
    else:
        taker_performance['taker_pnl_pct_volume'] = 0.0
    
    # Taker 实际手续费成本（从账户总手续费中提取，正为返佣，负为成本）
    taker_performance['actual_taker_fees_cost'] = accounts_bt_df['taker_fee'].iloc[-1] if not accounts_bt_df.empty else 0.0


    # --- 手续费节省分析 ---
    # 策略实际的总手续费净额 (正为收入/返佣，负为支出/成本)
    fee_analysis['total_actual_fees'] = accounts_bt_df['total_fee_cumulative'].iloc[-1] if not accounts_bt_df.empty else 0.0
    
    # --- 挂单行为指标 ---
    total_minutes = (accounts_bt_df.index.max() - accounts_bt_df.index.min()).total_seconds() / 60



    buy_limit_orders_api_num_stats_1min=limit_orders_df[limit_orders_df['order_side']==1][['revoke_cnt','adj_price_cnt','desc_volume_cnt','asc_volume_cnt']].resample("1min").sum().describe()
    sell_limit_orders_api_num_stats_1min=limit_orders_df[limit_orders_df['order_side']==-1][['revoke_cnt','adj_price_cnt','desc_volume_cnt','asc_volume_cnt']].resample("1min").sum().describe()
    
    
   
    
    order_behavior_metrics['avg_fill_time_sec'] = have_trade_limit_df['lifecycle_ms'].mean()/1000 if not have_trade_limit_df.empty else np.nan
    order_behavior_metrics['median_fill_time_sec'] = have_trade_limit_df['lifecycle_ms'].median()/1000 if not have_trade_limit_df.empty else np.nan
    order_behavior_metrics['avg_fill_rate'] = have_trade_limit_df['finish_pct'].mean() if not have_trade_limit_df.empty else np.nan
    order_behavior_metrics['finish_all_pct'] =(have_trade_limit_df['finish_pct']>0.9995).sum()/len(have_trade_limit_df)  if not have_trade_limit_df.empty else np.nan
    order_behavior_metrics['finish_hit_pct'] =(have_trade_limit_df['finish_pct']>0.0005).sum()/len(have_trade_limit_df)  if not have_trade_limit_df.empty else np.nan

    # 原有的 groupby 统计
    if not have_trade_limit_df.empty:
        # 修正 agg 语法为字典形式，以解决用户报告的错误
        order_behavior_metrics['filled_order_agg_stats'] = have_trade_limit_df.groupby('order_side').agg(
            {'lifecycle_ms': ['mean', 'median'],
             'info': 'count',
             'finish_pct': ['mean', 'median'],
             'alpha_limit_price_pct': ['mean', 'median']}
        )
    else:
        order_behavior_metrics['filled_order_agg_stats'] = pd.DataFrame() # 空DataFrame

    if not limit_orders_df.empty:
        # 修正 agg 语法为字典形式
        order_behavior_metrics['maker_order_agg_stats'] = limit_orders_df.groupby('order_side')[
            ['revoke_cnt', 'adj_price_cnt', 'desc_volume_cnt', 'asc_volume_cnt']
        ].describe().T
    else:
        order_behavior_metrics['maker_order_agg_stats'] = pd.DataFrame() # 空DataFrame

    # --- 返回结果 ---
    return {
        # 'accounts_bt_df': accounts_bt_df,
        # 'limit_orders_df': limit_orders_df,
        # 'mm_trades_df': mm_trades, 
        # 'taker_trades_df': taker_trades, 
        # 'have_trade_limit_df': have_trade_limit_df, 
        'buy_limit_orders_api_num_stats_1min':buy_limit_orders_api_num_stats_1min,
        'sell_limit_orders_api_num_stats_1min':sell_limit_orders_api_num_stats_1min,
        'overall_performance': overall_performance,
        'maker_performance': maker_performance,
        'taker_performance': taker_performance,
        'fee_analysis': fee_analysis, # 这部分现在只包含 'total_actual_fees'
        'order_behavior_metrics': order_behavior_metrics
    }


demo=MarketMakerBacktester()
demo.run_backtest(data_feed=UNION_mm_with_aggtrade_df_np)
'''
demo.run_backtest(data_feed=UNION_mm_with_aggtrade_df_np)
回测区间: 2025-03-01 00:00:01 至 2025-06-17 15:59:59
开始执行Numba加速的回测循环...
回测循环执行完毕。耗时: 2.67秒
回测完成。共记录 5970843 条账户变动，8245 条订单生命周期。
性能指标计算完成。
{'start_date': '2025-03-01 00:00:01',
 'end_date': '2025-06-17 15:59:59',
 'elapsed_time': 2.6715309619903564,
 'accounts_count': 5970843,
 'orders_count': 8245}
'''


useage:
pl_df=analyze_ddh_maker_performance_np(accounts_raw=demo.accounts,place_orders_stats_raw=demo.place_orders_stats)
res=analyze_ddh_maker_performance(accounts_raw=accounts, 
                                 place_orders_stats_raw=place_orders_stats)



其中UNION_mm_with_aggtrade_df_np数据准备如下流程：

from dotenv import load_dotenv
import pandas as pd
from tqdm import tqdm
import os
import time
from datetime import datetime,timedelta
from clickhouse_driver import Client
import numpy as np
from numba import njit,prange
import httpx
from pytz import timezone
import ray

load_dotenv()

import duckdb
import pandas as pd
from tqdm import tqdm
import glob
import numpy as np
from warnings import filterwarnings
from datetime import datetime,timedelta
from joblib import Parallel,delayed
import joblib
from copy import copy
from itertools import product
from clickhouse_driver import Client
filterwarnings('ignore')
from pandas import IndexSlice as idx
import numba as nb
import os
from collections import deque

import re
def parse_dt_str(string,return_type=False):
    match_day= re.search(r'\d{4}-\d{2}-\d{2}', string)
    if match_day:
        if return_type:
            return match_day.group(),"day"
        return match_day.group()
    match_month = re.search(r'\d{4}-\d{2}', string)
    if match_month:
        if return_type:
            return match_month.group(),"month"
        return match_month.group()
    match_year = re.search(r'\d{4}', string)
    if match_year:
        if return_type:
            return match_year.group(),"year"
        return match_year.group()
    if return_type:
        return "",""
    return ""




data_user = os.getenv('DATA_USER')
data_password = os.getenv('DATA_PASSWORD')
data_host = os.getenv('DATA_HOST')
data_port = int(os.getenv('DATA_PORT'))

data_user_host = os.getenv("USER_DATA_HOST")
data_user_user = os.getenv("USER_DATA_USER")
data_user_port = int(os.getenv("USER_DATA_PORT"))
data_user_password = os.getenv("USER_DATA_PASSWORD")


global_data_client = Client(
            host=data_host,
            port=data_port,
            user=data_user,
            password=data_password,
            database='blofin_db'
        )
global_user_data_client =  Client(
                    host=data_user_host,
                    port=data_user_port,
                    user=data_user_user,
                    password=data_user_password,
                    database="blofin",
                    settings={'strings_encoding': 'utf-8'})


global_save_path='/home/jovyan/work/lab/simple_tasks/data'

special_accounts_tuple=tuple([i[0] for i in global_data_client.execute("select distinct(uid) from blofin_db.blofin_special_account_table")])
# 定义起始日期和结束日期
global_start_date = datetime(2025, 3, 1)
global_end_date = datetime(2030, 6, 19)

def prepare_layer_orders(symbol="SOL",start_ts=0,end_ts=1e15,user_data_client=None):
    if user_data_client is None:
        user_data_client =  Client(
                        host=data_user_host,
                        port=data_user_port,
                        user=data_user_user,
                        password=data_user_password,
                        database="blofin",
                        settings={'strings_encoding': 'utf-8'})
    fetch_user_orders_sql=f'''
                                    select 
                                        update_time as ctime,
                                        CAST(avg_price as Float64) as avg_price,
                                        CAST(abs(trade_quantity) as Float64) as traded,
                                        if(order_side = 1,-1,1) as direction
                                        # 1 as mm
                                        # count()
                                    from blofin.blofin_order_dwd_order_trade final
                                    where  
                                    uid in (1000177983, 1000076668, 1000376560, 1000163824, 1000147297, 1000138777, 1000088578)
                                    AND counterparty_uid NOT IN {str(special_accounts_tuple)}
                                    and symbol='{symbol}-USDT'
                                    and ctime>{start_ts}
                                    and ctime<={end_ts}
                                    order by ctime asc;
                                '''
    symbol_orders=user_data_client.execute(fetch_user_orders_sql)
    symbol_orders_np=np.array(symbol_orders)
    user_data_client.disconnect()
    return symbol_orders_np




def prepare_hft_bt_data(symbol="SOL", platform='okx', start_ts=0, end_ts=10e16):
    start_time = time.time()
    print(f"开始准备 {symbol} 的 HFT 回测数据...")

    symbol_orders_np = prepare_layer_orders(symbol=symbol, start_ts=start_ts, end_ts=end_ts, user_data_client=None)
    symbol_mm_trades_df = pd.DataFrame(symbol_orders_np, columns=['create_time', 'trade_price', 'trade_quantity', 'order_side'])
    symbol_mm_trades_df['mm'] = 1
    
    symbols_info_filename = f"{global_save_path}/{platform}/symbols_info.parquet"
    all_okx_symbols_info = pd.read_parquet(symbols_info_filename)
    
    process_data_path = f"{global_save_path}/process_data/{platform}"
    platform_symbol = f'{symbol}-USDT-SWAP'
    files = sorted(glob.glob(f"{process_data_path}/{platform_symbol}/*.parquet"))
    
    files_map = {parse_dt_str(f): f for f in files}
    files_df = pd.Series(files_map)
    files_df.index = pd.to_datetime(files_df.index)
    files_df = files_df.sort_index()
    
    contractSize = all_okx_symbols_info.loc[platform_symbol]['contractSize']
    price_step = all_okx_symbols_info.loc[platform_symbol]['precision']['price']
    
    files_list = files_df.loc[
        (files_df.index > global_start_date - pd.Timedelta("1d")) &
        (files_df.index < global_end_date + pd.Timedelta("1d"))
    ].tolist()
    
    files_list_str = str(files_list)
    
    agg_max_ts = duckdb.sql(f"SELECT max(created_time) as max_ts FROM '{files_list[-1]}'").fetchone()[0]

    UNION_mm_with_aggtrade_df_np = duckdb.sql(f'''
        SELECT 
            created_time as create_time,
            CASE WHEN side='buy' THEN 1 ELSE -1 END as order_side,
            price as trade_price,
            {contractSize} * size as trade_quantity,
            0 as mm
        FROM read_parquet({files_list_str})
        WHERE create_time >= {start_ts} 
          AND create_time <= {agg_max_ts}
          AND create_time < {end_ts}
        
        UNION ALL
        
        SELECT 
            create_time,
            order_side,
            trade_price,
            trade_quantity,
            mm
        FROM symbol_mm_trades_df
        WHERE create_time <= {agg_max_ts}
        
        ORDER BY create_time ASC;
    ''').df().values

    elapsed = time.time() - start_time
    print(f"✅ {symbol} 的数据准备完成，耗时：{elapsed:.2f} 秒")
    return UNION_mm_with_aggtrade_df_np

start_ts=int(global_start_date.timestamp() * 1000)
end_ts = int(global_end_date.timestamp() * 1000)
UNION_mm_with_aggtrade_df_np=prepare_hft_bt_data(symbol="BTC",platform='okx',start_ts=start_ts,end_ts=end_ts)
