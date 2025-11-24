"""测试加载资金费率数据"""
import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone

# 添加项目根目录到路径（使用绝对路径）
project_root = Path(__file__).parent.parent.absolute()
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# 确保bigdata_plan在路径中
bigdata_plan_path = Path("/home/wilson/bigdata_plan")
if str(bigdata_plan_path) not in sys.path:
    sys.path.insert(0, str(bigdata_plan_path))

# 直接导入（在项目根目录下运行）
from src.data.preparer import DataPreparer


def test_load_funding_rate():
    """测试加载资金费率数据"""
    print("=" * 70)
    print("测试加载资金费率数据")
    print("=" * 70)
    
    # 配置参数
    symbol = "AXSUSDT"
    days = 10
    
    # 计算时间范围
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=days)
    
    print(f"\n配置参数:")
    print(f"  交易对: {symbol}")
    print(f"  时间范围: {start_date.strftime('%Y-%m-%d')} 到 {end_date.strftime('%Y-%m-%d')}")
    print(f"  天数: {days} 天")
    
    # 创建DataPreparer
    print(f"\n创建DataPreparer...")
    preparer = DataPreparer()
    
    print(f"  FundingRateReader可用: {preparer.funding_reader is not None}")
    
    if preparer.funding_reader is None:
        print(f"\n  ❌ FundingRateReader未可用，无法加载资金费率数据")
        print(f"  请检查bigdata_plan项目路径和依赖")
        return
    
    # 读取资金费率数据
    print(f"\n读取资金费率数据...")
    try:
        funding_data = preparer.prepare_funding_rate(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date
        )
        
        print(f"\n结果:")
        print(f"  数据shape: {funding_data.shape}")
        print(f"  记录数量: {len(funding_data)}")
        
        if len(funding_data) > 0:
            start_ts = int(funding_data[0, 0])
            end_ts = int(funding_data[-1, 0])
            start_dt = datetime.fromtimestamp(start_ts / 1000, tz=timezone.utc)
            end_dt = datetime.fromtimestamp(end_ts / 1000, tz=timezone.utc)
            
            print(f"  时间范围: {start_dt.strftime('%Y-%m-%d %H:%M:%S')} 到 {end_dt.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"  费率范围: {funding_data[:, 1].min():.8f} 到 {funding_data[:, 1].max():.8f}")
            print(f"  平均费率: {funding_data[:, 1].mean():.8f}")
            
            # 显示前几条数据
            print(f"\n前5条数据:")
            for i in range(min(5, len(funding_data))):
                ts = int(funding_data[i, 0])
                rate = funding_data[i, 1]
                dt = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
                print(f"  {i+1}. {dt.strftime('%Y-%m-%d %H:%M:%S')}: {rate:.8f}")
        else:
            print(f"  ⚠️  未加载到资金费率数据")
            
    except Exception as e:
        print(f"  ❌ 加载资金费率数据失败: {e}")
        import traceback
        traceback.print_exc()
    
    print(f"\n" + "=" * 70)
    print("测试完成")
    print("=" * 70)


if __name__ == "__main__":
    test_load_funding_rate()

