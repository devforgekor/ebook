"""
Redis Streams 기반 lean 워커 (asyncio)
메시지 유실 방지, graceful shutdown, 데드레터 큐 지원
"""
import asyncio
from apps.lean.config_settings import settings
import json
import signal
from core.ai.token_utils import TokenOptimizer, OpenAITokenizer
from core.utils.logger import setup_logger

try:
    import aioredis
except ImportError:
    raise RuntimeError("aioredis 패키지가 필요합니다. 'pip install aioredis'로 설치하세요.")


# 환경변수/설정 (Pydantic Settings 기반)
REDIS_URL = settings.REDIS_URL
STREAM_NAME = settings.LEAN_STREAM
RESULT_STREAM = settings.LEAN_RESULT_STREAM
GROUP = settings.LEAN_GROUP
WORKER_COUNT = settings.LEAN_WORKER_COUNT
DEADLETTER_STREAM = settings.LEAN_DLQ


# 공통 로거 설정
logger = setup_logger(
    name="lean_worker",
    log_dir=Path(settings.LOG_DIR),
    level="DEBUG" if settings.DEBUG else "INFO"
)

shutdown_event = asyncio.Event()

def handle_signal():
    shutdown_event.set()

async def worker(worker_id: int):
    redis = await aioredis.from_url(REDIS_URL, decode_responses=True)
    logger.info(f"[시작] Worker {worker_id} 시작 (Consumer Group: {GROUP})")
    # Consumer Group 생성 (존재하지 않을 경우)
    try:
        await redis.xgroup_create(STREAM_NAME, GROUP, id="0", mkstream=True)
    except Exception:
        pass  # 이미 존재
    consumer = f"worker-{worker_id}"
    optimizer = TokenOptimizer(OpenAITokenizer())
    while not shutdown_event.is_set():
        try:
            entries = await redis.xreadgroup(GROUP, consumer, {STREAM_NAME: ">"}, count=1, block=5000)
            if not entries:
                continue
            for stream_name, messages in entries:
                for msg_id, fields in messages:
                    try:
                        req = json.loads(fields['request'])
                        optimized = optimizer.optimize(req['messages'])
                        await redis.xadd(RESULT_STREAM, {'result': json.dumps(optimized)})
                        await redis.xack(STREAM_NAME, GROUP, msg_id)
                        logger.info({
                            "event": "optimized",
                            "worker_id": worker_id,
                            "msg_id": msg_id,
                            "result_len": len(optimized)
                        })
                    except Exception as e:
                        # 데드레터로 이동
                        await redis.xadd(DEADLETTER_STREAM, {'request': fields['request'], 'error': str(e)})
                        await redis.xack(STREAM_NAME, GROUP, msg_id)
                        logger.error({
                            "event": "deadletter",
                            "worker_id": worker_id,
                            "msg_id": msg_id,
                            "error": str(e)
                        })
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error({
                "event": "worker_error",
                "worker_id": worker_id,
                "error": str(e)
            })
    logger.info(f"[종료] Worker {worker_id} graceful shutdown 완료")

async def main():
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, handle_signal)
    tasks = [asyncio.create_task(worker(i)) for i in range(WORKER_COUNT)]
    await asyncio.gather(*tasks)

if __name__ == "__main__":
    asyncio.run(main())
