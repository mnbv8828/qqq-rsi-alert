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
    os.environ.get("TEST_MODE", "false").lower() == "true"
)

NY_TZ = ZoneInfo("America/New_York")


# ============================================================
# Yahoo Finance 데이터 재시도 설정
# ============================================================

# GitHub Actions가 실행된 직후 Yahoo 데이터가 아직 갱신되지
# 않았을 경우를 대비한 설정

DATA_RETRY_COUNT = 6

# 재시도 사이 대기시간
# 60초 × 5회 = 최대 약 5분 추가 대기
DATA_RETRY_INTERVAL = 60


# ============================================================
# 미국장 마감 후 실행 허용시간
# ============================================================

# 정상장:
# 16:00 마감
#
# 조기폐장:
# 13:00 마감 등
#
# GitHub Actions가 16:10 NY에 실행되는 경우
# 조기폐장일에는 3시간 이상 지날 수 있으므로
# 기존 120분보다 충분히 늘림

MAX_POST_CLOSE_MINUTES = 360


# ============================================================
# 분석 종목
# ============================================================

TICKERS = [
    "QQQ",
    "SPY",

    # 기술주
    "MSFT",
    "AMZN",
    "GOOG",
    "AAPL",
    "META",
    "NVDA",
    "TSLA",
    "PLTR",
]


# ============================================================
# 항상 표시
# ============================================================

ALWAYS_SHOW = {
    "QQQ",
    "SPY",
}


# ============================================================
# 매수조건 발생 시에만 표시
# ============================================================

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
# 전략 설정
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
#
# TradingView ta.rsi() Wilder 방식
# ============================================================

def calculate_rsi(
    series: pd.Series,
    length: int = 14,
) -> pd.Series:

    series = pd.to_numeric(
        series,
        errors="coerce",
    )

    delta = series.diff()

    gain = delta.clip(
        lower=0
    )

    loss = -delta.clip(
        upper=0
    )

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
        avg_gain /
        avg_loss.replace(
            0,
            np.nan,
        )
    )

    rsi = (
        100 -
        (
            100 /
            (1 + rs)
        )
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
#
# RSI <= 35
# → 숫자 앞에 초록색 원
#
# 실제 매수조건 RSI 기준은 30
# ============================================================

def format_rsi(rsi):

    if rsi <= 35:
        return f"🟢 {rsi:.2f}"

    return f"{rsi:.2f}"


# ============================================================
# NYSE 거래일정
# ============================================================

def get_nyse_market_close(now_ny):

    nyse = mcal.get_calendar(
        "NYSE"
    )

    today = now_ny.date()

    schedule = nyse.schedule(
        start_date=today,
        end_date=today,
    )

    if schedule.empty:
        return None

    market_close = schedule.iloc[0][
        "market_close"
    ]

    # UTC timestamp를 뉴욕시간으로 변환
    if market_close.tzinfo is None:
        market_close = market_close.tz_localize(
            "UTC"
        )

    market_close = market_close.tz_convert(
        NY_TZ
    )

    return market_close


# ============================================================
# 미국장 상태 확인
#
# 휴장일 자동 처리
# 조기폐장 자동 처리
# 서머타임/겨울시간 자동 처리
# ============================================================

def check_market_status():

    now_ny = datetime.now(
        NY_TZ
    )

    print(
        "현재 뉴욕 시간:",
        now_ny.strftime(
            "%Y-%m-%d %H:%M:%S %Z"
        ),
    )

    # --------------------------------------------------------
    # 수동 테스트
    # --------------------------------------------------------

    if TEST_MODE:

        print(
            "🧪 TEST MODE"
        )

        print(
            "미국장 시간 검사를 건너뜁니다."
        )

        return (
            True,
            None,
            now_ny,
        )

    # --------------------------------------------------------
    # NYSE 실제 마감시간
    # --------------------------------------------------------

    market_close = (
        get_nyse_market_close(
            now_ny
        )
    )

    # --------------------------------------------------------
    # 휴장
    # --------------------------------------------------------

    if market_close is None:

        print(
            "오늘은 NYSE 휴장일입니다."
        )

        return (
            False,
            None,
            now_ny,
        )

    print(
        "NYSE 실제 마감:",
        market_close.strftime(
            "%Y-%m-%d %H:%M:%S %Z"
        ),
    )

    # --------------------------------------------------------
    # 조기폐장 여부
    # --------------------------------------------------------

    if (
        market_close.hour != 16
        or
        market_close.minute != 0
    ):

        print(
            "⚠️ 오늘은 조기폐장입니다."
        )

    else:

        print(
            "정상 거래일입니다."
        )

    # --------------------------------------------------------
    # 아직 장이 안 끝남
    # --------------------------------------------------------

    if now_ny < market_close:

        remaining = (
            market_close -
            now_ny
        )

        print(
            "아직 미국장이 마감되지 않았습니다."
        )

        print(
            "남은 시간:",
            remaining,
        )

        return (
            False,
            market_close,
            now_ny,
        )

    # --------------------------------------------------------
    # 마감 후 경과시간
    # --------------------------------------------------------

    elapsed = (
        now_ny -
        market_close
    )

    elapsed_minutes = (
        elapsed.total_seconds()
        / 60
    )

    print(
        f"미국장 마감 후 "
        f"{elapsed_minutes:.1f}분 경과"
    )

    # --------------------------------------------------------
    # 너무 늦게 실행된 경우
    # --------------------------------------------------------

    if (
        elapsed_minutes >
        MAX_POST_CLOSE_MINUTES
    ):

        print(
            "미국장 마감 후 "
            f"{MAX_POST_CLOSE_MINUTES}분이 지났습니다."
        )

        return (
            False,
            market_close,
            now_ny,
        )

    print(
        "미국장 마감 후 실행 조건 충족"
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
    lows: pd.Series,
    index: int,
    left: int,
    right: int,
) -> bool:

    pivot_index = (
        index - right
    )

    if pivot_index - left < 0:
        return False

    if (
        pivot_index + right
        >= len(lows)
    ):
        return False

    pivot_value = float(
        lows.iloc[
            pivot_index
        ]
    )

    left_values = lows.iloc[
        pivot_index - left:
        pivot_index
    ]

    right_values = lows.iloc[
        pivot_index + 1:
        pivot_index + right + 1
    ]

    if len(left_values) != left:
        return False

    if len(right_values) != right:
        return False

    return (
        pivot_value <=
        float(
            left_values.min()
        )
        and
        pivot_value <=
        float(
            right_values.min()
        )
    )


# ============================================================
# Pivot High
# ============================================================

def is_pivot_high(
    highs: pd.Series,
    index: int,
    left: int,
    right: int,
) -> bool:

    pivot_index = (
        index - right
    )

    if pivot_index - left < 0:
        return False

    if (
        pivot_index + right
        >= len(highs)
    ):
        return False

    pivot_value = float(
        highs.iloc[
            pivot_index
        ]
    )

    left_values = highs.iloc[
        pivot_index - left:
        pivot_index
    ]

    right_values = highs.iloc[
        pivot_index + 1:
        pivot_index + right + 1
    ]

    if len(left_values) != left:
        return False

    if len(right_values) != right:
        return False

    return (
        pivot_value >=
        float(
            left_values.max()
        )
        and
        pivot_value >=
        float(
            right_values.max()
        )
    )


# ============================================================
# barssince
# ============================================================

def bars_since(
    condition: pd.Series
) -> pd.Series:

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

def run_strategy(
    df: pd.DataFrame
):

    df = df.copy()

    required = [
        "open",
        "high",
        "low",
        "close",
    ]

    # --------------------------------------------------------
    # 컬럼 확인
    # --------------------------------------------------------

    for column in required:

        if column not in df.columns:

            raise ValueError(
                f"필수 컬럼 없음: {column}"
            )

    # --------------------------------------------------------
    # 숫자 변환
    # --------------------------------------------------------

    for column in required:

        df[column] = pd.to_numeric(
            df[column],
            errors="coerce",
        )

    df = df.dropna(
        subset=required
    ).reset_index(
        drop=True
    )

    if len(df) < 100:

        raise ValueError(
            f"데이터가 너무 적습니다: "
            f"{len(df)}개"
        )

    # ========================================================
    # RSI
    # ========================================================

    df["rsi"] = calculate_rsi(
        df["close"],
        RSI_LENGTH,
    )

    df["is_oversold"] = (
        df["rsi"] <=
        OVERSOLD_LEVEL
    )

    df["is_overbought"] = (
        df["rsi"] >=
        OVERBOUGHT_LEVEL
    )

    # ========================================================
    # Pivot
    # ========================================================

    pivot_low_flags = []
    pivot_high_flags = []

    for i in range(len(df)):

        pivot_low_flags.append(
            is_pivot_low(
                df["low"],
                i,
                PIVOT_LEFT,
                PIVOT_RIGHT,
            )
        )

        pivot_high_flags.append(
            is_pivot_high(
                df["high"],
                i,
                PIVOT_LEFT,
                PIVOT_RIGHT,
            )
        )

    df["pivot_low"] = pd.Series(
        pivot_low_flags,
        index=df.index,
        dtype=bool,
    )

    df["pivot_high"] = pd.Series(
        pivot_high_flags,
        index=df.index,
        dtype=bool,
    )

    # ========================================================
    # Pivot RSI
    # ========================================================

    df["pivot_low_rsi"] = np.nan
    df["pivot_high_rsi"] = np.nan

    for i in range(len(df)):

        if bool(
            df["pivot_low"].iloc[i]
        ):

            pivot_index = (
                i - PIVOT_RIGHT
            )

            if pivot_index >= 0:

                df.loc[
                    i,
                    "pivot_low_rsi",
                ] = df["rsi"].iloc[
                    pivot_index
                ]

        if bool(
            df["pivot_high"].iloc[i]
        ):

            pivot_index = (
                i - PIVOT_RIGHT
            )

            if pivot_index >= 0:

                df.loc[
                    i,
                    "pivot_high_rsi",
                ] = df["rsi"].iloc[
                    pivot_index
                ]

    # ========================================================
    # 상승 다이버전스
    # ========================================================

    df["bull_divergence"] = pd.Series(
        False,
        index=df.index,
        dtype=bool,
    )

    previous_price_pivots = []
    previous_rsi_pivots = []
    previous_pivot_bars = []

    for i in range(len(df)):

        if not bool(
            df["pivot_low"].iloc[i]
        ):

            continue

        current_pivot_bar = (
            i - PIVOT_RIGHT
        )

        current_price = float(
            df["low"].iloc[
                current_pivot_bar
            ]
        )

        current_rsi = (
            df["rsi"].iloc[
                current_pivot_bar
            ]
        )

        if pd.isna(
            current_rsi
        ):

            continue

        current_rsi = float(
            current_rsi
        )

        bull_divergence = False

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
                current_pivot_bar -
                prev_bar
            )

            if (
                bars_between >=
                DIV_MIN_RANGE
                and
                bars_between <=
                DIV_MAX_RANGE
            ):

                if (
                    current_price <
                    prev_price
                    and
                    current_rsi >
                    prev_rsi
                ):

                    bull_divergence = True
                    break

        if bull_divergence:

            df.loc[
                i,
                "bull_divergence",
            ] = True

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

    # ========================================================
    # 원형파
    # ========================================================

    short_window = max(
        4,
        int(
            MAX_BARS * 0.45
        ),
    )

    df["lowest_40"] = (
        df["low"]
        .rolling(
            window=MAX_BARS,
            min_periods=MAX_BARS,
        )
        .min()
    )

    df["lowest_short"] = (
        df["low"]
        .rolling(
            window=short_window,
            min_periods=short_window,
        )
        .min()
    )

    df["highest_40"] = (
        df["high"]
        .rolling(
            window=MAX_BARS,
            min_periods=MAX_BARS,
        )
        .max()
    )

    df["highest_short"] = (
        df["high"]
        .rolling(
            window=short_window,
            min_periods=short_window,
        )
        .max()
    )

    # ========================================================
    # 최저점 / 최고점
    # ========================================================

    low_equals_lowest = pd.Series(
        False,
        index=df.index,
        dtype=bool,
    )

    valid_low = (
        df["low"].notna()
        &
        df["lowest_40"].notna()
    )

    low_equals_lowest.loc[
        valid_low
    ] = (
        np.abs(
            df.loc[
                valid_low,
                "low",
            ]
            -
            df.loc[
                valid_low,
                "lowest_40",
            ]
        )
        <= 1e-10
    )

    high_equals_highest = pd.Series(
        False,
        index=df.index,
        dtype=bool,
    )

    valid_high = (
        df["high"].notna()
        &
        df["highest_40"].notna()
    )

    high_equals_highest.loc[
        valid_high
    ] = (
        np.abs(
            df.loc[
                valid_high,
                "high",
            ]
            -
            df.loc[
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

    # ========================================================
    # 상태 변수
    # ========================================================

    stage1_long = False
    stage2_long = False

    stage1_short = False

    last_long_bar = None
    last_short_bar = None

    long_signal_list = []
    short_signal_list = []

    long_reason_list = []
    short_reason_list = []

    # ========================================================
    # 각 봉 계산
    # ========================================================

    for i in range(len(df)):

        is_oversold = bool(
            df["is_oversold"].iloc[i]
        )

        is_overbought = bool(
            df["is_overbought"].iloc[i]
        )

        bull_div_now = bool(
            df["bull_divergence"].iloc[i]
        )

        # ====================================================
        # LONG 1단계
        # ====================================================

        if is_oversold:

            if not stage1_long:

                stage1_long = True
                stage2_long = False

        # 과매도 → SHORT 취소

        if is_oversold:

            stage1_short = False

        # ====================================================
        # 상승 다이버전스
        # ====================================================

        if (
            stage1_long
            and
            bull_div_now
            and
            not stage2_long
        ):

            stage2_long = True

        # ====================================================
        # Higher Low
        # ====================================================

        low1 = df[
            "lowest_40"
        ].iloc[i]

        low2 = df[
            "lowest_short"
        ].iloc[i]

        bars_since_low = df[
            "bars_since_low"
        ].iloc[i]

        higher_low = False

        if (
            not pd.isna(low1)
            and
            not pd.isna(low2)
        ):

            higher_low = (
                float(low2)
                >
                float(low1)
                *
                (
                    1 +
                    MIN_HL_PERCENT / 100
                )
            )

        bars_ok_long = False

        if not pd.isna(
            bars_since_low
        ):

            bars_ok_long = (
                bars_since_low >=
                MIN_BARS
                and
                bars_since_low <=
                MAX_BARS
            )

        circular_long = (
            higher_low
            and
            bars_ok_long
        )

        # ====================================================
        # LONG cooldown
        # ====================================================

        cooldown_long = (
            last_long_bar is None
            or
            (
                i -
                last_long_bar
                >= SIGNAL_COOLDOWN
            )
        )

        # ====================================================
        # LONG Signal
        # ====================================================

        long_signal = (
            stage1_long
            and
            circular_long
            and
            cooldown_long
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

        # 과매도 종료

        if not is_oversold:

            stage1_long = False
            stage2_long = False

        # ====================================================
        # SHORT 1단계
        # ====================================================

        if is_overbought:

            if not stage1_short:

                stage1_short = True

        # 과매수 → LONG 취소

        if is_overbought:

            stage1_long = False
            stage2_long = False

        # ====================================================
        # Lower High
        # ====================================================

        high1 = df[
            "highest_40"
        ].iloc[i]

        high2 = df[
            "highest_short"
        ].iloc[i]

        bars_since_high = df[
            "bars_since_high"
        ].iloc[i]

        lower_high = False

        if (
            not pd.isna(high1)
            and
            not pd.isna(high2)
        ):

            lower_high = (
                float(high2)
                <
                float(high1)
                *
                (
                    1 -
                    MIN_HL_PERCENT / 100
                )
            )

        bars_ok_short = False

        if not pd.isna(
            bars_since_high
        ):

            bars_ok_short = (
                bars_since_high >=
                MIN_BARS
                and
                bars_since_high <=
                MAX_BARS
            )

        circular_short = (
            lower_high
            and
            bars_ok_short
        )

        # ====================================================
        # SHORT cooldown
        # ====================================================

        cooldown_short = (
            last_short_bar is None
            or
            (
                i -
                last_short_bar
                >= SIGNAL_COOLDOWN
            )
        )

        # ====================================================
        # SHORT Signal
        # ====================================================

        short_signal = (
            stage1_short
            and
            circular_short
            and
            cooldown_short
        )

        short_reason = ""

        if short_signal:

            short_reason = (
                "과매수 → Lower High"
            )

            last_short_bar = i

        # ====================================================
        # 결과 저장
        # ====================================================

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

    # ========================================================
    # 결과 저장
    # ========================================================

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

    # ========================================================
    # 최근 120일
    # ========================================================

    if len(df) > SIGNAL_LOOKBACK:

        recent_df = df.iloc[
            -SIGNAL_LOOKBACK:
        ].copy()

    else:

        recent_df = df.copy()

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
# Yahoo Finance 일봉 데이터
#
# 핵심:
# Yahoo 데이터가 아직 오늘 날짜로 갱신되지 않았으면
# 자동으로 여러 번 재시도
# ============================================================

def get_daily_data(
    ticker,
    expected_date=None,
):

    last_error = None

    for attempt in range(
        1,
        DATA_RETRY_COUNT + 1,
    ):

        try:

            print(
                f"{ticker}: "
                f"일봉 데이터 요청 "
                f"({attempt}/{DATA_RETRY_COUNT})"
            )

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
                    f"{ticker} 데이터가 비어 있습니다."
                )

            df.columns = [
                str(column).lower()
                for column in df.columns
            ]

            required = [
                "open",
                "high",
                "low",
                "close",
            ]

            for column in required:

                if column not in df.columns:

                    raise Exception(
                        f"{ticker} 데이터에 "
                        f"{column} 컬럼이 없습니다."
                    )

            # ------------------------------------------------
            # 예상 거래일이 지정된 경우
            # Yahoo 최신 데이터 날짜 확인
            # ------------------------------------------------

            if expected_date is not None:

                last_timestamp = df.index[-1]

                if hasattr(
                    last_timestamp,
                    "date",
                ):

                    last_date = (
                        last_timestamp.date()
                    )

                else:

                    last_date = last_timestamp

                print(
                    f"{ticker}: "
                    f"Yahoo 최근 거래일 = "
                    f"{last_date}"
                )

                # 오늘 데이터가 들어왔으면 성공
                if last_date == expected_date:

                    print(
                        f"{ticker}: "
                        "오늘 데이터 확인 완료"
                    )

                    return df

                # 아직 전날 데이터라면 재시도
                print(
                    f"{ticker}: "
                    f"오늘 데이터({expected_date}) "
                    f"미반영"
                )

            else:

                return df

        except Exception as e:

            last_error = e

            print(
                f"{ticker}: "
                f"Yahoo 데이터 요청 오류"
            )

            print(
                repr(e)
            )

        # ----------------------------------------------------
        # 마지막 시도라면 대기하지 않음
        # ----------------------------------------------------

        if attempt >= DATA_RETRY_COUNT:

            break

        print(
            f"{ticker}: "
            f"{DATA_RETRY_INTERVAL}초 후 "
            "다시 시도합니다."
        )

        time.sleep(
            DATA_RETRY_INTERVAL
        )

    # ========================================================
    # 모든 재시도 실패
    # ========================================================

    if last_error:

        raise Exception(
            f"{ticker}: "
            "Yahoo Finance 데이터를 "
            f"{DATA_RETRY_COUNT}회 요청했지만 "
            "최신 데이터를 확인하지 못했습니다."
        ) from last_error

    raise Exception(
        f"{ticker}: "
        "Yahoo Finance 최신 데이터를 "
        "가져오지 못했습니다."
    )


# ============================================================
# 주봉 RSI
# ============================================================

def get_weekly_rsi(ticker):

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
        str(column).lower()
        for column in df.columns
    ]

    close = pd.Series(
        df["close"]
    ).astype(float)

    weekly_rsi = (
        calculate_rsi(
            close,
            RSI_LENGTH,
        )
        .iloc[-1]
    )

    if pd.isna(
        weekly_rsi
    ):

        raise Exception(
            f"{ticker} 주봉 RSI 계산 실패"
        )

    return float(
        weekly_rsi
    )


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

    # --------------------------------------------------------
    # 일봉 데이터
    #
    # 오늘 데이터가 아직 Yahoo에 없다면
    # get_daily_data()가 자동 재시도
    # --------------------------------------------------------

    df = get_daily_data(
        ticker,
        expected_date=(
            None
            if TEST_MODE
            else today_ny
        ),
    )

    last_timestamp = df.index[-1]

    if hasattr(
        last_timestamp,
        "date",
    ):

        last_date = (
            last_timestamp.date()
        )

    else:

        last_date = last_timestamp

    print(
        f"{ticker} 최근 거래일:",
        last_date,
    )

    # --------------------------------------------------------
    # 자동 실행
    # 오늘 데이터가 아니면 제외
    #
    # get_daily_data()에서 이미 재시도했지만
    # 혹시 모를 최종 안전장치
    # --------------------------------------------------------

    if (
        last_date != today_ny
        and
        not TEST_MODE
    ):

        print(
            f"{ticker}: "
            "오늘 거래일 데이터 없음"
        )

        return None

    # --------------------------------------------------------
    # TEST MODE
    # --------------------------------------------------------

    if (
        TEST_MODE
        and
        last_date != today_ny
    ):

        print(
            f"{ticker}: "
            "TEST MODE → "
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
            price -
            previous_close
        )
        /
        previous_close
        *
        100
    )

    # --------------------------------------------------------
    # RSI
    # --------------------------------------------------------

    daily_rsi = float(
        calculate_rsi(
            df["close"],
            RSI_LENGTH,
        ).iloc[-1]
    )

    weekly_rsi = (
        get_weekly_rsi(
            ticker
        )
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
            "🟢 LONG\n"
            f"   └ {long_reason}"
        )

    buy_condition = (
        len(buy_conditions) > 0
    )

    print(
        f"{ticker}: "
        f"일봉 RSI={daily_rsi:.2f}, "
        f"주봉 RSI={weekly_rsi:.2f}"
    )

    if buy_condition:

        print(
            f"{ticker}: "
            "매수조건 발생"
        )

    else:

        print(
            f"{ticker}: "
            "매수조건 없음 → 제외"
        )

    return {
        "ticker": ticker,
        "date": last_date,
        "price": price,
        "change": change,

        "daily_rsi": daily_rsi,
        "weekly_rsi": weekly_rsi,

        "long_signal": long_signal,
        "long_reason": long_reason,

        "buy_condition": buy_condition,
        "buy_conditions": buy_conditions,
    }


# ============================================================
# QQQ / SPY 리포트
# ============================================================

def format_basic_result(
    result,
):

    ticker = result[
        "ticker"
    ]

    price = result[
        "price"
    ]

    change = result[
        "change"
    ]

    daily_rsi = result[
        "daily_rsi"
    ]

    weekly_rsi = result[
        "weekly_rsi"
    ]

    return f"""
⚪ {ticker}
━━━━━━━━━━━━━━━━━━

💰 종가
${price:.2f}

📈 등락률
{change:+.2f}%

📊 일봉 RSI(14)
{format_rsi(daily_rsi)}

📊 주봉 RSI(14)
{format_rsi(weekly_rsi)}

"""


# ============================================================
# 기술주 리포트
# ============================================================

def format_tech_result(
    result,
):

    ticker = result[
        "ticker"
    ]

    price = result[
        "price"
    ]

    change = result[
        "change"
    ]

    daily_rsi = result[
        "daily_rsi"
    ]

    weekly_rsi = result[
        "weekly_rsi"
    ]

    buy_conditions = result[
        "buy_conditions"
    ]

    condition_text = "\n".join(
        f"• {condition}"
        for condition
        in buy_conditions
    )

    return f"""
🟢 {ticker}
━━━━━━━━━━━━━━━━━━

💰 종가
${price:.2f}

📈 등락률
{change:+.2f}%

📊 일봉 RSI(14)
{format_rsi(daily_rsi)}

📊 주봉 RSI(14)
{format_rsi(weekly_rsi)}

🔔 매수조건
{condition_text}

"""


# ============================================================
# 전체 Telegram 리포트
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

    # --------------------------------------------------------
    # 마감시간
    # --------------------------------------------------------

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

        # 조기폐장 여부
        if (
            market_close.hour != 16
            or
            market_close.minute != 0
        ):

            close_label += (
                " (조기 폐장)"
            )

    # --------------------------------------------------------
    # 테스트 표시
    # --------------------------------------------------------

    test_banner = ""

    if TEST_MODE:

        test_banner = (
            "🧪 TEST MODE\n\n"
        )

    # --------------------------------------------------------
    # 헤더
    # --------------------------------------------------------

    report = f"""📊 미국장 일일 리포트

{test_banner}📅 거래일
{first_date}

🕐 NYSE 마감
{close_label}

📌 기본 분석
QQQ / SPY

📌 기술주
MSFT / AMZN / GOOG / AAPL
META / NVDA / TSLA / PLTR

"""

    # ========================================================
    # QQQ / SPY
    # 항상 표시
    # ========================================================

    for result in results:

        ticker = result[
            "ticker"
        ]

        if ticker not in ALWAYS_SHOW:
            continue

        report += format_basic_result(
            result
        )

    # ========================================================
    # 기술주
    #
    # 매수조건 발생한 종목만 표시
    # ========================================================

    tech_results = []

    for result in results:

        ticker = result[
            "ticker"
        ]

        if ticker not in TECH_STOCKS:
            continue

        if not result[
            "buy_condition"
        ]:
            continue

        tech_results.append(
            result
        )

    # ========================================================
    # 기술주 매수조건 발생
    # ========================================================

    if tech_results:

        report += (
            "\n━━━━━━━━━━━━━━━━━━\n"
            "🚀 기술주 매수조건 발생\n"
            "━━━━━━━━━━━━━━━━━━\n"
        )

        for result in tech_results:

            report += format_tech_result(
                result
            )

    # ========================================================
    # 마지막 줄
    #
    # 자동 분석 완료 없음
    # ========================================================

    return report


# ============================================================
# MAIN
# ============================================================

def main():

    print(
        "========================================"
    )

    print(
        "QQQ / SPY / 기술주 일일 분석 시작"
    )

    print(
        "========================================"
    )

    # --------------------------------------------------------
    # 미국장 상태
    # --------------------------------------------------------

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

    today_ny = now_ny.date()

    print(
        "분석 기준일:",
        today_ny,
    )

    # --------------------------------------------------------
    # 결과
    # --------------------------------------------------------

    results = []

    # --------------------------------------------------------
    # 종목 분석
    # --------------------------------------------------------

    for ticker in TICKERS:

        try:

            result = analyze_ticker(
                ticker,
                today_ny,
            )

            if result is None:

                continue

            # =================================================
            # QQQ / SPY
            # 항상 추가
            # =================================================

            if ticker in ALWAYS_SHOW:

                results.append(
                    result
                )

                print(
                    f"{ticker}: "
                    "항상 표시"
                )

                continue

            # =================================================
            # 기술주
            # 매수조건 있을 때만 추가
            # =================================================

            if ticker in TECH_STOCKS:

                if result[
                    "buy_condition"
                ]:

                    results.append(
                        result
                    )

                    print(
                        f"{ticker}: "
                        "매수조건 발생 → 표시"
                    )

                else:

                    print(
                        f"{ticker}: "
                        "매수조건 없음 → 제외"
                    )

        except Exception as e:

            print(
                f"{ticker} 분석 실패"
            )

            print(
                repr(e)
            )

    # --------------------------------------------------------
    # 결과 없음
    # --------------------------------------------------------

    if not results:

        print(
            "전송할 결과가 없습니다."
        )

        return

    # --------------------------------------------------------
    # Telegram 메시지 생성
    # --------------------------------------------------------

    report = make_report(
        results,
        market_close,
    )

    if not report:

        print(
            "리포트 생성 실패"
        )

        return

    # --------------------------------------------------------
    # 콘솔 출력
    # --------------------------------------------------------

    print(
        "\n========================================"
    )

    print(
        report
    )

    print(
        "========================================"
    )

    # --------------------------------------------------------
    # Telegram 전송
    # --------------------------------------------------------

    send_telegram(
        report
    )

    print(
        "Telegram 전송 완료"
    )


# ============================================================
# 실행
# ============================================================

if __name__ == "__main__":
    main()
