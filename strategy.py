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

# 실제 신호를 확인할 최근 일수
SIGNAL_LOOKBACK = 120


# ============================================================
# RSI
# TradingView ta.rsi()와 최대한 동일하게
# Wilder RMA 방식 사용
# ============================================================

def calculate_rsi(series: pd.Series, length: int = 14) -> pd.Series:

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

    rs = avg_gain / avg_loss.replace(0, np.nan)

    rsi = 100 - (100 / (1 + rs))

    # 상승만 계속되는 경우 TradingView RSI의 100 처리
    rsi = rsi.where(
        avg_loss != 0,
        100
    )

    # 하락만 계속되는 경우 0
    rsi = rsi.where(
        avg_gain != 0,
        0
    )

    return rsi


# ============================================================
# Pivot Low
#
# Pine:
# ta.pivotlow(low, 3, 3)
#
# 현재 bar에서 pivot이 확정되지만,
# 실제 pivot 위치는 3개 전 bar.
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

    pivot_value = lows.iloc[pivot_index]

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
        pivot_value <= left_values.min()
        and
        pivot_value <= right_values.max()
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

    pivot_value = highs.iloc[pivot_index]

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
        pivot_value >= left_values.max()
        and
        pivot_value >= right_values.max()
    )


# ============================================================
# ta.lowest()
# ============================================================

def rolling_lowest(
    series: pd.Series,
    length: int
) -> pd.Series:

    return series.rolling(
        window=length,
        min_periods=length
    ).min()


# ============================================================
# ta.highest()
# ============================================================

def rolling_highest(
    series: pd.Series,
    length: int
) -> pd.Series:

    return series.rolling(
        window=length,
        min_periods=length
    ).max()


# ============================================================
# barssince()
#
# Pine:
# ta.barssince(condition)
#
# 현재 bar부터 거꾸로 가면서 가장 최근 True까지의 bar 수
# ============================================================

def bars_since(
    condition: pd.Series
) -> pd.Series:

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
# 전략 실행
# ============================================================

def run_strategy(
    df: pd.DataFrame
):

    df = df.copy()

    # --------------------------------------------------------
    # 컬럼 확인
    # --------------------------------------------------------

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
    # Pivot 계산
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

    df["pivot_low"] = pivot_low_flags
    df["pivot_high"] = pivot_high_flags

    # ========================================================
    # Pivot RSI
    # ========================================================

    df["pivot_low_rsi"] = np.nan
    df["pivot_high_rsi"] = np.nan

    for i in range(len(df)):

        if df["pivot_low"].iloc[i]:

            pivot_index = i - PIVOT_RIGHT

            if pivot_index >= 0:

                df.loc[
                    i,
                    "pivot_low_rsi"
                ] = df["rsi"].iloc[
                    pivot_index
                ]

        if df["pivot_high"].iloc[i]:

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
    # Pine 원본:
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

        current_price = df["low"].iloc[
            current_pivot_bar
        ]

        current_rsi = df["rsi"].iloc[
            current_pivot_bar
        ]

        if pd.isna(current_rsi):
            continue

        bull_divergence = False

        # Pine:
        # array에 저장된 이전 pivot들을 검사
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

        # Pine:
        # if array.size > 20
        # array.pop()
        if len(previous_price_pivots) > 20:

            previous_price_pivots.pop()
            previous_rsi_pivots.pop()
            previous_pivot_bars.pop()

    # ========================================================
    # 단계 상태 변수
    # ========================================================

    stage1_long = False
    stage2_long = False

    stage1_short = False

    last_long_bar = None
    last_short_bar = None

    # 결과 저장
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
    # 원형파 계산
    # ========================================================

    short_window = max(
        4,
        int(MAX_BARS * 0.45)
    )

    df["lowest_40"] = rolling_lowest(
        df["low"],
        MAX_BARS
    )

    df["lowest_short"] = rolling_lowest(
        df["low"],
        short_window
    )

    df["highest_40"] = rolling_highest(
        df["high"],
        MAX_BARS
    )

    df["highest_short"] = rolling_highest(
        df["high"],
        short_window
    )

    # Pine:
    #
    # barsSinceLow =
    # nz(ta.barssince(low == low1), 0)
    #
    # low1 = ta.lowest(low, maxBars)

    low_equals_lowest = (
        np.isclose(
            df["low"],
            df["lowest_40"],
            rtol=1e-10,
            atol=1e-10
        )
    )

    high_equals_highest = (
        np.isclose(
            df["high"],
            df["highest_40"],
            rtol=1e-10,
            atol=1e-10
        )
    )

    df["bars_since_low"] = bars_since(
        low_equals_lowest
    )

    df["bars_since_high"] = bars_since(
        high_equals_highest
    )

    # ========================================================
    # 각 bar 전략 계산
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
        # LONG 1단계: 과매도
        # ====================================================

        if is_oversold:

            if not stage1_long:

                stage1_long = True
                stage2_long = False

        # ====================================================
        # 과매도 → 숏 단계 취소
        # ====================================================

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
        #
        # Pine:
        #
        # low1 = ta.lowest(low, maxBars)
        #
        # low2 = ta.lowest(
        #     low,
        #     math.max(
        #         4,
        #         int(maxBars * 0.45)
        #     )
        # )
        #
        # higherLow =
        # low2 > low1 * (1 + minHL / 100)
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
                low2
                >
                low1 * (
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
            i - last_long_bar
            >= SIGNAL_COOLDOWN
        )

        # ====================================================
        # 중요
        #
        # 원본 Pine의 최종 조건:
        #
        # longSignal =
        # stage1L
        # and circularL
        # and cooldownL
        #
        # 즉 stage2L을 강제하지 않음.
        #
        # 따라서 상승 다이버전스가 없어도
        # 과매도 상태 + Higher Low면 LONG.
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

            # Pine:
            # stage2L := false
            stage2_long = False

        # ====================================================
        # LONG 단계 종료
        #
        # Pine:
        #
        # if not isOversold
        #     stage1L := false
        #     oversoldLabeled := false
        # ====================================================

        if not is_oversold:

            stage1_long = False

            # 원본 Pine에서는 여기서
            # stage2L은 직접 false로 만들지 않음.
            #
            # 다만 새로운 과매도 사이클을 위해
            # stage1이 끝난 상태에서 남은 stage2가
            # 다음 사이클에 영향을 주지 않도록 정리.
            if not stage1_long:

                stage2_long = False

        # ====================================================
        # SHORT 1단계: 과매수
        # ====================================================

        if is_overbought:

            if not stage1_short:

                stage1_short = True

        # ====================================================
        # 과매수 → 롱 단계 취소
        # ====================================================

        if is_overbought:

            stage1_long = False
            stage2_long = False

        # ====================================================
        # Lower High
        #
        # Pine:
        #
        # high1 = ta.highest(high, maxBars)
        # high2 = ta.highest(high, shortWindow)
        #
        # lowerHigh =
        # high2 < high1 * (1 - minHL / 100)
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
                high2
                <
                high1 * (
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
            i - last_short_bar
            >= SIGNAL_COOLDOWN
        )

        # ====================================================
        # SHORT
        #
        # 과매수 + Lower High
        # 하락 다이버전스 없음
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
    # 결과 DataFrame
    # ========================================================

    df["stage1_long"] = stage1_long_list
    df["stage2_long"] = stage2_long_list

    df["stage1_short"] = stage1_short_list

    df["higher_low"] = higher_low_list
    df["lower_high"] = lower_high_list

    df["long_signal"] = long_signal_list
    df["short_signal"] = short_signal_list

    df["long_reason"] = long_reason_list
    df["short_reason"] = short_reason_list

    # ========================================================
    # 최근 120일만 신호 확인
    #
    # 계산 자체는 전체 데이터에서 하고
    # 실제 알람 후보는 최근 120일 범위로 제한
    # ========================================================

    if len(df) > SIGNAL_LOOKBACK:

        recent_start = (
            len(df) - SIGNAL_LOOKBACK
        )

        recent_df = df.iloc[
            recent_start:
        ].copy()

    else:

        recent_df = df.copy()

    # ========================================================
    # 가장 마지막 일봉
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
