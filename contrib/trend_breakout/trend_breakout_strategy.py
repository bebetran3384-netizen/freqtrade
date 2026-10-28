# pragma pylint: disable=missing-docstring, invalid-name, pointless-string-statement
# isort: skip_file
import talib.abstract as ta
from pandas import DataFrame

from freqtrade.strategy import IntParameter, IStrategy, informative


class TrendBreakoutStrategy(IStrategy):
    """
    Long-only trend following on 4h candles (Donchian channel breakout).

    - Regime filter: the pair and BTC must both be above their daily EMA50,
      and the pair above its 4h EMA200.
    - Entry: close breaks above the highest high of the previous `breakout_len` candles.
    - Exit: close breaks below the lowest low of the previous `exit_len` candles.
    - A fixed -15% stoploss is kept only as a catastrophe guard.
      There is no ROI target, so winners are allowed to run.

    A walk-forward test showed the earlier ATR trailing stop and volume filter
    added nothing: the widest stop tested was picked in 3 of 4 windows and the
    volume filter barely changed results, so both were removed.
    """

    INTERFACE_VERSION = 3

    can_short: bool = False
    timeframe = "4h"

    # Effectively disabled - exits are handled by the exit signal.
    minimal_roi = {"0": 100}

    stoploss = -0.15
    trailing_stop = False

    process_only_new_candles = True
    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = False

    startup_candle_count: int = 200

    # Hyperoptable parameters
    breakout_len = IntParameter(low=20, high=120, default=60, space="buy", optimize=True)
    exit_len = IntParameter(low=6, high=72, default=18, space="sell", optimize=True)

    order_types = {
        "entry": "limit",
        "exit": "limit",
        "stoploss": "market",
        "stoploss_on_exchange": False,
    }

    order_time_in_force = {"entry": "GTC", "exit": "GTC"}

    plot_config = {
        "main_plot": {
            "ema200": {"color": "white"},
        },
    }

    @informative("1d")
    def populate_indicators_1d(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema50"] = ta.EMA(dataframe, timeperiod=50)
        return dataframe

    @informative("1d", "BTC/{stake}", fmt="btc_{column}_{timeframe}")
    def populate_indicators_btc_1d(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema50"] = ta.EMA(dataframe, timeperiod=50)
        return dataframe

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema200"] = ta.EMA(dataframe, timeperiod=200)
        dataframe["regime_ok"] = (
            (dataframe["close_1d"] > dataframe["ema50_1d"])
            & (dataframe["btc_close_1d"] > dataframe["btc_ema50_1d"])
            & (dataframe["close"] > dataframe["ema200"])
        )
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        breakout_high = dataframe["high"].rolling(self.breakout_len.value).max().shift(1)
        dataframe.loc[
            dataframe["regime_ok"]
            & (dataframe["close"] > breakout_high)
            & (dataframe["volume"] > 0),
            "enter_long",
        ] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        exit_low = dataframe["low"].rolling(self.exit_len.value).min().shift(1)
        dataframe.loc[
            (dataframe["close"] < exit_low) & (dataframe["volume"] > 0),
            "exit_long",
        ] = 1
        return dataframe
