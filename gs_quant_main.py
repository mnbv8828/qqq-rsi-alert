import os
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas_market_calendars as mcal

from gs_quant_config import (
    BENCHMARK,
    STOCK_SCORE_THRESHOLD,
)

from gs_quant_data import (
    get_data,
    get_nasdaq100_tickers,
)

from gs_quant_indicators import add_indicators
from gs_quant_stock_ranking import rank_stocks
from gs_quant_entry_timing import calculate_entry_timing
from gs_quant_telegram import send_message


# ============================================================
# 기본 설정
# ============================================================

NY_TZ = ZoneInfo("America/New_York")

TEST_MODE = (
    os.environ.get("TEST_MODE", "false").lower()
    == "true"
)

# Yahoo 데이터 재시도
YAHOO_MAX_WAIT_MINUTES = 30
YAHOO_RETRY_INTERVAL_MINUTES = 5

# 장 마감 후 허용 실행 시간
MARKET_CLOSE_GRACE_MINUTES = 120

# 최소 데이터
MIN_REQUIRED_BARS = 252


# ============================================================
# NYSE 실제 마감시간 확인
# ============================================================

def get_nyse_market_close(now_ny):
    """
    현재 날짜의 NYSE 실제 마감시간 반환.

    정규장:
        16:00 ET

    조기폐장:
        13:00 ET 등

    pandas_market_calendars가
    서머타임 / 겨울시간 / 조기폐장을 처리한다.
    """

    nyse = mcal.get_calendar("NYSE")

    today = now_ny.date()

    schedule = nyse.schedule(
        start_date=today,
        end_date=today,
    )

    if schedule.empty:
        return None

    market_close = schedule.iloc[0]["market_close"]

    if market_close.tzinfo is None:
        market_close = market_close.tz_localize("UTC")

    return market_close.tz_convert(NY_TZ)


# ============================================================
# 시장 상태 확인
# ============================================================

def check_market_status():
    """
    TEST_MODE:
        시장시간 검사 생략

    LIVE MODE:
        NYSE 거래일 확인
        실제 마감시간 확인
        마감 후 120분 이내인지 확인
    """

    now_ny = datetime.now(NY_TZ)

    print()
    print("========================================")
    print("MARKET STATUS")
    print("========================================")

    print(
        "현재 뉴욕 시간:",
        now_ny.strftime(
            "%Y-%m-%d %H:%M:%S %Z"
        ),
    )

    # --------------------------------------------------------
    # TEST MODE
    # --------------------------------------------------------

    if TEST_MODE:

        print("🧪 TEST_MODE=true")
        print(
            "NYSE 시장시간 검사를 건너뜁니다."
        )

        return True, None, now_ny

    # --------------------------------------------------------
    # NYSE 실제 마감시간
    # --------------------------------------------------------

    market_close = get_nyse_market_close(
        now_ny
    )

    # --------------------------------------------------------
    # 휴장일
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # 아직 장이 끝나지 않은 경우
    # --------------------------------------------------------

    if now_ny < market_close:

        print(
            "아직 미국장이 마감되지 않았습니다."
        )

        return False, market_close, now_ny

    # --------------------------------------------------------
    # 장 마감 후 경과시간
    # --------------------------------------------------------

    elapsed = now_ny - market_close

    elapsed_minutes = (
        elapsed.total_seconds() / 60
    )

    print(
        f"장 마감 후 경과: "
        f"{elapsed_minutes:.1f}분"
    )

    # --------------------------------------------------------
    # 마감 후 120분 초과
    # --------------------------------------------------------

    if elapsed > timedelta(
        minutes=MARKET_CLOSE_GRACE_MINUTES
    ):

        print(
            "장 마감 후 허용시간을 "
            "초과했습니다."
        )

        return False, market_close, now_ny

    print(
        "시장시간 조건 통과."
    )

    return True, market_close, now_ny


# ============================================================
# Nasdaq-100 데이터 수집
# ============================================================

def analyze_all(tickers):
    """
    Nasdaq-100 전체 종목 데이터를 수집하고
    indicator를 계산한다.

    QQQ는 benchmark로 사용하므로
    ticker 목록에 없더라도 별도로 확보한다.
    """

    raw = {}
    missing_data = []

    # --------------------------------------------------------
    # QQQ를 데이터 수집 대상에 반드시 포함
    # --------------------------------------------------------

    download_tickers = list(tickers)

    if BENCHMARK not in download_tickers:
        download_tickers.append(BENCHMARK)

    total = len(download_tickers)

    print()
    print("========================================")
    print("GS QUANT DATA COLLECTION")
    print("========================================")

    print(
        f"전체 데이터 대상: {total}개"
    )

    # --------------------------------------------------------
    # 데이터 수집
    # --------------------------------------------------------

    for index, ticker in enumerate(
        download_tickers,
        1,
    ):

        try:

            print(
                f"[{index}/{total}] "
                f"{ticker} ... ",
                end="",
                flush=True,
            )

            df = get_data(ticker)

            if (
                df is None
                or len(df) < MIN_REQUIRED_BARS
            ):

                missing_data.append(ticker)

                print(
                    "FAIL (데이터 부족)"
                )

                continue

            # ------------------------------------------------
            # Indicator 계산
            # ------------------------------------------------

            df = add_indicators(df)

            raw[ticker] = df

            print(
                f"OK ({len(df)} bars)"
            )

        except Exception as e:

            missing_data.append(ticker)

            print(
                f"FAIL ({repr(e)})"
            )

    # --------------------------------------------------------
    # 결과
    # --------------------------------------------------------

    print()
    print(
        "========================================"
    )

    print(
        f"데이터 확보: "
        f"{len(raw)}/{total}"
    )

    if missing_data:

        print(
            "데이터 누락:",
            ", ".join(missing_data),
        )

    print(
        "========================================"
    )

    return raw, missing_data


# ============================================================
# Stock Ranking + Entry Timing
# ============================================================

def calculate_rankings(raw, tickers):
    """
    Stock Ranking >= 75인 종목만 선정.

    선정된 모든 종목에 대해
    Entry Timing을 계산한다.
    """

    # --------------------------------------------------------
    # Benchmark 확인
    # --------------------------------------------------------

    if BENCHMARK not in raw:

        raise RuntimeError(
            f"Benchmark {BENCHMARK} "
            "data unavailable."
        )

    benchmark = raw[BENCHMARK]

    rankings = []

    print()
    print(
        "========================================"
    )

    print(
        "CALCULATING STOCK RANKING"
    )

    print(
        "========================================"
    )

    # --------------------------------------------------------
    # Nasdaq-100 종목 순회
    # --------------------------------------------------------

    for ticker in tickers:

        # QQQ는 benchmark
        if ticker == BENCHMARK:
            continue

        if ticker not in raw:
            continue

        df = raw[ticker]

        try:

            # ------------------------------------------------
            # Stock Ranking
            # ------------------------------------------------

            result = rank_stocks(
                ticker,
                df,
                benchmark,
            )

            stock_score = int(
                result["stock_score"]
            )

            print(
                f"{ticker:<6} "
                f"Stock Ranking = "
                f"{stock_score}/100"
            )

            # ------------------------------------------------
            # 75점 이상만 표시
            # ------------------------------------------------

            if (
                stock_score
                >= STOCK_SCORE_THRESHOLD
            ):

                entry_score = (
                    calculate_entry_timing(
                        df,
                        benchmark,
                    )
                )

                result["entry_score"] = int(
                    entry_score
                )

                rankings.append(result)

        except Exception as e:

            print(
                f"{ticker} "
                f"ranking failed: "
                f"{repr(e)}"
            )

    # --------------------------------------------------------
    # Stock Ranking 높은 순으로 정렬
    # --------------------------------------------------------

    rankings.sort(
        key=lambda x: x["stock_score"],
        reverse=True,
    )

    return rankings


# ============================================================
# Telegram 메시지 생성
#
# Stock Ranking / Entry Timing을
# 별도 섹션으로 나누지 않고
# 종목별로 통합해서 표시
# ============================================================

def build_message(rankings, now_ny):

    now_text = now_ny.strftime(
        "%Y-%m-%d %H:%M ET"
    )

    lines = [
        "━━━━━━━━━━━━━━━━━━",
        "📊 NASDAQ 100 STOCK RANKING",
        "━━━━━━━━━━━━━━━━━━",
        f"기준시간: {now_text}",
        "",
    ]

    # --------------------------------------------------------
    # 75점 이상 종목이 없는 경우
    # --------------------------------------------------------

    if not rankings:

        lines.append(
            f"{STOCK_SCORE_THRESHOLD}점 이상 종목 없음"
        )

        return "\n".join(lines)

    # --------------------------------------------------------
    # 종목별 통합 표시
    # --------------------------------------------------------

    for index, result in enumerate(
        rankings,
        1,
    ):

        ticker = result["ticker"]

        stock_score = int(
            result["stock_score"]
        )

        entry_score = int(
            result["entry_score"]
        )

        # ----------------------------------------------------
        # Entry Timing 등급
        # ----------------------------------------------------

        if entry_score >= 75:

            label = "🟢 STRONG"

        elif entry_score >= 50:

            label = "🟡 WATCH"

        else:

            label = "🔴 WEAK"

        lines += [
            f"{index}. {ticker}",
            f"Stock Ranking  "
            f"{stock_score}/100",
            f"Entry Timing   "
            f"{entry_score}/85",
            label,
            "",
        ]

    return "\n".join(
        lines
    ).rstrip()


# ============================================================
# Yahoo 데이터 재시도
# ============================================================

def get_live_data_with_retry(tickers):
    """
    LIVE MODE 전용.

    QQQ benchmark가 확보될 때까지
    최대 30분 동안
    5분 간격으로 재시도한다.
    """

    max_attempts = (
        YAHOO_MAX_WAIT_MINUTES
        // YAHOO_RETRY_INTERVAL_MINUTES
    ) + 1

    last_raw = {}
    last_missing = []

    for attempt in range(
        1,
        max_attempts + 1,
    ):

        print()
        print(
            "========================================"
        )

        print(
            "Yahoo data attempt "
            f"{attempt}/{max_attempts}"
        )

        print(
            "========================================"
        )

        raw, missing_data = (
            analyze_all(tickers)
        )

        last_raw = raw
        last_missing = missing_data

        # ----------------------------------------------------
        # QQQ 확보
        # ----------------------------------------------------

        if BENCHMARK in raw:

            print()
            print(
                f"{BENCHMARK} data available."
            )

            return (
                raw,
                missing_data,
            )

        # ----------------------------------------------------
        # 마지막 시도
        # ----------------------------------------------------

        if attempt >= max_attempts:

            print()
            print(
                "========================================"
            )

            print(
                "Yahoo data retry failed."
            )

            print(
                f"최대 대기시간: "
                f"{YAHOO_MAX_WAIT_MINUTES}분"
            )

            if last_missing:

                print(
                    "누락:",
                    ", ".join(
                        last_missing
                    ),
                )

            print(
                "Telegram 메시지를 "
                "전송하지 않습니다."
            )

            print(
                "========================================"
            )

            return (
                last_raw,
                last_missing,
            )

        # ----------------------------------------------------
        # 5분 대기
        # ----------------------------------------------------

        print()
        print(
            f"{YAHOO_RETRY_INTERVAL_MINUTES}분 후 "
            "다시 확인합니다."
        )

        time.sleep(
            YAHOO_RETRY_INTERVAL_MINUTES
            * 60
        )

    return (
        last_raw,
        last_missing,
    )


# ============================================================
# Main
# ============================================================

def main():

    print()
    print(
        "========================================"
    )

    print(
        "GS QUANT ANALYZER"
    )

    print(
        "========================================"
    )

    print(
        f"TEST_MODE: {TEST_MODE}"
    )

    print(
        f"BENCHMARK: {BENCHMARK}"
    )

    print(
        f"STOCK SCORE THRESHOLD: "
        f"{STOCK_SCORE_THRESHOLD}"
    )

    # ========================================================
    # 1. Nasdaq-100 universe 가져오기
    # ========================================================

    print()
    print(
        "Loading Nasdaq-100 universe..."
    )

    try:

        tickers = (
            get_nasdaq100_tickers()
        )

    except Exception as e:

        print()
        print(
            "Nasdaq-100 universe "
            "loading failed:"
        )

        print(
            repr(e)
        )

        raise

    if not tickers:

        raise RuntimeError(
            "Nasdaq-100 ticker list is empty."
        )

    print(
        f"Nasdaq-100 universe: "
        f"{len(tickers)} stocks"
    )

    # ========================================================
    # 2. 시장 상태 확인
    # ========================================================

    (
        should_run,
        market_close,
        now_ny,
    ) = check_market_status()

    if not should_run:

        print()
        print(
            "GS Quant 분석을 "
            "실행하지 않습니다."
        )

        return

    # ========================================================
    # 3. 데이터 수집
    # ========================================================

    if TEST_MODE:

        print()
        print(
            "========================================"
        )

        print(
            "🧪 TEST MODE"
        )

        print(
            "시장시간 검사 및 "
            "Yahoo 재시도 제한을 건너뜁니다."
        )

        print(
            "즉시 분석을 시작합니다."
        )

        print(
            "========================================"
        )

        raw, missing_data = (
            analyze_all(tickers)
        )

    else:

        print()
        print(
            "========================================"
        )

        print(
            "LIVE MODE"
        )

        print(
            f"Yahoo 최대 대기: "
            f"{YAHOO_MAX_WAIT_MINUTES}분"
        )

        print(
            f"재시도 간격: "
            f"{YAHOO_RETRY_INTERVAL_MINUTES}분"
        )

        print(
            "========================================"
        )

        raw, missing_data = (
            get_live_data_with_retry(
                tickers
            )
        )

    # ========================================================
    # 4. Benchmark 확인
    # ========================================================

    if BENCHMARK not in raw:

        raise RuntimeError(
            f"Benchmark {BENCHMARK} "
            "data unavailable."
        )

    # ========================================================
    # 5. Stock Ranking + Entry Timing
    # ========================================================

    rankings = calculate_rankings(
        raw,
        tickers,
    )

    # ========================================================
    # 6. 결과 요약
    # ========================================================

    print()
    print(
        "========================================"
    )

    print(
        "RESULT"
    )

    print(
        "========================================"
    )

    usable_stock_count = sum(
        1
        for ticker in tickers
        if ticker in raw
    )

    print(
        f"Usable Nasdaq-100 stocks: "
        f"{usable_stock_count}/"
        f"{len(tickers)}"
    )

    print(
        f"Stock Ranking >= "
        f"{STOCK_SCORE_THRESHOLD}: "
        f"{len(rankings)}"
    )

    # ========================================================
    # 7. Telegram 메시지 생성
    # ========================================================

    message = build_message(
        rankings,
        now_ny,
    )

    # ========================================================
    # 8. 콘솔 출력
    # ========================================================

    print()
    print(
        "========================================"
    )

    print(
        message
    )

    print(
        "========================================"
    )

    # ========================================================
    # 9. Telegram 전송
    # ========================================================

    print()
    print(
        "Sending Telegram message..."
    )

    try:

        send_message(
            message
        )

        print(
            "Telegram message sent successfully."
        )

    except Exception as e:

        print(
            "Telegram send failed:"
        )

        print(
            repr(e)
        )

        raise


# ============================================================
# 실행
# ============================================================

if __name__ == "__main__":
    main()
