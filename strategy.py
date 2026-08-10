import numpy as np
import pandas as pd


# ============================================================
# 설정
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

# 실제 신호 판단 구간
SIGNAL_LOOKBACK = 120


# ============================================================
# RSI
# TradingView ta.rsi()의 Wilder 방식에 맞춤
# ============================================================

def calculate_rsi(
    series: pd.Series,
    length: int = 14
) -> pd.Series:

    series = pd.to_numeric(
        series,
        errors="coerce"
    )

    delta = series.diff()

    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(
        alpha=1 / length,
        adjust=False,
        min_periods=length
    ).mean()

    avg_loss = loss.ewm(
        alpha=1 / length,
        adjust=False,
        min_periods=length
    ).mean()

    rs = (
        avg_gain /
        avg_loss.replace(0, np.nan)
    )

    rsi = 100 - (
        100 / (1 + rs)
    )

    rsi = rsi.mask(
        avg_loss == 0,
        100
    )

    rsi = rsi.mask(
        avg_gain == 0,
        0
    )

    return rsi


# ============================================================
# Pivot Low
#
# Pine:
# ta.pivotlow(low, 3, 3)
# ============================================================

def is_pivot_low(
    lows: pd.Series,
    index: int,
    left: int,
    right: int
) -> bool:

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

    if len(left_values) != left:
        return False

    if len(right_values) != right:
        return False

    return (
        pivot_value <= float(left_values.min())
        and
        pivot_value <= float(right_values.min())
    )


# ============================================================
# Pivot High
# ============================================================

def is_pivot_high(
    highs: pd.Series,
    index: int,
    left: int,
    right: int
) -> bool:

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

    if len(left_values) != left:
        return False

    if len(right_values) != right:
        return False

    return (
        pivot_value >= float(left_values.max())
        and
        pivot_value >= float(right_values.max())
    )


# ============================================================
# barssince
# ============================================================

def bars_since(
    condition: pd.Series
) -> pd.Series:

    # 반드시 Series로 변환
    condition = pd.Series(
        condition,
        index=condition.index
        if hasattr(condition, "index")
        else None
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
        index=condition.index
    )


# ============================================================
# 전략
# ============================================================

def run_strategy(
    df: pd.DataFrame
):

    df = df.copy()

    # ========================================================
    # 컬럼 정리
    # ========================================================

    required = [
        "open",
        "high",
        "low",
        "close"
    ]

    for column in required:

        if column not in df.columns:

            raise ValueError(
                f"필수 컬럼 없음: {column}"
            )

    # 숫자형 변환
    for column in required:

        df[column] = pd.to_numeric(
            df[column],
            errors="coerce"
        )

    df = df.dropna(
        subset=required
    ).reset_index(drop=True)

    if len(df) < 100:

        raise ValueError(
            f"데이터가 너무 적습니다: {len(df)}개"
        )

    # ========================================================
    # RSI
    # ========================================================

    df["rsi"] = calculate_rsi(
        df["close"],
        RSI_LENGTH
    )

    # ========================================================
    # 과매도 / 과매수
    # ========================================================

    df["is_oversold"] = (
        df["rsi"] <= OVERSOLD_LEVEL
    )

    df["is_overbought"] = (
        df["rsi"] >= OVERBOUGHT_LEVEL
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
                PIVOT_RIGHT
            )
        )

        pivot_high_flags.append(
            is_pivot_high(
                df["high"],
                i,
                PIVOT_LEFT,
                PIVOT_RIGHT
            )
        )

    df["pivot_low"] = pd.Series(
        pivot_low_flags,
        index=df.index,
        dtype=bool
    )

    df["pivot_high"] = pd.Series(
        pivot_high_flags,
        index=df.index,
        dtype=bool
    )

    # ========================================================
    # Pivot RSI
    # ========================================================

    df["pivot_low_rsi"] = np.nan
    df["pivot_high_rsi"] = np.nan

    for i in range(len(df)):

        if bool(df["pivot_low"].iloc[i]):

            pivot_index = i - PIVOT_RIGHT

            if pivot_index >= 0:

                df.loc[
                    i,
                    "pivot_low_rsi"
                ] = df["rsi"].iloc[
                    pivot_index
                ]

        if bool(df["pivot_high"].iloc[i]):

            pivot_index = i - PIVOT_RIGHT

            if pivot_index >= 0:

                df.loc[
                    i,
                    "pivot_high_rsi"
                ] = df["rsi"].iloc[
                    pivot_index
                ]

    # ========================================================
    # 상승 다이버전스
    #
    # 가격:
    # 현재 Pivot Low < 이전 Pivot Low
    #
    # RSI:
    # 현재 Pivot RSI > 이전 Pivot RSI
    #
    # Pivot 간격:
    # 3 ~ 80 bars
    # ========================================================

    df["bull_divergence"] = pd.Series(
        False,
        index=df.index,
        dtype=bool
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

        current_rsi = df["rsi"].iloc[
            current_pivot_bar
        ]

        if pd.isna(current_rsi):
            continue

        current_rsi = float(
            current_rsi
        )

        bull_divergence = False

        # 이전 Pivot 검색
        for (
            prev_price,
            prev_rsi,
            prev_bar
        ) in zip(
            previous_price_pivots,
            previous_rsi_pivots,
            previous_pivot_bars
        ):

            bars_between = (
                current_pivot_bar -
                prev_bar
            )

            if (
                bars_between >= DIV_MIN_RANGE
                and
                bars_between <= DIV_MAX_RANGE
            ):

                if (
                    current_price < prev_price
                    and
                    current_rsi > prev_rsi
                ):

                    bull_divergence = True
                    break

        if bull_divergence:

            df.loc[
                i,
                "bull_divergence"
            ] = True

        # Pine array.unshift()
        previous_price_pivots.insert(
            0,
            current_price
        )

        previous_rsi_pivots.insert(
            0,
            current_rsi
        )

        previous_pivot_bars.insert(
            0,
            current_pivot_bar
        )

        # 최대 20개
        if len(previous_price_pivots) > 20:

            previous_price_pivots.pop()
            previous_rsi_pivots.pop()
            previous_pivot_bars.pop()

    # ========================================================
    # 원형파
    # ========================================================

    short_window = max(
        4,
        int(MAX_BARS * 0.45)
    )

    df["lowest_40"] = (
        df["low"]
        .rolling(
            window=MAX_BARS,
            min_periods=MAX_BARS
        )
        .min()
    )

    df["lowest_short"] = (
        df["low"]
        .rolling(
            window=short_window,
            min_periods=short_window
        )
        .min()
    )

    df["highest_40"] = (
        df["high"]
        .rolling(
            window=MAX_BARS,
            min_periods=MAX_BARS
        )
        .max()
    )

    df["highest_short"] = (
        df["high"]
        .rolling(
            window=short_window,
            min_periods=short_window
        )
        .max()
    )

    # ========================================================
    # 중요 수정
    #
    # np.isclose()는 ndarray를 반환한다.
    # 따라서 여기서는 Pandas Series를 직접 만든다.
    # ========================================================

    low_equals_lowest = pd.Series(
        False,
        index=df.index,
        dtype=bool
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
                "low"
            ]
            -
            df.loc[
                valid_low,
                "lowest_40"
            ]
        )
        <= 1e-10
    )

    high_equals_highest = pd.Series(
        False,
        index=df.index,
        dtype=bool
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
                "high"
            ]
            -
            df.loc[
                valid_high,
                "highest_40"
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
    # 단계 변수
    # ========================================================

    stage1_long = False
    stage2_long = False

    stage1_short = False

    last_long_bar = None
    last_short_bar = None

    # 결과 배열
    stage1_long_list = []
    stage2_long_list = []

    stage1_short_list = []

    higher_low_list = []
    lower_high_list = []

    long_signal_list = []
    short_signal_list = []

    long_reason_list = []
    short_reason_list = []

    # ========================================================
    # 각 일봉 계산
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

        low1 = df["lowest_40"].iloc[i]
        low2 = df["lowest_short"].iloc[i]

        bars_since_low = (
            df["bars_since_low"].iloc[i]
        )

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
                bars_since_low >= MIN_BARS
                and
                bars_since_low <= MAX_BARS
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
                i - last_long_bar
                >= SIGNAL_COOLDOWN
            )
        )

        # ====================================================
        # 원본 Pine 그대로
        #
        # longSignal =
        # stage1L and circularL and cooldownL
        #
        # stage2L은 최종 조건에 포함되지 않음.
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
                    "과매도 → 상승 다이버전스 "
                    "→ Higher Low"
                )

            else:

                long_reason = (
                    "과매도 → Higher Low"
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

        high1 = df["highest_40"].iloc[i]
        high2 = df["highest_short"].iloc[i]

        bars_since_high = (
            df["bars_since_high"].iloc[i]
        )

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
                bars_since_high >= MIN_BARS
                and
                bars_since_high <= MAX_BARS
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
                i - last_short_bar
                >= SIGNAL_COOLDOWN
            )
        )

        # ====================================================
        # SHORT
        #
        # 과매수 + Lower High
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

        stage1_long_list.append(
            stage1_long
        )

        stage2_long_list.append(
            stage2_long
        )

        stage1_short_list.append(
            stage1_short
        )

        higher_low_list.append(
            higher_low
        )

        lower_high_list.append(
            lower_high
        )

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

    df["stage1_long"] = pd.Series(
        stage1_long_list,
        index=df.index,
        dtype=bool
    )

    df["stage2_long"] = pd.Series(
        stage2_long_list,
        index=df.index,
        dtype=bool
    )

    df["stage1_short"] = pd.Series(
        stage1_short_list,
        index=df.index,
        dtype=bool
    )

    df["higher_low"] = pd.Series(
        higher_low_list,
        index=df.index,
        dtype=bool
    )

    df["lower_high"] = pd.Series(
        lower_high_list,
        index=df.index,
        dtype=bool
    )

    df["long_signal"] = pd.Series(
        long_signal_list,
        index=df.index,
        dtype=bool
    )

    df["short_signal"] = pd.Series(
        short_signal_list,
        index=df.index,
        dtype=bool
    )

    df["long_reason"] = long_reason_list
    df["short_reason"] = short_reason_list

    # ========================================================
    # 최근 120일
    #
    # 계산은 180일 전체에서 수행
    # 실제 관심 구간만 최근 120일
    # ========================================================

    if len(df) > SIGNAL_LOOKBACK:

        recent_df = df.iloc[
            -SIGNAL_LOOKBACK:
        ].copy()

    else:

        recent_df = df.copy()

    # ========================================================
    # 마지막 일봉
    # ========================================================

    last_row = df.iloc[-1]

    long_signal = bool(
        last_row["long_signal"]
    )

    short_signal = bool(
        last_row["short_signal"]
    )

    long_reason = str(
        last_row["long_reason"]
    )

    short_reason = str(
        last_row["short_reason"]
    )

    # ========================================================
    # 반환
    # ========================================================

    return {
        "df": df,
        "recent_df": recent_df,

        "long_signal": long_signal,
        "short_signal": short_signal,

        "long_reason": long_reason,
        "short_reason": short_reason,
    }
