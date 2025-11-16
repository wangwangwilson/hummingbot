import pandas as pd

from hummingbot.core.data_type.common import TradeType
from hummingbot.strategy_v2.backtesting.executor_simulator_base import ExecutorSimulation, ExecutorSimulatorBase
from hummingbot.strategy_v2.executors.position_executor.data_types import PositionExecutorConfig
from hummingbot.strategy_v2.models.executors import CloseType


class PositionExecutorSimulator(ExecutorSimulatorBase):
    def simulate(self, df: pd.DataFrame, config: PositionExecutorConfig, trade_cost: float) -> ExecutorSimulation:
        if config.triple_barrier_config.open_order_type.is_limit_type():
            entry_condition = (df['close'] <= config.entry_price) if config.side == TradeType.BUY else (df['close'] >= config.entry_price)
            start_timestamp = df[entry_condition]['timestamp'].min()
        else:
            start_timestamp = df['timestamp'].min()
        last_timestamp = df['timestamp'].max()
        
        # 确保时间戳是整数类型（兼容int64索引）
        if pd.api.types.is_integer_dtype(df.index):
            if pd.notna(start_timestamp):
                start_timestamp = int(start_timestamp)
            last_timestamp = int(last_timestamp)

        # Set up barriers
        tp = float(config.triple_barrier_config.take_profit) if config.triple_barrier_config.take_profit else None
        trailing_sl_trigger_pct = None
        trailing_sl_delta_pct = None
        if config.triple_barrier_config.trailing_stop:
            trailing_sl_trigger_pct = float(config.triple_barrier_config.trailing_stop.activation_price)
            trailing_sl_delta_pct = float(config.triple_barrier_config.trailing_stop.trailing_delta)
        tl = config.triple_barrier_config.time_limit if config.triple_barrier_config.time_limit else None
        tl_timestamp = config.timestamp + tl if tl else last_timestamp
        
        # 确保tl_timestamp是整数类型（兼容int64索引的切片操作）
        if pd.api.types.is_integer_dtype(df.index):
            tl_timestamp = int(tl_timestamp)

        # Filter dataframe based on the conditions
        df_filtered = df[:tl_timestamp].copy()

        df_filtered['net_pnl_pct'] = 0.0
        df_filtered['net_pnl_quote'] = 0.0
        df_filtered['cum_fees_quote'] = 0.0
        df_filtered['filled_amount_quote'] = 0.0
        df_filtered["current_position_average_price"] = float(config.entry_price)

        if pd.isna(start_timestamp):
            # 如果没有满足条件的entry，返回空的executor simulation
            df_filtered['net_pnl_pct'] = 0.0
            df_filtered['net_pnl_quote'] = 0.0
            df_filtered['cum_fees_quote'] = 0.0
            df_filtered['filled_amount_quote'] = 0.0
            return ExecutorSimulation(config=config, executor_simulation=df_filtered, close_type=CloseType.TIME_LIMIT)

        entry_price = float(df.loc[start_timestamp, 'close'])
        side_multiplier = 1 if config.side == TradeType.BUY else -1

        returns_df = df_filtered[start_timestamp:]
        # 计算从entry_price到当前价格的收益率
        # 对于买入：收益率 = (当前价格 - entry_price) / entry_price
        # 对于卖出：收益率 = (entry_price - 当前价格) / entry_price
        price_returns = (returns_df['close'] - entry_price) / entry_price * side_multiplier
        # 扣除交易成本（开仓和平仓各一次，所以是2倍）
        net_returns = price_returns - (2 * float(trade_cost))
        df_filtered.loc[start_timestamp:, 'net_pnl_pct'] = net_returns
        df_filtered.loc[start_timestamp:, 'filled_amount_quote'] = float(config.amount) * entry_price
        # 计算net_pnl_quote：使用已计算的net_pnl_pct和filled_amount_quote
        # 注意：这里需要确保filled_amount_quote在start_timestamp之后的行都有值
        df_filtered.loc[start_timestamp:, 'net_pnl_quote'] = df_filtered.loc[start_timestamp:, 'net_pnl_pct'] * df_filtered.loc[start_timestamp:, 'filled_amount_quote']
        # 交易费用：开仓和平仓各一次
        df_filtered.loc[start_timestamp:, 'cum_fees_quote'] = (2 * float(trade_cost)) * df_filtered.loc[start_timestamp:, 'filled_amount_quote']
        
        # 确保没有NaN值（兼容性修复）
        # 只对start_timestamp之前的行填充0，start_timestamp之后的行应该已经有正确的值
        df_filtered.loc[:start_timestamp, 'net_pnl_pct'] = df_filtered.loc[:start_timestamp, 'net_pnl_pct'].fillna(0.0)
        df_filtered.loc[:start_timestamp, 'net_pnl_quote'] = df_filtered.loc[:start_timestamp, 'net_pnl_quote'].fillna(0.0)
        df_filtered.loc[:start_timestamp, 'cum_fees_quote'] = df_filtered.loc[:start_timestamp, 'cum_fees_quote'].fillna(0.0)
        df_filtered.loc[:start_timestamp, 'filled_amount_quote'] = df_filtered.loc[:start_timestamp, 'filled_amount_quote'].fillna(0.0)
        # 对start_timestamp之后的行，只填充NaN（不应该有NaN，但为了安全）
        df_filtered.loc[start_timestamp:, 'net_pnl_pct'] = df_filtered.loc[start_timestamp:, 'net_pnl_pct'].fillna(0.0)
        df_filtered.loc[start_timestamp:, 'net_pnl_quote'] = df_filtered.loc[start_timestamp:, 'net_pnl_quote'].fillna(0.0)
        df_filtered.loc[start_timestamp:, 'cum_fees_quote'] = df_filtered.loc[start_timestamp:, 'cum_fees_quote'].fillna(0.0)
        df_filtered.loc[start_timestamp:, 'filled_amount_quote'] = df_filtered.loc[start_timestamp:, 'filled_amount_quote'].fillna(0.0)

        # Make sure the trailing stop pct rises linearly to the net p/l pct when above the trailing stop trigger pct (if any)
        if trailing_sl_trigger_pct is not None and trailing_sl_delta_pct is not None:
            df_filtered.loc[(df_filtered['net_pnl_pct'] > trailing_sl_trigger_pct).cummax(), 'ts'] = (
                df_filtered['net_pnl_pct'] - float(trailing_sl_delta_pct)
            ).cummax()

        # Determine the earliest close event
        first_tp_timestamp = df_filtered[df_filtered['net_pnl_pct'] > tp]['timestamp'].min() if tp else None
        first_sl_timestamp = None
        if config.triple_barrier_config.stop_loss:
            sl = float(config.triple_barrier_config.stop_loss)
            sl_price = float(entry_price) * (1 - sl * side_multiplier)
            sl_condition = df_filtered['low'] <= sl_price if config.side == TradeType.BUY else df_filtered['high'] >= sl_price
            first_sl_timestamp = df_filtered[sl_condition]['timestamp'].min()
        first_trailing_sl_timestamp = df_filtered[(~df_filtered['ts'].isna()) & (df_filtered['net_pnl_pct'] < df_filtered['ts'])]['timestamp'].min() if trailing_sl_delta_pct and trailing_sl_trigger_pct else None
        close_timestamp = min([timestamp for timestamp in [first_tp_timestamp, first_sl_timestamp, tl_timestamp, first_trailing_sl_timestamp] if not pd.isna(timestamp)])

        # Determine the close type
        if close_timestamp == first_tp_timestamp:
            close_type = CloseType.TAKE_PROFIT
        elif close_timestamp == first_sl_timestamp:
            close_type = CloseType.STOP_LOSS
        elif close_timestamp == first_trailing_sl_timestamp:
            close_type = CloseType.TRAILING_STOP
        else:
            close_type = CloseType.TIME_LIMIT

        # Set the final state of the DataFrame
        # 确保包含close_timestamp这一行（使用<=而不是<）
        if pd.api.types.is_integer_dtype(df_filtered.index):
            # 对于整数索引，使用<=来包含close_timestamp
            df_filtered = df_filtered[df_filtered.index <= close_timestamp]
        else:
            # 对于其他类型的索引，使用原来的切片方式
            df_filtered = df_filtered[:close_timestamp]
        
        # 确保最后一行有正确的filled_amount_quote（开仓+平仓）
        if len(df_filtered) > 0:
            last_index = df_filtered.index[-1]
            df_filtered.loc[last_index, "filled_amount_quote"] = float(config.amount) * entry_price * 2
            
            # 关键修复：确保最后一行（close_timestamp）的net_pnl_pct和net_pnl_quote正确计算
            # 使用最后一行（close_timestamp）的close价格作为exit_price
            exit_price = float(df_filtered.loc[last_index, 'close'])
            price_return = (exit_price - entry_price) / entry_price * side_multiplier
            net_return = price_return - (2 * float(trade_cost))
            
            # 更新最后一行的net_pnl_pct和net_pnl_quote
            df_filtered.loc[last_index, 'net_pnl_pct'] = net_return
            df_filtered.loc[last_index, 'net_pnl_quote'] = net_return * df_filtered.loc[last_index, 'filled_amount_quote']
            df_filtered.loc[last_index, 'cum_fees_quote'] = (2 * float(trade_cost)) * df_filtered.loc[last_index, 'filled_amount_quote']

        # Construct and return ExecutorSimulation object
        simulation = ExecutorSimulation(
            config=config,
            executor_simulation=df_filtered,
            close_type=close_type
        )
        return simulation
