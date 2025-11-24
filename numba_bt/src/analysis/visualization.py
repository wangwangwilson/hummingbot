"""回测结果可视化模块"""
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.patches import Rectangle
from datetime import datetime
from typing import Optional, Dict, Any


def plot_equity_curve(
    accounts: np.ndarray,
    title: str = "Equity Curve",
    save_path: Optional[str] = None
):
    """
    绘制净值曲线
    
    Args:
        accounts: 账户数据数组，格式 [timestamp, cash, pos, avg_cost, price, qty, side, taker_fee, maker_fee, type]
        title: 图表标题
        save_path: 保存路径，如果为None则显示图表
    """
    timestamps = accounts[:, 0]
    cash = accounts[:, 1]
    pos = accounts[:, 2]
    trade_price = accounts[:, 4]
    taker_fee = accounts[:, 7]
    maker_fee = accounts[:, 8]
    
    # 计算净值
    pos_value = pos * trade_price
    total_fee_cum = taker_fee + maker_fee
    equity = cash + pos_value + total_fee_cum
    
    # 转换为datetime
    dates = [datetime.fromtimestamp(ts / 1000) for ts in timestamps]
    
    fig, axes = plt.subplots(2, 1, figsize=(12, 8), sharex=True)
    
    # 净值曲线
    axes[0].plot(dates, equity, label='Equity', linewidth=1.5)
    axes[0].set_ylabel('Equity')
    axes[0].set_title(title)
    axes[0].legend()
    axes[0].grid(True, alpha=0.3)
    
    # 持仓曲线
    axes[1].plot(dates, pos, label='Position', linewidth=1.5, color='orange')
    axes[1].axhline(y=0, color='black', linestyle='--', alpha=0.3)
    axes[1].set_ylabel('Position')
    axes[1].set_xlabel('Time')
    axes[1].legend()
    axes[1].grid(True, alpha=0.3)
    
    # 格式化x轴日期
    axes[1].xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d %H:%M'))
    plt.xticks(rotation=45)
    
    plt.tight_layout()
    
    if save_path:
        plt.savefig(save_path, dpi=300, bbox_inches='tight')
    else:
        plt.show()
    
    plt.close()


def plot_drawdown(
    accounts: np.ndarray,
    title: str = "Drawdown",
    save_path: Optional[str] = None
):
    """
    绘制回撤曲线
    
    Args:
        accounts: 账户数据数组
        title: 图表标题
        save_path: 保存路径
    """
    timestamps = accounts[:, 0]
    cash = accounts[:, 1]
    pos = accounts[:, 2]
    trade_price = accounts[:, 4]
    taker_fee = accounts[:, 7]
    maker_fee = accounts[:, 8]
    
    # 计算净值
    pos_value = pos * trade_price
    total_fee_cum = taker_fee + maker_fee
    equity = cash + pos_value + total_fee_cum
    
    # 计算回撤
    peak_equity = np.maximum.accumulate(equity)
    drawdown = (equity - peak_equity) / peak_equity * 100
    
    # 转换为datetime
    dates = [datetime.fromtimestamp(ts / 1000) for ts in timestamps]
    
    fig, ax = plt.subplots(figsize=(12, 6))
    ax.fill_between(dates, drawdown, 0, alpha=0.3, color='red', label='Drawdown')
    ax.plot(dates, drawdown, linewidth=1.5, color='red')
    ax.set_ylabel('Drawdown (%)')
    ax.set_xlabel('Time')
    ax.set_title(title)
    ax.legend()
    ax.grid(True, alpha=0.3)
    
    # 格式化x轴日期
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d %H:%M'))
    plt.xticks(rotation=45)
    
    plt.tight_layout()
    
    if save_path:
        plt.savefig(save_path, dpi=300, bbox_inches='tight')
    else:
        plt.show()
    
    plt.close()


def plot_trade_distribution(
    accounts: np.ndarray,
    title: str = "Trade Distribution",
    save_path: Optional[str] = None
):
    """
    绘制交易分布图
    
    Args:
        accounts: 账户数据数组
        title: 图表标题
        save_path: 保存路径
    """
    order_role = accounts[:, 9]
    order_side = accounts[:, 6]
    
    maker_mask = (order_role == 2)
    taker_mask = (order_role == 1)
    
    maker_buy = np.sum((maker_mask) & (order_side == 1))
    maker_sell = np.sum((maker_mask) & (order_side == -1))
    taker_buy = np.sum((taker_mask) & (order_side == 1))
    taker_sell = np.sum((taker_mask) & (order_side == -1))
    
    fig, ax = plt.subplots(figsize=(10, 6))
    
    categories = ['Maker Buy', 'Maker Sell', 'Taker Buy', 'Taker Sell']
    counts = [maker_buy, maker_sell, taker_buy, taker_sell]
    colors = ['green', 'red', 'lightgreen', 'lightcoral']
    
    bars = ax.bar(categories, counts, color=colors, alpha=0.7)
    ax.set_ylabel('Trade Count')
    ax.set_title(title)
    ax.grid(True, alpha=0.3, axis='y')
    
    # 添加数值标签
    for bar in bars:
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., height,
                f'{int(height)}',
                ha='center', va='bottom')
    
    plt.tight_layout()
    
    if save_path:
        plt.savefig(save_path, dpi=300, bbox_inches='tight')
    else:
        plt.show()
    
    plt.close()


def plot_comprehensive_analysis(
    accounts: np.ndarray,
    place_orders_stats: Optional[np.ndarray] = None,
    performance: Optional[Dict[str, Any]] = None,
    title: str = "Comprehensive Backtest Analysis",
    save_path: Optional[str] = None
):
    """
    绘制综合回测分析图表
    
    包含：
    1. 价格和盈亏（双y轴）
    2. 仓位和累计交易额（双y轴）
    3. 订单成交点图（买卖、maker/taker）
    4. 统计指标表格
    
    Args:
        accounts: 账户数据数组
        place_orders_stats: 订单统计数据数组（可选）
        performance: 性能指标字典（可选）
        title: 图表标题
        save_path: 保存路径
    """
    if accounts.size == 0:
        print("⚠️  账户数据为空，无法绘制图表")
        return
    
    # 提取数据
    timestamps = accounts[:, 0]
    cash = accounts[:, 1]
    pos = accounts[:, 2]
    trade_price = accounts[:, 4]
    trade_quantity = accounts[:, 5]
    order_side = accounts[:, 6]
    taker_fee = accounts[:, 7]
    maker_fee = accounts[:, 8]
    order_role = accounts[:, 9]
    
    # 转换为datetime
    dates = [datetime.fromtimestamp(ts / 1000) for ts in timestamps]
    
    # 计算净值
    pos_value = pos * trade_price
    total_fee_cum = taker_fee + maker_fee
    equity = cash + pos_value + total_fee_cum
    pnl = np.diff(equity, prepend=equity[0])
    cumulative_pnl = np.cumsum(pnl)
    
    # 计算累计交易额
    trade_value = trade_quantity * trade_price
    cumulative_trade_value = np.cumsum(trade_value)
    
    # 分离maker和taker的累计交易额
    maker_mask = (order_role == 2)
    taker_mask = (order_role == 1)
    
    maker_trade_value = np.where(maker_mask, trade_value, 0)
    taker_trade_value = np.where(taker_mask, trade_value, 0)
    
    cumulative_maker_volume = np.cumsum(maker_trade_value)
    cumulative_taker_volume = np.cumsum(taker_trade_value)
    
    # 创建图表布局 - 增加高度，特别是表格部分，增加资金费图表
    fig = plt.figure(figsize=(20, 28))  # 增加整体高度以容纳4列表格
    gs = fig.add_gridspec(6, 2, height_ratios=[2.5, 2.5, 2.5, 2.5, 2, 5], hspace=0.4, wspace=0.3)  # 增加表格高度比例到5
    
    # 1. 价格和盈亏图（双y轴）- 占据第一行两列
    ax1 = fig.add_subplot(gs[0, :])
    ax1_twin = ax1.twinx()
    
    # 计算不含手续费的盈亏
    equity_no_fee = cash + pos_value
    pnl_no_fee = np.diff(equity_no_fee, prepend=equity_no_fee[0])
    cumulative_pnl_no_fee = np.cumsum(pnl_no_fee)
    
    line1 = ax1.plot(dates, trade_price, label='Price', color='blue', linewidth=1, alpha=0.7)
    line2 = ax1_twin.plot(dates, cumulative_pnl, label='Cumulative PnL (with fees)', color='orange', linewidth=1.5)
    line3 = ax1_twin.plot(dates, cumulative_pnl_no_fee, label='Cumulative PnL (no fees)', color='green', linewidth=1.5, linestyle='--', alpha=0.8)
    
    ax1.set_ylabel('Price', color='blue', fontsize=10)
    ax1_twin.set_ylabel('Cumulative PnL', color='orange', fontsize=10)
    ax1.tick_params(axis='y', labelcolor='blue')
    ax1_twin.tick_params(axis='y', labelcolor='orange')
    ax1.set_title('Price & Cumulative PnL', fontsize=11, fontweight='bold')
    ax1.grid(True, alpha=0.3)
    
    # 合并图例
    lines = line1 + line2 + line3
    labels = [l.get_label() for l in lines]
    ax1.legend(lines, labels, loc='upper left', fontsize=9)
    
    # 2. 仓位和累计交易额图（双y轴）- 占据第二行两列
    ax2 = fig.add_subplot(gs[1, :])
    ax2_twin = ax2.twinx()
    
    ax2.plot(dates, pos, label='Position', color='purple', linewidth=1.5)
    ax2.axhline(y=0, color='black', linestyle='--', alpha=0.3, linewidth=0.5)
    
    line3 = ax2_twin.plot(dates, cumulative_maker_volume, label='Cumulative Maker Volume', color='green', linewidth=1, alpha=0.7)
    line4 = ax2_twin.plot(dates, cumulative_taker_volume, label='Cumulative Taker Volume', color='red', linewidth=1, alpha=0.7)
    
    ax2.set_ylabel('Position', color='purple', fontsize=10)
    ax2_twin.set_ylabel('Cumulative Volume', color='green', fontsize=10)
    ax2.tick_params(axis='y', labelcolor='purple')
    ax2_twin.tick_params(axis='y', labelcolor='green')
    ax2.set_title('Position & Cumulative Trading Volume', fontsize=11, fontweight='bold')
    ax2.grid(True, alpha=0.3)
    
    lines2 = line3 + line4
    labels2 = [l.get_label() for l in lines2]
    ax2_twin.legend(lines2, labels2, loc='upper left', fontsize=9)
    
    # 3. 订单成交点图 - 占据第三行两列
    ax3 = fig.add_subplot(gs[2, :])
    
    if accounts.size > 0:
        # 提取有交易的记录
        trade_mask = trade_quantity > 0
        trade_dates = [dates[i] for i in range(len(dates)) if trade_mask[i]]
        trade_prices_plot = trade_price[trade_mask]
        trade_sides = order_side[trade_mask]
        trade_roles = order_role[trade_mask]
        trade_values = trade_value[trade_mask]
        
        # 归一化订单大小（用于标记大小）- 使用更强的对数缩放，让两级分化更明显，整体缩小
        if trade_values.size > 0:
            min_value = np.min(trade_values)
            max_value = np.max(trade_values)
            if max_value > min_value and min_value > 0:
                # 使用更强的对数缩放，让大小分化更明显
                log_min = np.log10(min_value)
                log_max = np.log10(max_value)
                log_values = np.log10(trade_values)
                # 使用平方根进一步强化分化，整体缩小：小额订单（3-20），大额订单（20-80）
                normalized_ratio = (log_values - log_min) / (log_max - log_min)
                # 使用平方根让分化更明显
                normalized_ratio_sqrt = np.sqrt(normalized_ratio)
                normalized_sizes = 3 + 77 * normalized_ratio_sqrt
            elif max_value > min_value:
                # 如果有0值，使用线性缩放但范围更小，整体缩小
                normalized_ratio = (trade_values - min_value) / (max_value - min_value)
                # 使用平方根强化分化
                normalized_ratio_sqrt = np.sqrt(normalized_ratio)
                normalized_sizes = 2 + 48 * normalized_ratio_sqrt
            else:
                normalized_sizes = np.full(len(trade_values), 15)
        else:
            normalized_sizes = np.array([])
        
        # 分类绘制
        # Maker Buy (绿色圆形)
        maker_buy_mask = (trade_roles == 2) & (trade_sides == 1)
        if np.any(maker_buy_mask):
            maker_buy_dates = [trade_dates[i] for i in range(len(trade_dates)) if maker_buy_mask[i]]
            maker_buy_prices = trade_prices_plot[maker_buy_mask]
            maker_buy_sizes = normalized_sizes[maker_buy_mask]
            ax3.scatter(maker_buy_dates, maker_buy_prices, s=maker_buy_sizes, 
                       c='green', marker='o', alpha=0.6, label='Maker Buy', edgecolors='darkgreen', linewidths=0.5)
        
        # Maker Sell (红色圆形)
        maker_sell_mask = (trade_roles == 2) & (trade_sides == -1)
        if np.any(maker_sell_mask):
            maker_sell_dates = [trade_dates[i] for i in range(len(trade_dates)) if maker_sell_mask[i]]
            maker_sell_prices = trade_prices_plot[maker_sell_mask]
            maker_sell_sizes = normalized_sizes[maker_sell_mask]
            ax3.scatter(maker_sell_dates, maker_sell_prices, s=maker_sell_sizes,
                       c='red', marker='o', alpha=0.6, label='Maker Sell', edgecolors='darkred', linewidths=0.5)
        
        # Taker Buy (绿色三角形)
        taker_buy_mask = (trade_roles == 1) & (trade_sides == 1)
        if np.any(taker_buy_mask):
            taker_buy_dates = [trade_dates[i] for i in range(len(trade_dates)) if taker_buy_mask[i]]
            taker_buy_prices = trade_prices_plot[taker_buy_mask]
            taker_buy_sizes = normalized_sizes[taker_buy_mask]
            ax3.scatter(taker_buy_dates, taker_buy_prices, s=taker_buy_sizes,
                       c='green', marker='^', alpha=0.6, label='Taker Buy', edgecolors='darkgreen', linewidths=0.5)
        
        # Taker Sell (红色三角形)
        taker_sell_mask = (trade_roles == 1) & (trade_sides == -1)
        if np.any(taker_sell_mask):
            taker_sell_dates = [trade_dates[i] for i in range(len(trade_dates)) if taker_sell_mask[i]]
            taker_sell_prices = trade_prices_plot[taker_sell_mask]
            taker_sell_sizes = normalized_sizes[taker_sell_mask]
            ax3.scatter(taker_sell_dates, taker_sell_prices, s=taker_sell_sizes,
                       c='red', marker='v', alpha=0.6, label='Taker Sell', edgecolors='darkred', linewidths=0.5)
        
        # 忽略Blofin trades，不绘制
    
    ax3.set_ylabel('Price', fontsize=10)
    ax3.set_xlabel('Time', fontsize=10)
    ax3.set_title('Trade Execution Scatter Plot', fontsize=11, fontweight='bold')
    ax3.grid(True, alpha=0.3)
    ax3.legend(loc='upper left', fontsize=8, ncol=3)
    
    # 格式化x轴日期
    for ax in [ax1, ax2, ax3]:
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d %H:%M'))
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha='right')
    
    # 4. 资金费率和累计收益图（双y轴）- 占据第四行两列
    ax4_funding = fig.add_subplot(gs[3, :])
    ax4_funding_twin = ax4_funding.twinx()
    
    # 提取资金费数据（info=6）
    funding_mask = order_role == 6
    if np.any(funding_mask):
        funding_timestamps = timestamps[funding_mask]
        funding_dates = [datetime.fromtimestamp(ts / 1000) for ts in funding_timestamps]
        
        # 计算每次资金费支付（通过现金变化）
        funding_fees = np.zeros(np.sum(funding_mask))
        funding_indices = np.where(funding_mask)[0]
        for i, idx in enumerate(funding_indices):
            if idx > 0:
                funding_fees[i] = cash[idx-1] - cash[idx]  # 资金费 = 前一个账户的现金 - 当前账户的现金
            else:
                funding_fees[i] = 0.0
        
        # 计算累计资金费收益（取反，因为是从现金中扣除的）
        cumulative_funding_income = -np.cumsum(funding_fees)
        
        # 从performance中获取资金费率数据（如果有的话）
        # 如果没有，我们使用一个简单的估算：资金费率 = 资金费 / 仓位价值
        funding_rates = np.zeros(len(funding_fees))
        for i, idx in enumerate(funding_indices):
            pos_at_funding = pos[idx]
            price_at_funding = trade_price[idx]
            pos_value_at_funding = pos_at_funding * price_at_funding
            if abs(pos_value_at_funding) > 1e-8:
                # 资金费率 = 资金费 / 仓位价值
                funding_rates[i] = funding_fees[i] / pos_value_at_funding
            else:
                funding_rates[i] = 0.0
        
        # 绘制资金费率（左y轴）
        line5 = ax4_funding.plot(funding_dates, funding_rates * 10000, label='Funding Rate (bps)', color='blue', marker='o', markersize=4, linewidth=1, alpha=0.7)
        ax4_funding.set_ylabel('Funding Rate (bps)', color='blue', fontsize=10)
        ax4_funding.tick_params(axis='y', labelcolor='blue')
        ax4_funding.axhline(y=0, color='black', linestyle='--', alpha=0.3, linewidth=0.5)
        
        # 绘制累计资金费收益（右y轴）
        line6 = ax4_funding_twin.plot(funding_dates, cumulative_funding_income, label='Cumulative Funding Income', color='green', marker='s', markersize=4, linewidth=1.5)
        ax4_funding_twin.set_ylabel('Cumulative Funding Income', color='green', fontsize=10)
        ax4_funding_twin.tick_params(axis='y', labelcolor='green')
        ax4_funding_twin.axhline(y=0, color='black', linestyle='--', alpha=0.3, linewidth=0.5)
        
        # 合并图例
        lines_funding = line5 + line6
        labels_funding = [l.get_label() for l in lines_funding]
        ax4_funding.legend(lines_funding, labels_funding, loc='upper left', fontsize=9)
    else:
        ax4_funding.text(0.5, 0.5, 'No Funding Rate Data', ha='center', va='center', transform=ax4_funding.transAxes, fontsize=12)
    
    ax4_funding.set_title('Funding Rate & Cumulative Funding Income', fontsize=11, fontweight='bold')
    ax4_funding.grid(True, alpha=0.3)
    ax4_funding.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d %H:%M'))
    plt.setp(ax4_funding.xaxis.get_majorticklabels(), rotation=45, ha='right')
    
    # 5. 统计图表行 - 第五行，左右两个子图
    # 5.1 左图：仓位价值分布
    ax5_left = fig.add_subplot(gs[4, 0])
    
    # 计算仓位价值
    pos_values = pos * trade_price
    
    # 分离正负仓位
    positive_pos = pos_values[pos_values > 0]
    negative_pos = pos_values[pos_values < 0]
    
    # 绘制直方图
    if len(positive_pos) > 0 or len(negative_pos) > 0:
            bins = 50
            if len(positive_pos) > 0 and len(negative_pos) > 0:
                # 同时有正负仓位
                all_values = np.concatenate([positive_pos, negative_pos])
                hist_range = (np.min(all_values), np.max(all_values))
                ax5_left.hist(positive_pos, bins=bins, alpha=0.7, color='green', label='Positive Position', range=hist_range)
                ax5_left.hist(negative_pos, bins=bins, alpha=0.7, color='red', label='Negative Position', range=hist_range)
            elif len(positive_pos) > 0:
                ax5_left.hist(positive_pos, bins=bins, alpha=0.7, color='green', label='Positive Position')
            elif len(negative_pos) > 0:
                ax5_left.hist(negative_pos, bins=bins, alpha=0.7, color='red', label='Negative Position')
            
            ax5_left.axvline(x=0, color='black', linestyle='--', alpha=0.5, linewidth=1)
            ax5_left.set_xlabel('Position Value', fontsize=10)
            ax5_left.set_ylabel('Frequency', fontsize=10)
            ax5_left.set_title('Position Value Distribution', fontsize=11, fontweight='bold')
            ax5_left.legend(fontsize=9)
            ax5_left.grid(True, alpha=0.3)
    
    # 5.2 右图：订单类型统计
    ax5_right = fig.add_subplot(gs[4, 1])
    
    # 统计订单类型
    maker_mask = (order_role == 2)
    taker_mask = (order_role == 1)
    
    maker_buy = np.sum((maker_mask) & (order_side == 1))
    maker_sell = np.sum((maker_mask) & (order_side == -1))
    taker_buy = np.sum((taker_mask) & (order_side == 1))
    taker_sell = np.sum((taker_mask) & (order_side == -1))
    
    categories = ['Maker Buy', 'Maker Sell', 'Taker Buy', 'Taker Sell']
    counts = [maker_buy, maker_sell, taker_buy, taker_sell]
    colors = ['green', 'red', 'lightgreen', 'lightcoral']
    
    bars = ax5_right.bar(categories, counts, color=colors, alpha=0.7)
    ax5_right.set_ylabel('Trade Count', fontsize=10)
    ax5_right.set_title('Trade Type Distribution', fontsize=11, fontweight='bold')
    ax5_right.grid(True, alpha=0.3, axis='y')
    
    # 添加数值标签
    for bar in bars:
        height = bar.get_height()
        if height > 0:
            ax5_right.text(bar.get_x() + bar.get_width()/2., height,
                    f'{int(height)}',
                    ha='center', va='bottom', fontsize=9)
    
    # 6. 统计指标表格 - 第六行，占据两列
    ax6 = fig.add_subplot(gs[5, :])
    ax6.axis('off')
    
    if performance:
        # 提取关键指标
        overall = performance.get('overall_performance', {})
        maker = performance.get('maker_performance', {})
        taker = performance.get('taker_performance', {})
        fees = performance.get('fee_analysis', {})
        funding = performance.get('funding_analysis', {})
        order_behavior = performance.get('order_behavior_metrics', {})
        
        # 准备表格数据 - 重新组织为4列格式，key:value更近
        # 将所有指标组织为4列：Metric1:Value1 | Metric2:Value2 | Metric3:Value3 | Metric4:Value4
        all_metrics = [
            # 总体绩效
            ('Total PnL (with fees)', f"{overall.get('total_pnl_with_fees', 0):.2f}"),
            ('Total PnL (no fees)', f"{overall.get('total_pnl_no_fees', 0):.2f}"),
            ('PnL Ratio (with fees, bps)', f"{overall.get('pnl_with_fees_ratio', 0):.4f}"),
            ('Max Drawdown (%)', f"{overall.get('max_drawdown', 0)*100:.2f}"),
            ('Sharpe Ratio', f"{overall.get('sharpe_ratio', np.nan):.4f}" if not np.isnan(overall.get('sharpe_ratio', np.nan)) else 'N/A'),
            ('Calmar Ratio', f"{overall.get('calmar_ratio', np.nan):.4f}" if not np.isnan(overall.get('calmar_ratio', np.nan)) else 'N/A'),
            ('Annualized Return (%)', f"{overall.get('annualized_return', np.nan)*100:.2f}" if not np.isnan(overall.get('annualized_return', np.nan)) else 'N/A'),
            # Maker/Taker绩效
            ('Maker PnL', f"{maker.get('total_maker_pnl_no_fees', 0):.2f}"),
            ('Maker Volume', f"{maker.get('maker_volume_total', 0):.2f}"),
            ('Maker PnL Ratio (bps)', f"{maker.get('maker_pnl_ratio', 0):.4f}"),
            ('Taker PnL', f"{taker.get('total_taker_pnl_no_fees', 0):.2f}"),
            ('Taker Volume', f"{taker.get('taker_volume_total', 0):.2f}"),
            ('Taker PnL Ratio (bps)', f"{taker.get('taker_pnl_ratio', 0):.4f}"),
            # 手续费
            ('Total Fees', f"{fees.get('total_actual_fees', 0):.2f}"),
            ('Maker Fees (rebate)', f"{maker.get('actual_maker_fees_cost_rebate', 0):.2f}"),
            ('Taker Fees (cost)', f"{taker.get('actual_taker_fees_cost', 0):.2f}"),
            # 资金费统计
            ('Funding Income', f"{funding.get('funding_income', 0):.2f}"),
            ('Funding Income Ratio (%)', f"{funding.get('funding_income_ratio', 0):.2f}"),
            ('Funding Return Rate (bps)', f"{funding.get('funding_return_rate', 0):.4f}"),
            # 订单行为指标
            ('Avg Fill Time (sec)', f"{order_behavior.get('avg_fill_time_sec', np.nan):.2f}" if not np.isnan(order_behavior.get('avg_fill_time_sec', np.nan)) else 'N/A'),
            ('Median Fill Time (sec)', f"{order_behavior.get('median_fill_time_sec', np.nan):.2f}" if not np.isnan(order_behavior.get('median_fill_time_sec', np.nan)) else 'N/A'),
            ('Fill Rate (%)', f"{order_behavior.get('avg_fill_rate', np.nan)*100:.2f}" if not np.isnan(order_behavior.get('avg_fill_rate', np.nan)) else 'N/A'),
            ('Finish All Rate (%)', f"{order_behavior.get('finish_all_pct', np.nan)*100:.2f}" if not np.isnan(order_behavior.get('finish_all_pct', np.nan)) else 'N/A'),
            ('Finish Hit Rate (%)', f"{order_behavior.get('finish_hit_pct', np.nan)*100:.2f}" if not np.isnan(order_behavior.get('finish_hit_pct', np.nan)) else 'N/A'),
            ('Avg Slippage (%)', f"{order_behavior.get('avg_slippage_pct', np.nan)*100:.4f}" if not np.isnan(order_behavior.get('avg_slippage_pct', np.nan)) else 'N/A'),
            ('Total Slippage Value', f"{order_behavior.get('total_slippage_value', 0):.2f}"),
            # API调用统计
            ('API Calls/min (mean)', f"{order_behavior.get('api_calls_per_minute', {}).get('mean', 0):.2f}"),
            ('API Calls/min (max)', f"{order_behavior.get('api_calls_per_minute', {}).get('max', 0):.2f}")
        ]
        
        # 将指标组织为4列，每行4个指标
        num_metrics = len(all_metrics)
        num_rows = (num_metrics + 3) // 4  # 向上取整
        
        # 创建4列表格数据
        table_data = []
        col_labels = ['Metric 1', 'Metric 2', 'Metric 3', 'Metric 4']
        
        for row in range(num_rows):
            row_data = []
            for col in range(4):
                idx = row * 4 + col
                if idx < num_metrics:
                    metric_name, metric_value = all_metrics[idx]
                    # key:value格式，更紧凑
                    row_data.append(f"{metric_name}: {metric_value}")
                else:
                    row_data.append("")  # 空单元格
            table_data.append(row_data)
        
        # 创建表格 - 4列布局，增大行高和列表高度
        table = ax6.table(cellText=table_data, colLabels=col_labels,
                         cellLoc='left', loc='center', bbox=[0, 0, 1, 1])
        table.auto_set_font_size(False)
        table.set_fontsize(9)  # 稍微减小字体以适应4列
        table.scale(1, 20)  # 增大行高到20，确保不挤压，key:value更清晰
        
        # 设置表头样式
        for i in range(4):
            table[(0, i)].set_facecolor('#40466e')
            table[(0, i)].set_text_props(weight='bold', color='white')
            table[(0, i)].set_height(0.1)  # 增加表头高度
        
        # 根据数值设置颜色（遍历所有单元格）
        for row in range(1, num_rows + 1):
            for col in range(4):
                cell_text = table_data[row - 1][col] if row - 1 < len(table_data) and col < len(table_data[row - 1]) else ""
                if cell_text:
                    # 增加单元格高度
                    table[(row, col)].set_height(0.1)
                    
                    # 提取数值
                    try:
                        # 从 "Metric Name: value" 格式中提取value
                        if ':' in cell_text:
                            value_str = cell_text.split(':')[1].strip()
                            # 清理字符串
                            value_str = value_str.replace('N/A', '0').replace('%', '').replace('bps', '').strip()
                            value = float(value_str)
                            
                            if value > 0:
                                table[(row, col)].set_facecolor('#d4edda')  # 浅绿色
                                table[(row, col)].set_text_props(color='#155724')  # 深绿色
                            elif value < 0:
                                table[(row, col)].set_facecolor('#f8d7da')  # 浅红色
                                table[(row, col)].set_text_props(color='#721c24')  # 深红色
                            else:
                                table[(row, col)].set_facecolor('#ffffff')
                                table[(row, col)].set_text_props(color='black')
                        else:
                            table[(row, col)].set_facecolor('#ffffff')
                            table[(row, col)].set_text_props(color='black')
                    except:
                        table[(row, col)].set_facecolor('#ffffff')
                        table[(row, col)].set_text_props(color='black')
                else:
                    table[(row, col)].set_facecolor('#ffffff')
                    table[(row, col)].set_text_props(color='black')
                    table[(row, col)].set_height(0.1)
        
        # 设置列宽，确保4列均匀分布
        table.auto_set_column_width([0, 1, 2, 3])
    
    # 设置总标题 - 增加上方间距
    fig.suptitle(title, fontsize=16, fontweight='bold', y=0.995)
    
    # 调整布局，使用subplots_adjust避免tight_layout警告，增加上方和底部空间，特别是表格部分
    plt.subplots_adjust(left=0.06, right=0.97, top=0.98, bottom=0.02, hspace=0.4, wspace=0.3)
    
    if save_path:
        plt.savefig(save_path, dpi=300, bbox_inches='tight', facecolor='white')
        print(f"✅ 综合分析图表已保存: {save_path}")
    else:
        plt.show()
    
    plt.close()

