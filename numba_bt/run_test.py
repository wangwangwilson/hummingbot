#!/usr/bin/env python3
"""快速测试脚本"""
import sys
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from tests.test_backtest import test_single_exchange_backtest

if __name__ == "__main__":
    print("开始运行回测框架测试...")
    success = test_single_exchange_backtest()
    if success:
        print("\n✅ 所有测试通过！")
        sys.exit(0)
    else:
        print("\n❌ 测试失败")
        sys.exit(1)

