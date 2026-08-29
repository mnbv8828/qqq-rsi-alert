import os
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import requests


# ============================================================
# 기본 설정
# ============================================================

SYMBOL = "005930"
SYMBOL_NAME = "삼성전자"

RSI_LENGTH = 14

# RSI 알림 기준
OVERSOLD_LEVEL = 35.0
OVERBOUGHT_LEVEL = 70.0

BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")

KIS_APP_KEY = os.environ.get("KIS_APP_KEY")
KIS_APP_SECRET = os.environ.get("KIS_APP_SECRET")

# GitHub Actions 수동 테스트 모드
TEST_MODE = (
    os.environ.get("TEST_MODE", "false").lower()
    == "true"
)

KST = ZoneInfo("Asia/Seoul")

BASE_URL = "https://openapi.koreainvestment.com:9443"

TOKEN_API = "/oauth2/tokenP"

MINUTE_API = (
    "/uapi/domestic-stock/v1/quotations/"
    "inquire-time-dailychartprice"
)

TR_ID = "FHKST03010230"

# RSI 계산용 과거 거래일
HISTORY_TRADING_DAYS = 10

TOKEN_MAX_RETRIES = 5
DATA_MAX_RETRIES = 3

CONNECT_TIMEOUT = 10
READ_TIMEOUT = 30


# ============================================================
# Telegram
# ============================================================

def send_telegram(message):

    if not BOT_TOKEN or not CHAT_ID:
        print("BOT_TOKEN 또는 CHAT_ID가 없습니다.")
        return False

    url = (
        f"https://api.telegram.org/"
        f"bot{BOT_TOKEN}/sendMessage"
    )

    try:

        response = requests.post(
            url,
            data={
                "chat_id": CHAT_ID,
                "text": message,
            },
            timeout=15,
        )

        response.raise_for_status()

        print("Telegram 전송 성공")

        return True

    except Exception as e:

        print(
            f"Telegram 전송 실패: {e}"
        )

        return False


# ============================================================
# KIS Access Token
# ============================================================

def get_access_token():

    if not KIS_APP_KEY:
        raise RuntimeError(
            "KIS_APP_KEY가 없습니다."
        )

    if not KIS_APP_SECRET:
        raise RuntimeError(
            "KIS_APP_SECRET가 없습니다."
        )

    url = f"{BASE_URL}{TOKEN_API}"

    headers = {
        "content-type": "application/json"
    }

    body = {
        "grant_type": "client_credentials",
        "appkey": KIS_APP_KEY,
        "appsecret": KIS_APP_SECRET,
    }

    last_error = None

    for attempt in range(
        1,
        TOKEN_MAX_RETRIES + 1
    ):

        print(
            f"KIS 토큰 요청 "
            f"{attempt}/{TOKEN_MAX_RETRIES}"
        )

        try:

            response = requests.post(
                url,
                headers=headers,
                json=body,
                timeout=(
                    CONNECT_TIMEOUT,
                    READ_TIMEOUT,
                ),
            )

            print(
                f"KIS 토큰 HTTP 응답: "
                f"{response.status_code}"
            )

            if response.status_code == 200:

                data = response.json()

                token = data.get(
                    "access_token"
                )

                if token:

                    print(
                        "KIS Access Token 발급 성공"
                    )

                    return token

                last_error = (
                    "access_token이 없습니다.\n"
                    f"{data}"
                )

            else:

                last_error = (
                    f"HTTP {response.status_code}\n"
                    f"{response.text}"
                )

        except requests.exceptions.ConnectTimeout as e:

            last_error = (
                f"KIS 연결 시간 초과: {e}"
            )

            print(
                "KIS 서버 연결 시간 초과"
            )

        except requests.exceptions.ReadTimeout as e:

            last_error = (
                f"KIS 응답 시간 초과: {e}"
            )

            print(
                "KIS 서버 응답 시간 초과"
            )

        except requests.exceptions.RequestException as e:

            last_error = (
                f"KIS 네트워크 오류: {e}"
            )

            print(
                f"KIS 네트워크 오류: {e}"
            )

        except Exception as e:

            last_error = str(e)

            print(
                f"예상하지 못한 오류: {e}"
            )

        if attempt < TOKEN_MAX_RETRIES:

            wait_seconds = 5 * attempt

            print(
                f"{wait_seconds}초 후 재시도..."
            )

            time.sleep(
                wait_seconds
            )

    raise RuntimeError(
        "KIS Access Token 발급 최종 실패\n"
        f"{last_error}"
    )


# ============================================================
# 하루치 1분봉 조회
# ============================================================

def get_minute_bars_for_date(
    token,
    target_date,
):

    date_str = target_date.strftime(
        "%Y%m%d"
    )

    all_rows = []

    current_time = "153000"

    for page in range(10):

        print(
            f"{date_str} "
            f"분봉 조회 "
            f"{page + 1}/10 "
            f"(기준 {current_time})"
        )

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
            "appkey": KIS_APP_KEY,
            "appsecret": KIS_APP_SECRET,
            "tr_id": TR_ID,
            "custtype": "P",
        }

        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": SYMBOL,
            "FID_INPUT_HOUR_1": current_time,
            "FID_INPUT_DATE_1": date_str,
            "FID_PW_DATA_INCU_YN": "Y",
            "FID_FAKE_TICK_INCU_YN": "",
        }

        response = None
        last_error = None
        success = False

        for attempt in range(
            1,
            DATA_MAX_RETRIES + 1
        ):

            try:

                response = requests.get(
                    f"{BASE_URL}{MINUTE_API}",
                    headers=headers,
                    params=params,
                    timeout=(
                        CONNECT_TIMEOUT,
                        READ_TIMEOUT,
                    ),
                )

                if response.status_code == 200:

                    success = True
                    break

                last_error = (
                    f"HTTP {response.status_code}\n"
                    f"{response.text}"
                )

                print(
                    f"분봉 조회 실패 "
                    f"{attempt}/{DATA_MAX_RETRIES}"
                )

            except requests.exceptions.RequestException as e:

                last_error = str(e)

                print(
                    f"분봉 네트워크 오류 "
                    f"{attempt}/{DATA_MAX_RETRIES}: "
                    f"{e}"
                )

            if attempt < DATA_MAX_RETRIES:

                time.sleep(
                    3 * attempt
                )

        if not success:

            raise RuntimeError(
                f"{date_str} 분봉 조회 실패\n"
                f"{last_error}"
            )

        data = response.json()

        if data.get("rt_cd") != "0":

            print(
                "KIS API 오류"
            )

            print(
                f"msg_cd: "
                f"{data.get('msg_cd')}"
            )

            print(
                f"msg1: "
                f"{data.get('msg1')}"
            )

            break

        rows = data.get(
            "output2",
            []
        )

        if not rows:
            break

        all_rows.extend(rows)

        times = [
            row.get(
                "stck_cntg_hour",
                ""
            )
            for row in rows
            if row.get(
                "stck_cntg_hour"
            )
        ]

        if not times:
            break

        oldest_time = min(times)

        if oldest_time <= "090000":
            break

        if len(rows) < 120:
            break

        current_time = oldest_time

        time.sleep(0.3)

    records = []

    for row in all_rows:

        time_value = row.get(
            "stck_cntg_hour"
        )

        if not time_value:
            continue

        try:

            dt = datetime.strptime(
                f"{date_str}{time_value}",
                "%Y%m%d%H%M%S",
            ).replace(
                tzinfo=KST
            )

            # ====================================================
            # 한국 정규장 범위
            #
            # 09:00:00 이상
            # 15:30:00 미만
            #
            # ====================================================

            market_open = dt.replace(
                hour=9,
                minute=0,
                second=0,
                microsecond=0,
            )

            market_close = dt.replace(
                hour=15,
                minute=30,
                second=0,
                microsecond=0,
            )

            if dt < market_open:
                continue

            if dt >= market_close:
                continue

            records.append(
                {
                    "datetime": dt,
                    "open": float(
                        row["stck_oprc"]
                    ),
                    "high": float(
                        row["stck_hgpr"]
                    ),
                    "low": float(
                        row["stck_lwpr"]
                    ),
                    "close": float(
                        row["stck_prpr"]
                    ),
                    "volume": int(
                        row["cntg_vol"]
                    ),
                }
            )

        except (
            KeyError,
            ValueError,
            TypeError,
        ):

            continue

    if not records:

        return pd.DataFrame(
            columns=[
                "datetime",
                "open",
                "high",
                "low",
                "close",
                "volume",
            ]
        )

    df = pd.DataFrame(
        records
    )

    df = (
        df
        .drop_duplicates(
            subset=["datetime"]
        )
        .sort_values(
            "datetime"
        )
        .reset_index(
            drop=True
        )
    )

    print(
        f"{date_str} → "
        f"{len(df)}개 1분봉"
    )

    return df


# ============================================================
# 최근 거래일 데이터
# ============================================================

def get_historical_minute_bars(
    token
):

    today = datetime.now(
        KST
    ).date()

    all_frames = []

    current_date = today
    checked_days = 0

    while (
        checked_days < 20
        and len(all_frames)
        < HISTORY_TRADING_DAYS
    ):

        if current_date.weekday() < 5:

            try:

                df = get_minute_bars_for_date(
                    token,
                    current_date,
                )

                if not df.empty:

                    all_frames.append(
                        df
                    )

            except Exception as e:

                print(
                    f"{current_date} "
                    f"조회 실패: {e}"
                )

        current_date -= timedelta(
            days=1
        )

        checked_days += 1

    if not all_frames:

        raise RuntimeError(
            "과거 분봉 데이터를 "
            "가져오지 못했습니다."
        )

    result = pd.concat(
        all_frames,
        ignore_index=True,
    )

    result = (
        result
        .drop_duplicates(
            subset=["datetime"]
        )
        .sort_values(
            "datetime"
        )
        .reset_index(
            drop=True
        )
    )

    print("================================")

    print(
        f"전체 1분봉 : "
        f"{len(result)}개"
    )

    print(
        f"시작 : "
        f"{result['datetime'].iloc[0]}"
    )

    print(
        f"마지막 : "
        f"{result['datetime'].iloc[-1]}"
    )

    print("================================")

    return result


# ============================================================
# 1분봉 → 정확한 30분봉
#
# 중요:
# 완성되지 않은 30분봉은 절대 사용하지 않는다.
# ============================================================

def make_30m_bars(
    df
):

    if df.empty:
        return pd.DataFrame()

    data = df.copy()

    data["datetime"] = pd.to_datetime(
        data["datetime"]
    )

    data = data.set_index(
        "datetime"
    )

    # ========================================================
    # 반드시 09:00 이상 15:30 미만만 사용
    # ========================================================

    market_open = datetime.strptime(
        "09:00",
        "%H:%M"
    ).time()

    market_close = datetime.strptime(
        "15:30",
        "%H:%M"
    ).time()

    data = data[
        (data.index.time >= market_open)
        &
        (data.index.time < market_close)
    ]

    if data.empty:
        return pd.DataFrame()

    # ========================================================
    # 먼저 30분봉 생성
    # ========================================================

    bars = (
        data
        .resample(
            "30min",
            origin="start_day",
            offset="9h",
            label="left",
            closed="left",
        )
        .agg(
            {
                "open": "first",
                "high": "max",
                "low": "min",
                "close": "last",
                "volume": "sum",
            }
        )
    )

    bars = bars.dropna(
        subset=[
            "open",
            "high",
            "low",
            "close",
        ]
    )

    if bars.empty:
        return pd.DataFrame()

    # ========================================================
    # 핵심 수정
    #
    # 각 30분봉이 실제로 완성되었는지 확인
    #
    # 예:
    #
    # 15:00~15:30 봉
    # 실제 마지막 데이터가 15:19
    #
    # → 미완성 봉이므로 제거
    #
    # 정상:
    #
    # 15:00~15:30
    # 마지막 데이터 >= 15:29
    #
    # → 완성봉으로 인정
    # ========================================================

    completed_bars = []

    for timestamp in bars.index:

        end_time = (
            timestamp
            + timedelta(minutes=30)
        )

        # 15:30 이후 시작 봉 제거
        if end_time > timestamp.replace(
            hour=15,
            minute=30,
            second=0,
            microsecond=0,
        ):
            continue

        # 해당 30분 구간의 원본 1분봉
        segment = data[
            (data.index >= timestamp)
            &
            (data.index < end_time)
        ]

        if segment.empty:
            continue

        first_time = segment.index.min()
        last_time = segment.index.max()

        # ====================================================
        # 완성 여부 판단
        #
        # 시작 직후 데이터가 존재하고
        # 마지막 1분이 29분 지점까지 존재해야 함
        # ====================================================

        expected_first = timestamp

        expected_last = (
            end_time
            - timedelta(minutes=1)
        )

        if first_time > (
            expected_first
            + timedelta(minutes=1)
        ):
            print(
                f"미완성 30분봉 제외 "
                f": {timestamp.strftime('%H:%M')}~"
                f"{end_time.strftime('%H:%M')} "
                f"(첫 데이터 {first_time.strftime('%H:%M')})"
            )
            continue

        if last_time < expected_last:
            print(
                f"미완성 30분봉 제외 "
                f": {timestamp.strftime('%H:%M')}~"
                f"{end_time.strftime('%H:%M')} "
                f"(마지막 데이터 "
                f"{last_time.strftime('%H:%M')})"
            )
            continue

        completed_bars.append(
            timestamp
        )

    bars = bars.loc[
        completed_bars
    ]

    # ========================================================
    # 최종 안전장치
    # ========================================================

    bars = bars[
        bars.index.time
        <
        datetime.strptime(
            "15:30",
            "%H:%M"
        ).time()
    ]

    print(
        f"완성된 30분봉 : "
        f"{len(bars)}개"
    )

    return bars


# ============================================================
# Wilder RSI(14)
# ============================================================

def calculate_rsi_wilder(
    close,
    length=14,
):

    close = pd.Series(
        close,
        dtype="float64",
    )

    delta = close.diff()

    gain = delta.clip(
        lower=0
    )

    loss = -delta.clip(
        upper=0
    )

    rsi = pd.Series(
        float("nan"),
        index=close.index,
        dtype="float64",
    )

    if len(close) <= length:
        return rsi

    avg_gain = gain.iloc[
        1:length + 1
    ].mean()

    avg_loss = loss.iloc[
        1:length + 1
    ].mean()

    if avg_loss == 0:

        if avg_gain == 0:
            rsi.iloc[length] = 50.0
        else:
            rsi.iloc[length] = 100.0

    else:

        rs = (
            avg_gain
            / avg_loss
        )

        rsi.iloc[length] = (
            100.0
            -
            (
                100.0
                / (1.0 + rs)
            )
        )

    for i in range(
        length + 1,
        len(close),
    ):

        current_gain = (
            gain.iloc[i]
        )

        current_loss = (
            loss.iloc[i]
        )

        avg_gain = (
            (
                avg_gain
                * (length - 1)
            )
            +
            current_gain
        ) / length

        avg_loss = (
            (
                avg_loss
                * (length - 1)
            )
            +
            current_loss
        ) / length

        if avg_loss == 0:

            if avg_gain == 0:
                rsi.iloc[i] = 50.0
            else:
                rsi.iloc[i] = 100.0

        else:

            rs = (
                avg_gain
                / avg_loss
            )

            rsi.iloc[i] = (
                100.0
                -
                (
                    100.0
                    / (1.0 + rs)
                )
            )

    return rsi


# ============================================================
# 마지막 완성 30분봉
# ============================================================

def get_last_completed_bar(
    bars
):

    now = datetime.now(
        KST
    )

    completed = []

    for timestamp in bars.index:

        timestamp = timestamp.to_pydatetime()

        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(
                tzinfo=KST
            )

        end_time = (
            timestamp
            + timedelta(minutes=30)
        )

        # ====================================================
        # 현재 시각 기준 실제 완성 여부
        # ====================================================

        if end_time > now:
            continue

        # ====================================================
        # 정규장 마지막 종료 시각 15:30
        # ====================================================

        market_close = timestamp.replace(
            hour=15,
            minute=30,
            second=0,
            microsecond=0,
        )

        if end_time > market_close:
            continue

        completed.append(
            timestamp
        )

    if not completed:

        raise RuntimeError(
            "완성된 30분봉이 없습니다."
        )

    timestamp = completed[-1]

    return (
        timestamp,
        bars.loc[timestamp],
    )


# ============================================================
# 30분봉 시간 표시
# ============================================================

def format_30m_period(
    timestamp
):

    if hasattr(timestamp, "to_pydatetime"):
        timestamp = timestamp.to_pydatetime()

    end_time = (
        timestamp
        + timedelta(minutes=30)
    )

    market_close = timestamp.replace(
        hour=15,
        minute=30,
        second=0,
        microsecond=0,
    )

    if end_time > market_close:
        end_time = market_close

    return (
        f"{timestamp.strftime('%Y-%m-%d %H:%M')}"
        f"~"
        f"{end_time.strftime('%H:%M')}"
    )


# ============================================================
# RSI 확인 + 알림
# ============================================================

def check_rsi(
    bars
):

    data = bars.copy()

    data["RSI"] = calculate_rsi_wilder(
        data["close"],
        RSI_LENGTH,
    )

    timestamp, current = (
        get_last_completed_bar(
            data
        )
    )

    current_rsi = float(
        current["RSI"]
    )

    position = data.index.get_loc(
        timestamp
    )

    if position <= 0:

        raise RuntimeError(
            "이전 30분봉이 없습니다."
        )

    previous_rsi = float(
        data["RSI"].iloc[
            position - 1
        ]
    )

    close = float(
        current["close"]
    )

    period_text = format_30m_period(
        timestamp
    )

    print("================================")
    print("최종 RSI 확인")
    print("================================")

    print(
        f"30분봉 : "
        f"{period_text}"
    )

    print(
        f"종가 : "
        f"{close:,.0f}원"
    )

    print(
        f"현재 RSI(14) : "
        f"{current_rsi:.2f}"
    )

    print(
        f"이전 RSI(14) : "
        f"{previous_rsi:.2f}"
    )

    print("================================")

    # ========================================================
    # TEST MODE
    # ========================================================

    if TEST_MODE:

        if current_rsi <= OVERSOLD_LEVEL:

            status = (
                f"🟢 RSI {OVERSOLD_LEVEL:.0f} 이하"
            )

        elif current_rsi >= OVERBOUGHT_LEVEL:

            status = (
                f"🔴 RSI {OVERBOUGHT_LEVEL:.0f} 이상"
            )

        else:

            status = "⚪ 정상 구간"

        message = (
            "🧪 삼성전자 30분봉 RSI 테스트\n\n"
            f"종목 : {SYMBOL_NAME} ({SYMBOL})\n"
            "주기 : 30분봉\n"
            "지표 : RSI(14)\n"
            "데이터 : 한국투자증권\n\n"
            f"30분봉 : {period_text}\n"
            f"종가 : {close:,.0f}원\n\n"
            f"RSI(14) : {current_rsi:.2f}\n"
            f"이전 RSI : {previous_rsi:.2f}\n\n"
            f"{status}\n\n"
            "※ 완성된 30분봉만 사용"
        )

        send_telegram(
            message
        )

        return

    # ========================================================
    # RSI 35 이하 진입
    #
    # 이전 RSI > 35
    # 현재 RSI <= 35
    # ========================================================

    if (
        previous_rsi > OVERSOLD_LEVEL
        and current_rsi <= OVERSOLD_LEVEL
    ):

        message = (
            "🟢 삼성전자 RSI 35 이하 진입\n\n"
            f"종목 : {SYMBOL_NAME} ({SYMBOL})\n"
            "주기 : 30분봉\n"
            "지표 : RSI(14)\n"
            "데이터 : 한국투자증권\n\n"
            f"30분봉 : {period_text}\n"
            f"종가 : {close:,.0f}원\n"
            f"RSI(14) : {current_rsi:.2f}\n"
            f"이전 RSI : {previous_rsi:.2f}\n\n"
            "📉 RSI가 35 이하로 "
            "진입했습니다.\n\n"
            "※ 완성된 30분봉 기준"
        )

        send_telegram(
            message
        )

        return

    # ========================================================
    # RSI 70 이상 진입
    #
    # 이전 RSI < 70
    # 현재 RSI >= 70
    # ========================================================

    if (
        previous_rsi < OVERBOUGHT_LEVEL
        and current_rsi >= OVERBOUGHT_LEVEL
    ):

        message = (
            "🔴 삼성전자 RSI 70 이상 진입\n\n"
            f"종목 : {SYMBOL_NAME} ({SYMBOL})\n"
            "주기 : 30분봉\n"
            "지표 : RSI(14)\n"
            "데이터 : 한국투자증권\n\n"
            f"30분봉 : {period_text}\n"
            f"종가 : {close:,.0f}원\n"
            f"RSI(14) : {current_rsi:.2f}\n"
            f"이전 RSI : {previous_rsi:.2f}\n\n"
            "📈 RSI가 70 이상으로 "
            "진입했습니다.\n\n"
            "※ 완성된 30분봉 기준"
        )

        send_telegram(
            message
        )

        return

    print(
        "RSI 35/70 신규 진입 없음"
    )


# ============================================================
# 장중 여부
# ============================================================

def is_market_hours():

    if TEST_MODE:

        print(
            "TEST_MODE=True "
            "→ 장시간 체크 생략"
        )

        return True

    now = datetime.now(
        KST
    )

    if now.weekday() >= 5:

        print(
            "주말 → 종료"
        )

        return False

    current_minutes = (
        now.hour * 60
        + now.minute
    )

    # ========================================================
    # GitHub Actions 실제 실행 허용 시간
    #
    # 09:35 ~ 15:35
    #
    # YAML에서도 동일하게 설정하지만
    # Python에서도 이중으로 보호
    # ========================================================

    start_minutes = (
        9 * 60 + 35
    )

    end_minutes = (
        15 * 60 + 35
    )

    if (
        start_minutes
        <= current_minutes
        <= end_minutes
    ):

        return True

    print(
        f"실행 가능 시간 외 → "
        f"{now.strftime('%H:%M:%S')}"
    )

    return False


# ============================================================
# MAIN
# ============================================================

def main():

    start = datetime.now(
        KST
    )

    print(
        "========================================"
    )

    print(
        "삼성전자 30분봉 RSI 알림"
    )

    print(
        "KIS + Wilder RSI(14)"
    )

    print(
        "과매도 기준 : RSI 35 이하"
    )

    print(
        "과매수 기준 : RSI 70 이상"
    )

    print(
        "30분봉 범위 : 09:00~15:30"
    )

    print(
        "실행 범위 : 09:35~15:35"
    )

    print(
        "========================================"
    )

    print(
        f"실행 : "
        f"{start.strftime('%Y-%m-%d %H:%M:%S')}"
    )

    print(
        f"TEST_MODE : "
        f"{TEST_MODE}"
    )

    print(
        "========================================"
    )

    if not is_market_hours():
        return

    token = get_access_token()

    minute_df = (
        get_historical_minute_bars(
            token
        )
    )

    bars = make_30m_bars(
        minute_df
    )

    print(
        f"생성된 완성 30분봉 : "
        f"{len(bars)}개"
    )

    if not bars.empty:

        print(
            "마지막 완성 30분봉 : "
            f"{format_30m_period(bars.index[-1])}"
        )

    if len(bars) < (
        RSI_LENGTH + 2
    ):

        raise RuntimeError(
            "RSI 계산에 필요한 "
            "완성 30분봉 데이터가 부족합니다."
        )

    check_rsi(
        bars
    )

    elapsed = (
        datetime.now(KST)
        - start
    ).total_seconds()

    print(
        "================================"
    )

    print(
        f"총 실행시간 : "
        f"{elapsed:.1f}초"
    )

    print(
        "================================"
    )


# ============================================================
# 실행
# ============================================================

if __name__ == "__main__":

    try:

        main()

    except Exception as e:

        print(
            "================================"
        )

        print(
            f"최종 오류 : {e}"
        )

        print(
            "================================"
        )

        if (
            TEST_MODE
            and BOT_TOKEN
            and CHAT_ID
        ):

            send_telegram(
                "⚠️ 삼성전자 RSI 테스트 오류\n\n"
                f"{e}"
            )

        raise
