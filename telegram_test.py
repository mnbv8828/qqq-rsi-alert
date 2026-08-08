import os
import requests

BOT_TOKEN = os.environ["BOT_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]

url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

response = requests.post(
    url,
    data={
        "chat_id": CHAT_ID,
        "text": "✅ QQQ 알림 봇 테스트 성공!\nGitHub Actions → Telegram 연결 정상입니다."
    },
    timeout=20
)

print(response.text)
response.raise_for_status()

print("텔레그램 테스트 메시지 전송 완료")
