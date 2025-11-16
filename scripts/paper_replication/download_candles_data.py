"""
数据下载脚本 - 复现论文实验

从Binance下载历史K线数据，用于回测论文中的策略
论文："Market Making in Crypto" by Stoikov et al. (2024)

数据要求：
- 30个加密货币
- 1分钟K线数据
- 2024年9月1日至10月14日（45天）
- 约60,000个数据点每个币
"""

import asyncio
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import List

import pandas as pd
from hummingbot.data_feed.candles_feed.binance_spot_candles import BinanceSpotCandles
from hummingbot.data_feed.candles_feed.binance_perpetual_candles import BinancePerpetualCandles
from hummingbot.data_feed.candles_feed.data_types import CandlesConfig


# 论文中使用的30个加密货币（按类别）
TRADING_PAIRS = {
    # Layer-1 Protocols (红色)
    "layer1": ["BTC-USDT", "ETH-USDT", "SOL-USDT", "ICP-USDT", "AVAX-USDT", 
               "DOT-USDT", "NEAR-USDT", "TRX-USDT", "TON-USDT"],
    
    # Meme Coins (橙色)
    "meme": ["DOGE-USDT", "SHIB-USDT", "PEPE-USDT", "BONK-USDT", "FLOKI-USDT"],
    
    # DeFi (紫色)
    "defi": ["UNI-USDT", "AAVE-USDT", "MKR-USDT", "OP-USDT", "DYDX-USDT", 
             "GALA-USDT", "ARB-USDT"],
    
    # Utility Tokens (绿色)
    "utility": ["LINK-USDT", "MATIC-USDT", "VET-USDT", "FIL-USDT", 
                "KAS-USDT", "ORDI-USDT", "XRP-USDT", "ADA-USDT", "LTC-USDT"]
}

# 论文中特别测试的三个币
PAPER_TEST_PAIRS = ["SOL-USDT", "DOGE-USDT", "GALA-USDT"]

# 用户指定的交易对（最近半年回测）
CUSTOM_TEST_PAIRS = ["BTC-USDT", "SOL-USDT", "ETH-USDT", "XRP-USDT", "AVAX-USDT", "DOT-USDT", "MYX-USDT"]

# 数据时间范围（论文使用2024年9月1日至10月14日）
START_DATE = datetime(2024, 9, 1)
END_DATE = datetime(2024, 10, 14)

# 最近半年的数据时间范围（用于自定义回测）
def get_last_6_months_range():
    """获取最近6个月的时间范围"""
    end_date = datetime.now()
    start_date = end_date - timedelta(days=180)  # 约6个月
    return start_date, end_date

# 数据存储路径（使用项目根目录）
def get_data_dir():
    """获取数据存储目录"""
    # 尝试使用 /workspace（Docker环境）
    workspace_dir = Path("/workspace/data/paper_replication")
    if workspace_dir.parent.parent.exists():
        return workspace_dir
    
    # 使用项目根目录下的 data 目录
    project_root = Path(__file__).parent.parent.parent
    data_dir = project_root / "data" / "paper_replication"
    return data_dir

DATA_DIR = get_data_dir()


def get_all_pairs() -> List[str]:
    """获取所有交易对列表"""
    all_pairs = []
    for category_pairs in TRADING_PAIRS.values():
        all_pairs.extend(category_pairs)
    return all_pairs


async def download_candles_for_pair(
    pair: str,
    interval: str = "1m",
    start_date: datetime = START_DATE,
    end_date: datetime = END_DATE,
    use_perpetual: bool = True
) -> pd.DataFrame:
    """
    下载指定交易对的K线数据
    
    Args:
        pair: 交易对（例如 "BTC-USDT"）
        interval: K线间隔（默认"1m"）
        start_date: 开始日期
        end_date: 结束日期
        use_perpetual: 是否使用永续合约（默认True，论文使用永续合约）
        
    Returns:
        pd.DataFrame: K线数据
    """
    print(f"开始下载 {pair} 的 {interval} K线数据...")
    
    # 创建K线配置
    config = CandlesConfig(
        connector="binance_perpetual" if use_perpetual else "binance",
        trading_pair=pair,
        interval=interval,
        max_records=100000  # 确保能获取足够的历史数据
    )
    
    # 创建数据源
    if use_perpetual:
        candles_feed = BinancePerpetualCandles()
    else:
        candles_feed = BinanceSpotCandles()
    
    try:
        # 计算需要的时间戳
        start_timestamp = int(start_date.timestamp() * 1000)
        end_timestamp = int(end_date.timestamp() * 1000)
        
        # 下载数据
        candles_df = await candles_feed.fetch_candles(
            config=config,
            start=start_timestamp,
            end=end_timestamp
        )
        
        if candles_df is not None and len(candles_df) > 0:
            print(f"✓ {pair}: 下载了 {len(candles_df)} 条数据")
            return candles_df
        else:
            print(f"✗ {pair}: 未获取到数据")
            return pd.DataFrame()
            
    except Exception as e:
        print(f"✗ {pair}: 下载失败 - {str(e)}")
        return pd.DataFrame()


async def download_all_candles(
    pairs: List[str] = None,
    interval: str = "1m",
    save_to_disk: bool = True
) -> dict:
    """
    下载所有交易对的K线数据
    
    Args:
        pairs: 交易对列表（None则下载所有）
        interval: K线间隔
        save_to_disk: 是否保存到磁盘
        
    Returns:
        dict: {pair: DataFrame}
    """
    if pairs is None:
        pairs = get_all_pairs()
    
    print(f"\n开始下载 {len(pairs)} 个交易对的数据...")
    print(f"时间范围: {START_DATE.date()} 至 {END_DATE.date()}")
    print(f"K线间隔: {interval}\n")
    
    results = {}
    
    # 逐个下载（避免并发过多导致限流）
    for pair in pairs:
        df = await download_candles_for_pair(pair, interval)
        if len(df) > 0:
            results[pair] = df
        
        # 短暂延迟避免限流
        await asyncio.sleep(0.5)
    
    # 保存数据
    if save_to_disk and len(results) > 0:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        
        for pair, df in results.items():
            filename = f"{pair.replace('-', '_')}_{interval}_{START_DATE.strftime('%Y%m%d')}_{END_DATE.strftime('%Y%m%d')}.csv"
            filepath = DATA_DIR / filename
            
            df.to_csv(filepath, index=False)
            print(f"保存: {filepath}")
    
    print(f"\n完成! 成功下载 {len(results)}/{len(pairs)} 个交易对的数据")
    return results


async def download_paper_test_pairs():
    """下载论文中特别测试的三个交易对"""
    print("=" * 60)
    print("下载论文测试交易对: SOL-USDT, DOGE-USDT, GALA-USDT")
    print("=" * 60)
    
    results = await download_all_candles(pairs=PAPER_TEST_PAIRS)
    return results


async def download_custom_pairs_last_6_months():
    """下载用户指定的交易对最近6个月的数据"""
    print("=" * 60)
    print(f"下载自定义交易对最近6个月数据: {', '.join(CUSTOM_TEST_PAIRS)}")
    print("=" * 60)
    
    start_date, end_date = get_last_6_months_range()
    print(f"时间范围: {start_date.date()} 至 {end_date.date()}")
    
    # 临时修改全局时间范围
    global START_DATE, END_DATE
    original_start = START_DATE
    original_end = END_DATE
    START_DATE = start_date
    END_DATE = end_date
    
    try:
        results = await download_all_candles(pairs=CUSTOM_TEST_PAIRS)
        return results
    finally:
        # 恢复原始时间范围
        START_DATE = original_start
        END_DATE = original_end


async def download_by_category(category: str):
    """按类别下载数据"""
    if category not in TRADING_PAIRS:
        print(f"错误: 未知类别 '{category}'")
        print(f"可用类别: {list(TRADING_PAIRS.keys())}")
        return
    
    pairs = TRADING_PAIRS[category]
    print(f"下载 {category} 类别的 {len(pairs)} 个交易对")
    return await download_all_candles(pairs=pairs)


def load_downloaded_data(pair: str, interval: str = "1m") -> pd.DataFrame:
    """
    加载已下载的数据
    
    Args:
        pair: 交易对
        interval: K线间隔
        
    Returns:
        pd.DataFrame: K线数据
    """
    filename = f"{pair.replace('-', '_')}_{interval}_{START_DATE.strftime('%Y%m%d')}_{END_DATE.strftime('%Y%m%d')}.csv"
    filepath = DATA_DIR / filename
    
    if not filepath.exists():
        raise FileNotFoundError(f"数据文件不存在: {filepath}")
    
    df = pd.read_csv(filepath)
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    return df


def get_data_summary():
    """获取已下载数据的摘要"""
    if not DATA_DIR.exists():
        print("数据目录不存在")
        return
    
    csv_files = list(DATA_DIR.glob("*.csv"))
    
    if len(csv_files) == 0:
        print("没有找到数据文件")
        return
    
    print(f"\n数据摘要:")
    print(f"数据目录: {DATA_DIR}")
    print(f"文件数量: {len(csv_files)}")
    
    total_size = sum(f.stat().st_size for f in csv_files) / (1024 * 1024)
    print(f"总大小: {total_size:.2f} MB")
    
    print("\n文件列表:")
    for f in sorted(csv_files):
        size_mb = f.stat().st_size / (1024 * 1024)
        
        # 读取行数
        try:
            df = pd.read_csv(f)
            rows = len(df)
            print(f"  {f.name}: {rows:,} 行, {size_mb:.2f} MB")
        except Exception as e:
            print(f"  {f.name}: 读取失败 - {e}")


async def main():
    """主函数"""
    import sys
    
    if len(sys.argv) > 1:
        command = sys.argv[1]
        
        if command == "test":
            # 下载测试交易对
            await download_paper_test_pairs()
        elif command == "custom" or command == "6months":
            # 下载自定义交易对最近6个月数据
            await download_custom_pairs_last_6_months()
        elif command == "all":
            # 下载所有交易对
            await download_all_candles()
        elif command in TRADING_PAIRS:
            # 按类别下载
            await download_by_category(command)
        elif command == "summary":
            # 显示摘要
            get_data_summary()
        else:
            print(f"未知命令: {command}")
            print("可用命令: test, custom/6months, all, layer1, meme, defi, utility, summary")
    else:
        # 默认下载测试交易对
        await download_paper_test_pairs()


if __name__ == "__main__":
    asyncio.run(main())
