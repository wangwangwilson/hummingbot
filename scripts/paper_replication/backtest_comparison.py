"""
回测对比脚本 - 复现论文实验

对比PMM Bar Portion策略与PMM Dynamic (MACD)基准策略
论文："Market Making in Crypto" by Stoikov et al. (2024)
"""

import asyncio
import os
import sys
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Dict, List

import pandas as pd
import numpy as np

# 配置SSL证书（支持zerotrust VPN）
cert_file = Path.home() / ".hummingbot_certs.pem"
if cert_file.exists():
    os.environ['SSL_CERT_FILE'] = str(cert_file)
    os.environ['REQUESTS_CA_BUNDLE'] = str(cert_file)
    os.environ['CURL_CA_BUNDLE'] = str(cert_file)

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from hummingbot.strategy_v2.backtesting.backtesting_engine_base import BacktestingEngineBase
from hummingbot.data_feed.candles_feed.candles_factory import CandlesConfig
from controllers.market_making.pmm_bar_portion import PMMBarPortionControllerConfig
from controllers.market_making.pmm_dynamic import PMMDynamicControllerConfig
from hummingbot.strategy_v2.executors.position_executor.data_types import TripleBarrierConfig


# 测试配置
TEST_PAIRS = ["SOL-USDT", "DOGE-USDT", "GALA-USDT"]

# 自定义交易对（最近半年回测）
CUSTOM_TEST_PAIRS = ["BTC-USDT", "SOL-USDT", "ETH-USDT", "XRP-USDT", "AVAX-USDT", "DOT-USDT", "MYX-USDT"]

# 论文时间范围
PAPER_START_DATE = "2024-09-01"
PAPER_END_DATE = "2024-10-14"

# 最近1天时间范围（用于快速验证）
def get_last_1_day_dates():
    """获取最近1天的日期字符串"""
    from datetime import datetime, timedelta
    current_year = datetime.now().year
    if current_year > 2024:
        end_date = datetime(2024, 11, 12)
    else:
        end_date = datetime.now()
    start_date = end_date - timedelta(days=1)
    return start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")

# 最近半年时间范围（2025-01-01 至 2025-11-12）
def get_last_6_months_dates():
    """获取最近6个月的日期字符串（2025-01-01 至 2025-11-12）"""
    from datetime import datetime
    start_date = datetime(2025, 1, 1)
    end_date = datetime(2025, 11, 12)
    return start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")

# 默认使用论文时间范围
START_DATE = PAPER_START_DATE
END_DATE = PAPER_END_DATE

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
            
            # 转换日期字符串为时间戳（秒，不是毫秒）
            from datetime import datetime
            start_dt = datetime.strptime(self.start_date, "%Y-%m-%d")
            end_dt = datetime.strptime(self.end_date, "%Y-%m-%d")
            # HistoricalCandlesConfig期望的是秒级时间戳
            start_ts = int(start_dt.timestamp())
            end_ts = int(end_dt.timestamp())
            
            # 验证数据获取（在回测前）
            print(f"验证数据获取...")
            from hummingbot.data_feed.candles_feed.candles_factory import CandlesFactory
            from hummingbot.data_feed.candles_feed.data_types import CandlesConfig, HistoricalCandlesConfig
            
            test_candle = CandlesFactory.get_candle(CandlesConfig(
                connector=config.candles_connector,
                trading_pair=config.candles_trading_pair,
                interval=config.interval,
                max_records=10000
            ))
            
            test_config = HistoricalCandlesConfig(
                connector_name=config.candles_connector,
                trading_pair=config.candles_trading_pair,
                interval=config.interval,
                start_time=start_ts,
                end_time=end_ts
            )
            
            # 添加重试机制
            max_retries = 3
            test_df = None
            for retry in range(max_retries):
                try:
                    test_df = await test_candle.get_historical_candles(test_config)
                    if len(test_df) > 0:
                        break
                    if retry < max_retries - 1:
                        print(f"  重试 {retry + 1}/{max_retries}...")
                        await asyncio.sleep(1)  # 等待1秒后重试
                except Exception as e:
                    if "429" in str(e) or "Too many requests" in str(e):
                        wait_time = (retry + 1) * 2  # 指数退避：2秒、4秒、6秒
                        print(f"  API限流，等待 {wait_time} 秒后重试...")
                        await asyncio.sleep(wait_time)
                    else:
                        print(f"  数据获取错误: {e}")
                        if retry < max_retries - 1:
                            await asyncio.sleep(1)
            
            if test_df is None or len(test_df) == 0:
                print(f"⚠️  错误: 数据获取失败（已重试{max_retries}次）！")
                print(f"   时间范围: {self.start_date} 至 {self.end_date}")
                print(f"   时间戳: {start_ts} ({datetime.fromtimestamp(start_ts)}) 至 {end_ts} ({datetime.fromtimestamp(end_ts)})")
                print(f"   建议: 检查网络连接、API限流状态或时间范围是否正确")
                return None
            
            print(f"✓ 数据获取成功: {len(test_df)} 条K线")
            if len(test_df) < 100:
                print(f"⚠️  警告: 数据量不足（{len(test_df)} < 100），可能影响回测质量")
            else:
                print(f"✓ 数据量充足: {len(test_df)} 条K线")
            
            # 运行回测
            results = await engine.run_backtesting(
                controller_config=config,
                start=start_ts,
                end=end_ts,
                backtesting_resolution=backtesting_resolution,
                trade_cost=TRADING_FEE
            )
            
            # 验证结果 - run_backtesting返回的是字典，包含executors列表
            if results:
                if isinstance(results, dict) and 'executors' in results:
                    executors = results['executors']
                    print(f"✓ 回测完成，生成 {len(executors)} 个executor")
                    if len(executors) == 0:
                        print(f"⚠️  警告: 未生成任何executor，可能是:")
                        print(f"   - 数据不足（需要至少100条K线）")
                        print(f"   - 价格未达到挂单价格（限价单）")
                        print(f"   - 时间范围太短")
                        # 检查processed_data
                        if 'processed_data' in results:
                            pd_data = results['processed_data']
                            if 'reference_price' in pd_data:
                                ref_price = pd_data['reference_price']
                                print(f"   - 参考价格: {ref_price}")
                                if ref_price == 0 or ref_price == Decimal("0"):
                                    print(f"   ⚠️  参考价格为0，说明数据获取失败！")
                            if 'spread_multiplier' in pd_data:
                                print(f"   - 价差倍数: {pd_data['spread_multiplier']}")
                    else:
                        # 统计成交的executor
                        filled = [e for e in executors if hasattr(e, 'filled_amount_quote') and float(e.filled_amount_quote) > 0]
                        active = [e for e in executors if hasattr(e, 'is_active') and e.is_active]
                        print(f"  - 活跃executor: {len(active)}/{len(executors)}")
                        print(f"  - 成交executor: {len(filled)}/{len(executors)}")
                        if len(filled) > 0:
                            total_pnl = sum(float(e.net_pnl_quote) for e in filled)
                            print(f"  - 总盈亏: ${total_pnl:.2f}")
                            # 显示前3个成交的executor详情
                            for i, e in enumerate(filled[:3]):
                                print(f"    Executor {i+1}: PnL=${float(e.net_pnl_quote):.2f}, Amount=${float(e.filled_amount_quote):.2f}")
                        else:
                            print(f"  ⚠️  所有executor都未成交，可能是限价单价格设置不当")
                            if len(executors) > 0:
                                e = executors[0]
                                print(f"    示例executor: entry_price={e.config.entry_price if hasattr(e, 'config') else 'N/A'}")
                elif isinstance(results, list):
                    print(f"✓ 回测完成，生成 {len(results)} 个executor（列表格式）")
                else:
                    print(f"✓ 回测完成，返回格式: {type(results)}")
            
            return results
            
        except IndexError as e:
            print(f"回测失败: 数据不足 - {str(e)}")
            print(f"提示: 请检查数据文件是否存在，或时间范围是否正确")
            import traceback
            traceback.print_exc()
            return None
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
        
        Args:
            results: 回测结果，可能是字典（包含'executors'）或executors列表
            initial_capital: 初始资金
        """
        # 处理不同的结果格式
        if isinstance(results, dict):
            if 'executors' in results:
                executors = results['executors']
            elif 'results' in results:
                # 如果已经有汇总结果，直接使用
                return results['results']
            else:
                executors = []
        elif isinstance(results, list):
            executors = results
        else:
            return {}
        
        # 提取交易数据 - executors是ExecutorInfo对象列表
        trades = []
        for executor in executors:
            # ExecutorInfo对象有属性，不是字典
            if hasattr(executor, 'close_type') and executor.close_type is not None:
                # 只统计已关闭且有成交的executor
                if float(executor.filled_amount_quote) > 0:
                    trade_pnl = float(executor.net_pnl_quote)
                    trades.append({
                        'pnl': trade_pnl,
                        'timestamp': float(executor.close_timestamp) if executor.close_timestamp else 0,
                        'side': str(executor.side) if hasattr(executor, 'side') else 'BUY',
                        'close_type': str(executor.close_type) if executor.close_type else 'UNKNOWN',
                        'filled_amount': float(executor.filled_amount_quote)
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


async def run_single_pair_comparison(trading_pair: str, use_custom_dates: bool = False, use_1day: bool = False):
    """对单个交易对运行策略对比"""
    print("\n" + "="*80)
    print(f"回测交易对: {trading_pair}")
    print("="*80)
    
    # 如果使用1天测试，使用最近1天
    if use_1day:
        start_date, end_date = get_last_1_day_dates()
        print(f"⚠️  使用最近1天数据（快速验证模式）")
    # 如果使用自定义日期，使用最近6个月
    elif use_custom_dates:
        start_date, end_date = get_last_6_months_dates()
    else:
        start_date, end_date = START_DATE, END_DATE
    
    backtester = StrategyBacktester(
        trading_pair=trading_pair,
        start_date=start_date,
        end_date=end_date,
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
    def get_output_dir():
        """获取输出目录"""
        workspace_dir = Path("/workspace/data/paper_replication/results")
        if workspace_dir.parent.parent.exists():
            return workspace_dir
        project_root = Path(__file__).parent.parent.parent
        return project_root / "data" / "paper_replication" / "results"
    
    output_dir = get_output_dir()
    output_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    summary_df.to_csv(output_dir / f"comparison_summary_{timestamp}.csv", index=False)
    
    print(f"\n结果已保存至: {output_dir}")
    
    return all_results


def run_single_pair_sync(pair: str, start_date: str, end_date: str, initial_portfolio: float):
    """同步运行单个交易对回测（用于多进程）"""
    import asyncio
    import sys
    import os
    from pathlib import Path
    from decimal import Decimal
    
    # 重新设置路径（多进程需要）
    script_dir = Path(__file__).parent
    project_root = script_dir.parent.parent
    sys.path.insert(0, str(project_root))
    
    # 配置SSL证书
    cert_file = Path.home() / ".hummingbot_certs.pem"
    if cert_file.exists():
        os.environ['SSL_CERT_FILE'] = str(cert_file)
        os.environ['REQUESTS_CA_BUNDLE'] = str(cert_file)
        os.environ['CURL_CA_BUNDLE'] = str(cert_file)
    
    try:
        # 重新导入所有必要的类和函数（多进程需要）
        # 注意：这里需要重新定义，因为多进程无法共享主进程的导入
        from scripts.paper_replication.backtest_comparison import (
            StrategyBacktester, 
            PerformanceAnalyzer
        )
        
        # 创建回测器
        backtester = StrategyBacktester(
            trading_pair=pair,
            start_date=start_date,
            end_date=end_date,
            initial_portfolio=initial_portfolio
        )
        
        # 运行回测
        bp_config = backtester.create_bp_config()
        macd_config = backtester.create_macd_config()
        
        # 运行回测
        bp_results = asyncio.run(backtester.run_backtest(bp_config))
        macd_results = asyncio.run(backtester.run_backtest(macd_config))
        
        # 分析结果
        analyzer = PerformanceAnalyzer()
        bp_metrics = analyzer.calculate_metrics(bp_results) if bp_results else {}
        macd_metrics = analyzer.calculate_metrics(macd_results) if macd_results else {}
        
        return {
            'trading_pair': pair,
            'bp_metrics': bp_metrics,
            'macd_metrics': macd_metrics,
            'bp_results': bp_results,
            'macd_results': macd_results
        }
    except Exception as e:
        import traceback
        error_msg = f"{str(e)}\n{traceback.format_exc()}"
        print(f"错误 [{pair}]: {error_msg}")
        return {
            'trading_pair': pair,
            'bp_metrics': {},
            'macd_metrics': {},
            'error': error_msg
        }


async def run_custom_pairs_comparison(use_1day: bool = False, parallel: bool = True, max_workers: int = 8):
    """运行自定义交易对的回测（支持asyncio并发）"""
    global START_DATE, END_DATE
    from datetime import datetime as dt
    
    print("\n" + "="*80)
    if use_1day:
        print("自定义交易对回测（最近1天 - 并发模式）")
    else:
        print("自定义交易对回测（最近半年：2025-01-01 至 2025-11-12）")
    print("="*80)
    print(f"测试交易对: {', '.join(CUSTOM_TEST_PAIRS)}")
    
    # 设置时间范围
    if use_1day:
        START_DATE, END_DATE = get_last_1_day_dates()
    else:
        START_DATE, END_DATE = get_last_6_months_dates()
    print(f"时间范围: {START_DATE} 至 {END_DATE}")
    print(f"初始资金: ${INITIAL_PORTFOLIO_USD}")
    print(f"交易费用: {TRADING_FEE*100:.2f}%")
    
    if parallel:
        print(f"并发模式: 启用（最多{max_workers}个并发任务）")
    else:
        print("并发模式: 禁用（顺序执行）")
    print("="*80)
    
    all_results = []
    start_time = dt.now()
    
    if parallel:
        # 使用asyncio并发执行，但添加延迟避免API限流
        print(f"\n开始并发回测（{len(CUSTOM_TEST_PAIRS)} 个交易对）...")
        print(f"⚠️  注意: 为避免API限流，将分批处理并添加延迟")
        
        # 减少并发数，避免API限流（Binance限制2400 requests/minute）
        # 每个交易对需要多次API调用，所以减少并发数
        safe_max_workers = min(max_workers, 4)  # 最多4个并发，避免限流
        semaphore = asyncio.Semaphore(safe_max_workers)
        
        async def run_with_semaphore_and_delay(pair, index):
            async with semaphore:
                # 添加延迟，避免同时发起太多请求
                if index > 0:
                    await asyncio.sleep(index * 0.5)  # 每个任务延迟0.5秒
                return await run_single_pair_comparison(pair, use_custom_dates=True, use_1day=use_1day)
        
        # 创建所有任务（带索引用于延迟）
        tasks = [run_with_semaphore_and_delay(pair, i) for i, pair in enumerate(CUSTOM_TEST_PAIRS)]
        
        # 并发执行并收集结果
        completed = 0
        for coro in asyncio.as_completed(tasks):
            completed += 1
            try:
                result = await coro
                all_results.append(result)
                elapsed = (dt.now() - start_time).total_seconds()
                pair = result.get('trading_pair', 'Unknown')
                print(f"[{completed}/{len(CUSTOM_TEST_PAIRS)}] ✓ {pair} 完成 (耗时: {elapsed:.1f}秒)")
                # 完成后短暂延迟，避免API限流
                await asyncio.sleep(0.2)
            except Exception as e:
                print(f"[{completed}/{len(CUSTOM_TEST_PAIRS)}] ✗ 失败: {e}")
                all_results.append({
                    'trading_pair': 'Unknown',
                    'bp_metrics': {},
                    'macd_metrics': {},
                    'error': str(e)
                })
    else:
        # 顺序执行
        for i, pair in enumerate(CUSTOM_TEST_PAIRS, 1):
            print(f"\n[{i}/{len(CUSTOM_TEST_PAIRS)}] 处理 {pair}...")
            result = await run_single_pair_comparison(pair, use_custom_dates=True, use_1day=use_1day)
            all_results.append(result)
            await asyncio.sleep(0.5)  # 短暂延迟避免过载
    
    total_time = (dt.now() - start_time).total_seconds()
    print(f"\n✓ 所有回测完成，总耗时: {total_time:.1f}秒 ({total_time/60:.1f}分钟)")
    print(f"平均每个交易对: {total_time/len(CUSTOM_TEST_PAIRS):.1f}秒")
    
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
    def get_output_dir():
        """获取输出目录"""
        workspace_dir = Path("/workspace/data/paper_replication/results")
        if workspace_dir.parent.parent.exists():
            return workspace_dir
        project_root = Path(__file__).parent.parent.parent
        return project_root / "data" / "paper_replication" / "results"
    
    output_dir = get_output_dir()
    output_dir.mkdir(parents=True, exist_ok=True)
    
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    summary_file = output_dir / f"custom_comparison_summary_{timestamp}.csv"
    summary_df.to_csv(summary_file, index=False)
    
    # 生成详细报告
    report_file = output_dir / f"backtest_report_{timestamp}.txt"
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write("="*80 + "\n")
        f.write("回测报告\n")
        f.write("="*80 + "\n\n")
        f.write(f"时间范围: {START_DATE} 至 {END_DATE}\n")
        f.write(f"测试交易对: {', '.join(CUSTOM_TEST_PAIRS)}\n")
        f.write(f"初始资金: ${INITIAL_PORTFOLIO_USD}\n")
        f.write(f"交易费用: {TRADING_FEE*100:.2f}%\n")
        f.write(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write("="*80 + "\n")
        f.write("汇总结果\n")
        f.write("="*80 + "\n\n")
        f.write(summary_df.to_string(index=False))
        f.write("\n\n")
        f.write("="*80 + "\n")
        f.write("各交易对详细结果\n")
        f.write("="*80 + "\n\n")
        for i, (pair, result) in enumerate(zip(CUSTOM_TEST_PAIRS, all_results), 1):
            f.write(f"\n[{i}/{len(CUSTOM_TEST_PAIRS)}] {pair}\n")
            f.write("-"*80 + "\n")
            if result:
                bp_metrics = result.get('bp_metrics', {})
                macd_metrics = result.get('macd_metrics', {})
                f.write(f"PMM Bar Portion:\n")
                f.write(f"  总收益: ${bp_metrics.get('total_return', 0):.2f} ({bp_metrics.get('total_return_pct', 0):.2f}%)\n")
                f.write(f"  Sharpe Ratio: {bp_metrics.get('sharpe_ratio', 0):.4f}\n")
                f.write(f"  最大回撤: ${bp_metrics.get('max_drawdown', 0):.2f} ({bp_metrics.get('max_drawdown_pct', 0):.2f}%)\n")
                f.write(f"  胜率: {bp_metrics.get('win_rate', 0):.2f}%\n")
                f.write(f"  总交易: {bp_metrics.get('total_trades', 0)}\n")
                f.write(f"PMM Dynamic (MACD):\n")
                f.write(f"  总收益: ${macd_metrics.get('total_return', 0):.2f} ({macd_metrics.get('total_return_pct', 0):.2f}%)\n")
                f.write(f"  Sharpe Ratio: {macd_metrics.get('sharpe_ratio', 0):.4f}\n")
                f.write(f"  最大回撤: ${macd_metrics.get('max_drawdown', 0):.2f} ({macd_metrics.get('max_drawdown_pct', 0):.2f}%)\n")
                f.write(f"  胜率: {macd_metrics.get('win_rate', 0):.2f}%\n")
                f.write(f"  总交易: {macd_metrics.get('total_trades', 0)}\n")
    
    print(f"\n结果已保存至: {output_dir}")
    print(f"  - 汇总CSV: {summary_file.name}")
    print(f"  - 详细报告: {report_file.name}")
    
    return all_results


async def main():
    """主函数"""
    if len(sys.argv) > 1:
        pair = sys.argv[1].upper()
        if pair in TEST_PAIRS:
            await run_single_pair_comparison(pair)
        elif pair in CUSTOM_TEST_PAIRS:
            # 支持单个自定义交易对（使用最近1天快速验证）
            await run_single_pair_comparison(pair, use_custom_dates=True, use_1day=True)
        elif pair == "ALL":
            await run_full_comparison()
        elif pair == "CUSTOM" or pair == "6MONTHS":
            # 运行自定义交易对回测（使用最近半年：2025-01-01 至 2025-11-12）
            await run_custom_pairs_comparison(use_1day=False, parallel=True, max_workers=8)
        elif pair == "TEST" or pair == "1DAY":
            # 快速测试模式（最近1天，并行）
            await run_custom_pairs_comparison(use_1day=True, parallel=True, max_workers=8)
        else:
            print(f"未知交易对: {pair}")
            print(f"可用选项: {', '.join(TEST_PAIRS + CUSTOM_TEST_PAIRS + ['ALL', 'CUSTOM/6MONTHS'])}")
    else:
        # 默认运行完整对比
        await run_full_comparison()


if __name__ == "__main__":
    asyncio.run(main())
