"""
공통 HTTP 클라이언트 (재시도 + 회로 차단기)
- httpx.AsyncClient 기반
- retry, timeout, circuit breaker 지원
"""
import httpx
import asyncio
from typing import Any, Dict, Optional, Callable

class CircuitBreaker:
    def __init__(self, fail_max=5, reset_timeout=30):
        self.fail_max = fail_max
        self.reset_timeout = reset_timeout
        self.fail_count = 0
        self.open_until = None

    def allow(self):
        if self.open_until is None:
            return True
        if asyncio.get_event_loop().time() > self.open_until:
            self.open_until = None
            self.fail_count = 0
            return True
        return False

    def record_failure(self):
        self.fail_count += 1
        if self.fail_count >= self.fail_max:
            self.open_until = asyncio.get_event_loop().time() + self.reset_timeout

    def record_success(self):
        self.fail_count = 0
        self.open_until = None

async def http_request(
    method: str,
    url: str,
    *,
    retries: int = 3,
    timeout: float = 10.0,
    circuit_breaker: Optional[CircuitBreaker] = None,
    client: Optional[httpx.AsyncClient] = None,
    **kwargs
) -> httpx.Response:
    """
    공통 HTTP 요청 함수 (재시도 + 회로 차단기)
    - method: "GET", "POST" 등
    - url: 요청 URL
    - retries: 재시도 횟수
    - timeout: 요청 타임아웃
    - circuit_breaker: 회로 차단기 인스턴스(선택)
    - client: 외부에서 httpx.AsyncClient 주입 가능
    - kwargs: httpx.AsyncClient.request에 전달
    """
    cb = circuit_breaker
    last_exc = None
    for attempt in range(1, retries + 1):
        if cb and not cb.allow():
            raise RuntimeError("Circuit breaker is open")
        try:
            _client = client or httpx.AsyncClient()
            async with _client as ac:
                resp = await ac.request(method, url, timeout=timeout, **kwargs)
                resp.raise_for_status()
            if cb:
                cb.record_success()
            return resp
        except Exception as e:
            last_exc = e
            if cb:
                cb.record_failure()
            if attempt == retries:
                raise
            await asyncio.sleep(2 ** (attempt - 1))  # exponential backoff
    raise last_exc
