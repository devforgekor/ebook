#!/usr/bin/env python3
"""Tests for collector module."""

import json
import sys
import os
from pathlib import Path
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestFetchRss:
    """Tests for _fetch_rss function."""

    def test_parse_rss_2_0(self):
        from collector import _fetch_rss
        
        mock_feed = MagicMock()
        mock_feed.entries = [
            {"title": "Test Article", "link": "https://example.com/1", "published": "Mon, 25 Aug 2026 10:00:00 +0000"},
            {"title": "Test Article 2", "link": "https://example.com/2", "published": "Tue, 26 Aug 2026 12:00:00 +0000"},
        ]
        
        with patch('feedparser.parse', return_value=mock_feed):
            items = _fetch_rss("https://example.com/rss", max_articles=5)
            
            assert len(items) == 2
            assert items[0]["title"] == "Test Article"
            assert items[0]["url"] == "https://example.com/1"

    def test_empty_feed(self):
        from collector import _fetch_rss
        
        mock_feed = MagicMock()
        mock_feed.entries = []
        
        with patch('feedparser.parse', return_value=mock_feed):
            items = _fetch_rss("https://example.com/rss")
            assert items == []

    def test_fetch_error_returns_empty(self):
        from collector import _fetch_rss
        
        with patch('feedparser.parse', side_effect=Exception("Network error")):
            items = _fetch_rss("https://example.com/rss")
            assert items == []


class TestParseDate:
    """Tests for _parse_date function."""

    def test_rfc_2822(self):
        from collector import _parse_date
        
        result = _parse_date("Mon, 25 Aug 2026 10:00:00 +0000")
        assert result is not None
        assert result.year == 2026
        assert result.month == 8
        assert result.day == 25

    def test_iso_8601(self):
        from collector import _parse_date
        
        result = _parse_date("2026-08-25T10:00:00+00:00")
        assert result is not None
        assert result.hour == 10

    def test_invalid_format_returns_none(self):
        from collector import _parse_date
        
        result = _parse_date("not a date")
        assert result is None


class TestNewsCollector:
    """Tests for NewsCollector class."""

    def test_init_loads_feeds(self):
        from collector import NewsCollector
        
        with patch('collector._load_feeds') as mock_load:
            mock_load.return_value = [{"name": "Test", "url": "http://test.com", "enabled": True}]
            
            collector = NewsCollector()
            assert len(collector.feeds) == 1

    def test_stats_initialized(self):
        from collector import NewsCollector
        
        with patch('collector._load_feeds', return_value=[]):
            collector = NewsCollector()
            assert collector._stats["feeds"] == 0
            assert collector._stats["saved"] == 0

    def test_dry_run_doesnt_save(self):
        from collector import NewsCollector
        
        mock_feed = {"name": "Test", "url": "http://test.com/rss", "category": "ai", "language": "en"}
        
        with patch('collector._load_feeds', return_value=[mock_feed]):
            collector = NewsCollector()
            
            with patch.object(collector, '_process_feed') as mock_process:
                collector.run(dry_run=True, limit=1)
                mock_process.assert_called_once()
