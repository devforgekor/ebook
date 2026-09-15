# [LEGACY] 이 파일은 더 이상 사용하지 않습니다. Redis Streams 기반 워커(workers/redis_worker.py)와 FastAPI API 서버(api/)를 사용하세요.
# 유지보수 및 테스트 목적 외에는 실행하지 마세요.
# lean 토큰 최적화 샘플 코드 (agora 표준)
import redis
import json
from config import DATA_DIR, LOG_DIR, REDIS_URL
from pathlib import Path

# Redis 연결
r = redis.Redis.from_url(REDIS_URL)

# 예시: 토큰 최적화 요청 큐 구독 및 처리
QUEUE_NAME = "lean:optimize"
RESULT_QUEUE = "lean:result"

def optimize_token(payload):
    # 실제 토큰 최적화 로직은 여기에 구현
    text = payload.get("text", "")
    # 예시: 단순 소문자 변환
    optimized = text.lower()
    return {"optimized": optimized}

def main():
    print("[lean] 토큰 최적화 큐 대기 중...")
    while True:
        _, msg = r.blpop(QUEUE_NAME)
        req = json.loads(msg)
        result = optimize_token(req["payload"])
        # 결과를 result 큐에 push
        r.rpush(RESULT_QUEUE, json.dumps({"msg_id": req["msg_id"], "result": result}))
        print(f"처리 완료: {req['msg_id']}")

if __name__ == "__main__":
    main()
