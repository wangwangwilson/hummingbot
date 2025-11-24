"""策略运行指标提取模块，用于策略优化指导"""
import numpy as np
from typing import Dict, Any, Optional
from datetime import datetime


def extract_strategy_metrics(
    accounts: np.ndarray,
    place_orders_stats: np.ndarray,
    performance: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    提取策略运行的关键指标，用于策略优化指导
    
    Args:
        accounts: 账户数据数组
        place_orders_stats: 订单统计数据数组
        performance: 性能指标字典（可选）
    
    Returns:
        策略指标字典
    """
    if accounts.size == 0:
        return {}
    
    # 提取账户数据
    timestamps = accounts[:, 0]
    cash = accounts[:, 1]
    pos = accounts[:, 2]
    trade_price = accounts[:, 4]
    trade_quantity = accounts[:, 5]
    order_side = accounts[:, 6]
    taker_fee = accounts[:, 7]
    maker_fee = accounts[:, 8]
    order_role = accounts[:, 9]
    
    # 1. 仓位相关指标
    pos_values = pos * trade_price
    max_pos_value = float(np.max(np.abs(pos_values)))
    avg_pos_value = float(np.mean(np.abs(pos_values[pos_values != 0]))) if np.any(pos_values != 0) else 0.0
    min_pos_value = float(np.min(np.abs(pos_values[pos_values != 0]))) if np.any(pos_values != 0) else 0.0
    
    # 多空比（基于仓位价值）
    long_pos_value = np.sum(pos_values[pos_values > 0])
    short_pos_value = np.abs(np.sum(pos_values[pos_values < 0]))
    long_short_ratio = float(long_pos_value / short_pos_value) if short_pos_value > 0 else (float('inf') if long_pos_value > 0 else 0.0)
    
    # 多空时间占比
    long_time_pct = float(np.sum(pos > 0) / len(pos) * 100) if len(pos) > 0 else 0.0
    short_time_pct = float(np.sum(pos < 0) / len(pos) * 100) if len(pos) > 0 else 0.0
    neutral_time_pct = float(np.sum(pos == 0) / len(pos) * 100) if len(pos) > 0 else 0.0
    
    # 2. 订单相关指标
    # 挂单统计
    place_order_mask = (order_role == 1)  # Taker下单
    place_order_count = int(np.sum(place_order_mask))
    
    # 撤单统计
    revoke_order_mask = (order_role == 3)  # 撤单
    revoke_order_count = int(np.sum(revoke_order_mask))
    
    # 挂撤单频率
    if len(timestamps) > 1:
        total_time_hours = (timestamps[-1] - timestamps[0]) / (1000 * 3600)
        place_order_freq = float(place_order_count / total_time_hours) if total_time_hours > 0 else 0.0
        revoke_order_freq = float(revoke_order_count / total_time_hours) if total_time_hours > 0 else 0.0
    else:
        place_order_freq = 0.0
        revoke_order_freq = 0.0
    
    # 挂撤单间隔（平均）
    if place_order_count > 1:
        place_order_timestamps = timestamps[place_order_mask]
        place_order_intervals = np.diff(np.sort(place_order_timestamps)) / 1000  # 转换为秒
        avg_place_interval_sec = float(np.mean(place_order_intervals)) if len(place_order_intervals) > 0 else 0.0
        median_place_interval_sec = float(np.median(place_order_intervals)) if len(place_order_intervals) > 0 else 0.0
    else:
        avg_place_interval_sec = 0.0
        median_place_interval_sec = 0.0
    
    if revoke_order_count > 1:
        revoke_order_timestamps = timestamps[revoke_order_mask]
        revoke_order_intervals = np.diff(np.sort(revoke_order_timestamps)) / 1000  # 转换为秒
        avg_revoke_interval_sec = float(np.mean(revoke_order_intervals)) if len(revoke_order_intervals) > 0 else 0.0
        median_revoke_interval_sec = float(np.median(revoke_order_intervals)) if len(revoke_order_intervals) > 0 else 0.0
    else:
        avg_revoke_interval_sec = 0.0
        median_revoke_interval_sec = 0.0
    
    # 3. 成交相关指标
    # Maker/Taker成交统计
    maker_trade_mask = (order_role == 2)  # Maker成交
    taker_trade_mask = (order_role == 0)  # Taker成交（真实成交）
    
    maker_trade_count = int(np.sum(maker_trade_mask))
    taker_trade_count = int(np.sum(taker_trade_mask))
    total_trade_count = maker_trade_count + taker_trade_count
    
    maker_taker_ratio = float(maker_trade_count / taker_trade_count) if taker_trade_count > 0 else (float('inf') if maker_trade_count > 0 else 0.0)
    
    # 成交订单多空比
    long_trades = np.sum(order_side > 0)
    short_trades = np.sum(order_side < 0)
    trade_long_short_ratio = float(long_trades / short_trades) if short_trades > 0 else (float('inf') if long_trades > 0 else 0.0)
    
    # 成交率（从place_orders_stats计算）
    if place_orders_stats.size > 0:
        # place_orders_stats格式: [place_time, lifecycle_ms, price, side, origin_volume, finish_volume, avg_match_price, initial_price, order_role, finish_type, ...]
        origin_volumes = place_orders_stats[:, 4]
        finish_volumes = place_orders_stats[:, 5]
        
        # 过滤掉无效数据
        valid_mask = (origin_volumes > 0) & (finish_volumes >= 0)
        if np.any(valid_mask):
            fill_rates = finish_volumes[valid_mask] / origin_volumes[valid_mask]
            avg_fill_rate = float(np.mean(fill_rates))
            median_fill_rate = float(np.median(fill_rates))
            min_fill_rate = float(np.min(fill_rates))
            max_fill_rate = float(np.max(fill_rates))
        else:
            avg_fill_rate = 0.0
            median_fill_rate = 0.0
            min_fill_rate = 0.0
            max_fill_rate = 0.0
    else:
        avg_fill_rate = 0.0
        median_fill_rate = 0.0
        min_fill_rate = 0.0
        max_fill_rate = 0.0
    
    # 4. 盈利分析（多空分离）
    # 计算每笔交易的PnL
    pnl_with_fee = np.zeros(len(accounts))
    for i in range(1, len(accounts)):
        prev_cash = accounts[i-1, 1]
        prev_pos = accounts[i-1, 2]
        prev_price = accounts[i-1, 4]
        prev_taker_fee = accounts[i-1, 7]
        prev_maker_fee = accounts[i-1, 8]
        
        curr_cash = accounts[i, 1]
        curr_pos = accounts[i, 2]
        curr_price = accounts[i, 4]
        curr_taker_fee = accounts[i, 7]
        curr_maker_fee = accounts[i, 8]
        
        # PnL = 现金变化 + 仓位价值变化 - 手续费变化
        cash_change = curr_cash - prev_cash
        pos_value_change = (curr_pos * curr_price) - (prev_pos * prev_price)
        fee_change = (curr_taker_fee + curr_maker_fee) - (prev_taker_fee + prev_maker_fee)
        pnl_with_fee[i] = cash_change + pos_value_change - fee_change
    
    # 分离多空交易
    long_trade_mask = order_side > 0
    short_trade_mask = order_side < 0
    
    long_pnl = np.sum(pnl_with_fee[long_trade_mask])
    short_pnl = np.sum(pnl_with_fee[short_trade_mask])
    
    # Maker/Taker盈利
    maker_pnl = np.sum(pnl_with_fee[maker_trade_mask])
    taker_pnl = np.sum(pnl_with_fee[taker_trade_mask])
    
    # 5. 交易额统计
    trade_value = trade_quantity * trade_price
    maker_trade_value = np.sum(trade_value[maker_trade_mask])
    taker_trade_value = np.sum(trade_value[taker_trade_mask])
    total_trade_value = np.sum(trade_value)
    
    maker_taker_volume_ratio = float(maker_trade_value / taker_trade_value) if taker_trade_value > 0 else (float('inf') if maker_trade_value > 0 else 0.0)
    
    # 6. 手续费统计
    total_taker_fee = float(np.sum(taker_fee))
    total_maker_fee = float(np.sum(maker_fee))
    total_fee = total_taker_fee + total_maker_fee
    
    # 7. 滑点统计（从performance获取，如果有）
    slippage_stats = {}
    if performance and 'order_behavior_metrics' in performance:
        order_behavior = performance['order_behavior_metrics']
        slippage_stats = {
            'avg_slippage_pct': float(order_behavior.get('avg_slippage_pct', 0) * 100),
            'total_slippage_value': float(order_behavior.get('total_slippage_value', 0)),
            'median_slippage_pct': float(order_behavior.get('median_slippage_pct', 0) * 100) if 'median_slippage_pct' in order_behavior else 0.0
        }
    
    # 8. 时间统计
    if len(timestamps) > 0:
        start_time = datetime.fromtimestamp(timestamps[0] / 1000)
        end_time = datetime.fromtimestamp(timestamps[-1] / 1000)
        duration_hours = (timestamps[-1] - timestamps[0]) / (1000 * 3600)
    else:
        start_time = None
        end_time = None
        duration_hours = 0.0
    
    # 组装结果
    metrics = {
        'position_metrics': {
            'max_position_value': max_pos_value,
            'avg_position_value': avg_pos_value,
            'min_position_value': min_pos_value,
            'long_short_ratio': long_short_ratio,
            'long_time_pct': long_time_pct,
            'short_time_pct': short_time_pct,
            'neutral_time_pct': neutral_time_pct
        },
        'order_metrics': {
            'place_order_count': place_order_count,
            'revoke_order_count': revoke_order_count,
            'place_order_freq_per_hour': place_order_freq,
            'revoke_order_freq_per_hour': revoke_order_freq,
            'avg_place_interval_sec': avg_place_interval_sec,
            'median_place_interval_sec': median_place_interval_sec,
            'avg_revoke_interval_sec': avg_revoke_interval_sec,
            'median_revoke_interval_sec': median_revoke_interval_sec
        },
        'trade_metrics': {
            'total_trade_count': int(total_trade_count),
            'maker_trade_count': maker_trade_count,
            'taker_trade_count': taker_trade_count,
            'maker_taker_ratio': maker_taker_ratio,
            'trade_long_short_ratio': trade_long_short_ratio,
            'avg_fill_rate': avg_fill_rate,
            'median_fill_rate': median_fill_rate,
            'min_fill_rate': min_fill_rate,
            'max_fill_rate': max_fill_rate
        },
        'pnl_metrics': {
            'long_pnl': float(long_pnl),
            'short_pnl': float(short_pnl),
            'maker_pnl': float(maker_pnl),
            'taker_pnl': float(taker_pnl),
            'total_pnl': float(np.sum(pnl_with_fee))
        },
        'volume_metrics': {
            'total_trade_value': float(total_trade_value),
            'maker_trade_value': float(maker_trade_value),
            'taker_trade_value': float(taker_trade_value),
            'maker_taker_volume_ratio': maker_taker_volume_ratio
        },
        'fee_metrics': {
            'total_fee': total_fee,
            'total_taker_fee': total_taker_fee,
            'total_maker_fee': total_maker_fee,
            'fee_to_volume_ratio_bps': float(total_fee / total_trade_value * 10000) if total_trade_value > 0 else 0.0
        },
        'slippage_metrics': slippage_stats,
        'time_metrics': {
            'start_time': start_time.isoformat() if start_time else None,
            'end_time': end_time.isoformat() if end_time else None,
            'duration_hours': float(duration_hours)
        }
    }
    
    # 添加performance中的关键指标（如果提供）
    if performance:
        if 'overall_performance' in performance:
            overall = performance['overall_performance']
            metrics['performance_summary'] = {
                'total_pnl_with_fees': float(overall.get('total_pnl_with_fees', 0)),
                'total_pnl_no_fees': float(overall.get('total_pnl_no_fees', 0)),
                'max_drawdown_pct': float(overall.get('max_drawdown', 0) * 100),
                'sharpe_ratio': float(overall.get('sharpe_ratio', 0)) if not np.isnan(overall.get('sharpe_ratio', 0)) else None,
                'calmar_ratio': float(overall.get('calmar_ratio', 0)) if not np.isnan(overall.get('calmar_ratio', 0)) else None
            }
        
        if 'maker_performance' in performance:
            maker_perf = performance['maker_performance']
            metrics['maker_performance'] = {
                'maker_pnl_ratio_bps': float(maker_perf.get('maker_pnl_ratio', 0)),
                'maker_volume_total': float(maker_perf.get('maker_volume_total', 0))
            }
        
        if 'taker_performance' in performance:
            taker_perf = performance['taker_performance']
            metrics['taker_performance'] = {
                'taker_pnl_ratio_bps': float(taker_perf.get('taker_pnl_ratio', 0)),
                'taker_volume_total': float(taker_perf.get('taker_volume_total', 0))
            }
    
    return metrics

