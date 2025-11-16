# Comprehensive Backtest Comparison - Status Report

## Overview

A comprehensive backtest comparison script has been created to compare three market-making strategies:
1. **PMM Simple** - Classic market-making strategy with fixed spreads
2. **PMM Dynamic (MACD)** - Market-making strategy using MACD indicator for dynamic spread adjustment
3. **PMM Bar Portion** - Market-making strategy using Bar Portion (BP) alpha signal

## Configuration

### Trading Pairs
- BTC-USDT, ETH-USDT, SOL-USDT, XRP-USDT, PEPE-USDT, ASTER-USDT, MYX-USDT, PUMP-USDT, XPL-USDT, OM-USDT, TRX-USDT, UMA-USDT

### Time Range
- **Start**: 2025-03-01
- **End**: 2025-11-09
- **Duration**: ~8.3 months

### Backtest Parameters
- **Resolution**: 15 minutes (aggregated from 1-minute data)
- **Initial Portfolio**: $10,000 per trading pair
- **Trading Fee**: 0.04% (0.0004)
- **Total Tasks**: 36 (12 pairs × 3 strategies)

## Strategy Parameters

### PMM Simple
- **Buy Spreads**: [0.5%, 1%, 2%]
- **Sell Spreads**: [0.5%, 1%, 2%]
- **Stop Loss**: 1%
- **Take Profit**: 0.5%
- **Time Limit**: 1 hour

### PMM Dynamic (MACD)
- **Buy Spreads**: [1%, 2%, 4%] (in volatility units)
- **Sell Spreads**: [1%, 2%, 4%] (in volatility units)
- **Stop Loss**: 1%
- **Take Profit**: 0.5%
- **Time Limit**: 1 hour

### PMM Bar Portion
- **Buy Spreads**: [1%, 2%] (in volatility units)
- **Sell Spreads**: [1%, 2%] (in volatility units)
- **Stop Loss**: 1%
- **Take Profit**: 0.5%
- **Time Limit**: 1 hour
- **Take Profit Order Type**: MARKET

## Features Implemented

### 1. Data Loading
- ✅ Local Binance Public Data integration
- ✅ 15-minute data aggregation from 1-minute source data
- ✅ Automatic data caching for performance
- ✅ Robust error handling for corrupted zip files

### 2. Backtesting
- ✅ Progress bar display (tqdm-style)
- ✅ Comprehensive metrics calculation:
  - Total PnL ($ and %)
  - Total Volume
  - Fill Rate (overall, buy, sell)
  - Win Rate
  - Max Position Value
  - Turnover Return (PnL / Volume)
  - Sharpe Ratio
  - Max Drawdown

### 3. Reporting
- ✅ Strategy comparison table
- ✅ Strategy parameters display
- ✅ JSON results export
- ✅ Equity curves (15-minute frequency)
- ✅ Position value curves (15-minute frequency)
- ✅ Cumulative PnL curves
- ✅ All plots with English annotations

### 4. Metrics Included
- ✅ Total Executors / Filled Executors
- ✅ Buy Fill Rate / Sell Fill Rate
- ✅ Max Position Value
- ✅ Turnover Return (PnL / Total Volume)
- ✅ Win Rate
- ✅ Winning / Losing Trades
- ✅ Strategy parameters (spreads, stop loss, take profit, time limit)

## Current Status

### Running Status
The backtest is currently running in the background. Monitor progress with:
```bash
./monitor_comprehensive_backtest.sh
```

Or check the log file:
```bash
tail -f comprehensive_backtest.log
```

### Progress Tracking
- Progress is displayed for each strategy/trading pair combination
- Total progress: [X]/36 tasks
- Estimated completion time: Varies by data availability and system performance

## Output Files

### Results File
- **Location**: `backtest_comparison_results_20250301_20251109.json`
- **Content**: Complete backtest results including:
  - Time range and trading pairs
  - Strategy configurations
  - Aggregated comparison metrics
  - Detailed results per trading pair and strategy

### Plot Files
1. **Equity & Position Value Curves**
   - **File**: `backtest_comparison_plots_20250301_20251109.png`
   - **Content**: Two subplots showing equity and position value over time
   - **Frequency**: 15 minutes
   - **Language**: English annotations

2. **Cumulative PnL Curves**
   - **File**: `backtest_cumulative_pnl_20250301_20251109.png`
   - **Content**: Cumulative PnL over time for all strategies
   - **Frequency**: 15 minutes
   - **Language**: English annotations

## Known Issues

1. **Corrupted Zip Files**: Some trading pairs (XRP, ASTER, etc.) have corrupted zip files for November 2025 dates. The script will skip these files and continue with available data.

2. **Missing Data**: Some trading pairs (PEPE, etc.) may not have data for the entire time range. These pairs will be skipped.

3. **Data Aggregation**: 15-minute data is aggregated from 1-minute source data, which may introduce minor timing discrepancies at boundaries.

## Next Steps

1. Wait for backtest completion
2. Review generated plots and comparison table
3. Analyze strategy performance differences
4. Adjust parameters if needed for optimization

## Monitoring Commands

```bash
# Check if process is running
pgrep -f comprehensive_backtest_comparison.py

# View latest progress
tail -50 comprehensive_backtest.log

# Monitor in real-time
tail -f comprehensive_backtest.log

# Check for completion
grep "Backtest Comparison Completed" comprehensive_backtest.log
```

## Notes

- All plots use English annotations as requested
- Position value curves show the total value of open positions over time
- Equity curves show the portfolio value (initial + cumulative PnL)
- All metrics are calculated per strategy and aggregated across trading pairs

