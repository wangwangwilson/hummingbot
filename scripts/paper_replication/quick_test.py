#!/usr/bin/env python3
"""
快速测试脚本 - 验证实现

快速测试策略实现是否正常工作
不需要下载大量数据，使用小规模数据进行验证
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime, timedelta
from decimal import Decimal

import pandas as pd
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from controllers.market_making.pmm_bar_portion import (
    PMMBarPortionController,
    PMMBarPortionControllerConfig
)
from controllers.market_making.pmm_dynamic import (
    PMMDynamicController,
    PMMDynamicControllerConfig
)


def test_bar_portion_calculation():
    """测试Bar Portion计算"""
    print("\n测试1: Bar Portion计算")
    print("-" * 60)
    
    # 创建测试数据
    test_data = pd.DataFrame({
        'open': [100, 101, 102, 103, 104],
        'high': [105, 106, 107, 108, 109],
        'low': [99, 100, 101, 102, 103],
        'close': [102, 103, 104, 105, 106]
    })
    
    # 创建控制器实例
    config = PMMBarPortionControllerConfig(
        connector_name="binance_perpetual",
        trading_pair="BTC-USDT",
        candles_connector="binance_perpetual",
        candles_trading_pair="BTC-USDT",
    )
    
    controller = PMMBarPortionController(config)
    
    # 计算Bar Portion
    bar_portion = controller.calculate_bar_portion(test_data)
    
    print(f"测试数据形状: {test_data.shape}")
    print(f"\nBar Portion结果:")
    for i, (idx, row) in enumerate(test_data.iterrows()):
        bp = bar_portion.iloc[i]
        print(f"  Candle {i+1}: Open={row['open']:.2f}, High={row['high']:.2f}, "
              f"Low={row['low']:.2f}, Close={row['close']:.2f} => BP={bp:.4f}")
    
    # 验证范围
    assert bar_portion.min() >= -1 and bar_portion.max() <= 1, "Bar Portion应在[-1, 1]范围内"
    
    # 验证计算
    expected_bp_0 = (102 - 100) / (105 - 99)
    assert abs(bar_portion.iloc[0] - expected_bp_0) < 0.001, "Bar Portion计算错误"
    
    print(f"\n✓ Bar Portion计算正确")
    print(f"  - 范围检查通过: [{bar_portion.min():.4f}, {bar_portion.max():.4f}]")
    print(f"  - 公式验证通过")


def test_stick_length_calculation():
    """测试Stick Length计算"""
    print("\n测试2: Stick Length计算")
    print("-" * 60)
    
    # 创建测试数据
    test_data = pd.DataFrame({
        'open': [100] * 20,
        'high': [105, 110, 108, 106, 112] * 4,
        'low': [95, 92, 94, 96, 90] * 4,
        'close': [102, 105, 103, 104, 106] * 4
    })
    
    config = PMMBarPortionControllerConfig(
        connector_name="binance_perpetual",
        trading_pair="BTC-USDT",
        atr_length=10
    )
    
    controller = PMMBarPortionController(config)
    
    # 计算Stick Length
    stick_length = controller.calculate_stick_length(test_data, atr_length=10)
    
    print(f"测试数据形状: {test_data.shape}")
    print(f"Stick Length统计:")
    print(f"  - 均值: {stick_length.mean():.4f}")
    print(f"  - 标准差: {stick_length.std():.4f}")
    print(f"  - 最小值: {stick_length.min():.4f}")
    print(f"  - 最大值: {stick_length.max():.4f}")
    
    print(f"\n✓ Stick Length计算完成")


def test_linear_regression():
    """测试线性回归"""
    print("\n测试3: 线性回归")
    print("-" * 60)
    
    # 创建测试数据（有明显线性关系）
    np.random.seed(42)
    X = pd.Series(np.random.randn(1000) * 0.5)
    y = pd.Series(-0.8 * X + 0.01 + np.random.randn(1000) * 0.02)
    
    config = PMMBarPortionControllerConfig(
        connector_name="binance_perpetual",
        trading_pair="BTC-USDT"
    )
    
    controller = PMMBarPortionController(config)
    
    # 拟合回归
    controller.fit_linear_regression(X, y)
    
    print(f"训练样本数: {len(X)}")
    print(f"回归系数: {controller._regression_coef:.6f}")
    print(f"回归截距: {controller._regression_intercept:.6f}")
    
    # 测试预测
    test_bp = 0.5
    predicted_return = controller.predict_price_shift(test_bp)
    print(f"\n预测测试:")
    print(f"  - 输入BP: {test_bp}")
    print(f"  - 预测价格变化: {predicted_return:.6f} ({predicted_return*100:.4f}%)")
    
    # 验证系数符号（论文中BP与收益负相关）
    assert controller._regression_coef < 0, "预期回归系数为负（均值回归）"
    
    print(f"\n✓ 线性回归测试通过")
    print(f"  - 系数符号正确（负相关）")


def test_config_creation():
    """测试配置创建"""
    print("\n测试4: 策略配置创建")
    print("-" * 60)
    
    # 测试BP配置
    bp_config = PMMBarPortionControllerConfig(
        connector_name="binance_perpetual",
        trading_pair="SOL-USDT",
        interval="1m",
        buy_spreads=[0.01, 0.02],
        sell_spreads=[0.01, 0.02],
        stop_loss=Decimal("0.03"),
        take_profit=Decimal("0.02"),
        time_limit=2700,
        leverage=20
    )
    
    print("PMM Bar Portion配置:")
    print(f"  - 交易对: {bp_config.trading_pair}")
    print(f"  - K线间隔: {bp_config.interval}")
    print(f"  - 买入Spread: {bp_config.buy_spreads}")
    print(f"  - 卖出Spread: {bp_config.sell_spreads}")
    print(f"  - 止损: {bp_config.stop_loss}")
    print(f"  - 止盈: {bp_config.take_profit}")
    print(f"  - 时间限制: {bp_config.time_limit}秒")
    print(f"  - 杠杆: {bp_config.leverage}x")
    
    # 测试MACD配置
    macd_config = PMMDynamicControllerConfig(
        connector_name="binance_perpetual",
        trading_pair="SOL-USDT",
        interval="1m",
        buy_spreads=[1.0, 2.0, 4.0],
        sell_spreads=[1.0, 2.0, 4.0],
        macd_fast=21,
        macd_slow=42,
        macd_signal=9,
        natr_length=14
    )
    
    print("\nPMM Dynamic (MACD)配置:")
    print(f"  - 交易对: {macd_config.trading_pair}")
    print(f"  - MACD快线: {macd_config.macd_fast}")
    print(f"  - MACD慢线: {macd_config.macd_slow}")
    print(f"  - MACD信号: {macd_config.macd_signal}")
    print(f"  - NATR长度: {macd_config.natr_length}")
    
    print(f"\n✓ 配置创建测试通过")


def test_metrics_calculation():
    """测试性能指标计算"""
    print("\n测试5: 性能指标计算")
    print("-" * 60)
    
    # 创建模拟交易数据
    np.random.seed(42)
    trades = []
    for i in range(100):
        pnl = np.random.randn() * 0.5 + 0.1  # 轻微正向偏差
        trades.append({
            'pnl': pnl,
            'timestamp': i * 1000,
            'side': 'BUY' if i % 2 == 0 else 'SELL',
            'close_type': 'TAKE_PROFIT' if pnl > 0 else 'STOP_LOSS'
        })
    
    trades_df = pd.DataFrame(trades)
    
    # 计算指标
    initial_capital = 1000
    trades_df['cumulative_pnl'] = trades_df['pnl'].cumsum()
    trades_df['portfolio_value'] = initial_capital + trades_df['cumulative_pnl']
    
    # 收益
    total_pnl = trades_df['pnl'].sum()
    total_return_pct = (total_pnl / initial_capital) * 100
    
    # Sharpe比率
    returns = trades_df['portfolio_value'].pct_change().dropna()
    sharpe_ratio = (returns.mean() / returns.std()) * np.sqrt(len(trades_df)) if returns.std() != 0 else 0
    
    # 最大回撤
    portfolio_values = trades_df['portfolio_value'].values
    running_max = np.maximum.accumulate(portfolio_values)
    drawdowns = (portfolio_values - running_max) / running_max
    max_drawdown_pct = abs(drawdowns.min()) * 100
    
    # 胜率
    winning_trades = len(trades_df[trades_df['pnl'] > 0])
    win_rate = (winning_trades / len(trades_df)) * 100
    
    print(f"模拟交易数: {len(trades_df)}")
    print(f"\n性能指标:")
    print(f"  - 总收益: ${total_pnl:.2f} ({total_return_pct:.2f}%)")
    print(f"  - Sharpe比率: {sharpe_ratio:.4f}")
    print(f"  - 最大回撤: {max_drawdown_pct:.2f}%")
    print(f"  - 胜率: {win_rate:.2f}%")
    print(f"  - 获胜交易: {winning_trades}/{len(trades_df)}")
    
    print(f"\n✓ 指标计算测试通过")


def run_all_tests():
    """运行所有测试"""
    print("\n" + "="*60)
    print("论文复现 - 快速测试")
    print("="*60)
    
    tests = [
        test_bar_portion_calculation,
        test_stick_length_calculation,
        test_linear_regression,
        test_config_creation,
        test_metrics_calculation,
    ]
    
    passed = 0
    failed = 0
    
    for test_func in tests:
        try:
            test_func()
            passed += 1
        except Exception as e:
            failed += 1
            print(f"\n✗ 测试失败: {test_func.__name__}")
            print(f"  错误: {str(e)}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "="*60)
    print(f"测试总结: {passed}通过, {failed}失败")
    print("="*60)
    
    if failed == 0:
        print("\n✓ 所有测试通过！实现验证成功。")
        print("  可以运行完整实验: python run_full_experiment.py")
    else:
        print(f"\n✗ {failed}个测试失败，请检查实现。")
    
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
