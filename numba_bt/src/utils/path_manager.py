"""实验结果路径管理工具"""
from pathlib import Path
from datetime import datetime
from typing import Optional, Literal, Tuple
import json

from ..const import RESULTS_PROD, RESULTS_TEST


class ResultPathManager:
    """实验结果路径管理器"""
    
    def __init__(
        self,
        mode: Literal["prod", "test"] = "test",
        base_dir: Optional[Path] = None
    ):
        """
        初始化路径管理器
        
        Args:
            mode: 模式，'prod' 或 'test'
            base_dir: 基础目录，如果为None则使用默认配置
        """
        if base_dir is None:
            self.base_dir = RESULTS_PROD if mode == "prod" else RESULTS_TEST
        else:
            self.base_dir = Path(base_dir)
        
        self.mode = mode
        self.current_run_dir = None
    
    def create_run_directory(
        self,
        symbol: str,
        experiment_name: str,
        experiment_scenario: str,
        parameters: Optional[dict] = None,
        timestamp: Optional[datetime] = None
    ) -> Path:
        """
        创建本次运行的目录结构
        
        目录结构: results/{mode}/{date}/{time}/{symbol}/{experiment_name}/
        
        Args:
            symbol: 交易对符号，如 'BTCUSDT' 或 'group1'
            experiment_name: 实验名称，格式: {symbol}_{target}_{scenario}_{params}
            experiment_scenario: 实验场景描述
            parameters: 参数字典，用于生成目录名
            timestamp: 时间戳，如果为None则使用当前时间
        
        Returns:
            创建的目录路径
        """
        if timestamp is None:
            timestamp = datetime.now()
        
        # 日期目录: 2025_11_16
        date_str = timestamp.strftime("%Y_%m_%d")
        
        # 时间目录: 10_12
        time_str = timestamp.strftime("%H_%M")
        
        # 构建完整路径
        run_dir = (
            self.base_dir / date_str / time_str / symbol / experiment_name
        )
        
        # 创建目录
        run_dir.mkdir(parents=True, exist_ok=True)
        
        self.current_run_dir = run_dir
        
        # 保存运行信息
        self._save_run_info(run_dir, symbol, experiment_name, experiment_scenario, parameters, timestamp)
        
        return run_dir
    
    def _save_run_info(
        self,
        run_dir: Path,
        symbol: str,
        experiment_name: str,
        experiment_scenario: str,
        parameters: Optional[dict],
        timestamp: datetime
    ):
        """保存运行信息到JSON文件"""
        info = {
            "mode": self.mode,
            "symbol": symbol,
            "experiment_name": experiment_name,
            "experiment_scenario": experiment_scenario,
            "parameters": parameters or {},
            "timestamp": timestamp.isoformat(),
            "directory": str(run_dir)
        }
        
        info_file = run_dir / "run_info.json"
        with open(info_file, 'w', encoding='utf-8') as f:
            json.dump(info, f, indent=2, ensure_ascii=False)
    
    def get_output_path(self, filename: str) -> Path:
        """
        获取输出文件路径
        
        Args:
            filename: 文件名
        
        Returns:
            完整的文件路径
        """
        if self.current_run_dir is None:
            raise ValueError("请先调用 create_run_directory 创建运行目录")
        
        return self.current_run_dir / filename
    
    def save_results(
        self,
        results: dict,
        filename: str = "results.json"
    ) -> Path:
        """
        保存结果到JSON文件
        
        Args:
            results: 结果字典
            filename: 文件名
        
        Returns:
            保存的文件路径
        """
        output_path = self.get_output_path(filename)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        
        return output_path
    
    @staticmethod
    def format_experiment_name(
        symbol: str,
        target: str,
        scenario: str,
        params: Optional[dict] = None
    ) -> str:
        """
        格式化实验名称
        
        格式: {symbol}_{target}_{scenario}_{param1}_{param2}_...
        
        Args:
            symbol: 交易对或组名
            target: 实验目标，如 'backtest', 'optimization', 'analysis'
            scenario: 实验场景，如 'maker_strategy', 'taker_strategy'
            params: 参数字典，如 {'exposure': 50000, 'target_pct': 0.5}
        
        Returns:
            格式化的实验名称
        """
        parts = [symbol, target, scenario]
        
        if params:
            # 将参数转换为字符串，按key排序
            param_strs = []
            for key, value in sorted(params.items()):
                if isinstance(value, float):
                    param_strs.append(f"{key}_{value:.2f}")
                elif isinstance(value, (int, str)):
                    param_strs.append(f"{key}_{value}")
                elif isinstance(value, (list, tuple)):
                    # 列表转换为下划线分隔的字符串，例如 [0, 8, 16] -> "0_8_16"
                    param_strs.append(f"{key}_{'_'.join(map(str, value))}")
                else:
                    param_strs.append(f"{key}_{str(value)}")
            
            parts.extend(param_strs)
        
        return "_".join(parts)


def create_result_directory(
    mode: Literal["prod", "test"],
    symbol: str,
    target: str,
    scenario: str,
    parameters: Optional[dict] = None,
    timestamp: Optional[datetime] = None
) -> Tuple[Path, ResultPathManager]:
    """
    便捷函数：创建结果目录并返回路径管理器
    
    Args:
        mode: 模式，'prod' 或 'test'
        symbol: 交易对符号
        target: 实验目标
        scenario: 实验场景
        parameters: 参数字典
        timestamp: 时间戳
    
    Returns:
        (目录路径, 路径管理器)
    """
    manager = ResultPathManager(mode=mode)
    experiment_name = manager.format_experiment_name(symbol, target, scenario, parameters)
    run_dir = manager.create_run_directory(
        symbol=symbol,
        experiment_name=experiment_name,
        experiment_scenario=scenario,
        parameters=parameters,
        timestamp=timestamp
    )
    
    return run_dir, manager

