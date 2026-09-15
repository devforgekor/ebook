from apps.chronicle.scripts.process_raw_chat_snapshots import extract_reasoning
from abc import ABC, abstractmethod
import asyncio
import re
import json
from pathlib import Path
from fastapi.concurrency import run_in_threadpool
from typing import Optional, Dict, Any
import httpx

# --- Tokenizer 추상 클래스 및 구현체 ---
class Tokenizer(ABC):
    @abstractmethod
    def count_tokens(self, text: str) -> int:
        """동기식 토큰 카운팅 (로컬 구현)"""
        pass

    async def count_tokens_async(self, text: str) -> int:
        """비동기 토큰 카운팅 (API 호출 등) - 기본 구현은 동기 함수를 스레드풀에서 실행"""
        return await run_in_threadpool(self.count_tokens, text)

class OpenAITokenizer(Tokenizer):
    def __init__(self, model="gpt-3.5-turbo"):
        try:
            import tiktoken
            self.encoding = tiktoken.encoding_for_model(model)
        except Exception:
            self.encoding = None

    def count_tokens(self, text: str) -> int:
        if self.encoding:
            return len(self.encoding.encode(text))
        return len(text.split())

class GeminiTokenizer(Tokenizer):
    def __init__(self, api_key=None):
        self.api_key = api_key
        # 실제 구현에서는 genai.Client 등 초기화

    def count_tokens(self, text: str) -> int:
        # fallback: 근사값 (글자 수 * 0.3)
        return int(len(text) * 0.3)

    async def count_tokens_async(self, text: str) -> int:
        # 실제 API 호출 필요시 구현
        await asyncio.sleep(0.01)
        return self.count_tokens(text)

# --- TokenOptimizer 클래스 (Tokenizer 주입) ---
class TokenOptimizer:
    def __init__(self, tokenizer: Tokenizer):
        self.tokenizer = tokenizer

    def optimize(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        # 예시: [THOUGHT] 제거 및 공백 정리
        optimized = []
        for msg in messages:
            text = msg.get('content', '')
            cleaned, _ = extract_reasoning(text)
            optimized.append({**msg, 'content': cleaned})
        return optimized

    def count_tokens(self, messages: List[Dict[str, Any]]) -> int:
        total = 0
        for msg in messages:
            text = msg.get('content', '')
            total += self.tokenizer.count_tokens(text)
        return total

    async def count_tokens_async(self, messages: List[Dict[str, Any]]) -> int:
        total = 0
        for msg in messages:
            text = msg.get('content', '')
            total += await self.tokenizer.count_tokens_async(text)
        return total
import re
import unicodedata
from typing import List, Dict, Any

def clean_text(text: str) -> str:
    """텍스트 정규화 및 공백 정리"""
    if not isinstance(text, str):
        return ""
    text = unicodedata.normalize('NFC', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

try:
    import tiktoken
    def count_tokens(messages: List[Dict[str, Any]], model: str = "gpt-3.5-turbo") -> int:
        try:
            enc = tiktoken.encoding_for_model(model)
        except Exception:
            enc = tiktoken.get_encoding("cl100k_base")
        total = 0
        for msg in messages:
            text = f"{msg.get('role', '')}: {msg.get('content', '')}"
            total += len(enc.encode(text))
        return total
except ImportError:
    def count_tokens(messages: List[Dict[str, Any]], model: str = None) -> int:
        total = 0
        for msg in messages:
            text = f"{msg.get('role', '')}: {msg.get('content', '')}"
            total += len(text.split())
        return total
