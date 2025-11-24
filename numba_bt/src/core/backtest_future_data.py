"""未来数据测试策略：使用未来30秒的价格方向进行挂单"""
import numpy as np
from numba import njit


@njit
def _calculate_future_30s_returns(data_feed):
    """
    预先计算所有时刻的未来30秒return
    
    Args:
        data_feed: 数据数组 [timestamp, order_side, price, quantity, mm_flag]
    
    Returns:
        未来30秒return数组，与data_feed长度相同
    """
    future_returns = np.zeros(len(data_feed))
    window_ms = 30 * 1000  # 30秒
    
    for i in range(len(data_feed)):
        if data_feed[i, 4] == 0:  # 跳过taker trades
            continue
        
        current_ts = data_feed[i, 0]
        current_price = data_feed[i, 2]
        target_ts = current_ts + window_ms
        
        # 向后查找30秒后的价格
        future_price = current_price
        found = False
        
        for j in range(i + 1, len(data_feed)):
            if data_feed[j, 4] == 0:  # 跳过taker trades
                continue
            
            if data_feed[j, 0] >= target_ts:
                future_price = data_feed[j, 2]
                found = True
                break
        
        # 如果找不到30秒后的价格，使用最后一个价格
        if not found and i < len(data_feed) - 1:
            # 查找最后一个市场数据价格
            for j in range(len(data_feed) - 1, i, -1):
                if data_feed[j, 4] != 0:
                    future_price = data_feed[j, 2]
                    break
        
        if current_price > 0:
            future_returns[i] = (future_price - current_price) / current_price
    
    return future_returns


@njit
def _run_backtest_future_data_numba(
    # ---- 数据 ----
    data_feed,
    future_30s_returns,  # 预先计算的未来30秒return数组
    # ---- 参数 ----
    exposure,
    target_pct,
    mini_price_step,
    taker_fee_rate,
    maker_fee_rate,
    open_ratio,
    # ---- 策略参数 ----
    return_percentile_20,
    return_percentile_80,
    spread_median,
    order_size,
    price_update_threshold,
    min_spread_pct,
    hedge_threshold_pct,
    stop_loss_pct,
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
    未来数据测试策略回测函数
    
    使用预先计算的未来30秒return来决定挂单策略，模拟完美预测
    """
    # 内部状态变量
    cash = initial_cash
    pos = initial_pos
    avg_cost_price = 0.0
    taker_fee = 0.0
    maker_fee = 0.0
    
    # 挂单状态
    buy_order = np.zeros(8)
    sell_order = np.zeros(8)
    is_buy_order_active = False
    is_sell_order_active = False
    
    # 结果数组的索引
    accounts_idx = 0
    stats_idx = 0
    
    last_mark_price = data_feed[0, 2] if len(data_feed) > 0 else 0.0
    
    # 资金费率相关
    funding_idx = 0
    if funding_rate_data.size == 0:
        funding_enabled = False
    else:
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
        
        # 更新标记价格
        if mm_flag != 0:
            last_mark_price = trade_price
        
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
        
        # 2. 止损检查
        current_equity = cash + pos_value
        if current_equity > max_equity:
            max_equity = current_equity
        
        equity_drawdown = max_equity - current_equity
        if equity_drawdown > exposure * stop_loss_pct and not stop_loss_triggered:
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
                
                accounts_log[accounts_idx] = [now_ts, cash, pos, avg_cost_price, hedge_price, hedge_volume, hedge_side, taker_fee, maker_fee, 7]
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
        
        # 3. 风险控制：仓位控制
        hedge_threshold = exposure * hedge_threshold_pct
        if abs(pos_value) > hedge_threshold:
            target_pos_value_actual = exposure * target_pct * np.sign(pos) if pos != 0 else 0.0
            hedge_volume = abs(pos - target_pos_value_actual / last_mark_price) if last_mark_price > 0 else 0.0
            
            if hedge_volume > 1e-8:
                hedge_side = -np.sign(pos - target_pos_value_actual / last_mark_price)
                hedge_price = last_mark_price + hedge_side * mini_price_step * 2
                
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
        
        # 4. 获取未来30s return（预先计算的）
        future_30s_return = future_30s_returns[i] if i < len(future_30s_returns) else 0.0
        
        # 5. 检查并处理挂单的撮合 (Maker Trade)
        # 5.1 买单撮合
        if is_buy_order_active and mm_flag != 0 and order_side < 0:
            buy_order_price = buy_order[1]
            cross_price = buy_order_price - trade_price
            
            trade_volume = 0.0
            if cross_price >= 0:
                trade_volume = min(buy_order[3], trade_quantity)
            
            if trade_volume > 0:
                finish_volume = buy_order[5] + trade_volume
                avg_match_price = (buy_order[6] * buy_order[5] + buy_order_price * trade_volume) / finish_volume if finish_volume > 0 else buy_order_price
                
                if trade_volume == buy_order[3]:
                    lifecycle_ms = now_ts - buy_order[7]
                    place_origin_volume = buy_order[5] + buy_order[3]
                    place_orders_stats_log[stats_idx] = [buy_order[7], lifecycle_ms, buy_order_price, 1, place_origin_volume, finish_volume, avg_match_price, buy_order[4], 0, 0, 0, 0, 0]
                    stats_idx += 1
                    is_buy_order_active = False
                else:
                    buy_order[3] -= trade_volume
                    buy_order[5] = finish_volume
                    buy_order[6] = avg_match_price
                
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
        if is_sell_order_active and mm_flag != 0 and order_side > 0:
            sell_order_price = sell_order[1]
            cross_price = trade_price - sell_order_price
            
            trade_volume = 0.0
            if cross_price >= 0:
                trade_volume = min(sell_order[3], trade_quantity)
            
            if trade_volume > 0:
                finish_volume = sell_order[5] + trade_volume
                avg_match_price = (sell_order[6] * sell_order[5] + sell_order_price * trade_volume) / finish_volume if finish_volume > 0 else sell_order_price
                
                if trade_volume == sell_order[3]:
                    lifecycle_ms = now_ts - sell_order[7]
                    place_origin_volume = sell_order[5] + sell_order[3]
                    place_orders_stats_log[stats_idx] = [sell_order[7], lifecycle_ms, sell_order_price, -1, place_origin_volume, finish_volume, avg_match_price, sell_order[4], 0, 0, 0, 0, 0]
                    stats_idx += 1
                    is_sell_order_active = False
                else:
                    sell_order[3] -= trade_volume
                    sell_order[5] = finish_volume
                    sell_order[6] = avg_match_price
                
                if pos * (-1) >= 0:
                    if (pos - trade_volume) != 0:
                        avg_cost_price = (avg_cost_price * abs(pos) + trade_volume * sell_order_price) / abs(pos - trade_volume)
                else:
                    if trade_volume > pos:
                        avg_cost_price = sell_order_price
                
                pos -= trade_volume
                order_value = trade_volume * sell_order_price
                cash += order_value
                maker_fee -= maker_fee_rate * order_value
                accounts_log[accounts_idx] = [now_ts, cash, pos, avg_cost_price, sell_order_price, trade_volume, -1, taker_fee, maker_fee, 2]
                accounts_idx += 1
        
        # 6. 未来数据策略逻辑：使用未来30s return决定挂单
        if mm_flag != 0:
            # 6.1 检查是否需要撤单
            if is_buy_order_active or is_sell_order_active:
                need_revoke_buy = False
                need_revoke_sell = False
                
                if is_buy_order_active and future_30s_return > return_percentile_80:
                    need_revoke_buy = True
                
                if is_sell_order_active and future_30s_return < return_percentile_20:
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
            
            # 6.2 根据未来return决定挂单策略（反向挂单逻辑）
            order_quantity = order_size / last_mark_price if last_mark_price > 0 else 0.0
            optimized_spread = max(spread_median * 3, min_spread_pct)
            
            if future_30s_return > return_percentile_80:
                # 未来看涨：买单挂远，卖单挂近（反向，避免单向持仓）
                if not is_buy_order_active:
                    buy_price = last_mark_price * (1 - abs(future_30s_return))
                    buy_order = np.array([now_ts, buy_price, 1, order_quantity, buy_price, 0.0, 0.0, now_ts])
                    is_buy_order_active = True
                
                if not is_sell_order_active:
                    sell_price = last_mark_price + mini_price_step
                    sell_order = np.array([now_ts, sell_price, -1, order_quantity, sell_price, 0.0, 0.0, now_ts])
                    is_sell_order_active = True
            
            elif future_30s_return < return_percentile_20:
                # 未来看跌：卖单挂远，买单挂近（反向，避免单向持仓）
                if not is_sell_order_active:
                    sell_price = last_mark_price * (1 + abs(future_30s_return))
                    sell_order = np.array([now_ts, sell_price, -1, order_quantity, sell_price, 0.0, 0.0, now_ts])
                    is_sell_order_active = True
                
                if not is_buy_order_active:
                    buy_price = last_mark_price - mini_price_step
                    buy_order = np.array([now_ts, buy_price, 1, order_quantity, buy_price, 0.0, 0.0, now_ts])
                    is_buy_order_active = True
            
            else:
                # 中性：多空等距等量
                if not is_buy_order_active:
                    buy_price = last_mark_price * (1 - optimized_spread / 2)
                    buy_order = np.array([now_ts, buy_price, 1, order_quantity, buy_price, 0.0, 0.0, now_ts])
                    is_buy_order_active = True
                
                if not is_sell_order_active:
                    sell_price = last_mark_price * (1 + optimized_spread / 2)
                    sell_order = np.array([now_ts, sell_price, -1, order_quantity, sell_price, 0.0, 0.0, now_ts])
                    is_sell_order_active = True
            
            # 6.3 订单更新
            if is_buy_order_active:
                price_diff_pct = abs(buy_order[1] - last_mark_price) / last_mark_price if last_mark_price > 0 else 0.0
                if price_diff_pct > price_update_threshold:
                    if future_30s_return > return_percentile_80:
                        buy_order[1] = last_mark_price * (1 - abs(future_30s_return))
                    elif future_30s_return < return_percentile_20:
                        buy_order[1] = last_mark_price - mini_price_step
                    else:
                        buy_order[1] = last_mark_price * (1 - optimized_spread / 2)
                    buy_order[0] = now_ts
            
            if is_sell_order_active:
                price_diff_pct = abs(sell_order[1] - last_mark_price) / last_mark_price if last_mark_price > 0 else 0.0
                if price_diff_pct > price_update_threshold:
                    if future_30s_return > return_percentile_80:
                        sell_order[1] = last_mark_price + mini_price_step
                    elif future_30s_return < return_percentile_20:
                        sell_order[1] = last_mark_price * (1 + abs(future_30s_return))
                    else:
                        sell_order[1] = last_mark_price * (1 + optimized_spread / 2)
                    sell_order[0] = now_ts
    
    return accounts_idx, stats_idx
