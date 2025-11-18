"""标准做市策略"""
import numpy as np
from typing import Dict, Any, Optional
from pathlib import Path

from .base_strategy import BaseStrategy
from ..analysis.statistics import analyze_performance


class StandardMMStrategy(BaseStrategy):
    """标准做市策略，基于原始回测逻辑"""
    
    def __init__(
        self,
        params: Optional[Dict[str, Any]] = None,
        params_file: Optional[Path] = None
    ):
        super().__init__(
            name="StandardMM",
            description="标准做市策略，支持Maker/Taker混合交易",
            params=params,
            params_file=params_file
        )
    
    def preprocess_data(self, data: np.ndarray) -> np.ndarray:
        """预处理数据（标准策略无需特殊处理）"""
        return data
    
    def run_backtest(self, data: np.ndarray) -> Dict[str, Any]:
        """
        执行回测
        
        Args:
            data: 市场数据数组
        
        Returns:
            回测结果字典
        """
        # 预处理数据
        processed_data = self.preprocess_data(data)
        
        # 执行回测
        self.backtester.run_backtest(processed_data)
        
        # 性能分析
        performance = analyze_performance(
            accounts_raw=self.backtester.accounts,
            place_orders_stats_raw=self.backtester.place_orders_stats
        )
        
        return {
            "strategy_name": self.name,
            "accounts": self.backtester.accounts,
            "place_orders_stats": self.backtester.place_orders_stats,
            "performance": performance
        }

