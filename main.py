import os
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import requests
import yfinance as yf
import pandas_market_calendars as mcal


# ============================================================
# 기본 설정
# ============================================================

BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")

TEST_MODE = (
    os.environ.get("TEST_MODE", "false").lower()
    == "true"
)

NY_TZ = ZoneInfo("America/New_York")

YAHOO_MAX_WAIT_MINUTES = 30
YAHOO_RETRY_INTERVAL_MINUTES = 5


# ============================================================
# 종목
# ============================================================

TICKERS = [
    "QQQ",
    "SPY",
    "MSFT",
    "AMZN",
    "GOOG",
    "AAPL",
    "META",
    "NVDA",
    "TSLA",
    "PLTR",
]

ALWAYS_SHOW = {
    "QQQ",
    "SPY",
}

TECH_STOCKS = {
    "MSFT",
    "AMZN",
    "GOOG",
    "AAPL",
    "META",
    "NVDA",
    "TSLA",
    "PLTR",
}


# ============================================================
# RSI / 전략 설정
# ============================================================

RSI_LENGTH = 14

OVERSOLD_LEVEL = 30.0
OVERBOUGHT_LEVEL = 70.0

PIVOT_LEFT = 3
PIVOT_RIGHT = 3

DIV_MIN_RANGE = 3
DIV_MAX_RANGE = 80

MIN_BARS = 5
MAX_BARS = 40

MIN_HL_PERCENT = 0.15

SIGNAL_COOLDOWN = 25
SIGNAL_LOOKBACK = 120


# ============================================================
# Telegram
# ============================================================

def send_telegram(message):

    if not BOT_TOKEN:
        raise Exception(
            "BOT_TOKEN이 설정되지 않았습니다."
        )

    if not CHAT_ID:
        raise Exception(
            "CHAT_ID가 설정되지 않았습니다."
        )

    url = (
        f"https://api.telegram.org/"
        f"bot{BOT_TOKEN}/sendMessage"
    )

    response = requests.post(
        url,
        data={
            "chat_id": CHAT_ID,
            "text": message,
        },
        timeout=20,
    )

    response.raise_for_status()


# ============================================================
# RSI
# ============================================================

def calculate_rsi(series, length=14):

    series = pd.to_numeric(
        series,
        errors="coerce",
    )

    delta = series.diff()

    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(
        alpha=1 / length,
        adjust=False,
        min_periods=length,
    ).mean()

    avg_loss = loss.ewm(
        alpha=1 / length,
        adjust=False,
        min_periods=length,
    ).mean()

    rs = (
        avg_gain
        / avg_loss.replace(0, np.nan)
    )

    rsi = 100 - (
        100 / (1 + rs)
    )

    rsi = rsi.mask(
        avg_loss == 0,
        100,
    )

    rsi = rsi.mask(
        avg_gain == 0,
        0,
    )

    return rsi


# ============================================================
# RSI 표시
# ============================================================

def rsi_value_text(
    value,
    weekly=False,
):

    if pd.isna(value):
        return "-"

    value = float(value)

    if weekly and value <= 35:
        mark = "🟢🟢"

    elif not weekly and value <= 35:
        mark = "🟢"

    else:
        mark = ""

    return f"{value:.2f}{mark}"


def rsi_change_text(
    current,
    previous,
):

    if (
        pd.isna(current)
        or pd.isna(previous)
    ):
        return "-"

    diff = (
        float(current)
        - float(previous)
    )

    return f"{diff:+.2f}"


# ============================================================
# NYSE 실제 마감시간
# ============================================================

def get_nyse_market_close(now_ny):

    nyse = mcal.get_calendar("NYSE")

    today = now_ny.date()

    schedule = nyse.schedule(
        start_date=today,
        end_date=today,
    )

    if schedule.empty:
        return None

    market_close = (
        schedule.iloc[0]["market_close"]
    )

    if market_close.tzinfo is None:
        market_close = (
            market_close.tz_localize("UTC")
        )

    return market_close.tz_convert(
        "America/New_York"
    )


# ============================================================
# 미국장 상태 확인
# ============================================================

def check_market_status():

    now_ny = datetime.now(NY_TZ)

    print(
        "현재 뉴욕 시간:",
        now_ny.strftime(
            "%Y-%m-%d %H:%M:%S %Z"
        ),
    )

    if TEST_MODE:

        print("🧪 TEST MODE")

        return True, None, now_ny

    market_close = (
        get_nyse_market_close(now_ny)
    )

    if market_close is None:

        print(
            "오늘은 NYSE 휴장일입니다."
        )

        return False, None, now_ny

    print(
        "NYSE 실제 마감:",
        market_close.strftime(
            "%Y-%m-%d %H:%M:%S %Z"
        ),
    )

    if now_ny < market_close:

        print(
            "아직 미국장이 마감되지 않았습니다."
        )

        return (
            False,
            market_close,
            now_ny,
        )

    # ========================================================
    # 마감 후 최대 180분까지 허용
    #
    # 서머타임:
    # 미국장 05:00 KST 마감
    # 한국 07:15 실행
    # → 135분 후
    #
    # 겨울시간:
    # 미국장 06:00 KST 마감
    # 한국 07:15 실행
    # → 75분 후
    #
    # 따라서 180분이면 1년 내내 안전
    # ========================================================

    if (
        now_ny - market_close
        > timedelta(minutes=180)
    ):

        print(
            "미국장 마감 후 "
            "180분이 지났습니다."
        )

        return (
            False,
            market_close,
            now_ny,
        )

    return (
        True,
        market_close,
        now_ny,
    )


# ============================================================
# Pivot Low
# ============================================================

def is_pivot_low(
    lows,
    index,
    left,
    right,
):

    pivot_index = index - right

    if pivot_index - left < 0:
        return False

    if pivot_index + right >= len(lows):
        return False

    pivot_value = float(
        lows.iloc[pivot_index]
    )

    left_values = lows.iloc[
        pivot_index - left:
        pivot_index
    ]

    right_values = lows.iloc[
        pivot_index + 1:
        pivot_index + right + 1
    ]

    return (
        len(left_values) == left
        and len(right_values) == right
        and pivot_value
        <= float(left_values.min())
        and pivot_value
        <= float(right_values.min())
    )


# ============================================================
# Pivot High
# ============================================================

def is_pivot_high(
    highs,
    index,
    left,
    right,
):

    pivot_index = index - right

    if pivot_index - left < 0:
        return False

    if pivot_index + right >= len(highs):
        return False

    pivot_value = float(
        highs.iloc[pivot_index]
    )

    left_values = highs.iloc[
        pivot_index - left:
        pivot_index
    ]

    right_values = highs.iloc[
        pivot_index + 1:
        pivot_index + right + 1
    ]

    return (
        len(left_values) == left
        and len(right_values) == right
        and pivot_value
        >= float(left_values.max())
        and pivot_value
        >= float(right_values.max())
    )


# ============================================================
# Bars Since
# ============================================================

def bars_since(condition):

    condition = pd.Series(
        condition,
        index=condition.index,
    )

    result = []

    count = np.nan

    for value in condition:

        if bool(value):
            count = 0

        elif not pd.isna(count):
            count += 1

        result.append(count)

    return pd.Series(
        result,
        index=condition.index,
    )


# ============================================================
# 전략
# ============================================================

def run_strategy(df):

    df = df.copy()

    required = [
        "open",
        "high",
        "low",
        "close",
    ]

    for column in required:

        if column not in df.columns:
            raise ValueError(
                f"필수 컬럼 없음: {column}"
            )

        df[column] = pd.to_numeric(
            df[column],
            errors="coerce",
        )

    df = df.dropna(
        subset=required
    ).reset_index(drop=True)

    if len(df) < 100:
        raise ValueError(
            f"데이터가 너무 적습니다: "
            f"{len(df)}개"
        )

    # --------------------------------------------------------
    # RSI
    # --------------------------------------------------------

    df["rsi"] = calculate_rsi(
        df["close"],
        RSI_LENGTH,
    )

    df["is_oversold"] = (
        df["rsi"]
        <= OVERSOLD_LEVEL
    )

    df["is_overbought"] = (
        df["rsi"]
        >= OVERBOUGHT_LEVEL
    )

    # --------------------------------------------------------
    # Pivot
    # --------------------------------------------------------

    df["pivot_low"] = [
        is_pivot_low(
            df["low"],
            i,
            PIVOT_LEFT,
            PIVOT_RIGHT,
        )
        for i in range(len(df))
    ]

    df["pivot_high"] = [
        is_pivot_high(
            df["high"],
            i,
            PIVOT_LEFT,
            PIVOT_RIGHT,
        )
        for i in range(len(df))
    ]

    df["pivot_low_rsi"] = np.nan
    df["pivot_high_rsi"] = np.nan

    for i in range(len(df)):

        pivot_index = (
            i - PIVOT_RIGHT
        )

        if (
            pivot_index >= 0
            and df["pivot_low"].iloc[i]
        ):

            df.loc[
                i,
                "pivot_low_rsi",
            ] = df["rsi"].iloc[
                pivot_index
            ]

        if (
            pivot_index >= 0
            and df["pivot_high"].iloc[i]
        ):

            df.loc[
                i,
                "pivot_high_rsi",
            ] = df["rsi"].iloc[
                pivot_index
            ]

    # --------------------------------------------------------
    # Bullish Divergence
    # --------------------------------------------------------

    df["bull_divergence"] = False

    previous_price_pivots = []
    previous_rsi_pivots = []
    previous_pivot_bars = []

    for i in range(len(df)):

        if not df["pivot_low"].iloc[i]:
            continue

        current_pivot_bar = (
            i - PIVOT_RIGHT
        )

        current_price = float(
            df["low"].iloc[
                current_pivot_bar
            ]
        )

        current_rsi = df["rsi"].iloc[
            current_pivot_bar
        ]

        if pd.isna(current_rsi):
            continue

        current_rsi = float(
            current_rsi
        )

        for (
            prev_price,
            prev_rsi,
            prev_bar,
        ) in zip(
            previous_price_pivots,
            previous_rsi_pivots,
            previous_pivot_bars,
        ):

            bars_between = (
                current_pivot_bar
                - prev_bar
            )

            if (
                DIV_MIN_RANGE
                <= bars_between
                <= DIV_MAX_RANGE
                and current_price
                < prev_price
                and current_rsi
                > prev_rsi
            ):

                df.loc[
                    i,
                    "bull_divergence",
                ] = True

                break

        previous_price_pivots.insert(
            0,
            current_price,
        )

        previous_rsi_pivots.insert(
            0,
            current_rsi,
        )

        previous_pivot_bars.insert(
            0,
            current_pivot_bar,
        )

        if len(
            previous_price_pivots
        ) > 20:

            previous_price_pivots.pop()
            previous_rsi_pivots.pop()
            previous_pivot_bars.pop()

    # --------------------------------------------------------
    # Higher Low / Lower High
    # --------------------------------------------------------

    short_window = max(
        4,
        int(
            MAX_BARS * 0.45
        ),
    )

    df["lowest_40"] = (
        df["low"]
        .rolling(
            MAX_BARS,
            min_periods=MAX_BARS,
        )
        .min()
    )

    df["lowest_short"] = (
        df["low"]
        .rolling(
            short_window,
            min_periods=short_window,
        )
        .min()
    )

    df["highest_40"] = (
        df["high"]
        .rolling(
            MAX_BARS,
            min_periods=MAX_BARS,
        )
        .max()
    )

    df["highest_short"] = (
        df["high"]
        .rolling(
            short_window,
            min_periods=short_window,
        )
        .max()
    )

    low_equals_lowest = pd.Series(
        False,
        index=df.index,
    )

    valid_low = (
        df["low"].notna()
        & df["lowest_40"].notna()
    )

    low_equals_lowest.loc[
        valid_low
    ] = (
        np.abs(
            df.loc[
                valid_low,
                "low",
            ]
            - df.loc[
                valid_low,
                "lowest_40",
            ]
        )
        <= 1e-10
    )

    high_equals_highest = pd.Series(
        False,
        index=df.index,
    )

    valid_high = (
        df["high"].notna()
        & df["highest_40"].notna()
    )

    high_equals_highest.loc[
        valid_high
    ] = (
        np.abs(
            df.loc[
                valid_high,
                "high",
            ]
            - df.loc[
                valid_high,
                "highest_40",
            ]
        )
        <= 1e-10
    )

    df["bars_since_low"] = bars_since(
        low_equals_lowest
    )

    df["bars_since_high"] = bars_since(
        high_equals_highest
    )

    # --------------------------------------------------------
    # Signal
    # --------------------------------------------------------

    stage1_long = False
    stage2_long = False
    stage1_short = False

    last_long_bar = None
    last_short_bar = None

    long_signal_list = []
    short_signal_list = []

    long_reason_list = []
    short_reason_list = []

    for i in range(len(df)):

        is_oversold = bool(
            df["is_oversold"].iloc[i]
        )

        is_overbought = bool(
            df["is_overbought"].iloc[i]
        )

        bull_div_now = bool(
            df[
                "bull_divergence"
            ].iloc[i]
        )

        # ----------------------------------------------------
        # Long Stage 1
        # ----------------------------------------------------

        if is_oversold:

            if not stage1_long:

                stage1_long = True
                stage2_long = False

            stage1_short = False

        # ----------------------------------------------------
        # Long Stage 2
        # ----------------------------------------------------

        if (
            stage1_long
            and bull_div_now
            and not stage2_long
        ):

            stage2_long = True

        low1 = df[
            "lowest_40"
        ].iloc[i]

        low2 = df[
            "lowest_short"
        ].iloc[i]

        bars_since_low = df[
            "bars_since_low"
        ].iloc[i]

        higher_low = (
            not pd.isna(low1)
            and not pd.isna(low2)
            and float(low2)
            > float(low1)
            * (
                1
                + MIN_HL_PERCENT
                / 100
            )
        )

        bars_ok_long = (
            not pd.isna(
                bars_since_low
            )
            and MIN_BARS
            <= bars_since_low
            <= MAX_BARS
        )

        circular_long = (
            higher_low
            and bars_ok_long
        )

        cooldown_long = (
            last_long_bar is None
            or i - last_long_bar
            >= SIGNAL_COOLDOWN
        )

        long_signal = (
            stage1_long
            and circular_long
            and cooldown_long
        )

        long_reason = ""

        if long_signal:

            if stage2_long:

                long_reason = (
                    "과매도 → "
                    "상승 다이버전스 → "
                    "Higher Low"
                )

            else:

                long_reason = (
                    "과매도 → "
                    "Higher Low"
                )

            last_long_bar = i

            stage2_long = False

        if not is_oversold:

            stage1_long = False
            stage2_long = False

        # ----------------------------------------------------
        # Short Stage
        # ----------------------------------------------------

        if is_overbought:

            stage1_short = True

            stage1_long = False
            stage2_long = False

        high1 = df[
            "highest_40"
        ].iloc[i]

        high2 = df[
            "highest_short"
        ].iloc[i]

        bars_since_high = df[
            "bars_since_high"
        ].iloc[i]

        lower_high = (
            not pd.isna(high1)
            and not pd.isna(high2)
            and float(high2)
            < float(high1)
            * (
                1
                - MIN_HL_PERCENT
                / 100
            )
        )

        bars_ok_short = (
            not pd.isna(
                bars_since_high
            )
            and MIN_BARS
            <= bars_since_high
            <= MAX_BARS
        )

        circular_short = (
            lower_high
            and bars_ok_short
        )

        cooldown_short = (
            last_short_bar is None
            or i - last_short_bar
            >= SIGNAL_COOLDOWN
        )

        short_signal = (
            stage1_short
            and circular_short
            and cooldown_short
        )

        short_reason = ""

        if short_signal:

            short_reason = (
                "과매수 → Lower High"
            )

            last_short_bar = i

        long_signal_list.append(
            long_signal
        )

        short_signal_list.append(
            short_signal
        )

        long_reason_list.append(
            long_reason
        )

        short_reason_list.append(
            short_reason
        )

    df["long_signal"] = pd.Series(
        long_signal_list,
        index=df.index,
        dtype=bool,
    )

    df["short_signal"] = pd.Series(
        short_signal_list,
        index=df.index,
        dtype=bool,
    )

    df["long_reason"] = (
        long_reason_list
    )

    df["short_reason"] = (
        short_reason_list
    )

    recent_df = (
        df.iloc[
            -SIGNAL_LOOKBACK:
        ].copy()
        if len(df)
        > SIGNAL_LOOKBACK
        else df.copy()
    )

    last_row = df.iloc[-1]

    return {
        "df": df,
        "recent_df": recent_df,

        "long_signal": bool(
            last_row["long_signal"]
        ),

        "short_signal": bool(
            last_row["short_signal"]
        ),

        "long_reason": str(
            last_row["long_reason"]
        ),

        "short_reason": str(
            last_row["short_reason"]
        ),
    }


# ============================================================
# 일봉 데이터
# ============================================================

def get_daily_data(ticker):

    df = yf.download(
        ticker,
        period="1y",
        interval="1d",
        auto_adjust=True,
        progress=False,
        multi_level_index=False,
    )

    if df.empty:

        raise Exception(
            f"{ticker} 데이터를 "
            "가져오지 못했습니다."
        )

    df.columns = [
        str(c).lower()
        for c in df.columns
    ]

    for c in [
        "open",
        "high",
        "low",
        "close",
    ]:

        if c not in df.columns:

            raise Exception(
                f"{ticker} 데이터에 "
                f"{c} 컬럼이 없습니다."
            )

    return df


# ============================================================
# 주봉 RSI
# ============================================================

def get_weekly_rsi_history(ticker):

    df = yf.download(
        ticker,
        period="5y",
        interval="1wk",
        auto_adjust=True,
        progress=False,
        multi_level_index=False,
    )

    if df.empty:

        raise Exception(
            f"{ticker} 주봉 데이터를 "
            "가져오지 못했습니다."
        )

    df.columns = [
        str(c).lower()
        for c in df.columns
    ]

    close = pd.Series(
        df["close"]
    ).astype(float)

    rsi_series = (
        calculate_rsi(
            close,
            RSI_LENGTH,
        )
        .dropna()
    )

    if len(rsi_series) < 3:

        raise Exception(
            f"{ticker} 주봉 RSI "
            "데이터가 부족합니다."
        )

    return rsi_series


# ============================================================
# 최근 거래일
# ============================================================

def get_last_data_date(df):

    last_timestamp = df.index[-1]

    if hasattr(
        last_timestamp,
        "date",
    ):

        return last_timestamp.date()

    return last_timestamp


# ============================================================
# 종목 분석
# ============================================================

def analyze_ticker(
    ticker,
    today_ny,
):

    print(
        "\n========================================"
    )

    print(
        f"{ticker} 분석 시작"
    )

    print(
        "========================================"
    )

    df = get_daily_data(ticker)

    last_date = get_last_data_date(
        df
    )

    print(
        f"{ticker} 최근 Yahoo 거래일:",
        last_date,
    )

    if (
        last_date != today_ny
        and not TEST_MODE
    ):

        print(
            f"{ticker}: "
            "Yahoo에 오늘 데이터가 "
            "아직 없습니다."
        )

        return None

    if (
        TEST_MODE
        and last_date != today_ny
    ):

        print(
            f"{ticker}: TEST MODE → "
            f"최근 거래일 {last_date} 사용"
        )

    # --------------------------------------------------------
    # 가격
    # --------------------------------------------------------

    price = float(
        df["close"].iloc[-1]
    )

    previous_close = float(
        df["close"].iloc[-2]
    )

    change = (
        (
            price
            - previous_close
        )
        / previous_close
        * 100
    )

    # --------------------------------------------------------
    # 일봉 RSI
    # --------------------------------------------------------

    daily_rsi_series = (
        calculate_rsi(
            df["close"],
            RSI_LENGTH,
        )
        .dropna()
    )

    if len(daily_rsi_series) < 3:

        raise Exception(
            f"{ticker} 일봉 RSI "
            "데이터가 부족합니다."
        )

    daily_rsi = float(
        daily_rsi_series.iloc[-1]
    )

    previous_daily_rsi = float(
        daily_rsi_series.iloc[-2]
    )

    two_days_ago_daily_rsi = float(
        daily_rsi_series.iloc[-3]
    )

    # --------------------------------------------------------
    # 주봉 RSI
    # --------------------------------------------------------

    weekly_rsi_series = (
        get_weekly_rsi_history(
            ticker
        )
    )

    weekly_rsi = float(
        weekly_rsi_series.iloc[-1]
    )

    previous_weekly_rsi = float(
        weekly_rsi_series.iloc[-2]
    )

    two_weeks_ago_weekly_rsi = float(
        weekly_rsi_series.iloc[-3]
    )

    # --------------------------------------------------------
    # 전략
    # --------------------------------------------------------

    strategy = run_strategy(
        df[
            [
                "open",
                "high",
                "low",
                "close",
            ]
        ]
    )

    long_signal = strategy[
        "long_signal"
    ]

    long_reason = strategy[
        "long_reason"
    ]

    # --------------------------------------------------------
    # 매수조건
    # --------------------------------------------------------

    buy_conditions = []

    if daily_rsi <= 30:

        buy_conditions.append(
            "🔴 일봉 RSI ≤ 30"
        )

    if weekly_rsi <= 30:

        buy_conditions.append(
            "🔴 주봉 RSI ≤ 30"
        )

    if long_signal:

        buy_conditions.append(
            f"🟢 LONG\n"
            f"   └ {long_reason}"
        )

    return {
        "ticker": ticker,

        "date": last_date,

        "price": price,

        "change": change,

        "daily_rsi": daily_rsi,

        "previous_daily_rsi": (
            previous_daily_rsi
        ),

        "two_days_ago_daily_rsi": (
            two_days_ago_daily_rsi
        ),

        "weekly_rsi": weekly_rsi,

        "previous_weekly_rsi": (
            previous_weekly_rsi
        ),

        "two_weeks_ago_weekly_rsi": (
            two_weeks_ago_weekly_rsi
        ),

        "long_signal": long_signal,

        "long_reason": long_reason,

        "buy_condition": bool(
            buy_conditions
        ),

        "buy_conditions": (
            buy_conditions
        ),
    }


# ============================================================
# RSI 테이블
# ============================================================

def make_rsi_table(result):

    daily_rsi = result[
        "daily_rsi"
    ]

    previous_daily_rsi = result[
        "previous_daily_rsi"
    ]

    daily_change = (
        rsi_change_text(
            daily_rsi,
            previous_daily_rsi,
        )
    )

    weekly_rsi = result[
        "weekly_rsi"
    ]

    previous_weekly_rsi = result[
        "previous_weekly_rsi"
    ]

    weekly_change = (
        rsi_change_text(
            weekly_rsi,
            previous_weekly_rsi,
        )
    )

    return (
        "📊 RSI(14)\n"
        f"일봉: {daily_rsi:.2f} "
        f"({daily_change}) / "
        f"주봉: {weekly_rsi:.2f} "
        f"({weekly_change})"
    )


# ============================================================
# QQQ / SPY RSI 원
#
# RSI <= 35 → 🟢
# RSI >= 70 → 🔴
# 그 외 → ⚪
# ============================================================

def get_rsi_circle(result):

    daily_rsi = result[
        "daily_rsi"
    ]

    weekly_rsi = result[
        "weekly_rsi"
    ]

    # RSI 35 이하 → 초록
    if (
        daily_rsi <= 35
        or weekly_rsi <= 35
    ):

        return "🟢"

    # RSI 70 이상 → 빨강
    if (
        daily_rsi >= 70
        or weekly_rsi >= 70
    ):

        return "🔴"

    # 그 외
    return "⚪"


# ============================================================
# QQQ / SPY 출력
# ============================================================

def format_basic_result(result):

    return (
        f"\n"
        f"{get_rsi_circle(result)} "
        f"{result['ticker']}\n"

        "━━━━━━━━━━━━━━━━━━\n\n"

        f"💰 종가\n"
        f"${result['price']:.2f} "
        f"({result['change']:+.2f}%)\n\n"

        f"{make_rsi_table(result)}\n"
    )


# ============================================================
# 기술주 출력
# ============================================================

def format_tech_result(result):

    condition_text = "\n".join(
        f"• {c}"
        for c in result[
            "buy_conditions"
        ]
    )

    return (
        f"\n🟢 "
        f"{result['ticker']}\n"

        "━━━━━━━━━━━━━━━━━━\n\n"

        f"💰 종가\n"
        f"${result['price']:.2f} "
        f"({result['change']:+.2f}%)\n\n"

        f"{make_rsi_table(result)}\n\n"

        f"🔔 매수조건\n"
        f"{condition_text}\n"
    )


# ============================================================
# 리포트 생성
# ============================================================

def make_report(
    results,
    market_close,
):

    if not results:
        return None

    first_date = results[0][
        "date"
    ]

    if market_close is None:

        close_label = (
            "수동 테스트 "
            "(최근 거래일 기준)"
        )

    else:

        close_label = (
            market_close.strftime(
                "%H:%M NY"
            )
        )

        if (
            market_close.hour != 16
            or market_close.minute != 0
        ):

            close_label += (
                " (조기 폐장)"
            )

    test_banner = (
        "🧪 TEST MODE\n\n"
        if TEST_MODE
        else ""
    )

    report = (
        "📊 미국장 일일 리포트\n\n"

        f"{test_banner}"

        f"📅 거래일\n"
        f"{first_date}\n\n"
    )

    # --------------------------------------------------------
    # QQQ / SPY
    # --------------------------------------------------------

    for result in results:

        if (
            result["ticker"]
            in ALWAYS_SHOW
        ):

            report += (
                format_basic_result(
                    result
                )
            )

            report += "\n"

    # --------------------------------------------------------
    # 기술주
    # --------------------------------------------------------

    tech_results = [
        r
        for r in results
        if (
            r["ticker"]
            in TECH_STOCKS
            and r["buy_condition"]
        )
    ]

    if tech_results:

        report += (
            "\n━━━━━━━━━━━━━━━━━━\n"
            "🚀 기술주 매수조건 발생\n"
            "━━━━━━━━━━━━━━━━━━\n"
        )

        for result in tech_results:

            report += (
                format_tech_result(
                    result
                )
            )

    return report


# ============================================================
# 전체 종목 분석
# ============================================================

def run_analysis(today_ny):

    results = []
    missing_data = []

    for ticker in TICKERS:

        try:

            result = analyze_ticker(
                ticker,
                today_ny,
            )

            if result is None:

                missing_data.append(
                    ticker
                )

                continue

            if (
                ticker
                in ALWAYS_SHOW
            ):

                results.append(
                    result
                )

                continue

            if (
                ticker
                in TECH_STOCKS
                and result[
                    "buy_condition"
                ]
            ):

                results.append(
                    result
                )

        except Exception as e:

            print(
                f"{ticker} 분석 실패: "
                f"{repr(e)}"
            )

    return (
        results,
        missing_data,
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print(
        "========================================"
    )

    print(
        "QQQ / SPY / 기술주 "
        "일일 분석 시작"
    )

    print(
        "========================================"
    )

    (
        should_run,
        market_close,
        now_ny,
    ) = check_market_status()

    if not should_run:

        print(
            "오늘은 실행하지 않습니다."
        )

        return

    # ========================================================
    # 한국시간 07:15 실행 시
    #
    # 뉴욕은 전날 저녁이므로
    # today_ny = 미국 전 거래일
    # ========================================================

    today_ny = now_ny.date()

    print(
        "분석 기준일:",
        today_ny,
    )

    # ========================================================
    # TEST MODE
    # ========================================================

    if TEST_MODE:

        (
            results,
            missing_data,
        ) = run_analysis(
            today_ny
        )

    # ========================================================
    # NORMAL MODE
    # ========================================================

    else:

        max_attempts = (
            YAHOO_MAX_WAIT_MINUTES
            // YAHOO_RETRY_INTERVAL_MINUTES
            + 1
        )

        results = []
        missing_data = []

        for attempt in range(
            max_attempts
        ):

            print(
                f"\nYahoo 데이터 확인 "
                f"{attempt + 1}/"
                f"{max_attempts}"
            )

            (
                results,
                missing_data,
            ) = run_analysis(
                today_ny
            )

            required_missing = [
                t
                for t in missing_data
                if t in ALWAYS_SHOW
            ]

            # QQQ / SPY 데이터가
            # 최신 거래일이면 전송
            if not required_missing:

                print(
                    "QQQ / SPY Yahoo "
                    "데이터가 최신 거래일로 "
                    "확인되었습니다."
                )

                break

            if (
                attempt
                == max_attempts - 1
            ):

                print(
                    f"Yahoo 데이터가 "
                    f"{YAHOO_MAX_WAIT_MINUTES}분 동안 "
                    "업데이트되지 않았습니다."
                )

                print(
                    "누락 종목:",
                    ", ".join(
                        missing_data
                    ),
                )

                print(
                    "이번 실행은 "
                    "Telegram 전송을 하지 않습니다."
                )

                return

            print(
                f"{YAHOO_RETRY_INTERVAL_MINUTES}분 후 "
                "다시 확인합니다."
            )

            time.sleep(
                YAHOO_RETRY_INTERVAL_MINUTES
                * 60
            )

    # ========================================================
    # 결과 없음
    # ========================================================

    if not results:

        print(
            "전송할 결과가 없습니다."
        )

        return

    # ========================================================
    # 리포트
    # ========================================================

    report = make_report(
        results,
        market_close,
    )

    if not report:

        print(
            "리포트 생성 실패"
        )

        return

    print(
        "\n========================================"
    )

    print(report)

    print(
        "========================================"
    )

    # ========================================================
    # Telegram 전송
    # ========================================================

    send_telegram(report)

    print(
        "Telegram 전송 완료"
    )


# ============================================================
# 실행
# ============================================================

if __name__ == "__main__":
    main()
