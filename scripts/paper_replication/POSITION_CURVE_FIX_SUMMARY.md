# Position Curve Fix Summary

## Problem Identified

The original `generate_equity_curve` function had critical issues:

1. **Only used `close_timestamp`**: It only recorded data when executors closed, meaning positions didn't change during executor lifetime
2. **Incorrect position accumulation**: It accumulated all closed executor positions, rather than tracking actual open positions at each time point
3. **Missing open events**: Executor open times (`timestamp`) were not used, causing positions to appear static until executors closed

## Root Cause

The function was only processing executor close events, not open events. This meant:
- Positions appeared to be 0 until executors closed
- Positions didn't change continuously as executors opened and closed
- The curve only showed data for the last 10 days (when most executors closed)

## Solution

### New Implementation

1. **Event-based tracking**: Create both "open" and "close" events for each executor
2. **Continuous position calculation**: Track current long/short positions at each time point
3. **Proper time range**: Use the full backtest time range (start_ts to end_ts)

### Key Changes

```python
# Create events: executor open and close
events = []
for executor in filled_executors:
    # Open event (from executor.config.timestamp)
    if hasattr(executor, 'config') and hasattr(executor.config, 'timestamp'):
        open_time = datetime.fromtimestamp(executor.config.timestamp)
        events.append({
            'timestamp': open_time,
            'type': 'open',
            'position_value': position_value,
            'side': side
        })
    
    # Close event (from executor.close_timestamp)
    if hasattr(executor, 'close_timestamp') and executor.close_timestamp:
        close_time = datetime.fromtimestamp(executor.close_timestamp)
        events.append({
            'timestamp': close_time,
            'type': 'close',
            'position_value': position_value,
            'pnl': pnl,
            'side': side
        })

# Process events chronologically
for timestamp in timeline:
    for event in events_before_timestamp:
        if event['type'] == 'open':
            # Add to current position
            if event['side'] == TradeType.BUY:
                current_long_position += event['position_value']
            elif event['side'] == TradeType.SELL:
                current_short_position += event['position_value']
        elif event['type'] == 'close':
            # Remove from current position and add PnL
            if event['side'] == TradeType.BUY:
                current_long_position -= event['position_value']
            elif event['side'] == TradeType.SELL:
                current_short_position -= event['position_value']
            cumulative_pnl += event['pnl']
```

## Verification Results

### Test: BTC-USDT (2025-01-01 to 2025-05-01)

**PMM Simple:**
- Position changes: 12 times
- Max position: $3,315.96
- Data points: 11,521 (full 4 months)
- Time span: 120 days

**PMM Dynamic (MACD):**
- Position changes: 37 times
- Max position: $10,018.36
- Data points: 11,521 (full 4 months)
- Time span: 120 days

**PMM Bar Portion:**
- Position changes: 141 times
- Max position: $10,187.35
- Data points: 11,521 (full 4 months)
- Time span: 120 days

## Improvements

1. ✅ **Full time range coverage**: Now shows data for the entire backtest period (not just last 10 days)
2. ✅ **Continuous position tracking**: Positions change as executors open and close
3. ✅ **Long/Short separation**: Tracks long and short positions separately
4. ✅ **Accurate PnL accumulation**: PnL is added when positions close, not accumulated incorrectly

## Files Updated

1. `comprehensive_backtest_comparison.py`: Updated `generate_equity_curve` function
2. `test_btc_position_curve.py`: Created test script to verify the fix

## Next Steps

1. Re-run the comprehensive backtest with the fixed code
2. Verify that position curves show continuous changes throughout the entire time period
3. Confirm that long/short positions alternate as expected

