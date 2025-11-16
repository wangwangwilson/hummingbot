#!/usr/bin/env python3
"""
快速分析脚本 - 不依赖完整hummingbot环境

直接查找和分析CSV数据文件
"""

import sys
from pathlib import Path
from datetime import datetime
import pandas as pd
import numpy as np

def find_data_files():
    """查找数据文件"""
    # 可能的目录
    possible_dirs = [
        Path("/Users/wilson/Desktop/mm_research/hummingbot/data/paper_replication"),
        Path("/workspace/data/paper_replication"),
        Path(__file__).parent.parent.parent / "data" / "paper_replication",
        Path(__file__).parent / "data",
    ]
    
    for data_dir in possible_dirs:
        if data_dir.exists():
            csv_files = list(data_dir.glob("*.csv"))
            if csv_files:
                print(f"找到数据目录: {data_dir}")
                print(f"找到 {len(csv_files)} 个CSV文件")
                return data_dir, csv_files
    
    # 搜索整个项目
    project_root = Path(__file__).parent.parent.parent
    print(f"在项目目录中搜索CSV文件: {project_root}")
    
    csv_files = list(project_root.rglob("*.csv"))
    if csv_files:
        print(f"找到 {len(csv_files)} 个CSV文件")
        # 过滤出可能的数据文件
        data_files = [f for f in csv_files if any(pair in f.name.upper() for pair in ['BTC', 'SOL', 'ETH', 'XRP', 'AVAX', 'DOT', 'MYX'])]
        if data_files:
            return data_files[0].parent, data_files
    
    return None, []


def analyze_data_files(data_dir, csv_files):
    """分析数据文件"""
    print("\n" + "="*80)
    print("数据文件分析")
    print("="*80)
    
    if not csv_files:
        print("未找到数据文件")
        return
    
    print(f"\n数据目录: {data_dir}")
    print(f"文件数量: {len(csv_files)}\n")
    
    # 分析每个文件
    for csv_file in csv_files[:10]:  # 只显示前10个
        try:
            df = pd.read_csv(csv_file)
            size_mb = csv_file.stat().st_size / (1024 * 1024)
            print(f"文件: {csv_file.name}")
            print(f"  大小: {size_mb:.2f} MB")
            print(f"  行数: {len(df):,}")
            if 'timestamp' in df.columns:
                if 'timestamp' in df.columns:
                    df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce', unit='ms')
                    if df['timestamp'].notna().any():
                        print(f"  时间范围: {df['timestamp'].min()} 至 {df['timestamp'].max()}")
            print()
        except Exception as e:
            print(f"  读取失败: {e}\n")


def find_results_files():
    """查找回测结果文件"""
    possible_dirs = [
        Path("/Users/wilson/Desktop/mm_research/hummingbot/data/paper_replication/results"),
        Path("/workspace/data/paper_replication/results"),
        Path(__file__).parent.parent.parent / "data" / "paper_replication" / "results",
    ]
    
    for results_dir in possible_dirs:
        if results_dir.exists():
            csv_files = list(results_dir.glob("*.csv"))
            if csv_files:
                return results_dir, csv_files
    
    return None, []


def main():
    """主函数"""
    print("="*80)
    print("快速数据分析工具")
    print("="*80)
    
    # 1. 查找数据文件
    print("\n【步骤 1】查找数据文件")
    print("-"*80)
    data_dir, csv_files = find_data_files()
    
    if csv_files:
        analyze_data_files(data_dir, csv_files)
    else:
        print("未找到数据文件")
        print("\n提示: 数据文件应包含以下交易对之一: BTC, SOL, ETH, XRP, AVAX, DOT, MYX")
    
    # 2. 查找回测结果
    print("\n【步骤 2】查找回测结果")
    print("-"*80)
    results_dir, results_files = find_results_files()
    
    if results_files:
        print(f"找到 {len(results_files)} 个结果文件")
        latest_file = max(results_files, key=lambda p: p.stat().st_mtime)
        print(f"最新结果: {latest_file.name}")
        
        # 分析结果
        try:
            from analyze_results import load_latest_results, analyze_results
            df = pd.read_csv(latest_file)
            analyze_results(df)
        except Exception as e:
            print(f"分析结果时出错: {e}")
            import traceback
            traceback.print_exc()
    else:
        print("未找到回测结果文件")
        print("\n提示: 需要先运行回测才能分析结果")
        print("运行: python3 backtest_comparison.py CUSTOM")
    
    print("\n" + "="*80)


if __name__ == "__main__":
    main()

