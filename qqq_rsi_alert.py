import json
import os
from datetime import datetime

import pandas as pd
import requests
import yfinance as yf

from config import *

STATE_FILE = "alert_state.json"


# ------------------------------
# 상태 읽기
# ------------------------------
def load_state():

    if not os.path.exists(STATE_FILE):

        return {
            "daily_low": False,
            "weekly_low": False
        }

    with open(STATE_FILE, "r", encoding="utf-8") as f:

        return json.load(f)


# ------------------------------
# 상태 저장
# ------------------------------
def save_state(state):

    with open(STATE_FILE, "w", encoding="utf-8") as f:

        json.dump(state, f, indent=4)


# ------------------------------
# 텔레그램
# ------------------------------
def send_telegram(message):

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    requests.post(
        url,
        data={
            "chat_id": CHAT_ID,
            "text": message
        },
        timeout=20
    )


# ------------------------------
# RSI 계산
# ------------------------------
def calculate_rsi(close, period=14):

    delta = close.diff()

    gain = delta.clip(lower=0)

    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(alpha=1/period, adjust=False).mean()

    avg_loss = loss.ewm(alpha=1/period, adjust=False).mean()

    rs = avg_gain / avg_loss

    rsi = 100 - (100 / (1 + rs))

    return rsi


# ------------------------------
# 시세 다운로드
# ------------------------------
def download(interval, period):

    df = yf.download(

        TICKER,

        interval=interval,

        period=period,

        auto_adjust=True,

        progress=False,

        multi_level_index=False

    )

    if df.empty:

        raise Exception("가격을 가져오지 못했습니다.")

    close = pd.Series(df["Close"]).astype(float)

    return close

import json
import os
from datetime import datetime

import pandas as pd
import requests
import yfinance as yf

from config import *

STATE_FILE = "alert_state.json"


# ------------------------------
# 상태 읽기
# ------------------------------
def load_state():

    if not os.path.exists(STATE_FILE):

        return {
            "daily_low": False,
            "weekly_low": False
        }

    with open(STATE_FILE, "r", encoding="utf-8") as f:

        return json.load(f)


# ------------------------------
# 상태 저장
# ------------------------------
def save_state(state):

    with open(STATE_FILE, "w", encoding="utf-8") as f:

        json.dump(state, f, indent=4)


# ------------------------------
# 텔레그램
# ------------------------------
def send_telegram(message):

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    requests.post(
        url,
        data={
            "chat_id": CHAT_ID,
            "text": message
        },
        timeout=20
    )


# ------------------------------
# RSI 계산
# ------------------------------
def calculate_rsi(close, period=14):

    delta = close.diff()

    gain = delta.clip(lower=0)

    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(alpha=1/period, adjust=False).mean()

    avg_loss = loss.ewm(alpha=1/period, adjust=False).mean()

    rs = avg_gain / avg_loss

    rsi = 100 - (100 / (1 + rs))

    return rsi


# ------------------------------
# 시세 다운로드
# ------------------------------
def download(interval, period):

    df = yf.download(

        TICKER,

        interval=interval,

        period=period,

        auto_adjust=True,

        progress=False,

        multi_level_index=False

    )

    if df.empty:

        raise Exception("가격을 가져오지 못했습니다.")

    close = pd.Series(df["Close"]).astype(float)

    return close

# ------------------------------
# 일봉 / 주봉 RSI 가져오기
# ------------------------------
def get_daily_weekly():

    daily_close = download("1d", "1y")
    weekly_close = download("1wk", "5y")

    daily_rsi = calculate_rsi(daily_close).iloc[-1]
    weekly_rsi = calculate_rsi(weekly_close).iloc[-1]

    current_price = daily_close.iloc[-1]

    return (
        float(current_price),
        float(daily_rsi),
        float(weekly_rsi)
    )


# ------------------------------
# 알림 메세지
# ------------------------------
def build_alert(price, daily, weekly):

    message = f"""📉 QQQ RSI 알림

💰 현재가
${price:.2f}

📅 일봉 RSI
{daily:.2f}

📈 주봉 RSI
{weekly:.2f}

"""

    if daily <= RSI_LOW and weekly <= RSI_LOW:

        message += "⚠ 일봉과 주봉 RSI가 모두 30 이하입니다."

    elif daily <= RSI_LOW:

        message += "⚠ 일봉 RSI가 30 이하입니다."

    elif weekly <= RSI_LOW:

        message += "⚠ 주봉 RSI가 30 이하입니다."

    return message


# ------------------------------
# RSI 체크
# ------------------------------
def check_rsi():

    state = load_state()

    price, daily_rsi, weekly_rsi = get_daily_weekly()

    print(f"현재가 : {price:.2f}")

    print(f"일봉 RSI : {daily_rsi:.2f}")

    print(f"주봉 RSI : {weekly_rsi:.2f}")

    send = False

    if daily_rsi <= RSI_LOW:

        if not state["daily_low"]:

            send = True

            state["daily_low"] = True

    else:

        state["daily_low"] = False

    if weekly_rsi <= RSI_LOW:

        if not state["weekly_low"]:

            send = True

            state["weekly_low"] = True

    else:

        state["weekly_low"] = False

    if send:

        send_telegram(

            build_alert(

                price,

                daily_rsi,

                weekly_rsi

            )

        )

        print("텔레그램 알림 전송")

    else:

        print("알림 없음")

    save_state(state)

# ------------------------------
# 일일 리포트
# ------------------------------
def send_daily_report():

    price, daily_rsi, weekly_rsi = get_daily_weekly()

    daily_close = download("1d", "1y")

    today = datetime.now().strftime("%Y-%m-%d")

    change = (
        (daily_close.iloc[-1] - daily_close.iloc[-2])
        / daily_close.iloc[-2]
        * 100
    )

    high_52 = daily_close.max()
    low_52 = daily_close.min()

    down_from_high = (
        (price - high_52) / high_52 * 100
    )

    up_from_low = (
        (price - low_52) / low_52 * 100
    )

    report = f"""
📊 QQQ 일일 리포트

📅 날짜
{today}

💰 종가
${price:.2f}

📈 일봉 RSI
{daily_rsi:.2f}

📊 주봉 RSI
{weekly_rsi:.2f}

📈 당일 등락률
{change:.2f}%

🏆 52주 최고가 대비
{down_from_high:.2f}%

📉 52주 최저가 대비
+{up_from_low:.2f}%
"""

    send_telegram(report)

    print("일일 리포트 전송 완료")


# ------------------------------
# 메인
# ------------------------------
if __name__ == "__main__":

    print("QQQ RSI 모니터 시작")

    check_rsi()

    # 장 종료 리포트는 GitHub Actions에서
    # 하루 한 번 별도 실행하도록 설정 예정