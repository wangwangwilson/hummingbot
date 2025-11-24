"""回测结果统计分析模块"""
import numpy as np
import polars as pl
from typing import Dict


def analyze_performance(
    accounts_raw: np.ndarray, 
    place_orders_stats_raw: np.ndarray
) -> Dict:
    """
    使用NumPy和Polars实现的性能分析函数，大幅提升性能。
    
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
    prev_avg_cost_price[0] = avg_cost_price[0]
    virtual_close_pnl = np.where(
        close_ind,
        -(trade_price - prev_avg_cost_price) * order_side * trade_quantity,
        0.0
    )
    realized_pnl_no_fee = np.cumsum(virtual_close_pnl)
    
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
        if equity_with_fee[0] > 0 and equity_with_fee[-1] > 0:
            annualized_return = ((equity_with_fee[-1] / equity_with_fee[0]) ** (1 / duration_years)) - 1
        elif equity_with_fee[0] < 0 and equity_with_fee[-1] < 0:
            annualized_return = np.nan
        else:
            annualized_return = np.nan

        if not np.isnan(annualized_return) and max_drawdown > 0:
            calmar_ratio = annualized_return / max_drawdown
        elif not np.isnan(annualized_return) and annualized_return > 0 and max_drawdown == 0:
            calmar_ratio = np.inf
    
    # 8. 计算夏普比率 (使用日度数据)
    sharpe_ratio = np.nan
    
    timestamps_days = now_ts // (1000 * 3600 * 24)
    if now_ts.size > 0:
        unique_days, last_indices = np.unique(timestamps_days, return_index=True)
        _, unique_indices_last = np.unique(timestamps_days[::-1], return_index=True)
        daily_equity_indices = (len(timestamps_days) - 1) - unique_indices_last
        daily_equity = equity_with_fee[np.sort(daily_equity_indices)]

        if daily_equity.size > 1:
            daily_returns = np.diff(daily_equity) / daily_equity[:-1]
            
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
    
    # 10. 计算未平仓浮动盈亏（Unrealized PnL）
    # 最终仓位和价格
    final_pos = pos[-1] if pos.size > 0 else 0.0
    final_price = trade_price[-1] if trade_price.size > 0 else 0.0
    final_avg_cost_price = avg_cost_price[-1] if avg_cost_price.size > 0 else 0.0
    
    # 未平仓浮动盈亏 = 最终仓位 * (最终价格 - 平均成本价)
    unrealized_pnl = final_pos * (final_price - final_avg_cost_price) if final_avg_cost_price > 0 else 0.0
    
    # 已实现PnL = Maker PnL + Taker PnL
    realized_pnl_no_fee = maker_pnl_no_fee + taker_pnl_no_fee
    
    # 验证：total_pnl_no_fees 应该等于 realized_pnl_no_fee + unrealized_pnl（理论上）
    # 但由于价格变化、其他交易类型等因素，可能不完全相等
    pnl_reconciliation = total_pnl_no_fees - (realized_pnl_no_fee + unrealized_pnl)
    
    # 10. 订单行为分析
    order_behavior_metrics = {}
    
    if len(place_orders_stats_raw) > 0:
        # 提取订单数据各列
        init_place_ts = place_orders_stats_raw[:, 0]
        lifecycle_ms = place_orders_stats_raw[:, 1]
        last_limit_price = place_orders_stats_raw[:, 2]
        order_side_orders = place_orders_stats_raw[:, 3]
        place_origin_volume = place_orders_stats_raw[:, 4]
        finish_volume = place_orders_stats_raw[:, 5]
        avg_match_trade_price = place_orders_stats_raw[:, 6]
        init_place_order_price = place_orders_stats_raw[:, 7]
        info = place_orders_stats_raw[:, 8]
        
        # 确保数值类型
        revoke_cnt_raw = place_orders_stats_raw[:, 9].astype(np.int64)
        adj_price_cnt_raw = place_orders_stats_raw[:, 10].astype(np.int64)
        desc_volume_cnt_raw = place_orders_stats_raw[:, 11].astype(np.int64)
        asc_volume_cnt_raw = place_orders_stats_raw[:, 12].astype(np.int64)

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
            avg_fill_time_sec = np.mean(lifecycle_ms[have_trade_mask]) / 1000
            median_fill_time_sec = np.median(lifecycle_ms[have_trade_mask]) / 1000
            avg_fill_rate = np.mean(finish_pct[have_trade_mask])
            
            finish_all_mask = finish_pct > 0.9995
            finish_hit_mask = finish_pct > 0.0005
            
            total_trades_count = np.sum(have_trade_mask)
            finish_all_pct = np.sum(finish_all_mask & have_trade_mask) / total_trades_count if total_trades_count > 0 else np.nan
            finish_hit_pct = np.sum(finish_hit_mask & have_trade_mask) / total_trades_count if total_trades_count > 0 else np.nan
            
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
            
            avg_slippage_pct = np.mean(price_slippage_pct[have_trade_mask])
            total_slippage_value = np.sum(price_slippage_value[have_trade_mask])
            
            # API Request Frequency Statistics
            minute_ts = init_place_ts // (60 * 1000)
            
            api_data = {
                'minute_ts': minute_ts.tolist(),
                'order_side': order_side_orders.tolist(),
                'revoke_cnt': revoke_cnt_raw.tolist(),
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
            
            buy_api_stats_df = pl.DataFrame()
            sell_api_stats_df = pl.DataFrame()
            
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
    
    # 11. 资金费统计
    funding_mask = order_role == 6  # info=6表示资金费支付
    funding_fees = np.zeros(len(accounts_raw))
    if np.any(funding_mask):
        # 计算每次资金费支付（通过现金变化）
        funding_indices = np.where(funding_mask)[0]
        for idx in funding_indices:
            if idx > 0:
                # 资金费 = 前一个账户的现金 - 当前账户的现金
                funding_fees[idx] = cash[idx-1] - cash[idx]
            else:
                # 第一条记录，无法计算变化
                funding_fees[idx] = 0.0
        
        total_funding_fee = np.sum(funding_fees)
        # 资金费收入（如果为负，表示支出；如果为正，表示收入）
        funding_income = -total_funding_fee  # 取反，因为是从现金中扣除的
        
        # 计算资金费收入占比（相对于总PnL）
        funding_income_ratio = (funding_income / total_pnl_with_fees * 100) if total_pnl_with_fees != 0 else 0.0
        
        # 计算资金费的交易额收益率（资金费收入 / 总交易额）
        funding_return_rate = (funding_income / total_trade_value * 10000) if total_trade_value > 0 else 0.0  # 转换为万分之几
    else:
        total_funding_fee = 0.0
        funding_income = 0.0
        funding_income_ratio = 0.0
        funding_return_rate = 0.0
    
    # 12. 构建并返回结果字典
    return {
        'overall_performance': {
            'total_pnl_with_fees': float(total_pnl_with_fees),
            'total_pnl_no_fees': float(total_pnl_no_fees),
            'realized_pnl_no_fees': float(realized_pnl_no_fee),  # 已实现PnL = Maker + Taker
            'unrealized_pnl_no_fees': float(unrealized_pnl),  # 未平仓浮动盈亏
            'pnl_reconciliation': float(pnl_reconciliation),  # 差异（应该接近0，但可能由于其他交易类型有差异）
            'final_position': float(final_pos),  # 最终仓位
            'final_price': float(final_price),  # 最终价格
            'final_avg_cost_price': float(final_avg_cost_price),  # 最终平均成本价
            'pnl_with_fees_ratio': float(pnl_with_fees_ratio),
            'pnl_no_fees_ratio': float(pnl_no_fees_ratio),
            'sharpe_ratio': float(sharpe_ratio),
            'max_drawdown': float(max_drawdown),
            'calmar_ratio': float(calmar_ratio),
            'annualized_return': float(annualized_return),
            'duration_years': float(duration_years)
        },
        'maker_performance': {
            'total_maker_pnl_no_fees': float(maker_pnl_no_fee),
            'maker_volume_total': float(maker_volume),
            'maker_pnl_ratio': float(maker_pnl_ratio),
            'maker_pnl_pct_volume': float(maker_pnl_pct_volume),
            'actual_maker_fees_cost_rebate': float(actual_maker_fees)
        },
        'taker_performance': {
            'total_taker_pnl_no_fees': float(taker_pnl_no_fee),
            'taker_volume_total': float(taker_volume),
            'taker_pnl_ratio': float(taker_pnl_ratio),
            'taker_pnl_pct_volume': float(taker_pnl_pct_volume),
            'actual_taker_fees_cost': float(actual_taker_fees)
        },
        'fee_analysis': {
            'total_actual_fees': float(total_fee_cum[-1]) if total_fee_cum.size > 0 else 0.0
        },
        'funding_analysis': {
            'total_funding_fee': float(total_funding_fee),
            'funding_income': float(funding_income),
            'funding_income_ratio': float(funding_income_ratio),  # 资金费收入占比（%）
            'funding_return_rate': float(funding_return_rate)  # 资金费交易额收益率（bps）
        },
        'order_behavior_metrics': order_behavior_metrics
    }

