"""回测结果可视化模块"""
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime
from typing import Optional


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

