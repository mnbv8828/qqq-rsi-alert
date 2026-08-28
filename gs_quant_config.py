# ============================================================
# GS QUANT CONFIG
# ============================================================

# QQQ는 Benchmark로만 사용
BENCHMARK = "QQQ"

# Stock Ranking 75점 이상만 표시
STOCK_SCORE_THRESHOLD = 75

# Nasdaq-100
NASDAQ100_URL = (
    "https://en.wikipedia.org/wiki/Nasdaq-100"
)

# Yahoo Finance
DATA_PERIOD = "2y"
MIN_BARS = 252

# Telegram
# 기존 QQQ 알림 봇의 Secrets 사용
BOT_TOKEN_ENV = "BOT_TOKEN"
CHAT_ID_ENV = "CHAT_ID"
