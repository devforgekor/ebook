#!/usr/bin/env python3
"""필터 호환 진입점. 실제 구현은 core.util.filters를 사용."""

from typing import Any, Dict

from neisync.core.util.filters import SubjectNameFilter, TextFilter

__all__ = ["TextFilter", "SubjectNameFilter"]

def filter_school(school: Dict[str, Any]) -> bool:
    """
    학교 정보 필터링 함수
    - 예: 폐교, 미인가, 기타 제외
    - True 반환 시 수집 대상
    """
    # 예시: 폐교/미인가 제외
    if school.get("status") in ("폐교", "미인가"):
        return False
    return True
