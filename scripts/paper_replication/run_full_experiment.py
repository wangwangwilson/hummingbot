#!/usr/bin/env python3
"""
完整实验运行脚本 - 论文复现

自动化运行完整的实验流程：
1. 下载数据
2. 运行回测
3. 生成可视化报告

论文："Market Making in Crypto" by Stoikov et al. (2024)
"""

import asyncio
import sys
from pathlib import Path

# 导入其他脚本
from download_candles_data import download_paper_test_pairs, get_data_summary
from backtest_comparison import run_full_comparison
from visualize_results import ResultsVisualizer


async def run_complete_experiment():
    """运行完整实验流程"""
    
    print("\n" + "="*80)
    print("论文复现：Market Making in Crypto")
    print("Stoikov et al. (2024)")
    print("="*80)
    
    # 步骤1: 下载数据
    print("\n【步骤 1/3】下载历史数据")
    print("-"*80)
    
    try:
        await download_paper_test_pairs()
        print("\n✓ 数据下载完成")
    except Exception as e:
        print(f"\n✗ 数据下载失败: {str(e)}")
        print("尝试继续使用已有数据...")
    
    # 显示数据摘要
    get_data_summary()
    
    # 步骤2: 运行回测
    print("\n【步骤 2/3】运行策略回测")
    print("-"*80)
    
    try:
        all_results = await run_full_comparison()
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
    print("  - 数据: /workspace/data/paper_replication/")
    print("  - 回测结果: /workspace/data/paper_replication/results/")
    print("  - 图表: /workspace/data/paper_replication/figures/")
    print("\n" + "="*80)


def print_help():
    """打印帮助信息"""
    help_text = """
论文复现工具 - 使用说明

用法:
    python run_full_experiment.py [选项]

选项:
    无参数      - 运行完整实验（下载+回测+可视化）
    --help      - 显示此帮助信息
    --data-only - 仅下载数据
    --test-only - 仅运行回测（需要已有数据）
    --viz-only  - 仅生成可视化（需要已有回测结果）

示例:
    # 运行完整实验
    python run_full_experiment.py
    
    # 仅下载数据
    python run_full_experiment.py --data-only
    
    # 仅运行回测
    python run_full_experiment.py --test-only

更多信息请参阅 README.md
"""
    print(help_text)


async def main():
    """主函数"""
    
    if len(sys.argv) > 1:
        option = sys.argv[1]
        
        if option == "--help" or option == "-h":
            print_help()
            return
        
        elif option == "--data-only":
            print("\n仅下载数据...")
            await download_paper_test_pairs()
            get_data_summary()
        
        elif option == "--test-only":
            print("\n仅运行回测...")
            all_results = await run_full_comparison()
        
        elif option == "--viz-only":
            print("\n仅生成可视化...")
            print("注意: 此选项需要已有回测结果")
            print("请先运行完整实验或使用 --test-only")
        
        else:
            print(f"未知选项: {option}")
            print("使用 --help 查看帮助")
    
    else:
        # 默认运行完整实验
        await run_complete_experiment()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n实验被用户中断")
        sys.exit(0)
    except Exception as e:
        print(f"\n\n实验失败: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
