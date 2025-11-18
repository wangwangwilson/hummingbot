"""回测框架测试脚本"""
import sys
from pathlib import Path
from datetime import datetime, timedelta
import numpy as np

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.data.preparer import DataPreparer
from src.wrapper.backtester import MarketMakerBacktester
from src.analysis.statistics import analyze_performance
from src.analysis.visualization import plot_equity_curve, plot_drawdown, plot_trade_distribution


def test_single_exchange_backtest():
    """测试单个交易所的回测 - 使用AXS最近2天数据"""
    print("=" * 60)
    print("开始测试单个交易所回测 - AXS (Binance)")
    print("=" * 60)
    
    # 初始化数据准备器
    preparer = DataPreparer()
    
    # 准备测试数据 - 使用Binance数据
    symbol = "AXSUSDT"
    trading_type = "um"  # 永续合约
    end_date = datetime.now()
    start_date = end_date - timedelta(days=2)  # 测试最近2天的数据
    
    print(f"\n准备数据: {symbol} {trading_type}")
    print(f"时间范围: {start_date} 到 {end_date}")
    
    try:
        # 尝试使用BinanceDataReader读取（支持zip文件）
        try:
            data = preparer.prepare_binance_aggtrades(
                symbol=symbol,
                trading_type=trading_type,
                start_date=start_date,
                end_date=end_date,
                contract_size=1.0
            )
            print("✅ 使用BinanceDataReader成功读取数据")
        except (ImportError, AttributeError) as e:
            print(f"⚠️  BinanceDataReader不可用: {e}")
            print("尝试使用DuckDB直接读取zip文件...")
            
            # 使用DuckDB直接读取zip内的CSV
            import glob
            import zipfile
            import tempfile
            import duckdb
            
            data_dir = Path("/mnt/hdd/binance-public-data/data/futures/um/daily/aggTrades") / symbol
            if not data_dir.exists():
                print(f"❌ 数据目录不存在: {data_dir}")
                return False
            
            zip_files = sorted(glob.glob(str(data_dir / "*.zip")))
            if not zip_files:
                print(f"❌ 未找到zip文件")
                return False
            
            print(f"找到 {len(zip_files)} 个zip文件")
            
            # 筛选最近2天的文件
            start_ts = int(start_date.timestamp() * 1000)
            end_ts = int(end_date.timestamp() * 1000)
            
            # 读取zip文件内容
            all_data = []
            conn = duckdb.connect()
            
            for zip_file in zip_files[-10:]:  # 只处理最近10个文件以加快速度
                try:
                    with zipfile.ZipFile(zip_file, 'r') as z:
                        csv_files = [f for f in z.namelist() if f.endswith('.csv')]
                        if not csv_files:
                            continue
                        
                        with z.open(csv_files[0]) as f:
                            csv_content = f.read().decode('utf-8')
                            
                            # 使用临时文件
                            with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as tmp:
                                tmp.write(csv_content)
                                tmp_path = tmp.name
                            
                            try:
                                # 读取CSV并过滤时间范围
                                # aggTrades格式: agg_trade_id, price, quantity, first_trade_id, last_trade_id, transact_time, is_buyer_maker
                                # 注意：CSV有header，使用header=true
                                df = conn.execute(f"""
                                    SELECT 
                                        CAST(transact_time AS BIGINT) as create_time,
                                        CASE WHEN is_buyer_maker = 'true' THEN -1 ELSE 1 END as order_side,
                                        CAST(price AS DOUBLE) as trade_price,
                                        CAST(quantity AS DOUBLE) as trade_quantity,
                                        0 as mm
                                    FROM read_csv_auto('{tmp_path}', header=true)
                                    WHERE CAST(transact_time AS BIGINT) >= {start_ts} 
                                      AND CAST(transact_time AS BIGINT) <= {end_ts}
                                """).df()
                                
                                if not df.empty:
                                    all_data.append(df.values)
                            finally:
                                import os
                                if os.path.exists(tmp_path):
                                    os.unlink(tmp_path)
                except Exception as e:
                    print(f"⚠️  处理文件 {zip_file} 时出错: {e}")
                    continue
            
            conn.close()
            
            if not all_data:
                print("❌ 未能从zip文件中读取到数据")
                return False
            
            # 合并所有数据
            data = np.vstack(all_data)
            print(f"✅ 从zip文件读取到 {len(data)} 条记录")
        
        if data.size == 0:
            print("❌ 无法获取测试数据，请检查数据目录")
            return False
        
        print(f"✅ 数据准备完成，共 {len(data)} 条记录")
        print(f"   时间范围: {datetime.fromtimestamp(data[0, 0]/1000)} 到 {datetime.fromtimestamp(data[-1, 0]/1000)}")
        
        # 使用全部数据进行完整测试（不再限制数据量）
        print(f"   使用全部 {len(data)} 条记录进行完整测试")
        
        # 初始化回测器
        print("\n初始化回测器...")
        # AXS价格通常在几美元，使用0.0001作为最小价格步长
        backtester = MarketMakerBacktester(
            exposure=250e4,
            target_pct=0.5,
            initial_cash=100e4,
            initial_pos=0.0,
            mini_price_step=0.0001  # AXS价格步长
        )
        
        # 执行回测
        print("\n执行回测...")
        backtester.run_backtest(data)
        
        print(f"\n✅ 回测完成")
        print(f"   账户记录数: {len(backtester.accounts)}")
        print(f"   订单记录数: {len(backtester.place_orders_stats)}")
        
        # 性能分析
        print("\n进行性能分析...")
        performance = analyze_performance(
            accounts_raw=backtester.accounts,
            place_orders_stats_raw=backtester.place_orders_stats
        )
        
        print("\n" + "=" * 60)
        print("回测结果摘要 (AXS - Binance - 2天)")
        print("=" * 60)
        print(f"数据时间范围: {datetime.fromtimestamp(data[0, 0]/1000)} 到 {datetime.fromtimestamp(data[-1, 0]/1000)}")
        print(f"总交易记录数: {len(data)}")
        print(f"账户变动记录数: {len(backtester.accounts)}")
        print(f"订单生命周期记录数: {len(backtester.place_orders_stats)}")
        print(f"\n总体绩效:")
        print(f"  总PnL (含手续费): {performance['overall_performance']['total_pnl_with_fees']:.2f}")
        print(f"  总PnL (不含手续费): {performance['overall_performance']['total_pnl_no_fees']:.2f}")
        print(f"  PnL比率 (含手续费, 万分之几): {performance['overall_performance']['pnl_with_fees_ratio']:.4f}")
        print(f"  PnL比率 (不含手续费, 万分之几): {performance['overall_performance']['pnl_no_fees_ratio']:.4f}")
        print(f"  最大回撤: {performance['overall_performance']['max_drawdown']*100:.2f}%")
        print(f"  夏普比率: {performance['overall_performance']['sharpe_ratio']:.4f}")
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
        
        # 生成可视化图表
        print("\n生成可视化图表...")
        # 生成可视化图表
        print("\n生成可视化图表...")
        try:
            output_dir = Path("output")
            output_dir.mkdir(exist_ok=True)
            
            plot_equity_curve(
                backtester.accounts,
                title=f"{symbol} Equity Curve (Binance, 2 days)",
                save_path=str(output_dir / "equity_curve.png")
            )
            print(f"✅ 净值曲线已保存: {output_dir / 'equity_curve.png'}")
            
            plot_drawdown(
                backtester.accounts,
                title=f"{symbol} Drawdown (Binance, 2 days)",
                save_path=str(output_dir / "drawdown.png")
            )
            print(f"✅ 回撤曲线已保存: {output_dir / 'drawdown.png'}")
            
            plot_trade_distribution(
                backtester.accounts,
                title=f"{symbol} Trade Distribution (Binance, 2 days)",
                save_path=str(output_dir / "trade_distribution.png")
            )
            print(f"✅ 交易分布图已保存: {output_dir / 'trade_distribution.png'}")
        except Exception as e:
            print(f"⚠️  生成图表时出错: {e}")
            import traceback
            traceback.print_exc()
        
        preparer.close()
        print("\n" + "=" * 60)
        print("✅ 测试完成！")
        print("=" * 60)
        return True
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        preparer.close()
        return False


if __name__ == "__main__":
    success = test_single_exchange_backtest()
    sys.exit(0 if success else 1)

