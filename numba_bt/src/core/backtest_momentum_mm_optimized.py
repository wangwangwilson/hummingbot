"""优化版本的基于30s return动量的做市策略核心回测函数"""
import numpy as np
from numba import njit


@njit
def _calculate_30s_return_numba(prices: np.ndarray, timestamps: np.ndarray, current_idx: int) -> float:
    """
    计算当前时刻的30秒收益率（Numba加速版本）
    
    Args:
        prices: 价格数组
        timestamps: 时间戳数组（毫秒）
        current_idx: 当前索引
    
    Returns:
        30秒收益率
    """
    if current_idx == 0:
        return 0.0
    
    window_ms = 30 * 1000  # 30秒
    target_ts = timestamps[current_idx] - window_ms
    
    # 向前查找30秒前的价格
    base_idx = current_idx
    for j in range(current_idx - 1, -1, -1):
        if timestamps[j] <= target_ts:
            base_idx = j
            break
    
    if base_idx < current_idx and prices[base_idx] > 0:
        return (prices[current_idx] - prices[base_idx]) / prices[base_idx]
    
    return 0.0


@njit
def _run_backtest_momentum_mm_optimized_numba(
    # ---- 数据 ----
    data_feed,
    # ---- 参数 ----
    exposure,
    target_pct,
    mini_price_step,
    taker_fee_rate,
    maker_fee_rate,
    open_ratio,
    # ---- 动量策略参数 ----
    return_percentile_20,
    return_percentile_80,
    spread_median,
    order_size,  # 单笔挂单金额（USDT）
    price_update_threshold,  # 价格更新阈值（相对价格）
    # ---- 优化参数 ----
    min_spread_pct,  # 最小spread百分比（至少0.2%）
    hedge_threshold_pct,  # 对冲阈值（0.8表示当仓位超过exposure*0.8时开始对冲）
    stop_loss_pct,  # 止损百分比（0.1表示单笔亏损超过exposure*0.1时止损）
    # ---- 初始状态 ----
    initial_cash,
    initial_pos,
    # ---- 预分配的结果数组 ----
    accounts_log,
    place_orders_stats_log,
    # ---- 扩展点：资金费率数据 ----
    funding_rate_data
):
    """
    优化版本的基于30s return动量的做市策略回测函数
    
    优化点：
    1. 反向挂单逻辑：看涨时买单挂远，卖单挂近（避免单向持仓）
    2. 增加spread：确保能覆盖手续费和滑点
    3. 改进仓位控制：更及时的对冲机制（exposure * 0.8时开始对冲）
    4. 优化订单更新：增加价格更新阈值
    5. 增加止损机制：限制单笔交易的最大亏损
    """
    # 内部状态变量
    cash = initial_cash
    pos = initial_pos
    avg_cost_price = 0.0
    taker_fee = 0.0
    maker_fee = 0.0
    target_pos_value = exposure * target_pct
    
    # 挂单状态：买卖各一档
    # [创建时间, 价格, 方向, 数量, 初始价格, 已成交量, 成交均价, 初始时间]
    buy_order = np.zeros(8)
    sell_order = np.zeros(8)
    is_buy_order_active = False
    is_sell_order_active = False
    
    # 价格历史（用于计算30s return）
    price_history = np.zeros(min(len(data_feed), 10000))  # 最多保存10000个价格
    timestamp_history = np.zeros(min(len(data_feed), 10000), dtype=np.int64)
    price_history_idx = 0
    price_history_size = 0
    
    # 结果数组的索引
    accounts_idx = 0
    stats_idx = 0
    
    last_mark_price = data_feed[0, 2] if len(data_feed) > 0 else 0.0
    
    # 资金费率相关
    funding_idx = 0
    # 确保funding_rate_data是2D数组
    if funding_rate_data.size == 0:
        funding_enabled = False
    else:
        # 检查是否是2D数组且至少有2列
        ndim = len(funding_rate_data.shape)
        if ndim == 2 and funding_rate_data.shape[0] > 0:
            funding_enabled = True
        else:
            funding_enabled = False
    last_funding_ts = -1
    
    # 止损相关
    initial_equity = initial_cash + initial_pos * last_mark_price
    max_equity = initial_equity
    stop_loss_triggered = False
    
    for i in range(data_feed.shape[0]):
        line = data_feed[i]
        now_ts, order_side, trade_price, trade_quantity, mm_flag = line[0], line[1], line[2], line[3], line[4]
        
        # 更新价格历史（只记录市场数据）
        if mm_flag != 0:
            last_mark_price = trade_price
            if price_history_size < len(price_history):
                price_history[price_history_size] = trade_price
                timestamp_history[price_history_size] = now_ts
                price_history_size += 1
            else:
                # 循环覆盖
                price_history[price_history_idx] = trade_price
                timestamp_history[price_history_idx] = now_ts
                price_history_idx = (price_history_idx + 1) % len(price_history)
        
        # 扩展点：检查资金费率支付
        if funding_enabled and funding_idx < funding_rate_data.shape[0]:
            funding_ts = funding_rate_data[funding_idx, 0]
            funding_rate = funding_rate_data[funding_idx, 1]
            
            if now_ts >= funding_ts and funding_ts > last_funding_ts:
                pos_value_funding = pos * last_mark_price
                funding_fee = pos_value_funding * funding_rate
                
                cash -= funding_fee
                
                accounts_log[accounts_idx] = [now_ts, cash, pos, avg_cost_price, last_mark_price, 0.0, 0.0, taker_fee, maker_fee, 6]
                accounts_idx += 1
                
                last_funding_ts = funding_ts
                funding_idx += 1
                if funding_idx >= funding_rate_data.shape[0]:
                    funding_enabled = False
        
        # 1. 处理交易所的真实成交 (Taker Trade)
        if mm_flag == 0:
            if pos * order_side < 0 and trade_quantity > abs(pos):
                avg_cost_price = trade_price
            elif pos * order_side >= 0:
                if (pos + order_side * trade_quantity) != 0:
                    avg_cost_price = (avg_cost_price * pos + order_side * trade_quantity * trade_price) / (pos + order_side * trade_quantity)
            
            pos += order_side * trade_quantity
            cash -= order_side * trade_quantity * trade_price
            
            accounts_log[accounts_idx] = [now_ts, cash, pos, avg_cost_price, trade_price, trade_quantity, order_side, taker_fee, maker_fee, 0]
            accounts_idx += 1
        
        pos_value = pos * last_mark_price
        
        # 2. 止损检查（优化点5）
        current_equity = cash + pos_value
        if current_equity > max_equity:
            max_equity = current_equity
        
        equity_drawdown = max_equity - current_equity
        if equity_drawdown > exposure * stop_loss_pct and not stop_loss_triggered:
            # 触发止损：强制平仓
            if abs(pos) > 1e-8:
                hedge_side = -np.sign(pos)
                hedge_volume = abs(pos)
                hedge_price = last_mark_price + hedge_side * mini_price_step
                
                pos += hedge_side * hedge_volume
                cash -= hedge_side * hedge_volume * hedge_price
                taker_fee -= taker_fee_rate * hedge_volume * hedge_price
                
                if abs(pos) < 1e-8:
                    avg_cost_price = 0.0
                else:
                    avg_cost_price = hedge_price
                
                accounts_log[accounts_idx] = [now_ts, cash, pos, avg_cost_price, hedge_price, hedge_volume, hedge_side, taker_fee, maker_fee, 7]  # info=7表示止损
                accounts_idx += 1
                
                # 撤单
                if is_buy_order_active:
                    lifecycle_ms = now_ts - buy_order[7]
                    place_origin_volume = buy_order[5] + buy_order[3]
                    place_orders_stats_log[stats_idx] = [buy_order[7], lifecycle_ms, buy_order[1], buy_order[2], place_origin_volume, buy_order[5], buy_order[6], buy_order[4], 4, 1, 0, 0, 0]
                    stats_idx += 1
                    is_buy_order_active = False
                
                if is_sell_order_active:
                    lifecycle_ms = now_ts - sell_order[7]
                    place_origin_volume = sell_order[5] + sell_order[3]
                    place_orders_stats_log[stats_idx] = [sell_order[7], lifecycle_ms, sell_order[1], sell_order[2], place_origin_volume, sell_order[5], sell_order[6], sell_order[4], 4, 1, 0, 0, 0]
                    stats_idx += 1
                    is_sell_order_active = False
                
                stop_loss_triggered = True
                continue
        
        # 3. 风险控制：改进的仓位控制（优化点3）
        # 当仓位超过exposure * hedge_threshold_pct时开始对冲
        hedge_threshold = exposure * hedge_threshold_pct
        if abs(pos_value) > hedge_threshold:
            target_pos_value_actual = exposure * target_pct * np.sign(pos) if pos != 0 else 0.0
            hedge_volume = abs(pos - target_pos_value_actual / last_mark_price) if last_mark_price > 0 else 0.0
            
            if hedge_volume > 1e-8:
                hedge_side = -np.sign(pos - target_pos_value_actual / last_mark_price)
                # 使用Maker订单对冲，而不是Taker（优化点3）
                # 但为了简化，这里仍然使用taker，但价格更优
                hedge_price = last_mark_price + hedge_side * mini_price_step * 2  # 稍微远离盘口
                
                # 撤单
                if is_buy_order_active:
                    lifecycle_ms = now_ts - buy_order[7]
                    place_origin_volume = buy_order[5] + buy_order[3]
                    place_orders_stats_log[stats_idx] = [buy_order[7], lifecycle_ms, buy_order[1], buy_order[2], place_origin_volume, buy_order[5], buy_order[6], buy_order[4], 4, 1, 0, 0, 0]
                    stats_idx += 1
                    is_buy_order_active = False
                
                if is_sell_order_active:
                    lifecycle_ms = now_ts - sell_order[7]
                    place_origin_volume = sell_order[5] + sell_order[3]
                    place_orders_stats_log[stats_idx] = [sell_order[7], lifecycle_ms, sell_order[1], sell_order[2], place_origin_volume, sell_order[5], sell_order[6], sell_order[4], 4, 1, 0, 0, 0]
                    stats_idx += 1
                    is_sell_order_active = False
                
                # 执行对冲
                pos += hedge_side * hedge_volume
                order_value = hedge_volume * hedge_price
                cash -= hedge_side * order_value
                taker_fee -= taker_fee_rate * order_value
                
                if abs(pos) < 1e-8:
                    avg_cost_price = 0.0
                elif abs(hedge_volume) > abs(pos) * 0.9:
                    avg_cost_price = hedge_price
                
                accounts_log[accounts_idx] = [now_ts, cash, pos, avg_cost_price, hedge_price, hedge_volume, hedge_side, taker_fee, maker_fee, 1]
                accounts_idx += 1
                continue
        
        # 4. 计算30s return
        current_30s_return = 0.0
        if price_history_size > 1 and mm_flag != 0:
            # 使用价格历史计算30s return
            current_30s_return = _calculate_30s_return_numba(
                price_history[:price_history_size],
                timestamp_history[:price_history_size],
                price_history_size - 1
            )
        
        # 5. 检查并处理挂单的撮合 (Maker Trade)
        # 5.1 买单撮合
        if is_buy_order_active and mm_flag != 0 and order_side < 0:  # 卖单成交，可能匹配买单
            buy_order_price = buy_order[1]
            cross_price = buy_order_price - trade_price
            
            trade_volume = 0.0
            if cross_price >= 0:  # 价格穿过或正好
                trade_volume = min(buy_order[3], trade_quantity)
            
            if trade_volume > 0:
                finish_volume = buy_order[5] + trade_volume
                avg_match_price = (buy_order[6] * buy_order[5] + buy_order_price * trade_volume) / finish_volume if finish_volume > 0 else buy_order_price
                
                if trade_volume == buy_order[3]:  # 完全成交
                    lifecycle_ms = now_ts - buy_order[7]
                    place_origin_volume = buy_order[5] + buy_order[3]
                    place_orders_stats_log[stats_idx] = [buy_order[7], lifecycle_ms, buy_order_price, 1, place_origin_volume, finish_volume, avg_match_price, buy_order[4], 0, 0, 0, 0, 0]
                    stats_idx += 1
                    is_buy_order_active = False
                else:  # 部分成交
                    buy_order[3] -= trade_volume
                    buy_order[5] = finish_volume
                    buy_order[6] = avg_match_price
                
                # 更新仓位和资金
                if pos >= 0:
                    if (pos + trade_volume) != 0:
                        avg_cost_price = (avg_cost_price * pos + trade_volume * buy_order_price) / (pos + trade_volume)
                else:
                    if trade_volume > abs(pos):
                        avg_cost_price = buy_order_price
                
                pos += trade_volume
                order_value = trade_volume * buy_order_price
                cash -= order_value
                maker_fee -= maker_fee_rate * order_value
                accounts_log[accounts_idx] = [now_ts, cash, pos, avg_cost_price, buy_order_price, trade_volume, 1, taker_fee, maker_fee, 2]
                accounts_idx += 1
        
        # 5.2 卖单撮合
        if is_sell_order_active and mm_flag != 0 and order_side > 0:  # 买单成交，可能匹配卖单
            sell_order_price = sell_order[1]
            cross_price = trade_price - sell_order_price
            
            trade_volume = 0.0
            if cross_price >= 0:  # 价格穿过或正好
                trade_volume = min(sell_order[3], trade_quantity)
            
            if trade_volume > 0:
                finish_volume = sell_order[5] + trade_volume
                avg_match_price = (sell_order[6] * sell_order[5] + sell_order_price * trade_volume) / finish_volume if finish_volume > 0 else sell_order_price
                
                if trade_volume == sell_order[3]:  # 完全成交
                    lifecycle_ms = now_ts - sell_order[7]
                    place_origin_volume = sell_order[5] + sell_order[3]
                    place_orders_stats_log[stats_idx] = [sell_order[7], lifecycle_ms, sell_order_price, -1, place_origin_volume, finish_volume, avg_match_price, sell_order[4], 0, 0, 0, 0, 0]
                    stats_idx += 1
                    is_sell_order_active = False
                else:  # 部分成交
                    sell_order[3] -= trade_volume
                    sell_order[5] = finish_volume
                    sell_order[6] = avg_match_price
                
                # 更新仓位和资金
                if pos * (-1) >= 0:  # 卖单成交，如果当前是空仓或零仓
                    if (pos - trade_volume) != 0:
                        avg_cost_price = (avg_cost_price * abs(pos) + trade_volume * sell_order_price) / abs(pos - trade_volume)
                else:  # 当前是多仓，卖单成交是平多或开空
                    if trade_volume > pos:
                        avg_cost_price = sell_order_price
                
                pos -= trade_volume
                order_value = trade_volume * sell_order_price
                cash += order_value
                maker_fee -= maker_fee_rate * order_value
                accounts_log[accounts_idx] = [now_ts, cash, pos, avg_cost_price, sell_order_price, trade_volume, -1, taker_fee, maker_fee, 2]
                accounts_idx += 1
        
        # 6. 优化版本的动量策略逻辑：反向挂单（优化点1）
        if mm_flag != 0:  # 只对市场数据执行策略
            # 6.1 检查是否需要撤单（反转信号）
            if is_buy_order_active or is_sell_order_active:
                # 检查反转：如果之前是看涨（return>80%）现在变成看跌（return<20%），或反之
                need_revoke_buy = False
                need_revoke_sell = False
                
                # 检查买单：如果之前是看跌信号但现在变成看涨，撤买单（因为看涨时买单应该挂远）
                if is_buy_order_active and current_30s_return > return_percentile_80:
                    need_revoke_buy = True
                
                # 检查卖单：如果之前是看涨信号但现在变成看跌，撤卖单（因为看跌时卖单应该挂远）
                if is_sell_order_active and current_30s_return < return_percentile_20:
                    need_revoke_sell = True
                
                if need_revoke_buy:
                    lifecycle_ms = now_ts - buy_order[7]
                    place_origin_volume = buy_order[5] + buy_order[3]
                    place_orders_stats_log[stats_idx] = [buy_order[7], lifecycle_ms, buy_order[1], 1, place_origin_volume, buy_order[5], buy_order[6], buy_order[4], 3, 1, 0, 0, 0]
                    stats_idx += 1
                    is_buy_order_active = False
                
                if need_revoke_sell:
                    lifecycle_ms = now_ts - sell_order[7]
                    place_origin_volume = sell_order[5] + sell_order[3]
                    place_orders_stats_log[stats_idx] = [sell_order[7], lifecycle_ms, sell_order[1], -1, place_origin_volume, sell_order[5], sell_order[6], sell_order[4], 3, 1, 0, 0, 0]
                    stats_idx += 1
                    is_sell_order_active = False
            
            # 6.2 根据return决定挂单策略（优化点1：反向挂单）
            # 计算挂单数量（基于order_size）
            order_quantity = order_size / last_mark_price if last_mark_price > 0 else 0.0
            
            # 优化spread（优化点2）：确保能覆盖手续费和滑点
            # spread = max(spread_median * 3, min_spread_pct)
            optimized_spread = max(spread_median * 3, min_spread_pct)
            
            if current_30s_return > return_percentile_80:
                # 看涨：买单挂远，卖单挂近（反向，避免单向持仓）
                if not is_buy_order_active:
                    # 买单挂在当前价格 - 一个return的价格比例处（挂远）
                    buy_price = last_mark_price * (1 - abs(current_30s_return))
                    buy_order = np.array([now_ts, buy_price, 1, order_quantity, buy_price, 0.0, 0.0, now_ts])
                    is_buy_order_active = True
                
                if not is_sell_order_active:
                    # 卖单挂盘口上方（挂近）
                    sell_price = last_mark_price + mini_price_step
                    sell_order = np.array([now_ts, sell_price, -1, order_quantity, sell_price, 0.0, 0.0, now_ts])
                    is_sell_order_active = True
            
            elif current_30s_return < return_percentile_20:
                # 看跌：卖单挂远，买单挂近（反向，避免单向持仓）
                if not is_sell_order_active:
                    # 卖单挂在当前价格 + 一个return的价格比例处（挂远）
                    sell_price = last_mark_price * (1 + abs(current_30s_return))
                    sell_order = np.array([now_ts, sell_price, -1, order_quantity, sell_price, 0.0, 0.0, now_ts])
                    is_sell_order_active = True
                
                if not is_buy_order_active:
                    # 买单挂盘口下方（挂近）
                    buy_price = last_mark_price - mini_price_step
                    buy_order = np.array([now_ts, buy_price, 1, order_quantity, buy_price, 0.0, 0.0, now_ts])
                    is_buy_order_active = True
            
            else:
                # 中性：多空等距等量，使用优化后的spread
                if not is_buy_order_active:
                    buy_price = last_mark_price * (1 - optimized_spread / 2)
                    buy_order = np.array([now_ts, buy_price, 1, order_quantity, buy_price, 0.0, 0.0, now_ts])
                    is_buy_order_active = True
                
                if not is_sell_order_active:
                    sell_price = last_mark_price * (1 + optimized_spread / 2)
                    sell_order = np.array([now_ts, sell_price, -1, order_quantity, sell_price, 0.0, 0.0, now_ts])
                    is_sell_order_active = True
            
            # 6.3 订单更新：根据挂单和最新成交价距离调整（优化点4：增加阈值）
            if is_buy_order_active:
                price_diff_pct = abs(buy_order[1] - last_mark_price) / last_mark_price if last_mark_price > 0 else 0.0
                if price_diff_pct > price_update_threshold:
                    # 更新买单价格
                    if current_30s_return > return_percentile_80:
                        buy_order[1] = last_mark_price * (1 - abs(current_30s_return))
                    elif current_30s_return < return_percentile_20:
                        buy_order[1] = last_mark_price - mini_price_step
                    else:
                        buy_order[1] = last_mark_price * (1 - optimized_spread / 2)
                    buy_order[0] = now_ts
            
            if is_sell_order_active:
                price_diff_pct = abs(sell_order[1] - last_mark_price) / last_mark_price if last_mark_price > 0 else 0.0
                if price_diff_pct > price_update_threshold:
                    # 更新卖单价格
                    if current_30s_return > return_percentile_80:
                        sell_order[1] = last_mark_price + mini_price_step
                    elif current_30s_return < return_percentile_20:
                        sell_order[1] = last_mark_price * (1 + abs(current_30s_return))
                    else:
                        sell_order[1] = last_mark_price * (1 + optimized_spread / 2)
                    sell_order[0] = now_ts
    
    return accounts_idx, stats_idx

