#!/usr/bin/env python3
# Status: experimental
# Path: ebooklib/apps/backend/lib/text_clean.py
"""제목/작가 등 메타데이터 텍스트 정규화 — 수집 시점 오염 제거.

[WHY] 소스마다 제목에 작가·사이트 접미사를 붙이고(예: `제목 - 작가 | 뉴토끼`),
공백/특수문자가 섞여 들어온다. 저장 전에 정규화해 중복·검색 실패·표시 오류를 줄인다.
"""

from __future__ import annotations

import html as _html
import re
import unicodedata

# 사이트/플랫폼 접미사 (제목 뒤에 붙는 표기)
_SITE_SUFFIXES = (
    "뉴토끼", "북토끼", "문피아", "조아라", "네이버", "네이버시리즈", "시리즈",
    "카카오페이지", "카카오", "리디", "리디북스", "노벨피아", "미스터블루",
    "북큐브", "원스토어", "톡소다", "toki", "newtoki", "munpia", "joara",
)
# 작가 라벨 접두/접미
_AUTHOR_LABELS = (
    "작가", "글쓴이", "저자", "지은이", "집필", "원작", "author", "by",
)


def clean_text(value: str, *, max_len: int = 200) -> str:
    """기본 클린: HTML 엔티티 해제 → 제어문자/다중공백 제거 → NFC → trim."""
    if not value:
        return ""
    text = _html.unescape(str(value))
    # 제로폭/제어문자 제거
    text = "".join(
        ch for ch in text if unicodedata.category(ch) not in ("Cf", "Cc") or ch in "\t\n"
    )
    text = text.replace("\u00a0", " ").replace("\u3000", " ")
    text = re.sub(r"[\t\n\r]+", " ", text)
    text = re.sub(r"\s{2,}", " ", text).strip()
    text = _strip_quotes(text)
    return text[:max_len].strip()


def _strip_quotes(text: str) -> str:
    text = text.strip()
    for pair in (("「", "」"), ("『", "』"), ("《", "》"), ("〈", "〉"), ("‘", "’"),
                 ("“", "”"), ("'", "'"), ("'", "'"), ('"', '"'), ("[", "]"), ("(", ")")):
        if len(text) > 2 and text.startswith(pair[0]) and text.endswith(pair[1]):
            # Check if the brackets are properly balanced (not just first/last char)
            # by ensuring the opening bracket is not followed by another opening bracket
            # before the closing one
            open_char, close_char = pair
            inner = text[1:-1].strip()
            # Check if there's another opening bracket before the closing one
            # which would indicate nested/unbalanced brackets
            if open_char in inner:
                continue  # Not a simple quoted string, skip this pair
            # 괄호 안이 사이트/각주 표기면 통째로 제거, 아니면 내용 유지
            if inner and not any(s in inner.lower() for s in _SITE_SUFFIXES):
                return inner
            return ""
    return text


def clean_title(value: str) -> str:
    """제목: ` - 작가`, ` | 사이트`, `[사이트]`, 화수 접미 등 잔여 표기 제거."""
    text = clean_text(value)
    if not text:
        return ""
    # 앞머리 [사이트] / (사이트) 및 꼬리 [독점]·[완결] 등 마케팅 표기 제거
    text = re.sub(r"^\s*[\[(]([^\])]{1,20})[\])]\s*", "", text)
    text = re.sub(r"\s*[\[(](독점|단독|완결|무료|연재중|신작|19금|성인|BL|GL)[\])]\s*$", "", text)
    # ` - 화수` / ` N화` / ` N편` 등 회차 접미 제거 (dash 없이도 매칭)
    text = re.sub(r"\s*[-–—]?\s*\d{1,5}\s*(화|편|장|회)\s*$", "", text)
    # ` | 사이트` / ` - 사이트` 접미 제거
    text = re.split(r"\s*[|｜]\s*", text)[0]
    parts = re.split(r"\s+[-–—]\s+", text)
    if len(parts) >= 2:
        tail = parts[-1].strip()
        if any(s in tail.lower() for s in _SITE_SUFFIXES) or len(tail) <= 12:
            text = " - ".join(parts[:-1]).strip() or parts[0].strip()
    # 끝의 사이트명 단독 제거
    text = re.sub(
        r"\s*[-–—]?\s*(" + "|".join(map(re.escape, _SITE_SUFFIXES)) + r")\s*$",
        "",
        text,
        flags=re.I,
    )
    return clean_text(text)


def clean_author(value: str) -> str:
    """작가: 라벨 제거·다중 작가 정리·'미상' 통일(빈 값은 '' 유지)."""
    text = clean_text(value)
    if not text:
        return ""
    # `작가: 홍길동`, `글쓴이 - 홍길동` 등 라벨 제거
    text = re.sub(
        r"^\s*(" + "|".join(map(re.escape, _AUTHOR_LABELS)) + r")\s*[:：]?\s*[-–—]?\s*",
        "",
        text,
        flags=re.I,
    )
    # 괄호 부가설명 제거: `홍길동(작가)` → `홍길동`
    text = re.sub(r"\s*[\[(][^\])]*[\])]\s*$", "", text).strip()
    # 여러 작가 구분 정규화
    text = re.sub(r"\s*[,/·]\s*", ", ", text)
    if text in ("미상", "없음", "무명", "unknown", "N/A", "-"):
        return "미상"
    return clean_text(text)


def normalize_meta(meta: dict) -> dict:
    """meta dict의 title/author를 정규화(변경 시 새 dict 반환용으로 사용)."""
    if meta.get("title"):
        meta["title"] = clean_title(meta["title"])
    if meta.get("author"):
        meta["author"] = clean_author(meta["author"])
    return meta
