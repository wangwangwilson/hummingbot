"""测试定时对冲策略（带对冲比例和资金费率）"""
from datetime import datetime, timedelta, timezone
import numpy as np
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.data.preparer import DataPreparer
from src.data.preprocessor import merge_exchange_data
from src.strategies.timed_hedge_strategy import TimedHedgeStrategy
from src.utils.path_manager import create_result_directory
from src.analysis.visualization import plot_comprehensive_analysis
from src.analysis.statistics import analyze_performance


def test_timed_hedge_with_funding():
    """测试定时对冲策略（带对冲比例和资金费率）"""
    print("=" * 70)
    print("测试定时对冲策略（带对冲比例和资金费率）")
    print("=" * 70)
    
    # 1. 配置参数
    symbol = "AXSUSDT"  # 使用AXSUSDT，因为数据可用
    trading_type = "um"  # 永续合约
    days = 10  # 测试最近10天数据
    
    # 计算时间范围
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=days)
    
    print(f"\n步骤1: 配置参数")
    print(f"  交易对: {symbol}")
    print(f"  交易类型: {trading_type}")
    print(f"  时间范围: {start_date.strftime('%Y-%m-%d')} 到 {end_date.strftime('%Y-%m-%d')}")
    
    # 2. 读取aggtrade数据
    print(f"\n步骤2: 读取aggtrade数据")
    import glob
    import zipfile
    import duckdb
    
    binance_data_dir = "/mnt/hdd/binance-public-data"
    data_path = f"{binance_data_dir}/data/futures/um/daily/aggTrades/{symbol}"
    
    try:
        # 使用DuckDB直接读取ZIP文件（daily目录）
        conn = duckdb.connect()
        zip_files = sorted(glob.glob(f"{data_path}/*.zip"))
        
        if not zip_files:
            print(f"  ❌ 未找到数据文件: {data_path}")
            return
        
        # 读取最近几天的数据
        start_ts = int(start_date.timestamp() * 1000)
        end_ts = int(end_date.timestamp() * 1000)
        
        import tempfile
        import pandas as pd
        data_list = []
        for zip_file in zip_files[-10:]:  # 读取最近10个文件
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
            print("  ❌ 未找到数据")
            return
        
        # 合并数据
        all_data = np.vstack(data_list)
        # 按时间戳排序
        all_data = all_data[all_data[:, 0].argsort()]
        
        # 转换为numpy数组并预处理（格式：[timestamp, order_side, price, quantity, mm_flag]）
        # 注意：all_data已经是 [timestamp, order_side, price, quantity, mm] 格式
        # 需要转换为preprocess_aggtrades需要的格式：[timestamp, price, quantity, is_buyer_maker]
        # 但preprocess_aggtrades需要is_buyer_maker，而我们有order_side
        # 所以我们需要转换：is_buyer_maker = -order_side (如果order_side=1，则is_buyer_maker=-1，表示买方是maker)
        from src.data.preprocessor import preprocess_aggtrades
        # 创建临时数组：[timestamp, price, quantity, is_buyer_maker]
        temp_array = np.zeros((len(all_data), 4))
        temp_array[:, 0] = all_data[:, 0]  # timestamp
        temp_array[:, 1] = all_data[:, 2]  # price
        temp_array[:, 2] = all_data[:, 3]  # quantity
        temp_array[:, 3] = -all_data[:, 1]  # is_buyer_maker = -order_side
        
        binance_data = preprocess_aggtrades(temp_array, exchange_flag=1, contract_size=1.0)
        
        print(f"  ✅ Binance数据: {len(binance_data)} 条记录")
        if len(binance_data) > 0:
            start_ts_data = int(binance_data[0, 0])
            end_ts_data = int(binance_data[-1, 0])
            start_dt_data = datetime.fromtimestamp(start_ts_data / 1000, tz=timezone.utc)
            end_dt_data = datetime.fromtimestamp(end_ts_data / 1000, tz=timezone.utc)
            print(f"    时间范围: {start_dt_data.strftime('%Y-%m-%d %H:%M:%S')} 到 {end_dt_data.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"    数据shape: {binance_data.shape}")
        
        if len(binance_data) == 0:
            print("  ❌ 未找到数据，退出测试")
            return
        
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
        print(f"    数据shape: {merged_data.shape}")
        print(f"    - Blofin trades (mm_flag=0): {len(blofin_data)} 条")
        print(f"    - Binance market data (mm_flag=1): {len(binance_market_data)} 条")
        if len(merged_data) > 0:
            start_ts_merged = int(merged_data[0, 0])
            end_ts_merged = int(merged_data[-1, 0])
            start_dt_merged = datetime.fromtimestamp(start_ts_merged / 1000, tz=timezone.utc)
            end_dt_merged = datetime.fromtimestamp(end_ts_merged / 1000, tz=timezone.utc)
            print(f"    合并后时间范围: {start_dt_merged.strftime('%Y-%m-%d %H:%M:%S')} 到 {end_dt_merged.strftime('%Y-%m-%d %H:%M:%S')}")
        
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
        print(f"    数据shape: {funding_data.shape if len(funding_data) > 0 else 'N/A'}")
        
        if len(funding_data) > 0:
            start_ts_funding = int(funding_data[0, 0])
            end_ts_funding = int(funding_data[-1, 0])
            start_dt_funding = datetime.fromtimestamp(start_ts_funding / 1000, tz=timezone.utc)
            end_dt_funding = datetime.fromtimestamp(end_ts_funding / 1000, tz=timezone.utc)
            print(f"    时间范围: {start_dt_funding.strftime('%Y-%m-%d %H:%M:%S')} 到 {end_dt_funding.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"    费率范围: {funding_data[:, 1].min():.6f} 到 {funding_data[:, 1].max():.6f}")
            
            # 检查时间对齐
            if len(merged_data) > 0:
                start_ts_merged = int(merged_data[0, 0])
                end_ts_merged = int(merged_data[-1, 0])
                print(f"    数据对齐检查:")
                print(f"      aggtrade时间范围: {datetime.fromtimestamp(start_ts_merged / 1000, tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} 到 {datetime.fromtimestamp(end_ts_merged / 1000, tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}")
                print(f"      funding时间范围: {start_dt_funding.strftime('%Y-%m-%d %H:%M:%S')} 到 {end_dt_funding.strftime('%Y-%m-%d %H:%M:%S')}")
                if start_ts_funding >= start_ts_merged and end_ts_funding <= end_ts_merged:
                    print(f"      ✅ 资金费时间范围在aggtrade时间范围内")
                else:
                    print(f"      ⚠️  资金费时间范围与aggtrade时间范围不完全对齐")
    except Exception as e:
        print(f"  ⚠️  读取资金费率数据失败: {e}")
        import traceback
        traceback.print_exc()
        funding_data = np.empty((0, 2), dtype=np.float64)
    
    # 4. 创建定时对冲策略
    print(f"\n步骤4: 创建定时对冲策略")
    strategy_params = {
        "exposure": 50000,
        "target_pct": 0.5,
        "mini_price_step": 0.0001,  # AXSUSDT
        "funding_rate_data": funding_data.tolist() if len(funding_data) > 0 else []
    }
    
    strategy = TimedHedgeStrategy(
        hedge_hours=[],  # 使用hedge_interval_hours，不需要指定具体小时
        hedge_target_ratio=0.2,
        timezone_offset=8,  # 默认UTC+8，支持其他时区（如0表示UTC）
        hedge_interval_hours=2,
        params=strategy_params
    )
    print(f"  ✅ 策略创建成功")
    print(f"    对冲目标比例: {strategy.hedge_target_ratio*100}%")
    print(f"    时区偏移: UTC+{strategy.timezone_offset}")
    print(f"    对冲间隔: 每{strategy.hedge_interval_hours}小时")
    print(f"    资金费率数据: {len(funding_data)} 条")
    
    # 5. 执行回测
    print(f"\n步骤5: 执行回测")
    try:
        results = strategy.run_backtest(merged_data)
        print(f"  ✅ 回测完成")
    except Exception as e:
        print(f"  ❌ 回测失败: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # 6. 分析结果
    print(f"\n步骤6: 分析结果")
    performance = results["performance"]
    
    print(f"\n对冲信息:")
    hedge_info = performance.get("hedge_info", {})
    print(f"  对冲时间点数量: {hedge_info.get('hedge_timestamps_count', 0)}")
    
    print(f"\n总体绩效:")
    overall = performance.get("overall_performance", {})
    print(f"  总PnL (含手续费): {overall.get('total_pnl_with_fees', 0):.2f}")
    print(f"  总PnL (不含手续费): {overall.get('total_pnl_no_fees', 0):.2f}")
    print(f"  最大回撤: {overall.get('max_drawdown', 0)*100:.2f}%")
    print(f"  夏普比率: {overall.get('sharpe_ratio', np.nan):.4f}")
    
    # 检查资金费支付
    accounts = results["accounts"]
    funding_payments = accounts[accounts[:, 9] == 6]  # info=6表示资金费支付
    if len(funding_payments) > 0:
        print(f"\n资金费支付:")
        print(f"  支付次数: {len(funding_payments)}")
        total_funding_cost = 0
        for i, payment in enumerate(funding_payments[:5]):  # 只显示前5个
            ts = payment[0]
            dt = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
            pos = payment[2]
            price = payment[4]
            pos_value = pos * price
            # 从账户变化中估算资金费（通过现金变化）
            if i > 0:
                prev_cash = accounts[accounts[:, 0] < ts][-1, 1] if len(accounts[accounts[:, 0] < ts]) > 0 else payment[1]
                funding_fee = prev_cash - payment[1]
                total_funding_cost += funding_fee
                print(f"    {dt.strftime('%Y-%m-%d %H:%M:%S')}: 仓位={pos:.4f}, 价格={price:.2f}, 仓位价值={pos_value:.2f}, 资金费={funding_fee:.2f}")
        if len(funding_payments) > 5:
            print(f"    ... 还有 {len(funding_payments) - 5} 个资金费支付点")
        print(f"  总资金费成本: {total_funding_cost:.2f}")
        
        # 显示资金费统计
        funding_stats = performance.get("funding_analysis", {})
        if funding_stats:
            print(f"\n资金费统计:")
            print(f"  资金费收入: {funding_stats.get('funding_income', 0):.2f}")
            print(f"  资金费收入占比: {funding_stats.get('funding_income_ratio', 0):.2f}%")
            print(f"  资金费交易额收益率: {funding_stats.get('funding_return_rate', 0):.4f} bps")
    
    # 7. 保存结果
    print(f"\n步骤7: 保存结果")
    run_dir, manager = create_result_directory(
        mode="test",
        symbol=symbol,
        target="backtest",
        scenario="timed_hedge_with_funding",
        parameters={
            "exposure": 50000,
            "target_pct": 0.5,
            "hedge_target_ratio": 0.2,
            "timezone_offset": 8,  # UTC+8
            "hedge_interval_hours": 2,
            "days": days
        }
    )
    
    manager.save_results(performance, "performance.json")
    manager.save_results(strategy.params, "strategy_params.json")
    
    # 不保存npy大文件，节省空间
    # np.save(manager.get_output_path("accounts.npy"), results["accounts"])
    # np.save(manager.get_output_path("place_orders_stats.npy"), results["place_orders_stats"])
    # if len(funding_data) > 0:
    #     np.save(manager.get_output_path("funding_rate_data.npy"), funding_data)
    
    print(f"  ✅ 结果已保存到: {run_dir}")
    print(f"  ⚠️  为节省空间，未保存npy大文件（accounts.npy, place_orders_stats.npy, funding_rate_data.npy）")
    
    # 8. 生成可视化图表
    print(f"\n步骤8: 生成可视化图表")
    try:
        plot_comprehensive_analysis(
            accounts=results["accounts"],
            place_orders_stats=results["place_orders_stats"],
            performance=performance,
            title=f"{symbol} Comprehensive Backtest Analysis (Timed Hedge with Funding)",
            save_path=str(manager.get_output_path("comprehensive_analysis.png"))
        )
        print(f"  ✅ 图表已生成")
    except Exception as e:
        print(f"  ⚠️  生成图表失败: {e}")
        import traceback
        traceback.print_exc()
    
    # 9. 验证对冲效果
    print(f"\n步骤9: 验证对冲效果")
    hedge_timestamps = hedge_info.get("hedge_timestamps", [])
    if len(hedge_timestamps) > 0:
        print(f"  检查前3个对冲点:")
        for i, ts in enumerate(hedge_timestamps[:3]):
            dt = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
            # 找到对冲后的账户记录
            hedge_mask = (accounts[:, 0] == ts) & (accounts[:, 9] == 5)  # info=5表示定时对冲
            if np.any(hedge_mask):
                hedge_account = accounts[hedge_mask][0]
                pos_after = hedge_account[2]
                target_pos = hedge_account[2] * 0.2  # 目标应该是20%
                print(f"    对冲点 {i+1} ({dt.strftime('%Y-%m-%d %H:%M:%S UTC')}): 对冲后仓位 = {pos_after:.6f}, 目标仓位 = {target_pos:.6f}")
    
    print(f"\n{'='*70}")
    print("✅ 定时对冲策略（带资金费率）测试完成！")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    test_timed_hedge_with_funding()

