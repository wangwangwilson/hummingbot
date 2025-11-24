"""优化版本的动量做市策略完整测试"""
import sys
import os
from pathlib import Path
from datetime import datetime, timezone
import numpy as np
import glob
import zipfile
import duckdb
import tempfile
import pandas as pd
import importlib.util

# 设置路径
project_root = Path(__file__).parent.parent.absolute()
os.chdir(project_root)
sys.path.insert(0, str(project_root))
sys.path.insert(0, '/home/wilson/bigdata_plan')

# 导入工具函数
return_stats_path = project_root / "src" / "utils" / "return_statistics.py"
spec = importlib.util.spec_from_file_location("return_statistics", return_stats_path)
return_stats_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(return_stats_module)
calculate_return_statistics = return_stats_module.calculate_return_statistics
calculate_spread_statistics = return_stats_module.calculate_spread_statistics

# 导入优化策略
strategy_path = project_root / "src" / "strategies" / "momentum_mm_optimized_strategy.py"
spec = importlib.util.spec_from_file_location("momentum_mm_optimized_strategy", strategy_path)
strategy_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(strategy_module)
MomentumMMOptimizedStrategy = strategy_module.MomentumMMOptimizedStrategy

# 导入其他模块
preparer_path = project_root / "src" / "data" / "preparer.py"
spec = importlib.util.spec_from_file_location("preparer", preparer_path)
preparer_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preparer_module)
DataPreparer = preparer_module.DataPreparer

path_manager_path = project_root / "src" / "utils" / "path_manager.py"
spec = importlib.util.spec_from_file_location("path_manager", path_manager_path)
path_manager_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(path_manager_module)
create_result_directory = path_manager_module.create_result_directory

visualization_path = project_root / "src" / "analysis" / "visualization.py"
spec = importlib.util.spec_from_file_location("visualization", visualization_path)
visualization_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(visualization_module)
plot_comprehensive_analysis = visualization_module.plot_comprehensive_analysis

statistics_path = project_root / "src" / "analysis" / "statistics.py"
spec = importlib.util.spec_from_file_location("statistics", statistics_path)
statistics_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(statistics_module)
analyze_performance = statistics_module.analyze_performance

# 导入策略指标提取模块
strategy_metrics_path = project_root / "src" / "utils" / "strategy_metrics.py"
spec = importlib.util.spec_from_file_location("strategy_metrics", strategy_metrics_path)
strategy_metrics_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(strategy_metrics_module)
extract_strategy_metrics = strategy_metrics_module.extract_strategy_metrics


def test_momentum_mm_optimized():
    """优化版本的动量做市策略完整测试"""
    print("=" * 70)
    print("优化版本的动量做市策略完整测试")
    print("=" * 70)
    
    # 1. 配置参数
    symbol = "AXSUSDT"
    start_date = datetime(2025, 9, 1, tzinfo=timezone.utc)
    end_date = datetime(2025, 10, 1, tzinfo=timezone.utc)
    
    print(f"\n步骤1: 配置参数")
    print(f"  交易对: {symbol}")
    print(f"  时间范围: {start_date.strftime('%Y-%m-%d')} 到 {end_date.strftime('%Y-%m-%d')}")
    
    # 2. 读取aggtrade数据
    print(f"\n步骤2: 读取aggtrade数据")
    binance_data_dir = "/mnt/hdd/binance-public-data"
    data_path = f"{binance_data_dir}/data/futures/um/daily/aggTrades/{symbol}"
    
    try:
        conn = duckdb.connect()
        zip_files = sorted(glob.glob(f"{data_path}/*.zip"))
        
        if not zip_files:
            print(f"  ❌ 未找到数据文件: {data_path}")
            return
        
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
            print(f"  ❌ 未找到数据")
            return
        
        binance_data = np.vstack(data_list)
        binance_data = binance_data[np.argsort(binance_data[:, 0])]
        
        print(f"  ✅ Binance数据: {len(binance_data)} 条记录")
        if len(binance_data) > 0:
            start_ts_data = int(binance_data[0, 0])
            end_ts_data = int(binance_data[-1, 0])
            start_dt_data = datetime.fromtimestamp(start_ts_data / 1000, tz=timezone.utc)
            end_dt_data = datetime.fromtimestamp(end_ts_data / 1000, tz=timezone.utc)
            print(f"    时间范围: {start_dt_data.strftime('%Y-%m-%d %H:%M:%S')} 到 {end_dt_data.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"    数据shape: {binance_data.shape}")
        
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
        print(f"  ✅ 合并后数据: {len(merged_data)} 条记录")
        print(f"    - Blofin trades (mm_flag=0): {len(blofin_data)} 条")
        print(f"    - Binance market data (mm_flag=1): {len(binance_market_data)} 条")
        
        conn.close()
        
    except Exception as e:
        print(f"  ❌ 读取aggtrade数据失败: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # 3. 统计30s return和spread分布
    print(f"\n步骤3: 统计30s return和spread分布")
    return_stats = calculate_return_statistics(merged_data)
    spread_stats = calculate_spread_statistics(merged_data)
    
    print(f"  30s Return统计:")
    print(f"    20%分位数: {return_stats['return_percentile_20']:.6f}")
    print(f"    80%分位数: {return_stats['return_percentile_80']:.6f}")
    print(f"    中位数: {return_stats['return_median']:.6f}")
    
    print(f"\n  Spread统计:")
    print(f"    中位数: {spread_stats['spread_median']:.6f}")
    
    # 4. 读取资金费率数据
    print(f"\n步骤4: 读取资金费率数据")
    try:
        preparer = DataPreparer()
        funding_data = preparer.prepare_funding_rate(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date
        )
        print(f"  ✅ 资金费率数据: {len(funding_data)} 条记录")
        if len(funding_data) > 0:
            start_ts_funding = int(funding_data[0, 0])
            end_ts_funding = int(funding_data[-1, 0])
            start_dt_funding = datetime.fromtimestamp(start_ts_funding / 1000, tz=timezone.utc)
            end_dt_funding = datetime.fromtimestamp(end_ts_funding / 1000, tz=timezone.utc)
            print(f"    时间范围: {start_dt_funding.strftime('%Y-%m-%d %H:%M:%S')} 到 {end_dt_funding.strftime('%Y-%m-%d %H:%M:%S')}")
    except Exception as e:
        print(f"  ⚠️  读取资金费率数据失败: {e}")
        funding_data = np.empty((0, 2), dtype=np.float64)
    
    # 5. 设计策略参数（优化版本）
    print(f"\n步骤5: 设计优化策略参数")
    return_p20 = return_stats['return_percentile_20']
    return_p80 = return_stats['return_percentile_80']
    spread_median = spread_stats['spread_median']
    
    # 优化参数
    order_size = 100.0
    min_spread_pct = max(spread_median * 3, 0.002)  # 至少0.2%
    price_update_threshold = max(spread_median * 3, 0.002)  # 增加阈值
    hedge_threshold_pct = 0.8  # 80%时开始对冲
    stop_loss_pct = 0.1  # 10%止损
    
    print(f"  策略参数:")
    print(f"    return_percentile_20: {return_p20:.6f}")
    print(f"    return_percentile_80: {return_p80:.6f}")
    print(f"    spread_median: {spread_median:.6f}")
    print(f"    order_size: {order_size}")
    print(f"    min_spread_pct: {min_spread_pct:.6f} (优化：至少0.2%)")
    print(f"    price_update_threshold: {price_update_threshold:.6f} (优化：增加阈值)")
    print(f"    hedge_threshold_pct: {hedge_threshold_pct} (优化：80%时开始对冲)")
    print(f"    stop_loss_pct: {stop_loss_pct} (优化：10%止损)")
    
    # 6. 创建优化策略
    print(f"\n步骤6: 创建优化版本的动量做市策略")
    strategy_params = {
        "exposure": 10000,
        "target_pct": 0.5,
        "initial_cash": 10000.0,
        "initial_pos": 0.0,
        "mini_price_step": 0.0001,
        "taker_fee_rate": 0.00015,
        "maker_fee_rate": -0.00005,
        "open_ratio": 0.5,
        "funding_rate_data": funding_data.tolist() if len(funding_data) > 0 else [],
        "return_percentile_20": return_p20,
        "return_percentile_80": return_p80,
        "spread_median": spread_median,
        "order_size": order_size,
        "price_update_threshold": price_update_threshold,
        "min_spread_pct": min_spread_pct,
        "hedge_threshold_pct": hedge_threshold_pct,
        "stop_loss_pct": stop_loss_pct
    }
    
    strategy = MomentumMMOptimizedStrategy(
        return_percentile_20=return_p20,
        return_percentile_80=return_p80,
        spread_median=spread_median,
        order_size=order_size,
        price_update_threshold=price_update_threshold,
        min_spread_pct=min_spread_pct,
        hedge_threshold_pct=hedge_threshold_pct,
        stop_loss_pct=stop_loss_pct,
        params=strategy_params
    )
    print(f"  ✅ 优化策略创建成功")
    
    # 7. 执行回测
    print(f"\n步骤7: 执行回测")
    try:
        results = strategy.run_backtest(merged_data)
        print(f"  ✅ 回测完成")
        print(f"    账户变动记录: {len(results['accounts'])} 条")
        print(f"    订单统计记录: {len(results['place_orders_stats'])} 条")
    except Exception as e:
        print(f"  ❌ 回测失败: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # 8. 分析结果
    print(f"\n步骤8: 分析结果")
    performance = analyze_performance(
        accounts_raw=results["accounts"],
        place_orders_stats_raw=results["place_orders_stats"]
    )
    
    print(f"  总体绩效:")
    overall = performance.get('overall_performance', {})
    print(f"    总PnL (含手续费): {overall.get('total_pnl_with_fees', 0):.2f}")
    print(f"    总PnL (不含手续费): {overall.get('total_pnl_no_fees', 0):.2f}")
    print(f"    最大回撤: {overall.get('max_drawdown', 0)*100:.2f}%")
    print(f"    夏普比率: {overall.get('sharpe_ratio', 0):.4f}")
    
    # 9. 提取策略指标
    print(f"\n步骤9: 提取策略运行指标")
    strategy_metrics = extract_strategy_metrics(
        accounts=results["accounts"],
        place_orders_stats=results["place_orders_stats"],
        performance=performance
    )
    
    print(f"  仓位指标:")
    pos_metrics = strategy_metrics.get('position_metrics', {})
    print(f"    最大仓位价值: {pos_metrics.get('max_position_value', 0):.2f}")
    print(f"    平均仓位价值: {pos_metrics.get('avg_position_value', 0):.2f}")
    print(f"    多空比: {pos_metrics.get('long_short_ratio', 0):.4f}")
    
    print(f"\n  订单指标:")
    order_metrics = strategy_metrics.get('order_metrics', {})
    print(f"    挂单频率: {order_metrics.get('place_order_freq_per_hour', 0):.2f} 次/小时")
    print(f"    撤单频率: {order_metrics.get('revoke_order_freq_per_hour', 0):.2f} 次/小时")
    print(f"    平均挂单间隔: {order_metrics.get('avg_place_interval_sec', 0):.2f} 秒")
    
    print(f"\n  成交指标:")
    trade_metrics = strategy_metrics.get('trade_metrics', {})
    print(f"    Maker/Taker比例: {trade_metrics.get('maker_taker_ratio', 0):.4f}")
    print(f"    平均成交率: {trade_metrics.get('avg_fill_rate', 0)*100:.2f}%")
    
    print(f"\n  盈利指标:")
    pnl_metrics = strategy_metrics.get('pnl_metrics', {})
    print(f"    多头盈利: {pnl_metrics.get('long_pnl', 0):.2f}")
    print(f"    空头盈利: {pnl_metrics.get('short_pnl', 0):.2f}")
    print(f"    Maker盈利: {pnl_metrics.get('maker_pnl', 0):.2f}")
    print(f"    Taker盈利: {pnl_metrics.get('taker_pnl', 0):.2f}")
    
    # 10. 保存结果
    print(f"\n步骤10: 保存结果")
    run_dir, manager = create_result_directory(
        mode="test",
        symbol=symbol,
        target="momentum_mm_optimized",
        scenario="30s_return_optimized",
        parameters={
            "exposure": 10000,
            "target_pct": 0.5,
            "return_p20": return_p20,
            "return_p80": return_p80,
            "spread_median": spread_median,
            "order_size": order_size,
            "min_spread_pct": min_spread_pct,
            "hedge_threshold_pct": hedge_threshold_pct,
            "stop_loss_pct": stop_loss_pct
        }
    )
    
    manager.save_results(performance, "performance.json")
    manager.save_results(strategy_params, "strategy_params.json")
    manager.save_results(return_stats, "return_statistics.json")
    manager.save_results(spread_stats, "spread_statistics.json")
    manager.save_results(strategy_metrics, "strategy_metrics.json")  # 保存策略指标
    
    print(f"  ✅ 结果已保存到: {run_dir}")
    print(f"  ⚠️  为节省空间，未保存npy大文件（accounts.npy, place_orders_stats.npy, funding_rate_data.npy）")
    
    # 11. 生成可视化图表
    print(f"\n步骤11: 生成可视化图表")
    try:
        plot_comprehensive_analysis(
            accounts=results["accounts"],
            place_orders_stats=results["place_orders_stats"],
            performance=performance,
            title=f"{symbol} Momentum MM Optimized Strategy Analysis",
            save_path=str(manager.get_output_path("comprehensive_analysis.png"))
        )
        print(f"  ✅ 图表已生成")
    except Exception as e:
        print(f"  ⚠️  图表生成失败: {e}")
        import traceback
        traceback.print_exc()
    
    # 12. 对比分析
    print(f"\n步骤12: 优化效果对比")
    print(f"  优化前预期亏损: -14,022.35")
    print(f"  优化后实际PnL: {overall.get('total_pnl_with_fees', 0):.2f}")
    improvement = overall.get('total_pnl_with_fees', 0) - (-14022.35)
    improvement_pct = (improvement / 14022.35 * 100) if 14022.35 > 0 else 0.0
    print(f"  改进幅度: {improvement:+.2f} ({improvement_pct:+.2f}%)")
    
    print(f"\n" + "=" * 70)
    print("✅ 优化版本的动量做市策略测试完成！")
    print("=" * 70)


if __name__ == "__main__":
    test_momentum_mm_optimized()

