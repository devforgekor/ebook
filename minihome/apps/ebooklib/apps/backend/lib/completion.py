#!/usr/bin/env python3
# Status: experimental
# Path: ebooklib/apps/backend/lib/completion.py
"""완결 판정 — 다중 소스 신뢰도 + 마지막 회차 직접 검수.

[WHY] 플랫폼 상태(문피아 finished / 네이버 og 텍스트)는 지연·오판이 있다.
규칙:
1) 문피아 `finished`(bool) 우선, 없으면 네이버 상태(보조). 카카오 상태는 사용하지 않음.
2) 둘 중 하나라도 '완결'이면 **마지막 저장 회차 본문**을 직접 검수해 완결 신호를 확인한다.
3) 검수에서 완결 신호가 없으면 '연재중'으로 보수 판정(오판 방지).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# 본문 끝 완결 신호(작가 표기 관행)
_COMPLETION_MARKERS = ("완결", "fin.", "fin ", "the end", "작가의 말", "감사합니다", "외전", "후기")
_TAIL_CHARS = 400


def tail_completed(content: str) -> bool:
    """본문 끝부분에서 완결 신호를 찾는다(오탐 방지를 위해 끝 400자만 검사)."""
    if not content:
        return False
    tail = content[-_TAIL_CHARS:].lower()
    return any(m in tail for m in _COMPLETION_MARKERS)


def last_chapter_completed(novel_dir: str | Path) -> Optional[bool]:
    """가장 마지막(최고 화수) 저장 회차의 본문 끝으로 완결 신호 판정.

    Returns: True(완결 신호 있음) / False(없음) / None(회차 없음·읽기 실패)
    """
    d = Path(novel_dir)
    if not d.is_dir():
        return None
    files = [
        f for f in d.glob("*.json")
        if f.stem.isdigit()
    ]
    if not files:
        return None

    def chapter_key(p: Path):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            return int(data.get("chapter") or 0), int(p.stem)
        except Exception:
            return 0, int(p.stem) if p.stem.isdigit() else 0

    try:
        latest = max(files, key=chapter_key)
        data = json.loads(latest.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        logger.debug(f"마지막 회차 검수 실패: {e}")
        return None
    return tail_completed(data.get("content") or "")


def resolve_status(
    novel_dir: str | Path,
    munpia_status: Optional[str] = None,
    naver_status: Optional[str] = None,
    current: str = "unknown",
) -> tuple[str, str]:
    """다중 소스 상태 → 최종 상태와 근거(reason). 카카오 상태는 받지 않는다.

    - 문피아 완결 또는 네이버 완결 → 마지막 회차 검수(신호 있어야 완결)
    - 둘 다 연재중 → 연재중
    - 판단 불가 → current 유지
    """
    src = {}
    if munpia_status and munpia_status != "unknown":
        src["munpia"] = munpia_status
    if naver_status and naver_status != "unknown":
        src["naver"] = naver_status

    if not src:
        return current, "no_source"

    if any(v == "완결" for v in src.values()):
        verified = last_chapter_completed(novel_dir)
        if verified is True:
            return "완결", f"verified:last_chapter({','.join(src)})"
        if verified is False:
            # 플랫폼은 완결이라 하지만 본문에 신호 없음 → 보수적으로 연재중
            return "연재중", f"unverified:no_marker({','.join(src)})"
        return "완결", f"platform({','.join(src)})"  # 검수 불가 시 플랫폼 신뢰

    if all(v == "연재중" for v in src.values()):
        return "연재중", "platform:ongoing"
    return current, "ambiguous"
