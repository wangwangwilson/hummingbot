#!/usr/bin/env python3
"""
参数优化程序 - 基于Optuna的参数优化
用于优化PMM策略的关键参数
支持增量保存结果，中途停止后可查看已完成的结果
"""

import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Optional
import json
import optuna
from optuna.samplers import TPESampler
import multiprocessing
from joblib import Parallel, delayed
import itertools

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# 导入必要的模块
from backtest_comparison_local import LocalBinanceDataProvider, LocalBacktestingDataProvider
from hummingbot.strategy_v2.backtesting.backtesting_engine_base import BacktestingEngineBase
from hummingbot.data_feed.candles_feed.data_types import CandlesConfig
from controllers.market_making.pmm_bar_portion import PMMBarPortionControllerConfig
from hummingbot.strategy_v2.executors.position_executor.data_types import OrderType

# 配置参数
TRADING_PAIR = "DOGE-USDT"
# 使用有数据的日期范围（2024年11月）
START_DATE = datetime(2024, 11, 20)
END_DATE = datetime(2024, 11, 30)
INITIAL_PORTFOLIO_USD = 10000
MAKER_FEE = 0.0
TAKER_FEE = 0.0002
BACKTEST_RESOLUTION = "1m"
N_TRIALS = 90  # Optuna试验次数，不超过90个
N_JOBS = multiprocessing.cpu_count()  # 使用所有CPU核心（明确指定数量）
RESULTS_FILE = Path(__file__).parent / "optimization_results_incremental.json"
STUDY_DB_FILE = Path(__file__).parent / "optuna_study.db"  # SQLite数据库用于多进程


def calculate_sharpe_ratio(pnls: List[float]) -> float:
    """计算夏普比率"""
    if len(pnls) < 2:
        return 0.0
    import numpy as np
    mean_pnl = np.mean(pnls)
    std_pnl = np.std(pnls)
    if std_pnl == 0:
        return 0.0
    return mean_pnl / std_pnl * np.sqrt(len(pnls))


def run_single_backtest(params: Dict, start_ts: int, end_ts: int) -> Dict:
    """运行单个回测"""
    try:
        local_data_provider = LocalBinanceDataProvider()
        local_backtesting_provider = LocalBacktestingDataProvider(local_data_provider)
        local_backtesting_provider.update_backtesting_time(start_ts, end_ts)
        
        config = PMMBarPortionControllerConfig(**params)
        
        candles_config = CandlesConfig(
            connector="binance_perpetual",
            trading_pair=TRADING_PAIR,
            interval=BACKTEST_RESOLUTION,
            max_records=100000
        )
        import asyncio
        asyncio.run(local_backtesting_provider.initialize_candles_feed([candles_config]))
        
        engine = BacktestingEngineBase()
        engine.backtesting_data_provider = local_backtesting_provider
        
        result = asyncio.run(engine.run_backtesting(
            controller_config=config,
            start=start_ts,
            end=end_ts,
            backtesting_resolution=BACKTEST_RESOLUTION,
            trade_cost=Decimal(str(TAKER_FEE)),
            show_progress=False
        ))
        
        if result and 'executors' in result:
            executors = result['executors']
            filled_executors = [
                e for e in executors 
                if hasattr(e, 'filled_amount_quote') and e.filled_amount_quote 
                and float(e.filled_amount_quote) > 0
            ]
            
            if len(filled_executors) == 0:
                return {'success': False, 'sharpe': 0.0, 'return': 0.0, 'total_pnl': 0.0, 'filled_count': 0, 'total_count': len(executors)}
            
            pnls = [float(e.net_pnl_quote) if hasattr(e, 'net_pnl_quote') and e.net_pnl_quote else 0.0 
                   for e in filled_executors]
            total_pnl = sum(pnls)
            sharpe = calculate_sharpe_ratio(pnls)
            return_pct = (total_pnl / INITIAL_PORTFOLIO_USD) * 100
            
            return {
                'success': True,
                'sharpe': sharpe,
                'return': return_pct,
                'total_pnl': total_pnl,
                'filled_count': len(filled_executors),
                'total_count': len(executors),
            }
        else:
            return {'success': False, 'sharpe': 0.0, 'return': 0.0, 'total_pnl': 0.0, 'filled_count': 0, 'total_count': 0}
    except Exception as e:
        print(f"Error in backtest: {e}")
        import traceback
        traceback.print_exc()
        return {'success': False, 'sharpe': 0.0, 'return': 0.0, 'total_pnl': 0.0, 'filled_count': 0, 'total_count': 0, 'error': str(e)}


def load_incremental_results() -> List[Dict]:
    """加载已保存的增量结果"""
    if RESULTS_FILE.exists():
        try:
            with open(RESULTS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get('trials', [])
        except:
            return []
    return []


def save_trial_result(trial_number: int, params: Dict, result: Dict, objective_value: float):
    """保存单个trial的结果到JSON文件（增量追加，支持多进程）"""
    trial_data = {
        'trial_number': trial_number,
        'params': {k: str(v) if isinstance(v, Decimal) else v for k, v in params.items()},
        'result': result,
        'objective_value': objective_value,
        'timestamp': datetime.now().isoformat()
    }
    
    # 使用文件锁确保多进程安全
    import fcntl
    import time
    
    max_retries = 10
    retry_delay = 0.1
    
    for attempt in range(max_retries):
        try:
            # 加载现有结果
            if RESULTS_FILE.exists():
                with open(RESULTS_FILE, 'r+', encoding='utf-8') as f:
                    fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                    try:
                        f.seek(0)
                        content = f.read()
                        if content.strip():
                            data = json.loads(content)
                            trials = data.get('trials', [])
                        else:
                            trials = []
                    except:
                        trials = []
                    
                    # 更新或添加trial结果
                    existing_index = next((i for i, t in enumerate(trials) if t.get('trial_number') == trial_number), None)
                    if existing_index is not None:
                        trials[existing_index] = trial_data
                    else:
                        trials.append(trial_data)
                    
                    # 保存更新后的结果
                    data = {
                        'trading_pair': TRADING_PAIR,
                        'start_date': START_DATE.isoformat(),
                        'end_date': END_DATE.isoformat(),
                        'n_trials': N_TRIALS,
                        'total_trials_completed': len(trials),
                        'trials': trials
                    }
                    
                    f.seek(0)
                    f.truncate()
                    json.dump(data, f, indent=2, default=str)
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            else:
                # 文件不存在，创建新文件
                with open(RESULTS_FILE, 'w', encoding='utf-8') as f:
                    fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                    data = {
                        'trading_pair': TRADING_PAIR,
                        'start_date': START_DATE.isoformat(),
                        'end_date': END_DATE.isoformat(),
                        'n_trials': N_TRIALS,
                        'total_trials_completed': 1,
                        'trials': [trial_data]
                    }
                    json.dump(data, f, indent=2, default=str)
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            
            # 成功保存，退出重试循环
            break
        except (IOError, OSError) as e:
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
                retry_delay *= 2  # 指数退避
            else:
                print(f"  ⚠ Failed to save trial {trial_number} after {max_retries} attempts: {e}")
    
    # 不在多进程环境下打印（避免输出混乱）
    # print(f"  ✓ Trial {trial_number} saved to {RESULTS_FILE}")


def objective_wrapper(trial_num: int, params_dict: Dict, start_ts: int, end_ts: int):
    """包装函数用于joblib多进程（不依赖Optuna Trial对象）"""
    import os
    pid = os.getpid()
    
    # 构建完整参数
    params = {
        "controller_name": "pmm_bar_portion",
        "connector_name": "binance_perpetual",
        "trading_pair": TRADING_PAIR,
        "total_amount_quote": Decimal(str(INITIAL_PORTFOLIO_USD)),
        "buy_spreads": [params_dict['buy_spread_base'], params_dict['buy_spread_base'] + params_dict['buy_spread_step']],
        "sell_spreads": [params_dict['sell_spread_base'], params_dict['sell_spread_base'] + params_dict['sell_spread_step']],
        "stop_loss": Decimal(str(params_dict['stop_loss'])),
        "take_profit": Decimal(str(params_dict['take_profit'])),
        "time_limit": params_dict['time_limit'],
        "candles_connector": "binance_perpetual",
        "candles_trading_pair": TRADING_PAIR,
        "interval": BACKTEST_RESOLUTION,
        "natr_length": params_dict['natr_length'],
        "atr_length": params_dict['atr_length'],
        "training_window": params_dict['training_window'],
        "take_profit_order_type": OrderType.MARKET,
        "buy_amounts_pct": [Decimal("0.5"), Decimal("0.5")],
        "sell_amounts_pct": [Decimal("0.5"), Decimal("0.5")],
        "executor_refresh_time": 300,
    }
    
    print(f"\n[Trial {trial_num} (PID {pid})] Testing parameters...")
    result = run_single_backtest(params, start_ts, end_ts)
    
    if result.get('success', False):
        objective_value = result['sharpe']  # 使用Sharpe比率作为优化目标
        print(f"  [Trial {trial_num} (PID {pid})] Sharpe: {objective_value:.4f}, Return: {result['return']:.2f}%, PnL: ${result['total_pnl']:.2f}")
    else:
        objective_value = float('-inf')
        print(f"  [Trial {trial_num} (PID {pid})] Failed: {result.get('error', 'Unknown error')}")
    
    # 保存trial结果（save_trial_result内部已处理文件锁）
    save_trial_result(trial_num, params, result, objective_value)
    
    return (trial_num, objective_value, {'params': params_dict, 'result': result})


def run_trial_wrapper(trial_num, params_dict, start_ts, end_ts):
    """包装函数用于多进程（模块级别，可被pickle）"""
    return objective_wrapper(trial_num, params_dict, start_ts, end_ts)


def main():
    """主函数"""
    print("="*80)
    print("Parameter Optimization using Optuna")
    print("="*80)
    print(f"Trading Pair: {TRADING_PAIR}")
    print(f"Time Range: {START_DATE.strftime('%Y-%m-%d')} to {END_DATE.strftime('%Y-%m-%d')}")
    print(f"Initial Portfolio: ${INITIAL_PORTFOLIO_USD:,.2f}")
    print(f"Number of Trials: {N_TRIALS}")
    print(f"Results File: {RESULTS_FILE}")
    print()
    
    # 加载已有结果（用于显示，但不影响新优化）
    existing_trials = load_incremental_results()
    if existing_trials:
        successful_existing = [t for t in existing_trials if t.get('result', {}).get('success', False)]
        print(f"Found {len(existing_trials)} existing trial results ({len(successful_existing)} successful)")
        if successful_existing:
            best_existing = max(successful_existing, key=lambda x: x.get('result', {}).get('sharpe', -999))
            print(f"  Best existing: Sharpe={best_existing.get('result', {}).get('sharpe', 0):.4f}")
        print("  (Starting new optimization, results will be appended)")
        print()
    
    # 使用joblib实现真正的多进程（因为Optuna的SQLite多进程有限制）
    # 先生成所有参数组合，然后并行运行
    print(f"Multiprocessing: {N_JOBS} jobs (using {N_JOBS} CPU cores)")
    print(f"Using joblib for true multiprocessing")
    
    # 创建Optuna study用于参数采样
    study = optuna.create_study(
        direction='maximize',
        sampler=TPESampler(seed=42)
    )
    
    # 生成所有trial的参数（使用Optuna的采样器）
    print(f"Generating {N_TRIALS} parameter combinations...")
    trial_params_list = []
    for i in range(N_TRIALS):
        trial = study.ask()  # 获取新的trial
        # 提取参数
        params_dict = {
            'buy_spread_base': trial.suggest_float('buy_spread_base', 0.01, 0.02, step=0.01),
            'sell_spread_base': trial.suggest_float('sell_spread_base', 0.01, 0.02, step=0.01),
            'buy_spread_step': trial.suggest_float('buy_spread_step', 0.01, 0.02, step=0.01),
            'sell_spread_step': trial.suggest_float('sell_spread_step', 0.01, 0.02, step=0.01),
            'stop_loss': trial.suggest_float('stop_loss', 0.015, 0.03, step=0.005),
            'take_profit': trial.suggest_float('take_profit', 0.01, 0.02, step=0.005),
            'time_limit': trial.suggest_int('time_limit', 1800, 5400, step=900),
            'natr_length': trial.suggest_int('natr_length', 14, 20, step=6),
            'atr_length': trial.suggest_int('atr_length', 10, 12, step=2),
            'training_window': trial.suggest_int('training_window', 60, 90, step=30),
        }
        trial_params_list.append((i, params_dict))
    
    print(f"Running {N_TRIALS} trials in parallel using {N_JOBS} processes...")
    
    start_ts = int(START_DATE.timestamp())
    end_ts = int(END_DATE.timestamp())
    
    try:
        # 使用joblib并行运行（使用模块级别的函数，可被pickle）
        results = Parallel(n_jobs=N_JOBS, backend='multiprocessing', verbose=10)(
            delayed(run_trial_wrapper)(trial_num, params_dict, start_ts, end_ts) 
            for trial_num, params_dict in trial_params_list
        )
        
        # 处理结果
        best_score = float('-inf')
        best_trial_num = None
        best_result_data = None
        for trial_num, score, result_data in results:
            if score > best_score:
                best_score = score
                best_trial_num = trial_num
                best_result_data = result_data
        
        print(f"\n{'='*80}")
        print("Optimization Complete")
        print(f"{'='*80}")
        
        if best_trial_num is not None:
            print(f"\nBest Trial: {best_trial_num}")
            print(f"Best Objective Value (Sharpe): {best_score:.4f}")
            print(f"\nBest Parameters:")
            for key, value in best_result_data['params'].items():
                print(f"  {key}: {value}")
            
            result = best_result_data['result']
            print(f"\nBest Results:")
            print(f"  Sharpe Ratio: {result.get('sharpe', 'N/A'):.4f}")
            print(f"  Return %: {result.get('return', 'N/A'):.2f}%")
            print(f"  Total PnL: ${result.get('total_pnl', 'N/A'):.2f}")
            print(f"  Filled Executors: {result.get('filled_count', 'N/A')}/{result.get('total_count', 'N/A')}")
        
    except KeyboardInterrupt:
        print("\n优化被用户中断，已保存的结果可在JSON文件中查看")
    
    # 从保存的结果中获取最终统计
    all_trials = load_incremental_results()
    successful = [t for t in all_trials if t.get('result', {}).get('success', False)]
    if successful:
        best_saved = max(successful, key=lambda x: x.get('result', {}).get('sharpe', -999))
        print(f"\n所有trial结果已保存到: {RESULTS_FILE}")
        print(f"共完成 {len(all_trials)} 个trials ({len(successful)} 成功)")
        print(f"最佳trial (从保存结果): {best_saved.get('trial_number')}, Sharpe: {best_saved.get('result', {}).get('sharpe', 0):.4f}")


if __name__ == "__main__":
    main()
