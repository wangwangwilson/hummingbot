"""测试动量做市策略的数据加载和统计"""
import sys
import os
from pathlib import Path
from datetime import datetime, timezone

# 设置路径
project_root = Path(__file__).parent.parent.absolute()
os.chdir(project_root)
sys.path.insert(0, str(project_root))
sys.path.insert(0, '/home/wilson/bigdata_plan')

# 直接导入（使用绝对路径）
import importlib.util
return_stats_path = project_root / "src" / "utils" / "return_statistics.py"
spec = importlib.util.spec_from_file_location("return_statistics", return_stats_path)
return_stats_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(return_stats_module)
calculate_return_statistics = return_stats_module.calculate_return_statistics
calculate_spread_statistics = return_stats_module.calculate_spread_statistics
import numpy as np
import glob
import zipfile
import duckdb
import tempfile
import pandas as pd

def test_data_load_and_statistics():
    """测试数据加载和统计"""
    print("=" * 70)
    print("测试动量做市策略 - 数据加载和统计")
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
        
        # 合并数据（直接实现，避免导入问题）
        # 简单合并：按时间排序
        all_data = np.vstack([blofin_data, binance_market_data])
        merged_data = all_data[np.argsort(all_data[:, 0])]
        print(f"  ✅ 合并后数据: {len(merged_data)} 条记录")
        
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
    print(f"    均值: {return_stats['return_mean']:.6f}")
    print(f"    标准差: {return_stats['return_std']:.6f}")
    print(f"    范围: [{return_stats['return_min']:.6f}, {return_stats['return_max']:.6f}]")
    print(f"    有效样本数: {return_stats['return_count']}")
    
    print(f"\n  Spread统计:")
    print(f"    中位数: {spread_stats['spread_median']:.6f}")
    print(f"    均值: {spread_stats['spread_mean']:.6f}")
    print(f"    标准差: {spread_stats['spread_std']:.6f}")
    
    # 4. 读取资金费率数据
    print(f"\n步骤4: 读取资金费率数据")
    try:
        # 直接导入DataPreparer
        import importlib.util
        preparer_path = project_root / "src" / "data" / "preparer.py"
        spec = importlib.util.spec_from_file_location("preparer", preparer_path)
        preparer_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(preparer_module)
        DataPreparer = preparer_module.DataPreparer
        
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
    
    print(f"\n" + "=" * 70)
    print("✅ 数据加载和统计测试完成！")
    print("=" * 70)
    
    return merged_data, funding_data, return_stats, spread_stats


if __name__ == "__main__":
    test_data_load_and_statistics()

