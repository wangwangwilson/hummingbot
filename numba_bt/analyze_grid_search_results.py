"""
网格搜索结果分析
分析哪些参数对盈利能力影响最大
"""
import json
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
from scipy import stats

# 设置中文字体
plt.rcParams['font.sans-serif'] = ['DejaVu Sans', 'Arial Unicode MS', 'SimHei']
plt.rcParams['axes.unicode_minus'] = False

def load_and_prepare_data(json_file):
    """加载并准备数据"""
    with open(json_file, 'r') as f:
        data = json.load(f)
    
    # 展开params字典
    expanded_data = []
    for item in data:
        row = item['params'].copy()
        row['total_pnl'] = item['total_pnl_no_fees']
        row['total_pnl_with_fees'] = item['total_pnl_with_fees']
        row['sharpe_ratio'] = item['sharpe_ratio']
        row['max_drawdown'] = item['max_drawdown']
        row['maker_pnl'] = item['maker_pnl']
        row['taker_pnl'] = item['taker_pnl']
        row['maker_volume'] = item['maker_volume']
        row['taker_volume'] = item['taker_volume']
        expanded_data.append(row)
    
    return pd.DataFrame(expanded_data)

def analyze_parameter_importance(df, output_dir):
    """分析参数重要性"""
    param_cols = ['order_size_pct_min', 'order_size_pct_max', 'as_model_buy_distance', 
                  'as_model_sell_distance', 'base_exposure', 'base_target_pct']
    
    results = {}
    
    # 1. 相关性分析
    correlations = {}
    for col in param_cols:
        corr = df[col].corr(df['total_pnl'])
        correlations[col] = corr
    
    # 2. 分组分析：盈利组 vs 亏损组
    profitable = df[df['total_pnl'] > 0]
    unprofitable = df[df['total_pnl'] <= 0]
    
    group_comparison = {}
    for col in param_cols:
        if len(profitable) > 0 and len(unprofitable) > 0:
            prof_mean = profitable[col].mean()
            unprof_mean = unprofitable[col].mean()
            # t检验
            t_stat, p_value = stats.ttest_ind(profitable[col], unprofitable[col])
            group_comparison[col] = {
                'profitable_mean': prof_mean,
                'unprofitable_mean': unprof_mean,
                'difference': prof_mean - unprof_mean,
                't_statistic': t_stat,
                'p_value': p_value
            }
    
    # 3. Top 20% vs Bottom 20%
    top_20 = df.nlargest(int(len(df) * 0.2), 'total_pnl')
    bottom_20 = df.nsmallest(int(len(df) * 0.2), 'total_pnl')
    
    top_bottom_comparison = {}
    for col in param_cols:
        top_mean = top_20[col].mean()
        bottom_mean = bottom_20[col].mean()
        top_bottom_comparison[col] = {
            'top_20_mean': top_mean,
            'bottom_20_mean': bottom_mean,
            'difference': top_mean - bottom_mean
        }
    
    # 4. 方差分析（ANOVA）- 对分类参数
    anova_results = {}
    for col in param_cols:
        # 将参数分成3组（低、中、高）
        df['param_group'] = pd.qcut(df[col], q=3, labels=['Low', 'Medium', 'High'], duplicates='drop')
        groups = [group['total_pnl'].values for name, group in df.groupby('param_group')]
        if len(groups) == 3 and all(len(g) > 0 for g in groups):
            f_stat, p_value = stats.f_oneway(*groups)
            anova_results[col] = {
                'f_statistic': f_stat,
                'p_value': p_value,
                'group_means': {name: group['total_pnl'].mean() 
                               for name, group in df.groupby('param_group')}
            }
        df = df.drop('param_group', axis=1)
    
    return {
        'correlations': correlations,
        'group_comparison': group_comparison,
        'top_bottom_comparison': top_bottom_comparison,
        'anova_results': anova_results
    }

def create_visualizations(df, importance_results, output_dir):
    """创建可视化图表"""
    param_cols = ['order_size_pct_min', 'order_size_pct_max', 'as_model_buy_distance', 
                  'as_model_sell_distance', 'base_exposure', 'base_target_pct']
    
    # 1. 参数重要性热力图
    fig, axes = plt.subplots(2, 2, figsize=(16, 12))
    
    # 1.1 相关性热力图
    corr_data = pd.DataFrame([importance_results['correlations']]).T
    corr_data.columns = ['Correlation']
    corr_data = corr_data.sort_values('Correlation', key=abs, ascending=False)
    
    ax = axes[0, 0]
    sns.barplot(data=corr_data.reset_index(), x='Correlation', y='index', ax=ax, palette='RdYlGn')
    ax.set_title('Parameter Correlation with Total PnL', fontsize=14, fontweight='bold')
    ax.set_xlabel('Correlation Coefficient')
    ax.set_ylabel('Parameter')
    ax.axvline(x=0, color='black', linestyle='--', linewidth=0.5)
    ax.grid(True, alpha=0.3, axis='x')
    
    # 1.2 盈利组 vs 亏损组对比
    comparison_data = []
    for col, stats in importance_results['group_comparison'].items():
        comparison_data.append({
            'Parameter': col,
            'Profitable': stats['profitable_mean'],
            'Unprofitable': stats['unprofitable_mean'],
            'Difference': stats['difference'],
            'P-value': stats['p_value']
        })
    comp_df = pd.DataFrame(comparison_data)
    comp_df = comp_df.sort_values('Difference', key=abs, ascending=False)
    
    ax = axes[0, 1]
    x = np.arange(len(comp_df))
    width = 0.35
    ax.bar(x - width/2, comp_df['Profitable'], width, label='Profitable', alpha=0.8, color='green')
    ax.bar(x + width/2, comp_df['Unprofitable'], width, label='Unprofitable', alpha=0.8, color='red')
    ax.set_xlabel('Parameter')
    ax.set_ylabel('Mean Value')
    ax.set_title('Profitable vs Unprofitable Parameter Comparison', fontsize=14, fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels(comp_df['Parameter'], rotation=45, ha='right')
    ax.legend()
    ax.grid(True, alpha=0.3, axis='y')
    
    # 1.3 Top 20% vs Bottom 20%对比
    top_bottom_data = []
    for col, stats in importance_results['top_bottom_comparison'].items():
        top_bottom_data.append({
            'Parameter': col,
            'Top 20%': stats['top_20_mean'],
            'Bottom 20%': stats['bottom_20_mean'],
            'Difference': stats['difference']
        })
    tb_df = pd.DataFrame(top_bottom_data)
    tb_df = tb_df.sort_values('Difference', key=abs, ascending=False)
    
    ax = axes[1, 0]
    x = np.arange(len(tb_df))
    width = 0.35
    ax.bar(x - width/2, tb_df['Top 20%'], width, label='Top 20%', alpha=0.8, color='blue')
    ax.bar(x + width/2, tb_df['Bottom 20%'], width, label='Bottom 20%', alpha=0.8, color='orange')
    ax.set_xlabel('Parameter')
    ax.set_ylabel('Mean Value')
    ax.set_title('Top 20% vs Bottom 20% Parameter Comparison', fontsize=14, fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels(tb_df['Parameter'], rotation=45, ha='right')
    ax.legend()
    ax.grid(True, alpha=0.3, axis='y')
    
    # 1.4 参数分布 vs 收益散点图（选择最重要的参数）
    sorted_params = sorted(importance_results['correlations'].items(), 
                         key=lambda x: abs(x[1]), reverse=True)
    top_3_params = [p[0] for p in sorted_params[:3]]
    
    ax = axes[1, 1]
    for i, param in enumerate(top_3_params):
        ax.scatter(df[param], df['total_pnl'], alpha=0.3, s=20, label=param)
    ax.set_xlabel('Parameter Value')
    ax.set_ylabel('Total PnL')
    ax.set_title('Top 3 Parameters vs Total PnL', fontsize=14, fontweight='bold')
    ax.legend()
    ax.grid(True, alpha=0.3)
    ax.axhline(y=0, color='black', linestyle='--', linewidth=0.5)
    
    plt.tight_layout()
    plt.savefig(output_dir / 'parameter_importance_analysis.png', dpi=150, bbox_inches='tight')
    plt.close()
    
    # 2. 每个参数的收益分布箱线图
    n_params = len(param_cols)
    n_cols = 3
    n_rows = (n_params + n_cols - 1) // n_cols
    
    fig, axes = plt.subplots(n_rows, n_cols, figsize=(18, 6*n_rows))
    axes = axes.flatten() if n_params > 1 else [axes]
    
    for idx, param in enumerate(param_cols):
        ax = axes[idx]
        # 分成3组
        df['param_group'] = pd.qcut(df[param], q=3, labels=['Low', 'Medium', 'High'], duplicates='drop')
        
        data_to_plot = []
        labels = []
        for name, group in df.groupby('param_group'):
            data_to_plot.append(group['total_pnl'].values)
            labels.append(f'{name}\n(n={len(group)})')
        
        if len(data_to_plot) > 0:
            bp = ax.boxplot(data_to_plot, labels=labels, patch_artist=True)
            for patch in bp['boxes']:
                patch.set_facecolor('lightblue')
            ax.set_title(f'{param}\nvs Total PnL', fontsize=12, fontweight='bold')
            ax.set_ylabel('Total PnL')
            ax.grid(True, alpha=0.3, axis='y')
            ax.axhline(y=0, color='red', linestyle='--', linewidth=0.5)
        
        df = df.drop('param_group', axis=1)
    
    # 隐藏多余的子图
    for idx in range(n_params, len(axes)):
        axes[idx].axis('off')
    
    plt.tight_layout()
    plt.savefig(output_dir / 'parameter_distribution_analysis.png', dpi=150, bbox_inches='tight')
    plt.close()
    
    # 3. 最佳参数组合分析
    top_10 = df.nlargest(10, 'total_pnl')
    
    fig, ax = plt.subplots(figsize=(14, 8))
    x = np.arange(len(top_10))
    colors = plt.cm.RdYlGn(np.linspace(0.3, 0.7, len(top_10)))
    bars = ax.barh(x, top_10['total_pnl'], color=colors)
    ax.set_yticks(x)
    ax.set_yticklabels([f"#{i+1}" for i in range(len(top_10))])
    ax.set_xlabel('Total PnL')
    ax.set_title('Top 10 Parameter Combinations', fontsize=14, fontweight='bold')
    ax.grid(True, alpha=0.3, axis='x')
    ax.axvline(x=0, color='black', linestyle='-', linewidth=0.5)
    
    # 添加参数信息到标签
    labels = []
    for idx, row in top_10.iterrows():
        param_str = ', '.join([f'{p}: {row[p]:.2f}' for p in param_cols[:3]])
        labels.append(f"{param_str}\nPnL: {row['total_pnl']:.0f}")
    ax.set_yticklabels(labels, fontsize=8)
    
    plt.tight_layout()
    plt.savefig(output_dir / 'top_10_combinations.png', dpi=150, bbox_inches='tight')
    plt.close()

def generate_report(df, importance_results, output_dir):
    """生成分析报告"""
    param_cols = ['order_size_pct_min', 'order_size_pct_max', 'as_model_buy_distance', 
                  'as_model_sell_distance', 'base_exposure', 'base_target_pct']
    
    report = []
    report.append("# 网格搜索结果分析报告\n")
    report.append(f"- 总参数组合数: {len(df)}\n")
    report.append(f"- 盈利组合数: {(df['total_pnl'] > 0).sum()} ({(df['total_pnl'] > 0).sum()/len(df)*100:.1f}%)\n")
    report.append(f"- 亏损组合数: {(df['total_pnl'] <= 0).sum()} ({(df['total_pnl'] <= 0).sum()/len(df)*100:.1f}%)\n")
    report.append(f"- 平均收益: {df['total_pnl'].mean():.2f}\n")
    report.append(f"- 最大收益: {df['total_pnl'].max():.2f}\n")
    report.append(f"- 最小收益: {df['total_pnl'].min():.2f}\n\n")
    
    report.append("## 1. 参数相关性分析\n")
    report.append("参数与总收益的相关系数（绝对值越大，影响越大）:\n\n")
    sorted_corr = sorted(importance_results['correlations'].items(), 
                        key=lambda x: abs(x[1]), reverse=True)
    for col, corr in sorted_corr:
        report.append(f"- **{col}**: {corr:+.4f}\n")
    
    report.append("\n## 2. 盈利组 vs 亏损组对比\n")
    report.append("| 参数 | 盈利组平均 | 亏损组平均 | 差异 | P值 |\n")
    report.append("|------|-----------|-----------|------|-----|\n")
    sorted_comp = sorted(importance_results['group_comparison'].items(),
                        key=lambda x: abs(x[1]['difference']), reverse=True)
    for col, stats in sorted_comp:
        sig = "***" if stats['p_value'] < 0.001 else "**" if stats['p_value'] < 0.01 else "*" if stats['p_value'] < 0.05 else ""
        report.append(f"| {col} | {stats['profitable_mean']:.4f} | {stats['unprofitable_mean']:.4f} | "
                     f"{stats['difference']:+.4f} | {stats['p_value']:.4f}{sig} |\n")
    
    report.append("\n## 3. Top 20% vs Bottom 20% 对比\n")
    report.append("| 参数 | Top 20%平均 | Bottom 20%平均 | 差异 |\n")
    report.append("|------|------------|---------------|------|\n")
    sorted_tb = sorted(importance_results['top_bottom_comparison'].items(),
                      key=lambda x: abs(x[1]['difference']), reverse=True)
    for col, stats in sorted_tb:
        report.append(f"| {col} | {stats['top_20_mean']:.4f} | {stats['bottom_20_mean']:.4f} | "
                     f"{stats['difference']:+.4f} |\n")
    
    # 最佳参数组合
    top_5 = df.nlargest(5, 'total_pnl')
    report.append("\n## 4. Top 5 参数组合\n")
    for idx, (_, row) in enumerate(top_5.iterrows(), 1):
        report.append(f"### 组合 #{idx} (PnL: {row['total_pnl']:.2f})\n")
        for col in param_cols:
            report.append(f"- {col}: {row[col]:.4f}\n")
        report.append(f"- Sharpe Ratio: {row['sharpe_ratio']:.4f}\n")
        report.append(f"- Max Drawdown: {row['max_drawdown']:.4f}\n\n")
    
    # 关键发现
    report.append("## 5. 关键发现\n\n")
    top_param = sorted_corr[0][0]
    top_corr = sorted_corr[0][1]
    report.append(f"1. **最重要的参数**: {top_param} (相关性: {top_corr:+.4f})\n")
    
    if len(importance_results['group_comparison']) > 0:
        top_diff_param = sorted_comp[0][0]
        top_diff = sorted_comp[0][1]['difference']
        report.append(f"2. **盈利组与亏损组差异最大的参数**: {top_diff_param} (差异: {top_diff:+.4f})\n")
    
    profitable = df[df['total_pnl'] > 0]
    if len(profitable) > 0:
        report.append(f"3. **盈利组合的平均特征**:\n")
        for col in param_cols:
            prof_mean = profitable[col].mean()
            all_mean = df[col].mean()
            report.append(f"   - {col}: {prof_mean:.4f} (全部平均: {all_mean:.4f})\n")
    
    with open(output_dir / 'parameter_importance_report.md', 'w', encoding='utf-8') as f:
        f.write(''.join(report))

def main():
    json_file = Path('results/test/2025_11_24/02_54/grid_search_results.json')
    output_dir = json_file.parent
    
    print("加载数据...")
    df = load_and_prepare_data(json_file)
    
    print("分析参数重要性...")
    importance_results = analyze_parameter_importance(df, output_dir)
    
    print("生成可视化图表...")
    create_visualizations(df, importance_results, output_dir)
    
    print("生成分析报告...")
    generate_report(df, importance_results, output_dir)
    
    print(f"\n✓ 分析完成！")
    print(f"结果保存在: {output_dir}")
    print(f"  - parameter_importance_analysis.png")
    print(f"  - parameter_distribution_analysis.png")
    print(f"  - top_10_combinations.png")
    print(f"  - parameter_importance_report.md")

if __name__ == '__main__':
    main()

