"""数据预处理模块：将原始数据转换为回测所需的格式"""
import numpy as np
from typing import List, Optional, Tuple

# mm_flag 设计规则（硬编码）
# 0: blofin trades (真实成交，Taker Trade)
# 1: binance trades (市场数据)
# 2: okx trades (市场数据)
# 3: bybit trades (市场数据)
# -1: binance orderbook (市场数据)
# -2: funding_rate (市场数据)


def preprocess_aggtrades(
    data: np.ndarray,
    exchange_flag: int = 1,  # 默认binance trades
    contract_size: float = 1.0
) -> np.ndarray:
    """
    预处理逐笔成交数据，转换为回测所需格式
    
    Args:
        data: 原始数据数组，列格式为 [timestamp, price, quantity, is_buyer_maker, ...]
        exchange_flag: 交易所标识 (0=市场数据, 1=用户订单)
        contract_size: 合约乘数，用于调整数量
    
    Returns:
        处理后的numpy数组，格式: [timestamp, order_side, price, quantity, mm_flag]
        - timestamp: 时间戳（毫秒）
        - order_side: 方向 (1=buy, -1=sell)
        - price: 成交价格
        - quantity: 成交数量（已乘以contract_size）
        - mm_flag: 是否为市场数据 (1=市场数据, 0=用户订单)
    """
    if data.size == 0:
        return np.empty((0, 5), dtype=np.float64)
    
    # 提取列
    timestamps = data[:, 0].astype(np.int64)
    prices = data[:, 1].astype(np.float64)
    quantities = data[:, 2].astype(np.float64) * contract_size
    
    # 处理方向：is_buyer_maker=True表示买方是maker，即主动卖出
    if data.shape[1] > 3:
        is_buyer_maker = data[:, 3].astype(bool)
        order_sides = np.where(is_buyer_maker, -1, 1).astype(np.float64)
    else:
        # 如果没有is_buyer_maker列，默认使用已有方向列或设为1
        order_sides = np.ones(len(data), dtype=np.float64)
    
    # mm_flag: 根据exchange_flag设置
    # 0: blofin trades, 1: binance trades, 2: okx, 3: bybit, -1: orderbook, -2: funding_rate
    mm_flags = np.full(len(data), exchange_flag, dtype=np.float64)
    
    # 组合结果
    result = np.column_stack([
        timestamps,
        order_sides,
        prices,
        quantities,
        mm_flags
    ])
    
    # 按时间戳排序
    sort_indices = np.argsort(result[:, 0])
    result = result[sort_indices]
    
    return result


def merge_exchange_data(
    data_list: List[np.ndarray],
    exchange_flags: Optional[List[int]] = None
) -> np.ndarray:
    """
    合并多个交易所的数据
    
    Args:
        data_list: 多个交易所的数据列表，每个数据格式为 [timestamp, order_side, price, quantity, mm_flag]
        exchange_flags: 交易所标识列表，如果为None则使用数据中的mm_flag
    
    Returns:
        合并后的数据，按时间戳排序
    """
    if not data_list:
        return np.empty((0, 5), dtype=np.float64)
    
    if exchange_flags is None:
        exchange_flags = [0] * len(data_list)
    
    # 为每个数据源设置交易所标识（如果需要）
    merged_data = []
    for i, data in enumerate(data_list):
        if data.size > 0:
            # 如果数据已经有mm_flag列，保持原样；否则设置exchange_flag
            if data.shape[1] >= 5:
                data_copy = data.copy()
                data_copy[:, 4] = exchange_flags[i]
            else:
                # 如果数据格式不对，跳过
                continue
            merged_data.append(data_copy)
    
    if not merged_data:
        return np.empty((0, 5), dtype=np.float64)
    
    # 合并所有数据
    result = np.vstack(merged_data)
    
    # 按时间戳排序
    sort_indices = np.argsort(result[:, 0])
    result = result[sort_indices]
    
    return result


def validate_data(data: np.ndarray) -> Tuple[bool, str]:
    """
    验证数据格式是否正确
    
    Args:
        data: 数据数组，格式应为 [timestamp, order_side, price, quantity, mm_flag]
    
    Returns:
        (is_valid, error_message)
    """
    if data.size == 0:
        return True, ""
    
    if data.ndim != 2 or data.shape[1] != 5:
        return False, f"数据维度错误：期望形状 (N, 5)，实际 {data.shape}"
    
    # 检查时间戳是否单调递增
    timestamps = data[:, 0]
    if not np.all(timestamps[:-1] <= timestamps[1:]):
        return False, "时间戳不是单调递增的"
    
    # 检查价格和数量是否为正
    prices = data[:, 2]
    quantities = data[:, 3]
    if np.any(prices <= 0):
        return False, "存在非正价格"
    if np.any(quantities <= 0):
        return False, "存在非正数量"
    
    # 检查方向是否为1或-1
    sides = data[:, 1]
    if not np.all(np.isin(sides, [-1, 1])):
        return False, "方向值必须为1或-1"
    
    return True, ""

