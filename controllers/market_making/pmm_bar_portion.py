from decimal import Decimal
from typing import List

import numpy as np
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
        # Need enough history for training window + some buffer
        self.max_records = max(config.training_window, config.natr_length, config.atr_length) + 100
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
        
        Args:
            current_bp: Current Bar Portion value
            
        Returns:
            float: Predicted price multiplier (e.g., 0.001 for 0.1% shift)
        """
        if self._regression_coef is None or self._regression_intercept is None:
            return 0.0
        
        # Predict next return
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
        """
        candles = self.market_data_provider.get_candles_df(
            connector_name=self.config.candles_connector,
            trading_pair=self.config.candles_trading_pair,
            interval=self.config.interval,
            max_records=self.max_records
        )
        
        if len(candles) < 100:
            # Not enough data, use default values
            self.processed_data = {
                "reference_price": Decimal(candles["close"].iloc[-1]),
                "spread_multiplier": Decimal("0.01"),  # 1% default spread
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
        
        # Fit regression model: predict next return from current Bar Portion
        # Shift returns forward to predict next period
        X_train = train_df["bar_portion"].iloc[:-1]
        y_train = train_df["returns"].iloc[1:]
        
        self.fit_linear_regression(X_train, y_train)
        
        # Get current Bar Portion and predict price shift
        current_bp = candles["bar_portion"].iloc[-1]
        price_shift = self.predict_price_shift(current_bp)
        
        # Calculate NATR for dynamic spread
        natr = ta.natr(candles["high"], candles["low"], candles["close"], 
                       length=self.config.natr_length) / 100
        
        # Calculate adjusted reference price
        current_close = candles["close"].iloc[-1]
        reference_price = current_close * (1 + price_shift)
        
        # Store processed data
        candles["spread_multiplier"] = natr
        candles["reference_price"] = reference_price
        candles["price_shift"] = price_shift
        
        self.processed_data = {
            "reference_price": Decimal(reference_price),
            "spread_multiplier": Decimal(natr.iloc[-1]),
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
