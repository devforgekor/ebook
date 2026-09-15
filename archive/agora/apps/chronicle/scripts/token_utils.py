"""
공용 토큰 및 텍스트 정리 유틸리티
"""
import re
import unicodedata

# 텍스트 정리 함수

def clean_text(text: str) -> str:
    """Normalize and clean text for chat dataset."""
    if not isinstance(text, str):
        return ""
    text = unicodedata.normalize('NFC', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

# 토큰 카운트 함수
try:
    import tiktoken
    def count_tokens(messages, model="gpt-3.5-turbo"):
        try:
            enc = tiktoken.encoding_for_model(model)
        except Exception:
            enc = tiktoken.get_encoding("cl100k_base")
        total = 0
        for msg in messages:
            text = (msg.get("role", "") + ": " + msg.get("content", ""))
            total += len(enc.encode(text))
        return total
except ImportError:
    def count_tokens(messages, model=None):
        total = 0
        for msg in messages:
            text = (msg.get("role", "") + ": " + msg.get("content", ""))
            total += len(text.split())
        return total
