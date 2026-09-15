#!/usr/bin/env python3
"""Tests for translator module."""

import json
import sys
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestTranslateToKorean:
    """Tests for translate_to_korean function."""

    def test_basic_translation(self):
        from translator import translate_to_korean
        
        with patch('translator._call_openrouter') as mock_openrouter:
            mock_openrouter.return_value = json.dumps({
                "title_ko": "테스트 제목",
                "summary_ko": "테스트 요약",
                "highlights_ko": ["하이라이트1", "하이라이트2"]
            })
            
            result = translate_to_korean("Test Title", "Test Summary", ["Highlight 1"])
            
            assert result["title_ko"] == "테스트 제목"
            assert result["summary_ko"] == "테스트 요약"
            assert result["highlights_ko"] == ["하이라이트1", "하이라이트2"]

    def test_empty_response_returns_original(self):
        from translator import translate_to_korean
        
        with patch('translator._call_openrouter', return_value=""):
            result = translate_to_korean("Title", "Summary", ["H1"])
            
            # title_ko is empty to trigger retry (needs_summary)
            assert result["title_ko"] == ""
            assert result["summary_ko"] == "Summary"
            assert result["highlights_ko"] == ["H1"]
            assert result["_summary_fallback"] is True

    def test_json_parse_error_returns_original(self):
        from translator import translate_to_korean
        
        with patch('translator._call_openrouter', return_value="invalid json"):
            result = translate_to_korean("Title", "Summary", ["H1"])
            
            # title_ko is empty to trigger retry (needs_summary)
            assert result["title_ko"] == ""
            assert result["summary_ko"] == "Summary"
            assert result["highlights_ko"] == ["H1"]
            assert result["_summary_fallback"] is True

    def test_empty_highlights(self):
        from translator import translate_to_korean
        
        with patch('translator._call_openrouter') as mock_openrouter:
            mock_openrouter.return_value = json.dumps({
                "title_ko": "제목",
                "summary_ko": "요약",
                "highlights_ko": []
            })
            
            result = translate_to_korean("Title", "Summary", [])
            assert result["highlights_ko"] == []


class TestTranslateArticle:
    """Tests for translate_article function."""

    def test_korean_article_passthrough(self):
        from translator import translate_article
        
        article = {
            "title": "한글 제목",
            "summary": "한글 요약",
            "highlights": ["하이라이트"],
            "language": "ko"
        }
        
        result = translate_article(article)
        
        assert result["title_ko"] == "한글 제목"
        assert result["summary_ko"] == "한글 요약"
        assert result["highlights_ko"] == ["하이라이트"]

    def test_english_article_translated(self):
        from translator import translate_article
        
        article = {
            "title": "English Title",
            "summary": "English Summary",
            "highlights": ["English Highlight"],
            "language": "en"
        }
        
        with patch('translator.translate_to_korean') as mock_translate:
            mock_translate.return_value = {
                "title_ko": "영문 제목",
                "summary_ko": "영문 요약",
                "highlights_ko": ["영문 하이라이트"]
            }
            
            result = translate_article(article)
            
            mock_translate.assert_called_once()
            assert result["title_ko"] == "영문 제목"

    def test_missing_fields_handled(self):
        from translator import translate_article
        
        article = {
            "title": "Title",
            "language": "ko"
        }
        
        result = translate_article(article)
        
        assert result["title_ko"] == "Title"
        assert result["summary_ko"] == ""
        assert result["highlights_ko"] == []


class TestLoadSecrets:
    """Tests for secret loading functions."""

    def test_get_openrouter_keys_empty(self):
        from translator import _get_openrouter_keys
        
        with patch('builtins.open', side_effect=FileNotFoundError):
            keys = _get_openrouter_keys()
            assert keys == []
