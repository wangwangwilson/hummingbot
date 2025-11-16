# Comprehensive Strategy Comparison

## Overview

This backtest compares three market-making strategies across 12 trading pairs:

### Strategies
1. **PMM Simple (Classic)** - Classic pure market-making strategy
2. **PMM Dynamic (MACD)** - Market-making with MACD signal for dynamic spread adjustment
3. **PMM Bar Portion (BP)** - Market-making with Bar Portion signal for mean reversion

### Trading Pairs
- BTC-USDT
- ETH-USDT
- SOL-USDT
- XRP-USDT
- PEPE-USDT
- ASTER-USDT
- MYX-USDT
- PUMP-USDT
- XPL-USDT
- OM-USDT
- TRX-USDT
- UMA-USDT

### Backtest Period
- Start: 2025-03-01
- End: 2025-11-09
- Duration: ~8 months

## Strategy Configurations

### PMM Simple
```python
{
    "buy_spreads": [0.005, 0.01],        # 0.5%, 1.0%
    "sell_spreads": [0.005, 0.01],
    "stop_loss": 0.01,                    # 1%
    "take_profit": 0.005,                 # 0.5%
    "time_limit": 900,                    # 15 minutes
    "executor_refresh_time": 300          # 5 minutes
}
```

### PMM Dynamic (MACD)
```python
{
    "buy_spreads": [0.005, 0.01],
    "sell_spreads": [0.005, 0.01],
    "macd_fast": 12,
    "macd_slow": 26,
    "macd_signal": 9,
    "natr_length": 100
}
```

### PMM Bar Portion (BP)
```python
{
    "buy_spreads": [0.005, 0.01],
    "sell_spreads": [0.005, 0.01],
    "stop_loss": 0.01,
    "take_profit": 0.005,
    "time_limit": 900,
    "bar_portion_threshold": 0.5
}
```

## Output Metrics

### Performance Metrics
- **Total PnL**: Total profit/loss in USD
- **Return %**: Percentage return on initial portfolio
- **Fill Rate**: Percentage of orders that were filled
- **Turnover Return**: PnL / Total Volume (%)

### Order Metrics
- **Total Executors**: Total number of order executors created
- **Filled Executors**: Number of executors that were filled
- **Buy Orders Total**: Total buy orders created
- **Sell Orders Total**: Total sell orders created
- **Buy Orders Filled**: Number of buy orders filled
- **Sell Orders Filled**: Number of sell orders filled
- **Buy Fill Rate**: Percentage of buy orders filled
- **Sell Fill Rate**: Percentage of sell orders filled

### Position Metrics
- **Max Position Value**: Maximum portfolio value reached
- **Daily Volume**: Average daily trading volume
- **Daily PnL**: Average daily profit/loss

## Output Files

### 1. Comparison Plots (per trading pair)
**Filename**: `strategy_comparison_{PAIR}_{START}_{END}.png`

Contains 5 subplots:
1. **Cumulative PnL**: Time series of cumulative profit/loss
2. **Portfolio Value**: Time series of total portfolio value
3. **Fill Rate Comparison**: Bar chart of buy/sell fill rates
4. **Total PnL Comparison**: Bar chart of total PnL by strategy
5. **Turnover Return Comparison**: Bar chart of PnL/Volume ratio

All plots use:
- **15-minute frequency** for time series
- **English annotations** (no Chinese)
- Clear labels showing backtest period and symbol

### 2. Comparison Report
**Filename**: `comparison_results_{START}_{END}.json`

JSON file containing:
- All metrics for each strategy-pair combination
- Strategy configurations
- Backtest period information

### 3. Console Output
**Filename**: `comprehensive_comparison_output.log`

Contains:
- Progress logs for each backtest
- Summary statistics
- Comparison tables

## Monitoring Progress

Use the monitoring script:
```bash
./monitor_comprehensive_comparison.sh
```

Or check the log file:
```bash
tail -f comprehensive_comparison_output.log
```

## Expected Runtime

- **Per backtest**: ~3-5 minutes (depends on data size)
- **Total backtests**: 36 (12 pairs × 3 strategies)
- **Total estimated time**: ~2-3 hours

## Key Features

### 1. Progress Logging
- Real-time progress bar using tqdm
- Completion status for each backtest
- Error handling with detailed logs

### 2. 15-Minute Aggregation
- Raw data: 1-minute candles
- Analysis frequency: 15-minute intervals
- Smooth curves while maintaining detail

### 3. English Annotations
- All plot labels in English
- Clear metric names
- Professional presentation

### 4. Comprehensive Metrics
- Traditional metrics (PnL, Return, Fill Rate)
- Advanced metrics (Turnover Return, Daily Volume)
- Order-level statistics (Buy/Sell split)

## Strategy Key Parameters

### PMM Simple
- **Position Threshold**: Managed through `total_amount_quote`
- **Refresh Time**: 300 seconds (5 minutes)
- **Spread Levels**: 2 levels (0.5%, 1.0%)

### PMM Dynamic (MACD)
- **MACD Fast**: 12 periods
- **MACD Slow**: 26 periods
- **Signal Line**: 9 periods
- **Volatility Adjustment**: NATR with 100-period window

### PMM Bar Portion (BP)
- **Bar Portion Threshold**: 0.5 (50%)
- **Risk Management**: Stop Loss 1%, Take Profit 0.5%
- **Position Duration**: 900 seconds (15 minutes)
- **Training Window**: 100 candles for regression model

## Interpretation Guide

### Good Strategy Characteristics
1. **High Fill Rate** (>40%): Orders are competitive with market
2. **Positive Turnover Return**: Profitable relative to volume
3. **Balanced Buy/Sell**: No severe directional bias
4. **Smooth Equity Curve**: Consistent performance over time
5. **Low Drawdown**: Capital preservation during downturns

### Red Flags
1. **Very Low Fill Rate** (<10%): Orders too far from market
2. **Negative Turnover Return**: Losing money on each trade
3. **Extreme Buy/Sell Imbalance**: One-sided market making
4. **Volatile Equity**: Inconsistent performance
5. **Large Drawdowns**: Significant capital loss periods

## Post-Analysis

After completion, analyze:
1. Which strategy performs best overall?
2. Are certain strategies better for specific pairs?
3. How do volatility levels affect each strategy?
4. What's the trade-off between fill rate and profitability?
5. How stable is performance across different market conditions?

## Troubleshooting

### Backtest Fails
- Check data availability for the trading pair
- Verify date range has local data
- Review error logs in output file

### Low Fill Rates
- Spreads may be too wide
- Consider tightening spread parameters
- Check if market was very volatile

### Memory Issues
- Process 1-2 pairs at a time
- Reduce backtest period length
- Use larger time intervals (e.g., 1 hour)

---

**Status**: Running
**Started**: 2025-11-13
**Expected Completion**: ~2-3 hours

