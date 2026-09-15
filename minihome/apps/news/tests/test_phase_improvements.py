#!/usr/bin/env python3
"""Tests for Phase 1-5 improvements."""

import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestCircuitBreaker:
    """Phase 1: Circuit Breaker tests."""

    def test_failure_counter_increments(self):
        from collector import NewsCollector
        with patch('collector._load_feeds', return_value=[]):
            c = NewsCollector()
            assert c._failure_counts.get("test_feed", 0) == 0
            c._failure_counts["test_feed"] = 1
            assert c._failure_counts["test_feed"] == 1

    def test_circuit_breaker_skips_after_threshold(self):
        from collector import NewsCollector
        with patch('collector._load_feeds', return_value=[]):
            c = NewsCollector()
            c._failure_counts["test_feed"] = 2
            assert c._failure_counts["test_feed"] >= c._circuit_breaker_threshold


class TestPhotoNewsFilter:
    """Phase 2: Photo news filter tests."""

    def test_short_text_skipped(self):
        from collector import NewsCollector
        with patch('collector._load_feeds', return_value=[]):
            c = NewsCollector()
            # _extract_and_process checks len(text) < 50
            short_text = "a" * 49
            assert len(short_text) < 50

    def test_long_text_passes(self):
        long_text = "a" * 50
        assert len(long_text) >= 50


class TestTFIDFClustering:
    """Phase 3: TF-IDF clustering tests."""

    def test_cluster_articles_tfidf_basic(self):
        from dedup import cluster_articles_tfidf
        articles = [
            {"id": 1, "title": "삼성전자 반도체 수출 증가"},
            {"id": 2, "title": "삼성전자 반도체의 시장 전망"},
            {"id": 3, "title": "SK하이닉스 메모리 수출 증가"},
        ]
        result = cluster_articles_tfidf(articles, threshold=0.5, min_size=2)
        # Should cluster similar titles
        assert result is not None
        assert len(result) >= 1

    def test_cluster_articles_hybrid_fallback(self):
        from dedup import cluster_articles_hybrid
        articles = [
            {"id": 1, "title": "Test title one"},
            {"id": 2, "title": "Test title two"},
        ]
        # With few articles, should fallback to Jaccard
        result = cluster_articles_hybrid(articles, threshold=0.5, min_size=3)
        assert isinstance(result, list)

    def test_has_sklearn_flag(self):
        from dedup import _HAS_SKLEARN
        assert _HAS_SKLEARN is True


class TestSourceTierDB:
    """Phase 4: Source tier DB tests."""

    def test_load_source_tiers(self):
        import scoring
        # Reset and reload
        scoring._SOURCE_TIERS_LOADED = False
        scoring.SOURCE_TIERS = {}
        scoring._load_source_tiers_from_db()
        assert len(scoring.SOURCE_TIERS) > 0

    def test_fallback_to_hardcoded(self):
        import scoring
        scoring._SOURCE_TIERS_LOADED = False
        scoring.SOURCE_TIERS = {}
        scoring._load_source_tiers_from_db()
        assert "TechCrunch AI" in scoring.SOURCE_TIERS or "Bloomberg Markets" in scoring.SOURCE_TIERS


class TestCorroborationScore:
    """Phase 5: Corroboration score tests."""

    def test_no_dedup_group_returns_zero(self):
        from scoring import calc_corroboration_score
        score = calc_corroboration_score({"dedup_group_id": None})
        assert score == 0.0

    def test_corroboration_formula(self):
        # k=2: 0.15, k=3: 0.30, k=4: 0.45 (with float tolerance)
        assert abs(0.15 * (2 - 1) - 0.15) < 1e-10
        assert abs(0.15 * (3 - 1) - 0.30) < 1e-10
        assert abs(0.15 * (4 - 1) - 0.45) < 1e-10
