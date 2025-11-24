"""测试定时对冲策略"""
import sys
from pathlib import Path
from datetime import datetime, timedelta
import numpy as np
import glob
import zipfile
import tempfile
import duckdb

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.data.preprocessor import merge_exchange_data
from src.strategies.timed_hedge_strategy import TimedHedgeStrategy
from src.utils.path_manager import create_result_directory
from src.analysis.visualization import (
    plot_equity_curve, plot_drawdown, plot_trade_distribution,
    plot_comprehensive_analysis
)


def test_timed_hedge_strategy():
    """测试定时对冲策略"""
    print("=" * 70)
    print("定时对冲策略测试 - AXS数据（Blofin + Binance）")
    print("=" * 70)
    
    symbol = "AXSUSDT"
    end_date = datetime.now()
    start_date = end_date - timedelta(days=10)  # 改为10天数据
    
    print(f"\n准备数据: {symbol}")
    print(f"时间范围: {start_date} 到 {end_date}")
    print(f"数据天数: 10天")
    print(f"策略: 定时对冲（UTC时间 0点、8点、16点）")
    
    start_ts = int(start_date.timestamp() * 1000)
    end_ts = int(end_date.timestamp() * 1000)
    
    try:
        # 1. 读取Binance数据
        print("\n" + "-" * 70)
        print("步骤1: 读取Binance数据")
        print("-" * 70)
        
        data_dir = Path("/mnt/hdd/binance-public-data/data/futures/um/daily/aggTrades") / symbol
        if not data_dir.exists():
            print(f"❌ 数据目录不存在: {data_dir}")
            return False
        
        zip_files = sorted(glob.glob(str(data_dir / "*.zip")))
        if not zip_files:
            print(f"❌ 未找到zip文件")
            return False
        
        print(f"找到 {len(zip_files)} 个zip文件")
        # 读取最近30天的文件以确保覆盖10天数据
        print(f"读取最近30天的zip文件...")
        
        conn = duckdb.connect()
        all_binance_data = []
        
        for zip_file in zip_files[-30:]:  # 读取最近30天的文件
            try:
                with zipfile.ZipFile(zip_file, 'r') as z:
                    csv_files = [f for f in z.namelist() if f.endswith('.csv')]
                    if not csv_files:
                        continue
                    
                    with z.open(csv_files[0]) as f:
                        csv_content = f.read().decode('utf-8')
                        
                        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as tmp:
                            tmp.write(csv_content)
                            tmp_path = tmp.name
                        
                        try:
                            df = conn.execute(f"""
                                SELECT 
                                    CAST(transact_time AS BIGINT) as create_time,
                                    CASE WHEN is_buyer_maker = 'true' THEN -1 ELSE 1 END as order_side,
                                    CAST(price AS DOUBLE) as trade_price,
                                    CAST(quantity AS DOUBLE) as trade_quantity,
                                    1 as mm
                                FROM read_csv_auto('{tmp_path}', header=true)
                                WHERE CAST(transact_time AS BIGINT) >= {start_ts} 
                                  AND CAST(transact_time AS BIGINT) <= {end_ts}
                            """).df()
                            
                            if not df.empty:
                                all_binance_data.append(df.values)
                        finally:
                            import os
                            if os.path.exists(tmp_path):
                                os.unlink(tmp_path)
            except Exception as e:
                print(f"⚠️  处理文件 {Path(zip_file).name} 时出错: {e}")
                continue
        
        conn.close()
        
        if not all_binance_data:
            print("❌ 未能从zip文件中读取到Binance数据")
            return False
        
        binance_data = np.vstack(all_binance_data)
        print(f"✅ 读取到 {len(binance_data)} 条Binance数据")
        
        # 2. 采样20%作为Blofin数据
        print("\n" + "-" * 70)
        print("步骤2: 从Binance数据中采样20%作为Blofin数据")
        print("-" * 70)
        
        np.random.seed(42)
        sample_size = int(len(binance_data) * 0.2)
        sample_indices = np.random.choice(len(binance_data), size=sample_size, replace=False)
        sample_indices = np.sort(sample_indices)
        
        blofin_data = binance_data[sample_indices].copy()
        blofin_data[:, 4] = 0  # mm_flag=0
        
        print(f"✅ 采样 {len(blofin_data)} 条数据作为Blofin trades (mm_flag=0)")
        
        # 3. 合并数据
        print("\n" + "-" * 70)
        print("步骤3: 合并Blofin和Binance数据")
        print("-" * 70)
        
        merged_data = merge_exchange_data([blofin_data, binance_data], [0, 1])
        print(f"✅ 合并后共 {len(merged_data)} 条数据")
        print(f"   Blofin trades (mm_flag=0): {np.sum(merged_data[:, 4] == 0)} 条")
        print(f"   Binance trades (mm_flag=1): {np.sum(merged_data[:, 4] == 1)} 条")
        
        # 4. 创建定时对冲策略
        print("\n" + "-" * 70)
        print("步骤4: 创建定时对冲策略")
        print("-" * 70)
        
        strategy = TimedHedgeStrategy(
            hedge_hours=[0, 8, 16],  # UTC时间：0点、8点、16点
            params={
                "exposure": 50000,
                "target_pct": 0.5,
                "initial_cash": 100e4,
                "initial_pos": 0.0,
                "mini_price_step": 0.0001
            }
        )
        
        print(f"✅ 策略创建成功: {strategy.name}")
        print(f"   策略说明: {strategy.description}")
        print(f"   对冲时间点: UTC {strategy.hedge_hours} 点")
        
        # 5. 执行回测
        print("\n" + "-" * 70)
        print("步骤5: 执行回测")
        print("-" * 70)
        
        results = strategy.run_backtest(merged_data)
        
        print(f"\n✅ 回测完成")
        print(f"   账户变动记录数: {len(results['accounts'])}")
        print(f"   订单生命周期记录数: {len(results['place_orders_stats'])}")
        
        # 6. 分析结果
        print("\n" + "-" * 70)
        print("步骤6: 分析结果")
        print("-" * 70)
        
        performance = results["performance"]
        hedge_info = performance.get("hedge_info", {})
        
        print(f"\n对冲信息:")
        print(f"  对冲时间点: UTC {hedge_info.get('hedge_hours', [])} 点")
        print(f"  对冲次数: {hedge_info.get('hedge_timestamps_count', 0)}")
        
        print(f"\n总体绩效:")
        print(f"  总PnL (含手续费): {performance['overall_performance']['total_pnl_with_fees']:.2f}")
        print(f"  总PnL (不含手续费): {performance['overall_performance']['total_pnl_no_fees']:.2f}")
        print(f"  最大回撤: {performance['overall_performance']['max_drawdown']*100:.2f}%")
        print(f"  夏普比率: {performance['overall_performance']['sharpe_ratio']:.4f}" if not np.isnan(performance['overall_performance']['sharpe_ratio']) else "  夏普比率: N/A")
        
        print(f"\nTaker绩效:")
        print(f"  Taker PnL: {performance['taker_performance']['total_taker_pnl_no_fees']:.2f}")
        print(f"  Taker交易量: {performance['taker_performance']['taker_volume_total']:.2f}")
        
        # 验证对冲效果：检查在对冲时间点附近的仓位
        print(f"\n验证对冲效果:")
        accounts = results["accounts"]
        hedge_timestamps = hedge_info.get("hedge_timestamps", [])
        
        if hedge_timestamps:
            for i, hedge_ts in enumerate(hedge_timestamps[:3]):  # 检查前3个对冲点
                # 找到对冲时间点之后的第一个账户记录
                after_hedge = accounts[accounts[:, 0] >= hedge_ts]
                if len(after_hedge) > 0:
                    pos_after = after_hedge[0, 2]  # 仓位
                    dt = datetime.fromtimestamp(hedge_ts / 1000)
                    print(f"  对冲点 {i+1} ({dt.strftime('%Y-%m-%d %H:%M UTC')}): 对冲后仓位 = {pos_after:.6f}")
        
        # 7. 创建结果目录并保存
        print("\n" + "-" * 70)
        print("步骤7: 保存结果")
        print("-" * 70)
        
        run_dir, manager = create_result_directory(
            mode="test",
            symbol=symbol,
            target="backtest",
            scenario="timed_hedge",
            parameters={
                "exposure": 50000,
                "target_pct": 0.5,
                "hedge_hours": strategy.hedge_hours,
                "days": 10
            }
        )
        
        print(f"✅ 结果目录已创建: {run_dir}")
        
        # 保存结果
        manager.save_results(performance, "performance.json")
        np.save(manager.get_output_path("accounts.npy"), results["accounts"])
        np.save(manager.get_output_path("orders_stats.npy"), results["place_orders_stats"])
        
        # 保存策略参数
        strategy.save_params(manager.get_output_path("strategy_params.json"))
        
        print(f"✅ 结果已保存到: {run_dir}")
        
        # 8. 生成可视化图表
        print("\n" + "-" * 70)
        print("步骤8: 生成可视化图表")
        print("-" * 70)
        
        try:
            # 生成综合分析图表
            plot_comprehensive_analysis(
                accounts=results["accounts"],
                place_orders_stats=results["place_orders_stats"],
                performance=performance,
                title=f"{symbol} Comprehensive Backtest Analysis (Timed Hedge Strategy)",
                save_path=str(manager.get_output_path("comprehensive_analysis.png"))
            )
            print(f"✅ 综合分析图表已保存")
            
            # 保留原有的单独图表（可选）
            plot_equity_curve(
                results["accounts"],
                title=f"{symbol} Equity Curve (Timed Hedge Strategy)",
                save_path=str(manager.get_output_path("equity_curve.png"))
            )
            print(f"✅ 净值曲线已保存")
            
            plot_drawdown(
                results["accounts"],
                title=f"{symbol} Drawdown (Timed Hedge Strategy)",
                save_path=str(manager.get_output_path("drawdown.png"))
            )
            print(f"✅ 回撤曲线已保存")
            
            plot_trade_distribution(
                results["accounts"],
                title=f"{symbol} Trade Distribution (Timed Hedge Strategy)",
                save_path=str(manager.get_output_path("trade_distribution.png"))
            )
            print(f"✅ 交易分布图已保存")
        except Exception as e:
            print(f"⚠️  生成图表时出错: {e}")
            import traceback
            traceback.print_exc()
        
        print("\n" + "=" * 70)
        print("✅ 定时对冲策略测试完成！")
        print("=" * 70)
        return True
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_timed_hedge_strategy()
    sys.exit(0 if success else 1)

参考数据说明 @DATA_STRUCTURE.md  我现在想根据kline和metric结合数据，构建一个CTA策略，策略思路就是 当 价格波动较大且交易额放大，同时3. `sum_open_interest` (DOUBLE) - 总持仓量单向 比骤然增大或减少时，同时伴随taker_buy_sell_ratio的异动变化，一般很有可能出现趋势行情，可以买入或者卖出。因此未来探索kline的return和交易量和sum_open_interest和taker_buy_sell_ratio关系很关键，kline是1分钟的，metrics数据是5min的频率，因此探索return必须是大于等于5分钟的return，那么采用q分位分箱的思路，探索 不同周期的return 和 交易量&sum_open_interest & taker_buy_sell_ratio，