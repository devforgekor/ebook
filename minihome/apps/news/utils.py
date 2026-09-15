#!/usr/bin/env python3
"""Shared utility functions for news modules."""


def has_chinese(text: str) -> bool:
    """Return True if text contains CJK ideographs (Chinese / Hanja)."""
    if not text:
        return False
    for ch in text:
        cp = ord(ch)
        if 0x3400 <= cp <= 0x9FFF or 0xF900 <= cp <= 0xFAFF:
            return True
    return False
