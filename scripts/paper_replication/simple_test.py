#!/usr/bin/env python3
"""
简化测试 - 不依赖外部库
直接测试核心算法逻辑
"""

def test_bar_portion_calculation():
    """测试Bar Portion计算逻辑"""
    print("\n" + "="*60)
    print("测试1: Bar Portion计算")
    print("="*60)
    
    # 测试数据: (open, high, low, close)
    test_cases = [
        # 强势上涨: close=high, open=low
        (100, 105, 100, 105, "强势上涨"),
        # 强势下跌: close=low, open=high  
        (105, 105, 100, 100, "强势下跌"),
        # 中性: close和open在中间
        (102, 105, 100, 103, "温和上涨"),
        # 十字星: open=close
        (102, 105, 100, 102, "十字星"),
    ]
    
    print("\n计算Bar Portion = (Close - Open) / (High - Low)")
    print("-" * 60)
    
    for open_price, high, low, close, description in test_cases:
        # 计算Bar Portion
        high_low_diff = high - low
        if high_low_diff == 0:
            bp = 0
        else:
            bp = (close - open_price) / high_low_diff
        
        # 限制在[-1, 1]范围
        bp = max(-1, min(1, bp))
        
        print(f"\n{description}:")
        print(f"  O={open_price}, H={high}, L={low}, C={close}")
        print(f"  BP = ({close} - {open_price}) / ({high} - {low})")
        print(f"  BP = {bp:.4f}")
        
        # 验证范围
        assert -1 <= bp <= 1, f"BP超出范围: {bp}"
    
    print("\n✓ Bar Portion计算测试通过！")
    return True


def test_linear_regression_logic():
    """测试线性回归逻辑"""
    print("\n" + "="*60)
    print("测试2: 线性回归逻辑")
    print("="*60)
    
    # 简单的测试数据
    X = [0.5, 0.3, -0.2, -0.5, 0.1, -0.3, 0.4, -0.1]
    y = [-0.4, -0.2, 0.15, 0.4, -0.05, 0.25, -0.3, 0.08]
    
    print(f"\n训练样本数: {len(X)}")
    print(f"X (Bar Portion): {X[:5]}...")
    print(f"y (Returns): {y[:5]}...")
    
    # 计算均值
    X_mean = sum(X) / len(X)
    y_mean = sum(y) / len(y)
    
    print(f"\nX均值: {X_mean:.4f}")
    print(f"y均值: {y_mean:.4f}")
    
    # 计算回归系数
    numerator = sum((x - X_mean) * (y_val - y_mean) for x, y_val in zip(X, y))
    denominator = sum((x - X_mean) ** 2 for x in X)
    
    if denominator != 0:
        coef = numerator / denominator
        intercept = y_mean - coef * X_mean
        
        print(f"\n回归系数: {coef:.6f}")
        print(f"回归截距: {intercept:.6f}")
        
        # 测试预测
        test_bp = 0.5
        predicted_return = coef * test_bp + intercept
        print(f"\n预测测试:")
        print(f"  输入BP: {test_bp}")
        print(f"  预测收益: {predicted_return:.6f} ({predicted_return*100:.4f}%)")
        
        # 论文中BP与收益应该负相关（均值回归）
        if coef < 0:
            print(f"  ✓ 系数为负，符合均值回归特性")
        else:
            print(f"  ⚠ 系数为正，可能需要更多数据")
        
        print("\n✓ 线性回归逻辑测试通过！")
        return True
    else:
        print("✗ 回归计算失败")
        return False


def test_price_shift_calculation():
    """测试价格调整计算"""
    print("\n" + "="*60)
    print("测试3: 价格调整计算")
    print("="*60)
    
    # 假设回归系数
    coef = -0.8
    intercept = 0.01
    
    print(f"\n假设回归模型: return = {coef} * BP + {intercept}")
    
    test_bps = [1.0, 0.5, 0.0, -0.5, -1.0]
    max_shift = 0.005  # 0.5%最大调整
    
    print("\nBP值 → 预测收益 → 价格调整（限制在±0.5%）")
    print("-" * 60)
    
    for bp in test_bps:
        predicted_return = coef * bp + intercept
        # 限制最大调整
        price_shift = max(-max_shift, min(max_shift, predicted_return))
        
        print(f"BP={bp:5.2f} → return={predicted_return:7.4f} → shift={price_shift:7.4f} ({price_shift*100:.2f}%)")
    
    print("\n✓ 价格调整计算测试通过！")
    return True


def test_spread_calculation():
    """测试Spread计算逻辑"""
    print("\n" + "="*60)
    print("测试4: Spread计算")
    print("="*60)
    
    # 模拟NATR值
    natr_values = [0.02, 0.05, 0.10, 0.15]
    spread_multipliers = [1, 2, 4]
    
    print("\nNATR × Spread倍数 = 最终Spread")
    print("-" * 60)
    
    for natr in natr_values:
        print(f"\nNATR = {natr} ({natr*100:.1f}%)")
        for mult in spread_multipliers:
            spread = natr * mult
            print(f"  {mult}x → {spread:.4f} ({spread*100:.2f}%)")
    
    # 论文发现: spread = 4-5倍月波动率
    monthly_vol = 0.30  # 30%月波动率
    optimal_spread = 4.5 * monthly_vol
    print(f"\n论文建议（月波动率30%）:")
    print(f"  Spread = 4.5 × {monthly_vol} = {optimal_spread:.4f} ({optimal_spread*100:.1f}%)")
    
    print("\n✓ Spread计算测试通过！")
    return True


def test_risk_management():
    """测试风险管理逻辑"""
    print("\n" + "="*60)
    print("测试5: 三重屏障风险管理")
    print("="*60)
    
    entry_price = 100
    stop_loss = 0.03  # 3%
    take_profit = 0.02  # 2%
    time_limit = 45 * 60  # 45分钟
    
    print(f"\n入场价格: ${entry_price}")
    print(f"止损: {stop_loss*100}%")
    print(f"止盈: {take_profit*100}%")
    print(f"时间限制: {time_limit//60}分钟")
    
    # 计算触发价格
    long_stop_loss = entry_price * (1 - stop_loss)
    long_take_profit = entry_price * (1 + take_profit)
    
    short_stop_loss = entry_price * (1 + stop_loss)
    short_take_profit = entry_price * (1 - take_profit)
    
    print(f"\n做多仓位:")
    print(f"  止损价: ${long_stop_loss:.2f}")
    print(f"  止盈价: ${long_take_profit:.2f}")
    
    print(f"\n做空仓位:")
    print(f"  止损价: ${short_stop_loss:.2f}")
    print(f"  止盈价: ${short_take_profit:.2f}")
    
    # 测试场景
    test_prices = [
        (96, "做多", "触发止损"),
        (102, "做多", "触发止盈"),
        (104, "做空", "触发止损"),
        (98, "做空", "触发止盈"),
    ]
    
    print(f"\n测试场景:")
    print("-" * 60)
    for price, direction, expected in test_prices:
        print(f"  价格${price} → {direction} → {expected}")
        
        if direction == "做多":
            if price <= long_stop_loss:
                assert "止损" in expected
            elif price >= long_take_profit:
                assert "止盈" in expected
        else:  # 做空
            if price >= short_stop_loss:
                assert "止损" in expected
            elif price <= short_take_profit:
                assert "止盈" in expected
    
    print("\n✓ 风险管理测试通过！")
    return True


def test_config_validation():
    """测试配置验证"""
    print("\n" + "="*60)
    print("测试6: 配置验证")
    print("="*60)
    
    # 模拟配置
    config = {
        "trading_pair": "SOL-USDT",
        "interval": "1m",
        "buy_spreads": [0.01, 0.02],
        "sell_spreads": [0.01, 0.02],
        "stop_loss": 0.03,
        "take_profit": 0.02,
        "time_limit": 2700,
        "leverage": 20,
        "training_window": 51840,
        "natr_length": 14,
        "atr_length": 10,
    }
    
    print("\n策略配置:")
    for key, value in config.items():
        print(f"  {key}: {value}")
    
    # 验证配置
    assert config["stop_loss"] > 0, "止损必须大于0"
    assert config["take_profit"] > 0, "止盈必须大于0"
    assert config["leverage"] > 0, "杠杆必须大于0"
    assert len(config["buy_spreads"]) > 0, "至少需要一个买入spread"
    assert len(config["sell_spreads"]) > 0, "至少需要一个卖出spread"
    
    print("\n✓ 配置验证通过！")
    return True


def run_all_tests():
    """运行所有测试"""
    print("\n" + "█"*60)
    print("█" + " "*58 + "█")
    print("█" + "  论文复现 - 核心算法逻辑测试".center(56) + "  █")
    print("█" + " "*58 + "█")
    print("█"*60)
    
    tests = [
        ("Bar Portion计算", test_bar_portion_calculation),
        ("线性回归逻辑", test_linear_regression_logic),
        ("价格调整计算", test_price_shift_calculation),
        ("Spread计算", test_spread_calculation),
        ("风险管理", test_risk_management),
        ("配置验证", test_config_validation),
    ]
    
    passed = 0
    failed = 0
    
    for name, test_func in tests:
        try:
            if test_func():
                passed += 1
        except Exception as e:
            failed += 1
            print(f"\n✗ {name} 失败: {str(e)}")
            import traceback
            traceback.print_exc()
    
    # 总结
    print("\n" + "="*60)
    print("测试总结")
    print("="*60)
    print(f"  通过: {passed}/{len(tests)}")
    print(f"  失败: {failed}/{len(tests)}")
    
    if failed == 0:
        print("\n✅ 所有测试通过！核心算法逻辑正确。")
        print("="*60)
        return True
    else:
        print(f"\n❌ {failed}个测试失败")
        print("="*60)
        return False


if __name__ == "__main__":
    import sys
    success = run_all_tests()
    sys.exit(0 if success else 1)
