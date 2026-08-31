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

# 알람 기준
OVERSOLD_LEVEL = 35.0
OVERBOUGHT_LEVEL = 70.0

BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")

KIS_APP_KEY = os.environ.get("KIS_APP_KEY")
KIS_APP_SECRET = os.environ.get("KIS_APP_SECRET")

TEST_MODE = (
    os.environ.get("TEST_MODE", "false").lower()
    == "true"
)

KST = ZoneInfo("Asia/Seoul")


# ============================================================
# KIS API
# ============================================================

BASE_URL = (
    "https://openapi.koreainvestment.com:9443"
)

TOKEN_API = "/oauth2/tokenP"


# ------------------------------------------------------------
# 당일분봉조회
# FHKST03010200
# ------------------------------------------------------------

TODAY_MINUTE_API = (
    "/uapi/domestic-stock/v1/quotations/"
    "inquire-time-itemchartprice"
)

TODAY_TR_ID = "FHKST03010200"


# ------------------------------------------------------------
# 과거 거래일 분봉조회
# FHKST03010230
# ------------------------------------------------------------

HISTORY_MINUTE_API = (
    "/uapi/domestic-stock/v1/quotations/"
    "inquire-time-dailychartprice"
)

HISTORY_TR_ID = "FHKST03010230"


# RSI 초기값 안정화를 위한 과거 거래일 수
HISTORY_TRADING_DAYS = 10

TOKEN_MAX_RETRIES = 5
DATA_MAX_RETRIES = 3

CONNECT_TIMEOUT = 10
READ_TIMEOUT = 30


# ============================================================
# 공통 빈 DataFrame
# ============================================================

def empty_minute_df():

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


# ============================================================
# Telegram
# ============================================================

def send_telegram(message):

    if not BOT_TOKEN or not CHAT_ID:

        print(
            "❌ BOT_TOKEN 또는 CHAT_ID가 없습니다."
        )

        print(
            f"BOT_TOKEN 존재 : {bool(BOT_TOKEN)}"
        )

        print(
            f"CHAT_ID 존재 : {bool(CHAT_ID)}"
        )

        return False

    url = (
        f"https://api.telegram.org/"
        f"bot{BOT_TOKEN}/sendMessage"
    )

    try:

        print(
            "📨 Telegram 전송 시도"
        )

        response = requests.post(
            url,
            data={
                "chat_id": CHAT_ID,
                "text": message,
            },
            timeout=15,
        )

        print(
            f"Telegram HTTP 상태코드 : "
            f"{response.status_code}"
        )

        print(
            f"Telegram 응답 : "
            f"{response.text}"
        )

        response.raise_for_status()

        data = response.json()

        if data.get("ok") is True:

            print(
                "✅ Telegram 전송 성공"
            )

            return True

        print(
            "❌ Telegram API 응답 실패"
        )

        return False

    except Exception as e:

        print(
            f"❌ Telegram 전송 실패 : {e}"
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

    url = (
        f"{BASE_URL}"
        f"{TOKEN_API}"
    )

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

            last_error = str(e)

            print(
                f"KIS 연결 시간 초과: {e}"
            )

        except requests.exceptions.ReadTimeout as e:

            last_error = str(e)

            print(
                f"KIS 응답 시간 초과: {e}"
            )

        except requests.exceptions.RequestException as e:

            last_error = str(e)

            print(
                f"KIS 네트워크 오류: {e}"
            )

        except Exception as e:

            last_error = str(e)

            print(
                f"예상하지 못한 오류: {e}"
            )

        if attempt < TOKEN_MAX_RETRIES:

            wait_seconds = (
                5 * attempt
            )

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
# KIS 공통 Header
# ============================================================

def get_kis_headers(
    token,
    tr_id,
):

    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
        "appkey": KIS_APP_KEY,
        "appsecret": KIS_APP_SECRET,
        "tr_id": tr_id,
        "custtype": "P",
    }


# ============================================================
# 당일분봉조회 1회
# FHKST03010200
# ============================================================

def get_today_minute_chunk(
    token,
    input_time,
):

    headers = get_kis_headers(
        token,
        TODAY_TR_ID,
    )

    params = {
        "FID_ETC_CLS_CODE": "",
        "FID_COND_MRKT_DIV_CODE": "J",
        "FID_INPUT_ISCD": SYMBOL,
        "FID_INPUT_HOUR_1": input_time,
        "FID_PW_DATA_INCU_YN": "Y",
    }

    last_error = None

    for attempt in range(
        1,
        DATA_MAX_RETRIES + 1
    ):

        try:

            print(
                f"당일분봉 조회 "
                f"(기준 {input_time}) "
                f"{attempt}/{DATA_MAX_RETRIES}"
            )

            response = requests.get(
                f"{BASE_URL}{TODAY_MINUTE_API}",
                headers=headers,
                params=params,
                timeout=(
                    CONNECT_TIMEOUT,
                    READ_TIMEOUT,
                ),
            )

            if response.status_code != 200:

                last_error = (
                    f"HTTP {response.status_code}\n"
                    f"{response.text}"
                )

                print(last_error)

            else:

                data = response.json()

                if data.get("rt_cd") != "0":

                    last_error = (
                        "KIS API 오류\n"
                        f"msg_cd: "
                        f"{data.get('msg_cd')}\n"
                        f"msg1: "
                        f"{data.get('msg1')}"
                    )

                    print(last_error)

                else:

                    rows = data.get(
                        "output2",
                        []
                    )

                    print(
                        f"당일분봉 수신: "
                        f"{len(rows)}개"
                    )

                    return rows

        except requests.exceptions.RequestException as e:

            last_error = str(e)

            print(
                f"네트워크 오류: {e}"
            )

        if attempt < DATA_MAX_RETRIES:

            time.sleep(
                3 * attempt
            )

    raise RuntimeError(
        "당일분봉 조회 실패\n"
        f"{last_error}"
    )


# ============================================================
# 오늘 1분봉 조회
# ============================================================

def get_today_minute_bars(
    token
):

    now = datetime.now(
        KST
    )

    today = now.date()

    market_open = datetime(
        today.year,
        today.month,
        today.day,
        9,
        0,
        0,
        tzinfo=KST,
    )

    market_close = datetime(
        today.year,
        today.month,
        today.day,
        15,
        30,
        0,
        tzinfo=KST,
    )

    # --------------------------------------------------------
    # 마지막 완성 30분봉 종료시각
    # --------------------------------------------------------

    if now.minute >= 30:

        latest_end = datetime(
            today.year,
            today.month,
            today.day,
            now.hour,
            30,
            0,
            tzinfo=KST,
        )

    else:

        latest_end = datetime(
            today.year,
            today.month,
            today.day,
            now.hour,
            0,
            0,
            tzinfo=KST,
        )

    if latest_end > market_close:

        latest_end = market_close

    if latest_end <= market_open:

        return empty_minute_df()

    all_rows = []

    # --------------------------------------------------------
    # 당일분봉 API 호출
    # --------------------------------------------------------

    anchor = (
        market_open
        + timedelta(minutes=30)
    )

    while anchor <= latest_end:

        input_time = (
            anchor.strftime("%H%M%S")
        )

        rows = get_today_minute_chunk(
            token,
            input_time,
        )

        all_rows.extend(
            rows
        )

        anchor += timedelta(
            minutes=30
        )

        time.sleep(0.3)

    # --------------------------------------------------------
    # DataFrame
    # --------------------------------------------------------

    records = []

    for row in all_rows:

        date_value = row.get(
            "stck_bsop_date"
        )

        time_value = row.get(
            "stck_cntg_hour"
        )

        if not date_value:
            continue

        if not time_value:
            continue

        try:

            dt = datetime.strptime(
                f"{date_value}{time_value}",
                "%Y%m%d%H%M%S",
            ).replace(
                tzinfo=KST
            )

            if dt < market_open:
                continue

            if dt >= market_close:
                continue

            if dt >= now:
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

        return empty_minute_df()

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
        "========================================"
    )

    print(
        "★ 오늘 데이터"
    )

    print(
        "★ KIS 당일분봉조회 "
        "FHKST03010200"
    )

    print(
        f"1분봉 : {len(df)}개"
    )

    print(
        f"시작 : "
        f"{df['datetime'].iloc[0]}"
    )

    print(
        f"마지막 : "
        f"{df['datetime'].iloc[-1]}"
    )

    print(
        "========================================"
    )

    return df


# ============================================================
# 과거 특정 거래일 1분봉
# FHKST03010230
# ============================================================

def get_history_minute_bars_for_date(
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
            f"과거 거래일 분봉 "
            f"{page + 1}/10 "
            f"(기준 {current_time})"
        )

        headers = get_kis_headers(
            token,
            HISTORY_TR_ID,
        )

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
                    f"{BASE_URL}{HISTORY_MINUTE_API}",
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

            except requests.exceptions.RequestException as e:

                last_error = str(e)

            if attempt < DATA_MAX_RETRIES:

                time.sleep(
                    3 * attempt
                )

        if not success:

            raise RuntimeError(
                f"{date_str} "
                f"과거분봉 조회 실패\n"
                f"{last_error}"
            )

        data = response.json()

        if data.get("rt_cd") != "0":

            raise RuntimeError(
                f"{date_str} KIS API 오류\n"
                f"msg_cd: "
                f"{data.get('msg_cd')}\n"
                f"msg1: "
                f"{data.get('msg1')}"
            )

        rows = data.get(
            "output2",
            []
        )

        if not rows:

            break

        all_rows.extend(
            rows
        )

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

        oldest_time = min(
            times
        )

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

            market_open = datetime(
                target_date.year,
                target_date.month,
                target_date.day,
                9,
                0,
                0,
                tzinfo=KST,
            )

            market_close = datetime(
                target_date.year,
                target_date.month,
                target_date.day,
                15,
                30,
                0,
                tzinfo=KST,
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

        return empty_minute_df()

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
        f"{len(df)}개"
    )

    return df


# ============================================================
# 가장 최근 실제 거래일 찾기
# ============================================================

def get_latest_trading_day(
    token,
    start_date=None,
):

    if start_date is None:

        start_date = (
            datetime.now(
                KST
            ).date()
        )

    candidate = start_date

    for _ in range(20):

        if candidate.weekday() < 5:

            print(
                "실제 거래일 확인: "
                f"{candidate}"
            )

            try:

                df = (
                    get_history_minute_bars_for_date(
                        token,
                        candidate,
                    )
                )

                if not df.empty:

                    print(
                        "★ 가장 최근 거래일:"
                        f" {candidate}"
                    )

                    return (
                        candidate,
                        df,
                    )

            except Exception as e:

                print(
                    f"{candidate} "
                    f"거래일 확인 실패: {e}"
                )

        candidate -= timedelta(
            days=1
        )

    raise RuntimeError(
        "최근 실제 거래일을 "
        "찾지 못했습니다."
    )


# ============================================================
# RSI 초기 계산용 과거 데이터
# ============================================================

def get_history_minute_bars(
    token,
    end_date,
):

    frames = []

    current_date = (
        end_date
        - timedelta(days=1)
    )

    checked_days = 0

    while (
        checked_days < 20
        and len(frames)
        < HISTORY_TRADING_DAYS
    ):

        if current_date.weekday() < 5:

            try:

                df = (
                    get_history_minute_bars_for_date(
                        token,
                        current_date,
                    )
                )

                if not df.empty:

                    frames.append(
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

    if not frames:

        raise RuntimeError(
            "RSI 초기 계산용 "
            "과거 데이터가 없습니다."
        )

    result = pd.concat(
        frames,
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

    print(
        "========================================"
    )

    print(
        "★ RSI 초기값용 과거 데이터"
    )

    print(
        f"과거 1분봉 : "
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

    print(
        "========================================"
    )

    return result


# ============================================================
# 1분봉 → 30분봉
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

    # --------------------------------------------------------
    # 정규장
    # --------------------------------------------------------

    data = data.between_time(
        "09:00",
        "15:29",
        inclusive="both",
    )

    if data.empty:

        return pd.DataFrame()

    # --------------------------------------------------------
    # 30분봉
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # 15:00~15:30까지만
    # --------------------------------------------------------

    bars = bars[
        bars.index.time
        <
        datetime.strptime(
            "15:30",
            "%H:%M",
        ).time()
    ]

    # --------------------------------------------------------
    # 완성된 30분봉만 사용
    # --------------------------------------------------------

    completed = []

    for timestamp in bars.index:

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

            continue

        segment = data[
            (data.index >= timestamp)
            &
            (data.index < end_time)
        ]

        if segment.empty:

            continue

        expected_last = (
            end_time
            - timedelta(minutes=1)
        )

        actual_last = (
            segment.index.max()
        )

        if actual_last < expected_last:

            continue

        completed.append(
            timestamp
        )

    if not completed:

        return pd.DataFrame()

    return bars.loc[
        completed
    ]


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
    bars,
    target_date=None,
):

    if bars.empty:

        raise RuntimeError(
            "30분봉 데이터가 없습니다."
        )

    data = bars.copy()

    if target_date is not None:

        data = data[
            data.index.date
            == target_date
        ]

    if data.empty:

        raise RuntimeError(
            "대상 거래일의 "
            "30분봉이 없습니다."
        )

    timestamp = data.index[-1]

    return (
        timestamp,
        data.loc[timestamp],
    )


# ============================================================
# 30분봉 시간 표시
# ============================================================

def format_30m_period(
    timestamp
):

    if timestamp.tzinfo is None:

        timestamp = timestamp.replace(
            tzinfo=KST
        )

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
# RSI 확인 + 알람
#
# ★ 변경사항
#
# RSI 35 이하:
# → 현재 RSI <= 35 이면 알림
#
# RSI 70 이상:
# → 현재 RSI >= 70 이면 알림
#
# 이전 RSI 값은 표시만 하고
# 진입 여부 판단에는 사용하지 않음
# ============================================================

def check_rsi(
    bars,
    target_date,
    data_source,
):

    data = bars.copy()

    data["RSI"] = (
        calculate_rsi_wilder(
            data["close"],
            RSI_LENGTH,
        )
    )

    timestamp, current = (
        get_last_completed_bar(
            data,
            target_date,
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

    period_text = (
        format_30m_period(
            timestamp
        )
    )

    print(
        "========================================"
    )

    print(
        "★ 최종 RSI"
    )

    print(
        "========================================"
    )

    print(
        f"데이터 날짜 : "
        f"{target_date}"
    )

    print(
        f"데이터 출처 : "
        f"{data_source}"
    )

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

    print(
        "========================================"
    )

    # ========================================================
    # 현재 RSI 상태
    # ========================================================

    if current_rsi <= OVERSOLD_LEVEL:

        status = (
            f"🟢 RSI "
            f"{OVERSOLD_LEVEL:.0f} 이하"
        )

    elif current_rsi >= OVERBOUGHT_LEVEL:

        status = (
            f"🔴 RSI "
            f"{OVERBOUGHT_LEVEL:.0f} 이상"
        )

    else:

        status = "⚪ 정상 구간"

    print(
        f"현재 상태 : {status}"
    )

    print(
        "========================================"
    )

    # ========================================================
    # TEST MODE
    # ========================================================

    if TEST_MODE:

        message = (
            "🧪 삼성전자 30분봉 RSI 테스트\n\n"
            f"종목 : "
            f"{SYMBOL_NAME} ({SYMBOL})\n"
            "주기 : 30분봉\n"
            "지표 : RSI(14)\n\n"
            f"데이터 날짜 : "
            f"{target_date}\n"
            f"데이터 출처 : "
            f"{data_source}\n\n"
            f"30분봉 : "
            f"{period_text}\n"
            f"종가 : "
            f"{close:,.0f}원\n\n"
            f"RSI(14) : "
            f"{current_rsi:.2f}\n"
            f"이전 RSI : "
            f"{previous_rsi:.2f}\n\n"
            f"{status}\n\n"
            "※ 완성된 30분봉 기준"
        )

        result = send_telegram(
            message
        )

        print(
            f"TEST Telegram 결과 : "
            f"{result}"
        )

        return

    # ========================================================
    # RSI 35 이하
    #
    # ★ 이전 RSI와 관계없이
    # ★ 현재 RSI가 35 이하이면 알림
    # ========================================================

    if current_rsi <= OVERSOLD_LEVEL:

        message = (
            "🟢 삼성전자 RSI 35 이하\n\n"
            f"종목 : "
            f"{SYMBOL_NAME} ({SYMBOL})\n"
            "주기 : 30분봉\n"
            "지표 : RSI(14)\n\n"
            f"데이터 날짜 : "
            f"{target_date}\n"
            f"데이터 출처 : "
            f"{data_source}\n\n"
            f"30분봉 : "
            f"{period_text}\n"
            f"종가 : "
            f"{close:,.0f}원\n"
            f"RSI(14) : "
            f"{current_rsi:.2f}\n"
            f"이전 RSI : "
            f"{previous_rsi:.2f}\n\n"
            "📉 현재 RSI가 35 이하입니다.\n\n"
            "※ 완성된 30분봉 기준"
        )

        result = send_telegram(
            message
        )

        print(
            f"🟢 RSI 35 이하 Telegram 결과 : "
            f"{result}"
        )

        return

    # ========================================================
    # RSI 70 이상
    #
    # ★ 이전 RSI와 관계없이
    # ★ 현재 RSI가 70 이상이면 알림
    # ========================================================

    elif current_rsi >= OVERBOUGHT_LEVEL:

        message = (
            "🔴 삼성전자 RSI 70 이상\n\n"
            f"종목 : "
            f"{SYMBOL_NAME} ({SYMBOL})\n"
            "주기 : 30분봉\n"
            "지표 : RSI(14)\n\n"
            f"데이터 날짜 : "
            f"{target_date}\n"
            f"데이터 출처 : "
            f"{data_source}\n\n"
            f"30분봉 : "
            f"{period_text}\n"
            f"종가 : "
            f"{close:,.0f}원\n"
            f"RSI(14) : "
            f"{current_rsi:.2f}\n"
            f"이전 RSI : "
            f"{previous_rsi:.2f}\n\n"
            "📈 현재 RSI가 70 이상입니다.\n\n"
            "※ 완성된 30분봉 기준"
        )

        result = send_telegram(
            message
        )

        print(
            f"🔴 RSI 70 이상 Telegram 결과 : "
            f"{result}"
        )

        return

    # ========================================================
    # 정상 구간
    # ========================================================

    print(
        "RSI 35 이하 / 70 이상 조건 없음"
    )


# ============================================================
# 실행 시간
#
# 일반 모드:
# 09:31 ~ 15:31
#
# TEST_MODE:
# 시간 제한 없음
# ============================================================

def is_allowed_to_run():

    now = datetime.now(
        KST
    )

    # --------------------------------------------------------
    # 테스트 모드
    # --------------------------------------------------------

    if TEST_MODE:

        print(
            "TEST_MODE=True"
        )

        print(
            "→ 실행 시간 제한 없음"
        )

        return True

    # --------------------------------------------------------
    # 일반 모드
    # --------------------------------------------------------

    if now.weekday() >= 5:

        print(
            "주말 → 일반 실행 안 함"
        )

        return False

    current_minutes = (
        now.hour * 60
        + now.minute
    )

    # ★ 09:31 시작
    start_minutes = (
        9 * 60 + 31
    )

    # ★ 15:31 마지막 실행
    end_minutes = (
        15 * 60 + 31
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
# 대상 데이터 결정
#
# 평일 TEST_MODE
# → 오늘 당일분봉
#
# 평일 일반
# → 오늘 당일분봉
#
# 주말 TEST_MODE
# → 가장 최근 실제 거래일
# ============================================================

def get_target_data(
    token
):

    now = datetime.now(
        KST
    )

    today = now.date()

    # ========================================================
    # 평일
    # ========================================================

    if today.weekday() < 5:

        print(
            "★ 평일"
        )

        print(
            f"★ 대상 날짜 : {today}"
        )

        print(
            "★ 오늘 당일분봉조회 사용"
        )

        today_df = (
            get_today_minute_bars(
                token
            )
        )

        if today_df.empty:

            raise RuntimeError(
                "오늘 당일분봉 데이터가 없습니다."
            )

        return (
            today,
            today_df,
            "KIS 당일분봉조회 "
            "FHKST03010200",
        )

    # ========================================================
    # 주말
    # ========================================================

    if TEST_MODE:

        print(
            "★ 주말 TEST_MODE"
        )

        print(
            "→ 가장 최근 실제 거래일의 1분봉 사용"
        )

        latest_date, latest_df = (
            get_latest_trading_day(
                token,
                today - timedelta(days=1),
            )
        )

        return (
            latest_date,
            latest_df,
            "KIS 과거 거래일 1분봉조회 "
            "FHKST03010230 "
            "(최근 거래일)",
        )

    # 일반 모드 주말
    return (
        None,
        empty_minute_df(),
        "주말 일반 실행 안 함",
    )


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
        "========================================"
    )

    print(
        "RSI : Wilder RSI(14)"
    )

    print(
        "알림 : RSI 35 이하"
    )

    print(
        "알림 : RSI 70 이상"
    )

    print(
        "30분봉 : 09:00~15:30"
    )

    print(
        "실행 : 09:31~15:31"
    )

    print(
        "평일 TEST → 당일 데이터"
    )

    print(
        "주말 TEST → 최근 거래일 1분봉"
    )

    print(
        f"TEST_MODE : {TEST_MODE}"
    )

    print(
        "========================================"
    )

    print(
        f"실행시각 : "
        f"{start.strftime('%Y-%m-%d %H:%M:%S')}"
    )

    print(
        "========================================"
    )

    # --------------------------------------------------------
    # 실행 가능 여부
    # --------------------------------------------------------

    if not is_allowed_to_run():

        return

    # --------------------------------------------------------
    # KIS Token
    # --------------------------------------------------------

    token = get_access_token()

    # --------------------------------------------------------
    # 대상 날짜 + 데이터
    # --------------------------------------------------------

    target_date, target_df, data_source = (
        get_target_data(
            token
        )
    )

    if target_date is None:

        return

    # --------------------------------------------------------
    # RSI 초기값용 과거 데이터
    # --------------------------------------------------------

    history_df = (
        get_history_minute_bars(
            token,
            target_date,
        )
    )

    # --------------------------------------------------------
    # 과거 + 대상일
    # --------------------------------------------------------

    all_df = pd.concat(
        [
            history_df,
            target_df,
        ],
        ignore_index=True,
    )

    all_df = (
        all_df
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
        "========================================"
    )

    print(
        f"전체 1분봉 : "
        f"{len(all_df)}개"
    )

    print(
        f"전체 시작 : "
        f"{all_df['datetime'].iloc[0]}"
    )

    print(
        f"전체 마지막 : "
        f"{all_df['datetime'].iloc[-1]}"
    )

    print(
        "========================================"
    )

    # --------------------------------------------------------
    # 30분봉 생성
    # --------------------------------------------------------

    bars = make_30m_bars(
        all_df
    )

    print(
        f"생성된 완성 30분봉 : "
        f"{len(bars)}개"
    )

    if bars.empty:

        raise RuntimeError(
            "30분봉 생성 실패"
        )

    # --------------------------------------------------------
    # 대상일 30분봉 확인
    # --------------------------------------------------------

    target_bars = bars[
        bars.index.date
        == target_date
    ]

    if target_bars.empty:

        raise RuntimeError(
            f"{target_date} "
            "30분봉이 없습니다."
        )

    print(
        f"대상일 30분봉 : "
        f"{len(target_bars)}개"
    )

    print(
        "마지막 대상 봉 : "
        f"{format_30m_period(target_bars.index[-1])}"
    )

    # --------------------------------------------------------
    # RSI 계산 + Telegram
    # --------------------------------------------------------

    check_rsi(
        bars,
        target_date,
        data_source,
    )

    elapsed = (
        datetime.now(KST)
        - start
    ).total_seconds()

    print(
        "========================================"
    )

    print(
        f"총 실행시간 : "
        f"{elapsed:.1f}초"
    )

    print(
        "========================================"
    )


# ============================================================
# 실행
# ============================================================

if __name__ == "__main__":

    try:

        main()

    except Exception as e:

        print(
            "========================================"
        )

        print(
            f"최종 오류 : {e}"
        )

        print(
            "========================================"
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
