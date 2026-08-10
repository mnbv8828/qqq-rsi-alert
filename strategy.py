import numpy as np
import pandas as pd


# ============================================================
# RSI
# ============================================================

def calculate_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()

    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(
        alpha=1 / period,
        adjust=False,
        min_periods=period
    ).mean()

    avg_loss = loss.ewm(
        alpha=1 / period,
        adjust=False,
        min_periods=period
    ).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)

    return 100 - (100 / (1 + rs))


# ============================================================
# Pine ta.pivotlow()
# ============================================================

def pivot_low(
    series: pd.Series,
    left: int,
    right: int
) -> pd.Series:

    result = pd.Series(
        np.nan,
        index=series.index,
        dtype=float
    )

    values = series.to_numpy()

    for i in range(left, len(series) - right):

        center = values[i]

        if np.isnan(center):
            continue

        left_values = values[i - left:i]
        right_values = values[i + 1:i + right + 1]

        if (
            np.isnan(left_values).any()
            or np.isnan(right_values).any()
        ):
            continue

        if (
            center <= left_values.min()
            and center <= right_values.min()
        ):
            # Pine에서는 right bar가 지난 시점에 확정
            result.iloc[i + right] = center

    return result


# ============================================================
# Pine ta.pivothigh()
# ============================================================

def pivot_high(
    series: pd.Series,
    left: int,
    right: int
) -> pd.Series:

    result = pd.Series(
        np.nan,
        index=series.index,
        dtype=float
    )

    values = series.to_numpy()

    for i in range(left, len(series) - right):

        center = values[i]

        if np.isnan(center):
            continue

        left_values = values[i - left:i]
        right_values = values[i + 1:i + right + 1]

        if (
            np.isnan(left_values).any()
            or np.isnan(right_values).any()
        ):
            continue

        if (
            center >= left_values.max()
            and center >= right_values.max()
        ):
            result.iloc[i + right] = center

    return result


# ============================================================
# 전략
# ============================================================

def run_strategy(
    df: pd.DataFrame,

    rsi_length: int = 14,

    oversold_level: float = 30.0,
    overbought_level: float = 70.0,

    pivot_left: int = 3,
    pivot_right: int = 3,

    div_min_range: int = 3,
    div_max_range: int = 80,

    min_bars: int = 5,
    max_bars: int = 40,

    min_hl: float = 0.15,

    signal_cooldown: int = 25,
):

    df = df.copy().reset_index(drop=True)

    # --------------------------------------------------------
    # RSI
    # --------------------------------------------------------

    df["rsi"] = calculate_rsi(
        df["close"],
        rsi_length
    )

    df["oversold"] = (
        df["rsi"] <= oversold_level
    )

    df["overbought"] = (
        df["rsi"] >= overbought_level
    )

    # --------------------------------------------------------
    # Pivot
    # --------------------------------------------------------

    df["pivot_low"] = pivot_low(
        df["low"],
        pivot_left,
        pivot_right
    )

    df["rsi_pivot_low"] = pivot_low(
        df["rsi"],
        pivot_left,
        pivot_right
    )

    df["pivot_high"] = pivot_high(
        df["high"],
        pivot_left,
        pivot_right
    )

    # --------------------------------------------------------
    # 상태 변수
    # --------------------------------------------------------

    stage1L = False
    stage2L = False

    stage1S = False

    last_long_bar = None
    last_short_bar = None

    oversold_bar = None
    overbought_bar = None

    # Pine 배열
    pl_price_arr = []
    pl_rsi_arr = []
    pl_bar_arr = []

    # 결과
    df["bull_divergence"] = False
    df["higher_low"] = False
    df["lower_high"] = False

    df["stage1_long"] = False
    df["stage2_long"] = False
    df["stage1_short"] = False

    df["long_signal"] = False
    df["short_signal"] = False

    long_reason = ""
    short_reason = ""

    # ========================================================
    # BAR LOOP
    # ========================================================

    for i in range(len(df)):

        row = df.iloc[i]

        low = float(row["low"])
        high = float(row["high"])

        rsi = row["rsi"]

        is_oversold = (
            not pd.isna(rsi)
            and rsi <= oversold_level
        )

        is_overbought = (
            not pd.isna(rsi)
            and rsi >= overbought_level
        )

        # ====================================================
        # LONG 1단계: 과매도
        # ====================================================

        if is_oversold:

            if not stage1L:

                oversold_bar = i

                stage1L = True
                stage2L = False

            # 원본:
            # 과매도 → 숏 단계 취소
            stage1S = False

        # ====================================================
        # 상승 다이버전스
        # ====================================================

        bull_div_now = False

        pl = df.iloc[i]["pivot_low"]
        rsi_pl = df.iloc[i]["rsi_pivot_low"]

        if (
            not pd.isna(pl)
            and not pd.isna(rsi_pl)
        ):

            curr_pivot_bar = i - pivot_right

            if len(pl_price_arr) > 0:

                for j in range(len(pl_price_arr)):

                    prev_price = pl_price_arr[j]
                    prev_rsi = pl_rsi_arr[j]
                    prev_bar = pl_bar_arr[j]

                    bars_between = (
                        curr_pivot_bar - prev_bar
                    )

                    if (
                        bars_between >= div_min_range
                        and bars_between <= div_max_range
                    ):

                        # Pine:
                        #
                        # if pl < prevPrice
                        # and rsiPL > prevRsi

                        if (
                            pl < prev_price
                            and rsi_pl > prev_rsi
                        ):

                            bull_div_now = True
                            break

            # Pine array.unshift()
            pl_price_arr.insert(0, float(pl))
            pl_rsi_arr.insert(0, float(rsi_pl))
            pl_bar_arr.insert(0, curr_pivot_bar)

            # 최대 20개
            if len(pl_price_arr) > 20:

                pl_price_arr.pop()
                pl_rsi_arr.pop()
                pl_bar_arr.pop()

        if bull_div_now:

            df.loc[
                i,
                "bull_divergence"
            ] = True

        # ====================================================
        # LONG 2단계
        # ====================================================

        if (
            stage1L
            and bull_div_now
            and not stage2L
        ):

            stage2L = True

        # ====================================================
        # 원형파 / Higher Low
        #
        # Pine:
        #
        # low1 = ta.lowest(low, maxBars)
        # low2 = ta.lowest(low, maxBars * 0.45)
        #
        # ====================================================

        start_max = max(
            0,
            i - maxBars + 1
        )

        long_window = df.iloc[
            start_max:i + 1
        ]

        low1 = float(
            long_window["low"].min()
        )

        short_length = max(
            4,
            int(maxBars * 0.45)
        )

        start_short = max(
            0,
            i - short_length + 1
        )

        short_window = df.iloc[
            start_short:i + 1
        ]

        low2 = float(
            short_window["low"].min()
        )

        # Pine:
        #
        # barsSinceLow =
        # ta.barssince(low == low1)

        bars_since_low = 0

        for k in range(
            i,
            start_max - 1,
            -1
        ):

            if float(df.iloc[k]["low"]) == low1:

                bars_since_low = i - k
                break

        higher_low = (
            low2 >
            low1 * (1 + min_hl / 100)
        )

        bars_ok_l = (
            bars_since_low >= min_bars
            and bars_since_low <= maxBars
        )

        circular_l = (
            higher_low
            and bars_ok_l
        )

        df.loc[
            i,
            "higher_low"
        ] = circular_l

        # ====================================================
        # LONG FINAL
        # ====================================================

        cooldown_l = (
            last_long_bar is None
            or (
                i - last_long_bar
                >= signal_cooldown
            )
        )

        long_signal = (
            stage1L
            and circular_l
            and cooldown_l
        )

        # 마지막 확정봉 포함 모든 봉 계산
        if long_signal:

            df.loc[
                i,
                "long_signal"
            ] = True

            last_long_bar = i

            if stage2L:

                long_reason = (
                    "과매도 → "
                    "상승 다이버전스 → "
                    "Higher Low → 진입"
                )

            else:

                long_reason = (
                    "과매도 → "
                    "Higher Low → 진입"
                )

            # Pine 원본 그대로
            stage2L = False

        # ====================================================
        # 과매도가 아니면 LONG 상태 종료
        #
        # ★ 중요: Pine 원본 그대로
        # ====================================================

        if not is_oversold:

            stage1L = False
            # Pine:
            # oversoldLabeled := false

        # ====================================================
        # SHORT 1단계: 과매수
        # ====================================================

        if is_overbought:

            if not stage1S:

                overbought_bar = i

                stage1S = True

            # 과매수 → 롱 단계 취소
            stage1L = False
            stage2L = False

        # ====================================================
        # Lower High
        # ====================================================

        high1 = float(
            long_window["high"].max()
        )

        high2 = float(
            short_window["high"].max()
        )

        bars_since_high = 0

        for k in range(
            i,
            start_max - 1,
            -1
        ):

            if float(df.iloc[k]["high"]) == high1:

                bars_since_high = i - k
                break

        lower_high = (
            high2 <
            high1 * (1 - min_hl / 100)
        )

        bars_ok_s = (
            bars_since_high >= min_bars
            and bars_since_high <= maxBars
        )

        circular_s = (
            lower_high
            and bars_ok_s
        )

        df.loc[
            i,
            "lower_high"
        ] = circular_s

        # ====================================================
        # SHORT FINAL
        #
        # Pine 원본:
        #
        # 과매수 + Lower High
        #
        # ====================================================

        cooldown_s = (
            last_short_bar is None
            or (
                i - last_short_bar
                >= signal_cooldown
            )
        )

        short_signal = (
            stage1S
            and circular_s
            and cooldown_s
        )

        if short_signal:

            df.loc[
                i,
                "short_signal"
            ] = True

            last_short_bar = i

            short_reason = (
                "과매수 → "
                "Lower High → 하락 진입"
            )

        # ====================================================
        # 과매수가 아니면 SHORT 종료
        # ====================================================

        if not is_overbought:

            stage1S = False

        # ====================================================
        # 상태 저장
        # ====================================================

        df.loc[
            i,
            "stage1_long"
        ] = stage1L

        df.loc[
            i,
            "stage2_long"
        ] = stage2L

        df.loc[
            i,
            "stage1_short"
        ] = stage1S

    # ========================================================
    # 마지막 확정봉
    # ========================================================

    last = df.iloc[-1]

    return {
        "df": df,

        "long_signal": bool(
            last["long_signal"]
        ),

        "short_signal": bool(
            last["short_signal"]
        ),

        "long_reason": long_reason,

        "short_reason": short_reason,
    }
