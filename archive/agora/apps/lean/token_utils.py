"""
이 파일은 legacy입니다. 반드시 core/ai/token_utils.py를 사용하세요.
새로운 기능/테스트/운영은 core/ai/token_utils.py 기준으로 작성해야 합니다.
"""
"""
공용 토큰 및 텍스트 정리 유틸리티 (v2.0)
"""
import logging
import re
import unicodedata
from typing import Tuple, Optional, List, Union, Any

logger = logging.getLogger(__name__)

# Pre-compiled regex patterns for performance
_WS_PATTERN = re.compile(r'\s+')
_THOUGHT_PATTERN = re.compile(r'\[THOUGHT\](.*?)\[/THOUGHT\]', re.DOTALL)


def clean_text(text: str) -> str:
    """
    텍스트를 유니코드 정규화(NFC) 및 공백 정리하여 반환합니다.
    예: "  Hello   World  " -> "Hello World"
    """
    if not isinstance(text, str):
        return ""
    text = unicodedata.normalize('NFC', text)
    text = _WS_PATTERN.sub(' ', text)
    return text.strip()


def extract_reasoning(text: str, return_list: bool = False) -> Tuple[str, Optional[Union[str, List[str]]]]:
    """
    텍스트에서 [THOUGHT]...[/THOUGHT] 모든 구간을 분리하여 (본문, 생각로그) 형태로 반환합니다.
    중첩 태그는 지원하지 않으며, 닫히지 않은 태그는 무시하고 본문에 포함합니다.
    return_list=True 시 reasoning을 리스트로 반환합니다.
    """
    if not isinstance(text, str):
        return "", None

    reasoning_list = _THOUGHT_PATTERN.findall(text)
    cleaned = _THOUGHT_PATTERN.sub('', text)
    cleaned = clean_text(cleaned)

    if not reasoning_list:
        return cleaned, None

    if return_list:
        return cleaned, [clean_text(r) for r in reasoning_list]
    return cleaned, " ".join(clean_text(r) for r in reasoning_list)


# tiktoken availability check
try:
    import tiktoken
    _TIKTOKEN_AVAILABLE = True
except ImportError:
    _TIKTOKEN_AVAILABLE = False
    logger.warning("tiktoken not installed; using word count fallback (inaccurate).")


def count_tokens(
    messages: List[dict],
    model: str = "gpt-3.5-turbo-0613",
    fallback_korean_ratio: float = 2.5
) -> int:
    """
    메시지 리스트의 총 토큰 수를 계산합니다. OpenAI의 메시지 포맷에 따른 오버헤드를 반영합니다.
    참고: https://github.com/openai/openai-python/blob/main/chatml.md

    Args:
        messages: OpenAI 메시지 형식의 리스트.
        model: 사용할 모델명 (tiktoken 인코딩 선택 및 오버헤드 계산에 사용).
        fallback_korean_ratio: tiktoken 미설치 시 공백 기준 어절 수에 곱하는 토큰 근사 계수.
                             기본값은 한국어 문장을 보수적으로 추정하기 위한 2.5입니다.

    Returns:
        총 토큰 수 (정수).
    """
    if not isinstance(messages, list):
        raise ValueError("messages는 리스트여야 합니다.")
    if not messages:
        return 0

    # tiktoken available path
    if _TIKTOKEN_AVAILABLE:
        try:
            encoding = tiktoken.encoding_for_model(model)
        except (KeyError, Exception):
            encoding = tiktoken.get_encoding("cl100k_base")

        # Define per-model overheads
        if model in {
            "gpt-3.5-turbo-0613",
            "gpt-3.5-turbo-16k-0613",
            "gpt-4-0314",
            "gpt-4-32k-0314",
            "gpt-4-0613",
            "gpt-4-32k-0613",
        }:
            tokens_per_message = 3
            tokens_per_name = 1
        elif model == "gpt-3.5-turbo-0301":
            tokens_per_message = 4
            tokens_per_name = -1
        elif "gpt-3.5-turbo" in model:
            return count_tokens(messages, model="gpt-3.5-turbo-0613", fallback_korean_ratio=fallback_korean_ratio)
        elif "gpt-4" in model:
            return count_tokens(messages, model="gpt-4-0613", fallback_korean_ratio=fallback_korean_ratio)
        else:
            tokens_per_message = 3
            tokens_per_name = 1

        num_tokens = 0
        for message in messages:
            if not isinstance(message, dict):
                continue

            num_tokens += tokens_per_message

            if isinstance(message.get("name"), str):
                num_tokens += tokens_per_name

            content = message.get("content")
            if isinstance(content, str):
                num_tokens += len(encoding.encode(content))
            elif isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "text":
                        txt = part.get("text", "")
                        if isinstance(txt, str):
                            num_tokens += len(encoding.encode(txt))

        num_tokens += 3  # every reply is primed with <|start|>assistant<|message|>
        return num_tokens

    # Fallback path (tiktoken not installed)
    total = 0
    for msg in messages:
        if not isinstance(msg, dict):
            continue

        # Overhead per message - tiktoken 경로와 유사하게 맞춤
        total += 3
        if isinstance(msg.get("name"), str):
            total += 1

        content = msg.get("content")
        if isinstance(content, str):
            total += int(len(content.split()) * fallback_korean_ratio)
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    txt = part.get("text", "")
                    if isinstance(txt, str):
                        total += int(len(txt.split()) * fallback_korean_ratio)

    total += 3  # reply prime
    return total


def strip_internal_fields(messages: List[dict], fields=("reasoning",)) -> List[dict]:
    """
    전송 전에 내부 메타 필드를 제거합니다.
    예: strip_internal_fields(processed_msgs, fields=("reasoning",))
    """
    if not isinstance(messages, list):
        return []

    out = []
    for m in messages:
        if not isinstance(m, dict):
            out.append(m)
            continue
        out.append({k: v for k, v in m.items() if k not in fields})
    return out


def process_messages_for_token_saving(
    messages: List[dict],
    return_reasoning_list: bool = False
) -> List[dict]:
    """
    대화 메시지 리스트 전체를 순회하며 content를 정제(clean_text)하고,
    [THOUGHT] 구간을 reasoning 필드로 분리합니다.
    멀티모달 메시지(content가 리스트인 경우)의 text 파트만 처리하며,
    이미지/파일 등 다른 타입은 그대로 보존합니다.

    Args:
        messages: 원본 메시지 리스트.
        return_reasoning_list: True면 reasoning을 리스트로 저장.

    Returns:
        정제된 메시지 리스트 (원본은 변경되지 않음).
    """
    if not isinstance(messages, list):
        return []

    processed_messages = []
    for msg in messages:
        if not isinstance(msg, dict) or "content" not in msg:
            processed_messages.append(msg)
            continue

        content = msg["content"]
        new_msg = msg.copy()

        # Case 1: content is a string (plain text)
        if isinstance(content, str):
            cleaned, reasoning = extract_reasoning(content, return_list=return_reasoning_list)
            new_msg["content"] = cleaned
            if reasoning is not None:
                new_msg["reasoning"] = reasoning
            processed_messages.append(new_msg)

        # Case 2: content is a list (multimodal)
        elif isinstance(content, list):
            new_parts = []
            collected_reasoning = []

            for part in content:
                # Only process text parts
                if (
                    isinstance(part, dict)
                    and part.get("type") == "text"
                    and isinstance(part.get("text"), str)
                ):
                    cleaned, reasoning = extract_reasoning(
                        part["text"],
                        return_list=return_reasoning_list
                    )
                    new_part = part.copy()
                    new_part["text"] = cleaned
                    new_parts.append(new_part)

                    if reasoning is not None:
                        if isinstance(reasoning, list):
                            collected_reasoning.extend(reasoning)
                        else:
                            collected_reasoning.append(reasoning)
                else:
                    # Preserve non-text parts (images, files, etc.)
                    new_parts.append(part)

            new_msg["content"] = new_parts
            if collected_reasoning:
                new_msg["reasoning"] = (
                    collected_reasoning
                    if return_reasoning_list
                    else " ".join(collected_reasoning)
                )
            processed_messages.append(new_msg)

        # Case 3: content is neither string nor list (unexpected) → keep as is
        else:
            processed_messages.append(new_msg)

    return processed_messages


# Explicitly declare public API
__all__ = [
    "clean_text",
    "extract_reasoning",
    "count_tokens",
    "strip_internal_fields",
    "process_messages_for_token_saving",
]
