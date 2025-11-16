#!/usr/bin/env python3
"""
最近1个月回测对比分析 - BTC、SOL、ETH
包括盈亏归因分析和参数合理性分析
"""

import asyncio
import sys
import json
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Dict, List
import pandas as pd
import numpy as np

# 配置SSL证书
cert_file = Path.home() / ".hummingbot_certs.pem"
if cert_file.exists():
    import os
    os.environ['SSL_CERT_FILE'] = str(cert_file)
    os.environ['REQUESTS_CA_BUNDLE'] = str(cert_file)
    os.environ['CURL_CA_BUNDLE'] = str(cert_file)

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
tradingview_ai_path = Path("/Users/wilson/Desktop/tradingview-ai")
sys.path.insert(0, str(tradingview_ai_path))

# 临时禁用ccxt
class FakeCCXT:
    pass
sys.modules['ccxt'] = FakeCCXT()

from hummingbot.strategy_v2.backtesting.backtesting_engine_base import BacktestingEngineBase
from controllers.market_making.pmm_bar_portion import PMMBarPortionControllerConfig
from controllers.market_making.pmm_dynamic import PMMDynamicControllerConfig
from hummingbot.strategy_v2.executors.position_executor.data_types import TripleBarrierConfig, OrderType

# 导入本地数据管理器
from backtest_comparison_local import LocalBinanceDataProvider, LocalBacktestingDataProvider

# 交易对列表
TRADING_PAIRS = ["BTC-USDT", "SOL-USDT", "ETH-USDT"]

# 最近1个月时间范围
def get_last_1_month_dates():
    """获取最近1个月的日期范围"""
    # 使用固定日期范围（2025-10-11 至 2025-11-11）
    start_date = datetime(2025, 10, 11)
    end_date = datetime(2025, 11, 11)
    return start_date, end_date

# 策略配置
def create_bp_config(trading_pair: str, total_amount: Decimal) -> PMMBarPortionControllerConfig:
    """创建PMM Bar Portion策略配置"""
    return PMMBarPortionControllerConfig(
        controller_name="pmm_bar_portion",
        connector_name="binance_perpetual",
        trading_pair=trading_pair,
        total_amount_quote=total_amount,
        buy_spreads=[0.01, 0.02],  # 1%, 2% (以波动率单位)
        sell_spreads=[0.01, 0.02],
        buy_amounts_pct=[Decimal("0.5"), Decimal("0.5")],
        sell_amounts_pct=[Decimal("0.5"), Decimal("0.5")],
        candles_connector="binance_perpetual",
        candles_trading_pair=trading_pair,
        interval="1m",
        stop_loss=Decimal("0.01"),  # 1%止损
        take_profit=Decimal("0.005"),  # 0.5%止盈
        time_limit=3600,  # 1小时
        take_profit_order_type=OrderType.MARKET
    )

def create_macd_config(trading_pair: str, total_amount: Decimal) -> PMMDynamicControllerConfig:
    """创建PMM Dynamic (MACD)策略配置"""
    return PMMDynamicControllerConfig(
        controller_name="pmm_dynamic",
        connector_name="binance_perpetual",
        trading_pair=trading_pair,
        total_amount_quote=total_amount,
        buy_spreads=[0.01, 0.02],
        sell_spreads=[0.01, 0.02],
        buy_amounts_pct=[Decimal("0.5"), Decimal("0.5")],
        sell_amounts_pct=[Decimal("0.5"), Decimal("0.5")],
        candles_connector="binance_perpetual",
        candles_trading_pair=trading_pair,
        interval="1m",
        stop_loss=Decimal("0.01"),
        take_profit=Decimal("0.005"),
        time_limit=3600,
        take_profit_order_type=OrderType.MARKET
    )

async def run_backtest(engine: BacktestingEngineBase, config, start_ts: int, end_ts: int, 
                      strategy_name: str, symbol: str) -> Dict:
    """运行单个策略回测"""
    try:
        from controllers.market_making.pmm_bar_portion import PMMBarPortionController
        from controllers.market_making.pmm_dynamic import PMMDynamicController
        
        if isinstance(config, PMMBarPortionControllerConfig):
            controller = PMMBarPortionController(
                config=config,
                market_data_provider=engine.backtesting_data_provider,
                actions_queue=None
            )
        elif isinstance(config, PMMDynamicControllerConfig):
            controller = PMMDynamicController(
                config=config,
                market_data_provider=engine.backtesting_data_provider,
                actions_queue=None
            )
        else:
            raise ValueError(f"Unknown config type: {type(config)}")
        
        # 运行回测
        result = await engine.run_backtesting(
            controller_config=config,
            start=start_ts,
            end=end_ts,
            backtesting_resolution="1m",  # 1分钟（字符串格式）
            trade_cost=Decimal("0.0004"),  # 0.04%
            show_progress=True
        )
        
        return result
        
    except Exception as e:
        print(f"  ✗ 回测失败: {e}")
        import traceback
        traceback.print_exc()
        return None

async def run_symbol_backtest(symbol: str, start_date: datetime, end_date: datetime) -> Dict:
    """运行单个品种的回测"""
    print(f"\n{'='*80}")
    print(f"回测品种: {symbol}")
    print(f"时间范围: {start_date.strftime('%Y-%m-%d')} 至 {end_date.strftime('%Y-%m-%d')}")
    print(f"{'='*80}")
    
    # 转换时间戳
    start_ts = int(start_date.timestamp())
    end_ts = int(end_date.timestamp())
    
    # 初始化数据提供器
    print(f"\n[{symbol}] 初始化数据提供器...")
    local_data_provider = LocalBinanceDataProvider()
    local_backtesting_provider = LocalBacktestingDataProvider(local_data_provider)
    local_backtesting_provider.update_backtesting_time(start_ts, end_ts)
    
    # 验证数据加载
    print(f"[{symbol}] 验证数据加载...")
    test_df = local_data_provider.get_historical_candles(
        symbol=symbol,
        start_ts=start_ts,
        end_ts=end_ts,
        interval="1m"
    )
    print(f"[{symbol}] ✓ 数据量: {len(test_df):,} 条K线")
    
    if len(test_df) == 0:
        print(f"[{symbol}] ✗ 数据加载失败，跳过")
        return None
    
    # 创建策略配置
    print(f"[{symbol}] 创建策略配置...")
    bp_config = create_bp_config(symbol, Decimal("10000"))
    macd_config = create_macd_config(symbol, Decimal("10000"))
    
    # 运行回测
    results = {}
    
    # PMM Bar Portion策略
    print(f"\n[{symbol}] [1/2] 运行PMM Bar Portion策略回测...")
    engine_bp = BacktestingEngineBase()
    engine_bp.backtesting_data_provider = local_backtesting_provider
    bp_result = await run_backtest(engine_bp, bp_config, start_ts, end_ts, "PMM Bar Portion", symbol)
    if bp_result:
        results['bp'] = bp_result
    
    # PMM Dynamic (MACD)策略
    print(f"\n[{symbol}] [2/2] 运行PMM Dynamic (MACD)策略回测...")
    engine_macd = BacktestingEngineBase()
    engine_macd.backtesting_data_provider = local_backtesting_provider
    macd_result = await run_backtest(engine_macd, macd_config, start_ts, end_ts, "PMM Dynamic", symbol)
    if macd_result:
        results['macd'] = macd_result
    
    return {
        'symbol': symbol,
        'start_date': start_date.strftime('%Y-%m-%d'),
        'end_date': end_date.strftime('%Y-%m-%d'),
        'data_count': len(test_df),
        'results': results
    }

def analyze_pnl_attribution(executors: List) -> Dict:
    """分析盈亏归因"""
    if not executors or len(executors) == 0:
        return {
            'total_pnl': 0,
            'long_pnl': 0,
            'short_pnl': 0,
            'by_close_type': {},
            'by_duration': {},
            'winning_trades': 0,
            'losing_trades': 0,
            'break_even_trades': 0
        }
    
    total_pnl = Decimal("0")
    long_pnl = Decimal("0")
    short_pnl = Decimal("0")
    by_close_type = {}
    by_duration = {}
    winning_trades = 0
    losing_trades = 0
    break_even_trades = 0
    
    for executor in executors:
        if not hasattr(executor, 'net_pnl_quote'):
            continue
        
        pnl = Decimal(str(executor.net_pnl_quote)) if executor.net_pnl_quote else Decimal("0")
        total_pnl += pnl
        
        # 按方向分类
        if hasattr(executor, 'side') and executor.side:
            if 'BUY' in str(executor.side).upper():
                long_pnl += pnl
            elif 'SELL' in str(executor.side).upper():
                short_pnl += pnl
        
        # 按关闭类型分类
        if hasattr(executor, 'close_type') and executor.close_type:
            close_type = str(executor.close_type)
            if close_type not in by_close_type:
                by_close_type[close_type] = Decimal("0")
            by_close_type[close_type] += pnl
        
        # 按持续时间分类
        if hasattr(executor, 'timestamp') and hasattr(executor, 'close_timestamp'):
            try:
                duration = executor.close_timestamp - executor.timestamp if executor.close_timestamp else 0
                duration_minutes = duration // 60 if duration > 0 else 0
                duration_bucket = f"{duration_minutes // 10 * 10}-{(duration_minutes // 10 + 1) * 10}分钟"
                if duration_bucket not in by_duration:
                    by_duration[duration_bucket] = Decimal("0")
                by_duration[duration_bucket] += pnl
            except:
                pass
        
        # 统计盈亏
        if pnl > 0:
            winning_trades += 1
        elif pnl < 0:
            losing_trades += 1
        else:
            break_even_trades += 1
    
    return {
        'total_pnl': float(total_pnl),
        'long_pnl': float(long_pnl),
        'short_pnl': float(short_pnl),
        'by_close_type': {k: float(v) for k, v in by_close_type.items()},
        'by_duration': {k: float(v) for k, v in by_duration.items()},
        'winning_trades': winning_trades,
        'losing_trades': losing_trades,
        'break_even_trades': break_even_trades
    }

def analyze_parameter_reasonableness(results: Dict, symbol: str) -> Dict:
    """分析参数合理性"""
    analysis = {
        'symbol': symbol,
        'issues': [],
        'recommendations': []
    }
    
    # 检查成交率
    for strategy_name in ['bp', 'macd']:
        if strategy_name not in results:
            continue
        
        executors = results[strategy_name].get('executors', [])
        if not executors:
            continue
        
        total_executors = len(executors)
        filled_executors = sum(1 for e in executors if hasattr(e, 'filled_amount_quote') and e.filled_amount_quote and float(e.filled_amount_quote) > 0)
        fill_rate = filled_executors / total_executors if total_executors > 0 else 0
        
        if fill_rate < 0.01:
            analysis['issues'].append(f"{strategy_name.upper()}策略成交率极低 ({fill_rate*100:.2f}%)，可能价差设置过宽")
            analysis['recommendations'].append(f"考虑缩小价差范围，或调整reference_price计算逻辑")
        
        # 检查盈亏分布
        pnl_attribution = analyze_pnl_attribution(executors)
        if pnl_attribution['total_pnl'] == 0 and filled_executors > 0:
            analysis['issues'].append(f"{strategy_name.upper()}策略有成交但无盈亏，可能止盈止损设置不合理")
            analysis['recommendations'].append(f"检查止盈({0.5}%)和止损({1}%)设置，考虑调整以覆盖交易费用")
        
        # 检查关闭类型分布
        close_types = pnl_attribution['by_close_type']
        if 'EARLY_STOP' in close_types and close_types.get('EARLY_STOP', 0) < 0:
            early_stop_count = sum(1 for e in executors if hasattr(e, 'close_type') and str(e.close_type) == 'EARLY_STOP')
            if early_stop_count > total_executors * 0.9:
                analysis['issues'].append(f"{strategy_name.upper()}策略90%以上订单未成交被提前停止")
                analysis['recommendations'].append(f"检查挂单价格计算，确保订单价格能被市场价格触及")
    
    return analysis

def generate_comparison_report(all_results: List[Dict]) -> str:
    """生成对比分析报告"""
    report = []
    report.append("="*80)
    report.append("最近1个月回测对比分析报告 - BTC、SOL、ETH")
    report.append("="*80)
    report.append("")
    
    # 汇总表格
    report.append("【1. 回测结果汇总】")
    report.append("-"*80)
    report.append(f"{'品种':<10} {'策略':<20} {'总Executor':<12} {'成交Executor':<12} {'成交率':<10} {'总盈亏($)':<12} {'总盈亏(%)':<12}")
    report.append("-"*80)
    
    summary_data = []
    for result in all_results:
        if not result or 'results' not in result:
            continue
        
        symbol = result['symbol']
        for strategy_name in ['bp', 'macd']:
            if strategy_name not in result['results']:
                continue
            
            executors = result['results'][strategy_name].get('executors', [])
            total_executors = len(executors)
            filled_executors = sum(1 for e in executors if hasattr(e, 'filled_amount_quote') and e.filled_amount_quote and float(e.filled_amount_quote) > 0)
            fill_rate = filled_executors / total_executors if total_executors > 0 else 0
            
            total_pnl = sum(float(e.net_pnl_quote) if hasattr(e, 'net_pnl_quote') and e.net_pnl_quote else 0 for e in executors)
            total_pnl_pct = (total_pnl / 10000) * 100 if total_pnl != 0 else 0
            
            strategy_display = "PMM Bar Portion" if strategy_name == 'bp' else "PMM Dynamic"
            report.append(f"{symbol:<10} {strategy_display:<20} {total_executors:<12} {filled_executors:<12} {fill_rate*100:<9.2f}% {total_pnl:<12.2f} {total_pnl_pct:<11.2f}%")
            
            summary_data.append({
                'symbol': symbol,
                'strategy': strategy_display,
                'total_executors': total_executors,
                'filled_executors': filled_executors,
                'fill_rate': fill_rate,
                'total_pnl': total_pnl,
                'total_pnl_pct': total_pnl_pct
            })
    
    report.append("")
    
    # 盈亏归因分析
    report.append("【2. 盈亏归因分析】")
    report.append("-"*80)
    
    for result in all_results:
        if not result or 'results' not in result:
            continue
        
        symbol = result['symbol']
        report.append(f"\n{symbol}:")
        
        for strategy_name in ['bp', 'macd']:
            if strategy_name not in result['results']:
                continue
            
            executors = result['results'][strategy_name].get('executors', [])
            pnl_attr = analyze_pnl_attribution(executors)
            
            strategy_display = "PMM Bar Portion" if strategy_name == 'bp' else "PMM Dynamic"
            report.append(f"  {strategy_display}:")
            report.append(f"    总盈亏: ${pnl_attr['total_pnl']:.2f}")
            report.append(f"    多单盈亏: ${pnl_attr['long_pnl']:.2f}")
            report.append(f"    空单盈亏: ${pnl_attr['short_pnl']:.2f}")
            report.append(f"    盈利交易: {pnl_attr['winning_trades']}")
            report.append(f"    亏损交易: {pnl_attr['losing_trades']}")
            report.append(f"    持平交易: {pnl_attr['break_even_trades']}")
            
            if pnl_attr['by_close_type']:
                report.append(f"    按关闭类型分类:")
                for close_type, pnl in pnl_attr['by_close_type'].items():
                    report.append(f"      {close_type}: ${pnl:.2f}")
    
    report.append("")
    
    # 参数合理性分析
    report.append("【3. 参数合理性分析】")
    report.append("-"*80)
    
    for result in all_results:
        if not result or 'results' not in result:
            continue
        
        symbol = result['symbol']
        param_analysis = analyze_parameter_reasonableness(result['results'], symbol)
        
        report.append(f"\n{symbol}:")
        if param_analysis['issues']:
            report.append("  问题:")
            for issue in param_analysis['issues']:
                report.append(f"    - {issue}")
        else:
            report.append("  ✓ 未发现明显问题")
        
        if param_analysis['recommendations']:
            report.append("  建议:")
            for rec in param_analysis['recommendations']:
                report.append(f"    - {rec}")
    
    report.append("")
    
    # 跨品种对比
    report.append("【4. 跨品种对比】")
    report.append("-"*80)
    
    # 按品种汇总
    symbol_summary = {}
    for data in summary_data:
        symbol = data['symbol']
        if symbol not in symbol_summary:
            symbol_summary[symbol] = {'bp': {}, 'macd': {}}
        
        strategy_key = 'bp' if 'Bar Portion' in data['strategy'] else 'macd'
        symbol_summary[symbol][strategy_key] = data
    
    report.append(f"{'品种':<10} {'BP成交率':<12} {'BP盈亏':<12} {'MACD成交率':<12} {'MACD盈亏':<12}")
    report.append("-"*80)
    
    for symbol in ['BTC-USDT', 'SOL-USDT', 'ETH-USDT']:
        if symbol not in symbol_summary:
            continue
        
        bp_data = symbol_summary[symbol].get('bp', {})
        macd_data = symbol_summary[symbol].get('macd', {})
        
        bp_fill = bp_data.get('fill_rate', 0) * 100
        bp_pnl = bp_data.get('total_pnl', 0)
        macd_fill = macd_data.get('fill_rate', 0) * 100
        macd_pnl = macd_data.get('total_pnl', 0)
        
        report.append(f"{symbol:<10} {bp_fill:<11.2f}% ${bp_pnl:<10.2f} {macd_fill:<11.2f}% ${macd_pnl:<10.2f}")
    
    report.append("")
    report.append("="*80)
    
    return "\n".join(report)

async def main():
    """主函数"""
    print("="*80)
    print("最近1个月回测对比分析 - BTC、SOL、ETH")
    print("="*80)
    print()
    
    # 获取时间范围
    start_date, end_date = get_last_1_month_dates()
    print(f"时间范围: {start_date.strftime('%Y-%m-%d')} 至 {end_date.strftime('%Y-%m-%d')}")
    print(f"交易对: {', '.join(TRADING_PAIRS)}")
    print()
    
    # 运行回测
    all_results = []
    for symbol in TRADING_PAIRS:
        result = await run_symbol_backtest(symbol, start_date, end_date)
        if result:
            all_results.append(result)
    
    # 生成报告
    print("\n" + "="*80)
    print("生成分析报告...")
    print("="*80)
    
    report = generate_comparison_report(all_results)
    print(report)
    
    # 保存报告
    report_file = Path(__file__).parent / "BACKTEST_1MONTH_REPORT.md"
    report_file.write_text(report, encoding='utf-8')
    print(f"\n✓ 报告已保存至: {report_file}")
    
    # 保存详细结果（JSON）
    json_file = Path(__file__).parent / "BACKTEST_1MONTH_RESULTS.json"
    json_data = {
        'start_date': start_date.strftime('%Y-%m-%d'),
        'end_date': end_date.strftime('%Y-%m-%d'),
        'trading_pairs': TRADING_PAIRS,
        'results': []
    }
    
    for result in all_results:
        json_result = {
            'symbol': result['symbol'],
            'data_count': result['data_count'],
            'strategies': {}
        }
        
        for strategy_name in ['bp', 'macd']:
            if strategy_name not in result['results']:
                continue
            
            executors = result['results'][strategy_name].get('executors', [])
            pnl_attr = analyze_pnl_attribution(executors)
            
            json_result['strategies'][strategy_name] = {
                'total_executors': len(executors),
                'filled_executors': sum(1 for e in executors if hasattr(e, 'filled_amount_quote') and e.filled_amount_quote and float(e.filled_amount_quote) > 0),
                'pnl_attribution': pnl_attr
            }
        
        json_data['results'].append(json_result)
    
    json_file.write_text(json.dumps(json_data, indent=2, default=str), encoding='utf-8')
    print(f"✓ 详细结果已保存至: {json_file}")

if __name__ == "__main__":
    asyncio.run(main())

