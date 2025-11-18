from decimal import Decimal
from typing import List, Optional

import pandas as pd
from pydantic import Field

from hummingbot.data_feed.candles_feed.data_types import CandlesConfig
from hummingbot.strategy_v2.controllers.market_making_controller_base import (
    MarketMakingControllerBase,
    MarketMakingControllerConfigBase,
)
from hummingbot.strategy_v2.executors.position_executor.data_types import PositionExecutorConfig


class PMMSimpleConfig(MarketMakingControllerConfigBase):
    controller_name: str = "pmm_simple"
    # As this controller is a simple version of the PMM, we are not using the candles feed
    candles_config: List[CandlesConfig] = Field(default=[])
    use_future_data: bool = Field(default=False, description="Use future price direction as signal (ideal benchmark)")


class PMMSimpleController(MarketMakingControllerBase):
    def __init__(self, config: PMMSimpleConfig, *args, **kwargs):
        super().__init__(config, *args, **kwargs)
        self.config = config
    
    async def update_processed_data(self):
        """更新处理后的数据，如果启用未来数据，使用下一根K线的价格方向"""
        if self.config.use_future_data:
            # 使用未来数据：获取下一根K线的价格变化方向
            current_time = self.market_data_provider.time()
            candles = self.market_data_provider.get_candles_df(
                connector_name=self.config.connector_name,
                trading_pair=self.config.trading_pair,
                interval="1m",
                max_records=10000  # 获取更多数据以确保包含未来数据
            )
            
            if len(candles) >= 2 and 'timestamp' in candles.columns:
                # 在回测中，需要根据当前时间戳找到对应的K线和下一根K线
                # 确保timestamp是数值类型（秒级）
                if candles['timestamp'].dtype == 'object' or pd.api.types.is_datetime64_any_dtype(candles['timestamp']):
                    # 如果是datetime类型，转换为秒级时间戳
                    candles_timestamps = pd.to_datetime(candles['timestamp']).astype('int64') // 10**9
                else:
                    # 如果是毫秒级时间戳，转换为秒级
                    if candles['timestamp'].max() > 1e10:
                        candles_timestamps = candles['timestamp'] / 1000
                    else:
                        candles_timestamps = candles['timestamp']
                
                # 找到当前时间戳对应的K线（使用<=查找，找到最接近的）
                current_mask = candles_timestamps <= current_time
                current_candles = candles[current_mask]
                if len(current_candles) > 0:
                    current_close = current_candles["close"].iloc[-1]
                    
                    # 找到下一根K线（时间戳大于当前时间的第一根）
                    future_mask = candles_timestamps > current_time
                    future_candles = candles[future_mask]
                    if len(future_candles) > 0:
                        future_close = future_candles["close"].iloc[0]
                        # 计算价格变化方向（未来收益率）
                        future_return = (future_close - current_close) / current_close if current_close > 0 else 0.0
                    else:
                        # 没有未来数据，使用当前价格
                        future_return = 0.0
                else:
                    # 如果找不到当前时间对应的K线，使用最新的K线
                    current_close = candles["close"].iloc[-1]
                    future_return = 0.0
                
                # 计算价格变化方向（未来收益率）
                # future_return 已经在上面计算好了
                
                # 使用未来收益率调整reference_price
                # 如果未来价格上涨，提高reference_price（更多卖单，因为价格会涨，我们想在高位卖出）
                # 如果未来价格下跌，降低reference_price（更多买单，因为价格会跌，我们想在低位买入）
                from hummingbot.core.data_type.common import PriceType
                try:
                    current_market_price = self.market_data_provider.get_price_by_type(
                        connector_name=self.config.connector_name,
                        trading_pair=self.config.trading_pair,
                        price_type=PriceType.MidPrice
                    )
                    if current_market_price and current_market_price > 0:
                        base_price = float(current_market_price)
                    else:
                        base_price = float(current_close)
                except:
                    base_price = float(current_close)
                
                # 使用未来收益率调整价格
                # 如果未来价格上涨（future_return > 0），我们希望更多卖单，所以提高reference_price
                # 如果未来价格下跌（future_return < 0），我们希望更多买单，所以降低reference_price
                # 调整幅度：使用未来收益率的绝对值，但限制在合理范围内（例如0.5%）
                max_shift = 0.005  # 最大0.5%的调整
                price_shift = max(-max_shift, min(max_shift, future_return))
                reference_price = base_price * (1 + price_shift)
                
                self.processed_data = {
                    "reference_price": Decimal(str(reference_price)),
                    "spread_multiplier": Decimal("0.01"),
                    "features": pd.DataFrame({"reference_price": [reference_price], "future_return": [future_return]})
                }
            else:
                # 数据不足，使用当前价格
                from hummingbot.core.data_type.common import PriceType
                try:
                    current_price = self.market_data_provider.get_price_by_type(
                        connector_name=self.config.connector_name,
                        trading_pair=self.config.trading_pair,
                        price_type=PriceType.MidPrice
                    )
                    if current_price and current_price > 0:
                        reference_price = Decimal(str(current_price))
                    else:
                        reference_price = Decimal("0")
                except:
                    reference_price = Decimal("0")
                
                self.processed_data = {
                    "reference_price": reference_price,
                    "spread_multiplier": Decimal("0.01"),
                    "features": pd.DataFrame()
                }
        else:
            # 不使用未来数据时，使用当前市场价格作为reference_price
            from hummingbot.core.data_type.common import PriceType
            try:
                current_price = self.market_data_provider.get_price_by_type(
                    connector_name=self.config.connector_name,
                    trading_pair=self.config.trading_pair,
                    price_type=PriceType.MidPrice
                )
                if current_price and current_price > 0:
                    reference_price = Decimal(str(current_price))
                else:
                    # 如果无法获取市场价格，尝试从candles获取
                    candles = self.market_data_provider.get_candles_df(
                        connector_name=self.config.connector_name,
                        trading_pair=self.config.trading_pair,
                        interval="1m",
                        max_records=100
                    )
                    if len(candles) > 0:
                        reference_price = Decimal(str(candles["close"].iloc[-1]))
                    else:
                        reference_price = Decimal("0")
            except:
                reference_price = Decimal("0")
            
            self.processed_data = {
                "reference_price": reference_price,
                "spread_multiplier": Decimal("0.01"),
                "features": pd.DataFrame()
            }

    def get_executor_config(self, level_id: str, price: Decimal, amount: Decimal):
        trade_type = self.get_trade_type_from_level_id(level_id)
        return PositionExecutorConfig(
            timestamp=self.market_data_provider.time(),
            level_id=level_id,
            connector_name=self.config.connector_name,
            trading_pair=self.config.trading_pair,
            entry_price=price,
            amount=amount,
            triple_barrier_config=self.config.triple_barrier_config,
            leverage=self.config.leverage,
            side=trade_type,
        )
