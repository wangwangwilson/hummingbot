from decimal import Decimal
from typing import List

import pandas as pd
import pandas_ta as ta  # noqa: F401
from pydantic import Field, field_validator
from pydantic_core.core_schema import ValidationInfo

from hummingbot.data_feed.candles_feed.data_types import CandlesConfig
from hummingbot.strategy_v2.controllers.market_making_controller_base import (
    MarketMakingControllerBase,
    MarketMakingControllerConfigBase,
)
from hummingbot.strategy_v2.executors.position_executor.data_types import PositionExecutorConfig


class PMMDynamicControllerConfig(MarketMakingControllerConfigBase):
    controller_name: str = "pmm_dynamic"
    candles_config: List[CandlesConfig] = []
    buy_spreads: List[float] = Field(
        default="1,2,4",
        json_schema_extra={
            "prompt": "Enter a comma-separated list of buy spreads measured in units of volatility(e.g., '1, 2'): ",
            "prompt_on_new": True, "is_updatable": True}
    )
    sell_spreads: List[float] = Field(
        default="1,2,4",
        json_schema_extra={
            "prompt": "Enter a comma-separated list of sell spreads measured in units of volatility(e.g., '1, 2'): ",
            "prompt_on_new": True, "is_updatable": True}
    )
    candles_connector: str = Field(
        default=None,
        json_schema_extra={
            "prompt": "Enter the connector for the candles data, leave empty to use the same exchange as the connector: ",
            "prompt_on_new": True})
    candles_trading_pair: str = Field(
        default=None,
        json_schema_extra={
            "prompt": "Enter the trading pair for the candles data, leave empty to use the same trading pair as the connector: ",
            "prompt_on_new": True})
    interval: str = Field(
        default="3m",
        json_schema_extra={
            "prompt": "Enter the candle interval (e.g., 1m, 5m, 1h, 1d): ",
            "prompt_on_new": True})
    macd_fast: int = Field(
        default=21,
        json_schema_extra={"prompt": "Enter the MACD fast period: ", "prompt_on_new": True})
    macd_slow: int = Field(
        default=42,
        json_schema_extra={"prompt": "Enter the MACD slow period: ", "prompt_on_new": True})
    macd_signal: int = Field(
        default=9,
        json_schema_extra={"prompt": "Enter the MACD signal period: ", "prompt_on_new": True})
    natr_length: int = Field(
        default=14,
        json_schema_extra={"prompt": "Enter the NATR length: ", "prompt_on_new": True})
    use_future_data: bool = Field(default=False, description="Use future price direction as signal (ideal benchmark)")

    @field_validator("candles_connector", mode="before")
    @classmethod
    def set_candles_connector(cls, v, validation_info: ValidationInfo):
        if v is None or v == "":
            return validation_info.data.get("connector_name")
        return v

    @field_validator("candles_trading_pair", mode="before")
    @classmethod
    def set_candles_trading_pair(cls, v, validation_info: ValidationInfo):
        if v is None or v == "":
            return validation_info.data.get("trading_pair")
        return v


class PMMDynamicController(MarketMakingControllerBase):
    """
    This is a dynamic version of the PMM controller.It uses the MACD to shift the mid-price and the NATR
    to make the spreads dynamic. It also uses the Triple Barrier Strategy to manage the risk.
    """

    def __init__(self, config: PMMDynamicControllerConfig, *args, **kwargs):
        self.config = config
        # 与BP策略保持一致，使用足够大的max_records以覆盖整个回测区间
        self.max_records = 200_000
        if len(self.config.candles_config) == 0:
            self.config.candles_config = [CandlesConfig(
                connector=config.candles_connector,
                trading_pair=config.candles_trading_pair,
                interval=config.interval,
                max_records=self.max_records
            )]
        super().__init__(config, *args, **kwargs)

    async def update_processed_data(self):
        """
        Update processed data.
        
        If use_future_data is True, uses the next candle's price direction as signal.
        """
        # 如果启用未来数据，使用下一根K线的价格方向
        if self.config.use_future_data:
            candles = self.market_data_provider.get_candles_df(
                connector_name=self.config.candles_connector,
                trading_pair=self.config.candles_trading_pair,
                interval=self.config.interval,
                max_records=self.max_records
            )
            
            if len(candles) >= 2:
                # 获取当前和下一根K线的价格
                current_close = candles["close"].iloc[-1]
                future_close = candles["close"].iloc[-2] if len(candles) >= 2 else current_close
                
                # 计算未来收益率
                future_return = (future_close - current_close) / current_close if current_close > 0 else 0.0
                
                # 使用未来收益率调整reference_price
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
                
                # 使用未来收益率调整价格（最大0.5%的调整）
                max_shift = 0.005
                price_multiplier = max(-max_shift, min(max_shift, future_return))
                reference_price_value = base_price * (1 + price_multiplier)
                
                # 计算NATR
                natr = ta.natr(candles["high"], candles["low"], candles["close"], length=self.config.natr_length)
                if natr is None or len(natr) == 0:
                    natr_value = Decimal("0.01")
                else:
                    natr = natr / 100
                    natr_value = Decimal(float(natr.iloc[-1])) if not pd.isna(natr.iloc[-1]) else Decimal("0.01")
                    if natr_value <= 0 or natr_value > Decimal("0.1"):
                        natr_value = Decimal("0.01")
                
                candles["reference_price"] = reference_price_value
                candles["spread_multiplier"] = natr if natr is not None and not natr.empty else pd.Series([float(natr_value)] * len(candles), index=candles.index)
                candles["future_return"] = future_return
                
                self.processed_data = {
                    "reference_price": Decimal(reference_price_value),
                    "spread_multiplier": natr_value,
                    "features": candles
                }
                return
        
        candles = self.market_data_provider.get_candles_df(connector_name=self.config.candles_connector,
                                                           trading_pair=self.config.candles_trading_pair,
                                                           interval=self.config.interval,
                                                           max_records=self.max_records)
        
        # 关键修复：总是使用当前最新的市场价格作为基础
        current_market_price = None
        try:
            from hummingbot.core.data_type.common import PriceType
            current_market_price = Decimal(self.market_data_provider.get_price_by_type(
                self.config.candles_connector, self.config.candles_trading_pair, PriceType.MidPrice))
        except:
            pass
        
        # 如果无法从market_data_provider获取，使用candles的close价格
        if current_market_price is None or current_market_price == 0:
            if len(candles) > 0:
                current_market_price = Decimal(candles["close"].iloc[-1])
            else:
                current_market_price = Decimal("0")
        
        # 检查数据是否为空
        if len(candles) == 0:
            self.processed_data = {
                "reference_price": current_market_price,
                "spread_multiplier": Decimal("0.01"),
                "features": pd.DataFrame()
            }
            return
        
        # 降低数据要求：至少需要MACD计算所需的数据（macd_slow + macd_signal）
        min_required = max(self.config.macd_slow + self.config.macd_signal, self.config.natr_length, 30)
        
        if len(candles) < min_required:
            # Not enough data, but still calculate with available data
            # 尝试使用更少的数据计算NATR和MACD
            if len(candles) >= self.config.natr_length:
                natr = ta.natr(candles["high"], candles["low"], candles["close"], length=self.config.natr_length)
                if natr is not None and len(natr) > 0:
                    natr = natr / 100
                    natr_value = Decimal(float(natr.iloc[-1])) if not pd.isna(natr.iloc[-1]) else Decimal("0.01")
                else:
                    natr_value = Decimal("0.01")
            else:
                natr_value = Decimal("0.01")
            
            # 尝试计算MACD（即使数据不足）
            if len(candles) >= self.config.macd_slow:
                try:
                    macd_output = ta.macd(candles["close"], fast=self.config.macd_fast,
                                          slow=self.config.macd_slow, signal=self.config.macd_signal)
                    if macd_output is not None and len(macd_output) > 0:
                        macd = macd_output[f"MACD_{self.config.macd_fast}_{self.config.macd_slow}_{self.config.macd_signal}"]
                        macd_signal = - (macd - macd.mean()) / macd.std() if macd.std() > 0 else pd.Series([0.0] * len(macd))
                        macdh = macd_output[f"MACDh_{self.config.macd_fast}_{self.config.macd_slow}_{self.config.macd_signal}"]
                        macdh_signal = macdh.apply(lambda x: 1 if x > 0 else -1)
                        max_price_shift = natr_value / 2 if isinstance(natr_value, Decimal) else Decimal("0.01")
                        price_multiplier = ((0.5 * macd_signal + 0.5 * macdh_signal) * float(max_price_shift)).iloc[-1] if len(macd_signal) > 0 else 0.0
                    else:
                        price_multiplier = 0.0
                except:
                    price_multiplier = 0.0
            else:
                price_multiplier = 0.0
            
            # 关键修复：优先使用当前市场价格
            if current_market_price and current_market_price > 0:
                current_price = current_market_price
            else:
                current_price = Decimal(candles["close"].iloc[-1]) if len(candles) > 0 else Decimal("0")
            reference_price = current_price * (1 + price_multiplier)
            
            self.processed_data = {
                "reference_price": reference_price,
                "spread_multiplier": natr_value,
                "features": candles
            }
            return
        
        natr = ta.natr(candles["high"], candles["low"], candles["close"], length=self.config.natr_length)
        if natr is None or len(natr) == 0:
            # NATR计算失败，使用默认值
            self.processed_data = {
                "reference_price": Decimal(candles["close"].iloc[-1]),
                "spread_multiplier": Decimal("0.01"),
                "features": candles
            }
            return
        
        natr = natr / 100
        macd_output = ta.macd(candles["close"], fast=self.config.macd_fast,
                              slow=self.config.macd_slow, signal=self.config.macd_signal)
        macd = macd_output[f"MACD_{self.config.macd_fast}_{self.config.macd_slow}_{self.config.macd_signal}"]
        macd_signal = - (macd - macd.mean()) / macd.std()
        macdh = macd_output[f"MACDh_{self.config.macd_fast}_{self.config.macd_slow}_{self.config.macd_signal}"]
        macdh_signal = macdh.apply(lambda x: 1 if x > 0 else -1)
        max_price_shift = natr / 2
        price_multiplier = ((0.5 * macd_signal + 0.5 * macdh_signal) * max_price_shift).iloc[-1]
        # 关键修复：优先使用当前市场价格计算reference_price
        if current_market_price and current_market_price > 0:
            current_price = float(current_market_price)
        else:
            current_price = candles["close"].iloc[-1]
        reference_price_value = current_price * (1 + price_multiplier)
        
        # 确保spread_multiplier和reference_price是Series（与candles长度一致）
        candles["spread_multiplier"] = natr
        candles["reference_price"] = reference_price_value  # 使用计算出的标量值
        self.processed_data = {
            "reference_price": Decimal(reference_price_value),
            "spread_multiplier": Decimal(candles["spread_multiplier"].iloc[-1]),
            "features": candles
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
