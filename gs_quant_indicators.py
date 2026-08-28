import numpy as np
import pandas as pd


def add_indicators(df):
    df = df.copy()
    close = df["Close"]
    high = df["High"]
    low = df["Low"]

    # Trend
    df["MA20"] = close.rolling(20).mean()
    df["MA50"] = close.rolling(50).mean()
    df["MA200"] = close.rolling(200).mean()
    df["EMA20"] = close.ewm(span=20, adjust=False).mean()

    # Momentum
    df["RET20"] = close.pct_change(20)
    df["RET60"] = close.pct_change(60)
    df["RET120"] = close.pct_change(120)

    # RSI - independent implementation for this new system
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/14, adjust=False, min_periods=14).mean()
    avg_loss = loss.ewm(alpha=1/14, adjust=False, min_periods=14).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    df["RSI"] = 100 - (100 / (1 + rs))

    # MACD
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    df["MACD"] = ema12 - ema26
    df["MACD_SIGNAL"] = df["MACD"].ewm(span=9, adjust=False).mean()

    # Volatility
    daily_ret = close.pct_change()
    df["VOL20"] = daily_ret.rolling(20).std() * np.sqrt(252)

    # ATR
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    df["ATR14"] = tr.rolling(14).mean()
    df["ATR_PCT"] = df["ATR14"] / close

    # Bollinger position
    mid = close.rolling(20).mean()
    std = close.rolling(20).std()
    upper = mid + 2 * std
    lower = mid - 2 * std
    df["BB_POS"] = (close - lower) / (upper - lower)

    # Drawdown from 252-day high
    high252 = close.rolling(252).max()
    df["DD252"] = close / high252 - 1

    # Volume
    df["VOL_RATIO"] = df["Volume"] / df["Volume"].rolling(20).mean()

    return df.dropna()
