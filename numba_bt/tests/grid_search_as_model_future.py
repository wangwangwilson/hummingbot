"""AS_MODEL未来数据策略参数网格搜索"""
import sys
import os
from pathlib import Path
from datetime import datetime, timezone
import numpy as np
import glob
import zipfile
import duckdb
import tempfile
import importlib.util
from itertools import product
from joblib import Parallel, delayed
from tqdm import tqdm
import json
import matplotlib.pyplot as plt
import seaborn as sns

# 设置路径
project_root = Path(__file__).parent.parent.absolute()
os.chdir(project_root)
sys.path.insert(0, str(project_root))
sys.path.insert(0, '/home/wilson/bigdata_plan')

# 导入策略
strategy_path = project_root / "src" / "strategies" / "as_model_future_strategy.py"
spec = importlib.util.spec_from_file_location("as_model_future_strategy", strategy_path)
strategy_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(strategy_module)
ASModelFutureStrategy = strategy_module.ASModelFutureStrategy

# 导入其他模块
preparer_path = project_root / "src" / "data" / "preparer.py"
spec = importlib.util.spec_from_file_location("preparer", preparer_path)
preparer_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preparer_module)
DataPreparer = preparer_module.DataPreparer

statistics_path = project_root / "src" / "analysis" / "statistics.py"
spec = importlib.util.spec_from_file_location("statistics", statistics_path)
statistics_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(statistics_module)
analyze_performance = statistics_module.analyze_performance

core_path = project_root / "src" / "core" / "backtest_as_model_future.py"
spec = importlib.util.spec_from_file_location("backtest_as_model_future", core_path)
core_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(core_module)
_calculate_future_30s_returns = core_module._calculate_future_30s_returns
_run_backtest_as_model_future_numba = core_module._run_backtest_as_model_future_numba
_run_backtest_as_model_future_numba = core_module._run_backtest_as_model_future_numba


def load_data(symbol, start_date, end_date):
    """加载数据（只执行一次，然后分发给多进程）"""
    print(f"正在加载数据...")
    
    # 读取aggtrade数据
    binance_data_dir = "/mnt/hdd/binance-public-data"
    data_path = f"{binance_data_dir}/data/futures/um/daily/aggTrades/{symbol}"
    
    conn = duckdb.connect()
    zip_files = sorted(glob.glob(f"{data_path}/*.zip"))
    
    if not zip_files:
        raise ValueError(f"未找到数据文件: {data_path}")
    
    start_ts = int(start_date.timestamp() * 1000)
    end_ts = int(end_date.timestamp() * 1000)
    
    data_list = []
    for zip_file in zip_files:
        try:
            with zipfile.ZipFile(zip_file, 'r') as zf:
                csv_files = [f for f in zf.namelist() if f.endswith('.csv')]
                if not csv_files:
                    continue
                
                with zf.open(csv_files[0]) as f:
                    csv_content = f.read().decode('utf-8')
                    
                    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as tmp:
                        tmp.write(csv_content)
                        tmp_path = tmp.name
                    
                    try:
                        query = f"""
                        SELECT 
                            CAST(transact_time AS BIGINT) as timestamp,
                            CASE WHEN is_buyer_maker = 'true' THEN -1 ELSE 1 END as order_side,
                            CAST(price AS DOUBLE) as trade_price,
                            CAST(quantity AS DOUBLE) as trade_quantity,
                            1 as mm
                        FROM read_csv_auto('{tmp_path}', header=true)
                        WHERE CAST(transact_time AS BIGINT) >= {start_ts} 
                          AND CAST(transact_time AS BIGINT) <= {end_ts}
                        """
                        df = conn.execute(query).df()
                        if not df.empty:
                            data_list.append(df.values)
                    finally:
                        if os.path.exists(tmp_path):
                            os.unlink(tmp_path)
        except Exception as e:
            print(f"  ⚠️  读取文件失败 {Path(zip_file).name}: {e}")
            continue
    
    if not data_list:
        raise ValueError("未找到数据")
    
    binance_data = np.vstack(data_list)
    binance_data = binance_data[np.argsort(binance_data[:, 0])]
    
    # 模拟Blofin trades（20%的数据）
    np.random.seed(42)
    blofin_indices = np.random.choice(len(binance_data), size=int(len(binance_data) * 0.2), replace=False)
    blofin_data = binance_data[blofin_indices].copy()
    blofin_data[:, 4] = 0
    
    remaining_indices = np.setdiff1d(np.arange(len(binance_data)), blofin_indices)
    binance_market_data = binance_data[remaining_indices].copy()
    binance_market_data[:, 4] = 1
    
    # 合并数据
    all_data = np.vstack([blofin_data, binance_market_data])
    merged_data = all_data[np.argsort(all_data[:, 0])]
    
    conn.close()
    
    # 读取资金费率数据
    preparer = DataPreparer()
    funding_data = preparer.prepare_funding_rate(
        symbol=symbol,
        start_date=start_date,
        end_date=end_date
    )
    
    # 预先计算未来30秒return
    print(f"正在计算未来30秒return...")
    future_30s_returns = _calculate_future_30s_returns(merged_data)
    print(f"✅ 数据加载完成")
    
    return merged_data, funding_data, future_30s_returns


def run_single_backtest(params, data_tuple):
    """运行单个回测（用于多进程，直接调用核心函数避免重复计算）"""
    merged_data, funding_data, future_30s_returns = data_tuple
    
    try:
        # 直接调用核心函数，避免通过策略类（减少开销和重复计算future_30s_returns）
        # 准备参数
        base_exposure = params["base_exposure"]
        base_target_pct = params["base_target_pct"]
        mini_price_step = 0.0001
        taker_fee_rate = 0.00015
        maker_fee_rate = -0.00005
        open_ratio = 0.5
        initial_cash = 10000.0
        initial_pos = 0.0
        
        # 准备资金费率数据
        if len(funding_data) > 0:
            funding_rate_data = funding_data
        else:
            funding_rate_data = np.empty((0, 2), dtype=np.float64)
        
        # 预分配结果数组
        accounts_log = np.zeros((len(merged_data) * 2, 10), dtype=np.float64)
        place_orders_stats_log = np.zeros((len(merged_data), 13), dtype=np.float64)
        
        # 执行回测（直接调用核心函数，使用预计算的future_30s_returns）
        accounts_count, stats_count = _run_backtest_as_model_future_numba(
            merged_data,
            future_30s_returns,  # 使用预计算的结果，避免重复计算
            base_exposure,
            base_target_pct,
            mini_price_step,
            taker_fee_rate,
            maker_fee_rate,
            open_ratio,
            params["as_model_buy_distance"],
            params["as_model_sell_distance"],
            params["order_size_pct_min"],
            params["order_size_pct_max"],
            initial_cash,
            initial_pos,
            accounts_log,
            place_orders_stats_log,
            funding_rate_data
        )
        
        # 分析结果
        performance = analyze_performance(
            accounts_raw=accounts_log[:accounts_count],
            place_orders_stats_raw=place_orders_stats_log[:stats_count]
        )
        
        # 提取关键指标
        overall = performance.get('overall_performance', {})
        maker = performance.get('maker_performance', {})
        taker = performance.get('taker_performance', {})
        
        result = {
            "params": params,
            "total_pnl_no_fees": overall.get('total_pnl_no_fees', 0.0),
            "total_pnl_with_fees": overall.get('total_pnl_with_fees', 0.0),
            "realized_pnl_no_fees": overall.get('realized_pnl_no_fees', 0.0),
            "unrealized_pnl_no_fees": overall.get('unrealized_pnl_no_fees', 0.0),
            "max_drawdown": overall.get('max_drawdown', 0.0),
            "sharpe_ratio": overall.get('sharpe_ratio', 0.0),
            "maker_pnl": maker.get('total_maker_pnl_no_fees', 0.0),
            "taker_pnl": taker.get('total_taker_pnl_no_fees', 0.0),
            "maker_volume": maker.get('maker_volume_total', 0.0),
            "taker_volume": taker.get('taker_volume_total', 0.0),
        }
        
        return result
        
    except Exception as e:
        print(f"❌ 参数组合失败: {params}, 错误: {e}")
        return {
            "params": params,
            "total_pnl_no_fees": float('-inf'),
            "error": str(e)
        }


def generate_parameter_grid():
    """生成参数网格（约500个组合）"""
    # 关键参数及其范围（根据重要性调整）
    param_grid = {
        # 挂单量控制（最重要，影响最大）
        "order_size_pct_min": [0.03, 0.04, 0.05, 0.06, 0.07, 0.08],  # 6个
        "order_size_pct_max": [0.08, 0.09, 0.10, 0.11, 0.12, 0.13],  # 6个
        
        # AS_MODEL距离参数（重要）
        "as_model_buy_distance": [0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3],  # 7个
        "as_model_sell_distance": [0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3],  # 7个
        
        # Exposure和target_pct（中等重要）
        "base_exposure": [8000, 10000, 12000, 15000],  # 4个
        "base_target_pct": [0.3, 0.4, 0.5, 0.6, 0.7],  # 5个
    }
    
    # 生成所有组合
    param_names = list(param_grid.keys())
    param_values = list(param_grid.values())
    
    all_combinations = list(product(*param_values))
    
    # 过滤不合理的组合（order_size_pct_min < order_size_pct_max）
    valid_combinations = []
    for combo in all_combinations:
        params_dict = dict(zip(param_names, combo))
        if params_dict["order_size_pct_min"] < params_dict["order_size_pct_max"]:
            valid_combinations.append(params_dict)
    
    # 如果组合数太多，随机采样到约500个
    if len(valid_combinations) > 600:
        np.random.seed(42)
        indices = np.random.choice(len(valid_combinations), size=500, replace=False)
        valid_combinations = [valid_combinations[i] for i in indices]
    
    print(f"生成了 {len(valid_combinations)} 个有效参数组合")
    print(f"理论组合数: {len(all_combinations)}")
    print(f"过滤后: {len(valid_combinations)}")
    
    return valid_combinations


def plot_parameter_analysis(results, output_dir):
    """绘制参数分析图表"""
    if not results:
        print("⚠️  没有结果可分析")
        return
    
    # 提取数据
    param_names = ["order_size_pct_min", "order_size_pct_max", "as_model_buy_distance", 
                   "as_model_sell_distance", "base_exposure", "base_target_pct"]
    
    # 创建图表
    fig, axes = plt.subplots(2, 3, figsize=(18, 12))
    axes = axes.flatten()
    
    for idx, param_name in enumerate(param_names):
        ax = axes[idx]
        
        # 按参数分组，计算平均收益
        param_values = []
        avg_pnls = []
        std_pnls = []
        
        # 获取该参数的所有唯一值
        unique_values = sorted(set([r["params"][param_name] for r in results if "error" not in r]))
        
        for val in unique_values:
            # 筛选该参数值的所有结果
            filtered_results = [r for r in results if r["params"][param_name] == val and "error" not in r]
            
            if filtered_results:
                pnls = [r["total_pnl_no_fees"] for r in filtered_results]
                param_values.append(val)
                avg_pnls.append(np.mean(pnls))
                std_pnls.append(np.std(pnls))
        
        if param_values:
            # 绘制柱状图
            bars = ax.bar(range(len(param_values)), avg_pnls, yerr=std_pnls, 
                         capsize=5, alpha=0.7, color='steelblue', edgecolor='black')
            
            # 设置x轴标签
            ax.set_xticks(range(len(param_values)))
            ax.set_xticklabels([f"{v:.3f}" if isinstance(v, float) else f"{v}" for v in param_values], 
                             rotation=45, ha='right')
            
            # 添加数值标签
            for i, (bar, avg) in enumerate(zip(bars, avg_pnls)):
                height = bar.get_height()
                ax.text(bar.get_x() + bar.get_width()/2., height,
                       f'{avg:.0f}',
                       ha='center', va='bottom', fontsize=9)
            
            ax.set_xlabel(param_name, fontsize=11, fontweight='bold')
            ax.set_ylabel('Average PnL (no fees)', fontsize=10)
            ax.set_title(f'{param_name} vs PnL', fontsize=12, fontweight='bold')
            ax.grid(True, alpha=0.3, axis='y')
            ax.axhline(y=0, color='red', linestyle='--', alpha=0.5)
    
    plt.tight_layout()
    plt.savefig(output_dir / "parameter_analysis.png", dpi=300, bbox_inches='tight')
    print(f"✅ 参数分析图表已保存: {output_dir / 'parameter_analysis.png'}")
    plt.close()
    
    # 保存详细结果
    results_file = output_dir / "grid_search_results.json"
    with open(results_file, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print(f"✅ 详细结果已保存: {results_file}")


def main():
    """主函数"""
    print("=" * 70)
    print("AS_MODEL未来数据策略参数网格搜索")
    print("=" * 70)
    
    # 配置
    symbol = "AXSUSDT"
    start_date = datetime(2025, 9, 1, tzinfo=timezone.utc)
    end_date = datetime(2025, 10, 1, tzinfo=timezone.utc)
    n_jobs = -1  # 使用所有CPU核心
    
    print(f"\n配置:")
    print(f"  交易对: {symbol}")
    print(f"  时间范围: {start_date.strftime('%Y-%m-%d')} 到 {end_date.strftime('%Y-%m-%d')}")
    print(f"  并行进程数: {n_jobs if n_jobs > 0 else 'auto'}")
    
    # 1. 加载数据（只执行一次）
    print(f"\n步骤1: 加载数据")
    merged_data, funding_data, future_30s_returns = load_data(symbol, start_date, end_date)
    data_tuple = (merged_data, funding_data, future_30s_returns)
    
    # 2. 生成参数网格
    print(f"\n步骤2: 生成参数网格")
    param_combinations = generate_parameter_grid()
    
    # 3. 并行执行回测
    print(f"\n步骤3: 并行执行回测（{len(param_combinations)} 个组合）")
    print(f"  使用 {n_jobs if n_jobs > 0 else 'auto'} 个进程")
    
    # 使用joblib并行执行，带tqdm进度条
    # 注意：tqdm需要配合joblib使用，使用tqdm_joblib或者手动更新
    from tqdm import tqdm
    
    # 使用joblib并行执行，带tqdm进度条
    print("  开始执行...")
    
    # 使用joblib并行执行，手动更新tqdm
    # 由于joblib的并行特性，tqdm更新可能不够实时，但可以显示总体进度
    results = []
    
    # 分批处理以便更新进度条
    batch_size = max(1, len(param_combinations) // 100)  # 每批约1%
    with tqdm(total=len(param_combinations), desc="网格搜索进度", ncols=100) as pbar:
        for i in range(0, len(param_combinations), batch_size):
            batch = param_combinations[i:i+batch_size]
            batch_results = Parallel(n_jobs=n_jobs, verbose=0)(
                delayed(run_single_backtest)(params, data_tuple)
                for params in batch
            )
            results.extend(batch_results)
            pbar.update(len(batch))
    
    # 4. 分析结果
    print(f"\n步骤4: 分析结果")
    valid_results = [r for r in results if "error" not in r]
    print(f"  成功: {len(valid_results)} / {len(results)}")
    
    if valid_results:
        pnls = [r["total_pnl_no_fees"] for r in valid_results]
        print(f"  平均PnL: {np.mean(pnls):.2f}")
        print(f"  最大PnL: {np.max(pnls):.2f}")
        print(f"  最小PnL: {np.min(pnls):.2f}")
        print(f"  最佳参数组合:")
        best_result = max(valid_results, key=lambda x: x["total_pnl_no_fees"])
        for key, value in best_result["params"].items():
            print(f"    {key}: {value}")
        print(f"  PnL: {best_result['total_pnl_no_fees']:.2f}")
    
    # 5. 保存结果和图表
    print(f"\n步骤5: 保存结果")
    output_dir = project_root / "results" / "test" / datetime.now().strftime("%Y_%m_%d") / datetime.now().strftime("%H_%M")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    plot_parameter_analysis(results, output_dir)
    
    print(f"\n" + "=" * 70)
    print("✅ 网格搜索完成！")
    print("=" * 70)


if __name__ == "__main__":
    main()

