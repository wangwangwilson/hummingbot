#!/usr/bin/env python3
"""
检查回测状态和结果
"""

import sys
from pathlib import Path
from datetime import datetime

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

def check_backtest_status():
    """检查回测状态"""
    results_dir = Path(__file__).parent.parent.parent / "data" / "paper_replication" / "results"
    
    print("="*80)
    print("回测状态检查")
    print("="*80)
    
    # 检查进程
    import subprocess
    try:
        result = subprocess.run(
            ["ps", "aux"],
            capture_output=True,
            text=True
        )
        running = "backtest_comparison.py CUSTOM" in result.stdout
        if running:
            print("✓ 回测进程正在运行")
            # 提取运行时间
            for line in result.stdout.split('\n'):
                if "backtest_comparison.py CUSTOM" in line and "grep" not in line:
                    parts = line.split()
                    if len(parts) > 9:
                        runtime = parts[9]
                        cpu = parts[2]
                        mem = parts[3]
                        print(f"  运行时间: {runtime}")
                        print(f"  CPU使用: {cpu}%")
                        print(f"  内存使用: {mem}%")
        else:
            print("✗ 回测进程未运行")
    except Exception as e:
        print(f"无法检查进程: {e}")
    
    print()
    
    # 检查结果文件
    if results_dir.exists():
        csv_files = sorted(results_dir.glob("custom_comparison_summary_*.csv"), reverse=True)
        txt_files = sorted(results_dir.glob("backtest_report_*.txt"), reverse=True)
        
        if csv_files:
            latest_csv = csv_files[0]
            print(f"最新汇总结果: {latest_csv.name}")
            print(f"  修改时间: {datetime.fromtimestamp(latest_csv.stat().st_mtime)}")
            
            # 读取并分析
            import pandas as pd
            try:
                df = pd.read_csv(latest_csv)
                print(f"  交易对数量: {len(df)}")
                
                # 检查是否有非零结果
                bp_returns = df['BP Return (%)'].str.rstrip('%').astype(float)
                macd_returns = df['MACD Return (%)'].str.rstrip('%').astype(float)
                
                non_zero_bp = (bp_returns != 0).sum()
                non_zero_macd = (macd_returns != 0).sum()
                
                print(f"  BP策略非零结果: {non_zero_bp}/{len(df)}")
                print(f"  MACD策略非零结果: {non_zero_macd}/{len(df)}")
                
                if non_zero_bp == 0 and non_zero_macd == 0:
                    print("  ⚠️  警告: 所有结果都是0，可能回测未完成或有问题")
                else:
                    print("  ✓ 有非零结果，回测可能已完成")
                    print("\n  结果预览:")
                    print(df.to_string(index=False))
            except Exception as e:
                print(f"  读取失败: {e}")
        else:
            print("未找到汇总结果文件")
        
        if txt_files:
            latest_txt = txt_files[0]
            print(f"\n最新详细报告: {latest_txt.name}")
            print(f"  修改时间: {datetime.fromtimestamp(latest_txt.stat().st_mtime)}")
            print(f"  文件大小: {latest_txt.stat().st_size} 字节")
        else:
            print("\n未找到详细报告文件")
    else:
        print(f"结果目录不存在: {results_dir}")
    
    print()
    print("="*80)

if __name__ == "__main__":
    check_backtest_status()

