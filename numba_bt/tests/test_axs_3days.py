"""AXS最近3天数据完整测试 - 包含blofin和binance数据融合"""
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

from src.data.preparer import DataPreparer
from src.data.preprocessor import preprocess_aggtrades, merge_exchange_data
from src.wrapper.backtester import MarketMakerBacktester
from src.analysis.statistics import analyze_performance
from src.analysis.visualization import plot_equity_curve, plot_drawdown, plot_trade_distribution
from src.utils.path_manager import create_result_directory


def test_axs_3days_with_blofin():
    """测试AXS最近3天数据，包含blofin和binance数据融合"""
    print("=" * 70)
    print("AXS最近3天数据完整测试 - Blofin + Binance数据融合")
    print("=" * 70)
    
    symbol = "AXSUSDT"
    trading_type = "um"
    end_date = datetime.now()
    start_date = end_date - timedelta(days=3)
    
    print(f"\n准备数据: {symbol} {trading_type}")
    print(f"时间范围: {start_date} 到 {end_date}")
    print(f"策略参数: exposure=50000, target_pct=0.5")
    
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
        
        # 读取最近3天的zip文件
        conn = duckdb.connect()
        all_binance_data = []
        
        for zip_file in zip_files[-15:]:  # 处理最近15个文件以确保覆盖3天
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
                                    1 as mm  -- binance trades = 1
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
        
        # 合并所有Binance数据
        binance_data = np.vstack(all_binance_data)
        print(f"✅ 读取到 {len(binance_data)} 条Binance数据")
        print(f"   时间范围: {datetime.fromtimestamp(binance_data[0, 0]/1000)} 到 {datetime.fromtimestamp(binance_data[-1, 0]/1000)}")
        
        # 2. 从Binance数据中随机采样20%作为Blofin数据
        print("\n" + "-" * 70)
        print("步骤2: 从Binance数据中采样20%作为Blofin数据")
        print("-" * 70)
        
        np.random.seed(42)  # 固定随机种子以便复现
        sample_size = int(len(binance_data) * 0.2)
        sample_indices = np.random.choice(len(binance_data), size=sample_size, replace=False)
        sample_indices = np.sort(sample_indices)  # 保持时间顺序
        
        blofin_data = binance_data[sample_indices].copy()
        blofin_data[:, 4] = 0  # 设置mm_flag=0 (blofin trades)
        
        print(f"✅ 采样 {len(blofin_data)} 条数据作为Blofin trades (mm_flag=0)")
        print(f"   时间范围: {datetime.fromtimestamp(blofin_data[0, 0]/1000)} 到 {datetime.fromtimestamp(blofin_data[-1, 0]/1000)}")
        
        # 3. 合并数据
        print("\n" + "-" * 70)
        print("步骤3: 合并Blofin和Binance数据")
        print("-" * 70)
        
        merged_data = merge_exchange_data([blofin_data, binance_data], [0, 1])
        print(f"✅ 合并后共 {len(merged_data)} 条数据")
        print(f"   Blofin数据 (mm_flag=0): {np.sum(merged_data[:, 4] == 0)} 条")
        print(f"   Binance数据 (mm_flag=1): {np.sum(merged_data[:, 4] == 1)} 条")
        print(f"   时间范围: {datetime.fromtimestamp(merged_data[0, 0]/1000)} 到 {datetime.fromtimestamp(merged_data[-1, 0]/1000)}")
        
        # 4. 执行回测
        print("\n" + "-" * 70)
        print("步骤4: 执行回测")
        print("-" * 70)
        
        backtester = MarketMakerBacktester(
            exposure=50000,
            target_pct=0.5,
            initial_cash=100e4,
            initial_pos=0.0,
            mini_price_step=0.0001  # AXS价格步长
        )
        
        print("开始执行Numba加速的回测循环...")
        backtester.run_backtest(merged_data)
        
        print(f"\n✅ 回测完成")
        print(f"   账户变动记录数: {len(backtester.accounts)}")
        print(f"   订单生命周期记录数: {len(backtester.place_orders_stats)}")
        
        # 5. 性能分析
        print("\n" + "-" * 70)
        print("步骤5: 性能分析")
        print("-" * 70)
        
        performance = analyze_performance(
            accounts_raw=backtester.accounts,
            place_orders_stats_raw=backtester.place_orders_stats
        )
        
        print("\n" + "=" * 70)
        print("回测结果摘要 (AXS - 3天 - Blofin + Binance)")
        print("=" * 70)
        print(f"数据时间范围: {datetime.fromtimestamp(merged_data[0, 0]/1000)} 到 {datetime.fromtimestamp(merged_data[-1, 0]/1000)}")
        print(f"总交易记录数: {len(merged_data)}")
        print(f"  - Blofin trades (mm_flag=0): {np.sum(merged_data[:, 4] == 0)} 条")
        print(f"  - Binance trades (mm_flag=1): {np.sum(merged_data[:, 4] == 1)} 条")
        print(f"账户变动记录数: {len(backtester.accounts)}")
        print(f"订单生命周期记录数: {len(backtester.place_orders_stats)}")
        
        print(f"\n总体绩效:")
        print(f"  总PnL (含手续费): {performance['overall_performance']['total_pnl_with_fees']:.2f}")
        print(f"  总PnL (不含手续费): {performance['overall_performance']['total_pnl_no_fees']:.2f}")
        print(f"  PnL比率 (含手续费, 万分之几): {performance['overall_performance']['pnl_with_fees_ratio']:.4f}")
        print(f"  PnL比率 (不含手续费, 万分之几): {performance['overall_performance']['pnl_no_fees_ratio']:.4f}")
        print(f"  最大回撤: {performance['overall_performance']['max_drawdown']*100:.2f}%")
        print(f"  夏普比率: {performance['overall_performance']['sharpe_ratio']:.4f}" if not np.isnan(performance['overall_performance']['sharpe_ratio']) else "  夏普比率: N/A")
        print(f"  年化收益率: {performance['overall_performance']['annualized_return']*100:.2f}%" if not np.isnan(performance['overall_performance']['annualized_return']) else "  年化收益率: N/A")
        print(f"  卡玛比率: {performance['overall_performance']['calmar_ratio']:.4f}" if not np.isnan(performance['overall_performance']['calmar_ratio']) else "  卡玛比率: N/A")
        print(f"  回测时长: {performance['overall_performance']['duration_years']*365:.2f} 天")
        
        print(f"\nMaker绩效:")
        print(f"  Maker PnL: {performance['maker_performance']['total_maker_pnl_no_fees']:.2f}")
        print(f"  Maker交易量: {performance['maker_performance']['maker_volume_total']:.2f}")
        print(f"  Maker PnL比率 (万分之几): {performance['maker_performance']['maker_pnl_ratio']:.4f}")
        print(f"  Maker手续费返佣: {performance['maker_performance']['actual_maker_fees_cost_rebate']:.2f}")
        
        print(f"\nTaker绩效:")
        print(f"  Taker PnL: {performance['taker_performance']['total_taker_pnl_no_fees']:.2f}")
        print(f"  Taker交易量: {performance['taker_performance']['taker_volume_total']:.2f}")
        print(f"  Taker PnL比率 (万分之几): {performance['taker_performance']['taker_pnl_ratio']:.4f}")
        print(f"  Taker手续费成本: {performance['taker_performance']['actual_taker_fees_cost']:.2f}")
        
        print(f"\n手续费分析:")
        print(f"  总手续费净额: {performance['fee_analysis']['total_actual_fees']:.2f}")
        
        # 6. 创建结果目录并保存结果
        print("\n" + "-" * 70)
        print("步骤6: 创建结果目录并保存结果")
        print("-" * 70)
        
        # 创建结果目录
        run_dir, manager = create_result_directory(
            mode="test",
            symbol=symbol,
            target="backtest",
            scenario="multi_exchange",
            parameters={
                "exposure": 50000,
                "target_pct": 0.5,
                "days": 3
            }
        )
        
        print(f"✅ 结果目录已创建: {run_dir}")
        
        # 保存性能分析结果
        manager.save_results(performance, "performance.json")
        print(f"✅ 性能分析结果已保存: {run_dir / 'performance.json'}")
        
        # 保存账户和订单数据（可选）
        if len(backtester.accounts) > 0:
            np.save(manager.get_output_path("accounts.npy"), backtester.accounts)
            print(f"✅ 账户数据已保存: {run_dir / 'accounts.npy'}")
        
        if len(backtester.place_orders_stats) > 0:
            np.save(manager.get_output_path("orders_stats.npy"), backtester.place_orders_stats)
            print(f"✅ 订单统计已保存: {run_dir / 'orders_stats.npy'}")
        
        # 7. 生成可视化图表
        print("\n" + "-" * 70)
        print("步骤7: 生成可视化图表")
        print("-" * 70)
        
        try:
            plot_equity_curve(
                backtester.accounts,
                title=f"{symbol} Equity Curve (3 days, Blofin+Binance)",
                save_path=str(manager.get_output_path("equity_curve.png"))
            )
            print(f"✅ 净值曲线已保存: {run_dir / 'equity_curve.png'}")
            
            plot_drawdown(
                backtester.accounts,
                title=f"{symbol} Drawdown (3 days, Blofin+Binance)",
                save_path=str(manager.get_output_path("drawdown.png"))
            )
            print(f"✅ 回撤曲线已保存: {run_dir / 'drawdown.png'}")
            
            plot_trade_distribution(
                backtester.accounts,
                title=f"{symbol} Trade Distribution (3 days, Blofin+Binance)",
                save_path=str(manager.get_output_path("trade_distribution.png"))
            )
            print(f"✅ 交易分布图已保存: {run_dir / 'trade_distribution.png'}")
        except Exception as e:
            print(f"⚠️  生成图表时出错: {e}")
            import traceback
            traceback.print_exc()
        
        print("\n" + "=" * 70)
        print("✅ 完整测试通过！")
        print("=" * 70)
        return True
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_axs_3days_with_blofin()
    sys.exit(0 if success else 1)

