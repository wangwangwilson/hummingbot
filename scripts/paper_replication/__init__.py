"""
论文复现包 - Market Making in Crypto

复现Stoikov et al. (2024)论文中的策略和实验
"""

__version__ = "1.0.0"
__author__ = "Hummingbot Community"
__paper__ = "Market Making in Crypto by Stoikov et al. (2024)"

from .download_candles_data import (
    download_candles_for_pair,
    download_all_candles,
    download_paper_test_pairs,
    get_data_summary,
    load_downloaded_data,
    TRADING_PAIRS,
    PAPER_TEST_PAIRS,
)

from .backtest_comparison import (
    StrategyBacktester,
    PerformanceAnalyzer,
    run_single_pair_comparison,
    run_full_comparison,
)

from .visualize_results import (
    ResultsVisualizer,
)

__all__ = [
    # 数据下载
    'download_candles_for_pair',
    'download_all_candles',
    'download_paper_test_pairs',
    'get_data_summary',
    'load_downloaded_data',
    'TRADING_PAIRS',
    'PAPER_TEST_PAIRS',
    
    # 回测
    'StrategyBacktester',
    'PerformanceAnalyzer',
    'run_single_pair_comparison',
    'run_full_comparison',
    
    # 可视化
    'ResultsVisualizer',
]
