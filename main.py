import os
import sys

import pandas as pd
import requests
import yfinance as yf

from strategy import run_strategy


# ============================================================
# 설정
# ============================================================

TICKERS = [
    x.strip()
    for x in os.getenv(
        "TICKERS",
        "QQQ"
    ).split(",")
    if x.strip()
]

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")


# ============================================================
# Telegram
# ============================================================

def send_telegram(message: str) -> bool:

    if not BOT_TOKEN or not CHAT_ID:

        print(
            "ERROR: BOT_TOKEN 또는 CHAT_ID가 없습니다."
        )

        return False

    url = (
        "https://api.telegram.org/bot"
        f"{BOT_TOKEN}/sendMessage"
    )

    payload = {
        "chat_id": CHAT_ID,
        "text": message,
    }

    try:

        response = requests.post(
            url,
            data=payload,
            timeout=20
        )

        response.raise_for_status()

        print("Telegram 전송 완료")

        return True

    except Exception as e:

        print(
            f"Telegram 전송 실패: {e}"
        )

        return False


# ============================================================
# Yahoo Finance 일봉 데이터
# ============================================================

def get_data(ticker: str) -> pd.DataFrame:

    print(
        f"[{ticker}] 최근 180일 일봉 다운로드"
    )

    df = yf.download(
        ticker,
        period="180d",
        interval="1d",
        auto_adjust=False,
        progress=False,
        prepost=False,
    )

    if df.empty:

        raise RuntimeError(
            f"{ticker}: Yahoo Finance 데이터가 없습니다."
        )

    # --------------------------------------------------------
    # yfinance MultiIndex 대응
    # --------------------------------------------------------

    if isinstance(
        df.columns,
        pd.MultiIndex
    ):

        df.columns = (
            df.columns
            .get_level_values(0)
        )

    # --------------------------------------------------------
    # 컬럼 이름 변경
    # --------------------------------------------------------

    df = df.rename(
        columns={
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "volume",
        }
    )

    required_columns = [
        "open",
        "high",
        "low",
        "close",
    ]

    for column in required_columns:

        if column not in df.columns:

            raise RuntimeError(
                f"{ticker}: {column} 데이터가 없습니다."
            )

    df = df[
        required_columns
    ].dropna()

    if len(df) < 100:

        raise RuntimeError(
            f"{ticker}: 일봉 데이터가 너무 적습니다. "
            f"현재 {len(df)}개"
        )

    # --------------------------------------------------------
    # 날짜
    # --------------------------------------------------------

    df["date"] = [
        str(index.date())
        if hasattr(index, "date")
        else str(index)
        for index in df.index
    ]

    df = df.reset_index(drop=True)

    return df


# ============================================================
# 가격 표시
# ============================================================

def format_price(value) -> str:

    return f"{float(value):,.2f}"


# ============================================================
# TRUE / FALSE 표시
# ============================================================

def check_mark(value) -> str:

    return "✅" if bool(value) else "❌"


# ============================================================
# 일일 리포트
# ============================================================

def make_daily_report(
    ticker: str,
    row: pd.Series,
    result: dict
) -> str:

    long_signal = bool(
        result["long_signal"]
    )

    short_signal = bool(
        result["short_signal"]
    )

    # --------------------------------------------------------
    # 최종 판정
    # --------------------------------------------------------

    if long_signal:

        status = (
            "🚨 LONG 진입 신호"
        )

    elif short_signal:

        status = (
            "🚨 SHORT 진입 신호"
        )

    else:

        status = (
            "⏸ 진입 신호 없음"
        )

    # --------------------------------------------------------
    # LONG 조건
    # --------------------------------------------------------

    long_reason = (
        result["long_reason"]
        if result["long_reason"]
        else "없음"
    )

    # --------------------------------------------------------
    # SHORT 조건
    # --------------------------------------------------------

    short_reason = (
        result["short_reason"]
        if result["short_reason"]
        else "없음"
    )

    # --------------------------------------------------------
    # 메시지
    # --------------------------------------------------------

    message = (
        "📊 QQQ 일봉 전략 리포트\n"
        "\n"
        f"종목: {ticker}\n"
        f"기준일: {row['date']}\n"
        f"현재가: ${format_price(row['close'])}\n"
        f"RSI: {row['rsi']:.2f}\n"
        "\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "🟢 LONG 조건\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"🟠 과매도: "
        f"{check_mark(row['stage1_long'])}\n"
        f"🟢 상승 다이버전스: "
        f"{check_mark(row['bull_divergence'])}\n"
        f"🔵 Higher Low: "
        f"{check_mark(row['higher_low'])}\n"
        f"▶ LONG: "
        f"{'🚨 발생' if long_signal else '❌ 없음'}\n"
        f"조건: {long_reason}\n"
        "\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "🔴 SHORT 조건\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"🔴 과매수: "
        f"{check_mark(row['stage1_short'])}\n"
        f"🟣 Lower High: "
        f"{check_mark(row['lower_high'])}\n"
        f"▶ SHORT: "
        f"{'🚨 발생' if short_signal else '❌ 없음'}\n"
        f"조건: {short_reason}\n"
        "\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"📌 최종 판정: {status}\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "\n"
        "기준: 일봉\n"
        "계산 데이터: 최근 180일\n"
        "관심 구간: 최근 120일\n"
        "\n"
        "X Trading Indicator"
    )

    return message


# ============================================================
# 콘솔 상태 출력
# ============================================================

def print_status(
    ticker: str,
    row: pd.Series
):

    print()
    print("=" * 60)
    print(f"[{ticker}]")
    print("=" * 60)

    print(
        f"일봉: {row['date']}"
    )

    print(
        f"가격: ${format_price(row['close'])}"
    )

    print(
        f"RSI: {row['rsi']:.2f}"
    )

    print(
        f"과매도: {row['stage1_long']}"
    )

    print(
        f"상승 다이버전스: "
        f"{row['bull_divergence']}"
    )

    print(
        f"Higher Low: "
        f"{row['higher_low']}"
    )

    print(
        f"과매수: "
        f"{row['stage1_short']}"
    )

    print(
        f"Lower High: "
        f"{row['lower_high']}"
    )

    print(
        f"LONG: "
        f"{row['long_signal']}"
    )

    print(
        f"SHORT: "
        f"{row['short_signal']}"
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 60)
    print("X Trading Indicator")
    print("기준: 일봉")
    print("전략 계산 데이터: 최근 180일")
    print("관심 구간: 최근 120일")
    print("Telegram: 매일 장 마감 후 리포트 전송")
    print("=" * 60)

    # --------------------------------------------------------
    # Telegram 설정 확인
    # --------------------------------------------------------

    if not BOT_TOKEN or not CHAT_ID:

        print(
            "ERROR: GitHub Secrets에 "
            "BOT_TOKEN / CHAT_ID를 설정하세요."
        )

        sys.exit(1)

    # --------------------------------------------------------
    # 종목별 검사
    # --------------------------------------------------------

    for ticker in TICKERS:

        try:

            # =================================================
            # 데이터 다운로드
            # =================================================

            df = get_data(ticker)

            # =================================================
            # 전략 계산
            # =================================================

            result = run_strategy(df)

            result_df = result["df"]

            # 마지막 일봉
            row = result_df.iloc[-1]

            # =================================================
            # 상태 출력
            # =================================================

            print_status(
                ticker,
                row
            )

            # =================================================
            # 일일 리포트 생성
            # =================================================

            message = make_daily_report(
                ticker,
                row,
                result
            )

            print()
            print(
                "📨 오늘의 Telegram 리포트 전송"
            )

            # =================================================
            # Telegram 전송
            #
            # 신호가 없어도 무조건 전송
            # =================================================

            send_telegram(
                message
            )

            # =================================================
            # 콘솔 표시
            # =================================================

            if result["long_signal"]:

                print(
                    "🟢 LONG 신호 발생!"
                )

            elif result["short_signal"]:

                print(
                    "🔴 SHORT 신호 발생!"
                )

            else:

                print(
                    "→ 현재 진입 신호 없음"
                )

        except Exception as e:

            print()
            print(
                f"❌ [{ticker}] 오류 발생:"
            )

            print(e)

    print()
    print("=" * 60)
    print("실행 완료")
    print("=" * 60)


# ============================================================
# 실행
# ============================================================

if __name__ == "__main__":
    main()
