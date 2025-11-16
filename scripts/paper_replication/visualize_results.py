"""
结果可视化脚本 - 论文复现

生成策略对比的详细图表和分析报告
论文："Market Making in Crypto" by Stoikov et al. (2024)
"""

import sys
from pathlib import Path
from typing import Dict, List

import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
import seaborn as sns

# 设置绘图样式
sns.set_style("whitegrid")
plt.rcParams['figure.figsize'] = (12, 8)
plt.rcParams['font.size'] = 10


class ResultsVisualizer:
    """结果可视化器"""
    
    def __init__(self, output_dir: str = None):
        if output_dir is None:
            # 自动检测输出目录
            workspace_dir = Path("/workspace/data/paper_replication/figures")
            if workspace_dir.parent.parent.exists():
                output_dir = str(workspace_dir)
            else:
                project_root = Path(__file__).parent.parent.parent
                output_dir = str(project_root / "data" / "paper_replication" / "figures")
        
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def plot_cumulative_returns(
        self,
        bp_trades_df: pd.DataFrame,
        macd_trades_df: pd.DataFrame,
        trading_pair: str,
        initial_capital: float = 1000
    ):
        """绘制累积收益曲线"""
        fig, ax = plt.subplots(figsize=(14, 7))
        
        # 绘制BP策略
        if len(bp_trades_df) > 0:
            bp_trades_df = bp_trades_df.sort_values('timestamp')
            bp_trades_df['cumulative_pnl'] = bp_trades_df['pnl'].cumsum()
            bp_portfolio = initial_capital + bp_trades_df['cumulative_pnl']
            
            ax.plot(
                range(len(bp_portfolio)),
                bp_portfolio,
                label='PMM Bar Portion',
                linewidth=2,
                color='#2E86AB'
            )
        
        # 绘制MACD策略
        if len(macd_trades_df) > 0:
            macd_trades_df = macd_trades_df.sort_values('timestamp')
            macd_trades_df['cumulative_pnl'] = macd_trades_df['pnl'].cumsum()
            macd_portfolio = initial_capital + macd_trades_df['cumulative_pnl']
            
            ax.plot(
                range(len(macd_portfolio)),
                macd_portfolio,
                label='PMM Dynamic (MACD)',
                linewidth=2,
                color='#A23B72'
            )
        
        # 基准线
        ax.axhline(y=initial_capital, color='gray', linestyle='--', 
                   label=f'Initial Capital (${initial_capital})', alpha=0.7)
        
        ax.set_xlabel('Trade Number', fontsize=12)
        ax.set_ylabel('Portfolio Value ($)', fontsize=12)
        ax.set_title(f'Cumulative Returns Comparison - {trading_pair}', 
                     fontsize=14, fontweight='bold')
        ax.legend(loc='best', fontsize=11)
        ax.grid(True, alpha=0.3)
        
        plt.tight_layout()
        filename = self.output_dir / f"cumulative_returns_{trading_pair.replace('-', '_')}.png"
        plt.savefig(filename, dpi=300, bbox_inches='tight')
        print(f"保存图表: {filename}")
        plt.close()
    
    def plot_drawdown(
        self,
        bp_trades_df: pd.DataFrame,
        macd_trades_df: pd.DataFrame,
        trading_pair: str,
        initial_capital: float = 1000
    ):
        """绘制回撤曲线"""
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10))
        
        # BP策略回撤
        if len(bp_trades_df) > 0:
            bp_trades_df = bp_trades_df.sort_values('timestamp')
            bp_trades_df['cumulative_pnl'] = bp_trades_df['pnl'].cumsum()
            bp_portfolio = initial_capital + bp_trades_df['cumulative_pnl']
            
            running_max = np.maximum.accumulate(bp_portfolio.values)
            drawdown = (bp_portfolio.values - running_max) / running_max * 100
            
            ax1.fill_between(
                range(len(drawdown)),
                drawdown,
                0,
                color='#2E86AB',
                alpha=0.3,
                label='Drawdown'
            )
            ax1.plot(
                range(len(drawdown)),
                drawdown,
                color='#2E86AB',
                linewidth=2
            )
            
            ax1.set_title(f'PMM Bar Portion - Drawdown - {trading_pair}',
                         fontsize=12, fontweight='bold')
            ax1.set_ylabel('Drawdown (%)', fontsize=11)
            ax1.grid(True, alpha=0.3)
            ax1.legend()
        
        # MACD策略回撤
        if len(macd_trades_df) > 0:
            macd_trades_df = macd_trades_df.sort_values('timestamp')
            macd_trades_df['cumulative_pnl'] = macd_trades_df['pnl'].cumsum()
            macd_portfolio = initial_capital + macd_trades_df['cumulative_pnl']
            
            running_max = np.maximum.accumulate(macd_portfolio.values)
            drawdown = (macd_portfolio.values - running_max) / running_max * 100
            
            ax2.fill_between(
                range(len(drawdown)),
                drawdown,
                0,
                color='#A23B72',
                alpha=0.3,
                label='Drawdown'
            )
            ax2.plot(
                range(len(drawdown)),
                drawdown,
                color='#A23B72',
                linewidth=2
            )
            
            ax2.set_title(f'PMM Dynamic (MACD) - Drawdown - {trading_pair}',
                         fontsize=12, fontweight='bold')
            ax2.set_xlabel('Trade Number', fontsize=11)
            ax2.set_ylabel('Drawdown (%)', fontsize=11)
            ax2.grid(True, alpha=0.3)
            ax2.legend()
        
        plt.tight_layout()
        filename = self.output_dir / f"drawdown_{trading_pair.replace('-', '_')}.png"
        plt.savefig(filename, dpi=300, bbox_inches='tight')
        print(f"保存图表: {filename}")
        plt.close()
    
    def plot_trade_distribution(
        self,
        bp_trades_df: pd.DataFrame,
        macd_trades_df: pd.DataFrame,
        trading_pair: str
    ):
        """绘制交易P&L分布"""
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))
        
        # BP策略
        if len(bp_trades_df) > 0:
            ax1.hist(
                bp_trades_df['pnl'],
                bins=50,
                color='#2E86AB',
                alpha=0.7,
                edgecolor='black'
            )
            ax1.axvline(
                x=0,
                color='red',
                linestyle='--',
                linewidth=2,
                label='Break-even'
            )
            ax1.axvline(
                x=bp_trades_df['pnl'].mean(),
                color='green',
                linestyle='--',
                linewidth=2,
                label=f"Mean: ${bp_trades_df['pnl'].mean():.4f}"
            )
            ax1.set_title(f'PMM Bar Portion - Trade P&L Distribution',
                         fontsize=12, fontweight='bold')
            ax1.set_xlabel('Trade P&L ($)', fontsize=11)
            ax1.set_ylabel('Frequency', fontsize=11)
            ax1.legend()
            ax1.grid(True, alpha=0.3)
        
        # MACD策略
        if len(macd_trades_df) > 0:
            ax2.hist(
                macd_trades_df['pnl'],
                bins=50,
                color='#A23B72',
                alpha=0.7,
                edgecolor='black'
            )
            ax2.axvline(
                x=0,
                color='red',
                linestyle='--',
                linewidth=2,
                label='Break-even'
            )
            ax2.axvline(
                x=macd_trades_df['pnl'].mean(),
                color='green',
                linestyle='--',
                linewidth=2,
                label=f"Mean: ${macd_trades_df['pnl'].mean():.4f}"
            )
            ax2.set_title(f'PMM Dynamic (MACD) - Trade P&L Distribution',
                         fontsize=12, fontweight='bold')
            ax2.set_xlabel('Trade P&L ($)', fontsize=11)
            ax2.set_ylabel('Frequency', fontsize=11)
            ax2.legend()
            ax2.grid(True, alpha=0.3)
        
        plt.suptitle(f'{trading_pair} - Trade Distribution Comparison',
                    fontsize=14, fontweight='bold', y=1.02)
        plt.tight_layout()
        filename = self.output_dir / f"trade_distribution_{trading_pair.replace('-', '_')}.png"
        plt.savefig(filename, dpi=300, bbox_inches='tight')
        print(f"保存图表: {filename}")
        plt.close()
    
    def plot_metrics_comparison(
        self,
        comparison_data: List[Dict],
        metrics: List[str] = None
    ):
        """绘制多个交易对的指标对比"""
        if metrics is None:
            metrics = ['total_return_pct', 'sharpe_ratio', 'max_drawdown_pct', 'win_rate']
        
        metric_names = {
            'total_return_pct': 'Total Return (%)',
            'sharpe_ratio': 'Sharpe Ratio',
            'max_drawdown_pct': 'Max Drawdown (%)',
            'win_rate': 'Win Rate (%)'
        }
        
        n_metrics = len(metrics)
        fig, axes = plt.subplots(2, 2, figsize=(16, 12))
        axes = axes.flatten()
        
        for idx, metric in enumerate(metrics):
            ax = axes[idx]
            
            pairs = [d['trading_pair'] for d in comparison_data]
            bp_values = [d['bp_metrics'].get(metric, 0) for d in comparison_data]
            macd_values = [d['macd_metrics'].get(metric, 0) for d in comparison_data]
            
            x = np.arange(len(pairs))
            width = 0.35
            
            bars1 = ax.bar(
                x - width/2,
                bp_values,
                width,
                label='PMM Bar Portion',
                color='#2E86AB',
                alpha=0.8
            )
            bars2 = ax.bar(
                x + width/2,
                macd_values,
                width,
                label='PMM Dynamic (MACD)',
                color='#A23B72',
                alpha=0.8
            )
            
            ax.set_xlabel('Trading Pair', fontsize=11)
            ax.set_ylabel(metric_names.get(metric, metric), fontsize=11)
            ax.set_title(f'{metric_names.get(metric, metric)} Comparison',
                        fontsize=12, fontweight='bold')
            ax.set_xticks(x)
            ax.set_xticks(pairs)
            ax.legend()
            ax.grid(True, alpha=0.3, axis='y')
            
            # 添加数值标签
            for bars in [bars1, bars2]:
                for bar in bars:
                    height = bar.get_height()
                    ax.text(
                        bar.get_x() + bar.get_width()/2.,
                        height,
                        f'{height:.2f}',
                        ha='center',
                        va='bottom',
                        fontsize=9
                    )
        
        plt.suptitle('Strategy Performance Comparison Across Trading Pairs',
                    fontsize=14, fontweight='bold', y=1.00)
        plt.tight_layout()
        filename = self.output_dir / "metrics_comparison_all_pairs.png"
        plt.savefig(filename, dpi=300, bbox_inches='tight')
        print(f"保存图表: {filename}")
        plt.close()
    
    def generate_full_report(
        self,
        all_results: List[Dict],
        initial_capital: float = 1000
    ):
        """生成完整的可视化报告"""
        print("\n生成可视化报告...")
        print("="*80)
        
        # 为每个交易对生成图表
        for result in all_results:
            pair = result['trading_pair']
            bp_metrics = result['bp_metrics']
            macd_metrics = result['macd_metrics']
            
            print(f"\n处理 {pair}...")
            
            # 获取交易数据
            bp_trades = bp_metrics.get('trades_data', pd.DataFrame())
            macd_trades = macd_metrics.get('trades_data', pd.DataFrame())
            
            if len(bp_trades) > 0 or len(macd_trades) > 0:
                # 累积收益
                self.plot_cumulative_returns(
                    bp_trades, macd_trades, pair, initial_capital
                )
                
                # 回撤
                self.plot_drawdown(
                    bp_trades, macd_trades, pair, initial_capital
                )
                
                # 交易分布
                self.plot_trade_distribution(
                    bp_trades, macd_trades, pair
                )
        
        # 汇总对比
        print("\n生成汇总对比图...")
        self.plot_metrics_comparison(all_results)
        
        print("\n" + "="*80)
        print(f"所有图表已保存至: {self.output_dir}")
        print("="*80)


def main():
    """主函数"""
    # 这个脚本通常由backtest_comparison.py调用
    # 也可以单独运行来重新生成图表
    
    print("结果可视化工具")
    print("使用方法: 在backtest_comparison.py中自动调用")
    print("或者提供结果数据手动调用generate_full_report()")


if __name__ == "__main__":
    main()
