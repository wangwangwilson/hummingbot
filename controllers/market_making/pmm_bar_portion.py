from decimal import Decimal
from typing import List

import numpy as np
import pandas as pd
try:
    import pandas_ta as ta  # noqa: F401
except ImportError:
    ta = None  # pandas-ta not available, but may not be needed
    # 简单的natr实现
    class SimpleTA:
        @staticmethod
        def natr(high, low, close, length=14):
            """简单的NATR实现"""
            tr = pd.concat([high - low, abs(high - close.shift()), abs(low - close.shift())], axis=1).max(axis=1)
            atr = tr.rolling(window=length).mean()
            natr = (atr / close) * 100
            return natr
    
    ta = SimpleTA()
from pydantic import Field, field_validator
from pydantic_core.core_schema import ValidationInfo

from hummingbot.data_feed.candles_feed.data_types import CandlesConfig
from hummingbot.strategy_v2.controllers.market_making_controller_base import (
    MarketMakingControllerBase,
    MarketMakingControllerConfigBase,
)
from hummingbot.strategy_v2.executors.position_executor.data_types import PositionExecutorConfig


class PMMBarPortionControllerConfig(MarketMakingControllerConfigBase):
    """
    PMM Bar Portion Controller Configuration
    
    Based on the paper "Market Making in Crypto" by Stoikov et al. (2024)
    This controller uses Bar Portion (BP) alpha signal for mid-price adjustment.
    
    Bar Portion = (Close - Open) / (High - Low)
    Range: -1 to 1, capturing mean-reversion behavior.
    """
    controller_name: str = "pmm_bar_portion"
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
        default="1m",
        json_schema_extra={
            "prompt": "Enter the candle interval (e.g., 1m, 5m, 1h, 1d): ",
            "prompt_on_new": True})
    natr_length: int = Field(
        default=14,
        json_schema_extra={"prompt": "Enter the NATR length for volatility measurement: ", "prompt_on_new": True})
    training_window: int = Field(
        default=51840,
        json_schema_extra={
            "prompt": "Enter the training window size in candles (default: 51840 for 36 days of 1m data): ",
            "prompt_on_new": True})
    atr_length: int = Field(
        default=10,
        json_schema_extra={"prompt": "Enter the ATR length for stick length calculation: ", "prompt_on_new": True})
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


class PMMBarPortionController(MarketMakingControllerBase):
    """
    PMM Bar Portion Controller
    
    Implements the Bar Portion (BP) alpha signal from the paper:
    "Market Making in Crypto" by Stoikov et al. (2024)
    
    Key features:
    - Uses Bar Portion signal to predict price movements
    - Rolling linear regression for alpha generation
    - NATR-based dynamic spread adjustment
    - Triple Barrier strategy for risk management
    """

    def __init__(self, config: PMMBarPortionControllerConfig, *args, **kwargs):
        self.config = config
        # 使用一个足够大的max_records以覆盖整个回测区间，避免只读取尾部少量K线
        self.max_records = 200_000
        if len(self.config.candles_config) == 0:
            self.config.candles_config = [CandlesConfig(
                connector=config.candles_connector,
                trading_pair=config.candles_trading_pair,
                interval=config.interval,
                max_records=self.max_records
            )]
        super().__init__(config, *args, **kwargs)
        
        # Store regression coefficients
        self._regression_coef = None
        self._regression_intercept = None

    def calculate_bar_portion(self, df: pd.DataFrame) -> pd.Series:
        """
        Calculate Bar Portion signal
        
        Formula: BP = (Close - Open) / (High - Low)
        Range: -1 to 1
        
        Returns:
            pd.Series: Bar Portion values
        """
        high_low_diff = df["high"] - df["low"]
        # Avoid division by zero
        high_low_diff = high_low_diff.replace(0, np.nan)
        
        bar_portion = (df["close"] - df["open"]) / high_low_diff
        # Clip to [-1, 1] range
        bar_portion = bar_portion.clip(-1, 1)
        
        return bar_portion.fillna(0)

    def calculate_stick_length(self, df: pd.DataFrame, atr_length: int = 10) -> pd.Series:
        """
        Calculate Stick Length normalized by ATR
        
        Formula: Stick Length = (High - Low) / ATR
        
        Args:
            df: Candle dataframe
            atr_length: ATR lookback period
            
        Returns:
            pd.Series: Normalized stick length
        """
        atr = ta.atr(df["high"], df["low"], df["close"], length=atr_length)
        stick_length = (df["high"] - df["low"]) / atr.shift(1)
        return stick_length.fillna(1)

    def fit_linear_regression(self, X: pd.Series, y: pd.Series):
        """
        Fit linear regression model: y = a*X + b
        
        Args:
            X: Independent variable (Bar Portion)
            y: Dependent variable (Returns)
        """
        # Remove NaN values
        valid_mask = ~(X.isna() | y.isna())
        X_clean = X[valid_mask].values.reshape(-1, 1)
        y_clean = y[valid_mask].values
        
        if len(X_clean) < 100:  # Need minimum data for regression
            return
        
        # Simple linear regression using numpy
        X_mean = X_clean.mean()
        y_mean = y_clean.mean()
        
        numerator = ((X_clean.flatten() - X_mean) * (y_clean - y_mean)).sum()
        denominator = ((X_clean.flatten() - X_mean) ** 2).sum()
        
        if denominator != 0:
            self._regression_coef = numerator / denominator
            self._regression_intercept = y_mean - self._regression_coef * X_mean

    def predict_price_shift(self, current_bp: float) -> float:
        """
        Predict price shift based on Bar Portion signal
        
        论文逻辑：BP信号是均值回归信号
        - BP高（>0.7）→ 预测价格会回调（下跌）→ 应该向下偏斜（更多卖单）
        - BP低（<-0.7）→ 预测价格会反弹（上涨）→ 应该向上偏斜（更多买单）
        
        Args:
            current_bp: Current Bar Portion value
            
        Returns:
            float: Predicted price multiplier (e.g., -0.001 for 0.1% downward shift when BP is high)
        """
        if self._regression_coef is None or self._regression_intercept is None:
            # 如果没有回归模型，使用简单的均值回归逻辑
            # BP高 → 预测回调 → 降低价格（更多卖单）
            max_shift = 0.005  # 0.5% maximum shift
            return -float(current_bp) * max_shift
        
        # Predict next return using regression
        predicted_return = self._regression_coef * current_bp + self._regression_intercept
        
        # Convert to price multiplier and cap the shift
        max_shift = 0.005  # 0.5% maximum shift
        price_multiplier = np.clip(predicted_return, -max_shift, max_shift)
        
        return float(price_multiplier)

    async def update_processed_data(self):
        """
        Update processed data including:
        - Bar Portion calculation
        - Linear regression training
        - Price prediction
        - Spread calculation
        
        If use_future_data is True, uses the next candle's price direction as signal.
        """
        # 如果启用未来数据，使用下一根K线的价格方向
        if self.config.use_future_data:
            candles = self.market_data_provider.get_candles_df(
                connector_name=self.config.candles_connector,
                trading_pair=self.config.candles_trading_pair,
                interval=self.config.interval,
                max_records=max(self.max_records, 10000)  # 获取更多数据以确保包含未来数据
            )
            
            if len(candles) >= 2 and 'timestamp' in candles.columns:
                # 在回测中，需要根据当前时间戳找到对应的K线和下一根K线
                current_time = self.market_data_provider.time()
                
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
                        # 计算未来收益率
                        future_return = (future_close - current_close) / current_close if current_close > 0 else 0.0
                    else:
                        # 没有未来数据，使用当前价格
                        future_return = 0.0
                else:
                    # 如果找不到当前时间对应的K线，使用最新的K线
                    current_close = candles["close"].iloc[-1]
                    future_return = 0.0
                
                # 使用未来收益率调整reference_price
                from hummingbot.core.data_type.common import PriceType
                try:
                    current_market_price = self.market_data_provider.get_price_by_type(
                        connector_name=self.config.candles_connector,
                        trading_pair=self.config.candles_trading_pair,
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
                price_shift = max(-max_shift, min(max_shift, future_return))
                reference_price = base_price * (1 + price_shift)
                
                # 计算NATR
                natr = ta.natr(candles["high"], candles["low"], candles["close"], 
                              length=self.config.natr_length) / 100
                if natr is None or natr.empty or pd.isna(natr.iloc[-1]):
                    natr_value = Decimal("0.01")
                else:
                    natr_value = Decimal(float(natr.iloc[-1]))
                    if natr_value <= 0 or natr_value > Decimal("0.1"):
                        natr_value = Decimal("0.01")
                
                candles["reference_price"] = reference_price
                candles["spread_multiplier"] = natr if natr is not None and not natr.empty else pd.Series([float(natr_value)] * len(candles), index=candles.index)
                candles["future_return"] = future_return
                
                self.processed_data = {
                    "reference_price": Decimal(str(reference_price)),
                    "spread_multiplier": natr_value,
                    "features": candles
                }
                return
        
        candles = self.market_data_provider.get_candles_df(
            connector_name=self.config.candles_connector,
            trading_pair=self.config.candles_trading_pair,
            interval=self.config.interval,
            max_records=self.max_records
        )
        
        # 降低数据要求：至少需要training_window + natr_length的数据
        min_required = max(self.config.training_window, self.config.natr_length, self.config.atr_length, 30)
        
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
        
        if len(candles) < min_required:
            # Not enough data, but still use current market price
            if len(candles) == 0:
                # 如果完全没有数据，使用当前市场价格
                current_price = current_market_price
                
                self.processed_data = {
                    "reference_price": current_price,
                    "spread_multiplier": Decimal("0.01"),  # 1% default spread
                    "features": pd.DataFrame()
                }
                return
            
            # 即使数据不足，也要使用当前市场价格并尝试计算因子
            # 优先使用当前市场价格，如果没有则使用candles的close价格
            if current_market_price and current_market_price > 0:
                current_price = current_market_price
            else:
                current_price = Decimal(candles["close"].iloc[-1])
                if current_price == 0:
                    # 如果close价格为0，尝试使用high或low的平均值
                    if len(candles) > 0:
                        current_price = Decimal((float(candles["high"].iloc[-1]) + float(candles["low"].iloc[-1])) / 2)
            
            # 计算简单的BP因子（即使数据不足）
            if len(candles) >= 1:
                candles["bar_portion"] = self.calculate_bar_portion(candles)
            
            # 尝试计算NATR（即使数据不足）
            if len(candles) >= self.config.natr_length:
                try:
                    natr = ta.natr(candles["high"], candles["low"], candles["close"], 
                                   length=self.config.natr_length) / 100
                    if natr is not None and not natr.empty and not pd.isna(natr.iloc[-1]):
                        natr_value = Decimal(float(natr.iloc[-1]))
                        if natr_value <= 0 or natr_value > Decimal("0.1"):
                            natr_value = Decimal("0.01")
                    else:
                        natr_value = Decimal("0.01")
                except:
                    natr_value = Decimal("0.01")
            else:
                natr_value = Decimal("0.01")
            
            # 尝试计算价格偏移（即使数据不足）
            price_shift = 0.0
            if len(candles) >= 2:
                try:
                    # 使用简单的BP信号
                    current_bp = candles["bar_portion"].iloc[-1] if "bar_portion" in candles.columns else 0.0
                    # 简单的线性关系：BP * 0.1% 作为价格偏移
                    price_shift = float(current_bp) * 0.001
                except:
                    price_shift = 0.0
            
            reference_price = current_price * (1 + price_shift)
            if reference_price <= 0:
                reference_price = current_price
            
            # 确保features DataFrame包含reference_price和spread_multiplier列
            candles["reference_price"] = float(reference_price)
            candles["spread_multiplier"] = float(natr_value)
            
            self.processed_data = {
                "reference_price": reference_price,
                "spread_multiplier": natr_value,
                "features": candles
            }
            return
        
        # Calculate Bar Portion signal
        candles["bar_portion"] = self.calculate_bar_portion(candles)
        
        # Calculate returns for training
        candles["returns"] = candles["close"].pct_change()
        
        # Use training window for regression (if we have enough data)
        if len(candles) >= self.config.training_window:
            train_df = candles.iloc[-self.config.training_window:]
        else:
            train_df = candles
        
        # 检查是否有足够的数据进行训练
        if len(train_df) < 2:
            # 数据不足，使用默认值
            current_price = Decimal(candles["close"].iloc[-1]) if len(candles) > 0 else Decimal("0")
            if current_price == 0:
                # 尝试从market_data_provider获取价格
                try:
                    from hummingbot.core.data_type.common import PriceType
                    current_price = Decimal(self.market_data_provider.get_price_by_type(
                        self.config.candles_connector, self.config.candles_trading_pair, PriceType.MidPrice))
                except:
                    pass
            
            self.processed_data = {
                "reference_price": current_price,
                "spread_multiplier": Decimal("0.01"),
                "features": candles
            }
            return
        
        # Fit regression model: predict next return from current Bar Portion
        # 论文逻辑：BP信号是均值回归信号，BP高时预测未来收益为负（回调）
        # 因此我们需要预测：未来收益 = -f(BP)，即BP高时收益为负
        # Shift returns forward to predict next period
        X_train = train_df["bar_portion"].iloc[:-1]
        y_train = train_df["returns"].iloc[1:]
        
        self.fit_linear_regression(X_train, y_train)
        
        # Get current Bar Portion and predict price shift
        current_bp = candles["bar_portion"].iloc[-1]
        
        # 论文逻辑：BP信号与未来收益呈单调递减关系（均值回归）
        # BP高（>0.7）→ 预测价格会回调（下跌）→ 应该向下偏斜（更多卖单）
        # BP低（<-0.7）→ 预测价格会反弹（上涨）→ 应该向上偏斜（更多买单）
        # 
        # 如果回归系数为正，说明BP高时收益为正（趋势），这与论文的均值回归逻辑相反
        # 如果回归系数为负，说明BP高时收益为负（回调），符合论文逻辑
        # 
        # 为了确保符合论文逻辑，我们使用负的预测收益：
        # - 如果BP高，预测收益为负，降低reference_price（更多卖单）
        # - 如果BP低，预测收益为正，提高reference_price（更多买单）
        predicted_return = self.predict_price_shift(current_bp)
        
        # 根据论文逻辑，BP是均值回归信号，应该取反
        # 但先检查回归系数的符号，如果已经是负的，说明符合论文逻辑
        if self._regression_coef is not None:
            # 如果回归系数为正，说明BP高时收益为正（趋势），需要取反
            # 如果回归系数为负，说明BP高时收益为负（回调），符合论文逻辑
            if self._regression_coef > 0:
                # 回归系数为正，说明是趋势信号，需要取反以符合均值回归逻辑
                price_shift = -predicted_return
            else:
                # 回归系数为负，说明已经是均值回归信号，直接使用
                price_shift = predicted_return
        else:
            # 如果没有回归系数，使用简单的均值回归逻辑
            # BP高 → 预测回调 → 降低价格（更多卖单）
            # BP低 → 预测反弹 → 提高价格（更多买单）
            max_shift = 0.005  # 0.5%最大偏移
            price_shift = -float(current_bp) * max_shift  # 取反，BP高时降低价格
        
        # Calculate NATR for dynamic spread
        natr = ta.natr(candles["high"], candles["low"], candles["close"], 
                       length=self.config.natr_length) / 100
        
        # Ensure NATR is valid (not NaN or None)
        if natr is None or natr.empty or pd.isna(natr.iloc[-1]):
            natr_value = Decimal("0.01")  # 1% default
        else:
            natr_value = Decimal(float(natr.iloc[-1]))
            # Ensure NATR is reasonable (between 0.001 and 0.1, i.e., 0.1% to 10%)
            if natr_value <= 0 or natr_value > Decimal("0.1"):
                natr_value = Decimal("0.01")
        
        # Calculate adjusted reference price
        # 关键修复：优先使用当前市场价格，确保reference_price随市场变化
        if current_market_price and current_market_price > 0:
            current_close = float(current_market_price)
        else:
            current_close = candles["close"].iloc[-1]
            if current_close == 0 or pd.isna(current_close):
                # Fallback to high/low average
                current_close = (candles["high"].iloc[-1] + candles["low"].iloc[-1]) / 2
        
        reference_price = current_close * (1 + price_shift)
        
        # Ensure reference_price is valid
        if reference_price <= 0 or pd.isna(reference_price):
            reference_price = current_close
        
        # Store processed data
        candles["spread_multiplier"] = natr if natr is not None and not natr.empty else pd.Series([float(natr_value)] * len(candles), index=candles.index)
        candles["reference_price"] = reference_price
        candles["price_shift"] = price_shift
        
        self.processed_data = {
            "reference_price": Decimal(reference_price),
            "spread_multiplier": natr_value,
            "features": candles,
            "bar_portion": float(current_bp),
            "regression_coef": self._regression_coef if self._regression_coef else 0.0,
        }

    def get_executor_config(self, level_id: str, price: Decimal, amount: Decimal):
        """
        Create position executor config with triple barrier strategy
        
        Args:
            level_id: Level identifier (e.g., "buy_0", "sell_1")
            price: Entry price
            amount: Position amount
            
        Returns:
            PositionExecutorConfig: Executor configuration
        """
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
