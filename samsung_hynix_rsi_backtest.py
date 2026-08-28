import os
import time
from datetime import datetime, timedelta, date
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import requests


# ============================================================
# 삼성전자 / SK하이닉스 30분봉 RSI 눌림매매 백테스트
#
# 전략:
#   1) 30분봉 RSI(14) <= 30 이 되는 봉의 종가에 1차 매수
#   2) 1차 매수가 대비 -5%, -10%, -15%에 각각 추가매수
#   3) 총 4회 동일 금액 분할매수
#   4) RSI(14) >= 70 이 되는 봉의 종가에 전량 매도
#
# 데이터:
#   한국투자증권(KIS) API 1분봉 -> 직접 30분봉 생성
#
# 주의:
#   본 백테스트는 "봉 종가 기준" 전략이다.
#   추가매수 가격이 한 30분봉 안에서 도달했는지는 1분봉의 low로 확인한다.
#   같은 30분봉에서 여러 단계가 동시에 도달하면 가격 레벨별로 체결한 것으로 계산한다.
# ============================================================


# ============================================================
# 환경변수
# ============================================================

KIS_APP_KEY = os.environ.get("KIS_APP_KEY")
KIS_APP_SECRET = os.environ.get("KIS_APP_SECRET")

# ------------------------------------------------------------
# 백테스트 기간
# 기본: 2026-01-01 ~ 오늘
# GitHub Actions 환경변수로 변경 가능
# ------------------------------------------------------------

START_DATE = os.environ.get("BACKTEST_START", "2026-01-01")
END_DATE = os.environ.get(
    "BACKTEST_END",
    datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d"),
)

# ------------------------------------------------------------
# 초기자금
# 1개 종목당 1,000만원을 기준으로 별도 계산
# ------------------------------------------------------------

INITIAL_CAPITAL = float(
    os.environ.get("INITIAL_CAPITAL", "10000000")
)

# ------------------------------------------------------------
# RSI 설정
# ------------------------------------------------------------

RSI_LENGTH = 14
OVERSOLD_LEVEL = 30.0
OVERBOUGHT_LEVEL = 70.0

# ------------------------------------------------------------
# 분할매수
# 1차 0%, 2차 -5%, 3차 -10%, 4차 -15%
# ------------------------------------------------------------

BUY_LEVELS = [0.00, -0.05, -0.10, -0.15]

# ============================================================
# KIS API
# ============================================================

KST = ZoneInfo("Asia/Seoul")

BASE_URL = "https://openapi.koreainvestment.com:9443"
TOKEN_API = "/oauth2/tokenP"
MINUTE_API = (
    "/uapi/domestic-stock/v1/quotations/"
    "inquire-time-dailychartprice"
)
TR_ID = "FHKST03010230"

TOKEN_MAX_RETRIES = 5
DATA_MAX_RETRIES = 3

CONNECT_TIMEOUT = 10
READ_TIMEOUT = 30

# KIS 호출 사이 최소 대기
API_SLEEP_SECONDS = 0.35

# 종목
SYMBOLS = {
    "삼성전자": "005930",
    "SK하이닉스": "000660",
}


# ============================================================
# 날짜 유틸
# ============================================================

def parse_date(value):
    return datetime.strptime(value, "%Y-%m-%d").date()


def daterange(start_date, end_date):
    current = start_date

    while current <= end_date:
        yield current
        current += timedelta(days=1)


# ============================================================
# KIS Access Token
# ============================================================

def get_access_token():
    if not KIS_APP_KEY:
        raise RuntimeError("KIS_APP_KEY가 없습니다.")

    if not KIS_APP_SECRET:
        raise RuntimeError("KIS_APP_SECRET가 없습니다.")

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

    for attempt in range(1, TOKEN_MAX_RETRIES + 1):
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

                token = data.get("access_token")

                if token:
                    print("KIS Access Token 발급 성공")
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

        except requests.exceptions.RequestException as e:
            last_error = str(e)
            print(f"KIS 네트워크 오류: {e}")

        if attempt < TOKEN_MAX_RETRIES:
            time.sleep(5 * attempt)

    raise RuntimeError(
        "KIS Access Token 발급 최종 실패\n"
        f"{last_error}"
    )


# ============================================================
# 하루치 1분봉 조회
# ============================================================

def get_minute_bars_for_date(
    token,
    symbol,
    target_date,
):
    date_str = target_date.strftime("%Y%m%d")

    all_rows = []

    # 15:30부터 역순으로 조회
    current_time = "153000"

    for page in range(15):

        print(
            f"{symbol} {date_str} "
            f"분봉 조회 {page + 1}/15 "
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
            "FID_INPUT_ISCD": symbol,
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
                    f"{attempt}/{DATA_MAX_RETRIES}: {e}"
                )

            if attempt < DATA_MAX_RETRIES:
                time.sleep(3 * attempt)

        if not success:
            raise RuntimeError(
                f"{symbol} {date_str} 분봉 조회 실패\n"
                f"{last_error}"
            )

        data = response.json()

        if data.get("rt_cd") != "0":
            print(
                f"KIS API 오류: "
                f"{data.get('msg_cd')} "
                f"{data.get('msg1')}"
            )
            break

        rows = data.get("output2", [])

        if not rows:
            break

        all_rows.extend(rows)

        times = [
            row.get("stck_cntg_hour", "")
            for row in rows
            if row.get("stck_cntg_hour")
        ]

        if not times:
            break

        oldest_time = min(times)

        if oldest_time <= "090000":
            break

        # 한 페이지가 짧으면 더 이상 과거 데이터가 없다고 판단
        if len(rows) < 100:
            break

        current_time = oldest_time

        time.sleep(API_SLEEP_SECONDS)

    records = []

    for row in all_rows:
        time_value = row.get("stck_cntg_hour")

        if not time_value:
            continue

        try:
            dt = datetime.strptime(
                f"{date_str}{time_value}",
                "%Y%m%d%H%M%S",
            ).replace(tzinfo=KST)

            records.append(
                {
                    "datetime": dt,
                    "open": float(row["stck_oprc"]),
                    "high": float(row["stck_hgpr"]),
                    "low": float(row["stck_lwpr"]),
                    "close": float(row["stck_prpr"]),
                    "volume": int(row["cntg_vol"]),
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

    df = pd.DataFrame(records)

    df = (
        df
        .drop_duplicates(subset=["datetime"])
        .sort_values("datetime")
        .reset_index(drop=True)
    )

    print(
        f"{symbol} {date_str} → "
        f"{len(df)}개 1분봉"
    )

    return df


# ============================================================
# 전체 기간 데이터 수집
# ============================================================

def get_historical_minute_bars(
    token,
    symbol,
    start_date,
    end_date,
):
    frames = []

    total_days = (
        end_date - start_date
    ).days + 1

    completed_days = 0

    for target_date in daterange(
        start_date,
        end_date,
    ):
        completed_days += 1

        # 토/일 제외
        if target_date.weekday() >= 5:
            continue

        print(
            "========================================"
        )
        print(
            f"{symbol} "
            f"{target_date} "
            f"({completed_days}/{total_days})"
        )
        print(
            "========================================"
        )

        try:
            df = get_minute_bars_for_date(
                token,
                symbol,
                target_date,
            )

            if not df.empty:
                frames.append(df)

        except Exception as e:
            print(
                f"{symbol} {target_date} "
                f"조회 실패: {e}"
            )

        time.sleep(API_SLEEP_SECONDS)

    if not frames:
        raise RuntimeError(
            f"{symbol} 기간 내 데이터를 "
            f"가져오지 못했습니다."
        )

    result = pd.concat(
        frames,
        ignore_index=True,
    )

    result = (
        result
        .drop_duplicates(subset=["datetime"])
        .sort_values("datetime")
        .reset_index(drop=True)
    )

    print(
        f"{symbol} 전체 1분봉: "
        f"{len(result):,}개"
    )

    return result


# ============================================================
# 1분봉 → 30분봉
# ============================================================

def make_30m_bars(df):
    data = df.copy()

    data = data.set_index("datetime")

    data = data.between_time(
        "09:00",
        "15:30",
        inclusive="both",
    )

    bars = (
        data
        .resample(
            "30min",
            origin="start_day",
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

    # 장 마감 후 생성되는 이상한 구간 제거
    bars = bars[
        (bars.index.time >= datetime.strptime(
            "09:00", "%H:%M"
        ).time())
        &
        (bars.index.time <= datetime.strptime(
            "15:00", "%H:%M"
        ).time())
    ]

    return bars


# ============================================================
# Wilder RSI
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

    gain = delta.clip(lower=0)

    loss = -delta.clip(upper=0)

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
        rs = avg_gain / avg_loss

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
        current_gain = gain.iloc[i]
        current_loss = loss.iloc[i]

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
            rs = avg_gain / avg_loss

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
# 단일 종목 백테스트
# ============================================================

def backtest_symbol(
    name,
    bars,
    initial_capital,
):
    data = bars.copy()

    data["RSI"] = calculate_rsi_wilder(
        data["close"],
        RSI_LENGTH,
    )

    # 각 분할매수에 사용할 금액
    tranche_cash = (
        initial_capital
        / len(BUY_LEVELS)
    )

    in_position = False

    first_entry_price = None

    filled_levels = []

    shares = 0.0
    invested = 0.0

    entry_time = None

    trades = []

    equity_points = []

    pending_entry = False

    for timestamp, row in data.iterrows():

        close = float(row["close"])
        low = float(row["low"])
        rsi = float(row["RSI"])

        if np.isnan(rsi):
            continue

        # ====================================================
        # 신규 진입
        # ====================================================

        if not in_position:

            if rsi <= OVERSOLD_LEVEL:

                first_entry_price = close

                entry_price = first_entry_price

                buy_cash = tranche_cash

                buy_shares = (
                    buy_cash
                    / entry_price
                )

                shares += buy_shares
                invested += buy_cash

                filled_levels = [0]

                in_position = True

                entry_time = timestamp

                pending_entry = True

                print(
                    f"[{name}] "
                    f"1차 매수 "
                    f"{timestamp} "
                    f"RSI={rsi:.2f} "
                    f"가격={entry_price:,.0f}"
                )

        # ====================================================
        # 추가매수
        # ====================================================

        if in_position:

            for level_index in range(
                1,
                len(BUY_LEVELS),
            ):

                if level_index in filled_levels:
                    continue

                target_price = (
                    first_entry_price
                    *
                    (
                        1.0
                        +
                        BUY_LEVELS[level_index]
                    )
                )

                # 1분봉 low 기준으로 해당 가격 도달 확인
                if low <= target_price:

                    buy_cash = tranche_cash

                    buy_shares = (
                        buy_cash
                        / target_price
                    )

                    shares += buy_shares
                    invested += buy_cash

                    filled_levels.append(
                        level_index
                    )

                    print(
                        f"[{name}] "
                        f"{level_index + 1}차 매수 "
                        f"{timestamp} "
                        f"가격={target_price:,.0f}"
                    )

            # =================================================
            # RSI 70 청산
            #
            # 신규 1차 매수 직후 같은 봉에서
            # RSI가 이미 70 이상인 비정상 상황은 제외
            # =================================================

            if (
                rsi >= OVERBOUGHT_LEVEL
                and len(filled_levels) > 0
                and not (
                    pending_entry
                    and rsi >= OVERBOUGHT_LEVEL
                )
            ):

                exit_price = close

                exit_value = (
                    shares
                    * exit_price
                )

                profit = (
                    exit_value
                    - invested
                )

                return_pct = (
                    profit
                    / invested
                    * 100.0
                )

                hold_hours = (
                    timestamp
                    - entry_time
                ).total_seconds() / 3600.0

                avg_buy_price = (
                    invested
                    / shares
                    if shares > 0
                    else 0
                )

                trades.append(
                    {
                        "종목": name,
                        "진입일": entry_time.strftime(
                            "%Y-%m-%d %H:%M"
                        ),
                        "청산일": timestamp.strftime(
                            "%Y-%m-%d %H:%M"
                        ),
                        "1차매수가": first_entry_price,
                        "평균매수가": avg_buy_price,
                        "청도가": exit_price,
                        "분할매수횟수": len(
                            filled_levels
                        ),
                        "투입금액": invested,
                        "청산금액": exit_value,
                        "손익": profit,
                        "수익률": return_pct,
                        "보유시간": hold_hours,
                        "최종RSI": rsi,
                    }
                )

                print(
                    f"[{name}] "
                    f"청산 {timestamp} "
                    f"RSI={rsi:.2f} "
                    f"수익률={return_pct:+.2f}%"
                )

                in_position = False
                first_entry_price = None
                filled_levels = []
                shares = 0.0
                invested = 0.0
                entry_time = None

        pending_entry = False

        # 미실현 자산
        if in_position:
            current_value = shares * close

            total_equity = (
                initial_capital
                - invested
                + current_value
            )

        else:
            total_equity = initial_capital

        equity_points.append(
            {
                "datetime": timestamp,
                "equity": total_equity,
            }
        )

    # ========================================================
    # 마지막에 포지션이 남아 있으면 별도 기록
    # ========================================================

    open_position = None

    if in_position:

        last_timestamp = data.index[-1]

        last_close = float(
            data["close"].iloc[-1]
        )

        current_value = (
            shares
            * last_close
        )

        unrealized_profit = (
            current_value
            - invested
        )

        unrealized_return = (
            unrealized_profit
            / invested
            * 100.0
        )

        avg_buy_price = (
            invested
            / shares
            if shares > 0
            else 0
        )

        open_position = {
            "종목": name,
            "진입일": entry_time.strftime(
                "%Y-%m-%d %H:%M"
            ),
            "마지막일": last_timestamp.strftime(
                "%Y-%m-%d %H:%M"
            ),
            "1차매수가": first_entry_price,
            "평균매수가": avg_buy_price,
            "현재가": last_close,
            "분할매수횟수": len(
                filled_levels
            ),
            "투입금액": invested,
            "평가금액": current_value,
            "미실현손익": unrealized_profit,
            "미실현수익률": unrealized_return,
        }

    trades_df = pd.DataFrame(trades)

    equity_df = pd.DataFrame(
        equity_points
    )

    if not equity_df.empty:

        equity_df["peak"] = (
            equity_df["equity"]
            .cummax()
        )

        equity_df["drawdown"] = (
            equity_df["equity"]
            / equity_df["peak"]
            - 1.0
        )

        max_drawdown = (
            equity_df["drawdown"].min()
            * 100.0
        )

    else:
        max_drawdown = 0.0

    return (
        trades_df,
        equity_df,
        open_position,
        max_drawdown,
    )


# ============================================================
# 통계 계산
# ============================================================

def summarize(
    name,
    trades_df,
    initial_capital,
    max_drawdown,
):
    if trades_df.empty:

        return {
            "종목": name,
            "거래횟수": 0,
            "승률": 0.0,
            "평균수익률": 0.0,
            "총실현손익": 0.0,
            "평균보유시간": 0.0,
            "최대수익률": 0.0,
            "최대손실률": 0.0,
            "최대MDD": max_drawdown,
            "최대분할매수": 0,
            "5%이상수익거래": 0,
        }

    wins = trades_df[
        trades_df["손익"] > 0
    ]

    summary = {
        "종목": name,
        "거래횟수": len(trades_df),
        "승률": (
            len(wins)
            / len(trades_df)
            * 100.0
        ),
        "평균수익률": trades_df[
            "수익률"
        ].mean(),
        "총실현손익": trades_df[
            "손익"
        ].sum(),
        "평균보유시간": trades_df[
            "보유시간"
        ].mean(),
        "최대수익률": trades_df[
            "수익률"
        ].max(),
        "최대손실률": trades_df[
            "수익률"
        ].min(),
        "최대MDD": max_drawdown,
        "최대분할매수": trades_df[
            "분할매수횟수"
        ].max(),
        "5%이상수익거래": len(
            trades_df[
                trades_df["수익률"] >= 5.0
            ]
        ),
    }

    return summary


# ============================================================
# 출력
# ============================================================

def print_summary(
    name,
    summary,
    open_position,
):
    print("")
    print("============================================================")
    print(f"📊 {name} 백테스트 결과")
    print("============================================================")

    print(
        f"거래횟수          : "
        f"{summary['거래횟수']}"
    )

    print(
        f"승률              : "
        f"{summary['승률']:.2f}%"
    )

    print(
        f"평균 수익률       : "
        f"{summary['평균수익률']:+.2f}%"
    )

    print(
        f"총 실현손익       : "
        f"{summary['총실현손익']:+,.0f}원"
    )

    print(
        f"평균 보유시간     : "
        f"{summary['평균보유시간']:.1f}시간"
    )

    print(
        f"최대 수익률       : "
        f"{summary['최대수익률']:+.2f}%"
    )

    print(
        f"최대 손실률       : "
        f"{summary['최대손실률']:+.2f}%"
    )

    print(
        f"최대 MDD          : "
        f"{summary['최대MDD']:.2f}%"
    )

    print(
        f"최대 분할매수     : "
        f"{summary['최대분할매수']}회"
    )

    print(
        f"5% 이상 수익거래  : "
        f"{summary['5%이상수익거래']}회"
    )

    if open_position:
        print("")
        print("⚠️ 기간 종료 시 미청산 포지션")

        print(
            f"진입일            : "
            f"{open_position['진입일']}"
        )

        print(
            f"평균매수가        : "
            f"{open_position['평균매수가']:,.0f}원"
        )

        print(
            f"현재가            : "
            f"{open_position['현재가']:,.0f}원"
        )

        print(
            f"분할매수횟수      : "
            f"{open_position['분할매수횟수']}회"
        )

        print(
            f"미실현손익        : "
            f"{open_position['미실현손익']:+,.0f}원"
        )

        print(
            f"미실현수익률      : "
            f"{open_position['미실현수익률']:+.2f}%"
        )


# ============================================================
# Telegram
# ============================================================

def send_telegram(message):
    bot_token = os.environ.get("BOT_TOKEN")
    chat_id = os.environ.get("CHAT_ID")

    if not bot_token or not chat_id:
        print(
            "BOT_TOKEN/CHAT_ID 없음 → "
            "Telegram 전송 생략"
        )
        return False

    url = (
        f"https://api.telegram.org/"
        f"bot{bot_token}/sendMessage"
    )

    try:
        response = requests.post(
            url,
            data={
                "chat_id": chat_id,
                "text": message,
            },
            timeout=20,
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
# Telegram 결과 메시지
# ============================================================

def make_telegram_message(
    start_date,
    end_date,
    summaries,
    open_positions,
):
    lines = []

    lines.append(
        "🧪 삼성전자 / SK하이닉스\n"
        "30분봉 RSI 눌림매매 백테스트"
    )

    lines.append("")
    lines.append(
        f"기간 : {start_date} ~ {end_date}"
    )

    lines.append(
        "전략 : RSI(14) ≤ 30 진입"
    )

    lines.append(
        "분할 : 0 / -5 / -10 / -15%"
    )

    lines.append(
        "청산 : RSI(14) ≥ 70"
    )

    for summary in summaries:

        lines.append("")
        lines.append(
            f"━━━━━━━━━━━━━━━━━━"
        )

        lines.append(
            f"📌 {summary['종목']}"
        )

        lines.append(
            f"거래 : {summary['거래횟수']}회"
        )

        lines.append(
            f"승률 : {summary['승률']:.1f}%"
        )

        lines.append(
            f"평균수익 : "
            f"{summary['평균수익률']:+.2f}%"
        )

        lines.append(
            f"실현손익 : "
            f"{summary['총실현손익']:+,.0f}원"
        )

        lines.append(
            f"MDD : "
            f"{summary['최대MDD']:.2f}%"
        )

        lines.append(
            f"5% 이상 : "
            f"{summary['5%이상수익거래']}회"
        )

    if open_positions:

        lines.append("")
        lines.append(
            "⚠️ 기간 종료 미청산"
        )

        for position in open_positions:

            lines.append(
                f"{position['종목']} "
                f"{position['미실현수익률']:+.2f}%"
            )

    return "\n".join(lines)


# ============================================================
# MAIN
# ============================================================

def main():

    start_date = parse_date(
        START_DATE
    )

    end_date = parse_date(
        END_DATE
    )

    if start_date > end_date:
        raise ValueError(
            "BACKTEST_START가 BACKTEST_END보다 "
            "늦습니다."
        )

    print("")
    print("============================================================")
    print("삼성전자 / SK하이닉스")
    print("30분봉 RSI 눌림매매 백테스트")
    print("============================================================")

    print(
        f"기간 : "
        f"{start_date} ~ {end_date}"
    )

    print(
        f"초기자금 : "
        f"{INITIAL_CAPITAL:,.0f}원 / 종목"
    )

    print(
        f"RSI : "
        f"{RSI_LENGTH}"
    )

    print(
        f"진입 : "
        f"RSI <= {OVERSOLD_LEVEL}"
    )

    print(
        f"분할 : "
        f"{BUY_LEVELS}"
    )

    print(
        f"청산 : "
        f"RSI >= {OVERBOUGHT_LEVEL}"
    )

    print("============================================================")

    token = get_access_token()

    summaries = []
    open_positions = []

    output_dir = "backtest_results"

    os.makedirs(
        output_dir,
        exist_ok=True,
    )

    for name, symbol in SYMBOLS.items():

        print("")
        print("############################################################")
        print(f"{name} ({symbol})")
        print("############################################################")

        minute_df = get_historical_minute_bars(
            token,
            symbol,
            start_date,
            end_date,
        )

        raw_filename = (
            f"{output_dir}/"
            f"{symbol}_1m_"
            f"{start_date}_{end_date}.csv"
        )

        minute_df.to_csv(
            raw_filename,
            index=False,
            encoding="utf-8-sig",
        )

        bars = make_30m_bars(
            minute_df
        )

        bars_filename = (
            f"{output_dir}/"
            f"{symbol}_30m_"
            f"{start_date}_{end_date}.csv"
        )

        bars.to_csv(
            bars_filename,
            encoding="utf-8-sig",
        )

        print(
            f"{name} 30분봉 : "
            f"{len(bars):,}개"
        )

        trades_df, equity_df, open_position, max_drawdown = (
            backtest_symbol(
                name,
                bars,
                INITIAL_CAPITAL,
            )
        )

        trades_filename = (
            f"{output_dir}/"
            f"{symbol}_trades_"
            f"{start_date}_{end_date}.csv"
        )

        trades_df.to_csv(
            trades_filename,
            index=False,
            encoding="utf-8-sig",
        )

        equity_filename = (
            f"{output_dir}/"
            f"{symbol}_equity_"
            f"{start_date}_{end_date}.csv"
        )

        equity_df.to_csv(
            equity_filename,
            index=False,
            encoding="utf-8-sig",
        )

        summary = summarize(
            name,
            trades_df,
            INITIAL_CAPITAL,
            max_drawdown,
        )

        summaries.append(summary)

        if open_position:
            open_positions.append(
                open_position
            )

        print_summary(
            name,
            summary,
            open_position,
        )

    summary_df = pd.DataFrame(
        summaries
    )

    summary_filename = (
        f"{output_dir}/"
        f"summary_"
        f"{start_date}_{end_date}.csv"
    )

    summary_df.to_csv(
        summary_filename,
        index=False,
        encoding="utf-8-sig",
    )

    print("")
    print("============================================================")
    print("📊 최종 요약")
    print("============================================================")

    print(
        summary_df.to_string(
            index=False
        )
    )

    print("")
    print(
        f"결과 파일 : "
        f"{output_dir}/"
    )

    message = make_telegram_message(
        start_date,
        end_date,
        summaries,
        open_positions,
    )

    send_telegram(message)


# ============================================================
# 실행
# ============================================================

if __name__ == "__main__":

    try:
        main()

    except Exception as e:

        print("")
        print("============================================================")
        print(f"❌ 최종 오류 : {e}")
        print("============================================================")

        raise
