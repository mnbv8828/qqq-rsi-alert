import io

import pandas as pd
import requests
import yfinance as yf

from gs_quant_config import (
    DATA_PERIOD,
    MIN_BARS,
)


# ============================================================
# Nasdaq-100 Universe
# ============================================================

WIKIPEDIA_API_URL = "https://en.wikipedia.org/w/api.php"

NASDAQ100_PAGE = "List_of_NASDAQ-100_companies"


def get_nasdaq100_tickers():
    """
    Wikipedia MediaWiki API에서 현재 Nasdaq-100 구성종목을
    자동으로 가져온다.

    일반 URL에 pd.read_html()을 직접 사용하는 방식 대신
    API → HTML → DataFrame 방식으로 처리하여
    GitHub Actions의 HTTP 403 / lxml URL 오류를 피한다.
    """

    headers = {
        "User-Agent": (
            "GS-Quant/1.0 "
            "(Nasdaq-100 stock ranking analyzer)"
        )
    }

    params = {
        "action": "parse",
        "page": NASDAQ100_PAGE,
        "prop": "text",
        "format": "json",
        "formatversion": "2",
    }

    response = requests.get(
        WIKIPEDIA_API_URL,
        params=params,
        headers=headers,
        timeout=30,
    )

    response.raise_for_status()

    data = response.json()

    if "parse" not in data:
        raise RuntimeError(
            "Wikipedia API did not return parsed page data."
        )

    html = data["parse"]["text"]

    # --------------------------------------------------------
    # API가 반환한 HTML을 DataFrame으로 변환
    # --------------------------------------------------------

    try:
        tables = pd.read_html(
            io.StringIO(html)
        )
    except Exception as e:
        raise RuntimeError(
            f"Could not parse Nasdaq-100 tables: {e}"
        ) from e

    # --------------------------------------------------------
    # Ticker 컬럼이 있는 Nasdaq-100 구성종목 테이블 찾기
    # --------------------------------------------------------

    for table in tables:

        if table.empty:
            continue

        # MultiIndex column 처리
        if isinstance(
            table.columns,
            pd.MultiIndex,
        ):
            columns = [
                " ".join(
                    str(x)
                    for x in col
                    if str(x) != "nan"
                ).strip()
                for col in table.columns
            ]
        else:
            columns = [
                str(col).strip()
                for col in table.columns
            ]

        ticker_col = None

        for original, normalized in zip(
            table.columns,
            columns,
        ):

            normalized_lower = (
                normalized.lower()
            )

            if (
                normalized_lower == "ticker"
                or "ticker" in normalized_lower
            ):
                ticker_col = original
                break

        if ticker_col is None:
            continue

        # ----------------------------------------------------
        # ticker 추출
        # ----------------------------------------------------

        tickers = (
            table[ticker_col]
            .astype(str)
            .str.strip()
            .str.upper()
        )

        cleaned = []

        for ticker in tickers:

            if not ticker:
                continue

            if ticker in {
                "NAN",
                "NONE",
                "TICKER",
            }:
                continue

            # Wikipedia 표에서 불필요한 문자 제거
            ticker = (
                ticker
                .replace("[1]", "")
                .replace("[2]", "")
                .strip()
            )

            # Yahoo Finance 형식
            # 예: BRK.B → BRK-B
            ticker = ticker.replace(
                ".",
                "-",
            )

            # 일반적인 미국 주식 ticker만 허용
            if (
                1 <= len(ticker) <= 6
                and ticker.replace(
                    "-",
                    "",
                ).isalnum()
            ):
                cleaned.append(ticker)

        cleaned = sorted(
            set(cleaned)
        )

        # Nasdaq-100은 약 100개 종목
        if len(cleaned) >= 90:

            print(
                f"Nasdaq-100 universe loaded: "
                f"{len(cleaned)} stocks"
            )

            return cleaned

    raise RuntimeError(
        "Could not obtain a valid Nasdaq-100 "
        "constituent list."
    )


# ============================================================
# Yahoo Finance Data
# ============================================================

def get_data(ticker):
    """
    Yahoo Finance에서 일봉 데이터를 가져온다.

    DATA_PERIOD:
        config.py의 DATA_PERIOD

    MIN_BARS:
        config.py의 MIN_BARS
    """

    df = yf.download(
        ticker,
        period=DATA_PERIOD,
        interval="1d",
        auto_adjust=True,
        progress=False,
    )

    if df is None or df.empty:
        return None

    # --------------------------------------------------------
    # yfinance MultiIndex 처리
    # --------------------------------------------------------

    if isinstance(
        df.columns,
        pd.MultiIndex,
    ):
        df.columns = (
            df.columns
            .get_level_values(0)
        )

    # --------------------------------------------------------
    # 필수 컬럼 확인
    # --------------------------------------------------------

    required = {
        "Open",
        "High",
        "Low",
        "Close",
        "Volume",
    }

    if not required.issubset(
        df.columns
    ):
        return None

    df = df[
        [
            "Open",
            "High",
            "Low",
            "Close",
            "Volume",
        ]
    ].dropna()

    # --------------------------------------------------------
    # 최소 봉 수 확인
    # --------------------------------------------------------

    if len(df) < MIN_BARS:
        return None

    return df
