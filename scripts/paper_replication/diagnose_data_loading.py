#!/usr/bin/env python3
"""
详细诊断数据加载问题
检查数据文件是否存在、数据数量和连续性
"""

import sys
from datetime import datetime, date
from pathlib import Path
import pandas as pd

# Add project paths
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
tradingview_ai_path = Path("/Users/wilson/Desktop/tradingview-ai")
sys.path.insert(0, str(tradingview_ai_path))

# Temporary disable ccxt
class FakeCCXT:
    pass
sys.modules['ccxt'] = FakeCCXT()

from backtest_comparison_local import LocalBinanceDataProvider

# Test parameters
TRADING_PAIR = "BTC-USDT"
START_DATE = datetime(2025, 1, 1)
END_DATE = datetime(2025, 5, 1)
BACKTEST_RESOLUTION = "1m"


def check_data_files_exist():
    """检查数据文件是否存在"""
    print("="*80)
    print("1. 检查数据文件是否存在")
    print("="*80)
    
    from src.data.sources.binance_public_data_manager import BinancePublicDataManager
    
    manager = BinancePublicDataManager()
    binance_symbol = TRADING_PAIR.replace('-', '')
    start_date = START_DATE.date()
    end_date = END_DATE.date()
    
    print(f"数据目录: {manager.data_dir}")
    print(f"交易对: {binance_symbol}")
    print(f"日期范围: {start_date} 到 {end_date}")
    print()
    
    # 检查文件列表
    current_date = start_date
    file_count = 0
    missing_files = []
    existing_files = []
    
    while current_date <= end_date:
        # 检查日级别文件
        file_name = f"{binance_symbol}-1m-{current_date.strftime('%Y-%m-%d')}.zip"
        file_path = manager.data_dir / "futures" / "um" / "daily" / "klines" / binance_symbol / "1m" / file_name
        
        if file_path.exists():
            file_size = file_path.stat().st_size
            existing_files.append((current_date, file_path, file_size))
            file_count += 1
        else:
            missing_files.append((current_date, file_name))
        
        # 移动到下一天
        try:
            from datetime import timedelta
            current_date = current_date + timedelta(days=1)
        except:
            break
    
    print(f"找到文件: {file_count} 个")
    print(f"缺失文件: {len(missing_files)} 个")
    
    if existing_files:
        print(f"\n存在的文件（前10个）:")
        for d, path, size in existing_files[:10]:
            print(f"  {d}: {path.name} ({size:,} bytes)")
    
    if missing_files:
        print(f"\n缺失的文件（前10个）:")
        for d, name in missing_files[:10]:
            print(f"  {d}: {name}")
    
    return len(existing_files) > 0, missing_files


def check_data_loading():
    """检查数据加载情况"""
    print(f"\n{'='*80}")
    print("2. 检查数据加载情况")
    print(f"{'='*80}")
    
    local_data_provider = LocalBinanceDataProvider()
    start_ts = int(START_DATE.timestamp())
    end_ts = int(END_DATE.timestamp())
    
    print(f"请求时间范围: {START_DATE} 到 {END_DATE}")
    print(f"时间戳范围: {start_ts} 到 {end_ts}")
    print()
    
    # 加载数据
    print("正在加载数据...")
    df = local_data_provider.get_historical_candles(
        symbol=TRADING_PAIR,
        start_ts=start_ts,
        end_ts=end_ts,
        interval=BACKTEST_RESOLUTION
    )
    
    print(f"加载结果: {len(df):,} 条K线")
    
    if df.empty:
        print("  ⚠ 警告: 数据为空！")
        return False, df
    
    # 检查时间范围
    min_ts = df['timestamp'].min()
    max_ts = df['timestamp'].max()
    min_dt = datetime.fromtimestamp(min_ts)
    max_dt = datetime.fromtimestamp(max_ts)
    
    print(f"实际时间范围: {min_dt} 到 {max_dt}")
    print(f"预期时间范围: {START_DATE} 到 {END_DATE}")
    
    if min_ts < start_ts or max_ts > end_ts:
        print(f"  ⚠ 警告: 时间范围超出预期")
    else:
        print(f"  ✓ 时间范围在预期内")
    
    # 检查数据连续性
    print(f"\n检查数据连续性...")
    df_sorted = df.sort_values('timestamp')
    time_diffs = df_sorted['timestamp'].diff().dropna()
    expected_diff = 60  # 1分钟 = 60秒
    
    gaps = time_diffs[time_diffs > expected_diff * 1.5]
    print(f"  总数据点: {len(df_sorted):,}")
    print(f"  时间间隔: {expected_diff} 秒（1分钟）")
    print(f"  发现间隔: {len(gaps)} 个")
    
    if len(gaps) > 0:
        print(f"  ⚠ 警告: 发现 {len(gaps)} 个时间间隔")
        print(f"    最大间隔: {gaps.max() / 60:.1f} 分钟")
        print(f"    平均间隔: {gaps.mean() / 60:.1f} 分钟")
        
        # 显示前5个间隔
        print(f"    前5个间隔位置:")
        for idx in gaps.head(5).index:
            gap_ts = df_sorted.iloc[idx]['timestamp']
            gap_dt = datetime.fromtimestamp(gap_ts)
            gap_size = gaps.loc[idx] / 60
            print(f"      {gap_dt}: {gap_size:.1f} 分钟")
    else:
        print(f"  ✓ 数据连续性良好")
    
    # 检查数据分布
    print(f"\n检查数据分布...")
    df_sorted['date'] = pd.to_datetime(df_sorted['timestamp'], unit='s').dt.date
    daily_counts = df_sorted['date'].value_counts().sort_index()
    
    print(f"  日期范围: {daily_counts.index.min()} 到 {daily_counts.index.max()}")
    print(f"  总天数: {len(daily_counts)} 天")
    print(f"  平均每天: {daily_counts.mean():.0f} 条K线")
    print(f"  预期每天: {24 * 60} 条K线（1分钟数据）")
    
    # 检查缺失的日期
    expected_days = (END_DATE.date() - START_DATE.date()).days + 1
    if len(daily_counts) < expected_days:
        missing_days = expected_days - len(daily_counts)
        print(f"  ⚠ 警告: 缺失 {missing_days} 天的数据")
        print(f"    预期天数: {expected_days}")
        print(f"    实际天数: {len(daily_counts)}")
    
    # 按月统计
    print(f"\n按月统计:")
    df_sorted['month'] = pd.to_datetime(df_sorted['timestamp'], unit='s').dt.to_period('M')
    monthly_counts = df_sorted['month'].value_counts().sort_index()
    for month, count in monthly_counts.items():
        print(f"  {month}: {count:,} 条K线")
    
    return True, df


def check_binance_manager_directly():
    """直接使用BinancePublicDataManager检查"""
    print(f"\n{'='*80}")
    print("3. 直接使用BinancePublicDataManager检查")
    print(f"{'='*80}")
    
    from src.data.sources.binance_public_data_manager import BinancePublicDataManager
    
    manager = BinancePublicDataManager()
    binance_symbol = TRADING_PAIR.replace('-', '')
    start_date = START_DATE.date()
    end_date = END_DATE.date()
    
    print(f"直接调用 get_klines_data...")
    print(f"  交易对: {binance_symbol}")
    print(f"  日期范围: {start_date} 到 {end_date}")
    
    try:
        df = manager.get_klines_data(
            symbol=binance_symbol,
            start_date=start_date,
            end_date=end_date,
            check_gaps=False
        )
        
        print(f"  结果: {len(df):,} 条K线")
        
        if df.empty:
            print(f"  ⚠ 警告: 返回空DataFrame")
        else:
            print(f"  ✓ 成功加载数据")
            print(f"    时间范围: {df.index.min()} 到 {df.index.max()}")
            print(f"    列: {list(df.columns)}")
        
        return df
    except Exception as e:
        print(f"  ✗ 错误: {str(e)}")
        import traceback
        traceback.print_exc()
        return pd.DataFrame()


def main():
    """主函数"""
    print("="*80)
    print("数据加载诊断")
    print("="*80)
    print(f"交易对: {TRADING_PAIR}")
    print(f"时间范围: {START_DATE.strftime('%Y-%m-%d')} 到 {END_DATE.strftime('%Y-%m-%d')}")
    print(f"分辨率: {BACKTEST_RESOLUTION}")
    print()
    
    # 1. 检查文件是否存在
    files_exist, missing_files = check_data_files_exist()
    
    # 2. 检查数据加载
    load_success, df = check_data_loading()
    
    # 3. 直接使用BinancePublicDataManager
    df_direct = check_binance_manager_directly()
    
    # 总结
    print(f"\n{'='*80}")
    print("诊断总结")
    print(f"{'='*80}")
    print(f"文件存在: {'✓' if files_exist else '✗'}")
    print(f"数据加载: {'✓' if load_success else '✗'}")
    print(f"加载数据量: {len(df):,} 条K线")
    print(f"直接加载: {len(df_direct):,} 条K线")
    
    if not files_exist:
        print(f"\n⚠ 问题: 数据文件不存在或缺失")
        print(f"  缺失文件数: {len(missing_files)}")
    elif not load_success or len(df) == 0:
        print(f"\n⚠ 问题: 数据加载失败或返回空数据")
    elif len(df) < 100000:  # 4个月应该有约17万条1分钟数据
        print(f"\n⚠ 警告: 数据量可能不足")
        print(f"  预期: ~172,800 条（4个月 * 30天 * 24小时 * 60分钟）")
        print(f"  实际: {len(df):,} 条")
    else:
        print(f"\n✓ 数据加载正常")


if __name__ == "__main__":
    main()

