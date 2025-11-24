"""测试基于30s return动量的做市策略"""
from datetime import datetime, timedelta, timezone
import numpy as np
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 添加bigdata_plan到路径
bigdata_plan_path = Path("/home/wilson/bigdata_plan")
if str(bigdata_plan_path) not in sys.path:
    sys.path.insert(0, str(bigdata_plan_path))

from src.data.preparer import DataPreparer
from src.data.preprocessor import merge_exchange_data
from src.strategies.momentum_mm_strategy import MomentumMMStrategy
from src.utils.return_statistics import calculate_return_statistics, calculate_spread_statistics
from src.utils.path_manager import create_result_directory
from src.analysis.visualization import plot_comprehensive_analysis
from src.analysis.statistics import analyze_performance


def test_momentum_mm_strategy():
    """测试动量做市策略"""
    print("=" * 70)
    print("测试基于30s return动量的做市策略")
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
    import glob
    import zipfile
    import duckdb
    import tempfile
    import pandas as pd
    
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
                            import os
                            if os.path.exists(tmp_path):
                                os.unlink(tmp_path)
            except Exception as e:
                print(f"  ⚠️  读取文件失败 {Path(zip_file).name}: {e}")
                continue
        
        if not data_list:
            print(f"  ❌ 未找到数据")
            return
        
        binance_data = np.vstack(data_list)
        binance_data = binance_data[np.argsort(binance_data[:, 0])]  # 按时间排序
        
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
        blofin_data[:, 4] = 0  # mm_flag = 0 (Blofin trades)
        
        # 剩余数据作为Binance市场数据
        remaining_indices = np.setdiff1d(np.arange(len(binance_data)), blofin_indices)
        binance_market_data = binance_data[remaining_indices].copy()
        binance_market_data[:, 4] = 1  # mm_flag = 1 (Binance market data)
        
        # 合并数据
        merged_data = merge_exchange_data([blofin_data, binance_market_data], [0, 1])
        print(f"  ✅ 合并后数据: {len(merged_data)} 条记录")
        print(f"    - Blofin trades (mm_flag=0): {len(blofin_data)} 条")
        print(f"    - Binance market data (mm_flag=1): {len(binance_market_data)} 条")
        
        conn.close()
        
    except Exception as e:
        print(f"  ❌ 读取aggtrade数据失败: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # 3. 读取资金费率数据
    print(f"\n步骤3: 读取资金费率数据")
    preparer = DataPreparer()
    try:
        funding_data = preparer.prepare_funding_rate(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date
        )
        print(f"  ✅ 资金费率数据: {len(funding_data)} 条记录")
    except Exception as e:
        print(f"  ⚠️  读取资金费率数据失败: {e}")
        funding_data = np.empty((0, 2), dtype=np.float64)
    
    # 4. 统计30s return和spread分布
    print(f"\n步骤4: 统计30s return和spread分布")
    return_stats = calculate_return_statistics(merged_data)
    spread_stats = calculate_spread_statistics(merged_data)
    
    print(f"  30s Return统计:")
    print(f"    20%分位数: {return_stats['return_percentile_20']:.6f}")
    print(f"    80%分位数: {return_stats['return_percentile_80']:.6f}")
    print(f"    中位数: {return_stats['return_median']:.6f}")
    print(f"    均值: {return_stats['return_mean']:.6f}")
    print(f"    标准差: {return_stats['return_std']:.6f}")
    print(f"    范围: [{return_stats['return_min']:.6f}, {return_stats['return_max']:.6f}]")
    print(f"    有效样本数: {return_stats['return_count']}")
    
    print(f"  Spread统计:")
    print(f"    中位数: {spread_stats['spread_median']:.6f}")
    print(f"    均值: {spread_stats['spread_mean']:.6f}")
    print(f"    标准差: {spread_stats['spread_std']:.6f}")
    
    # 5. 设计策略参数
    print(f"\n步骤5: 设计策略参数")
    return_p20 = return_stats['return_percentile_20']
    return_p80 = return_stats['return_percentile_80']
    spread_median = spread_stats['spread_median']
    
    # 根据统计设计参数
    order_size = 100.0  # 单笔挂单金额（USDT）
    price_update_threshold = max(spread_median * 2, 0.001)  # 价格更新阈值
    
    print(f"  策略参数:")
    print(f"    return_percentile_20: {return_p20:.6f}")
    print(f"    return_percentile_80: {return_p80:.6f}")
    print(f"    spread_median: {spread_median:.6f}")
    print(f"    order_size: {order_size}")
    print(f"    price_update_threshold: {price_update_threshold:.6f}")
    
    # 6. 创建策略
    print(f"\n步骤6: 创建动量做市策略")
    strategy_params = {
        "exposure": 10000,
        "target_pct": 0.5,
        "initial_cash": 10000.0,
        "initial_pos": 0.0,
        "mini_price_step": 0.0001,  # AXSUSDT
        "funding_rate_data": funding_data.tolist() if len(funding_data) > 0 else [],
        "return_percentile_20": return_p20,
        "return_percentile_80": return_p80,
        "spread_median": spread_median,
        "order_size": order_size,
        "price_update_threshold": price_update_threshold
    }
    
    strategy = MomentumMMStrategy(
        return_percentile_20=return_p20,
        return_percentile_80=return_p80,
        spread_median=spread_median,
        order_size=order_size,
        price_update_threshold=price_update_threshold,
        params=strategy_params
    )
    print(f"  ✅ 策略创建成功")
    
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
    
    # 9. 保存结果
    print(f"\n步骤9: 保存结果")
    run_dir, manager = create_result_directory(
        base_type="test",
        symbol=symbol,
        experiment_name="momentum_mm",
        experiment_scenario="30s_return",
        params={
            "exposure": 10000,
            "target_pct": 0.5,
            "return_p20": return_p20,
            "return_p80": return_p80,
            "spread_median": spread_median,
            "order_size": order_size
        }
    )
    
    manager.save_results(performance, "performance.json")
    manager.save_results(strategy_params, "strategy_params.json")
    manager.save_results(return_stats, "return_statistics.json")
    manager.save_results(spread_stats, "spread_statistics.json")
    
    print(f"  ✅ 结果已保存到: {run_dir}")
    
    # 10. 生成可视化图表
    print(f"\n步骤10: 生成可视化图表")
    try:
        plot_comprehensive_analysis(
            accounts=results["accounts"],
            place_orders_stats=results["place_orders_stats"],
            performance=performance,
            title=f"{symbol} Momentum MM Strategy Analysis",
            save_path=str(manager.get_output_path("comprehensive_analysis.png"))
        )
        print(f"  ✅ 图表已生成")
    except Exception as e:
        print(f"  ⚠️  图表生成失败: {e}")
        import traceback
        traceback.print_exc()
    
    print(f"\n" + "=" * 70)
    print("✅ 动量做市策略测试完成！")
    print("=" * 70)


if __name__ == "__main__":
    test_momentum_mm_strategy()

