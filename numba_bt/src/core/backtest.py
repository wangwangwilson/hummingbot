"""核心回测引擎，使用Numba加速"""
import numpy as np
from numba import njit

# mm_flag 设计规则（硬编码）
# 0: blofin trades (真实成交，Taker Trade)
# 1: binance trades (市场数据)
# 2: okx trades (市场数据)
# 3: bybit trades (市场数据)
# -1: binance orderbook (市场数据)
# -2: funding_rate (市场数据)
# 只有当 mm_flag == 0 时，才会处理为交易所的真实成交 (Taker Trade)


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
        # 只有当 mm_flag == 0 时，才处理为真实成交
        if mm_flag == 0:
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
            # mm_flag != 0: 市场数据，只更新价格
            last_mark_price = trade_price

        pos_value = pos * last_mark_price

        # 2. 检查并处理挂单的撮合 (Maker Trade)
        # 只有市场数据（mm_flag != 0）才能触发挂单成交
        have_trade_match = False
        if is_order_active and mm_flag != 0 and now_place_order[2] * order_side < 0:
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

