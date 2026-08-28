import os
import requests

from gs_quant_config import (
    BOT_TOKEN_ENV,
    CHAT_ID_ENV,
)


def send_message(message):
    # GitHub Actions Secrets에서 가져오기
    token = os.environ.get(
        BOT_TOKEN_ENV
    )

    chat_id = os.environ.get(
        CHAT_ID_ENV
    )

    if not token:
        raise RuntimeError(
            f"Set {BOT_TOKEN_ENV} "
            "environment variable."
        )

    if not chat_id:
        raise RuntimeError(
            f"Set {CHAT_ID_ENV} "
            "environment variable."
        )

    url = (
        f"https://api.telegram.org/"
        f"bot{token}/sendMessage"
    )

    response = requests.post(
        url,
        json={
            "chat_id": chat_id,
            "text": message,
        },
        timeout=20,
    )

    response.raise_for_status()

    result = response.json()

    if not result.get("ok"):
        raise RuntimeError(
            f"Telegram API error: {result}"
        )

    return result
