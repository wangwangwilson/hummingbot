#!/usr/bin/env python3
"""
回测结果分析脚本

对回测结果进行详细分析，生成分析报告
"""

import sys
from pathlib import Path
from datetime import datetime
import pandas as pd
import numpy as np

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


def get_results_dir():
    """获取结果目录"""
    workspace_dir = Path("/workspace/data/paper_replication/results")
    if workspace_dir.parent.parent.exists():
        return workspace_dir
    return project_root / "data" / "paper_replication" / "results"


def load_latest_results():
    """加载最新的回测结果"""
    results_dir = get_results_dir()
    
    if not results_dir.exists():
        print(f"结果目录不存在: {results_dir}")
        return None
    
    # 查找最新的CSV文件
    csv_files = list(results_dir.glob("*.csv"))
    if not csv_files:
        print("未找到回测结果文件")
        return None
    
    # 按修改时间排序
    latest_file = max(csv_files, key=lambda p: p.stat().st_mtime)
    print(f"加载结果文件: {latest_file.name}")
    
    df = pd.read_csv(latest_file)
    return df


def analyze_results(df):
    """分析回测结果"""
    print("\n" + "="*80)
    print("回测结果分析报告")
    print("="*80)
    
    if df is None or len(df) == 0:
        print("没有可分析的数据")
        return
    
    print(f"\n分析时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"交易对数量: {len(df)}")
    
    # 1. 收益分析
    print("\n【1. 收益分析】")
    print("-"*80)
    
    # 提取数值（去除%符号）
    def extract_value(val):
        if isinstance(val, str):
            return float(val.replace('%', '').replace('$', ''))
        return float(val)
    
    bp_returns = df['BP Return (%)'].apply(lambda x: extract_value(str(x)))
    macd_returns = df['MACD Return (%)'].apply(lambda x: extract_value(str(x)))
    
    print(f"BP策略平均收益: {bp_returns.mean():.2f}%")
    print(f"MACD策略平均收益: {macd_returns.mean():.2f}%")
    print(f"收益差异: {bp_returns.mean() - macd_returns.mean():.2f}%")
    
    # 统计胜率
    bp_wins = (bp_returns > macd_returns).sum()
    print(f"\nBP策略胜出次数: {bp_wins}/{len(df)} ({bp_wins/len(df)*100:.1f}%)")
    
    # 2. 风险分析
    print("\n【2. 风险分析】")
    print("-"*80)
    
    bp_sharpe = df['BP Sharpe'].apply(lambda x: extract_value(str(x)))
    macd_sharpe = df['MACD Sharpe'].apply(lambda x: extract_value(str(x)))
    
    print(f"BP策略平均Sharpe: {bp_sharpe.mean():.4f}")
    print(f"MACD策略平均Sharpe: {macd_sharpe.mean():.4f}")
    
    bp_dd = df['BP Max DD (%)'].apply(lambda x: extract_value(str(x)))
    macd_dd = df['MACD Max DD (%)'].apply(lambda x: extract_value(str(x)))
    
    print(f"\nBP策略平均最大回撤: {bp_dd.mean():.2f}%")
    print(f"MACD策略平均最大回撤: {macd_dd.mean():.2f}%")
    print(f"回撤改善: {macd_dd.mean() - bp_dd.mean():.2f}%")
    
    # 3. 最佳/最差表现
    print("\n【3. 最佳/最差表现】")
    print("-"*80)
    
    best_bp_idx = bp_returns.idxmax()
    worst_bp_idx = bp_returns.idxmin()
    
    print(f"BP策略最佳表现: {df.iloc[best_bp_idx]['Trading Pair']} ({bp_returns.iloc[best_bp_idx]:.2f}%)")
    print(f"BP策略最差表现: {df.iloc[worst_bp_idx]['Trading Pair']} ({bp_returns.iloc[worst_bp_idx]:.2f}%)")
    
    best_macd_idx = macd_returns.idxmax()
    worst_macd_idx = macd_returns.idxmin()
    
    print(f"MACD策略最佳表现: {df.iloc[best_macd_idx]['Trading Pair']} ({macd_returns.iloc[best_macd_idx]:.2f}%)")
    print(f"MACD策略最差表现: {df.iloc[worst_macd_idx]['Trading Pair']} ({macd_returns.iloc[worst_macd_idx]:.2f}%)")
    
    # 4. 综合评分
    print("\n【4. 综合评分】")
    print("-"*80)
    
    # 计算综合得分（收益*0.5 + Sharpe*0.3 - 回撤*0.2）
    bp_score = (bp_returns / 100 * 0.5 + bp_sharpe * 0.3 - bp_dd / 100 * 0.2).mean()
    macd_score = (macd_returns / 100 * 0.5 + macd_sharpe * 0.3 - macd_dd / 100 * 0.2).mean()
    
    print(f"BP策略综合得分: {bp_score:.4f}")
    print(f"MACD策略综合得分: {macd_score:.4f}")
    
    if bp_score > macd_score:
        print(f"\n✓ BP策略表现更优 (领先 {((bp_score/macd_score-1)*100):.1f}%)")
    else:
        print(f"\n✓ MACD策略表现更优 (领先 {((macd_score/bp_score-1)*100):.1f}%)")
    
    # 5. 详细对比表
    print("\n【5. 详细对比表】")
    print("-"*80)
    print(df.to_string(index=False))
    
    # 6. 保存分析报告
    print("\n【6. 保存分析报告】")
    print("-"*80)
    
    report_dir = get_results_dir().parent / "analysis"
    report_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_file = report_dir / f"analysis_report_{timestamp}.txt"
    
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write("="*80 + "\n")
        f.write("回测结果分析报告\n")
        f.write("="*80 + "\n\n")
        f.write(f"分析时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"交易对数量: {len(df)}\n\n")
        f.write("【收益分析】\n")
        f.write(f"BP策略平均收益: {bp_returns.mean():.2f}%\n")
        f.write(f"MACD策略平均收益: {macd_returns.mean():.2f}%\n")
        f.write(f"收益差异: {bp_returns.mean() - macd_returns.mean():.2f}%\n")
        f.write(f"BP策略胜出次数: {bp_wins}/{len(df)} ({bp_wins/len(df)*100:.1f}%)\n\n")
        f.write("【风险分析】\n")
        f.write(f"BP策略平均Sharpe: {bp_sharpe.mean():.4f}\n")
        f.write(f"MACD策略平均Sharpe: {macd_sharpe.mean():.4f}\n")
        f.write(f"BP策略平均最大回撤: {bp_dd.mean():.2f}%\n")
        f.write(f"MACD策略平均最大回撤: {macd_dd.mean():.2f}%\n\n")
        f.write("【综合评分】\n")
        f.write(f"BP策略综合得分: {bp_score:.4f}\n")
        f.write(f"MACD策略综合得分: {macd_score:.4f}\n\n")
        f.write("【详细对比表】\n")
        f.write(df.to_string(index=False))
    
    print(f"分析报告已保存至: {report_file}")
    
    print("\n" + "="*80)
    print("分析完成！")
    print("="*80)


def main():
    """主函数"""
    print("回测结果分析工具")
    print("="*80)
    
    df = load_latest_results()
    if df is not None:
        analyze_results(df)
    else:
        print("无法加载回测结果，请先运行回测")


if __name__ == "__main__":
    main()

