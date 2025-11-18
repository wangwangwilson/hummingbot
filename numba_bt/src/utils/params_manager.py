"""参数管理模块：JSON格式的参数保存和加载"""
import json
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime


class ParamsManager:
    """参数管理器，支持JSON格式的保存和加载"""
    
    @staticmethod
    def save_params(
        params: Dict[str, Any],
        filepath: Path,
        description: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Path:
        """
        保存参数到JSON文件
        
        Args:
            params: 参数字典
            filepath: 保存路径
            description: 参数描述
            metadata: 元数据（如创建时间、作者等）
        
        Returns:
            保存的文件路径
        """
        filepath = Path(filepath)
        filepath.parent.mkdir(parents=True, exist_ok=True)
        
        # 构建完整的参数文档
        param_doc = {
            "description": description or "Strategy parameters",
            "metadata": metadata or {
                "created_at": datetime.now().isoformat(),
                "version": "1.0"
            },
            "parameters": params
        }
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(param_doc, f, indent=2, ensure_ascii=False)
        
        return filepath
    
    @staticmethod
    def load_params(filepath: Path) -> Dict[str, Any]:
        """
        从JSON文件加载参数
        
        Args:
            filepath: 参数文件路径
        
        Returns:
            参数字典
        """
        filepath = Path(filepath)
        
        if not filepath.exists():
            raise FileNotFoundError(f"参数文件不存在: {filepath}")
        
        with open(filepath, 'r', encoding='utf-8') as f:
            param_doc = json.load(f)
        
        return param_doc.get("parameters", param_doc)
    
    @staticmethod
    def get_default_mm_params() -> Dict[str, Any]:
        """
        获取默认的做市策略参数
        
        Returns:
            默认参数字典
        """
        return {
            # 核心参数
            "exposure": 250000.0,
            "target_pct": 0.5,
            
            # Taker相关参数
            "enable_spl_taker": True,
            "sp_taker_value_thred_pct": 0.02,
            "sp_taker_pct": 0.001,
            "const_taker_step_size": 1,
            
            # Maker挂单参数
            "buy_maker_place_thred_pct": 0.7,
            "sell_maker_place_thred_pct": 0.7,
            "buy_place_grid_step_value": 5000.0,
            "sell_place_grid_step_value": 5000.0,
            "buy_revoke_grid_step_value_pct": 0.003,
            "sell_revoke_grid_step_value_pct": 0.003,
            
            # 价格调整策略
            "enable_price_step_maker": True,
            "enable_AS_adjust": True,
            "AS_MODEL": 0,
            "adjust_maker_step_num_max": 200,
            "const_maker_step_num": 5,
            "adj_price_step_thred": 10,
            "enable_cost_price_lock": False,
            "sp_pct": 0.0005,
            "sp_pct_grid_step": 0.0001,
            
            # 交易设置
            "taker_fee_rate": 0.00015,
            "maker_fee_rate": -0.00005,
            "open_ratio": 0.5,
            
            # 初始状态
            "initial_cash": 1000000.0,
            "initial_pos": 0.0,
            
            # 价格精度
            "mini_price_step": None
        }

