"""策略基类"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
import numpy as np
from pathlib import Path
import sys

# 支持相对导入和绝对导入
try:
    from ..wrapper.backtester import MarketMakerBacktester
    from ..utils.params_manager import ParamsManager
except ImportError:
    # 如果相对导入失败，尝试绝对导入
    from pathlib import Path
    project_root = Path(__file__).parent.parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    try:
        from src.wrapper.backtester import MarketMakerBacktester
        from src.utils.params_manager import ParamsManager
    except ImportError:
        # 如果绝对导入也失败，使用importlib
        import importlib.util
        backtester_path = project_root / "src" / "wrapper" / "backtester.py"
        spec = importlib.util.spec_from_file_location("backtester", backtester_path)
        backtester_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(backtester_module)
        MarketMakerBacktester = backtester_module.MarketMakerBacktester
        
        params_manager_path = project_root / "src" / "utils" / "params_manager.py"
        spec = importlib.util.spec_from_file_location("params_manager", params_manager_path)
        params_manager_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(params_manager_module)
        ParamsManager = params_manager_module.ParamsManager


class BaseStrategy(ABC):
    """策略基类，所有策略都应继承此类"""
    
    def __init__(
        self,
        name: str,
        description: str,
        params: Optional[Dict[str, Any]] = None,
        params_file: Optional[Path] = None
    ):
        """
        初始化策略
        
        Args:
            name: 策略名称
            description: 策略说明
            params: 参数字典，如果提供则直接使用
            params_file: 参数文件路径，如果提供则从文件加载
        """
        self.name = name
        self.description = description
        
        # 加载参数
        if params is not None:
            self.params = params
        elif params_file is not None:
            self.params = ParamsManager.load_params(params_file)
        else:
            # 使用默认参数
            self.params = ParamsManager.get_default_mm_params()
        
        # 创建回测器实例
        self.backtester = self._create_backtester()
        
        # 策略特定的状态
        self.strategy_state = {}
    
    def _create_backtester(self) -> MarketMakerBacktester:
        """创建回测器实例"""
        return MarketMakerBacktester(**self.params)
    
    @abstractmethod
    def preprocess_data(self, data: np.ndarray) -> np.ndarray:
        """
        预处理数据（策略特定的数据转换）
        
        Args:
            data: 原始数据数组
        
        Returns:
            处理后的数据数组
        """
        pass
    
    @abstractmethod
    def run_backtest(self, data: np.ndarray) -> Dict[str, Any]:
        """
        执行回测（策略特定的回测逻辑）
        
        Args:
            data: 市场数据数组
        
        Returns:
            回测结果字典
        """
        pass
    
    def save_params(self, filepath: Path, metadata: Optional[Dict[str, Any]] = None):
        """
        保存策略参数
        
        Args:
            filepath: 保存路径
            metadata: 元数据
        """
        if metadata is None:
            metadata = {
                "strategy_name": self.name,
                "strategy_description": self.description
            }
        
        ParamsManager.save_params(
            params=self.params,
            filepath=filepath,
            description=f"{self.name}: {self.description}",
            metadata=metadata
        )
    
    def get_params(self) -> Dict[str, Any]:
        """获取当前参数"""
        return self.params.copy()
    
    def update_params(self, new_params: Dict[str, Any]):
        """
        更新参数并重新创建回测器
        
        Args:
            new_params: 新参数字典
        """
        self.params.update(new_params)
        self.backtester = self._create_backtester()

