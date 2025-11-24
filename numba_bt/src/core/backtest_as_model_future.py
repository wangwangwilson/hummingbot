"""基于AS_MODEL不对等挂单的未来数据策略回测核心"""
import numpy as np
from numba import njit


@njit
def _calculate_30min_return_median(data_feed, current_idx, window_minutes=30):
    """
    计算过去30分钟的30s return序列中位值
    
    Args:
        data_feed: 数据数组 [timestamp, order_side, price, quantity, mm_flag]
        current_idx: 当前索引
        window_minutes: 时间窗口（分钟）
    
    Returns:
        过去30分钟30s return序列的中位值
    """
    if current_idx == 0:
        return 0.0
    
    window_ms = window_minutes * 60 * 1000
    current_ts = data_feed[current_idx, 0]
    target_ts = current_ts - window_ms
    
    # 收集过去30分钟的价格（只取市场数据）
    prices = []
    timestamps = []
    
    for j in range(current_idx - 1, -1, -1):
        if data_feed[j, 4] == 0:  # 跳过taker trades
            continue
        
        ts = data_feed[j, 0]
        if ts < target_ts:
            break
        
        prices.append(data_feed[j, 2])
        timestamps.append(ts)
    
    if len(prices) < 2:
        return 0.0
    
    # 计算30s return序列
    returns = []
    for i in range(len(prices) - 1):
        # 查找30秒前的价格
        target_ts_30s = timestamps[i] - 30 * 1000
        base_price = prices[i]
        
        for k in range(i - 1, -1, -1):
            if timestamps[k] <= target_ts_30s:
                if prices[k] > 0:
                    ret = (prices[i] - prices[k]) / prices[k]
                    returns.append(ret)
                break
    
    if len(returns) == 0:
        return 0.0
    
    # 计算中位值
    returns_array = np.array(returns)
    return np.median(returns_array)


@njit
def _calculate_future_30s_returns(data_feed):
    """预先计算所有时刻的未来30秒return"""
    future_returns = np.zeros(len(data_feed))
    window_ms = 30 * 1000
    
    for i in range(len(data_feed)):
        if data_feed[i, 4] == 0:
            continue
        
        current_ts = data_feed[i, 0]
        current_price = data_feed[i, 2]
        target_ts = current_ts + window_ms
        
        future_price = current_price
        found = False
        
        for j in range(i + 1, len(data_feed)):
            if data_feed[j, 4] == 0:
                continue
            
            if data_feed[j, 0] >= target_ts:
                future_price = data_feed[j, 2]
                found = True
                break
        
        if not found and i < len(data_feed) - 1:
            for j in range(len(data_feed) - 1, i, -1):
                if data_feed[j, 4] != 0:
                    future_price = data_feed[j, 2]
                    break
        
        if current_price > 0:
            future_returns[i] = (future_price - current_price) / current_price
    
    return future_returns


@njit
def _calculate_return_percentiles(returns_array, percentiles):
    """计算return序列的分位数"""
    if len(returns_array) == 0:
        return np.zeros(len(percentiles))
    
    sorted_returns = np.sort(returns_array)
    result = np.zeros(len(percentiles))
    
    for i, pct in enumerate(percentiles):
        idx = int(pct * (len(sorted_returns) - 1))
        if idx < 0:
            idx = 0
        elif idx >= len(sorted_returns):
            idx = len(sorted_returns) - 1
        result[i] = sorted_returns[idx]
    
    return result


@njit
def _get_return_percentile_rank(return_value, returns_array):
    """获取return值在序列中的分位数排名（0-1）"""
    if len(returns_array) == 0:
        return 0.5
    
    count_below = 0
    for r in returns_array:
        if r < return_value:
            count_below += 1
    
    return count_below / len(returns_array)


@njit
def _run_backtest_as_model_future_numba(
    # ---- 数据 ----
    data_feed,
    future_30s_returns,  # 预先计算的未来30秒return数组
    # ---- 参数 ----
    base_exposure,
    base_target_pct,
    mini_price_step,
    taker_fee_rate,
    maker_fee_rate,
    open_ratio,
    # ---- AS_MODEL参数 ----
    as_model_buy_distance,
    as_model_sell_distance,
    order_size_pct_min,  # 挂单量占资金的最小百分比（如0.05表示5%）
    order_size_pct_max,  # 挂单量占资金的最大百分比（如0.10表示10%）
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
    基于AS_MODEL不对等挂单的未来数据策略回测函数
    
    策略逻辑：
    1. 每30s更新一次策略决策
    2. 基础挂单距离 = 过去30分钟30s return序列中位值
    3. 根据未来30s return的分位数决定挂单策略：
       - return < 5%: 看空偏卖，short上限3*exposure
       - return 5-10%: short上限2*exposure，买单距离2倍，卖单距离0.5倍
       - return 10-90%: 中性，根据仓位决定不对称性
       - return 90-95%: 看多偏买，long上限2*exposure
       - return > 95%: 看多偏买，long上限3*exposure
    """
    # 内部状态变量
    cash = initial_cash
    pos = initial_pos
    avg_cost_price = 0.0
    taker_fee = 0.0
    maker_fee = 0.0
    
    # 动态exposure和target_pct
    current_exposure = base_exposure
    current_target_pct = base_target_pct
    
    # 挂单状态
    buy_order = np.zeros(8)
    sell_order = np.zeros(8)
    is_buy_order_active = False
    is_sell_order_active = False
    
    # 结果数组的索引
    accounts_idx = 0
    stats_idx = 0
    
    last_mark_price = data_feed[0, 2] if len(data_feed) > 0 else 0.0
    
    # 30s决策间隔相关
    last_decision_ts = -1
    decision_interval_ms = 30 * 1000  # 30秒
    
    # 价格历史（用于计算过去30分钟return中位值）
    max_history_size = 10000
    price_history = np.zeros(max_history_size)
    timestamp_history = np.zeros(max_history_size, dtype=np.int64)
    price_history_size = 0
    price_history_idx = 0
    
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
    
    # 过去30分钟30s return序列（用于计算分位数）
    max_return_history_size = 60  # 30分钟 = 60个30秒
    return_history_30min = np.zeros(max_return_history_size)
    return_history_size = 0
    
    for i in range(data_feed.shape[0]):
        line = data_feed[i]
        now_ts, order_side, trade_price, trade_quantity, mm_flag = line[0], line[1], line[2], line[3], line[4]
        
        # 更新标记价格和历史
        if mm_flag != 0:
            last_mark_price = trade_price
            
            # 更新价格历史
            if price_history_size < max_history_size:
                price_history[price_history_size] = trade_price
                timestamp_history[price_history_size] = now_ts
                price_history_size += 1
            else:
                # 循环覆盖
                price_history[price_history_idx] = trade_price
                timestamp_history[price_history_idx] = now_ts
                price_history_idx = (price_history_idx + 1) % max_history_size
        
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
        
        pos_value = abs(pos * last_mark_price)
        
        # 2. 检查并处理挂单的撮合 (Maker Trade)
        # 2.1 买单撮合
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
        
        # 2.2 卖单撮合
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
        
        # 3. 30s决策间隔检查：只在每30s更新一次策略决策
        if mm_flag != 0 and (now_ts - last_decision_ts >= decision_interval_ms or last_decision_ts < 0):
            last_decision_ts = now_ts
            
            # 3.1 更新过去30分钟30s return序列
            if price_history_size >= 2:
                # 计算过去30分钟的return序列
                window_ms = 30 * 60 * 1000
                target_ts = now_ts - window_ms
                
                recent_returns = np.zeros(max_return_history_size)
                recent_returns_size = 0
                
                # 从最新价格开始向前查找
                if price_history_size < max_history_size:
                    # 未满，直接使用
                    start_idx = price_history_size - 1
                    for j in range(start_idx, 0, -1):
                        if timestamp_history[j] < target_ts:
                            break
                        
                        # 查找30秒前的价格
                        target_ts_30s = timestamp_history[j] - 30 * 1000
                        current_price = price_history[j]
                        
                        for k in range(j - 1, -1, -1):
                            if timestamp_history[k] <= target_ts_30s:
                                if price_history[k] > 0 and current_price > 0:
                                    ret = (current_price - price_history[k]) / price_history[k]
                                    if recent_returns_size < max_return_history_size:
                                        recent_returns[recent_returns_size] = ret
                                        recent_returns_size += 1
                                break
                else:
                    # 已满，使用循环索引
                    start_idx = (price_history_idx - 1 + max_history_size) % max_history_size
                    for j_offset in range(price_history_size - 1):
                        j = (start_idx - j_offset + max_history_size) % max_history_size
                        
                        if timestamp_history[j] < target_ts:
                            break
                        
                        # 查找30秒前的价格
                        target_ts_30s = timestamp_history[j] - 30 * 1000
                        current_price = price_history[j]
                        
                        for k_offset in range(1, j_offset + 1):
                            k = (start_idx - k_offset + max_history_size) % max_history_size
                            if timestamp_history[k] <= target_ts_30s:
                                if price_history[k] > 0 and current_price > 0:
                                    ret = (current_price - price_history[k]) / price_history[k]
                                    if recent_returns_size < max_return_history_size:
                                        recent_returns[recent_returns_size] = ret
                                        recent_returns_size += 1
                                break
                
                # 更新return历史
                for idx in range(recent_returns_size):
                    if idx < max_return_history_size:
                        return_history_30min[idx] = recent_returns[idx]
                return_history_size = recent_returns_size if recent_returns_size < max_return_history_size else max_return_history_size
            
            # 3.2 计算基础挂单距离（过去30分钟30s return序列中位值）
            base_spread_pct = 0.0
            if return_history_size > 0:
                abs_returns = np.abs(return_history_30min[:return_history_size])
                base_spread_pct = np.median(abs_returns)
            
            # 如果中位值为0，使用默认值
            if base_spread_pct <= 0:
                base_spread_pct = 0.000419  # 默认spread
            
            # 3.3 获取未来30s return和分位数排名
            future_30s_return = future_30s_returns[i] if i < len(future_30s_returns) else 0.0
            
            # 计算分位数排名
            return_percentile_rank = 0.5
            if return_history_size > 0:
                returns_array = return_history_30min[:return_history_size]
                return_percentile_rank = _get_return_percentile_rank(future_30s_return, returns_array)
            
            # 3.4 根据分位数决定策略
            # 恢复初始exposure和target_pct
            current_exposure = base_exposure
            current_target_pct = base_target_pct
            
            # 计算AS_MODEL基础距离和量
            base_buy_distance_pct = base_spread_pct * as_model_buy_distance
            base_sell_distance_pct = base_spread_pct * as_model_sell_distance
            
            # 根据当前资金计算挂单量（5%-10%之间）
            current_equity = cash + pos * last_mark_price
            base_order_size_usdt = current_equity * order_size_pct_min  # 最小5%
            max_order_size_usdt = current_equity * order_size_pct_max  # 最大10%
            
            # 根据as_model不确定性调整挂单量
            # 基础量使用最小百分比，然后根据as_model调整
            base_buy_volume_usdt = base_order_size_usdt * as_model_buy_distance
            base_sell_volume_usdt = base_order_size_usdt * as_model_sell_distance
            
            # 限制在5%-10%之间
            base_buy_volume_usdt = min(max(base_buy_volume_usdt, base_order_size_usdt), max_order_size_usdt)
            base_sell_volume_usdt = min(max(base_sell_volume_usdt, base_order_size_usdt), max_order_size_usdt)
            
            # 转换为数量
            base_buy_volume = base_buy_volume_usdt / last_mark_price if last_mark_price > 0 else 0.0
            base_sell_volume = base_sell_volume_usdt / last_mark_price if last_mark_price > 0 else 0.0
            
            # 根据分位数调整
            if return_percentile_rank < 0.05:
                # return < 5%: 看空偏卖
                current_exposure = base_exposure * 3
                current_target_pct = base_target_pct
                
                # 取消买单
                if is_buy_order_active:
                    lifecycle_ms = now_ts - buy_order[7]
                    place_origin_volume = buy_order[5] + buy_order[3]
                    place_orders_stats_log[stats_idx] = [buy_order[7], lifecycle_ms, buy_order[1], 1, place_origin_volume, buy_order[5], buy_order[6], buy_order[4], 3, 1, 0, 0, 0]
                    stats_idx += 1
                    is_buy_order_active = False
                
                # 卖单挂盘口位置
                if not is_sell_order_active:
                    sell_price = last_mark_price + mini_price_step
                    sell_order = np.array([now_ts, sell_price, -1, base_sell_volume, sell_price, 0.0, 0.0, now_ts])
                    is_sell_order_active = True
                else:
                    # 更新卖单到盘口
                    sell_order[1] = last_mark_price + mini_price_step
                    sell_order[0] = now_ts
            
            elif return_percentile_rank < 0.10:
                # return 5-10%: short上限2*exposure
                current_exposure = base_exposure * 2
                current_target_pct = base_target_pct
                
                # 买单距离2倍，卖单距离0.5倍，买量0.5倍，卖量2倍
                buy_distance_pct = base_buy_distance_pct * 2
                sell_distance_pct = base_sell_distance_pct * 0.5
                
                # 调整挂单量，但限制在5%-10%范围内
                buy_volume_usdt = base_buy_volume_usdt * 0.5
                sell_volume_usdt = base_sell_volume_usdt * 2
                buy_volume_usdt = min(max(buy_volume_usdt, base_order_size_usdt), max_order_size_usdt)
                sell_volume_usdt = min(max(sell_volume_usdt, base_order_size_usdt), max_order_size_usdt)
                
                buy_volume = buy_volume_usdt / last_mark_price if last_mark_price > 0 else 0.0
                sell_volume = sell_volume_usdt / last_mark_price if last_mark_price > 0 else 0.0
                
                # 更新或创建挂单
                if not is_buy_order_active:
                    buy_price = last_mark_price * (1 - buy_distance_pct)
                    buy_order = np.array([now_ts, buy_price, 1, buy_volume, buy_price, 0.0, 0.0, now_ts])
                    is_buy_order_active = True
                else:
                    buy_order[1] = last_mark_price * (1 - buy_distance_pct)
                    buy_order[3] = buy_volume
                    buy_order[0] = now_ts
                
                if not is_sell_order_active:
                    sell_price = last_mark_price * (1 + sell_distance_pct)
                    sell_order = np.array([now_ts, sell_price, -1, sell_volume, sell_price, 0.0, 0.0, now_ts])
                    is_sell_order_active = True
                else:
                    sell_order[1] = last_mark_price * (1 + sell_distance_pct)
                    sell_order[3] = sell_volume
                    sell_order[0] = now_ts
            
            elif return_percentile_rank < 0.90:
                # return 10-90%: 中性，根据当前仓位决定不对称性
                # 简化：使用基础AS_MODEL
                buy_distance_pct = base_buy_distance_pct
                sell_distance_pct = base_sell_distance_pct
                buy_volume = base_buy_volume
                sell_volume = base_sell_volume
                
                # 根据仓位调整（如果仓位偏向一边，减少该方向的挂单）
                # 但确保调整后的量仍然在5%-10%范围内
                if pos > 0:
                    # 多头仓位，减少买单量，增加卖单量
                    buy_volume_usdt = base_buy_volume_usdt * 0.8
                    sell_volume_usdt = base_sell_volume_usdt * 1.2
                elif pos < 0:
                    # 空头仓位，减少卖单量，增加买单量
                    buy_volume_usdt = base_buy_volume_usdt * 1.2
                    sell_volume_usdt = base_sell_volume_usdt * 0.8
                else:
                    buy_volume_usdt = base_buy_volume_usdt
                    sell_volume_usdt = base_sell_volume_usdt
                
                # 严格限制在5%-10%范围内
                buy_volume_usdt = min(max(buy_volume_usdt, base_order_size_usdt), max_order_size_usdt)
                sell_volume_usdt = min(max(sell_volume_usdt, base_order_size_usdt), max_order_size_usdt)
                
                buy_volume = buy_volume_usdt / last_mark_price if last_mark_price > 0 else 0.0
                sell_volume = sell_volume_usdt / last_mark_price if last_mark_price > 0 else 0.0
                
                # 验证：确保挂单量在5%-10%范围内
                buy_volume_usdt_actual = buy_volume * last_mark_price if last_mark_price > 0 else 0.0
                sell_volume_usdt_actual = sell_volume * last_mark_price if last_mark_price > 0 else 0.0
                
                if buy_volume_usdt_actual > max_order_size_usdt:
                    buy_volume = max_order_size_usdt / last_mark_price if last_mark_price > 0 else 0.0
                if sell_volume_usdt_actual > max_order_size_usdt:
                    sell_volume = max_order_size_usdt / last_mark_price if last_mark_price > 0 else 0.0
                
                if not is_buy_order_active:
                    buy_price = last_mark_price * (1 - buy_distance_pct)
                    buy_order = np.array([now_ts, buy_price, 1, buy_volume, buy_price, 0.0, 0.0, now_ts])
                    is_buy_order_active = True
                else:
                    buy_order[1] = last_mark_price * (1 - buy_distance_pct)
                    buy_order[3] = buy_volume
                    buy_order[0] = now_ts
                
                if not is_sell_order_active:
                    sell_price = last_mark_price * (1 + sell_distance_pct)
                    sell_order = np.array([now_ts, sell_price, -1, sell_volume, sell_price, 0.0, 0.0, now_ts])
                    is_sell_order_active = True
                else:
                    sell_order[1] = last_mark_price * (1 + sell_distance_pct)
                    sell_order[3] = sell_volume
                    sell_order[0] = now_ts
            
            elif return_percentile_rank < 0.95:
                # return 90-95%: 看多偏买，long上限2*exposure
                current_exposure = base_exposure * 2
                current_target_pct = base_target_pct
                
                # 类似卖的逻辑，但方向相反
                # 取消卖单
                if is_sell_order_active:
                    lifecycle_ms = now_ts - sell_order[7]
                    place_origin_volume = sell_order[5] + sell_order[3]
                    place_orders_stats_log[stats_idx] = [sell_order[7], lifecycle_ms, sell_order[1], -1, place_origin_volume, sell_order[5], sell_order[6], sell_order[4], 3, 1, 0, 0, 0]
                    stats_idx += 1
                    is_sell_order_active = False
                
                # 买单挂盘口位置
                if not is_buy_order_active:
                    buy_price = last_mark_price - mini_price_step
                    buy_order = np.array([now_ts, buy_price, 1, base_buy_volume, buy_price, 0.0, 0.0, now_ts])
                    is_buy_order_active = True
                else:
                    buy_order[1] = last_mark_price - mini_price_step
                    buy_order[0] = now_ts
            
            else:
                # return > 95%: 看多偏买，long上限3*exposure
                current_exposure = base_exposure * 3
                current_target_pct = base_target_pct
                
                # 取消卖单
                if is_sell_order_active:
                    lifecycle_ms = now_ts - sell_order[7]
                    place_origin_volume = sell_order[5] + sell_order[3]
                    place_orders_stats_log[stats_idx] = [sell_order[7], lifecycle_ms, sell_order[1], -1, place_origin_volume, sell_order[5], sell_order[6], sell_order[4], 3, 1, 0, 0, 0]
                    stats_idx += 1
                    is_sell_order_active = False
                
                # 买单挂盘口位置
                if not is_buy_order_active:
                    buy_price = last_mark_price - mini_price_step
                    buy_order = np.array([now_ts, buy_price, 1, base_buy_volume, buy_price, 0.0, 0.0, now_ts])
                    is_buy_order_active = True
                else:
                    buy_order[1] = last_mark_price - mini_price_step
                    buy_order[0] = now_ts
            
            # 3.5 风险控制：根据动态exposure进行对冲（优先使用maker，减少taker）
            hedge_threshold = current_exposure * current_target_pct
            if pos_value > hedge_threshold:
                target_pos_value = current_exposure * current_target_pct * np.sign(pos) if pos != 0 else 0.0
                hedge_volume = abs(pos - target_pos_value / last_mark_price) if last_mark_price > 0 else 0.0
                
                if hedge_volume > 1e-8:
                    hedge_side = -np.sign(pos - target_pos_value / last_mark_price)
                    
                    # 优先使用maker订单对冲，而不是taker
                    # 策略：调整挂单，让对冲方向的订单更容易成交
                    if hedge_side < 0:  # 需要卖出对冲（多头仓位过大）
                        # 取消买单，卖单挂盘口位置（更容易成交）
                        if is_buy_order_active:
                            lifecycle_ms = now_ts - buy_order[7]
                            place_origin_volume = buy_order[5] + buy_order[3]
                            place_orders_stats_log[stats_idx] = [buy_order[7], lifecycle_ms, buy_order[1], 1, place_origin_volume, buy_order[5], buy_order[6], buy_order[4], 4, 1, 0, 0, 0]
                            stats_idx += 1
                            is_buy_order_active = False
                        
                        # 卖单挂盘口位置，但挂单量仍然控制在5%-10%范围内
                        # 使用最大允许的挂单量（10%资金）以加速对冲
                        hedge_order_size_usdt = max_order_size_usdt  # 使用最大允许的挂单量（10%）
                        hedge_order_volume = hedge_order_size_usdt / last_mark_price if last_mark_price > 0 else 0.0
                        
                        if not is_sell_order_active:
                            sell_price = last_mark_price + mini_price_step
                            sell_order = np.array([now_ts, sell_price, -1, hedge_order_volume, sell_price, 0.0, 0.0, now_ts])
                            is_sell_order_active = True
                        else:
                            # 更新卖单到盘口，但限制挂单量在10%以内
                            sell_order[1] = last_mark_price + mini_price_step
                            sell_order[3] = min(max(sell_order[3], hedge_order_volume), hedge_order_volume)  # 限制在10%以内
                            sell_order[0] = now_ts
                    
                    elif hedge_side > 0:  # 需要买入对冲（空头仓位过大）
                        # 取消卖单，买单挂盘口位置（更容易成交）
                        if is_sell_order_active:
                            lifecycle_ms = now_ts - sell_order[7]
                            place_origin_volume = sell_order[5] + sell_order[3]
                            place_orders_stats_log[stats_idx] = [sell_order[7], lifecycle_ms, sell_order[1], -1, place_origin_volume, sell_order[5], sell_order[6], sell_order[4], 4, 1, 0, 0, 0]
                            stats_idx += 1
                            is_sell_order_active = False
                        
                        # 买单挂盘口位置，但挂单量仍然控制在5%-10%范围内
                        # 使用最大允许的挂单量（10%资金）以加速对冲
                        hedge_order_size_usdt = max_order_size_usdt  # 使用最大允许的挂单量（10%）
                        hedge_order_volume = hedge_order_size_usdt / last_mark_price if last_mark_price > 0 else 0.0
                        
                        if not is_buy_order_active:
                            buy_price = last_mark_price - mini_price_step
                            buy_order = np.array([now_ts, buy_price, 1, hedge_order_volume, buy_price, 0.0, 0.0, now_ts])
                            is_buy_order_active = True
                        else:
                            # 更新买单到盘口，但限制挂单量在10%以内
                            buy_order[1] = last_mark_price - mini_price_step
                            buy_order[3] = min(max(buy_order[3], hedge_order_volume), hedge_order_volume)  # 限制在10%以内
                            buy_order[0] = now_ts
                    
                    # 只有在仓位严重超标时才使用taker对冲（超过2倍exposure）
                    if pos_value > current_exposure * 2:
                        # 使用taker紧急对冲
                        hedge_price = last_mark_price + hedge_side * mini_price_step * 2
                        
                        # 撤单
                        if is_buy_order_active:
                            lifecycle_ms = now_ts - buy_order[7]
                            place_origin_volume = buy_order[5] + buy_order[3]
                            place_orders_stats_log[stats_idx] = [buy_order[7], lifecycle_ms, buy_order[1], 1, place_origin_volume, buy_order[5], buy_order[6], buy_order[4], 4, 1, 0, 0, 0]
                            stats_idx += 1
                            is_buy_order_active = False
                        
                        if is_sell_order_active:
                            lifecycle_ms = now_ts - sell_order[7]
                            place_origin_volume = sell_order[5] + sell_order[3]
                            place_orders_stats_log[stats_idx] = [sell_order[7], lifecycle_ms, sell_order[1], -1, place_origin_volume, sell_order[5], sell_order[6], sell_order[4], 4, 1, 0, 0, 0]
                            stats_idx += 1
                            is_sell_order_active = False
                        
                        # 执行taker对冲
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
    
    return accounts_idx, stats_idx

