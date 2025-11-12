"""
回测对比脚本 - 复现论文实验

对比PMM Bar Portion策略与PMM Dynamic (MACD)基准策略
论文："Market Making in Crypto" by Stoikov et al. (2024)
"""

import asyncio
import sys
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Dict, List

import pandas as pd
import numpy as np

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from hummingbot.strategy_v2.backtesting.backtesting_engine_base import BacktestingEngineBase
from hummingbot.data_feed.candles_feed.candles_factory import CandlesConfig
from controllers.market_making.pmm_bar_portion import PMMBarPortionControllerConfig
from controllers.market_making.pmm_dynamic import PMMDynamicControllerConfig
from hummingbot.strategy_v2.executors.position_executor.data_types import TripleBarrierConfig


# 测试配置
TEST_PAIRS = ["SOL-USDT", "DOGE-USDT", "GALA-USDT"]
START_DATE = "2024-09-01"
END_DATE = "2024-10-14"
INITIAL_PORTFOLIO_USD = 1000  # 初始资金
TRADING_FEE = 0.0004  # 0.04% 交易费用


class StrategyBacktester:
    """策略回测器"""
    
    def __init__(
        self,
        trading_pair: str,
        start_date: str,
        end_date: str,
        initial_portfolio: float = INITIAL_PORTFOLIO_USD
    ):
        self.trading_pair = trading_pair
        self.start_date = start_date
        self.end_date = end_date
        self.initial_portfolio = initial_portfolio
        
    def create_bp_config(
        self,
        spreads: List[float] = None,
        stop_loss: float = 0.03,
        take_profit: float = 0.02,
        time_limit_minutes: int = 45
    ) -> PMMBarPortionControllerConfig:
        """创建Bar Portion策略配置"""
        if spreads is None:
            spreads = [0.01, 0.02]  # 1%, 2% spread
        
        return PMMBarPortionControllerConfig(
            controller_name="pmm_bar_portion",
            connector_name="binance_perpetual",
            trading_pair=self.trading_pair,
            candles_connector="binance_perpetual",
            candles_trading_pair=self.trading_pair,
            interval="1m",
            buy_spreads=spreads,
            sell_spreads=spreads,
            buy_amounts_pct=None,  # 平均分配
            sell_amounts_pct=None,
            executor_refresh_time=300,  # 5分钟
            cooldown_time=15,
            leverage=20,
            natr_length=14,
            training_window=51840,  # 36天 @ 1分钟
            atr_length=10,
            # Triple Barrier配置
            stop_loss=Decimal(str(stop_loss)),
            take_profit=Decimal(str(take_profit)),
            time_limit=time_limit_minutes * 60,
        )
    
    def create_macd_config(
        self,
        spreads: List[float] = None,
        stop_loss: float = 0.03,
        take_profit: float = 0.02,
        time_limit_minutes: int = 45,
        macd_fast: int = 21,
        macd_slow: int = 42,
        macd_signal: int = 9
    ) -> PMMDynamicControllerConfig:
        """创建MACD基准策略配置"""
        if spreads is None:
            spreads = [1.0, 2.0, 4.0]  # 以波动率倍数计
        
        return PMMDynamicControllerConfig(
            controller_name="pmm_dynamic",
            connector_name="binance_perpetual",
            trading_pair=self.trading_pair,
            candles_connector="binance_perpetual",
            candles_trading_pair=self.trading_pair,
            interval="1m",
            buy_spreads=spreads,
            sell_spreads=spreads,
            buy_amounts_pct=None,
            sell_amounts_pct=None,
            executor_refresh_time=300,
            cooldown_time=15,
            leverage=20,
            macd_fast=macd_fast,
            macd_slow=macd_slow,
            macd_signal=macd_signal,
            natr_length=14,
            # Triple Barrier配置
            stop_loss=Decimal(str(stop_loss)),
            take_profit=Decimal(str(take_profit)),
            time_limit=time_limit_minutes * 60,
        )
    
    async def run_backtest(
        self,
        config,
        backtesting_resolution: str = "1m"
    ) -> Dict:
        """
        运行回测
        
        Args:
            config: 策略配置
            backtesting_resolution: 回测时间分辨率
            
        Returns:
            Dict: 回测结果
        """
        print(f"\n运行回测: {config.controller_name} - {self.trading_pair}")
        print(f"时间范围: {self.start_date} 至 {self.end_date}")
        
        try:
            # 创建回测引擎
            engine = BacktestingEngineBase()
            engine.config = config
            
            # 运行回测
            results = await engine.run_backtest(
                start=self.start_date,
                end=self.end_date,
                backtesting_resolution=backtesting_resolution
            )
            
            return results
            
        except Exception as e:
            print(f"回测失败: {str(e)}")
            import traceback
            traceback.print_exc()
            return None


class PerformanceAnalyzer:
    """性能分析器"""
    
    @staticmethod
    def calculate_metrics(results: Dict, initial_capital: float = INITIAL_PORTFOLIO_USD) -> Dict:
        """
        计算性能指标
        
        指标包括:
        - Total Return
        - Sharpe Ratio
        - Maximum Drawdown
        - Win Rate
        - Total Trades
        - Average Trade P&L
        """
        if not results or 'executors' not in results:
            return {}
        
        executors = results['executors']
        
        # 提取交易数据
        trades = []
        for executor in executors:
            if 'close_type' in executor and executor['close_type'] != 'EXPIRED':
                trade_pnl = executor.get('net_pnl', 0)
                trades.append({
                    'pnl': trade_pnl,
                    'timestamp': executor.get('close_timestamp', 0),
                    'side': executor.get('side', 'BUY'),
                    'close_type': executor.get('close_type', 'UNKNOWN')
                })
        
        if len(trades) == 0:
            return {
                'total_return': 0.0,
                'total_return_pct': 0.0,
                'sharpe_ratio': 0.0,
                'max_drawdown': 0.0,
                'max_drawdown_pct': 0.0,
                'win_rate': 0.0,
                'total_trades': 0,
                'winning_trades': 0,
                'losing_trades': 0,
                'avg_trade_pnl': 0.0,
                'total_pnl': 0.0
            }
        
        # 计算累积P&L
        trades_df = pd.DataFrame(trades)
        trades_df = trades_df.sort_values('timestamp')
        trades_df['cumulative_pnl'] = trades_df['pnl'].cumsum()
        trades_df['portfolio_value'] = initial_capital + trades_df['cumulative_pnl']
        
        # 计算回报
        total_pnl = trades_df['pnl'].sum()
        total_return_pct = (total_pnl / initial_capital) * 100
        
        # 计算Sharpe Ratio
        if len(trades_df) > 1:
            returns = trades_df['portfolio_value'].pct_change().dropna()
            if returns.std() != 0:
                sharpe_ratio = (returns.mean() / returns.std()) * np.sqrt(len(trades_df))
            else:
                sharpe_ratio = 0.0
        else:
            sharpe_ratio = 0.0
        
        # 计算最大回撤
        portfolio_values = trades_df['portfolio_value'].values
        running_max = np.maximum.accumulate(portfolio_values)
        drawdowns = (portfolio_values - running_max) / running_max
        max_drawdown_pct = abs(drawdowns.min()) * 100 if len(drawdowns) > 0 else 0.0
        max_drawdown = abs(drawdowns.min() * initial_capital) if len(drawdowns) > 0 else 0.0
        
        # 计算胜率
        winning_trades = len(trades_df[trades_df['pnl'] > 0])
        losing_trades = len(trades_df[trades_df['pnl'] < 0])
        win_rate = (winning_trades / len(trades_df)) * 100 if len(trades_df) > 0 else 0.0
        
        # 平均交易P&L
        avg_trade_pnl = trades_df['pnl'].mean()
        
        return {
            'total_return': total_pnl,
            'total_return_pct': total_return_pct,
            'sharpe_ratio': sharpe_ratio,
            'max_drawdown': max_drawdown,
            'max_drawdown_pct': max_drawdown_pct,
            'win_rate': win_rate,
            'total_trades': len(trades_df),
            'winning_trades': winning_trades,
            'losing_trades': losing_trades,
            'avg_trade_pnl': avg_trade_pnl,
            'total_pnl': total_pnl,
            'trades_data': trades_df
        }
    
    @staticmethod
    def compare_strategies(bp_metrics: Dict, macd_metrics: Dict) -> pd.DataFrame:
        """对比两个策略的指标"""
        comparison = {
            'Metric': [
                'Total Return ($)',
                'Total Return (%)',
                'Sharpe Ratio',
                'Max Drawdown ($)',
                'Max Drawdown (%)',
                'Win Rate (%)',
                'Total Trades',
                'Winning Trades',
                'Losing Trades',
                'Avg Trade P&L ($)'
            ],
            'PMM Bar Portion': [
                f"${bp_metrics.get('total_return', 0):.2f}",
                f"{bp_metrics.get('total_return_pct', 0):.2f}%",
                f"{bp_metrics.get('sharpe_ratio', 0):.4f}",
                f"${bp_metrics.get('max_drawdown', 0):.2f}",
                f"{bp_metrics.get('max_drawdown_pct', 0):.2f}%",
                f"{bp_metrics.get('win_rate', 0):.2f}%",
                bp_metrics.get('total_trades', 0),
                bp_metrics.get('winning_trades', 0),
                bp_metrics.get('losing_trades', 0),
                f"${bp_metrics.get('avg_trade_pnl', 0):.4f}"
            ],
            'PMM Dynamic (MACD)': [
                f"${macd_metrics.get('total_return', 0):.2f}",
                f"{macd_metrics.get('total_return_pct', 0):.2f}%",
                f"{macd_metrics.get('sharpe_ratio', 0):.4f}",
                f"${macd_metrics.get('max_drawdown', 0):.2f}",
                f"{macd_metrics.get('max_drawdown_pct', 0):.2f}%",
                f"{macd_metrics.get('win_rate', 0):.2f}%",
                macd_metrics.get('total_trades', 0),
                macd_metrics.get('winning_trades', 0),
                macd_metrics.get('losing_trades', 0),
                f"${macd_metrics.get('avg_trade_pnl', 0):.4f}"
            ]
        }
        
        return pd.DataFrame(comparison)


async def run_single_pair_comparison(trading_pair: str):
    """对单个交易对运行策略对比"""
    print("\n" + "="*80)
    print(f"回测交易对: {trading_pair}")
    print("="*80)
    
    backtester = StrategyBacktester(
        trading_pair=trading_pair,
        start_date=START_DATE,
        end_date=END_DATE,
        initial_portfolio=INITIAL_PORTFOLIO_USD
    )
    
    # 创建配置
    bp_config = backtester.create_bp_config()
    macd_config = backtester.create_macd_config()
    
    # 运行回测
    print("\n[1/2] 运行PMM Bar Portion策略回测...")
    bp_results = await backtester.run_backtest(bp_config)
    
    print("\n[2/2] 运行PMM Dynamic (MACD)策略回测...")
    macd_results = await backtester.run_backtest(macd_config)
    
    # 分析结果
    analyzer = PerformanceAnalyzer()
    
    bp_metrics = analyzer.calculate_metrics(bp_results) if bp_results else {}
    macd_metrics = analyzer.calculate_metrics(macd_results) if macd_results else {}
    
    # 打印对比
    print("\n" + "="*80)
    print(f"策略对比结果 - {trading_pair}")
    print("="*80)
    
    comparison_df = analyzer.compare_strategies(bp_metrics, macd_metrics)
    print(comparison_df.to_string(index=False))
    
    return {
        'trading_pair': trading_pair,
        'bp_metrics': bp_metrics,
        'macd_metrics': macd_metrics,
        'comparison_df': comparison_df
    }


async def run_full_comparison():
    """对论文中的所有测试交易对运行完整对比"""
    print("\n" + "="*80)
    print("论文策略完整对比测试")
    print("="*80)
    print(f"测试交易对: {', '.join(TEST_PAIRS)}")
    print(f"时间范围: {START_DATE} 至 {END_DATE}")
    print(f"初始资金: ${INITIAL_PORTFOLIO_USD}")
    print("="*80)
    
    all_results = []
    
    for pair in TEST_PAIRS:
        result = await run_single_pair_comparison(pair)
        all_results.append(result)
        
        # 间隔一下避免过载
        await asyncio.sleep(1)
    
    # 汇总结果
    print("\n" + "="*80)
    print("汇总结果")
    print("="*80)
    
    summary_data = []
    for result in all_results:
        pair = result['trading_pair']
        bp = result['bp_metrics']
        macd = result['macd_metrics']
        
        summary_data.append({
            'Trading Pair': pair,
            'BP Return (%)': f"{bp.get('total_return_pct', 0):.2f}%",
            'MACD Return (%)': f"{macd.get('total_return_pct', 0):.2f}%",
            'BP Sharpe': f"{bp.get('sharpe_ratio', 0):.4f}",
            'MACD Sharpe': f"{macd.get('sharpe_ratio', 0):.4f}",
            'BP Max DD (%)': f"{bp.get('max_drawdown_pct', 0):.2f}%",
            'MACD Max DD (%)': f"{macd.get('max_drawdown_pct', 0):.2f}%",
        })
    
    summary_df = pd.DataFrame(summary_data)
    print(summary_df.to_string(index=False))
    
    # 保存结果
    output_dir = Path("/workspace/data/paper_replication/results")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    summary_df.to_csv(output_dir / f"comparison_summary_{timestamp}.csv", index=False)
    
    print(f"\n结果已保存至: {output_dir}")
    
    return all_results


async def main():
    """主函数"""
    if len(sys.argv) > 1:
        pair = sys.argv[1].upper()
        if pair in TEST_PAIRS:
            await run_single_pair_comparison(pair)
        elif pair == "ALL":
            await run_full_comparison()
        else:
            print(f"未知交易对: {pair}")
            print(f"可用选项: {', '.join(TEST_PAIRS + ['ALL'])}")
    else:
        # 默认运行完整对比
        await run_full_comparison()


if __name__ == "__main__":
    asyncio.run(main())
