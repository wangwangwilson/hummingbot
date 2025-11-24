"""30s return和spread统计工具"""
import numpy as np
from typing import Tuple, Dict, Any
from numba import njit


@njit
def calculate_30s_returns(prices: np.ndarray, timestamps: np.ndarray) -> np.ndarray:
    """
    计算30秒收益率
    
    Args:
        prices: 价格数组
        timestamps: 时间戳数组（毫秒）
    
    Returns:
        收益率数组（与prices长度相同，第一个值为0）
    """
    returns = np.zeros(len(prices))
    window_ms = 30 * 1000  # 30秒 = 30000毫秒
    
    for i in range(1, len(prices)):
        # 找到30秒前的价格
        target_ts = timestamps[i] - window_ms
        # 向前查找最接近的价格
        base_idx = i
        for j in range(i - 1, -1, -1):
            if timestamps[j] <= target_ts:
                base_idx = j
                break
        
        if base_idx < i and prices[base_idx] > 0:
            returns[i] = (prices[i] - prices[base_idx]) / prices[base_idx]
    
    return returns


def calculate_return_statistics(data: np.ndarray) -> Dict[str, Any]:
    """
    计算30s return统计信息
    
    Args:
        data: 市场数据数组 [timestamp, order_side, price, quantity, mm_flag]
    
    Returns:
        统计信息字典
    """
    # 提取价格和时间戳（只使用市场数据，mm_flag != 0）
    market_mask = data[:, 4] != 0
    if np.sum(market_mask) == 0:
        return {
            "return_percentile_20": 0.0,
            "return_percentile_80": 0.0,
            "return_mean": 0.0,
            "return_std": 0.0,
            "return_median": 0.0
        }
    
    market_data = data[market_mask]
    prices = market_data[:, 2]
    timestamps = market_data[:, 0]
    
    # 计算30s return
    returns = calculate_30s_returns(prices, timestamps)
    
    # 过滤掉0值（第一个值）
    valid_returns = returns[returns != 0]
    
    if len(valid_returns) == 0:
        return {
            "return_percentile_20": 0.0,
            "return_percentile_80": 0.0,
            "return_mean": 0.0,
            "return_std": 0.0,
            "return_median": 0.0
        }
    
    # 计算分位数
    percentile_20 = np.percentile(valid_returns, 20)
    percentile_80 = np.percentile(valid_returns, 80)
    
    return {
        "return_percentile_20": float(percentile_20),
        "return_percentile_80": float(percentile_80),
        "return_mean": float(np.mean(valid_returns)),
        "return_std": float(np.std(valid_returns)),
        "return_median": float(np.median(valid_returns)),
        "return_min": float(np.min(valid_returns)),
        "return_max": float(np.max(valid_returns)),
        "return_count": len(valid_returns)
    }


def calculate_spread_statistics(data: np.ndarray) -> Dict[str, Any]:
    """
    计算spread统计信息（基于相邻买卖挂单价格差）
    
    注意：这个函数需要从订单统计数据中计算，目前返回默认值
    实际实现需要从回测结果中提取maker订单的买卖价格差
    
    Args:
        data: 市场数据数组
    
    Returns:
        spread统计信息字典
    """
    # 简化实现：基于价格波动估算spread
    market_mask = data[:, 4] != 0
    if np.sum(market_mask) == 0:
        return {
            "spread_median": 0.0,
            "spread_mean": 0.0,
            "spread_std": 0.0
        }
    
    market_data = data[market_mask]
    prices = market_data[:, 2]
    
    # 计算价格变化率作为spread的近似
    price_changes = np.abs(np.diff(prices) / prices[:-1])
    valid_changes = price_changes[price_changes > 0]
    
    if len(valid_changes) == 0:
        return {
            "spread_median": 0.0,
            "spread_mean": 0.0,
            "spread_std": 0.0
        }
    
    return {
        "spread_median": float(np.median(valid_changes)),
        "spread_mean": float(np.mean(valid_changes)),
        "spread_std": float(np.std(valid_changes))
    }

