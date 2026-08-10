import json
import os
import sys
from datetime import datetime

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

STATE_FILE = "alert_state.json"


# ============================================================
# 상태
# ============================================================

def load_state():

    if not os.path.exists(STATE_FILE):

        return {}

    try:

        with open(
            STATE_FILE,
            "r",
            encoding="utf-8"
        ) as f:

            return json.load(f)

    except Exception:

        return {}


def save_state(state):

    with open(
        STATE_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            state,
            f,
            ensure_ascii=False,
            indent=2
        )


# ============================================================
# Telegram
# ============================================================

def send_telegram(message):

    if not BOT_TOKEN or not CHAT_ID:

        print(
            "BOT_TOKEN 또는 CHAT_ID가 없습니다."
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
# Yahoo Finance
# ============================================================

def get_data(ticker):

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
            f"{ticker}: 데이터 없음"
        )

    # yfinance MultiIndex 대응
    if isinstance(
        df.columns,
        pd.MultiIndex
    ):

        df.columns = (
            df.columns
            .get_level_values(0)
        )

    df = df.rename(
        columns={
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "volume",
        }
    )

    required = [
        "open",
        "high",
        "low",
        "close",
    ]

    for col in required:

        if col not in df.columns:

            raise RuntimeError(
                f"{ticker}: {col} 없음"
            )

    df = df[
        required
    ].dropna()

    # 최근 120일만 전략 신호 확인
    # 계산 자체는 180일 데이터로 수행
    return df


# ============================================================
# 가격
# ============================================================

def fmt_price(value):

    return f"{float(value):,.2f}"


# ============================================================
# Telegram 메시지
# ============================================================

def make_long_message(
    ticker,
    row,
    reason
):

    date = str(
        row["date"]
    )

    return (
        "🟢 LONG 진입 신호\n"
        "\n"
        f"종목: {ticker}\n"
        f"일봉: {date}\n"
        f"현재가: ${fmt_price(row['close'])}\n"
        f"RSI: {row['rsi']:.2f}\n"
        "\n"
        f"조건: {reason}\n"
        "\n"
        "X Trading Indicator"
    )


def make_short_message(
    ticker,
    row,
    reason
):

    date = str(
        row["date"]
    )

    return (
        "🔴 SHORT 진입 신호\n"
        "\n"
        f"종목: {ticker}\n"
        f"일봉: {date}\n"
        f"현재가: ${fmt_price(row['close'])}\n"
        f"RSI: {row['rsi']:.2f}\n"
        "\n"
        f"조건: {reason}\n"
        "\n"
        "X Trading Indicator"
    )


# ============================================================
# 메인
# ============================================================

def main():

    if not BOT_TOKEN or not CHAT_ID:

        print(
            "GitHub Secrets에 "
            "BOT_TOKEN / CHAT_ID를 설정하세요."
        )

        sys.exit(1)

    state = load_state()

    print("=" * 60)
    print("X Trading Indicator")
    print("기준: 최근 120일 / 일봉")
    print("=" * 60)

    for ticker in TICKERS:

        try:

            df = get_data(ticker)

            # 날짜를 별도 컬럼으로 저장
            df["date"] = [
                str(x.date())
                if hasattr(x, "date")
                else str(x)
                for x in df.index
            ]

            # ------------------------------------------------
            # 전략 계산
            # ------------------------------------------------

            result = run_strategy(df)

            result_df = result["df"]

            # 마지막 확정 일봉
            row = result_df.iloc[-1]

            signal_date = str(
                row["date"]
            )

            print()
            print(
                f"[{ticker}] "
                f"{signal_date}"
            )

            print(
                f"가격: "
                f"${fmt_price(row['close'])}"
            )

            print(
                f"RSI: "
                f"{row['rsi']:.2f}"
            )

            print(
                "과매도: "
                f"{row['stage1_long']}"
            )

            print(
                "상승 다이버전스: "
                f"{row['bull_divergence']}"
            )

            print(
                "Higher Low: "
                f"{row['higher_low']}"
            )

            print(
                "과매수: "
                f"{row['stage1_short']}"
            )

            print(
                "Lower High: "
                f"{row['lower_high']}"
            )

            # ------------------------------------------------
            # 최근 120일 범위 확인
            # ------------------------------------------------

            # 데이터 자체는 180일을 사용하지만
            # 알람은 마지막 봉 기준
            #
            # signal key:
            # ticker + 날짜 + 방향
            #
            # 같은 일봉에서 중복 Telegram 방지
            # ------------------------------------------------

            # LONG
            if result["long_signal"]:

                signal_key = (
                    f"{ticker}_"
                    f"{signal_date}_LONG"
                )

                if not state.get(
                    signal_key,
                    False
                ):

                    message = (
                        make_long_message(
                            ticker,
                            row,
                            result[
                                "long_reason"
                            ]
                        )
                    )

                    if send_telegram(
                        message
                    ):

                        state[
                            signal_key
                        ] = True

                else:

                    print(
                        "이미 보낸 LONG 신호"
                    )

            # SHORT
            elif result["short_signal"]:

                signal_key = (
                    f"{ticker}_"
                    f"{signal_date}_SHORT"
                )

                if not state.get(
                    signal_key,
                    False
                ):

                    message = (
                        make_short_message(
                            ticker,
                            row,
                            result[
                                "short_reason"
                            ]
                        )
                    )

                    if send_telegram(
                        message
                    ):

                        state[
                            signal_key
                        ] = True

                else:

                    print(
                        "이미 보낸 SHORT 신호"
                    )

            else:

                print(
                    "→ 현재 신호 없음"
                )

        except Exception as e:

            print(
                f"[{ticker}] 오류: {e}"
            )

    save_state(state)

    print()
    print("완료")


if __name__ == "__main__":

    main()
