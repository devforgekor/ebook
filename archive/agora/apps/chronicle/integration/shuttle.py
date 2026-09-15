def send_telegram_message(message: str, chat_id: str = None):
import os
import requests
import redis

def send_telegram_message(message: str):
    """
    1. HTTP API로 텔레그램 봇에 메시지 전송 시도
    2. 실패 시 Redis 큐에 메시지 백업(비동기 처리)
    """
    BOT_API_URL = os.getenv("TELEGRAM_BOT_API_URL", "http://localhost:8000/send")
    REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
    REDIS_QUEUE = os.getenv("REDIS_QUEUE", "telegram_queue")

    try:
        resp = requests.post(BOT_API_URL, json={"msg": message}, timeout=2)
        resp.raise_for_status()
        print("[텔레그램 HTTP 전송 성공]", resp.text)
    except Exception as e:
        print("[HTTP 실패, Redis 큐에 백업]", e)
        r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0)
        r.lpush(REDIS_QUEUE, message)
        print("[Redis 큐에 메시지 저장 완료]")

# 사용 예시
if __name__ == "__main__":
    send_telegram_message("테스트 메시지 from integration (HTTP+Redis)")
