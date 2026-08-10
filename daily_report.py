import os
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import yfinance as yf


BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")

TICKER = "QQQ"
RSI_PERIOD = 14


def send_telegram(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    response = requests.post(
        url,
        data={
            "chat_id": CHAT_ID,
            "text": message
        },
        timeout=20
    )

    response.raise_for_status()


def calculate_rsi(close, period=14):
    delta = close.diff()

    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(
        alpha=1 / period,
        adjust=False
    ).mean()

    avg_loss = loss.ewm(
        alpha=1 / period,
        adjust=False
    ).mean()

    rs = avg_gain / avg_loss

    rsi = 100 - (100 / (1 + rs))

    return rsi


def get_daily_data():

    df = yf.download(
        TICKER,
        period="1y",
        interval="1d",
        auto_adjust=True,
        progress=False,
        multi_level_index=False
    )

    if df.empty:
        raise Exception("QQQ 데이터를 가져오지 못했습니다.")

    close = pd.Series(df["Close"]).astype(float)

    return close


def get_weekly_rsi():

    df = yf.download(
        TICKER,
        period="5y",
        interval="1wk",
        auto_adjust=True,
        progress=False,
        multi_level_index=False
    )

    if df.empty:
        raise Exception("QQQ 주봉 데이터를 가져오지 못했습니다.")

    close = pd.Series(df["Close"]).astype(float)

    weekly_rsi = calculate_rsi(
        close,
        RSI_PERIOD
    ).iloc[-1]

    return float(weekly_rsi)


def main():

    # 뉴욕 시간
    now_ny = datetime.now(
        ZoneInfo("America/New_York")
    )

    today_ny = now_ny.date()

    print("현재 뉴욕 시간:", now_ny)

 

    close = get_daily_data()

    last_date = close.index[-1]

    if hasattr(last_date, "date"):
        last_date = last_date.date()

    # 오늘 거래가 없으면 종료
    if last_date != today_ny:
        print("오늘 미국장 거래 데이터가 없습니다.")
        print("최근 거래일:", last_date)
        return

    # 현재 종가
    price = float(close.iloc[-1])

    # 일봉 RSI
    daily_rsi = float(
        calculate_rsi(
            close,
            RSI_PERIOD
        ).iloc[-1]
    )

    # 주봉 RSI
    weekly_rsi = get_weekly_rsi()

    # 전일 종가
    previous_close = float(close.iloc[-2])

    # 당일 등락률
    change = (
        (price - previous_close)
        / previous_close
        * 100
    )

    # RSI 상태
    events = []

    if daily_rsi <= 30:
        events.append("🔴 일봉 RSI 30 이하")

    if weekly_rsi <= 30:
        events.append("🔴 주봉 RSI 30 이하")

    if not events:
        events.append("특이사항 없음")

    event_text = "\n".join(
        f"• {event}" for event in events
    )

    report = f"""📊 QQQ 일일 리포트
━━━━━━━━━━━━━━━━━━

📅 거래일
{last_date}

💰 종가
${price:.2f}

📈 일봉 RSI(14)
{daily_rsi:.2f}

📊 주봉 RSI(14)
{weekly_rsi:.2f}

📈 당일 등락률
{change:+.2f}%

━━━━━━━━━━━━━━━━━━

🔔 오늘의 RSI 상태

{event_text}
"""

    send_telegram(report)

    print("일일 리포트 전송 완료")


if __name__ == "__main__":
    main()
