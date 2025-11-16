#!/usr/bin/env python3
"""
自定义交易对完整实验脚本

对 BTC, SOL, ETH, XRP, AVAX, DOT, MYX 进行最近半年的回测和分析
"""

import asyncio
import sys
from datetime import datetime, timedelta
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

try:
    from download_candles_data import download_custom_pairs_last_6_months, get_data_summary
    from backtest_comparison import run_custom_pairs_comparison
    from visualize_results import ResultsVisualizer
except ImportError as e:
    print(f"导入错误: {e}")
    print("请确保在hummingbot项目环境中运行此脚本")
    print("或者先运行: ./install 来安装hummingbot环境")
    sys.exit(1)


async def run_custom_experiment():
    """运行自定义交易对的完整实验"""
    
    print("\n" + "="*80)
    print("自定义交易对回测实验")
    print("交易对: BTC, SOL, ETH, XRP, AVAX, DOT, MYX")
    print("时间范围: 最近6个月")
    print("="*80)
    
    # 步骤1: 下载数据
    print("\n【步骤 1/3】下载历史数据（最近6个月）")
    print("-"*80)
    
    try:
        await download_custom_pairs_last_6_months()
        print("\n✓ 数据下载完成")
    except Exception as e:
        print(f"\n✗ 数据下载失败: {str(e)}")
        print("尝试继续使用已有数据...")
        import traceback
        traceback.print_exc()
    
    # 显示数据摘要
    get_data_summary()
    
    # 步骤2: 运行回测
    print("\n【步骤 2/3】运行策略回测")
    print("-"*80)
    
    try:
        all_results = await run_custom_pairs_comparison()
        print("\n✓ 回测完成")
    except Exception as e:
        print(f"\n✗ 回测失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return
    
    # 步骤3: 生成可视化
    print("\n【步骤 3/3】生成可视化报告")
    print("-"*80)
    
    try:
        visualizer = ResultsVisualizer()
        visualizer.generate_full_report(all_results)
        print("\n✓ 可视化报告生成完成")
    except Exception as e:
        print(f"\n✗ 可视化生成失败: {str(e)}")
        import traceback
        traceback.print_exc()
    
    # 最终总结
    print("\n" + "="*80)
    print("实验完成！")
    print("="*80)
    print("\n结果文件位置：")
    
    # 检测数据目录
    workspace_dir = Path("/workspace/data/paper_replication")
    if workspace_dir.parent.parent.exists():
        data_dir = workspace_dir
    else:
        data_dir = project_root / "data" / "paper_replication"
    
    print(f"  - 数据: {data_dir}/")
    print(f"  - 回测结果: {data_dir}/results/")
    print(f"  - 图表: {data_dir}/figures/")
    print("\n" + "="*80)


if __name__ == "__main__":
    try:
        asyncio.run(run_custom_experiment())
    except KeyboardInterrupt:
        print("\n\n实验被用户中断")
        sys.exit(0)
    except Exception as e:
        print(f"\n\n实验失败: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

