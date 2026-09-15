import asyncio
import random
import time
from typing import Optional, Dict, Any
import httpx
from neisync.core.config import settings
from neisync.core.logging import get_logger

logger = get_logger('core.http')

RETRY_STATUS = {429, 500, 502, 503, 504}

class TokenBucket:
    def __init__(self, rate: float, capacity: int):
        self.rate = rate
        self.capacity = capacity
        self.tokens = capacity
        self.updated = time.monotonic()
        self.lock = asyncio.Lock()
    
    async def acquire(self, tokens: int = 1):
        async with self.lock:
            now = time.monotonic()
            delta = now - self.updated
            self.tokens = min(self.capacity, self.tokens + delta * self.rate)
            self.updated = now
            while self.tokens < tokens:
                wait = (tokens - self.tokens) / self.rate
                await asyncio.sleep(wait)
                now = time.monotonic()
                delta = now - self.updated
                self.tokens = min(self.capacity, self.tokens + delta * self.rate)
                self.updated = now
            self.tokens -= tokens

class HttpClient:
    def __init__(self, bucket_key: str = 'default'):
        self.bucket_key = bucket_key
        self.bucket = TokenBucket(settings.http_rate_per_sec, settings.http_burst)
        self.client = httpx.AsyncClient(timeout=settings.http_timeout)
        self.circuit = {"fail": 0, "open_until": 0.0}
    
    async def request(self, method: str, url: str, **kwargs) -> httpx.Response:
        now = time.monotonic()
        if now < self.circuit["open_until"]:
            raise RuntimeError("circuit-open")
        
        for attempt in range(settings.http_max_retries + 1):
            await self.bucket.acquire()
            start = time.monotonic()
            try:
                resp = await self.client.request(method, url, **kwargs)
                latency = (time.monotonic() - start) * 1000
                if resp.status_code in RETRY_STATUS:
                    if attempt == settings.http_max_retries:
                        self.circuit["fail"] += 1
                        if self.circuit["fail"] >= 5:
                            self.circuit["open_until"] = time.monotonic() + 60
                        raise httpx.HTTPStatusError(
                            f"max retries exceeded with status {resp.status_code}",
                            request=resp.request, response=resp
                        )
                    sleep = min(8.0, (2 ** attempt)) * (0.5 + random.random() / 2)
                    logger.warning(f"retry {attempt+1}/{settings.http_max_retries} after {sleep:.2f}s",
                                  extra={'url': url, 'status': resp.status_code})
                    await asyncio.sleep(sleep)
                    continue
                resp.raise_for_status()
                self.circuit["fail"] = 0
                logger.info(f"HTTP {resp.status_code}", extra={'url': url, 'latency_ms': round(latency, 2)})
                return resp
            except httpx.TimeoutException:
                latency = (time.monotonic() - start) * 1000
                if attempt == settings.http_max_retries:
                    self.circuit["fail"] += 1
                    if self.circuit["fail"] >= 5:
                        self.circuit["open_until"] = time.monotonic() + 60
                    raise
                sleep = min(8.0, (2 ** attempt)) * (0.5 + random.random() / 2)
                logger.warning(f"timeout, retry {attempt+1}", extra={'url': url})
                await asyncio.sleep(sleep)
            except httpx.HTTPStatusError as e:
                if e.response is not None and e.response.status_code not in RETRY_STATUS:
                    raise
    
    async def close(self):
        await self.client.aclose()

_http_clients: Dict[str, HttpClient] = {}

async def get_http_client(bucket_key: str = 'default') -> HttpClient:
    if bucket_key not in _http_clients:
        _http_clients[bucket_key] = HttpClient(bucket_key)
    return _http_clients[bucket_key]

async def close_all_clients():
    for client in _http_clients.values():
        await client.close()
